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

    # 写入缓存
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
    orchestrator = DebateOrchestrator(llm, db=db)

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
            logger.info(f"Debate stream cancelled by client (session {session_id})")
            try:
                await db.rollback()
            except Exception:
                pass
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
        if t == "factbook_start":
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
        elif t == "factbook":  # 兼容旧的单事件 factbook
            db.add(ChatMessage(
                session_id=session_id, role="system", content=ev["content"],
                meta={"round_type": "factbook"},
            ))
            await db.commit()
            yield f"event: factbook_done\ndata: {json.dumps({'content': ev['content']}, ensure_ascii=False)}\n\n"
        elif t == "agent_start":
            yield f"event: agent_start\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        elif t == "agent_token":
            yield f"event: agent_token\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        elif t == "agent_done":
            round_num = ev["round_num"]
            db.add(ChatMessage(
                session_id=session_id, role="assistant", content=ev["content"],
                agents_used=[ev["agent_name"]],
                meta={"round_type": ev["round_type"], "round_num": ev["round_num"],
                      "agent_id": ev["agent_id"], "agent_name": ev["agent_name"]},
            ))
            await db.commit()
            yield f"event: agent_done\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        elif t == "agent_failed":
            # 失败：发事件后暂停，不发 done——前端显示原地重试按钮
            yield f"event: agent_failed\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            return
        elif t == "summary_start":
            yield "event: summary_start\ndata: {}\n\n"
        elif t == "summary_token":
            yield f"event: summary_token\ndata: {json.dumps({'delta': ev['delta']}, ensure_ascii=False)}\n\n"
        elif t == "summary_done":
            db.add(ChatMessage(
                session_id=session_id, role="assistant", content=ev["content"],
                agents_used=["总结"],
                meta={"round_type": "summary", "round_num": round_num + 1},
            ))
            session.last_message_at = datetime.now()
            await db.commit()
            yield f"event: summary_done\ndata: {json.dumps({'content': ev['content']}, ensure_ascii=False)}\n\n"
        elif t == "summary_failed":
            yield f"event: summary_failed\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            return
    yield "event: done\ndata: {}\n\n"


@router.post("/sessions/{session_id}/resume-stream")
async def resume_debate_stream(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """原地重试：从失败的 agent 处继续辩论。重建 history/completed/context，调 orchestrator resume。"""
    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id or (session.type or "chat") != "debate":
        return {"error": "辩论会话不存在"}

    # 从 messages 重建 resume 态 + 辩论参数
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

    # 重建 agents + target_info
    agent_rows = (await db.execute(select(Agent).where(Agent.id.in_(session.agent_ids or [])))).scalars().all()
    agents = [{"id": a.id, "name": a.name, "system_prompt": a.system_prompt, "description": a.description or ""} for a in agent_rows]
    target_info = {
        "type": "stock", "code": target_code or "", "name": target_name or target_code or "",
        "data": {"code": target_code or "", "name": target_name or "", "market": ""},
    }

    llm = llm_manager.get()
    orchestrator = DebateOrchestrator(llm, db=db)
    resume = {"history": history, "completed": completed, "context": context, "summary_done": summary_done}

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
