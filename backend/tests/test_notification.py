"""Notification alert evaluation tests (ISSUE-025).

check_alerts must (a) assemble the target stock's latest data so the generated
check(data) can read data['close']/['pe_ratio'] (previously passed {} → KeyError
swallowed → alert never fired), and (b) actually fire a Notification when the
condition holds. alert_check/backup_reminder scheduler stubs now drive the
engines (no longer log-only).
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
from app.models.notification import Alert, Notification  # noqa: E402
from app.models.stock import FinancialReport, Stock  # noqa: E402
from app.models.user import User  # noqa: E402
from app.scheduler import jobs  # noqa: E402
from app.services.notification.service import AlertEngine  # noqa: E402
from app.utils.security import hash_password  # noqa: E402


async def _fresh():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory, tmp.name


async def test_check_alerts_assembles_data_and_fires():
    engine, factory, db_path = await _fresh()
    try:
        async with factory() as db:
            db.add(User(username="alert_user", email="a@a.com",
                        password_hash=hash_password("pw"), role="user", is_active=True))
            db.add(Stock(code="600519", name="贵州茅台", market="SH", is_active=True))
            await db.commit()
            # Latest snapshot the generated check(data) reads.
            db.add(FinancialReport(
                stock_code="600519", report_type="Latest", report_date=__import__("datetime").date(2026, 8, 6),
                price=150.0, pe_ratio=25.0, pb_ratio=8.0, market_cap=100000.0,
            ))
            await db.commit()
            uid = (await db.execute(select(User).where(User.username == "alert_user"))).scalar_one().id
            # check reads data['close'] > 100 → True with price=150.
            db.add(Alert(
                user_id=uid, name="茅台破百", nl_condition="close>100",
                condition_code="def check(data):\n    return data.get('close', 0) > 100\n",
                target_type="stock", target_id="600519", is_active=True,
            ))
            await db.commit()

        # AlertEngine with a dummy LLM (check_alerts doesn't call the LLM).
        async with factory() as db:
            eng = AlertEngine(db, llm=type("L", (), {})())
            await eng.check_alerts()
            await db.commit()

        async with factory() as db:
            notes = (await db.execute(select(Notification).where(Notification.user_id != 0))).scalars().all()
            assert any(n.type == "alert" for n in notes), "alert should have fired a notification"
            al = (await db.execute(select(Alert).where(Alert.name == "茅台破百"))).scalar_one()
            assert al.last_triggered_at is not None, "last_triggered_at should be set"
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass


async def test_check_alerts_no_fire_when_condition_false():
    engine, factory, db_path = await _fresh()
    try:
        async with factory() as db:
            db.add(User(username="alert_user2", email="b@b.com",
                        password_hash=hash_password("pw"), role="user", is_active=True))
            db.add(Stock(code="000001", name="平安银行", market="SZ", is_active=True))
            await db.commit()
            db.add(FinancialReport(
                stock_code="000001", report_type="Latest", report_date=__import__("datetime").date(2026, 8, 6),
                price=12.0,
            ))
            await db.commit()
            uid = (await db.execute(select(User).where(User.username == "alert_user2"))).scalar_one().id
            db.add(Alert(
                user_id=uid, name="破百", nl_condition="close>100",
                condition_code="def check(data):\n    return data.get('close', 0) > 100\n",
                target_type="stock", target_id="000001", is_active=True,
            ))
            await db.commit()

        async with factory() as db:
            await AlertEngine(db, llm=type("L", (), {})()).check_alerts()
            await db.commit()

        async with factory() as db:
            notes = (await db.execute(select(Notification))).scalars().all()
            assert not any(n.type == "alert" for n in notes), "alert must not fire (price 12 < 100)"
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass


async def test_scheduler_alert_check_drives_engine(monkeypatch):
    """alert_check must call AlertEngine.check_alerts (no longer a log-only stub)."""
    called = {"n": 0}

    class _FakeEngine:
        def __init__(self, db, llm):
            pass

        async def check_alerts(self):
            called["n"] += 1

    import app.services.notification.service as svc_mod
    from app.services.llm import manager as llm_mod

    orig_engine = svc_mod.AlertEngine
    orig_get = llm_mod.llm_manager.get
    orig_factory = jobs.async_session_factory
    svc_mod.AlertEngine = _FakeEngine
    llm_mod.llm_manager.get = lambda: type("L", (), {})()
    try:
        engine, factory, db_path = await _fresh()
        jobs.async_session_factory = factory
        await jobs.alert_check()
        assert called["n"] == 1, "alert_check did not drive AlertEngine.check_alerts"
    finally:
        svc_mod.AlertEngine = orig_engine
        llm_mod.llm_manager.get = orig_get
        jobs.async_session_factory = orig_factory
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass
