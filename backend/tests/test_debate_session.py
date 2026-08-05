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


async def _fake_run_debate_stream(self, agents, target_info, max_rounds, **kwargs):
    """桩：yield 结构化事件（事实 agent 消化 + 2 agent + summary 流），不打 LLM。"""
    yield {"type": "factbook_start"}
    yield {"type": "factbook_token", "delta": "事实摘要"}
    yield {"type": "factbook_done", "content": "<target>测试 FactBook</target>"}
    for a in agents:
        yield {"type": "agent_start", "round_num": 1, "round_type": "analysis",
               "agent_id": a["id"], "agent_name": a["name"]}
        yield {"type": "agent_token", "round_num": 1, "agent_id": a["id"], "delta": f"观点{a['name']}"}
        yield {"type": "agent_done", "round_num": 1, "round_type": "analysis",
               "agent_id": a["id"], "agent_name": a["name"],
               "content": f"观点{a['name']}", "finish_reason": "stop"}
    yield {"type": "summary_start"}
    yield {"type": "summary_token", "delta": "测试总结"}
    yield {"type": "summary_done", "content": "测试总结：多空分歧。"}


async def _fail_first_agent_stream(self, agents, target_info, max_rounds, **kwargs):
    """桩：事实 agent 消化 + 第1个 agent 失败（agent_failed）→ 暂停，不发 done。"""
    yield {"type": "factbook_start"}
    yield {"type": "factbook_done", "content": "<target>fb</target>"}
    a = agents[0]
    yield {"type": "agent_start", "round_num": 1, "round_type": "analysis",
           "agent_id": a["id"], "agent_name": a["name"]}
    yield {"type": "agent_failed", "round_num": 1, "round_type": "analysis",
           "agent_id": a["id"], "agent_name": a["name"], "error": "LLMProviderError('RemoteDisconnected')"}


async def _cancel_after_round1_stream(self, agents, target_info, max_rounds, **kwargs):
    """桩：yield 事实 + 第1个 agent 的 done 后抛 CancelledError，模拟客户端中途断连。"""
    yield {"type": "factbook_start"}
    yield {"type": "factbook_done", "content": "<target>fb</target>"}
    a = agents[0]
    yield {"type": "agent_start", "round_num": 1, "round_type": "analysis",
           "agent_id": a["id"], "agent_name": a["name"]}
    yield {"type": "agent_token", "round_num": 1, "agent_id": a["id"], "delta": "第1轮观点"}
    yield {"type": "agent_done", "round_num": 1, "round_type": "analysis",
           "agent_id": a["id"], "agent_name": a["name"],
           "content": "第1轮观点", "finish_reason": "stop"}
    raise asyncio.CancelledError()


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
            agent_dones = []
            summary_done = None
            has_factbook = False
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
                elif ev == "factbook_done":
                    has_factbook = bool(data.get("content"))
                elif ev == "factbook_token":
                    has_factbook = has_factbook or bool(data.get("delta"))
                elif ev == "agent_done":
                    agent_dones.append(data)
                elif ev == "summary_done":
                    summary_done = data.get("content")

            check("session 事件暴露 session_id", session_id is not None)
            check("factbook 事件下发", has_factbook)
            check("2 条 agent_done", len(agent_dones) == 2)
            check("agent_done 带 content", all(d.get("content") for d in agent_dones))
            check("summary_done 事件", summary_done is not None)

            # GET /chat/sessions/{id} 回看
            r = await c.get(f"/api/v1/chat/sessions/{session_id}", headers=h)
            sess = r.json()
            check("get debate session -> 200", r.status_code == 200)
            check("session type=debate", sess.get("type") == "debate")
            msgs = sess.get("messages", [])
            check("含 user 消息", any(m["role"] == "user" for m in msgs))
            check("含 factbook system 消息",
                  any(m["role"] == "system" and (m.get("meta") or {}).get("round_type") == "factbook" for m in msgs))
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


async def _cancel_main() -> int:
    """模拟客户端中途断连（orchestrator 第1轮后抛 CancelledError）：
    会话壳 + 已 commit 的第1轮 opinion 应持久保留，不应抛 PendingRollbackError 刷屏。
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(User(username="debate_cancel", email="c@c.com",
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
            except BaseException:
                try:
                    await session.rollback()
                except BaseException:
                    pass
                raise

    app.dependency_overrides[get_db] = _gdb
    orig_gen = DebateOrchestrator.run_debate_stream
    orig_get = llm_mod.llm_manager.get
    DebateOrchestrator.run_debate_stream = _cancel_after_round1_stream
    llm_mod.llm_manager.get = lambda: type("L", (), {})()

    failures: list[str] = []

    def check(label, cond):
        print(f"  {'PASS' if cond else 'FAIL'}: {label}")
        if not cond:
            failures.append(label)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            tok = (await c.post("/api/v1/auth/login",
                                json={"username": "debate_cancel", "password": "pw"})).json()["access_token"]
            h = {"Authorization": f"Bearer {tok}"}
            # CancelledError 在生成器内被吞掉，HTTP 仍应正常结束（200），不应抛
            r = await c.post("/api/v1/debate/start-stream", headers=h,
                             json={"agent_ids": [1, 2], "target_type": "stock",
                                   "target_id": "600519", "rounds": 2})
            check("cancel: start-stream 不抛（200）", r.status_code == 200)

            session_id = None
            agent_done_count = 0
            for block in r.text.split("\n\n"):
                lines = block.strip().split("\n")
                if len(lines) < 2:
                    continue
                ev = lines[0].replace("event: ", "")
                if ev == "session":
                    import json as _j
                    session_id = _j.loads(lines[1].replace("data: ", "")).get("session_id")
                elif ev == "agent_done":
                    agent_done_count += 1
            check("cancel: 收到 session 事件", session_id is not None)
            check("cancel: 第1个 agent_done 已下发", agent_done_count >= 1)

            # 已 commit 的会话壳 + factbook + 第1个 agent_done opinion 应持久保留
            r = await c.get(f"/api/v1/chat/sessions/{session_id}", headers=h)
            sess = r.json()
            check("cancel: 会话仍存在", r.status_code == 200 and sess.get("type") == "debate")
            msgs = sess.get("messages", [])
            check("cancel: user 消息保留", any(m["role"] == "user" for m in msgs))
            check("cancel: factbook 保留",
                  any(m["role"] == "system" and (m.get("meta") or {}).get("round_type") == "factbook" for m in msgs))
            check("cancel: 第1个 agent opinion 保留",
                  any(m["role"] == "assistant" and (m.get("meta") or {}).get("round_num") == 1 for m in msgs))
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


async def test_debate_cancel():
    assert await _cancel_main() == 0


def test_challenge_sees_all_others():
    """回归：challenge 轮的 agent 必须看到上一轮（analysis）全部 *其他* agent 的发言，
    不是 history[-1]（当前正在建的轮，只含前面 agent）。"""
    orch = DebateOrchestrator(llm=None)  # _build_agent_messages 不用 llm
    agents = [
        {"id": 1, "name": "巴菲特", "system_prompt": "S1", "description": ""},
        {"id": 2, "name": "索罗斯", "system_prompt": "S2", "description": ""},
        {"id": 3, "name": "芒格", "system_prompt": "S3", "description": ""},
    ]
    # analysis 轮（round_num=0）已有全部 3 人发言
    analysis = DebateRound(round_type="analysis", opinions=[
        AgentOpinion(1, "巴菲特", "巴菲特的分析内容XYZ"),
        AgentOpinion(2, "索罗斯", "索罗斯的分析内容ABC"),
        AgentOpinion(3, "芒格", "芒格的分析内容QQQ"),
    ])
    history = [analysis, DebateRound(round_type="challenge", opinions=[])]  # challenge 轮槽位（空，正在建）

    # 第 3 个 agent（芒格）做 challenge：必须看到巴菲特+索罗斯（不是只看排前面的）
    msgs = orch._build_agent_messages(agents[2], "challenge", 1, {"name": "t", "code": "c", "data": {}}, "", history)
    user_content = msgs[1].content
    assert "巴菲特的分析内容XYZ" in user_content, f"challenge 应含巴菲特(排在前): {user_content[:80]}"
    assert "索罗斯的分析内容ABC" in user_content, f"challenge 应含索罗斯(排在前): {user_content[:80]}"
    # 不应含自己（芒格）
    assert "芒格的分析内容QQQ" not in user_content, "challenge 不应含自己"
    print("  PASS: challenge 看到上一轮全部其他 agent（非仅排前面的）")


async def _resume_main() -> int:
    """agent 失败 → start-stream 暂停（agent_failed，无 done）；resume-stream 从失败处继续成功。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(User(username="debate_res", email="r@r.com",
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
            except BaseException:
                try:
                    await session.rollback()
                except BaseException:
                    pass
                raise

    app.dependency_overrides[get_db] = _gdb
    orig_gen = DebateOrchestrator.run_debate_stream
    orig_get = llm_mod.llm_manager.get
    llm_mod.llm_manager.get = lambda: type("L", (), {})()

    failures: list[str] = []

    def check(label, cond):
        print(f"  {'PASS' if cond else 'FAIL'}: {label}")
        if not cond:
            failures.append(label)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            tok = (await c.post("/api/v1/auth/login",
                                json={"username": "debate_res", "password": "pw"})).json()["access_token"]
            h = {"Authorization": f"Bearer {tok}"}

            # 1. start-stream：第1个 agent 失败 → agent_failed + 暂停（无 done）
            DebateOrchestrator.run_debate_stream = _fail_first_agent_stream
            r = await c.post("/api/v1/debate/start-stream", headers=h,
                             json={"agent_ids": [1, 2], "target_type": "stock",
                                   "target_id": "600519", "rounds": 1})
            events = []
            sid = None
            for block in r.text.split("\n\n"):
                lines = block.strip().split("\n")
                if len(lines) < 2:
                    continue
                ev = lines[0].replace("event: ", "")
                if ev == "session":
                    sid = __import__("json").loads(lines[1].replace("data: ", "")).get("session_id")
                events.append(ev)
            check("start: 200", r.status_code == 200)
            check("start: 收到 agent_failed", "agent_failed" in events)
            check("start: 失败后无 done（暂停）", "done" not in events)
            check("start: 暴露 session_id", sid is not None)

            # 失败的 agent 不应落 agent_done 消息
            r = await c.get(f"/api/v1/chat/sessions/{sid}", headers=h)
            msgs = r.json().get("messages", [])
            check("start: 失败 agent 无 done 消息",
                  not any(m["role"] == "assistant" for m in msgs))

            # 2. resume-stream：换成功桩，从失败处继续 → agent_done + summary + done
            DebateOrchestrator.run_debate_stream = _fake_run_debate_stream
            r = await c.post(f"/api/v1/debate/sessions/{sid}/resume-stream", headers=h)
            events2 = []
            has_done = False
            for block in r.text.split("\n\n"):
                lines = block.strip().split("\n")
                if len(lines) < 2:
                    continue
                ev = lines[0].replace("event: ", "")
                events2.append(ev)
                if ev == "done":
                    has_done = True
            check("resume: 200", r.status_code == 200)
            check("resume: 收到 agent_done", "agent_done" in events2)
            check("resume: 收到 summary_done", "summary_done" in events2)
            check("resume: 完成（done）", has_done)

            # resume 后 agent 消息已落库
            r = await c.get(f"/api/v1/chat/sessions/{sid}", headers=h)
            msgs2 = r.json().get("messages", [])
            check("resume: agent 消息落库", any(m["role"] == "assistant" and (m.get("meta") or {}).get("round_type") == "analysis" for m in msgs2))
            check("resume: summary 落库", any(m["role"] == "assistant" and (m.get("meta") or {}).get("round_type") == "summary" for m in msgs2))
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


async def test_debate_resume():
    assert await _resume_main() == 0


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(_main()) == 0 and asyncio.run(_cancel_main()) == 0 and asyncio.run(_resume_main()) == 0 else 1)
