from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from sqlalchemy import select

from app.bot.handlers.admin import free, signal
from app.db.models import Signal, Subscription, SubscriptionSource
from app.services import signals
from app.services.signals import active_subscriber_ids, broadcast_signal

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    monkeypatch.setattr(signals, "SEND_INTERVAL", 0)


async def add_sub(session, user_id, ends_at):
    session.add(
        Subscription(
            user_id=user_id, starts_at=ends_at - timedelta(days=30), ends_at=ends_at, source=SubscriptionSource.PAYMENT
        )
    )
    await session.commit()


def blocked_error():
    return TelegramForbiddenError(method=SendMessage(chat_id=1, text="x"), message="Forbidden: bot was blocked")


async def test_only_active_subscribers_are_listed_once(session):
    await add_sub(session, 1, NOW + timedelta(days=5))
    await add_sub(session, 1, NOW + timedelta(days=35))  # renewed: still one user
    await add_sub(session, 2, NOW - timedelta(days=1))  # expired
    assert await active_subscriber_ids(session, NOW) == [1]


async def test_broadcast_sends_protected_message_and_records_result(session):
    await add_sub(session, 1, NOW + timedelta(days=5))
    await add_sub(session, 2, NOW + timedelta(days=5))
    bot = SimpleNamespace(send_message=AsyncMock())

    result = await broadcast_signal(bot, session, text="BTC long 60000", created_by=99)

    assert result.recipients == 2 and result.failed == 0
    assert bot.send_message.await_count == 2
    user_id, text = bot.send_message.await_args_list[0].args
    assert user_id == 1 and "BTC long 60000" in text
    assert bot.send_message.await_args_list[0].kwargs == {"protect_content": True}
    stored = await session.scalar(select(Signal))
    assert (stored.text, stored.recipients, stored.created_by) == ("BTC long 60000", 2, 99)


async def test_blocked_user_counts_as_failed_and_does_not_stop_others(session):
    await add_sub(session, 1, NOW + timedelta(days=5))
    await add_sub(session, 2, NOW + timedelta(days=5))

    async def send(user_id, text, **kwargs):
        if user_id == 1:
            raise blocked_error()

    bot = SimpleNamespace(send_message=AsyncMock(side_effect=send))
    result = await broadcast_signal(bot, session, text="ETH short", created_by=99)
    assert (result.recipients, result.failed) == (1, 1)


def admin_message(text, user_id=99):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id), answer=AsyncMock(), text=text
    )


def command(args):
    return SimpleNamespace(args=args)


async def test_signal_command_needs_text_and_subscribers(session):
    bot = SimpleNamespace(send_message=AsyncMock())

    msg = admin_message("/signal")
    await signal(msg, command(None), bot, session)
    assert "Формат" in msg.answer.await_args.args[0]

    msg = admin_message("/signal x")
    await signal(msg, command("BTC long"), bot, session)
    assert "нет" in msg.answer.await_args.args[0]
    bot.send_message.assert_not_awaited()


async def test_signal_command_reports_delivery(session):
    await add_sub(session, 1, NOW + timedelta(days=5))
    bot = SimpleNamespace(send_message=AsyncMock())
    msg = admin_message("/signal BTC long")
    await signal(msg, command("BTC long"), bot, session)
    assert "Отправлено подписчикам: 1" in msg.answer.await_args.args[0]


async def test_free_command_posts_to_public_channel():
    bot = SimpleNamespace(send_message=AsyncMock())
    msg = admin_message("/free hi")
    await free(msg, command("Итоги недели"), bot, SimpleNamespace(public_channel_id=-1002))
    bot.send_message.assert_awaited_once_with(-1002, "Итоги недели")

    msg = admin_message("/free hi")
    await free(msg, command("x"), bot, SimpleNamespace(public_channel_id=None))
    assert "PUBLIC_CHANNEL_ID" in msg.answer.await_args.args[0]
