"""Debate session persistence tests.

验证辩论对应 chat 页面一个会话标签（type='debate'）：
- POST /debate/start-stream 建 ChatSession + 落每个 opinion / summary 为 ChatMessage
- 首事件 event: session 暴露 session_id
- GET /chat/sessions/{id} 能取回 type='debate' + 带 meta 的 messages
- GET /chat/sessions 列表含该 debate 会话且 type='debate'

orchestrator + LLM 用桩替换（不打真实 FactBook / 联网 / LLM）。
Run via pytest。
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
from app.models.stock import Stock  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.debate.orchestrator import (  # noqa: E402
    AgentOpinion,
    DebateOrchestrator,
    DebateRound,
)
from app.services.llm import manager as llm_mod  # noqa: E402
from app.utils.security import hash_password  # noqa: E402


async def _fake_run_debate_stream(self, agents, target_info, max_rounds):
    """桩：直接 yield 一个分析轮 + 一段总结，不打 LLM/FactBook。"""
    yield DebateRound(
        round_type="analysis",
        opinions=[
            AgentOpinion(agent_id=agents[0]["id"], agent_name=agents[0]["name"], content="测试观点A"),
            AgentOpinion(agent_id=agents[1]["id"], agent_name=agents[1]["name"], content="测试观点B"),
        ],
    )
    yield "测试总结：多空分歧。"


async def _main() -> int:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(User(username="debate_test", email="d@d.com",
                    password_hash=hash_password("pw"), role="user", is_active=True))
        db.add(Agent(id=1, name="测试A", type="master", system_prompt="A", description=""))
        db.add(Agent(id=2, name="测试B", type="master", system_prompt="B", description=""))
        db.add(Stock(code="600519", name="贵州茅台", market="SH", is_active=True))
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
    # 桩：orchestrator 不打 LLM/FactBook；llm_manager.get 返回 None（orchestrator 不用）
    orig_gen = DebateOrchestrator.run_debate_stream
    orig_get = llm_mod.llm_manager.get
    DebateOrchestrator.run_debate_stream = _fake_run_debate_stream
    llm_mod.llm_manager.get = lambda: type("L", (), {})()  # dummy llm

    failures: list[str] = []

    def check(label, cond):
        print(f"  {'PASS' if cond else 'FAIL'}: {label}")
        if not cond:
            failures.append(label)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            tok = (await c.post("/api/v1/auth/login",
                                json={"username": "debate_test", "password": "pw"})).json()["access_token"]
            h = {"Authorization": f"Bearer {tok}"}

            # 开辩（SSE）
            r = await c.post("/api/v1/debate/start-stream", headers=h,
                             json={"agent_ids": [1, 2], "target_type": "stock",
                                   "target_id": "600519", "rounds": 1})
            check("start-stream -> 200", r.status_code == 200)

            # 解析 SSE 事件
            session_id = None
            rounds = []
            summary = None
            for block in r.text.split("\n\n"):
                lines = block.strip().split("\n")
                if len(lines) < 2:
                    continue
                ev = lines[0].replace("event: ", "")
                data_str = lines[1].replace("data: ", "")
                import json as _j
                try:
                    data = _j.loads(data_str)
                except Exception:
                    continue
                if ev == "session":
                    session_id = data.get("session_id")
                elif ev == "round":
                    rounds.append(data)
                elif ev == "summary":
                    summary = data.get("summary")

            check("session 事件暴露 session_id", session_id is not None)
            check("至少 1 轮 round", len(rounds) >= 1)
            check("round 含 opinions", bool(rounds[0].get("opinions")))
            check("summary 事件", summary is not None)

            # GET /chat/sessions/{id} 回看
            r = await c.get(f"/api/v1/chat/sessions/{session_id}", headers=h)
            sess = r.json()
            check("get debate session -> 200", r.status_code == 200)
            check("session type=debate", sess.get("type") == "debate")
            msgs = sess.get("messages", [])
            check("含 user 消息", any(m["role"] == "user" for m in msgs))
            assistant = [m for m in msgs if m["role"] == "assistant"]
            check("含 2 条 opinion 消息", sum(1 for m in assistant if (m.get("meta") or {}).get("round_type") == "analysis") == 2)
            check("含 1 条 summary 消息", sum(1 for m in assistant if (m.get("meta") or {}).get("round_type") == "summary") == 1)
            check("opinion meta 带 agent_name",
                  all((m.get("meta") or {}).get("agent_name") for m in assistant if (m.get("meta") or {}).get("round_type") == "analysis"))

            # 列表含该 debate 会话且 type=debate
            r = await c.get("/api/v1/chat/sessions", headers=h)
            lst = r.json()
            mine = [s for s in lst if s["id"] == session_id]
            check("列表含本 debate 会话", len(mine) == 1)
            check("列表项 type=debate", mine and mine[0].get("type") == "debate")
    finally:
        DebateOrchestrator.run_debate_stream = orig_gen
        llm_mod.llm_manager.get = orig_get
        app.dependency_overrides.clear()
        await engine.dispose()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    print(f"\n{'ALL PASSED' if not failures else 'FAILURES: ' + str(failures)}")
    return 0 if not failures else 1


async def test_debate_session():
    assert await _main() == 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
