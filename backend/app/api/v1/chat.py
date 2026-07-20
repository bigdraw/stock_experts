"""Chat API — 对话式 agent 交互（idea16/29）。

会话持久化 + 流式 SSE + 上下文压缩（LobeChat 架构蓝本）。
保留现有：/chat/agents, /chat/skills, /chat/analyze/*。

端点：
  GET    /chat/sessions              列出会话
  POST   /chat/sessions              创建会话
  GET    /chat/sessions/{id}         取会话 + messages
  PATCH  /chat/sessions/{id}         重命名
  DELETE /chat/sessions/{id}         删除
  POST   /chat/sessions/{id}/stream  流式发消息（SSE）
  POST   /chat                        非流式 fallback（保留）
  GET    /chat/agents                列出 agent
  GET    /chat/skills                列出技能
  POST   /chat/analyze/*            分析工具
"""

import json
import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.database import get_db
from app.models.agent import Agent
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.services.chat_pipeline import (
    ChatPipeline,
    compress_context,
    estimate_tokens,
    should_compress,
)
from app.services.llm.manager import llm_manager
from app.services.llm.provider import LLMMessage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

_pipeline = ChatPipeline()


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


class SessionCreateRequest(BaseModel):
    title: str = "新对话"
    agent_ids: list[int] = []


@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出当前用户的会话。"""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.last_message_at.desc().nullslast(), ChatSession.updated_at.desc())
    )
    sessions = result.scalars().all()
    return [
        {
            "id": s.id,
            "title": s.title,
            "agent_ids": s.agent_ids or [],
            "pinned": s.pinned,
            "last_message_at": str(s.last_message_at) if s.last_message_at else None,
            "updated_at": str(s.updated_at),
        }
        for s in sessions
    ]


@router.post("/sessions")
async def create_session(
    req: SessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新会话。"""
    session = ChatSession(user_id=current_user.id, title=req.title, agent_ids=req.agent_ids)
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return {"id": session.id, "title": session.title, "agent_ids": session.agent_ids, "pinned": session.pinned}


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取会话 + 活跃 messages。"""
    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        return {"error": "会话不存在"}
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id, ChatMessage.is_compressed == False)  # noqa: E712
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()
    return {
        "id": session.id, "title": session.title, "agent_ids": session.agent_ids or [],
        "pinned": session.pinned, "summary": session.summary,
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content,
             "agents_used": m.agents_used or [], "stocks_detected": m.stocks_detected or [],
             "created_at": str(m.created_at)}
            for m in messages
        ],
    }


class SessionPatchRequest(BaseModel):
    title: str | None = None
    pinned: bool | None = None


@router.patch("/sessions/{session_id}")
async def patch_session(
    session_id: int, req: SessionPatchRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """重命名/置顶会话。"""
    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        return {"error": "会话不存在"}
    if req.title is not None:
        session.title = req.title
    if req.pinned is not None:
        session.pinned = req.pinned
    await db.commit()
    return {"id": session.id, "title": session.title, "pinned": session.pinned}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """删除会话。"""
    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        return {"error": "会话不存在"}
    await db.delete(session)
    await db.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Streaming chat (SSE)
# ---------------------------------------------------------------------------


class StreamRequest(BaseModel):
    message: str
    agent_ids: list[int] = []


@router.post("/sessions/{session_id}/stream")
async def chat_stream(
    session_id: int, req: StreamRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """流式发消息（SSE）。

    SSE 格式：event: text\\ndata: {"content":"增量"}\\n\\n / event: stop / event: error
    """
    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        return {"error": "会话不存在"}

    # 1. 保存 user 消息
    stock_codes = re.findall(r"\b(\d{6})\b", req.message)
    user_msg = ChatMessage(
        session_id=session_id, role="user", content=req.message,
        stocks_detected=stock_codes[:3], token_count=estimate_tokens(req.message),
    )
    db.add(user_msg)
    await db.flush()

    # 2. 加载活跃历史
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id, ChatMessage.is_compressed == False)  # noqa: E712
        .order_by(ChatMessage.created_at.asc())
    )
    db_messages = result.scalars().all()
    messages = [{"role": m.role, "content": m.content} for m in db_messages]

    # 3. 压缩
    if should_compress(messages):
        summary = await compress_context(messages, session, db, llm_manager)
        if summary:
            old_msgs = db_messages[:-8]
            for m in old_msgs:
                m.is_compressed = True
            session.summary = summary
            session.summary_upto_msg_id = old_msgs[-1].id if old_msgs else None
            await db.flush()
            messages = [{"role": m.role, "content": m.content} for m in db_messages if not m.is_compressed]

    # 4. 组装 pipeline context
    agent_ids = req.agent_ids or session.agent_ids or []
    agents, default_agent = [], None
    if agent_ids:
        agent_result = await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))
        agents = list(agent_result.scalars().all())
    else:
        default_result = await db.execute(
            select(Agent).where(Agent.type == "master", Agent.name == "现代价值分析")
        )
        default_agent = default_result.scalar_one_or_none()

    ctx = {"message": req.message, "agents": agents, "default_agent": default_agent,
           "session_summary": session.summary, "db": db}

    # 5. 执行管线
    messages = await _pipeline.run(messages, ctx)

    # 6. 流式 SSE
    async def event_stream():
        full_response = ""
        try:
            llm = llm_manager.get()
            async for chunk in llm.chat_stream([LLMMessage(role=m["role"], content=m["content"]) for m in messages]):
                if chunk.content:
                    full_response += chunk.content
                    yield f"event: text\ndata: {json.dumps({'content': chunk.content}, ensure_ascii=False)}\n\n"
            yield f"event: stop\ndata: {json.dumps({'reason': 'stop'})}\n\n"
        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
            full_response = f"[错误] {e}"
        finally:
            if full_response:
                assistant_msg = ChatMessage(
                    session_id=session_id, role="assistant", content=full_response,
                    agents_used=[a.name for a in agents] or (["现代价值分析(默认)"] if default_agent else []),
                    stocks_detected=stock_codes[:3], token_count=estimate_tokens(full_response),
                )
                db.add(assistant_msg)
                session.last_message_at = datetime.now()
                if session.title == "新对话":
                    session.title = req.message[:20] + ("…" if len(req.message) > 20 else "")
                await db.commit()

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                                      "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------
# Non-streaming fallback + agents/skills/analyze (保留)
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    agent_ids: list[int] = []


@router.post("")
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """非流式 fallback。"""
    agents, default_agent = [], None
    if req.agent_ids:
        result = await db.execute(select(Agent).where(Agent.id.in_(req.agent_ids)))
        agents = list(result.scalars().all())
    else:
        default_result = await db.execute(select(Agent).where(Agent.type == "master", Agent.name == "现代价值分析"))
        default_agent = default_result.scalar_one_or_none()

    stock_codes = re.findall(r"\b(\d{6})\b", req.message)
    context_data = ""
    for code in stock_codes[:3]:
        try:
            from app.services.data.cache import ensure_financial_reports
            from app.services.data.value_analysis import analyze
            await ensure_financial_reports(db, code)
            await db.commit()
            va = await analyze(db, code)
            if "error" not in va:
                context_data += f"\n--- {code} ---\n" + json.dumps(va.get("latest", {}), ensure_ascii=False, default=str)[:800]
        except Exception:
            pass

    user_content = f"{req.message}\n\n<stock_data>\n{context_data}\n</stock_data>" if context_data else req.message
    system_parts = ["你是一个投资分析助手。基于以下投资理念回答用户问题。"]
    for a in agents:
        system_parts.append(f"\n--- Agent: {a.name} ---\n{a.system_prompt}")
    if not agents and default_agent:
        system_parts.append(f"\n--- {default_agent.name} ---\n{default_agent.system_prompt}")

    try:
        llm = llm_manager.get()
        response = await llm.chat([
            LLMMessage(role="system", content="\n".join(system_parts)),
            LLMMessage(role="user", content=user_content),
        ])
        return {"response": response.content,
                "agents_used": [a.name for a in agents] or (["现代价值分析(默认)"] if default_agent else []),
                "stocks_detected": stock_codes[:3]}
    except Exception as e:
        return {"error": f"LLM 调用失败: {e}", "response": "LLM 未配置。"}


@router.get("/agents")
async def list_chat_agents(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Agent).order_by(Agent.id))
    return [{"id": a.id, "name": a.name, "type": a.type, "description": a.description} for a in result.scalars().all()]


@router.get("/skills")
async def list_chat_skills(current_user: User = Depends(get_current_user)):
    from app.api.agent import TOOLS
    return [{"name": t["name"], "desc": t["desc"], "path": t["path"]} for t in TOOLS]


class StockAnalysisRequest(BaseModel):
    code: str


@router.post("/analyze/stock")
async def analyze_stock(req: StockAnalysisRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.models.stock import Stock
    from app.services.data.cache import ensure_financial_reports
    from app.services.data.value_analysis import analyze
    stock = await db.get(Stock, req.code)
    if not stock:
        return {"found": False, "message": f"股票 {req.code} 不存在"}
    await ensure_financial_reports(db, req.code)
    await db.commit()
    va = await analyze(db, req.code)
    return {"found": True, "stock": {"code": stock.code, "name": stock.name, "market": stock.market}, "value_analysis": va}


class PortfolioAnalysisRequest(BaseModel):
    portfolio_id: int


@router.post("/analyze/portfolio")
async def analyze_portfolio(req: PortfolioAnalysisRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.models.portfolio import Portfolio, PortfolioItem
    from app.services.risk.service import compute_dashboard, generate_alerts
    portfolio = await db.get(Portfolio, req.portfolio_id)
    if not portfolio:
        return {"found": False, "message": f"组合 {req.portfolio_id} 不存在"}
    items_result = await db.execute(select(PortfolioItem).where(PortfolioItem.portfolio_id == req.portfolio_id))
    items = items_result.scalars().all()
    from app.models.stock import FinancialReport
    positions = []
    for item in items:
        fin_result = await db.execute(select(FinancialReport).where(FinancialReport.stock_code == item.stock_code, FinancialReport.report_type == "Latest").order_by(FinancialReport.report_date.desc()).limit(1))
        fin = fin_result.scalar_one_or_none()
        positions.append({"symbol": item.stock_code, "shares": float(item.shares or 0), "cost_basis": float(item.avg_cost or 0), "current_price": float(fin.price) if fin and fin.price else 0, "sector": "Unknown"})
    dashboard = compute_dashboard(positions)
    alerts = [a.__dict__ for a in generate_alerts(positions)]
    return {"found": True, "portfolio": {"id": portfolio.id, "name": portfolio.name}, "positions": positions, "risk_dashboard": dashboard, "risk_alerts": alerts}


class FundAnalysisRequest(BaseModel):
    code: str


@router.post("/analyze/fund")
async def analyze_fund(req: FundAnalysisRequest, current_user: User = Depends(get_current_user)):
    import akshare as ak

    from app.services.data.akshare_provider import _bypass_proxy, _restore_proxy
    code = req.code.strip()
    result = {"found": False, "code": code}
    if code.startswith(("5", "1")) and len(code) == 6:
        op = _bypass_proxy()
        try:
            df = ak.fund_etf_hist_em(symbol=code, period="daily", adjust="qfq")
            if len(df) > 0:
                latest = df.iloc[-1]
                result = {"found": True, "code": code, "type": "ETF", "latest_date": str(latest["日期"]), "close": float(latest["收盘"]), "volume": float(latest["成交量"]), "rows": len(df)}
        except Exception as e:
            result["message"] = f"ETF 查询失败: {str(e)[:60]}"
        finally:
            _restore_proxy(op)
    if not result.get("found") and len(code) == 6:
        op = _bypass_proxy()
        try:
            df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
            if len(df) > 0:
                latest = df.iloc[-1]
                result = {"found": True, "code": code, "type": "开放式基金", "latest_date": str(latest["净值日期"]), "nav": float(latest["单位净值"]), "rows": len(df)}
        except Exception as e:
            result["message"] = f"基金查询失败: {str(e)[:60]}"
        finally:
            _restore_proxy(op)
    if not result.get("found") and "message" not in result:
        result["message"] = "未找到该基金"
    return result
