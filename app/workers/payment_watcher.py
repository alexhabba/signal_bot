"""Polls the blockchain for incoming USDT and applies each transfer to its invoice."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot import texts
from app.config import Settings
from app.services.access import make_join_link
from app.services.payments import Outcome, PaymentResult, last_payment_time, process_transfer
from app.services.tron import TronGridClient

logger = logging.getLogger(__name__)

# Re-scan a little before the newest recorded payment; duplicates are skipped by tx hash.
OVERLAP = timedelta(minutes=5)


async def poll_once(
    sessionmaker: async_sessionmaker[AsyncSession], client: TronGridClient, settings: Settings
) -> list[PaymentResult]:
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        last = await last_payment_time(session, settings.payment_network)
    since = last - OVERLAP if last else now - timedelta(hours=settings.scan_lookback_hours)

    transfers = await client.incoming_transfers(settings.payment_address, since)
    results = []
    for transfer in transfers:
        async with sessionmaker() as session:
            result = await process_transfer(
                session,
                transfer,
                network=settings.payment_network,
                now=datetime.now(timezone.utc),
                tolerance=settings.underpay_tolerance,
                underpay_window=settings.underpay_window,
            )
        if result.outcome != Outcome.DUPLICATE:
            logger.info("Transfer %s: %s", transfer.tx_hash, result.outcome.value)
            results.append(result)
    return results


async def notify(bot: Bot, settings: Settings, result: PaymentResult) -> None:
    try:
        if result.outcome == Outcome.PAID:
            user_id = result.invoice.user_id
            await bot.send_message(user_id, texts.payment_received(texts.format_date(result.subscription.ends_at)))
            await bot.send_message(user_id, texts.SIGNALS_IN_CHAT)
            if settings.channel_id:
                link = await make_join_link(
                    bot, settings.channel_id, user_id, timedelta(hours=settings.invite_link_ttl_hours)
                )
                await bot.send_message(user_id, texts.join_link(link, settings.invite_link_ttl_hours))
        elif result.outcome == Outcome.UNDERPAID:
            await bot.send_message(result.invoice.user_id, texts.underpaid(result.payment.amount, result.shortfall))
            await _notify_admins(
                bot,
                settings,
                texts.admin_underpaid(
                    result.invoice.user_id, result.invoice.id, result.payment.amount, result.invoice.amount
                ),
            )
        elif result.outcome == Outcome.UNMATCHED:
            p = result.payment
            await _notify_admins(bot, settings, texts.admin_unmatched(p.tx_hash, p.amount, p.from_address))
    except TelegramAPIError as exc:
        logger.warning("Notification for %s failed: %s", result.outcome.value, exc)


async def _notify_admins(bot: Bot, settings: Settings, text: str) -> None:
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except TelegramAPIError as exc:
            logger.warning("Could not notify admin %s: %s", admin_id, exc)


async def run(bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], client: TronGridClient, settings: Settings):
    if not settings.payment_address:
        logger.error("PAYMENT_ADDRESS is not set; payment watcher is off")
        return
    while True:
        try:
            for result in await poll_once(sessionmaker, client, settings):
                await notify(bot, settings, result)
        except Exception:  # keep polling through API hiccups
            logger.exception("Payment poll failed")
        await asyncio.sleep(settings.poll_interval_seconds)
