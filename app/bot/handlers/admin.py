from datetime import datetime, timedelta, timezone

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.config import Settings
from app.db.models import AuditLog, Invoice, InvoiceStatus, Payment, Subscription, SubscriptionSource, User
from app.services.access import make_join_link
from app.services.payments import activate_subscription
from app.services.signals import active_subscriber_ids, broadcast_signal

router = Router(name="admin")


class IsAdmin(Filter):
    async def __call__(self, message: Message, settings: Settings) -> bool:
        return message.from_user is not None and settings.is_admin(message.from_user.id)


router.message.filter(IsAdmin())


@router.message(Command("stats"))
async def stats(message: Message, session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    users = await session.scalar(select(func.count()).select_from(User))
    paid = await session.scalar(select(func.count()).select_from(Invoice).where(Invoice.status == InvoiceStatus.PAID))
    pending = await session.scalar(
        select(func.count()).select_from(Invoice).where(Invoice.status == InvoiceStatus.PENDING)
    )
    subs = await session.scalar(
        select(func.count(func.distinct(Subscription.user_id))).where(Subscription.ends_at > now)
    )
    await message.answer(
        f"Пользователей: {users}\nАктивных подписок: {subs}\nОплаченных счетов: {paid}\nОжидают оплаты: {pending}"
    )


@router.message(Command("grant"))
async def grant(message: Message, command: CommandObject, bot: Bot, session: AsyncSession, settings: Settings) -> None:
    """/grant <user_id> <days>: add access manually, e.g. after an underpayment was settled."""
    try:
        user_id, days = (int(part) for part in (command.args or "").split())
    except ValueError:
        await message.answer("Формат: /grant &lt;user_id&gt; &lt;дней&gt;")
        return
    if await session.get(User, user_id) is None:
        await message.answer("Такого пользователя нет: он должен сначала написать боту /start.")
        return

    subscription = await activate_subscription(
        session,
        user_id=user_id,
        days=days,
        now=datetime.now(timezone.utc),
        source=SubscriptionSource.ADMIN,
        invoice_id=None,
    )
    session.add(AuditLog(actor_id=message.from_user.id, action="grant", details=f"user={user_id} days={days}"))
    await session.commit()

    ends_at = texts.format_date(subscription.ends_at)
    await message.answer(f"Готово: доступ пользователя {user_id} до {ends_at} (UTC).")
    try:
        await bot.send_message(user_id, texts.payment_received(ends_at))
        await bot.send_message(user_id, texts.SIGNALS_IN_CHAT)
        if settings.channel_id:
            ttl = timedelta(hours=settings.invite_link_ttl_hours)
            link = await make_join_link(bot, settings.channel_id, user_id, ttl)
            await bot.send_message(user_id, texts.join_link(link, settings.invite_link_ttl_hours))
    except TelegramAPIError as exc:
        await message.answer(f"Доступ выдан, но сообщение пользователю не ушло: {exc}")


@router.message(Command("unmatched"))
async def unmatched(message: Message, session: AsyncSession) -> None:
    """Recent transfers that didn't match any invoice or were short."""
    payments = list(
        await session.scalars(
            select(Payment)
            .outerjoin(Invoice, Payment.invoice_id == Invoice.id)
            .where((Payment.invoice_id.is_(None)) | (Invoice.status == InvoiceStatus.UNDERPAID))
            .order_by(Payment.block_time.desc())
            .limit(20)
        )
    )
    if not payments:
        await message.answer("Спорных платежей нет.")
        return
    lines = [
        f"{texts.format_date(p.block_time)} · {texts.format_amount(p.amount)} USDT · "
        f"{'счёт #' + str(p.invoice_id) if p.invoice_id else 'без счёта'}\n<code>{p.tx_hash}</code>"
        for p in payments
    ]
    await message.answer("\n\n".join(lines))


@router.message(Command("signal"))
async def signal(message: Message, command: CommandObject, bot: Bot, session: AsyncSession) -> None:
    """/signal <text>: send a full signal to every subscriber with an active subscription."""
    text = (command.args or "").strip()
    if not text:
        await message.answer(texts.SIGNAL_USAGE)
        return
    if not await active_subscriber_ids(session):
        await message.answer(texts.NO_SUBSCRIBERS)
        return
    result = await broadcast_signal(bot, session, text=text, created_by=message.from_user.id)
    await message.answer(texts.broadcast_report(result.recipients, result.failed))


@router.message(Command("free"))
async def free(message: Message, command: CommandObject, bot: Bot, settings: Settings) -> None:
    """/free <text>: publish a free signal in the open channel."""
    text = (command.args or "").strip()
    if not text:
        await message.answer(texts.FREE_USAGE)
        return
    if not settings.public_channel_id:
        await message.answer(texts.PUBLIC_CHANNEL_NOT_CONFIGURED)
        return
    try:
        await bot.send_message(settings.public_channel_id, text)
    except TelegramAPIError as exc:
        await message.answer(f"Не удалось опубликовать в канале: {exc}")
        return
    await message.answer("Опубликовано в открытом канале.")
