from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import Plan, User
from app.db.session import create_tables, make_sessionmaker


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await create_tables(engine)
    async with make_sessionmaker(engine)() as session:
        session.add_all([User(id=1), User(id=2), User(id=3)])
        session.add(Plan(id=1, title="1 месяц", days=30, price=Decimal("30")))
        session.add(Plan(id=2, title="3 месяца", days=90, price=Decimal("80")))
        await session.commit()
        yield session
    await engine.dispose()
