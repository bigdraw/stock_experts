"""Debate API routes."""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.database import get_db
from app.models.agent import Agent
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

    Yields one event per round + summary + done:
      event: round\\ndata: {"round_type":"analysis","opinions":[...]}\n\n
      event: summary\\ndata: {"summary":"..."}\n\n
      event: done\\ndata: {}\n\n
    """
    agents, target_info = await _prepare_debate(req, db, current_user)
    llm = llm_manager.get()
    orchestrator = DebateOrchestrator(llm, db=db)

    async def event_stream():
        try:
            async for item in orchestrator.run_debate_stream(agents, target_info, req.rounds):
                if isinstance(item, DebateRound):
                    data = {
                        "round_type": item.round_type,
                        "round_label": ROUND_TYPE_LABELS.get(item.round_type, item.round_type),
                        "opinions": [{"agent_name": op.agent_name, "content": op.content} for op in item.opinions],
                    }
                    yield f"event: round\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                elif isinstance(item, str):
                    yield f"event: summary\ndata: {json.dumps({'summary': item}, ensure_ascii=False)}\n\n"
            yield "event: done\ndata: {}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
