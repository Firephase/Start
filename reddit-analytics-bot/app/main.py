import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.bot import router
from app.config import Config
from app.db import create_session_factory
from app.reddit_client import make_reddit_client

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    config = Config.load()

    session_factory = await create_session_factory(config.database_url)
    reddit = make_reddit_client(config)

    bot = Bot(token=config.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    try:
        await dispatcher.start_polling(
            bot,
            session_factory=session_factory,
            reddit=reddit,
            config=config,
        )
    finally:
        await reddit.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
