"""What the scheduler needs to act on: renewal reminders and expired access."""

from datetime import datetime, timedelta
import math

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Subscription
from app.services.subscriptions import as_utc

REMINDER_DAYS = (3, 1)


def _latest_per_user():
    return select(Subscription.user_id, func.max(Subscription.ends_at).label("ends_at")).group_by(
        Subscription.user_id
    ).subquery()


async def _latest_subscriptions(session: AsyncSession, *conditions) -> list[Subscription]:
    latest = _latest_per_user()
    return list(
        await session.scalars(
            select(Subscription)
            .join(latest, (Subscription.user_id == latest.c.user_id) & (Subscription.ends_at == latest.c.ends_at))
            .where(*conditions)
        )
    )


async def due_reminders(session: AsyncSession, now: datetime) -> list[tuple[Subscription, int]]:
    """Users whose access ends in 3 or 1 days and who haven't been reminded for that day yet."""
    window = timedelta(days=max(REMINDER_DAYS))
    subs = await _latest_subscriptions(
        session, Subscription.ends_at > now, Subscription.ends_at <= now + window
    )
    due = []
    for sub in subs:
        days_left = math.ceil((as_utc(sub.ends_at) - now) / timedelta(days=1))
        reminder = next((d for d in sorted(REMINDER_DAYS) if days_left <= d), None)
        if reminder is not None and (sub.reminded_days is None or sub.reminded_days > reminder):
            due.append((sub, reminder))
    return due


async def due_revocations(session: AsyncSession, now: datetime, grace: timedelta) -> list[Subscription]:
    """Users whose latest subscription ended (plus grace) and who are still in the channel."""
    return await _latest_subscriptions(
        session, Subscription.ends_at <= now - grace, Subscription.access_revoked.is_(False)
    )


async def mark_revoked(session: AsyncSession, user_id: int) -> None:
    await session.execute(update(Subscription).where(Subscription.user_id == user_id).values(access_revoked=True))
    await session.commit()
