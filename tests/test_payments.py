from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.db.models import InvoiceStatus, Payment, Plan, Subscription, SubscriptionSource
from app.services.invoices import create_invoice, expire_invoices
from app.services.payments import Outcome, activate_subscription, process_transfer
from app.services.subscriptions import active_until, as_utc
from app.services.tron import Transfer

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
TTL = timedelta(minutes=60)


async def issue(session, user_id, plan_id=1, now=NOW):
    plan = await session.get(Plan, plan_id)
    return await create_invoice(
        session, user_id=user_id, plan=plan, network="TRC20", address="TAddr", ttl=TTL, slots=99, now=now
    )


def transfer(amount, at=NOW + timedelta(minutes=5), tx="tx1"):
    return Transfer(tx_hash=tx, from_address="TSender", to_address="TAddr", amount=Decimal(amount), block_time=at)


async def pay(session, t, now=None, **kwargs):
    return await process_transfer(session, t, network="TRC20", now=now or t.block_time, **kwargs)


async def test_exact_amount_pays_invoice_and_starts_subscription(session):
    invoice = await issue(session, 1)
    result = await pay(session, transfer("30.01"))
    assert result.outcome == Outcome.PAID
    assert result.invoice.id == invoice.id
    assert invoice.status == InvoiceStatus.PAID
    assert as_utc(result.subscription.ends_at) == NOW + timedelta(minutes=5, days=30)
    assert await active_until(session, 1, now=NOW + timedelta(days=1))


async def test_amount_picks_the_right_user(session):
    await issue(session, 1)
    second = await issue(session, 2)
    result = await pay(session, transfer("30.02"))
    assert result.invoice.id == second.id
    assert result.subscription.user_id == 2


async def test_same_transfer_is_processed_once(session):
    await issue(session, 1)
    assert (await pay(session, transfer("30.01"))).outcome == Outcome.PAID
    assert (await pay(session, transfer("30.01"))).outcome == Outcome.DUPLICATE
    assert len(list(await session.scalars(select(Subscription)))) == 1


async def test_unknown_amount_is_unmatched_and_recorded(session):
    await issue(session, 1)
    result = await pay(session, transfer("12.34"))
    assert result.outcome == Outcome.UNMATCHED
    assert (await session.scalar(select(Payment))).invoice_id is None


async def test_exchange_fee_deducted_is_underpaid(session):
    invoice = await issue(session, 1)
    await issue(session, 2)  # 30.02, different cents
    result = await pay(session, transfer("29.01"))
    assert result.outcome == Outcome.UNDERPAID
    assert result.invoice.id == invoice.id
    assert result.shortfall == Decimal("1")
    assert invoice.status == InvoiceStatus.UNDERPAID
    assert await active_until(session, 1, now=NOW + timedelta(minutes=10)) is None


async def test_underpay_within_tolerance_counts_as_paid(session):
    await issue(session, 1)
    result = await pay(session, transfer("29.91"), tolerance=Decimal("0.5"))
    assert result.outcome == Outcome.PAID


async def test_late_payment_on_expired_invoice_still_matches(session):
    invoice = await issue(session, 1)
    late = NOW + TTL + timedelta(hours=2)
    await expire_invoices(session, now=late)
    result = await pay(session, transfer("30.01", at=late))
    assert result.outcome == Outcome.PAID
    assert result.invoice.id == invoice.id


async def test_transfer_before_invoice_does_not_match(session):
    await issue(session, 1)
    result = await pay(session, transfer("30.01", at=NOW - timedelta(minutes=1)))
    assert result.outcome == Outcome.UNMATCHED


async def test_cancelled_invoice_is_not_paid(session):
    invoice = await issue(session, 1)
    invoice.status = InvoiceStatus.CANCELLED
    await session.commit()
    assert (await pay(session, transfer("30.01"))).outcome == Outcome.UNMATCHED


async def test_renewal_extends_from_current_end(session):
    first = await activate_subscription(
        session, user_id=1, days=30, now=NOW, source=SubscriptionSource.ADMIN, invoice_id=None
    )
    await session.commit()
    second = await activate_subscription(
        session, user_id=1, days=30, now=NOW + timedelta(days=10), source=SubscriptionSource.ADMIN, invoice_id=None
    )
    assert as_utc(second.starts_at) == as_utc(first.ends_at)
    assert as_utc(second.ends_at) == NOW + timedelta(days=60)
