import logging
from datetime import timedelta

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.keyboards import CancelInvoiceCallback, PlanCallback, invoice_keyboard, plans_keyboard
from app.config import Settings
from app.db.models import Plan
from app.services.invoices import NoFreeAmountError, cancel_invoice, create_invoice
from app.services.subscriptions import active_until

logger = logging.getLogger(__name__)
router = Router(name="user")


async def _active_plans(session: AsyncSession) -> list[Plan]:
    return list(await session.scalars(select(Plan).where(Plan.is_active).order_by(Plan.sort_order)))


@router.message(CommandStart())
async def start(message: Message, session: AsyncSession) -> None:
    plans = await _active_plans(session)
    if not plans:
        await message.answer(texts.NO_PLANS)
        return
    await message.answer(texts.WELCOME, reply_markup=plans_keyboard(plans))


@router.message(Command("status"))
async def status(message: Message, session: AsyncSession) -> None:
    ends_at = await active_until(session, message.from_user.id)
    if ends_at is None:
        await message.answer(texts.NO_SUBSCRIPTION)
        return
    await message.answer(texts.subscription_active(ends_at.strftime("%d.%m.%Y %H:%M")))


@router.callback_query(PlanCallback.filter())
async def choose_plan(query: CallbackQuery, callback_data: PlanCallback, session: AsyncSession, settings: Settings) -> None:
    plan = await session.get(Plan, callback_data.plan_id)
    if plan is None or not plan.is_active:
        await query.answer(texts.NO_PLANS, show_alert=True)
        return
    if not settings.payment_address:
        logger.error("PAYMENT_ADDRESS is not configured")
        await query.answer(texts.PAYMENTS_UNAVAILABLE, show_alert=True)
        return

    ttl = timedelta(minutes=settings.invoice_ttl_minutes)
    try:
        invoice = await create_invoice(
            session,
            user_id=query.from_user.id,
            plan=plan,
            network=settings.payment_network,
            address=settings.payment_address,
            ttl=ttl,
            slots=settings.amount_offset_slots,
        )
    except NoFreeAmountError:
        logger.warning("No free invoice amount for plan %s", plan.id)
        await query.answer(texts.PAYMENTS_UNAVAILABLE, show_alert=True)
        return

    await query.message.answer(
        texts.invoice_text(
            plan_title=plan.title,
            amount=invoice.amount,
            network=invoice.network,
            address=invoice.address,
            minutes_left=settings.invoice_ttl_minutes,
        ),
        reply_markup=invoice_keyboard(invoice.id),
    )
    await query.answer()


@router.callback_query(CancelInvoiceCallback.filter())
async def cancel(query: CallbackQuery, callback_data: CancelInvoiceCallback, session: AsyncSession) -> None:
    cancelled = await cancel_invoice(session, callback_data.invoice_id, query.from_user.id)
    if cancelled and query.message is not None:
        await query.message.edit_reply_markup(reply_markup=None)
    await query.answer(texts.INVOICE_CANCELLED if cancelled else texts.INVOICE_NOT_FOUND)
