"""Agent tool discovery — 让 agent 自发现平台的指标/分析能力（idea3）。

GET /agent/tools 返回所有分析端点的清单（路径/方法/一句话/参数/返回字段），
agent（opencode/MCP/任意 HTTP agent）据此调用得出结论，无需人工告知 API。
GET /agent/web-search?q=... 联网搜索（tavily 优先，无 key 降级 DuckDuckGo）。
这是"把已实现的指标计算/获取逻辑抽取为 agent 可调用工具"的发现层；
具体计算复用 /quant/* 与 /stocks/{code}/* 既有端点，不重写。
"""

import logging
import os

import httpx
from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


TOOLS: list[dict] = [
    {
        "name": "value_analysis",
        "method": "GET",
        "path": "/api/v1/stocks/{code}/value-analysis",
        "desc": "价值投资分析：估值(PE/PB/PS/PCF/Graham/股息率) + 盈利能力(ROE/ROA/ROIC/利润率)"
                " + 财务安全(资产负债率/流动比率/利息保障) + 现金流(OCF/FCF/FCF yield/盈利质量)"
                " + 成长性(CAGR) + 分红。复用缓存财报+三大报表，按需拉取。",
        "params": {"code": "股票代码如 600519"},
        "returns": "latest(当期指标) / valuation / growth(CAGR) / trend(近20期) / dividends",
        "auth": "Bearer token (任意登录用户)",
    },
    {
        "name": "latest_indicators",
        "method": "GET",
        "path": "/api/v1/stocks/{code}/indicators",
        "desc": "最新行情快照（Sina 20 字段：price/open/high/low/per/pb/mktcap/turnover 等）",
        "params": {"code": "股票代码"},
        "returns": "20 个行情字段 + is_profitable",
        "auth": "Bearer token",
    },
    {
        "name": "quotes_kline",
        "method": "GET",
        "path": "/api/v1/stocks/{code}/quotes",
        "desc": "历史K线（全量缓存+按需拉取），支持 period=daily/weekly/monthly/quarterly/yearly",
        "params": {"code": "股票代码", "period": "周期(默认daily)", "limit": "条数(默认1000)"},
        "returns": "OHLCV 日K列表",
        "auth": "Bearer token",
    },
    {
        "name": "financials",
        "method": "GET",
        "path": "/api/v1/stocks/{code}/financials",
        "desc": "周期财报历史（Q1/H1/Q3/Annual，按需拉取并缓存），含营收/净利/ROE/EPS/利润率等",
        "params": {"code": "股票代码"},
        "returns": "周期财报列表（不含 Latest 快照）",
        "auth": "Bearer token",
    },
    {
        "name": "quant_strategies",
        "method": "GET",
        "path": "/api/v1/quant/strategies",
        "desc": "列出 9 个结构化策略模板（sma/ema/macd/rsi/bollinger/momentum/mean_reversion/breakout/volume_momentum）+ 默认参数",
        "params": {},
        "returns": "策略名→{name,description,default_parameters,optimization_ranges}",
        "auth": "Bearer token",
    },
    {
        "name": "quant_backtest_run",
        "method": "POST",
        "path": "/api/v1/quant/backtest/run",
        "desc": "服务端取数回测：选策略+股票+区间，后端拉历史K线+跑纯pandas回测，返回指标+权益曲线",
        "params": {"strategy_type": "策略名", "parameters": "策略参数", "stock_code": "股票", "days": "回测窗口", "initial_capital": "初始资金"},
        "returns": "metrics(total_return/sharpe/max_drawdown/win_rate/profit_factor) + equity_curve",
        "auth": "Bearer token",
    },
    {
        "name": "quant_regime",
        "method": "POST",
        "path": "/api/v1/quant/regime",
        "desc": "市场状态识别（bull/bear/choppy/transitional），4因子加权",
        "params": {"prices": "指数价格序列", "vix_level": "波动率", "breadth_ratio": "涨跌家数比"},
        "returns": "{regime, confidence, drivers, votes}",
        "auth": "Bearer token",
    },
    {
        "name": "quant_risk_dashboard",
        "method": "POST",
        "path": "/api/v1/quant/risk/dashboard",
        "desc": "组合风险看板：总市值/行业集中度/VaR95/99/总盈亏",
        "params": {"positions": "[{symbol,shares,cost_basis,current_price,sector}]"},
        "returns": "{total_value, sector_concentration, portfolio_var_95/99, total_pnl}",
        "auth": "Bearer token",
    },
    {
        "name": "quant_signals_evaluate",
        "method": "POST",
        "path": "/api/v1/quant/signals/evaluate",
        "desc": "信号条件求值（price/rsi/volume/sma × lt/gt/crosses_above等），支持跨次状态",
        "params": {"condition": "{indicator,operator,threshold,...}", "bars": "OHLCV"},
        "returns": "{triggered, current_value, new_state}",
        "auth": "Bearer token",
    },
    {
        "name": "quant_screening",
        "method": "POST",
        "path": "/api/v1/quant/screening/{screen}",
        "desc": "可解释三策略打分（bullish/bearish/supply_demand），返回 flag+score+reason",
        "params": {"screen": "策略名", "bars": "OHLCV", "symbol": "标的代码"},
        "returns": "{combined_score, flags, reason, indicators} 或 {qualified:false}",
        "auth": "Bearer token",
    },
    {
        "name": "web_search",
        "method": "GET",
        "path": "/agent/web-search?q=...",
        "desc": "联网搜索（tavily 优先，无 key 降级 DuckDuckGo），返回摘要+结果列表",
        "params": {"q": "搜索查询"},
        "returns": "{source, query, answer, results:[{title,url,content}]}",
        "auth": "Bearer token",
    },
]


@router.get("/tools")
async def list_tools() -> dict:
    """列出所有 agent 可调用的分析工具（端点+schema）。"""
    return {"tools": TOOLS, "count": len(TOOLS), "base_url": "http://127.0.0.1:8000"}


@router.get("/web-search")
async def web_search(q: str = Query(..., description="搜索查询")):
    """联网搜索（agent 的 tavily 替代/实现）。

    优先用 TAVILY_API_KEY 调 tavily；无 key 时降级 DuckDuckGo Instant Answer API
    （免费、无需 key，返回摘要+相关话题）。这样 agent 的"tavily 联网搜索"始终可用。
    """
    tavily_key = os.environ.get("TAVILY_API_KEY")
    if tavily_key:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": tavily_key,
                        "query": q,
                        "max_results": 5,
                        "include_answer": True,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "source": "tavily",
                        "query": q,
                        "answer": data.get("answer", ""),
                        "results": [
                            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")[:200]}
                            for r in data.get("results", [])
                        ],
                    }
        except Exception as e:
            logger.warning(f"tavily search failed: {e}, fallback to DuckDuckGo")

    # DuckDuckGo Instant Answer (free, no key)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": q, "format": "json", "no_html": 1, "skip_disambig": 1},
            )
            if resp.status_code == 200:
                data = resp.json()
                results = []
                if data.get("AbstractText"):
                    results.append({
                        "title": data.get("Heading", q),
                        "url": data.get("AbstractURL", ""),
                        "content": data["AbstractText"][:300],
                    })
                for topic in (data.get("RelatedTopics") or [])[:5]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append({
                            "title": topic.get("Text", "")[:80],
                            "url": topic.get("FirstURL", ""),
                            "content": topic.get("Text", "")[:200],
                        })
                return {
                    "source": "duckduckgo",
                    "query": q,
                    "answer": data.get("AbstractText", ""),
                    "results": results,
                }
    except Exception as e:
        logger.error(f"web search failed: {e}")
        return {"error": f"web search failed: {e}", "query": q}

    return {"error": "web search returned no results", "query": q}
