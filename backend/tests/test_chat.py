"""Chat session + streaming tests.

Test session CRUD + SSE streaming + context compression.
Run via pytest.
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
from app.models.user import User  # noqa: E402
from app.services.chat_pipeline import estimate_tokens, should_compress  # noqa: E402
from app.utils.security import hash_password  # noqa: E402


async def _main() -> int:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(User(username="chat_test", email="test@test.com",
                    password_hash=hash_password("pw"), role="user", is_active=True))
        await db.commit()

    async def _gdb():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _gdb
    failures: list[str] = []

    def check(label, cond):
        print(f"  {'PASS' if cond else 'FAIL'}: {label}")
        if not cond:
            failures.append(label)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        tok = (await c.post("/api/v1/auth/login", json={"username": "chat_test", "password": "pw"})).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}

        # 1. Create session
        r = await c.post("/api/v1/chat/sessions", headers=h, json={"title": "测试对话", "agent_ids": []})
        check("create session -> 200", r.status_code == 200)
        sid = r.json().get("id")
        check("session has id", sid is not None)

        # 2. List sessions
        r = await c.get("/api/v1/chat/sessions", headers=h)
        check("list sessions -> has 1", r.status_code == 200 and len(r.json()) >= 1)

        # 3. Get session
        r = await c.get(f"/api/v1/chat/sessions/{sid}", headers=h)
        check("get session -> has title", r.status_code == 200 and r.json().get("title") == "测试对话")
        check("get session -> empty messages", r.json().get("messages") == [])

        # 4. Patch (rename)
        r = await c.patch(f"/api/v1/chat/sessions/{sid}", headers=h, json={"title": "改名后"})
        check("patch session -> renamed", r.status_code == 200 and r.json().get("title") == "改名后")

        # 5. Delete
        r = await c.delete(f"/api/v1/chat/sessions/{sid}", headers=h)
        check("delete session -> ok", r.status_code == 200 and r.json().get("status") == "deleted")
        r = await c.get(f"/api/v1/chat/sessions/{sid}", headers=h)
        check("deleted session -> error", "error" in r.json())

        # 6. Unit tests for compression
        check("estimate_tokens non-zero", estimate_tokens("hello world") > 0)
        check("should_compress false for short", not should_compress([{"content": "hi"}]))
        check("should_compress true for huge", should_compress([{"content": "x" * 300000}]))

    app.dependency_overrides.clear()
    await engine.dispose()
    try:
        os.unlink(tmp.name)
    except OSError:
        pass

    print(f"\n{'ALL PASSED' if not failures else 'FAILURES: ' + str(failures)}")
    return 0 if not failures else 1


async def test_chat_sessions():
    assert await _main() == 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
