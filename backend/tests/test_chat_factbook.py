"""Single-agent chat FactBook injection test (Part 1).

When a stock code (6 digits) is in the user message, the single-agent stream
must pre-fetch FactBook platform data + inject the digest into the agent's
context (prioritized over tavily). Mocks FactBook.collect_streaming/format +
llm.chat_stream so no network.
"""

import asyncio
import os
import sys
import tempfile

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select as sa_select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.agent import Agent  # noqa: E402
from app.models.chat import ChatMessage  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.llm.provider import LLMStreamChunk  # noqa: E402
from app.utils.security import hash_password  # noqa: E402


class _FakeLLM:
    """Yields one canned chunk; records the user message it received."""

    def __init__(self):
        self.received_user_content = ""

    async def chat_stream(self, messages, tools=None, max_tokens=None, enable_thinking=True, **kw):
        # capture the last user message (the one we injected the digest into)
        for m in reversed(messages):
            if getattr(m, "role", None) == "user":
                self.received_user_content = getattr(m, "content", "")
                break
        yield LLMStreamChunk(content="最终答案", finish_reason="stop")


async def _main() -> int:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(User(username="fb_test", email="f@f.com",
                    password_hash=hash_password("pw"), role="user", is_active=True))
        db.add(Agent(id=99, name="测试大师", type="master", system_prompt="你是测试agent", description=""))
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

    # Monkeypatch FactBook.collect_streaming (no akshare) + FactBook.format (fixed digest).
    from app.services.debate.factbook import FactBook

    async def _fake_collect(self, code, db):
        yield {"type": "collecting", "stage": "value", "message": "正在获取价值分析…"}
        yield {"type": "factbook_raw", "raw": {"stock_code": code, "stock_name": "测试股"}}

    orig_collect = FactBook.collect_streaming
    orig_format = FactBook.format
    FactBook.collect_streaming = _fake_collect
    FactBook.format = lambda self, raw: "FAKEFB DIGEST: PE=30 ROE=15%"

    fake_llm = _FakeLLM()
    from app.services.llm import manager as llm_mod
    orig_get = llm_mod.llm_manager.get
    llm_mod.llm_manager.get = lambda: fake_llm

    failures: list[str] = []

    def check(label, cond):
        print(f"  {'PASS' if cond else 'FAIL'}: {label}")
        if not cond:
            failures.append(label)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            tok = (await c.post("/api/v1/auth/login", json={"username": "fb_test", "password": "pw"})).json()["access_token"]
            h = {"Authorization": f"Bearer {tok}"}
            r = await c.post("/api/v1/chat/sessions", headers=h, json={"title": "t", "agent_ids": [99]})
            sid = r.json()["id"]
            # message with a stock code → triggers FactBook phase
            r = await c.post(f"/api/v1/chat/sessions/{sid}/stream", headers=h,
                              json={"message": "分析 600519 的估值", "agent_ids": [99]})
            body = r.text
            check("SSE has factbook_start", "event: factbook_start" in body)
            check("SSE has collecting progress", "event: collecting" in body)
            check("SSE has factbook_done with digest", "FAKEFB DIGEST" in body)
            check("SSE has assistant text", "最终答案" in body)

            # The LLM received the digest injected into its user message
            check("LLM user msg contains FactBook digest", "FAKEFB DIGEST" in fake_llm.received_user_content)

            # A system factbook ChatMessage was persisted
            async with factory() as db2:
                msgs = (await db2.execute(sa_select(ChatMessage).where(ChatMessage.session_id == sid))).scalars().all()
            fb = [m for m in msgs if (m.meta or {}).get("round_type") == "factbook"]
            check("persisted system factbook message", len(fb) == 1 and "FAKEFB DIGEST" in (fb[0].content or ""))
    finally:
        FactBook.collect_streaming = orig_collect
        FactBook.format = orig_format
        llm_mod.llm_manager.get = orig_get
        app.dependency_overrides.clear()
        await engine.dispose()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    print(f"\n{'ALL PASSED' if not failures else 'FAILURES: ' + str(failures)}")
    return 0 if not failures else 1


async def test_chat_single_agent_injects_factbook():
    assert await _main() == 0


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(_main()) == 0 else 1)
