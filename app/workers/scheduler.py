"""Periodic jobs: expire unpaid invoices, remind about renewal, remove expired users."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot import texts
from app.config import Settings
from app.services.access import remove_from_channel
from app.services.invoices import expire_invoices
from app.services.lifecycle import due_reminders, due_revocations, mark_revoked

logger = logging.getLogger(__name__)


async def tick(bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        expired = await expire_invoices(session, now)
        if expired:
            logger.info("Expired %s invoices", expired)

        for sub, reminder in await due_reminders(session, now):
            try:
                await bot.send_message(sub.user_id, texts.renewal_reminder(texts.format_date(sub.ends_at)))
            except TelegramAPIError as exc:
                logger.warning("Reminder to %s failed: %s", sub.user_id, exc)
            sub.reminded_days = reminder
            await session.commit()

        for sub in await due_revocations(session, now, timedelta(hours=settings.grace_hours)):
            if settings.channel_id and not await remove_from_channel(bot, settings.channel_id, sub.user_id):
                continue  # retry on the next tick
            await mark_revoked(session, sub.user_id)
            try:
                await bot.send_message(sub.user_id, texts.SUBSCRIPTION_ENDED)
            except TelegramAPIError:
                pass


async def run(bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    while True:
        try:
            await tick(bot, sessionmaker, settings)
        except Exception:
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(settings.scheduler_interval_seconds)
