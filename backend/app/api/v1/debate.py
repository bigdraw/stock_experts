"""Debate API routes."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.database import get_db
from app.models.agent import Agent
from app.models.chat import ChatMessage, ChatSession
from app.models.stock import Stock
from app.models.user import User
from app.schemas import DebateStartRequest
from app.services.debate.orchestrator import AgentOpinion, DebateOrchestrator, DebateRound
from app.services.llm.manager import llm_manager
from app.utils.exceptions import BadRequestException, NotFoundException

router = APIRouter(prefix="/debate", tags=["debate"])
logger = logging.getLogger(__name__)

ROUND_TYPE_LABELS = {"analysis": "独立分析", "challenge": "质疑", "response": "回应"}

# Sessions whose background continuation is running after a client disconnect
# (ISSUE-022). A resume-stream request for one of these must refuse rather than
# race the background task (which would double-execute the failed agent and
# write duplicate ChatMessages / hit SQLite "database is locked").
_running_debates: set[int] = set()
# Strong references to background debate tasks so the event loop doesn't GC them
# mid-execution (ISSUE-022 / asyncio.create_task footgun).
_background_tasks: set[asyncio.Task] = set()


async def _prepare_debate(req: DebateStartRequest, db: AsyncSession, current_user: User):
    """Shared: validate + load agents + target info."""
    if len(req.agent_ids) < 2:
        raise BadRequestException("At least 2 agents required for a debate")

    agents = []
    for agent_id in req.agent_ids:
        agent = await db.get(Agent, agent_id)
        if not agent:
            raise NotFoundException(f"Agent {agent_id} not found")
        agents.append({
            "id": agent.id, "name": agent.name,
            "system_prompt": agent.system_prompt, "description": agent.description or "",
        })

    target_info = {"type": req.target_type, "code": req.target_id, "name": req.target_id, "data": {}}
    if req.target_type == "stock":
        stock = await db.get(Stock, req.target_id)
        if stock:
            target_info["name"] = stock.name
            target_info["data"] = {"code": stock.code, "name": stock.name, "market": stock.market}

    return agents, target_info


@router.post("/start")
async def start_debate(
    req: DebateStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a multi-agent debate (blocking, returns full result).

    带缓存复用：同一 stock + 同一 agent 组合，7 天内的结果直接返回缓存。
    """
    agents, target_info = await _prepare_debate(req, db, current_user)

    # 缓存检查
    from app.services.analysis_cache import get_cached_analysis, set_cached_analysis
    cached = await get_cached_analysis(db, target_info["code"], list(req.agent_ids), "debate")
    if cached:
        return cached

    llm = llm_manager.get()
    orchestrator = DebateOrchestrator(llm, db=db)
    result = await orchestrator.run_debate(agents, target_info, max_rounds=req.rounds)
    response = {
        "rounds": [
            {
                "round_type": r.round_type,
                "opinions": [{"agent_name": op.agent_name, "content": op.content} for op in r.opinions],
            }
            for r in result.rounds
        ],
        "summary": result.summary,
    }

    # Only cache a completed, non-empty result (ISSUE-022): run_debate now
    # raises on failure, but defend in depth — caching an empty/failed result
    # for 7 days would poison every subsequent /debate/start for this stock.
    if result.rounds:
        await set_cached_analysis(db, target_info["code"], list(req.agent_ids), response, "debate")
    await db.commit()
    return response


@router.post("/start-stream")
async def start_debate_stream(
    req: DebateStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a multi-agent debate with SSE streaming.

    辩论对应 chat 页面一个会话标签（type='debate'）：开辩即建 ChatSession，
    每个 opinion / summary 落为 ChatMessage（meta 带 round_type/round_num/agent），
    支持刷新/重进回看。

    Yields:
      event: session  data: {"session_id": id}     # 新会话 id（首事件）
      event: round     data: {"round_type","round_label","opinions":[...]}
      event: summary   data: {"summary":"..."}
      event: done      data: {}
      event: error     data: {"message":"..."}
    """
    agents, target_info = await _prepare_debate(req, db, current_user)
    llm = llm_manager.get()
    orchestrator = DebateOrchestrator(llm, db=db, validate_data=req.validate_data)

    # 建 debate 会话 + 存 user 消息（产物落库，支持回看）
    name = target_info.get("name", target_info.get("code", ""))
    code = target_info.get("code", "")
    agent_ids = [a["id"] for a in agents]
    agent_names = [a["name"] for a in agents]
    session = ChatSession(
        user_id=current_user.id,
        title=f"辩论：{name}({code})" if code else f"辩论：{name}",
        agent_ids=agent_ids,
        type="debate",
    )
    db.add(session)
    await db.flush()
    session_id = session.id
    user_prompt = f"辩论标的：{name}({code})，{req.rounds} 轮，参与：{', '.join(agent_names)}"
    db.add(ChatMessage(
        session_id=session_id, role="user", content=user_prompt,
        stocks_detected=[code] if code else [],
        # 存 target/rounds 到 meta，供 resume-stream 重建辩论参数（原地重试时复用）
        meta={"target_code": code, "target_name": name, "rounds": req.rounds,
              "agent_ids": agent_ids},
    ))
    # 会话 + user 消息立即落盘——辩论流很长，客户端中途断连也要保留会话壳
    await db.commit()

    async def event_stream():
        try:
            # 首事件：暴露 session_id（前端据此更新 URL / 关联会话）
            yield f"event: session\ndata: {json.dumps({'session_id': session_id}, ensure_ascii=False)}\n\n"
            async for sse in _translate_debate_events(
                orchestrator.run_debate_stream(agents, target_info, req.rounds),
                session_id, session, db,
            ):
                yield sse
        except asyncio.CancelledError:
            # 用户切页面（非点停止）→ SSE 连接断 → 不 rollback+stop，而是 commit+后台续跑
            logger.info(f"Debate stream: client disconnect (session {session_id}); committing + background continuation")
            try:
                await db.commit()  # 保留已完成的 agent_done/factbook（不 rollback）
            except Exception:
                pass
            # 后台续跑：用 resume 机制从已落库 messages 重建 → 继续到完成/暂停。
            # Claim the session so a concurrent resume-stream can't race the
            # background task (double-write / SQLite lock) — ISSUE-022.
            if session_id not in _running_debates:
                _running_debates.add(session_id)
                task = asyncio.create_task(
                    _finish_debate_background(session_id, agents, target_info, req.rounds)
                )
                # Hold a strong reference so the loop doesn't GC the task
                # mid-execution (ISSUE-022 / asyncio.create_task footgun).
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)
            # NOTE: CancelledError is intentionally NOT re-raised here. The
            # documented behaviour is "commit + background continuation": the
            # live SSE response ends cleanly (200) with already-committed
            # opinions persisted, and the background task finishes the debate.
            # Re-raising would cancel the response task and break that contract
            # (see test_debate_cancel). See ISSUE-022 note in ISSUES.md.
        except Exception as e:
            logger.exception(f"Debate stream error (session {session_id})")
            try:
                await db.rollback()
            except Exception:
                pass
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


async def _translate_debate_events(ev_gen, session_id: int, session, db) -> AsyncIterator[str]:
    """把 orchestrator 的事件流转成 SSE + 持久化。agent_failed/summary_failed 时暂停
    （return，不发 done）——前端据此显示原地重试按钮。"""
    round_num = 0
    async for ev in ev_gen:
        t = ev.get("type")
        if t == "collecting":
            # FactBook 采集进度（正在获取价值分析/K线/行业/宏观/市场状态…）
            yield f"event: collecting\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        elif t == "factbook_start":
            yield "event: factbook_start\ndata: {}\n\n"
        elif t == "factbook_token":
            yield f"event: factbook_token\ndata: {json.dumps({'delta': ev['delta']}, ensure_ascii=False)}\n\n"
        elif t == "factbook_done":
            # 事实 agent 消化完成的 digest 落 system 消息（回看可见）
            db.add(ChatMessage(
                session_id=session_id, role="system", content=ev["content"],
                meta={"round_type": "factbook"},
            ))
            await db.commit()
            yield f"event: factbook_done\ndata: {json.dumps({'content': ev['content']}, ensure_ascii=False)}\n\n"
        elif t == "validation_start":
            yield "event: validation_start\ndata: {}\n\n"
        elif t == "validation_reasoning":
            yield f"event: validation_reasoning\ndata: {json.dumps({'delta': ev['delta']}, ensure_ascii=False)}\n\n"
        elif t == "validation_token":
            yield f"event: validation_token\ndata: {json.dumps({'delta': ev['delta']}, ensure_ascii=False)}\n\n"
        elif t == "validation_done":
            _vmeta: dict = {"round_type": "validation"}
            if ev.get("reasoning"):
                _vmeta["reasoning"] = ev["reasoning"]
            db.add(ChatMessage(
                session_id=session_id, role="system", content=ev["content"],
                meta=_vmeta,
            ))
            await db.commit()
            yield f"event: validation_done\ndata: {json.dumps({'content': ev['content'], 'reasoning': ev.get('reasoning', '')}, ensure_ascii=False)}\n\n"
        elif t == "factbook":  # 兼容旧的单事件 factbook
            db.add(ChatMessage(
                session_id=session_id, role="system", content=ev["content"],
                meta={"round_type": "factbook"},
            ))
            await db.commit()
            yield f"event: factbook_done\ndata: {json.dumps({'content': ev['content']}, ensure_ascii=False)}\n\n"
        elif t == "agent_start":
            yield f"event: agent_start\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        elif t == "agent_reasoning":
            # 思考链增量（不单独落库，agent_done 时随 meta.reasoning 持久化）
            yield f"event: agent_reasoning\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        elif t == "agent_token":
            yield f"event: agent_token\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        elif t == "agent_done":
            round_num = ev["round_num"]
            meta = {"round_type": ev["round_type"], "round_num": ev["round_num"],
                    "agent_id": ev["agent_id"], "agent_name": ev["agent_name"]}
            if ev.get("reasoning"):
                meta["reasoning"] = ev["reasoning"]  # 思考链随消息持久化（回看可见）
            db.add(ChatMessage(
                session_id=session_id, role="assistant", content=ev["content"],
                agents_used=[ev["agent_name"]], meta=meta,
            ))
            await db.commit()
            yield f"event: agent_done\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        elif t == "agent_failed":
            # 失败：发事件后暂停，不发 done——前端显示原地重试按钮
            yield f"event: agent_failed\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            return
        elif t == "summary_start":
            yield "event: summary_start\ndata: {}\n\n"
        elif t == "summary_reasoning":
            yield f"event: summary_reasoning\ndata: {json.dumps({'delta': ev['delta']}, ensure_ascii=False)}\n\n"
        elif t == "summary_token":
            yield f"event: summary_token\ndata: {json.dumps({'delta': ev['delta']}, ensure_ascii=False)}\n\n"
        elif t == "summary_done":
            meta: dict = {"round_type": "summary", "round_num": round_num + 1}
            if ev.get("reasoning"):
                meta["reasoning"] = ev["reasoning"]
            db.add(ChatMessage(
                session_id=session_id, role="assistant", content=ev["content"],
                agents_used=["总结"], meta=meta,
            ))
            session.last_message_at = datetime.now()
            await db.commit()
            yield f"event: summary_done\ndata: {json.dumps({'content': ev['content']}, ensure_ascii=False)}\n\n"
        elif t == "summary_failed":
            yield f"event: summary_failed\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            return
    yield "event: done\ndata: {}\n\n"


async def _rebuild_resume(session_id: int, agents: list[dict], db: AsyncSession) -> dict | None:
    """从已落库 messages 重建辩论 resume 态（共享：resume-stream 端点 + 后台续跑共用）。

    返回 {resume, target_info, rounds, session} 或 None（会话不存在）。
    """
    session = await db.get(ChatSession, session_id)
    if not session or (session.type or "chat") != "debate":
        return None

    msgs = (await db.execute(
        select(ChatMessage).where(
            ChatMessage.session_id == session_id, ChatMessage.is_compressed == False  # noqa: E712
        ).order_by(ChatMessage.created_at.asc())
    )).scalars().all()

    rounds_map: dict[int, dict] = {}
    completed: set[tuple[int, int]] = set()
    context = ""
    summary_done = False
    target_code = target_name = None
    rounds = 3
    for m in msgs:
        meta = m.meta or {}
        if m.role == "user":
            target_code = meta.get("target_code")
            target_name = meta.get("target_name")
            rounds = meta.get("rounds", 3)
        elif m.role == "system" and meta.get("round_type") == "factbook":
            context = m.content
        elif m.role == "assistant":
            if meta.get("round_type") == "summary":
                summary_done = True
            elif meta.get("round_num") and meta.get("agent_id") is not None:
                rn = meta["round_num"]
                r = rounds_map.setdefault(rn, {"round_type": meta.get("round_type", "analysis"), "opinions": []})
                r["opinions"].append(AgentOpinion(meta["agent_id"], meta.get("agent_name", "agent"), m.content))
                completed.add((rn, meta["agent_id"]))

    history = [
        DebateRound(round_type=rounds_map[k]["round_type"], opinions=rounds_map[k]["opinions"])
        for k in sorted(rounds_map)
    ]
    target_info = {
        "type": "stock", "code": target_code or "", "name": target_name or target_code or "",
        "data": {"code": target_code or "", "name": target_name or "", "market": ""},
    }
    resume = {"history": history, "completed": completed, "context": context, "summary_done": summary_done}
    return {"resume": resume, "target_info": target_info, "rounds": rounds, "session": session}


async def _finish_debate_background(session_id: int, agents: list[dict], target_info: dict, max_rounds: int):
    """后台续跑辩论（客户端断连后）：用独立 db + resume 机制续跑到完成/agent_failed→暂停。

    无 SSE——只 persist（agent_done/summary_done 落库）。用户回来 selectSession 看到结果。
    """
    from app.database import async_session_factory

    logger.info(f"Background debate {session_id}: starting (client disconnected)")
    try:
        async with async_session_factory() as db:
            rebuilt = await _rebuild_resume(session_id, agents, db)
            if not rebuilt:
                logger.warning(f"Background debate {session_id}: no resume state")
                return
            session = rebuilt["session"]
            resume = rebuilt["resume"]
            target = rebuilt["target_info"]
            rounds = rebuilt["rounds"]

            llm = llm_manager.get()
            orchestrator = DebateOrchestrator(llm, db=db)

            async for ev in orchestrator.run_debate_stream(agents, target, rounds, resume=resume):
                t = ev.get("type")
                if t == "collecting":
                    continue  # 进度事件不持久化
                elif t == "factbook_done":
                    # 已在 live stream 落库（resume 时 context 从 DB 读），跳过
                    continue
                elif t == "agent_done":
                    meta = {"round_type": ev["round_type"], "round_num": ev["round_num"],
                            "agent_id": ev["agent_id"], "agent_name": ev["agent_name"]}
                    if ev.get("reasoning"):
                        meta["reasoning"] = ev["reasoning"]
                    db.add(ChatMessage(
                        session_id=session_id, role="assistant", content=ev["content"],
                        agents_used=[ev["agent_name"]], meta=meta,
                    ))
                    await db.commit()
                elif t == "summary_done":
                    # ISSUE-030: background resume may reach summary with no
                    # agent_done in THIS run (all already persisted by the live
                    # stream), so round_num=0 would mislabel summary as round 1.
                    # The summary is the final round = max_rounds.
                    meta = {"round_type": "summary", "round_num": rounds}
                    if ev.get("reasoning"):
                        meta["reasoning"] = ev["reasoning"]
                    db.add(ChatMessage(
                        session_id=session_id, role="assistant", content=ev["content"],
                        agents_used=["总结"], meta=meta,
                    ))
                    session.last_message_at = datetime.now()
                    await db.commit()
                elif t in ("agent_failed", "summary_failed"):
                    logger.info(f"Background debate {session_id}: paused at {t} (user can retry)")
                    break
            logger.info(f"Background debate {session_id}: completed")
    except Exception as e:
        logger.exception(f"Background debate {session_id} error: {e}")
    finally:
        # Release the claim so a later resume-stream can proceed (ISSUE-022).
        _running_debates.discard(session_id)


@router.post("/sessions/{session_id}/resume-stream")
async def resume_debate_stream(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """原地重试：从失败的 agent 处继续辩论。用共享 _rebuild_resume 重建状态。"""
    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id or (session.type or "chat") != "debate":
        return {"error": "辩论会话不存在"}

    # Refuse while the background continuation is still running (ISSUE-022):
    # racing it would re-execute the failed agent and write duplicate messages.
    if session_id in _running_debates:
        return {"error": "该辩论正在后台续跑，请稍后刷新查看结果"}

    # 重建 agents（从 session.agent_ids）
    agent_rows = (await db.execute(select(Agent).where(Agent.id.in_(session.agent_ids or [])))).scalars().all()
    agents = [{"id": a.id, "name": a.name, "system_prompt": a.system_prompt, "description": a.description or ""} for a in agent_rows]

    rebuilt = await _rebuild_resume(session_id, agents, db)
    if not rebuilt:
        return {"error": "辩论会话状态重建失败"}
    session = rebuilt["session"]
    resume = rebuilt["resume"]
    target_info = rebuilt["target_info"]
    rounds = rebuilt["rounds"]

    llm = llm_manager.get()
    orchestrator = DebateOrchestrator(llm, db=db)

    async def event_stream():
        try:
            yield f"event: session\ndata: {json.dumps({'session_id': session_id}, ensure_ascii=False)}\n\n"
            async for sse in _translate_debate_events(
                orchestrator.run_debate_stream(agents, target_info, rounds, resume=resume),
                session_id, session, db,
            ):
                yield sse
        except asyncio.CancelledError:
            try:
                await db.rollback()
            except Exception:
                pass
        except Exception as e:
            logger.exception("Debate resume stream error")
            try:
                await db.rollback()
            except Exception:
                pass
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
