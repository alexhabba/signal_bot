from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import User


class DbSessionMiddleware(BaseMiddleware):
    """Opens a DB session per update and makes sure the sender exists in the users table."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.sessionmaker() as session:
            tg_user: TgUser | None = data.get("event_from_user")
            if tg_user is not None and not tg_user.is_bot:
                await upsert_user(session, tg_user)
            data["session"] = session
            return await handler(event, data)


async def upsert_user(session: AsyncSession, tg_user: TgUser) -> User:
    user = await session.get(User, tg_user.id)
    if user is None:
        user = User(id=tg_user.id)
        session.add(user)
    user.username = tg_user.username
    user.full_name = tg_user.full_name
    user.language = tg_user.language_code
    try:
        await session.commit()
    except IntegrityError:
        # Two updates from a new user were handled at once and the other one inserted the row first.
        await session.rollback()
        user = await session.get(User, tg_user.id)
        user.username = tg_user.username
        user.full_name = tg_user.full_name
        user.language = tg_user.language_code
        await session.commit()
    return user
