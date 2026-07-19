"""Authorization tests: confirm admin-gating of settings/data/tasks routes
and the is_active check on get_current_user.

Runnable both via ``pytest tests/test_authz.py`` and standalone:
``python -m tests.test_authz``

Uses an in-memory-temp-file SQLite + dependency override of get_db so it
never touches the real stock.db. This is the P0-C verification and the
seed fixture for the P2 test suite.
"""

import asyncio
import os
import sys
import tempfile

# Ensure backend root is on sys.path when run as a script.
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
from app.models.user import User  # noqa: E402
from app.utils.security import hash_password  # noqa: E402

ADMIN = ("authz_admin", "admin")
NORMAL = ("authz_normal", "user")
DISABLED = ("authz_disabled", "user")


async def _seed(test_engine):
    """Create a fresh temp DB, seed three users, return credentials->token map."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add_all([
            User(username=ADMIN[0], password_hash=hash_password("pw-admin"), role=ADMIN[1], is_active=True),
            User(username=NORMAL[0], password_hash=hash_password("pw-normal"), role=NORMAL[1], is_active=True),
            User(username=DISABLED[0], password_hash=hash_password("pw-disabled"), role=DISABLED[1], is_active=False),
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
        for (name, _), pw in [(ADMIN, "pw-admin"), (NORMAL, "pw-normal"), (DISABLED, "pw-disabled")]:
            r = await client.post("/api/v1/auth/login", json={"username": name, "password": pw})
            tokens[name] = r.json().get("access_token")
    return tokens


async def main():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    try:
        tokens = await _seed(test_engine)
        failures = []

        def check(label, cond):
            print(f"  {'PASS' if cond else 'FAIL'}: {label}")
            if not cond:
                failures.append(label)

        admin_h = {"Authorization": f"Bearer {tokens[ADMIN[0]]}"}
        normal_h = {"Authorization": f"Bearer {tokens[NORMAL[0]]}"}
        disabled_h = {"Authorization": f"Bearer {tokens[DISABLED[0]]}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. No token -> 401 on protected route
            r = await client.get("/api/v1/settings/proxy")
            check("no-token settings/proxy -> 401", r.status_code == 401)

            # 2. Non-admin -> 403 on admin-gated settings route
            r = await client.get("/api/v1/settings/proxy", headers=normal_h)
            check("non-admin settings/proxy -> 403", r.status_code == 403)

            # 3. Non-admin -> 403 on data collection trigger (must gate BEFORE bg task starts)
            r = await client.post("/api/v1/data/collect/full", headers=normal_h)
            check("non-admin data/collect/full -> 403", r.status_code == 403)

            # 4. Non-admin -> 403 on task control (stop). Must gate before 404.
            r = await client.post("/api/v1/tasks/nope/stop", headers=normal_h)
            check("non-admin tasks/{id}/stop -> 403", r.status_code == 403)

            # 5. Non-admin -> 200 on user-level route (auth/me)
            r = await client.get("/api/v1/auth/me", headers=normal_h)
            check("non-admin auth/me -> 200", r.status_code == 200)

            # 6. Disabled user (valid token, is_active=False) -> 401 on auth/me
            r = await client.get("/api/v1/auth/me", headers=disabled_h)
            check("disabled-user auth/me -> 401 (is_active enforced)", r.status_code == 401)

            # 7. Admin -> 200 on auth/me
            r = await client.get("/api/v1/auth/me", headers=admin_h)
            check("admin auth/me -> 200", r.status_code == 200)

        app.dependency_overrides.clear()
        print(f"\n{'ALL PASSED' if not failures else 'FAILURES: '+str(failures)}")
        return 0 if not failures else 1
    finally:
        await test_engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))


# pytest entrypoint (asyncio_mode = "auto" runs this). The standalone
# `python -m tests.test_authz` path above is kept for manual/ad-hoc runs.
async def test_authz_gating():
    assert await main() == 0
