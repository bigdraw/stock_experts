"""价值投资分析（组合器，复用已有能力，不重 fetch）。

不自己 fetch 三大报表/重算已缓存指标，而是：
1. 读已缓存的 financial_reports 周期财报（ensure_financial_reports 已拉）——
   复用 roe/eps/bps/revenue/net_profit/margins/growth/debt_ratio。
2. 调 provider.get_financial_statements（provider 方法，复用 _bypass_proxy/_parse_cn_number）
   取三大报表的"新字段"（total_assets/current_assets/current_liab/equity/ocf/capex/interest_exp）。
3. 按 report_date merge，只算 financial_reports 缓存里**没有**的指标：
   ROIC / OCF / FCF / FCF yield / 流动比率 / 现金比率 / 利息保障 / 盈利质量(OCF/净利)。
4. 估值复用 Latest 快照（per/pb/mktcap/price）+ 已缓存 revenue/eps/bps + 新 OCF + 分红。

价值投资指标分层：估值 / 盈利能力 / 财务安全 / 现金流 / 成长性 / 股东回报。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import FinancialReport, Stock
from app.services.data.akshare_provider import AkShareProvider

logger = logging.getLogger(__name__)
_TAX_RATE = 0.25


async def analyze(db: AsyncSession, stock_code: str, provider: AkShareProvider | None = None) -> dict[str, Any]:
    """价值投资分析。读缓存 + provider 取新字段 + 组合，返回指标 dict。"""
    provider = provider or AkShareProvider()

    # 股票市场 → 三大报表需要的 sh/sz 前缀
    stock = await db.get(Stock, stock_code)
    if not stock:
        return {"error": f"Stock {stock_code} not found"}
    prefix = "sh" if stock.market == "SH" else "sz"

    # 1. 读已缓存的周期财报（复用 ensure_financial_reports 的成果）
    rows = (
        await db.execute(
            select(FinancialReport)
            .where(FinancialReport.stock_code == stock_code, FinancialReport.report_type != "Latest")
            .order_by(FinancialReport.report_date.asc())
        )
    ).scalars().all()
    cached = {}
    for r in rows:
        rd = r.report_date.strftime("%Y-%m-%d") if r.report_date else None
        if not rd:
            continue
        cached[rd] = {
            "roe": r.roe, "eps": r.eps, "bps": r.bps,
            "revenue": r.revenue, "net_profit": r.net_profit,
            "gross_margin": r.gross_margin, "net_margin": r.net_margin,
            "debt_ratio": r.debt_ratio,
            "revenue_growth": r.revenue_growth, "net_profit_growth": r.net_profit_growth,
        }

    # 2. provider 取三大报表新字段
    statements = await provider.get_financial_statements(f"{prefix}{stock_code}")
    # statements report_date 是 YYYYMMDD → 归一 YYYY-MM-DD
    stmt_by_date = {}
    for s in statements:
        rd = s["report_date"]
        rd_norm = f"{rd[:4]}-{rd[4:6]}-{rd[6:8]}" if len(rd) == 8 and "-" not in rd else rd
        s["report_date"] = rd_norm
        stmt_by_date[rd_norm] = s

    # 3. merge + 算新指标（只算缓存没有的）
    periods = []
    all_dates = sorted(set(cached) | set(stmt_by_date))
    for rd in all_dates:
        c = cached.get(rd, {})
        s = stmt_by_date.get(rd, {})
        total_assets = s.get("total_assets")
        current_assets = s.get("current_assets")
        current_liab = s.get("current_liab")
        equity = s.get("equity")
        op_profit = s.get("op_profit")
        net_profit = s.get("net_profit") or c.get("net_profit")
        interest_exp = s.get("interest_exp")
        ocf = s.get("ocf")
        capex = s.get("capex")
        revenue = s.get("revenue") or c.get("revenue")

        # 所得税率近似（从利润表利润总额+净利润推）
        tax_rate = _TAX_RATE
        # ROIC NOPAT 用 EBIT 口径 = 营业利润 + 利息费用（ISSUE-028）。利润表"营业利润"
        # 已扣除财务费用（利息），直接用 op_profit 会让利息在分子(NOPAT)与分母(投入
        # 资本含付息负债)双重扣减，ROIC 系统性偏低。interest_exp 缺失时退回 op_profit。
        if op_profit is not None:
            ebit = op_profit + (interest_exp or 0)
            nopat = ebit * (1 - tax_rate)
        else:
            nopat = None
        # ROIC 投入资本 = 股东权益 + 非流动负债（= 总资产 - 流动负债 - 货币资金中超出经营需要的部分）
        # 简化：equity + (total_liab - current_liab)；如果 total_liab 缺失则退回 total_assets - current_liab
        if total_assets and current_liab:
            non_current_liab = s.get("total_liab")
            if non_current_liab is not None and non_current_liab >= current_liab:
                invested = s.get("equity", 0) + (non_current_liab - current_liab) if s.get("equity") else (total_assets - current_liab)
            else:
                invested = total_assets - current_liab
        else:
            invested = None
        roic = nopat / invested if (nopat is not None and invested and invested > 0) else None
        roa = net_profit / total_assets if (net_profit and total_assets) else None
        current_ratio = current_assets / current_liab if (current_assets and current_liab) else None
        cash_ratio = s.get("cash") / current_liab if (s.get("cash") and current_liab) else None
        interest_coverage = op_profit / interest_exp if (op_profit and interest_exp and interest_exp != 0) else None
        fcf = (ocf - capex) if (ocf is not None and capex is not None) else None
        # earnings_quality 仅在净利>0 时计算（ISSUE-030）：OCF/净利双负时比值为正伪信号
        # （如 OCF=-0.48亿/净利=-0.12亿=4.0，表面像盈利质量高，实为双重负数）。
        earnings_quality = ocf / net_profit if (ocf and net_profit and net_profit > 0) else None

        periods.append({
            "report_date": rd,
            # 复用缓存
            "roe": c.get("roe"), "eps": c.get("eps"), "bps": c.get("bps"),
            "revenue": revenue, "net_profit": net_profit,
            "gross_margin": c.get("gross_margin"), "net_margin": c.get("net_margin"),
            "debt_ratio": c.get("debt_ratio") or (s.get("total_liab") / total_assets if (s.get("total_liab") and total_assets) else None),
            "revenue_growth": c.get("revenue_growth"), "net_profit_growth": c.get("net_profit_growth"),
            # 新算
            "roa": roa, "roic": roic, "current_ratio": current_ratio, "cash_ratio": cash_ratio,
            "interest_coverage": interest_coverage, "ocf": ocf, "fcf": fcf, "capex": capex,
            "earnings_quality": earnings_quality,
            "total_assets": total_assets, "equity": equity,
        })

    if not periods:
        return {"error": "无可分析报告期（先访问该股详情页触发财报拉取）"}

    latest = periods[-1]
    annuals = [p for p in periods if p["report_date"].endswith("12-31")]

    # 4. 成长性 CAGR（复用缓存 revenue/net_profit/equity 年报）
    def _cagr(field: str, years: int):
        if len(annuals) < years + 1:
            return None
        s, e = annuals[-(years + 1)].get(field), annuals[-1].get(field)
        # 基期或终期 ≤0 → CAGR 无意义（负数开根号产生复数）
        if not s or not e or s <= 0 or e <= 0 or e > 20 * s:
            return None
        return (e / s) ** (1 / years) - 1

    growth = {}
    for f in ("revenue", "net_profit", "equity"):
        growth[f] = {"cagr_3y": _cagr(f, 3), "cagr_5y": _cagr(f, 5)}

    # 4.5 TTM（滚动 12 个月）累计值：最近年报累计 − 同季上年累计 + 最新累计
    #     用于 Graham/PCF/FCF yield，避免直接用单季累计 ×4 在季节性强的字段上失真。
    def _ttm(field: str):
        if latest.get(field) is None:
            return None
        rd = latest["report_date"]
        if rd.endswith("12-31"):
            return latest[field]
        annuals_f = [p for p in periods
                     if p["report_date"].endswith("12-31") and p.get(field) is not None]
        if not annuals_f:
            return None
        last_annual = annuals_f[-1][field]
        try:
            same_q_prev = f"{int(rd[:4]) - 1}{rd[4:]}"
        except (ValueError, IndexError):
            return None
        prev = next((p for p in periods
                     if p["report_date"] == same_q_prev and p.get(field) is not None), None)
        if prev is None:
            return last_annual  # 缺同季上年 → 退回最近年报值，不强行 ×4
        return last_annual - prev[field] + latest[field]

    # 5. 估值：复用 Latest 快照
    snap = (
        await db.execute(
            select(FinancialReport).where(
                FinancialReport.stock_code == stock_code, FinancialReport.report_type == "Latest"
            ).order_by(FinancialReport.report_date.desc()).limit(1)
        )
    ).scalar_one_or_none()
    valuation = {}
    market_cap = None
    price = None
    if snap:
        market_cap = (snap.mktcap or 0) * 10000 if snap.mktcap else None  # 万元→元
        price = snap.price
        # PE 用 TTM EPS；EPS≤0 或极小（<0.01，PE>5000 无意义）→ 不退回 snap.per（避免亏损公司给出正 PE）
        ttm_eps = _ttm("eps")
        if price and ttm_eps and ttm_eps > 0.01:
            valuation["pe"] = price / ttm_eps
        # EPS≤0 或极小 → PE 不设（None），不退回快照
        valuation["pb"] = snap.pb
        # PS 用 TTM 营收（与 PCF/FCF yield 口径一致），不用 Q1 年化
        ttm_rev = _ttm("revenue")
        if market_cap and ttm_rev:
            valuation["ps"] = market_cap / ttm_rev
            valuation["ps_basis"] = "ttm"
        elif market_cap and latest.get("revenue"):
            # TTM 算不出时退回简单年化（旧逻辑，比无值好），但标记低置信度（ISSUE-028）：
            # 之前静默降级会让 FactBook/digest 把 Q1×4 当 TTM，对季节性强的周期股
            # 误导"贵/便宜"判断（实测浩物股份偏高 29%）。
            rd = latest["report_date"]
            ann_rev = latest["revenue"] * (
                1 if rd.endswith("12-31") else 4 if rd.endswith("03-31")
                else 2 if rd.endswith("06-30") else 4 / 3
            )
            valuation["ps"] = market_cap / ann_rev if ann_rev else None
            valuation["ps_basis"] = "annualized"  # 下游应降权 / 标注
        ttm_ocf = _ttm("ocf")
        if market_cap and ttm_ocf:
            valuation["pcf"] = market_cap / ttm_ocf
        ttm_fcf = _ttm("fcf")
        if market_cap and ttm_fcf is not None:
            valuation["fcf_yield"] = ttm_fcf / market_cap
        # Graham number = sqrt(22.5 * EPS_ttm * BVPS)；EPS 用 TTM（已算），BVPS 用最新期末
        # EPS/BVPS ≤ 0 时 sqrt 负数会返回复数 → 跳过
        # ttm_eps 已在上面计算（PE 用），这里复用
        if ttm_eps and ttm_eps > 0 and latest.get("bps") and latest["bps"] > 0:
            valuation["graham_number"] = (22.5 * ttm_eps * latest["bps"]) ** 0.5

    # 6. 分红 + 股息率（TTM 口径：近 12 个月除权分红之和 / 最新价）
    dividends = await provider.get_dividends(stock_code)
    # 按除权日倒序（缺 ex_date 用 announce_date），保证 [:20] 保留最新、而非最旧
    def _div_date(d: dict) -> str:
        for k in ("ex_date", "announce_date"):
            v = (d.get(k) or "").strip()
            if v:
                return v
        return ""
    dividends = sorted(dividends, key=_div_date, reverse=True)
    if price and dividends:
        today_str = date.today().strftime("%Y-%m-%d")
        cutoff = (date.today() - timedelta(days=365)).strftime("%Y-%m-%d")
        ttm_dps = 0.0
        has_recent = False
        for d in dividends:
            dd = _div_date(d)
            if dd and cutoff <= dd <= today_str:
                ttm_dps += d.get("dividend_per_share") or 0
                has_recent = True
        # 只用近 12 个月有分红时才算股息率——5 年前的旧分红不算（避免误报）
        if has_recent and ttm_dps > 0:
            valuation["dividend_yield"] = ttm_dps / price
        # 无近 12 个月分红 → dividend_yield 不设（None），表示"当前无分红"

    return {
        "latest": latest,
        "valuation": valuation,
        "growth": growth,
        "trend": periods[-20:],
        "dividends": dividends[:20],
        "annual_count": len(annuals),  # 年报期数（非连续分红年数，事实 agent 勿当连续分红年用）
        "dividend_count": len(dividends),
    }
