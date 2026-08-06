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
from app.services.debate.factbook import FACT_AGENT_SYSTEM, FactBook
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
            "type": s.type or "chat",
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
        "type": session.type or "chat", "pinned": session.pinned, "summary": session.summary,
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content,
             "agents_used": m.agents_used or [], "stocks_detected": m.stocks_detected or [],
             "meta": m.meta, "created_at": str(m.created_at)}
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
    """删除会话——同时删其所有消息，避免孤儿消息被复用 id 的新会话"复活"。

    依赖 FK CASCADE（database.py 已开 PRAGMA foreign_keys=ON），但显式删消息作双保险
    （兼容旧连接/未开 FK 的环境）。
    """
    from sqlalchemy import delete as sa_delete

    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        return {"error": "会话不存在"}
    await db.execute(sa_delete(ChatMessage).where(ChatMessage.session_id == session_id))
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
    # 立即 commit（不只 flush）——客户端中途切走/abort 时 get_db 会 rollback，
    # 若只 flush 则 user 消息被回滚，回来重载就消失了。
    await db.commit()

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

    # 6. 流式 SSE：多 agent（@mention ≥2）→ 一次 tavily 检索 + 每 agent 流式分析；
    #    单 agent → function-calling ReAct（模型可调 tavily_search 真工具）
    from app.services.llm.provider import LLMMessage
    from app.services.llm.tools import DEBATE_TOOLS, execute_tool

    async def event_stream():
        try:
            llm = llm_manager.get()

            # 平台 FactBook 数据采集（gated on detected stock code）：单/多 agent 共用。
            # collect_streaming → FactBook.format 摘要 → 发 factbook SSE + 持久化 system 消息。
            # 比 tavily 更准（K线/行业/宏观/regime/全 trend+分红，平台自有）。失败非致命（摘要空，tavily 兜底）。
            fb_digest_holder = {"digest": ""}

            async def _factbook_phase(code: str):
                fb = FactBook()
                yield "event: factbook_start\ndata: {}\n\n"
                raw: dict = {}
                try:
                    async for ev in fb.collect_streaming(code, db):
                        t = ev.get("type")
                        if t == "collecting":
                            yield f"event: collecting\ndata: {json.dumps({'stage': ev.get('stage'), 'message': ev.get('message')}, ensure_ascii=False)}\n\n"
                        elif t == "factbook_raw":
                            raw = ev.get("raw") or {}
                except Exception:
                    logger.exception(f"FactBook collect failed for {code}")
                digest = fb.format(raw) if raw else ""
                fb_digest_holder["digest"] = digest
                if digest:
                    yield f"event: factbook_done\ndata: {json.dumps({'content': digest, 'reasoning': ''}, ensure_ascii=False)}\n\n"
                    db.add(ChatMessage(session_id=session_id, role="system", content=digest,
                                       meta={"round_type": "factbook"}))
                    await db.commit()
                else:
                    yield f"event: factbook_done\ndata: {json.dumps({'content': '', 'reasoning': ''}, ensure_ascii=False)}\n\n"

            if len(agents) >= 2:
                # ── 多 agent @mention 流程（同辩论结构：数据 agent → 投资 agent）──
                history_text = "\n\n".join(
                    f"【{m['role']}】: {m['content'][:600]}" for m in messages[-8:] if m["role"] in ("user", "assistant")
                )

                # 1. 平台 FactBook 数据采集（gated stock_codes）→ fb_digest，注入 fact-agent
                #    上下文（优先于 tavily；平台 K线/行业/宏观/regime/全 trend+分红 更准）。
                fb_digest = ""
                if stock_codes:
                    fb = FactBook()
                    _raw: dict = {}
                    try:
                        async for ev in fb.collect_streaming(stock_codes[0], db):
                            if ev.get("type") == "collecting":
                                yield f"event: collecting\ndata: {json.dumps({'stage': ev.get('stage'), 'message': ev.get('message')}, ensure_ascii=False)}\n\n"
                            elif ev.get("type") == "factbook_raw":
                                _raw = ev.get("raw") or {}
                    except Exception:
                        logger.exception(f"FactBook collect failed for {stock_codes[0]}")
                    fb_digest = fb.format(_raw) if _raw else ""

                # 2. 数据获取 agent（LLM + tavily function-calling ReAct）：复用辩论的 FACT_AGENT_SYSTEM（不评价只给数据）
                yield "event: factbook_start\ndata: {}\n\n"
                fact_system = FACT_AGENT_SYSTEM + (
                    "\n\n**额外能力**：你可以根据用户问题调用 tavily_search 获取必要的信息（公司/行业/宏观/分红/财报等），"
                    "然后按上述格式整理检索到的数据。检索结果与已有数据合并，缺失项标注。"
                )
                fact_user = f"用户问题：{req.message}\n\n近期对话上下文：\n{history_text}"
                if fb_digest:
                    fact_user = (
                        f"【平台 FactBook 数据（已采集，优先引用；缺失项已标注；如需实时新闻再调 tavily_search）】\n"
                        f"{fb_digest}\n\n{fact_user}"
                    )
                fact_messages = [
                    LLMMessage(role="system", content=fact_system),
                    LLMMessage(role="user", content=fact_user),
                ]
                data_summary = ""
                fact_reasoning = ""
                for _ in range(5):  # ReAct 最多 5 轮（检索+消化）
                    tool_calls = None
                    turn_content = ""
                    async for chunk in llm.chat_stream(
                        fact_messages, tools=DEBATE_TOOLS, max_tokens=None, enable_thinking=True,
                    ):
                        if chunk.tool_calls:
                            tool_calls = chunk.tool_calls
                        if chunk.reasoning:
                            fact_reasoning += chunk.reasoning
                            yield f"event: factbook_reasoning\ndata: {json.dumps({'delta': chunk.reasoning}, ensure_ascii=False)}\n\n"
                        if chunk.content:
                            turn_content += chunk.content
                            data_summary += chunk.content
                            yield f"event: factbook_token\ndata: {json.dumps({'delta': chunk.content}, ensure_ascii=False)}\n\n"
                    if not tool_calls:
                        break
                    fact_messages.append(LLMMessage(role="assistant", content=turn_content, tool_calls=tool_calls))
                    for tc in tool_calls:
                        fn = tc.get("function", {}) or {}
                        result = await execute_tool(fn.get("name", ""), fn.get("arguments", ""))
                        fact_messages.append(LLMMessage(role="tool", content=result, tool_call_id=tc.get("id", "")))
                yield f"event: factbook_done\ndata: {json.dumps({'content': data_summary, 'reasoning': fact_reasoning}, ensure_ascii=False)}\n\n"
                db.add(ChatMessage(session_id=session_id, role="system", content=data_summary,
                                   meta={"round_type": "factbook"}))
                await db.commit()

                # 2. 每 @agent 顺序流式分析（基于数据摘要 + 上下文）
                for ag in agents:
                    yield f"event: agent_start\ndata: {json.dumps({'agent_id': ag.id, 'agent_name': ag.name, 'round_type': 'analysis', 'round_num': 1}, ensure_ascii=False)}\n\n"
                    sys_prompt = (ag.system_prompt or "") + (
                        "\n\n（数据摘要已在下方提供，直接引用即可，无需调用外部工具）"
                    )
                    user_content = (
                        f"用户问题：{req.message}\n\n数据摘要（数据 agent 整理）：\n{data_summary or '（无）'}\n\n"
                        f"上下文（近期对话）：\n{history_text}\n\n"
                        f"请基于你的投资理念，结合数据摘要与上下文，对该问题给出补充分析。"
                    )
                    content = ""
                    reasoning = ""
                    try:
                        async for chunk in llm.chat_stream(
                            [LLMMessage(role="system", content=sys_prompt),
                             LLMMessage(role="user", content=user_content)],
                            max_tokens=None, enable_thinking=True,
                        ):
                            if chunk.reasoning:
                                reasoning += chunk.reasoning
                                yield f"event: agent_reasoning\ndata: {json.dumps({'agent_id': ag.id, 'delta': chunk.reasoning}, ensure_ascii=False)}\n\n"
                            if chunk.content:
                                content += chunk.content
                                yield f"event: agent_token\ndata: {json.dumps({'agent_id': ag.id, 'delta': chunk.content}, ensure_ascii=False)}\n\n"
                    except Exception as e:
                        logger.exception(f"Multi-agent {ag.name} stream error")
                        content = f"[本 agent 调用失败: {e!r}]"
                    yield f"event: agent_done\ndata: {json.dumps({'agent_id': ag.id, 'agent_name': ag.name, 'round_type': 'analysis', 'content': content, 'reasoning': reasoning}, ensure_ascii=False)}\n\n"
                    _meta: dict = {"round_type": "analysis", "agent_id": ag.id, "agent_name": ag.name}
                    if reasoning:
                        _meta["reasoning"] = reasoning
                    db.add(ChatMessage(session_id=session_id, role="assistant", content=content,
                                       agents_used=[ag.name], meta=_meta))
                    await db.commit()
                yield "event: done\ndata: {}\n\n"
            else:
                # ── 单 agent ReAct（function-calling）──
                full_response = ""
                llm_messages = [LLMMessage(role=m["role"], content=m["content"]) for m in messages]
                full_reasoning = ""

                # 平台 FactBook 数据采集（gated stock_codes）→ digest 注入 user 消息（优先于 tavily）。
                # 之前单 agent 仅注入 800 字 latest 切片，需财务数据时只能调 tavily（数据未必比平台好）。
                if stock_codes:
                    async for sse in _factbook_phase(stock_codes[0]):
                        yield sse
                    _digest = fb_digest_holder["digest"]
                    if _digest:
                        for i in range(len(llm_messages) - 1, -1, -1):
                            if llm_messages[i].role == "user":
                                llm_messages[i].content = (
                                    f"用户问题：{req.message}\n\n"
                                    f"【平台 FactBook 数据】（已为你采集，优先引用；缺失项已标注；"
                                    f"如需补充实时新闻再调 tavily_search）\n{_digest}\n\n请基于以上数据回答。"
                                )
                                break

                for _ in range(5):  # ReAct 最多 5 轮
                    tool_calls = None
                    turn_content = ""
                    async for chunk in llm.chat_stream(
                        llm_messages, tools=DEBATE_TOOLS, max_tokens=None, enable_thinking=True,
                    ):
                        if chunk.tool_calls:
                            tool_calls = chunk.tool_calls
                        if chunk.reasoning:
                            full_reasoning += chunk.reasoning
                            yield f"event: reasoning\ndata: {json.dumps({'delta': chunk.reasoning}, ensure_ascii=False)}\n\n"
                        if chunk.content:
                            turn_content += chunk.content
                            full_response += chunk.content
                            yield f"event: text\ndata: {json.dumps({'content': chunk.content}, ensure_ascii=False)}\n\n"
                    if not tool_calls:
                        break  # 最终答案（已流式）
                    llm_messages.append(LLMMessage(role="assistant", content=turn_content, tool_calls=tool_calls))
                    for tc in tool_calls:
                        fn = tc.get("function", {}) or {}
                        result = await execute_tool(fn.get("name", ""), fn.get("arguments", ""))
                        llm_messages.append(LLMMessage(role="tool", content=result, tool_call_id=tc.get("id", "")))
                # ISSUE-030: persist the assistant message BEFORE yielding stop,
                # so a client disconnect between stop and the finally-commit
                # doesn't lose the message (stop would tell the UI it's done).
                if full_response:
                    _sa_meta: dict = {}
                    if full_reasoning:
                        _sa_meta["reasoning"] = full_reasoning
                    db.add(ChatMessage(
                        session_id=session_id, role="assistant", content=full_response,
                        agents_used=[a.name for a in agents] or (["现代价值分析(默认)"] if default_agent else []),
                        stocks_detected=stock_codes[:3], token_count=estimate_tokens(full_response),
                        meta=_sa_meta,
                    ))
                    await db.commit()
                yield f"event: stop\ndata: {json.dumps({'reason': 'stop'})}\n\n"
        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
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
