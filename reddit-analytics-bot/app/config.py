import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    bot_owner_id: int
    reddit_user_agent: str
    resend_api_key: str
    resend_from_email: str
    database_url: str

    @classmethod
    def load(cls) -> "Config":
        owner_id_raw = _require("BOT_OWNER_ID")
        try:
            bot_owner_id = int(owner_id_raw)
        except ValueError:
            raise RuntimeError("BOT_OWNER_ID must be a Telegram numeric user id")

        return cls(
            telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
            bot_owner_id=bot_owner_id,
            reddit_user_agent=os.getenv(
                "REDDIT_USER_AGENT", "reddit-analytics-bot/0.1"
            ),
            resend_api_key=_require("RESEND_API_KEY"),
            resend_from_email=_require("RESEND_FROM_EMAIL"),
            database_url=os.getenv(
                "DATABASE_URL", "sqlite+aiosqlite:///./data/bot.db"
            ),
        )
