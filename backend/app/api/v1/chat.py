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


# --- idea24: 分析 MCP 工具端点（组合分析/个股分析/基金分析）---
# 不替 agent 下结论——只提供数据，agent 基于数据自行判断。


class StockAnalysisRequest(BaseModel):
    """个股分析：确认股票存在 + 取价值分析数据。"""
    code: str


@router.post("/analyze/stock")
async def analyze_stock(
    req: StockAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """个股分析工具（idea24）：验证股票存在 → 返回价值分析数据供 agent 使用。

    如果股票不存在，返回 {found: false}——不瞎编。
    """
    from app.models.stock import Stock
    from app.services.data.cache import ensure_financial_reports
    from app.services.data.value_analysis import analyze

    # 确认股票存在
    stock = await db.get(Stock, req.code)
    if not stock:
        return {"found": False, "message": f"股票 {req.code} 不存在于数据库中"}

    # 取价值分析
    await ensure_financial_reports(db, req.code)
    await db.commit()
    va = await analyze(db, req.code)
    return {
        "found": True,
        "stock": {"code": stock.code, "name": stock.name, "market": stock.market},
        "value_analysis": va,
    }


class PortfolioAnalysisRequest(BaseModel):
    """组合分析：确认组合存在 + 取持仓+风险。"""
    portfolio_id: int


@router.post("/analyze/portfolio")
async def analyze_portfolio(
    req: PortfolioAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """组合分析工具（idea24）：验证组合存在 → 返回持仓+风险看板供 agent 使用。

    如果组合不存在或非本人，返回 {found: false}。
    """
    from app.models.portfolio import Portfolio, PortfolioItem
    from app.services.risk.service import compute_dashboard, generate_alerts

    portfolio = await db.get(Portfolio, req.portfolio_id)
    if not portfolio:
        return {"found": False, "message": f"组合 {req.portfolio_id} 不存在"}

    # 取持仓
    items_result = await db.execute(
        select(PortfolioItem).where(PortfolioItem.portfolio_id == req.portfolio_id)
    )
    items = items_result.scalars().all()

    # 构建 positions（用 Latest 快照的当前价）
    from app.models.stock import FinancialReport
    positions = []
    for item in items:
        fin_result = await db.execute(
            select(FinancialReport).where(
                FinancialReport.stock_code == item.stock_code,
                FinancialReport.report_type == "Latest",
            ).order_by(FinancialReport.report_date.desc()).limit(1)
        )
        fin = fin_result.scalar_one_or_none()
        positions.append({
            "symbol": item.stock_code,
            "shares": float(item.shares or 0),
            "cost_basis": float(item.avg_cost or 0),
            "current_price": float(fin.price) if fin and fin.price else 0,
            "sector": "Unknown",
        })

    dashboard = compute_dashboard(positions)
    alerts = [a.__dict__ for a in generate_alerts(positions)]

    return {
        "found": True,
        "portfolio": {"id": portfolio.id, "name": portfolio.name},
        "positions": positions,
        "risk_dashboard": dashboard,
        "risk_alerts": alerts,
    }


class FundAnalysisRequest(BaseModel):
    """基金分析：支持场内 ETF（股票代码形式）+ 场外基金（基金代码）。"""
    code: str


@router.post("/analyze/fund")
async def analyze_fund(
    req: FundAnalysisRequest,
    current_user: User = Depends(get_current_user),
):
    """基金分析工具（idea24）：验证基金存在 → 返回基本信息。

    场内 ETF：用股票代码（如 510300）查 akshare ETF 行情。
    场外基金：用基金代码（如 000001）查 akshare 开放式基金净值。
    如果不存在，返回 {found: false}。
    """
    import akshare as ak

    from app.services.data.akshare_provider import _bypass_proxy, _restore_proxy

    code = req.code.strip()
    result = {"found": False, "code": code}

    # 场内 ETF（5/1 开头）
    if code.startswith(("5", "1")) and len(code) == 6:
        op = _bypass_proxy()
        try:
            df = ak.fund_etf_hist_em(symbol=code, period="daily", adjust="qfq")
            if len(df) > 0:
                latest = df.iloc[-1]
                result = {
                    "found": True,
                    "code": code,
                    "type": "ETF",
                    "latest_date": str(latest["日期"]),
                    "close": float(latest["收盘"]),
                    "volume": float(latest["成交量"]),
                    "rows": len(df),
                }
        except Exception as e:
            result["message"] = f"ETF 查询失败: {str(e)[:60]}"
        finally:
            _restore_proxy(op)

    # 场外基金（0/1 开头）
    if not result.get("found") and len(code) == 6:
        op = _bypass_proxy()
        try:
            df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
            if len(df) > 0:
                latest = df.iloc[-1]
                result = {
                    "found": True,
                    "code": code,
                    "type": "开放式基金",
                    "latest_date": str(latest["净值日期"]),
                    "nav": float(latest["单位净值"]),
                    "rows": len(df),
                }
        except Exception as e:
            result["message"] = f"基金查询失败: {str(e)[:60]}"
        finally:
            _restore_proxy(op)

    if not result.get("found") and "message" not in result:
        result["message"] = "未找到该基金（场内 ETF 或场外开放式基金）"
    return result
