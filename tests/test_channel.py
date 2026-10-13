from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.bot.handlers.channel import on_join_request
from app.db.models import Subscription, SubscriptionSource

CHANNEL = -1001


def join_request(user_id, chat_id=CHANNEL):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id), from_user=SimpleNamespace(id=user_id), approve=AsyncMock(), decline=AsyncMock()
    )


async def test_approves_paying_user_and_declines_others(session):
    now = datetime.now(timezone.utc)
    session.add(
        Subscription(user_id=1, starts_at=now, ends_at=now + timedelta(days=30), source=SubscriptionSource.PAYMENT)
    )
    await session.commit()
    settings = SimpleNamespace(channel_id=CHANNEL)

    paying, stranger = join_request(1), join_request(2)
    await on_join_request(paying, session=session, settings=settings)
    await on_join_request(stranger, session=session, settings=settings)

    paying.approve.assert_awaited_once()
    stranger.decline.assert_awaited_once()
    stranger.approve.assert_not_awaited()


async def test_ignores_other_chats(session):
    request = join_request(1, chat_id=-999)
    await on_join_request(request, session=session, settings=SimpleNamespace(channel_id=CHANNEL))
    request.approve.assert_not_awaited()
    request.decline.assert_not_awaited()
