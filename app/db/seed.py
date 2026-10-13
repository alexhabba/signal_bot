from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Plan

# Placeholder prices until the real ones are decided; edit them in the plans table.
DEFAULT_PLANS = [
    ("1 месяц", 30, Decimal("30")),
    ("3 месяца", 90, Decimal("80")),
    ("12 месяцев", 365, Decimal("250")),
]


async def seed_plans(session: AsyncSession) -> None:
    if await session.scalar(select(func.count()).select_from(Plan)):
        return
    session.add_all(
        Plan(title=title, days=days, price=price, sort_order=i) for i, (title, days, price) in enumerate(DEFAULT_PLANS)
    )
    await session.commit()
