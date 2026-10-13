from datetime import datetime, timedelta, timezone

from app.db.models import Subscription, SubscriptionSource
from app.services.lifecycle import due_reminders, due_revocations, mark_revoked

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


async def add_sub(session, user_id, ends_at, **kwargs):
    sub = Subscription(
        user_id=user_id, starts_at=ends_at - timedelta(days=30), ends_at=ends_at, source=SubscriptionSource.ADMIN, **kwargs
    )
    session.add(sub)
    await session.commit()
    return sub


async def test_reminds_at_three_days_then_one_day(session):
    sub = await add_sub(session, 1, NOW + timedelta(days=2, hours=12))
    assert [(s.id, d) for s, d in await due_reminders(session, NOW)] == [(sub.id, 3)]

    sub.reminded_days = 3
    await session.commit()
    assert await due_reminders(session, NOW) == []
    assert [(s.id, d) for s, d in await due_reminders(session, NOW + timedelta(days=2))] == [(sub.id, 1)]


async def test_no_reminder_when_far_from_end_or_renewed(session):
    await add_sub(session, 1, NOW + timedelta(days=10))
    await add_sub(session, 2, NOW + timedelta(days=2))
    await add_sub(session, 2, NOW + timedelta(days=32))  # already renewed
    assert await due_reminders(session, NOW) == []


async def test_revokes_expired_users_once(session):
    await add_sub(session, 1, NOW - timedelta(hours=1))
    await add_sub(session, 2, NOW + timedelta(days=5))
    due = await due_revocations(session, NOW, grace=timedelta(0))
    assert [s.user_id for s in due] == [1]

    await mark_revoked(session, 1)
    assert await due_revocations(session, NOW, grace=timedelta(0)) == []


async def test_grace_period_delays_removal(session):
    await add_sub(session, 1, NOW - timedelta(hours=1))
    assert await due_revocations(session, NOW, grace=timedelta(hours=24)) == []


async def test_renewed_user_is_not_revoked(session):
    await add_sub(session, 1, NOW - timedelta(days=1))
    await add_sub(session, 1, NOW + timedelta(days=29))
    assert await due_revocations(session, NOW, grace=timedelta(0)) == []
