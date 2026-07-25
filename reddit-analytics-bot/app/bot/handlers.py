import datetime
import json
import re

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
import httpx

from app.analytics import build_analytics
from app.config import Config
from app.db import Chat, Report, Search, get_or_create_chat, get_or_create_user
from app.email_sender import send_email
from app.reddit_client import RedditUnavailableError, SearchParams, search_reddit
from app.report_format import format_email_html, format_telegram_summary

router = Router()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VALID_TIME_FILTERS = {"hour", "day", "week", "month", "year", "all"}


async def _get_chat_and_search(
    session: AsyncSession, message: Message
) -> tuple[Chat, Search | None]:
    user = await get_or_create_user(session, message.from_user.id)
    chat = await get_or_create_chat(session, message.chat.id, user)
    search = None
    if chat.current_search_id:
        search = await session.get(Search, chat.current_search_id)
    return chat, search


HELP_TEXT = (
    "Привет! Я ищу материалы на Reddit по твоему запросу и присылаю аналитику "
    "с ссылками на источники.\n\n"
    "1. /setemail you@example.com — куда слать отчёты\n"
    "2. /search <запрос> — начать поиск\n"
    "3. /filter subreddit:python days:30 limit:100 — уточнить фильтры\n"
    "4. /run — (пере)запустить поиск с текущими фильтрами\n"
    "5. /report — показать последний отчёт в чате\n"
    "6. /email — отправить последний отчёт на почту\n"
    "/help — эта справка"
)


@router.message(Command("start"))
async def cmd_start(message: Message, session_factory: async_sessionmaker) -> None:
    async with session_factory() as session:
        user = await get_or_create_user(session, message.from_user.id)
        await get_or_create_chat(session, message.chat.id, user)
        await session.commit()

    await message.answer(HELP_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("setemail"))
async def cmd_setemail(
    message: Message, command: CommandObject, session_factory: async_sessionmaker
) -> None:
    email = (command.args or "").strip()
    if not EMAIL_RE.match(email):
        await message.answer("Использование: /setemail you@example.com")
        return

    async with session_factory() as session:
        user = await get_or_create_user(session, message.from_user.id)
        user.email = email
        await session.commit()

    await message.answer(f"Почта сохранена: {email}")


@router.message(Command("search"))
async def cmd_search(
    message: Message, command: CommandObject, session_factory: async_sessionmaker
) -> None:
    query = (command.args or "").strip()
    if not query:
        await message.answer("Использование: /search <запрос>")
        return

    async with session_factory() as session:
        user = await get_or_create_user(session, message.from_user.id)
        chat = await get_or_create_chat(session, message.chat.id, user)

        search = Search(chat_id=chat.id, query=query)
        session.add(search)
        await session.flush()
        chat.current_search_id = search.id
        await session.commit()

    await message.answer(
        f"Создан новый поиск: «{query}». Уточни фильтры через /filter или сразу "
        "запусти /run."
    )


@router.message(Command("filter"))
async def cmd_filter(
    message: Message, command: CommandObject, session_factory: async_sessionmaker
) -> None:
    args = (command.args or "").strip()
    if not args:
        await message.answer(
            "Использование: /filter subreddit:python,news days:30 limit:100\n"
            "Поддерживаемые ключи: subreddit, days (или time_filter), limit"
        )
        return

    async with session_factory() as session:
        chat, search = await _get_chat_and_search(session, message)
        if search is None:
            await message.answer("Сначала создай поиск через /search <запрос>")
            return

        for token in args.split():
            if ":" not in token:
                continue
            key, value = token.split(":", 1)
            key = key.lower()
            if key == "subreddit":
                search.set_subreddits([s.strip() for s in value.split(",") if s.strip()])
            elif key in ("time_filter", "days"):
                if key == "days":
                    days_map = {
                        "1": "day", "7": "week", "30": "month", "365": "year",
                    }
                    search.time_filter = days_map.get(value, "all")
                elif value in VALID_TIME_FILTERS:
                    search.time_filter = value
            elif key == "limit":
                if value.isdigit():
                    search.limit = min(int(value), 200)

        await session.commit()

    await message.answer(
        f"Фильтры обновлены: subreddits={search.get_subreddits() or 'all'}, "
        f"time_filter={search.time_filter}, limit={search.limit}. Запусти /run."
    )


@router.message(Command("run"))
async def cmd_run(
    message: Message,
    session_factory: async_sessionmaker,
    reddit: httpx.AsyncClient,
) -> None:
    async with session_factory() as session:
        chat, search = await _get_chat_and_search(session, message)
        if search is None:
            await message.answer("Сначала создай поиск через /search <запрос>")
            return

        await message.answer(f"Ищу на Reddit по запросу «{search.query}»…")

        params = SearchParams(
            query=search.query,
            subreddits=search.get_subreddits(),
            time_filter=search.time_filter,
            limit=search.limit,
        )
        try:
            items = await search_reddit(reddit, params)
        except RedditUnavailableError as exc:
            await message.answer(str(exc))
            return
        analytics = build_analytics(search.query, items)

        report = Report(search_id=search.id, analytics_json=json.dumps(analytics))
        session.add(report)
        await session.commit()

    await message.answer(format_telegram_summary(analytics), parse_mode="HTML")


@router.message(Command("report"))
async def cmd_report(message: Message, session_factory: async_sessionmaker) -> None:
    async with session_factory() as session:
        chat, search = await _get_chat_and_search(session, message)
        if search is None:
            await message.answer("Ещё нет ни одного поиска. Начни с /search <запрос>")
            return

        result = await session.execute(
            select(Report)
            .where(Report.search_id == search.id)
            .order_by(Report.generated_at.desc())
            .limit(1)
        )
        report = result.scalar_one_or_none()

    if report is None:
        await message.answer("Отчётов пока нет. Запусти /run.")
        return

    analytics = json.loads(report.analytics_json)
    await message.answer(format_telegram_summary(analytics), parse_mode="HTML")


@router.message(Command("email"))
async def cmd_email(
    message: Message, session_factory: async_sessionmaker, config: Config
) -> None:
    async with session_factory() as session:
        user = await get_or_create_user(session, message.from_user.id)
        chat, search = await _get_chat_and_search(session, message)

        if not user.email:
            await message.answer("Сначала укажи почту: /setemail you@example.com")
            return
        if search is None:
            await message.answer("Ещё нет ни одного поиска. Начни с /search <запрос>")
            return

        result = await session.execute(
            select(Report)
            .where(Report.search_id == search.id)
            .order_by(Report.generated_at.desc())
            .limit(1)
        )
        report = result.scalar_one_or_none()
        if report is None:
            await message.answer("Отчётов пока нет. Запусти /run.")
            return

        analytics = json.loads(report.analytics_json)
        html = format_email_html(analytics)

        await send_email(
            api_key=config.resend_api_key,
            from_email=config.resend_from_email,
            to_email=user.email,
            subject=f"Reddit-аналитика: {analytics['query']}",
            html=html,
        )

        report.emailed_at = datetime.datetime.utcnow()
        await session.commit()

    await message.answer(f"Отчёт отправлен на {user.email}")
