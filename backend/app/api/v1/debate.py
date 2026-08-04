"""Debate API routes."""

import json
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.database import get_db
from app.models.agent import Agent
from app.models.chat import ChatMessage, ChatSession
from app.models.stock import Stock
from app.models.user import User
from app.schemas import DebateStartRequest
from app.services.debate.orchestrator import DebateOrchestrator, DebateRound
from app.services.llm.manager import llm_manager
from app.utils.exceptions import BadRequestException, NotFoundException

router = APIRouter(prefix="/debate", tags=["debate"])

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
    ))
    await db.flush()

    async def event_stream():
        round_num = 0
        try:
            # 首事件：暴露 session_id（前端据此更新 URL / 关联会话）
            yield f"event: session\ndata: {json.dumps({'session_id': session_id}, ensure_ascii=False)}\n\n"
            async for item in orchestrator.run_debate_stream(agents, target_info, req.rounds):
                if isinstance(item, DebateRound):
                    round_num += 1
                    data = {
                        "round_type": item.round_type,
                        "round_label": ROUND_TYPE_LABELS.get(item.round_type, item.round_type),
                        "round_num": round_num,
                        "opinions": [
                            {"agent_id": op.agent_id, "agent_name": op.agent_name, "content": op.content}
                            for op in item.opinions
                        ],
                    }
                    # 落库：每个 opinion 一条 assistant 消息（meta 带 round 结构）
                    for op in item.opinions:
                        db.add(ChatMessage(
                            session_id=session_id, role="assistant", content=op.content,
                            agents_used=[op.agent_name],
                            meta={"round_type": item.round_type, "round_num": round_num,
                                  "agent_id": op.agent_id, "agent_name": op.agent_name},
                        ))
                    await db.flush()
                    yield f"event: round\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                elif isinstance(item, str):
                    # summary 落库
                    db.add(ChatMessage(
                        session_id=session_id, role="assistant", content=item,
                        agents_used=["总结"],
                        meta={"round_type": "summary", "round_num": round_num + 1},
                    ))
                    await db.flush()
                    yield f"event: summary\ndata: {json.dumps({'summary': item}, ensure_ascii=False)}\n\n"
            yield "event: done\ndata: {}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            session.last_message_at = datetime.now()
            await db.commit()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
