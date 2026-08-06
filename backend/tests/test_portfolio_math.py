"""Portfolio accumulation tests (ISSUE-029).

Adding more of an existing stock must accumulate shares + recompute the
weighted-average cost basis (previously the existing item was skipped, so
shares/avg_cost stayed stale). Each add with shares>0 records a buy
Transaction for auditability.
"""

import os
import sys
import tempfile

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base  # noqa: E402
from app.models.portfolio import PortfolioItem, Transaction  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.portfolio.manager import PortfolioManager  # noqa: E402
from app.utils.security import hash_password  # noqa: E402


async def _fresh():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory, tmp.name


async def test_add_accumulates_weighted_avg_cost():
    engine, factory, db_path = await _fresh()
    try:
        async with factory() as db:
            db.add(User(username="pf", email="pf@pf.com",
                        password_hash=hash_password("pw"), role="user", is_active=True))
            await db.commit()
            uid = (await db.execute(select(User).where(User.username == "pf"))).scalar_one().id
            mgr = PortfolioManager(db)
            p = await mgr.create(uid, "p")
            pid = p.id

            # First add: 100 @ 10
            await mgr.add_stocks(pid, ["600519"], shares=100, avg_cost=10)
            # Second add: 100 @ 20 -> 200 @ 15 (weighted)
            await mgr.add_stocks(pid, ["600519"], shares=100, avg_cost=20)
            await db.commit()

            item = (await db.execute(
                select(PortfolioItem).where(PortfolioItem.portfolio_id == pid)
            )).scalar_one()
            assert item.shares == 200, f"shares should accumulate to 200, got {item.shares}"
            assert abs(item.avg_cost - 15.0) < 1e-6, f"avg_cost should be 15, got {item.avg_cost}"

            # Two buy transactions recorded.
            txns = (await db.execute(
                select(Transaction).where(Transaction.portfolio_id == pid).order_by(Transaction.ts)
            )).scalars().all()
            assert len(txns) == 2, f"expected 2 transactions, got {len(txns)}"
            assert all(t.side == "buy" for t in txns)
            assert txns[0].shares == 100 and abs(txns[0].price - 10) < 1e-9
            assert txns[1].shares == 100 and abs(txns[1].price - 20) < 1e-9
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass


async def test_watchlist_add_no_transaction():
    """shares==0 (add-by-filter watchlist) ensures the item exists but records
    no transaction and doesn't break accumulation."""
    engine, factory, db_path = await _fresh()
    try:
        async with factory() as db:
            db.add(User(username="pf2", email="p2@p.com",
                        password_hash=hash_password("pw"), role="user", is_active=True))
            await db.commit()
            uid = (await db.execute(select(User).where(User.username == "pf2"))).scalar_one().id
            mgr = PortfolioManager(db)
            pid = (await mgr.create(uid, "p")).id

            await mgr.add_stocks(pid, ["000001"], shares=0, avg_cost=0)  # watchlist
            await db.commit()

            item = (await db.execute(select(PortfolioItem))).scalar_one()
            assert item.shares == 0
            txns = (await db.execute(select(Transaction))).scalars().all()
            assert txns == [], "watchlist add (shares=0) must not record a transaction"
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass
