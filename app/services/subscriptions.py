from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Subscription


async def active_until(session: AsyncSession, user_id: int, now: datetime | None = None) -> datetime | None:
    """End of the user's access, or None if they have no active subscription."""
    now = now or datetime.now(timezone.utc)
    ends_at = await session.scalar(select(func.max(Subscription.ends_at)).where(Subscription.user_id == user_id))
    if ends_at is None:
        return None
    if ends_at.tzinfo is None:  # SQLite drops tzinfo
        ends_at = ends_at.replace(tzinfo=timezone.utc)
    return ends_at if ends_at > now else None
