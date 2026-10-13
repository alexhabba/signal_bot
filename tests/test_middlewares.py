from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.middlewares import upsert_user
from app.db.models import User


def tg_user(user_id=7, username="a"):
    return SimpleNamespace(id=user_id, username=username, full_name="A B", language_code="ru", is_bot=False)


async def test_upsert_creates_then_updates(session):
    await upsert_user(session, tg_user())
    user = await upsert_user(session, tg_user(username="b"))
    assert user.username == "b"
    assert await session.scalar(select(func.count()).select_from(User).where(User.id == 7)) == 1


async def test_upsert_survives_row_inserted_by_a_concurrent_update(session):
    sessionmaker = async_sessionmaker(session.bind, expire_on_commit=False)
    # The first session has not seen the row yet when the second one commits it.
    original_get = session.get
    calls = 0

    async def stale_get(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            async with sessionmaker() as other:
                await upsert_user(other, tg_user())
            return None
        return await original_get(*args, **kwargs)

    session.get = stale_get
    user = await upsert_user(session, tg_user(username="late"))
    assert user.username == "late"
