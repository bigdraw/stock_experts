"""IDOR / ownership tests (ISSUE-019).

Asserts that portfolio / notification / alert / agent-delete endpoints refuse
cross-user access: a request naming another user's private resource returns 404
(not 200 leaking its contents), and deactivating a shared/master agent requires
admin (403 for normal users).

Runnable via ``pytest tests/test_idor.py`` or standalone ``python -m tests.test_idor``.
Uses an in-memory-temp-file SQLite + dependency override of get_db so it never
touches the real stock.db.
"""

import asyncio
import os
import sys
import tempfile

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.agent import Agent  # noqa: E402
from app.models.notification import Alert, Notification  # noqa: E402
from app.models.user import User  # noqa: E402
from app.utils.security import hash_password  # noqa: E402

ADMIN = ("idor_admin", "admin")
USERA = ("idor_a", "user")
USERB = ("idor_b", "user")


async def _seed(test_engine):
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add_all([
            User(username=ADMIN[0], password_hash=hash_password("pw"), role=ADMIN[1], is_active=True),
            User(username=USERA[0], password_hash=hash_password("pw"), role=USERA[1], is_active=True),
            User(username=USERB[0], password_hash=hash_password("pw"), role=USERB[1], is_active=True),
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

    tokens = {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for name, pw in [(ADMIN[0], "pw"), (USERA[0], "pw"), (USERB[0], "pw")]:
            r = await client.post("/api/v1/auth/login", json={"username": name, "password": pw})
            tokens[name] = r.json().get("access_token")
    return tokens, factory


async def main():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    try:
        tokens, factory = await _seed(test_engine)
        failures = []

        def check(label, cond):
            print(f"  {'PASS' if cond else 'FAIL'}: {label}")
            if not cond:
                failures.append(label)

        a_h = {"Authorization": f"Bearer {tokens[USERA[0]]}"}
        b_h = {"Authorization": f"Bearer {tokens[USERB[0]]}"}
        admin_h = {"Authorization": f"Bearer {tokens[ADMIN[0]]}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # --- portfolio IDOR ---
            # USERA creates a portfolio + an item
            r = await client.post("/api/v1/portfolios", json={"name": "A's folio"}, headers=a_h)
            check("userA create portfolio -> 200", r.status_code == 200)
            pa_id = r.json().get("id")

            # USERA can read its own
            r = await client.get(f"/api/v1/portfolios/{pa_id}", headers=a_h)
            check("userA read own portfolio -> 200", r.status_code == 200)

            # USERB must NOT read USERA's portfolio (404, not 200)
            r = await client.get(f"/api/v1/portfolios/{pa_id}", headers=b_h)
            check("userB read A's portfolio -> 404 (IDOR blocked)", r.status_code == 404)

            # USERB must NOT add an item to USERA's portfolio
            r = await client.post(
                f"/api/v1/portfolios/{pa_id}/items",
                json={"stock_code": "600519"},
                headers=b_h,
            )
            check("userB add item to A's portfolio -> 404", r.status_code == 404)

            # USERB must NOT delete USERA's portfolio
            r = await client.delete(f"/api/v1/portfolios/{pa_id}", headers=b_h)
            check("userB delete A's portfolio -> 404", r.status_code == 404)

            # USERA still owns it (delete was blocked)
            r = await client.get(f"/api/v1/portfolios/{pa_id}", headers=a_h)
            check("A's portfolio survived B's delete attempt", r.status_code == 200)

            # --- notification IDOR ---
            async with factory() as db:
                n = Notification(user_id=1, type="system", title="x", content="x")  # admin's
                al = Alert(
                    user_id=1, name="a", nl_condition="x", condition_code="",
                    target_type="stock",
                )
                db.add_all([n, al])
                await db.commit()
                n_id, al_id = n.id, al.id

            # USERB must NOT mark admin's notification read (404, not 200)
            r = await client.put(f"/api/v1/notifications/{n_id}/read", headers=b_h)
            check("userB mark admin's notification read -> 404", r.status_code == 404)

            # USERB must NOT toggle/delete admin's alert
            r = await client.put(f"/api/v1/notifications/alerts/{al_id}/toggle", headers=b_h)
            check("userB toggle admin's alert -> 404", r.status_code == 404)
            r = await client.delete(f"/api/v1/notifications/alerts/{al_id}", headers=b_h)
            check("userB delete admin's alert -> 404", r.status_code == 404)

            # admin can toggle own alert
            r = await client.put(f"/api/v1/notifications/alerts/{al_id}/toggle", headers=admin_h)
            check("admin toggle own alert -> 200", r.status_code == 200)

            # --- agent delete admin-gate ---
            async with factory() as db:
                ag = Agent(name="guru", type="master", system_prompt="x")
                db.add(ag)
                await db.commit()
                ag_id = ag.id

            # normal USERA -> 403 (shared resource, admin-only)
            r = await client.delete(f"/api/v1/agents/{ag_id}", headers=a_h)
            check("userA delete master agent -> 403", r.status_code == 403)

            # admin -> 200
            r = await client.delete(f"/api/v1/agents/{ag_id}", headers=admin_h)
            check("admin delete master agent -> 200", r.status_code == 200)

        app.dependency_overrides.clear()
        print(f"\n{'ALL PASSED' if not failures else 'FAILURES: ' + str(failures)}")
        return 0 if not failures else 1
    finally:
        await test_engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass


async def test_idor_ownership():
    assert await main() == 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
