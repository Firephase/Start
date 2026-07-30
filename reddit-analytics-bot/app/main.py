import asyncio
import logging

import httpx
from aiogram import Bot, Dispatcher

from app.bot import router
from app.config import Config
from app.db import create_session_factory
from app.reddit_client import make_reddit_client

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    config = Config.load()

    session_factory = await create_session_factory(config.database_url)
    reddit = await make_reddit_client()
    http_client = httpx.AsyncClient()

    bot = Bot(token=config.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    try:
        await dispatcher.start_polling(
            bot,
            session_factory=session_factory,
            reddit=reddit,
            http_client=http_client,
            config=config,
        )
    finally:
        await reddit.aclose()
        await http_client.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
