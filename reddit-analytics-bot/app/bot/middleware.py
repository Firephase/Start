from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Config
from app.db import get_or_create_user

OPEN_COMMANDS = {"/start", "/help"}


class AllowlistMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        config: Config = data["config"]

        if event.from_user is None:
            return

        if event.from_user.id == config.bot_owner_id:
            return await handler(event, data)

        command = (event.text or "").split()[0].split("@")[0] if event.text else ""
        if command in OPEN_COMMANDS:
            return await handler(event, data)

        session_factory: async_sessionmaker = data["session_factory"]
        async with session_factory() as session:
            user = await get_or_create_user(session, event.from_user.id)
            allowed = user.is_allowed
            await session.commit()

        if not allowed:
            await event.answer(
                "You're not authorized to use this bot yet.\n"
                f"Your Telegram ID: {event.from_user.id}\n"
                "Ask the bot owner to grant you access."
            )
            return

        return await handler(event, data)
