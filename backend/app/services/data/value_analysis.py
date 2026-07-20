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
        nopat = op_profit * (1 - tax_rate) if op_profit is not None else None
        invested = (total_assets - current_liab) if (total_assets and current_liab) else None
        roic = nopat / invested if (nopat is not None and invested and invested != 0) else None
        roa = net_profit / total_assets if (net_profit and total_assets) else None
        current_ratio = current_assets / current_liab if (current_assets and current_liab) else None
        cash_ratio = s.get("cash") / current_liab if (s.get("cash") and current_liab) else None
        interest_coverage = op_profit / interest_exp if (op_profit and interest_exp and interest_exp != 0) else None
        fcf = (ocf - capex) if (ocf is not None and capex is not None) else None
        earnings_quality = ocf / net_profit if (ocf and net_profit and net_profit != 0) else None

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
        if not s or not e or s <= 0:
            return None
        return (e / s) ** (1 / years) - 1

    growth = {}
    for f in ("revenue", "net_profit", "equity"):
        growth[f] = {"cagr_3y": _cagr(f, 3), "cagr_5y": _cagr(f, 5)}

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
        valuation["pe"] = snap.per
        valuation["pb"] = snap.pb
        if market_cap and latest.get("revenue"):
            rd = latest["report_date"]
            ann_rev = latest["revenue"] * (
                1 if rd.endswith("12-31") else 4 if rd.endswith("03-31")
                else 2 if rd.endswith("06-30") else 4 / 3
            )
            valuation["ps"] = market_cap / ann_rev if ann_rev else None
        if market_cap and latest.get("ocf"):
            valuation["pcf"] = market_cap / (latest["ocf"] * 4)
        if market_cap and latest.get("fcf") is not None:
            valuation["fcf_yield"] = (latest["fcf"] * 4) / market_cap
        # Graham number = sqrt(22.5 * EPS * BVPS)
        if latest.get("eps") and latest.get("bps"):
            valuation["graham_number"] = (22.5 * latest["eps"] * latest["bps"]) ** 0.5

    # 6. 分红 + 股息率
    dividends = await provider.get_dividends(stock_code)
    if price and dividends:
        # 最新一次分红每股
        dps = next((d.get("dividend_per_share") for d in dividends if d.get("dividend_per_share")), None)
        if dps:
            valuation["dividend_yield"] = dps / price

    return {
        "latest": latest,
        "valuation": valuation,
        "growth": growth,
        "trend": periods[-20:],
        "dividends": dividends[:20],
        "annual_count": len(annuals),
    }
