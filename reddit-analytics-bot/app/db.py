import datetime
import json
from typing import Optional

from sqlalchemy import ForeignKey, JSON, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=datetime.datetime.utcnow
    )


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    current_search_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("searches.id"), nullable=True
    )


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id"))
    query: Mapped[str] = mapped_column(String(300))
    subreddits: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON list of subreddit names, empty/None = "all"
    time_filter: Mapped[str] = mapped_column(String(20), default="all")
    limit: Mapped[int] = mapped_column(default=50)
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    def get_subreddits(self) -> list[str]:
        return json.loads(self.subreddits) if self.subreddits else []

    def set_subreddits(self, names: list[str]) -> None:
        self.subreddits = json.dumps(names) if names else None


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("searches.id"))
    generated_at: Mapped[datetime.datetime] = mapped_column(
        default=datetime.datetime.utcnow
    )
    analytics_json: Mapped[str] = mapped_column(Text)
    emailed_at: Mapped[Optional[datetime.datetime]] = mapped_column(nullable=True)


async def create_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_or_create_user(session: AsyncSession, telegram_id: int) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id)
        session.add(user)
        await session.flush()
    return user


async def get_or_create_chat(
    session: AsyncSession, telegram_chat_id: int, user: User
) -> Chat:
    result = await session.execute(
        select(Chat).where(Chat.telegram_chat_id == telegram_chat_id)
    )
    chat = result.scalar_one_or_none()
    if chat is None:
        chat = Chat(telegram_chat_id=telegram_chat_id, user_id=user.id)
        session.add(chat)
        await session.flush()
    return chat
