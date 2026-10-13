from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db.models import Invoice, InvoiceStatus, Plan
from app.services.invoices import (
    REUSE_COOLDOWN,
    NoFreeAmountError,
    cancel_invoice,
    create_invoice,
    expire_invoices,
)

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
TTL = timedelta(minutes=60)


async def issue(session, user_id, plan_id=1, now=NOW, slots=99):
    plan = await session.get(Plan, plan_id)
    return await create_invoice(
        session, user_id=user_id, plan=plan, network="TRC20", address="TAddr", ttl=TTL, slots=slots, now=now
    )


async def test_each_pending_invoice_gets_a_unique_amount(session):
    first = await issue(session, 1)
    second = await issue(session, 2)
    assert first.amount == Decimal("30.01")
    assert second.amount == Decimal("30.02")
    assert first.status == InvoiceStatus.PENDING
    assert first.expires_at == NOW + TTL


async def test_same_user_and_plan_reuses_open_invoice(session):
    first = await issue(session, 1)
    again = await issue(session, 1)
    assert again.id == first.id


async def test_different_plans_do_not_collide(session):
    monthly = await issue(session, 1, plan_id=1)
    quarterly = await issue(session, 1, plan_id=2)
    assert monthly.amount == Decimal("30.01")
    assert quarterly.amount == Decimal("80.01")


async def test_cancelled_amount_is_freed(session):
    first = await issue(session, 1)
    assert await cancel_invoice(session, first.id, user_id=1)
    second = await issue(session, 2)
    assert second.amount == first.amount


async def test_cancel_only_own_pending_invoice(session):
    invoice = await issue(session, 1)
    assert not await cancel_invoice(session, invoice.id, user_id=2)


async def test_expired_amount_stays_reserved_during_cooldown(session):
    first = await issue(session, 1)
    later = NOW + TTL + timedelta(minutes=1)
    assert await expire_invoices(session, now=later) == 1
    await session.refresh(first)
    assert first.status == InvoiceStatus.EXPIRED

    second = await issue(session, 2, now=later)
    assert second.amount == Decimal("30.02")

    much_later = NOW + TTL + REUSE_COOLDOWN + timedelta(minutes=1)
    third = await issue(session, 3, now=much_later)
    assert third.amount == Decimal("30.01")


async def test_expired_invoice_is_not_returned_as_open(session):
    first = await issue(session, 1)
    again = await issue(session, 1, now=NOW + TTL + timedelta(seconds=1))
    assert again.id != first.id


async def test_runs_out_of_amounts(session):
    await issue(session, 1, slots=2)
    await issue(session, 2, slots=2)
    with pytest.raises(NoFreeAmountError):
        await issue(session, 3, slots=2)


async def test_paid_amount_can_be_reused(session):
    first = await issue(session, 1)
    first.status = InvoiceStatus.PAID
    await session.commit()
    second = await issue(session, 2)
    assert second.amount == Decimal("30.01")
    assert isinstance(second, Invoice)
