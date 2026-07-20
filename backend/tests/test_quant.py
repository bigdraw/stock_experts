"""Quant router end-to-end tests: hit the maverick-ported endpoints via ASGITransport.

Verifies wiring (routes resolve, auth gates, payloads compute). Uses a temp
SQLite + get_db override so it never touches the real stock.db.
Run via ``python -m tests.test_quant`` or pytest."""

import asyncio
import os
import sys
import tempfile

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

# Generate valid business-day dates (avoid invalid calendar dates like 2024-01-32).
import pandas as _pd  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.utils.security import hash_password  # noqa: E402

_DATES = [d.strftime("%Y-%m-%d") for d in _pd.bdate_range("2024-01-01", periods=59)]
BARS = [
    {"date": _DATES[i], "close": 100 + i * 0.5, "high": 101 + i * 0.5,
     "low": 99 + i * 0.5, "volume": 10000 + i * 100}
    for i in range(len(_DATES))
]


async def _setup() -> tuple[dict[str, str],]:
    """Seed temp DB with admin + normal users, override get_db, return token headers."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add_all([
            User(username="q_admin", password_hash=hash_password("pw"), role="admin", is_active=True),
            User(username="q_user", password_hash=hash_password("pw"), role="user", is_active=True),
        ])
        await db.commit()

    async def _get_test_db() -> AsyncSession:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _get_test_db

    tokens: dict[str, str] = {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for name in ("q_admin", "q_user"):
            r = await c.post("/api/v1/auth/login", json={"username": name, "password": "pw"})
            tokens[name] = r.json().get("access_token")
    return tokens


def main() -> int:
    return asyncio.run(_main())


async def _main() -> int:
    tokens = await _setup()
    admin_h = {"Authorization": f"Bearer {tokens['q_admin']}"}
    user_h = {"Authorization": f"Bearer {tokens['q_user']}"}
    failures: list[str] = []

    def check(label, cond):
        print(f"  {'PASS' if cond else 'FAIL'}: {label}")
        if not cond:
            failures.append(label)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # 1. strategies list (user)
        r = await c.get("/api/v1/quant/strategies", headers=user_h)
        check("GET /strategies -> 200", r.status_code == 200)
        check("strategies includes sma_cross", "sma_cross" in r.json())

        # 2. parse NL (user)
        r = await c.post("/api/v1/quant/strategies/parse", headers=user_h,
                         json={"description": "用 10 和 30 的 SMA 金叉"})
        check("parse -> sma_cross 10/30",
              r.status_code == 200 and r.json()["strategy_type"] == "sma_cross"
              and r.json()["parameters"]["fast_period"] == 10)

        # 3. backtest (user)
        r = await c.post("/api/v1/quant/backtest", headers=user_h,
                         json={"strategy_type": "sma_cross",
                               "parameters": {"fast_period": 5, "slow_period": 10},
                               "bars": BARS})
        check("POST /backtest -> 200 with metrics",
              r.status_code == 200 and "metrics" in r.json()
              and "total_return" in r.json()["metrics"])

        # 4. regime (user)
        r = await c.post("/api/v1/quant/regime", headers=user_h,
                         json={"prices": [100 + i * 0.3 for i in range(60)],
                          "vix_level": 15, "breadth_ratio": 0.6})
        check("POST /regime -> 200 + regime field",
              r.status_code == 200 and r.json()["regime"] in
              ("bull", "bear", "choppy", "transitional"))

        # 5. risk dashboard (user)
        r = await c.post("/api/v1/quant/risk/dashboard", headers=user_h,
                         json={"positions": [
                             {"symbol": "600519", "shares": 100, "cost_basis": 1500,
                              "current_price": 1800, "sector": "白酒"}]})
        check("POST /risk/dashboard -> 200 + total_value",
              r.status_code == 200 and "total_value" in r.json())

        # 6. signals evaluate (user)
        r = await c.post("/api/v1/quant/signals/evaluate", headers=user_h,
                         json={"condition": {"indicator": "price", "operator": "gt", "threshold": 100},
                               "bars": BARS})
        check("POST /signals/evaluate -> 200 + triggered",
              r.status_code == 200 and "triggered" in r.json())

        # 7. journal trades — non-admin blocked (403)
        r = await c.post("/api/v1/quant/journal/trades", headers=user_h,
                         json={"symbol": "600519", "side": "long", "entry_price": 1500, "shares": 100})
        check("non-admin journal write -> 403", r.status_code == 403)

        # 8. journal trade — admin ok
        r = await c.post("/api/v1/quant/journal/trades", headers=admin_h,
                         json={"symbol": "600519", "side": "long", "entry_price": 1500,
                               "shares": 100, "tags": ["trend"], "status": "closed", "pnl": 200})
        check("admin journal write -> 200", r.status_code == 200 and "id" in r.json())

        # 9. strategy recompute (admin)
        r = await c.post("/api/v1/quant/journal/recompute/trend", headers=admin_h)
        check("admin recompute -> 200 + win_count",
              r.status_code == 200 and "win_count" in r.json())

        # 10. audit decisions (admin)
        r = await c.get("/api/v1/quant/audit/decisions", headers=admin_h)
        check("admin audit decisions -> 200 list", r.status_code == 200 and isinstance(r.json(), list))

        # 11. no-token -> 401
        r = await c.get("/api/v1/quant/strategies")
        check("no-token /strategies -> 401", r.status_code == 401)

    app.dependency_overrides.clear()
    print(f"\n{'ALL PASSED' if not failures else 'FAILURES: '+str(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())


async def test_quant_router():
    assert await _main() == 0
