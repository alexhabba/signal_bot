"""Issuing invoices with a unique amount per pending payment.

All invoices are paid to one receiving address, so the amount is what tells payments apart:
a 30 USDT plan is billed as 30.01, 30.02, ... and no two reserved invoices share an amount.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ACTIVE_INVOICE_STATUSES, Invoice, InvoiceStatus, Plan

CENT = Decimal("0.01")

# An expired invoice keeps its amount reserved for this long, so a late transfer
# can still be matched to the right person instead of to a newer invoice.
REUSE_COOLDOWN = timedelta(hours=24)


# Serializes amount picking so two concurrent requests never get the same amount.
# Enough while the bot runs as a single process.
_issue_lock = asyncio.Lock()


class NoFreeAmountError(Exception):
    """Every amount slot for this price is reserved; retry later or raise amount_offset_slots."""


def _reserved_condition(now: datetime):
    return or_(
        Invoice.status.in_(ACTIVE_INVOICE_STATUSES),
        and_(Invoice.status == InvoiceStatus.EXPIRED, Invoice.expires_at > now - REUSE_COOLDOWN),
    )


async def find_open_invoice(session: AsyncSession, user_id: int, plan_id: int, now: datetime) -> Invoice | None:
    return await session.scalar(
        select(Invoice)
        .where(
            Invoice.user_id == user_id,
            Invoice.plan_id == plan_id,
            Invoice.status == InvoiceStatus.PENDING,
            Invoice.expires_at > now,
        )
        .order_by(Invoice.created_at.desc())
        .limit(1)
    )


async def pick_amount(session: AsyncSession, price: Decimal, network: str, slots: int, now: datetime) -> Decimal:
    candidates = [price + CENT * i for i in range(1, slots + 1)]
    taken = set(
        await session.scalars(
            select(Invoice.amount).where(
                Invoice.network == network,
                Invoice.amount.in_(candidates),
                _reserved_condition(now),
            )
        )
    )
    for amount in candidates:
        if amount not in taken:
            return amount
    raise NoFreeAmountError(f"no free amount for price {price} on {network}")


async def create_invoice(
    session: AsyncSession,
    *,
    user_id: int,
    plan: Plan,
    network: str,
    address: str,
    ttl: timedelta,
    slots: int,
    now: datetime | None = None,
) -> Invoice:
    """Return the user's open invoice for this plan, or issue a new one."""
    now = now or datetime.now(timezone.utc)
    async with _issue_lock:
        existing = await find_open_invoice(session, user_id, plan.id, now)
        if existing:
            return existing

        amount = await pick_amount(session, plan.price, network, slots, now)
        invoice = Invoice(
            user_id=user_id,
            plan_id=plan.id,
            network=network,
            address=address,
            amount=amount,
            status=InvoiceStatus.PENDING,
            created_at=now,
            expires_at=now + ttl,
        )
        session.add(invoice)
        await session.commit()
        return invoice


async def cancel_invoice(session: AsyncSession, invoice_id: int, user_id: int) -> bool:
    result = await session.execute(
        update(Invoice)
        .where(Invoice.id == invoice_id, Invoice.user_id == user_id, Invoice.status == InvoiceStatus.PENDING)
        .values(status=InvoiceStatus.CANCELLED)
    )
    await session.commit()
    return result.rowcount > 0


async def expire_invoices(session: AsyncSession, now: datetime | None = None) -> int:
    """Mark pending invoices past their deadline as expired. Returns how many changed."""
    now = now or datetime.now(timezone.utc)
    result = await session.execute(
        update(Invoice)
        .where(Invoice.status == InvoiceStatus.PENDING, Invoice.expires_at <= now)
        .values(status=InvoiceStatus.EXPIRED)
    )
    await session.commit()
    return result.rowcount
