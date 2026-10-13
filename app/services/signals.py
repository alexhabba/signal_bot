"""Sending signals: full ones to subscribers' private chats, free ones to the open channel."""

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.db.models import Signal, Subscription

logger = logging.getLogger(__name__)

# Telegram allows about 30 messages per second to different chats; stay under it.
SEND_INTERVAL = 0.05


async def active_subscriber_ids(session: AsyncSession, now: datetime | None = None) -> list[int]:
    now = now or datetime.now(timezone.utc)
    rows = await session.scalars(select(distinct(Subscription.user_id)).where(Subscription.ends_at > now))
    return sorted(rows)


async def _send(bot: Bot, user_id: int, text: str) -> bool:
    for _ in range(3):
        try:
            # protect_content blocks forwarding and saving, which makes leaking signals harder.
            await bot.send_message(user_id, text, protect_content=True)
            return True
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
        except TelegramForbiddenError:
            return False  # the user blocked the bot
        except TelegramAPIError as exc:
            logger.warning("Signal to %s failed: %s", user_id, exc)
            return False
    return False


async def broadcast_signal(
    bot: Bot, session: AsyncSession, *, text: str, created_by: int, now: datetime | None = None
) -> Signal:
    """Send `text` to every active subscriber and record how many received it."""
    ids = await active_subscriber_ids(session, now)
    message = texts.signal_message(text)
    delivered = 0
    for user_id in ids:
        if await _send(bot, user_id, message):
            delivered += 1
        await asyncio.sleep(SEND_INTERVAL)
    signal = Signal(text=text, recipients=delivered, failed=len(ids) - delivered, created_by=created_by)
    session.add(signal)
    await session.commit()
    return signal
