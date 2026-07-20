"""Chat API — 对话式 agent 交互（idea16）。

POST /chat {message, agent_ids} → 组合选中 agent 的 system_prompt + 用户消息
→ 如果消息含股票代码则自动取价值分析数据注入上下文 → 调 LLM → 返回回复。
GET /chat/agents → 列出可选 agent（供 @ 提及）。
GET /chat/skills → 列出可用技能（供 / 唤起，代理 /agent/tools）。
"""

import json
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.database import get_db
from app.models.agent import Agent
from app.models.user import User
from app.services.llm.manager import llm_manager
from app.services.llm.provider import LLMMessage

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    agent_ids: list[int] = []  # @提及的 agent ID 列表


@router.post("")
async def chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """对话：组合 agent 理念 + 用户消息（含自动取数）→ LLM 回复。"""
    # 1. 取选中 agent 的 system_prompt
    system_parts = ["你是一个投资分析助手。基于以下投资理念回答用户问题。"]
    if req.agent_ids:
        result = await db.execute(
            select(Agent).where(Agent.id.in_(req.agent_ids))
        )
        agents = result.scalars().all()
        for a in agents:
            system_parts.append(f"\n--- Agent: {a.name} ---\n{a.system_prompt}")
    else:
        # 无指定 agent → 用现代价值分析作为默认
        result = await db.execute(
            select(Agent).where(Agent.type == "master", Agent.name == "现代价值分析")
        )
        default = result.scalar_one_or_none()
        if default:
            system_parts.append(f"\n--- {default.name} ---\n{default.system_prompt}")

    # 2. 如果消息含 6 位股票代码 → 自动取价值分析数据注入
    stock_codes = re.findall(r"\b(\d{6})\b", req.message)
    context_data = ""
    for code in stock_codes[:3]:  # 最多 3 只
        try:
            from app.services.data.cache import ensure_financial_reports
            from app.services.data.value_analysis import analyze

            await ensure_financial_reports(db, code)
            await db.commit()
            va = await analyze(db, code)
            if "error" not in va:
                context_data += f"\n--- {code} 价值分析数据 ---\n"
                context_data += json.dumps(va.get("latest", {}), ensure_ascii=False, default=str)[:800]
                context_data += f"\n估值: {json.dumps(va.get('valuation', {}), ensure_ascii=False, default=str)}"
                context_data += f"\n成长: {json.dumps(va.get('growth', {}), ensure_ascii=False, default=str)}"
        except Exception:
            pass  # 静默失败，不阻塞对话

    user_content = req.message
    if context_data:
        user_content = f"{req.message}\n\n[平台已自动获取以下股票数据供你分析参考：{context_data}]"

    # 3. 调 LLM
    try:
        llm = llm_manager.get()
        response = await llm.chat([
            LLMMessage(role="system", content="\n".join(system_parts)),
            LLMMessage(role="user", content=user_content),
        ])
        return {
            "response": response.content,
            "agents_used": [a.name for a in (await db.execute(
                select(Agent).where(Agent.id.in_(req.agent_ids))
            )).scalars().all()] if req.agent_ids else ["现代价值分析(默认)"],
            "stocks_detected": stock_codes[:3],
        }
    except Exception as e:
        return {"error": f"LLM 调用失败: {e}", "response": "LLM 未配置或调用失败，请先在设置页配置 API Key。"}


@router.get("/agents")
async def list_chat_agents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出可选 agent（供 @ 提及）。"""
    result = await db.execute(select(Agent).order_by(Agent.id))
    return [
        {"id": a.id, "name": a.name, "type": a.type, "description": a.description}
        for a in result.scalars().all()
    ]


@router.get("/skills")
async def list_chat_skills(
    current_user: User = Depends(get_current_user),
):
    """列出可用技能（供 / 唤起，代理 /agent/tools）。"""
    from app.api.agent import TOOLS
    return [{"name": t["name"], "desc": t["desc"], "path": t["path"]} for t in TOOLS]
