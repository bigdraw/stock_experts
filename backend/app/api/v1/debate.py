"""Debate API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.database import get_db
from app.models.agent import Agent
from app.models.stock import Stock
from app.models.user import User
from app.schemas import DebateStartRequest
from app.services.debate.orchestrator import DebateOrchestrator
from app.services.llm.manager import llm_manager
from app.utils.exceptions import BadRequestException, NotFoundException

router = APIRouter(prefix="/debate", tags=["debate"])


@router.post("/start")
async def start_debate(
    req: DebateStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a multi-agent debate."""
    if len(req.agent_ids) < 2:
        raise BadRequestException("At least 2 agents required for a debate")

    # Load agents
    agents = []
    for agent_id in req.agent_ids:
        agent = await db.get(Agent, agent_id)
        if not agent:
            raise NotFoundException(f"Agent {agent_id} not found")
        agents.append(
            {
                "id": agent.id,
                "name": agent.name,
                "system_prompt": agent.system_prompt,
                "description": agent.description or "",
            }
        )

    # Load target data
    target_info = {
        "type": req.target_type,
        "code": req.target_id,
        "name": req.target_id,
        "data": {},
    }
    if req.target_type == "stock":
        stock = await db.get(Stock, req.target_id)
        if stock:
            target_info["name"] = stock.name
            target_info["data"] = {"code": stock.code, "name": stock.name, "market": stock.market}

    # Run debate
    llm = llm_manager.get()
    orchestrator = DebateOrchestrator(llm)
    result = await orchestrator.run_debate(agents, target_info, max_rounds=req.rounds)

    return {
        "rounds": [
            {
                "round_type": r.round_type,
                "opinions": [
                    {"agent_name": op.agent_name, "content": op.content} for op in r.opinions
                ],
            }
            for r in result.rounds
        ],
        "summary": result.summary,
    }
