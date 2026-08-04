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


async def _delete_main() -> int:
    """删会话必须级联删消息——否则 SQLite 复用 id 时新会话会"复活"旧对话。"""
    from sqlalchemy import select as sa_select

    from app.models.chat import ChatMessage

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(User(username="del_test", email="d@d.com",
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
        tok = (await c.post("/api/v1/auth/login", json={"username": "del_test", "password": "pw"})).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}

        # 1. 建会话 S1 + 直接种子 2 条消息（绕开 LLM）
        r = await c.post("/api/v1/chat/sessions", headers=h, json={"title": "s1", "agent_ids": []})
        s1 = r.json()["id"]
        async with factory() as db:
            db.add(ChatMessage(session_id=s1, role="user", content="旧用户消息"))
            db.add(ChatMessage(session_id=s1, role="assistant", content="旧助手消息"))
            await db.commit()

        r = await c.get(f"/api/v1/chat/sessions/{s1}", headers=h)
        check("seed: S1 有 2 条消息", len(r.json().get("messages", [])) == 2)

        # 2. 删 S1
        r = await c.delete(f"/api/v1/chat/sessions/{s1}", headers=h)
        check("delete -> ok", r.status_code == 200 and r.json().get("status") == "deleted")

        # 3. S1 取不到了
        r = await c.get(f"/api/v1/chat/sessions/{s1}", headers=h)
        check("S1 已删", "error" in r.json())

        # 4. 消息表里 S1 的消息也清了（无孤儿）
        async with factory() as db:
            cnt = (await db.execute(sa_select(ChatMessage).where(ChatMessage.session_id == s1))).scalars().all()
        check("无孤儿消息", len(cnt) == 0)

        # 5. 新建 S2 可能复用 s1 的 id → 必须是空的（不复活旧对话）
        r = await c.post("/api/v1/chat/sessions", headers=h, json={"title": "s2", "agent_ids": []})
        s2 = r.json()["id"]
        r = await c.get(f"/api/v1/chat/sessions/{s2}", headers=h)
        check(f"S2(id={s2}, S1={s1}) 不复活旧消息", r.json().get("messages") == [])

    app.dependency_overrides.clear()
    await engine.dispose()
    try:
        os.unlink(tmp.name)
    except OSError:
        pass

    print(f"\n{'ALL PASSED' if not failures else 'FAILURES: ' + str(failures)}")
    return 0 if not failures else 1


async def test_chat_delete_cascade():
    assert await _delete_main() == 0


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(_main()) == 0 and asyncio.run(_delete_main()) == 0 else 1)
