"""Matching incoming transfers to invoices and turning paid invoices into subscriptions."""

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import AuditLog, Invoice, InvoiceStatus, Payment, Subscription, SubscriptionSource
from app.services.invoices import REUSE_COOLDOWN
from app.services.subscriptions import as_utc
from app.services.tron import Transfer


class Outcome(str, enum.Enum):
    DUPLICATE = "duplicate"  # this transfer was already processed
    PAID = "paid"
    UNDERPAID = "underpaid"
    UNMATCHED = "unmatched"  # no invoice fits; needs an admin


@dataclass
class PaymentResult:
    outcome: Outcome
    payment: Payment | None = None
    invoice: Invoice | None = None
    subscription: Subscription | None = None

    @property
    def shortfall(self) -> Decimal:
        if self.invoice is None or self.payment is None:
            return Decimal("0")
        return self.invoice.amount - self.payment.amount


def _cents(amount: Decimal) -> Decimal:
    return amount % 1


async def _candidate_invoices(session: AsyncSession, network: str, at: datetime) -> list[Invoice]:
    """Invoices a transfer at `at` may belong to: pending ones, and ones that expired recently."""
    return list(
        await session.scalars(
            select(Invoice)
            .options(selectinload(Invoice.plan))
            .where(
                Invoice.network == network,
                Invoice.status.in_((InvoiceStatus.PENDING, InvoiceStatus.EXPIRED)),
                Invoice.created_at <= at,
                Invoice.expires_at > at - REUSE_COOLDOWN,
            )
        )
    )


def find_invoice(
    candidates: list[Invoice], amount: Decimal, tolerance: Decimal, underpay_window: Decimal
) -> tuple[Invoice | None, bool]:
    """Pick the invoice a transfer pays. Returns (invoice, fully_paid).

    An exact amount always wins. Otherwise a transfer slightly below an invoice counts against it
    when exactly one invoice fits: exchanges often deduct their withdrawal fee from the amount,
    which keeps the unique cents but lowers the whole part.
    """
    exact = [inv for inv in candidates if inv.amount == amount]
    if exact:
        return min(exact, key=lambda inv: inv.created_at), True

    short = [inv for inv in candidates if Decimal("0") < inv.amount - amount <= underpay_window]
    within_tolerance = [inv for inv in short if inv.amount - amount <= tolerance]
    if len(within_tolerance) == 1:
        return within_tolerance[0], True
    same_cents = [inv for inv in short if _cents(inv.amount) == _cents(amount)]
    if len(same_cents) == 1:
        return same_cents[0], False
    return None, False


async def activate_subscription(
    session: AsyncSession, *, user_id: int, days: int, now: datetime, source: SubscriptionSource, invoice_id: int | None
) -> Subscription:
    """Add `days` of access, starting when the current access ends (or now, if it already ended)."""
    current_end = await session.scalar(select(func.max(Subscription.ends_at)).where(Subscription.user_id == user_id))
    current_end = as_utc(current_end) if current_end is not None else None
    starts_at = max(now, current_end) if current_end is not None else now
    subscription = Subscription(
        user_id=user_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(days=days),
        source=source,
        invoice_id=invoice_id,
    )
    session.add(subscription)
    return subscription


async def process_transfer(
    session: AsyncSession,
    transfer: Transfer,
    *,
    network: str,
    now: datetime,
    tolerance: Decimal = Decimal("0"),
    underpay_window: Decimal = Decimal("5"),
) -> PaymentResult:
    """Record a transfer once and apply it to the invoice it pays. Safe to call repeatedly."""
    exists = await session.scalar(
        select(Payment.id).where(Payment.network == network, Payment.tx_hash == transfer.tx_hash)
    )
    if exists:
        return PaymentResult(Outcome.DUPLICATE)

    payment = Payment(
        network=network,
        tx_hash=transfer.tx_hash,
        from_address=transfer.from_address,
        amount=transfer.amount,
        block_time=transfer.block_time,
    )
    session.add(payment)

    candidates = await _candidate_invoices(session, network, transfer.block_time)
    invoice, fully_paid = find_invoice(candidates, transfer.amount, tolerance, underpay_window)

    result = PaymentResult(Outcome.UNMATCHED, payment=payment)
    if invoice is not None:
        payment.invoice_id = invoice.id
        result.invoice = invoice
        if fully_paid:
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = now
            result.outcome = Outcome.PAID
            result.subscription = await activate_subscription(
                session,
                user_id=invoice.user_id,
                days=invoice.plan.days,
                now=now,
                source=SubscriptionSource.PAYMENT,
                invoice_id=invoice.id,
            )
        else:
            invoice.status = InvoiceStatus.UNDERPAID
            result.outcome = Outcome.UNDERPAID

    session.add(
        AuditLog(
            action=f"payment_{result.outcome.value}",
            details=f"tx={transfer.tx_hash} amount={transfer.amount} invoice={invoice.id if invoice else None}",
        )
    )
    try:
        await session.commit()
    except IntegrityError:  # the same transfer was recorded concurrently
        await session.rollback()
        return PaymentResult(Outcome.DUPLICATE)
    return result


async def last_payment_time(session: AsyncSession, network: str) -> datetime | None:
    value = await session.scalar(select(func.max(Payment.block_time)).where(Payment.network == network))
    return as_utc(value) if value is not None else None
