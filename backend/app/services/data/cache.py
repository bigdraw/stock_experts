"""按需拉取并缓存行情/财报数据（fetch-on-demand + cache）。

解决"数据没下载"问题：StockDetail 的 K线/财报表、以及回测所需的历史OHLCV，
不依赖预先跑全量采集——首次访问时从 akshare 拉取所需区间并 upsert 入库，
后续直接读 DB。这样 K线图立即有数据、回测可即跑、且逐步积累 daily_quotes。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import DailyQuote, FinancialReport
from app.services.data.akshare_provider import AkShareProvider
from app.services.data.provider import FinancialReport as FR

logger = logging.getLogger(__name__)


async def ensure_daily_quotes(
    db: AsyncSession, code: str, days: int = 120, provider: AkShareProvider | None = None
) -> int:
    """确保 DB 有 code 最近 `days` 个交易日的日K；不足或过期则从 akshare 拉取并缓存。

    本地优先策略（不每次都打数据源）：
    1. DB 已有 >= days 根且**最新 bar 是今天/上一交易日**→直接返回缓存，不拉取。
    2. DB 已有 >= days 根但**最新 bar 过期**（如今天开盘后看昨天数据）→只拉
       最新 bar 之后的增量（delta，通常 1-2 根），不重拉全量。
    3. DB 不足 days 根→拉取最近 days*1.6 天的全量并 upsert（首次填充）。

    返回该股票在 DB 中的日K条数。upsert 按 (stock_code, date) 唯一约束去重。
    """
    provider = provider or AkShareProvider()
    # 先查 DB 已有量 + 最新日期
    existing = await db.execute(
        select(DailyQuote.date)
        .where(DailyQuote.stock_code == code)
        .order_by(DailyQuote.date.desc())
        .limit(days)
    )
    have_dates = [row[0] for row in existing.all()]
    have_set = set(have_dates)
    latest = have_dates[0] if have_dates else None
    today = date.today()
    days_behind = (today - latest).days if latest else 999
    is_weekend = today.weekday() >= 5  # Sat=5, Sun=6

    # 缓存命中（不拉取）：充足 且 最新 bar 是今天；或周末且最新是周五（市场休市）
    fresh = days_behind == 0 or (is_weekend and days_behind <= 2)
    if len(have_set) >= days and fresh:
        return len(have_set)

    # 确定拉取区间
    if latest is not None and len(have_set) >= days:
        # 情况2：缓存足但过期→只拉 latest 之后的增量（从 latest 次日起）
        start = (latest + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        # 情况3：不足→拉最近 days*1.6 天全量
        start = (today - timedelta(days=int(days * 1.6))).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    if start > end:
        return len(have_set)  # latest 已是今天，无需拉

    try:
        quotes = await provider.get_daily_quotes(code, start, end)
    except Exception as e:
        logger.warning(f"ensure_daily_quotes fetch failed for {code} [{start}~{end}]: {e}")
        return len(have_set)

    added = 0
    for q in quotes:
        qd = _parse_date(q.date)
        if qd is None or qd in have_set:
            continue
        db.add(
            DailyQuote(
                stock_code=code,
                date=qd,
                open=q.open, high=q.high, low=q.low, close=q.close,
                volume=q.volume, amount=q.amount, turnover_rate=q.turnover_rate,
            )
        )
        have_set.add(qd)
        added += 1
    if added:
        await db.flush()
        logger.info(f"ensure_daily_quotes: cached {added} bars for {code} [{start}~{end}]")
    return len(have_set)


async def ensure_financial_reports(
    db: AsyncSession, code: str, provider: AkShareProvider | None = None
) -> int:
    """确保 DB 有 code 的周期财报（Q1/H1/Q3/Annual）；无则从 akshare 拉取并缓存。

    full_basic_collection 只存 'Latest' 快照；周期财报来自 get_financial_reports
    与 get_financial_analysis_indicators。首次访问 StockDetail 时按需拉取该股财报。
    """
    provider = provider or AkShareProvider()
    # 已有周期财报就跳过
    existing = await db.execute(
        select(FinancialReport.id)
        .where(FinancialReport.stock_code == code, FinancialReport.report_type != "Latest")
        .limit(1)
    )
    if existing.first() is not None:
        return 0

    added = 0
    # 1. get_financial_reports（revenue/net_profit/roe/pe/pb/market_cap）
    try:
        reports = await provider.get_financial_reports(code)
    except Exception as e:
        logger.warning(f"get_financial_reports failed for {code}: {e}")
        reports = []
    for r in reports:
        added += await _upsert_financial(db, r)

    # 2. get_financial_analysis_indicators（eps/bps/gross_margin/net_margin/growth/debt_ratio）
    try:
        analysis = await provider.get_financial_analysis_indicators(code)
    except Exception as e:
        logger.warning(f"get_financial_analysis_indicators failed for {code}: {e}")
        analysis = []
    for r in analysis:
        added += await _upsert_financial(db, r)

    if added:
        await db.flush()
        logger.info(f"ensure_financial_reports: cached {added} periodic reports for {code}")
    return added


async def _upsert_financial(db: AsyncSession, r: FR) -> int:
    """upsert 一条 FinancialReport（按 stock_code+report_date+report_type 去重）。

    已存在则合并字段（保留已有非空值，补充新字段），否则插入。返回 1=新增/更新。
    """
    from datetime import datetime
    rd = _parse_date(r.report_date) or datetime.now().date()
    existing = await db.execute(
        select(FinancialReport).where(
            FinancialReport.stock_code == r.code,
            FinancialReport.report_date == rd,
            FinancialReport.report_type == (r.report_type or "Latest"),
        )
    )
    row = existing.scalar_one_or_none()
    if row is None:
        db.add(
            FinancialReport(
                stock_code=r.code, report_date=rd, report_type=r.report_type or "Latest",
                revenue=r.revenue, net_profit=r.net_profit, roe=r.roe,
                pe_ratio=r.pe_ratio, pb_ratio=r.pb_ratio, market_cap=r.market_cap,
                eps=r.eps, bps=r.bps, revenue_growth=r.revenue_growth,
                net_profit_growth=r.net_profit_growth, gross_margin=r.gross_margin,
                net_margin=r.net_margin, debt_ratio=r.debt_ratio,
            )
        )
        return 1
    # 合并：空字段补充
    for attr, val in [
        ("revenue", r.revenue), ("net_profit", r.net_profit), ("roe", r.roe),
        ("eps", r.eps), ("bps", r.bps), ("revenue_growth", r.revenue_growth),
        ("net_profit_growth", r.net_profit_growth), ("gross_margin", r.gross_margin),
        ("net_margin", r.net_margin), ("debt_ratio", r.debt_ratio),
    ]:
        if val is not None and getattr(row, attr) is None:
            setattr(row, attr, val)
    return 1


def _parse_date(s: str | None):
    """解析 YYYY-MM-DD 或 YYYYMMDD 为 date。"""
    if not s:
        return None
    from datetime import datetime
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(s), fmt).date()
        except ValueError:
            continue
    return None
