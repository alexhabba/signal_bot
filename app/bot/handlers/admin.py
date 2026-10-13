from aiogram import Router
from aiogram.filters import Command, Filter
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Invoice, InvoiceStatus, Subscription, User

router = Router(name="admin")


class IsAdmin(Filter):
    async def __call__(self, message: Message, settings: Settings) -> bool:
        return message.from_user is not None and settings.is_admin(message.from_user.id)


router.message.filter(IsAdmin())


@router.message(Command("stats"))
async def stats(message: Message, session: AsyncSession) -> None:
    users = await session.scalar(select(func.count()).select_from(User))
    paid = await session.scalar(select(func.count()).select_from(Invoice).where(Invoice.status == InvoiceStatus.PAID))
    pending = await session.scalar(
        select(func.count()).select_from(Invoice).where(Invoice.status == InvoiceStatus.PENDING)
    )
    subs = await session.scalar(select(func.count(func.distinct(Subscription.user_id))).where(Subscription.ends_at > func.now()))
    await message.answer(
        f"Пользователей: {users}\nАктивных подписок: {subs}\nОплаченных счетов: {paid}\nОжидают оплаты: {pending}"
    )
