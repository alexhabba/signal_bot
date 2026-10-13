from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot import texts
from app.db.models import Plan


class PlanCallback(CallbackData, prefix="plan"):
    plan_id: int


class CancelInvoiceCallback(CallbackData, prefix="cancel"):
    invoice_id: int


def plans_keyboard(plans: list[Plan]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.button(text=texts.plan_button(plan.title, plan.price), callback_data=PlanCallback(plan_id=plan.id))
    builder.adjust(1)
    return builder.as_markup()


def invoice_keyboard(invoice_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Отменить счёт", callback_data=CancelInvoiceCallback(invoice_id=invoice_id))
    return builder.as_markup()
