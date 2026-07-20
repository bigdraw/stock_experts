"""Stock API routes."""

from fastapi import APIRouter, Depends, Query
from pypinyin import Style, pinyin
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.database import get_db
from app.models.stock import DailyQuote, FinancialReport, Stock
from app.models.user import User
from app.schemas import DailyQuoteResponse, StockResponse
from app.utils.exceptions import NotFoundException

router = APIRouter(prefix="/stocks", tags=["stocks"])


def get_pinyin(text: str) -> str:
    """Convert Chinese text to pinyin."""
    if not text:
        return ""
    return "".join([item[0] for item in pinyin(text, style=Style.NORMAL)])


def get_first_letter(text: str) -> str:
    """Get first letter of each Chinese character."""
    if not text:
        return ""
    return "".join([item[0][0] for item in pinyin(text, style=Style.FIRST_LETTER)])


@router.get("/count")
async def count_stocks(
    market: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get total count of stocks."""
    query = select(func.count()).select_from(Stock).where(Stock.is_active)
    if market:
        query = query.where(Stock.market == market)
    result = await db.execute(query)
    count = result.scalar()
    return {"count": count}


@router.get("", response_model=list[StockResponse])
async def list_stocks(
    market: str | None = None,
    search: str | None = None,
    limit: int = Query(default=100, le=10000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List stocks with optional filtering."""
    query = select(Stock).where(Stock.is_active)
    if market:
        query = query.where(Stock.market == market)
    if search:
        query = query.where(Stock.name.contains(search) | Stock.code.contains(search))
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/with-indicators", response_model=list[dict])
async def list_stocks_with_indicators(
    market: str | None = None,
    search: str | None = None,
    limit: int = Query(default=100, le=10000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List stocks with their latest financial indicators."""
    from sqlalchemy import and_, func

    # Subquery to get the most recent report date for each stock
    latest_dates_subq = (
        select(FinancialReport.stock_code, func.max(FinancialReport.report_date).label("max_date"))
        .where(FinancialReport.report_type == "Latest")
        .group_by(FinancialReport.stock_code)
        .subquery()
    )

    # Main query joining stocks with their latest financial reports
    query = (
        select(
            Stock.code,
            Stock.name,
            Stock.market,
            Stock.industry,
            Stock.sector,
            Stock.is_active,
            # All 20 market fields from Sina API
            FinancialReport.symbol,
            FinancialReport.price,
            FinancialReport.pricechange,
            FinancialReport.changepercent,
            FinancialReport.buy,
            FinancialReport.sell,
            FinancialReport.settlement,
            FinancialReport.open,
            FinancialReport.high,
            FinancialReport.low,
            FinancialReport.volume,
            FinancialReport.amount,
            FinancialReport.ticktime,
            FinancialReport.per,
            FinancialReport.pb,
            FinancialReport.mktcap,
            FinancialReport.nmc,
            FinancialReport.turnoverratio,
            # Legacy fields for backward compatibility
            FinancialReport.pe_ratio,
            FinancialReport.pb_ratio,
            FinancialReport.market_cap,
            FinancialReport.circulating_market_cap,
            # 衍生指标
            FinancialReport.is_profitable,
        )
        .outerjoin(latest_dates_subq, Stock.code == latest_dates_subq.c.stock_code)
        .outerjoin(
            FinancialReport,
            and_(
                Stock.code == FinancialReport.stock_code,
                FinancialReport.report_date == latest_dates_subq.c.max_date,
                FinancialReport.report_type == "Latest",
            ),
        )
        .where(Stock.is_active)
    )

    if market:
        query = query.where(Stock.market == market)
    if search:
        query = query.where(Stock.name.contains(search) | Stock.code.contains(search))

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    # Convert to list of dicts
    return [
        {
            "code": row.code,
            "name": row.name,
            "market": row.market,
            "industry": row.industry,
            "sector": row.sector,
            "is_active": row.is_active,
            # All 20 market fields from Sina API
            "symbol": row.symbol,
            "price": row.price,
            "pricechange": row.pricechange,
            "changepercent": row.changepercent,
            "buy": row.buy,
            "sell": row.sell,
            "settlement": row.settlement,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "volume": row.volume,
            "amount": row.amount,
            "ticktime": row.ticktime,
            "per": row.per,
            "pb": row.pb,
            "mktcap": row.mktcap,
            "nmc": row.nmc,
            "turnoverratio": row.turnoverratio,
            # Legacy fields for backward compatibility
            "pe_ratio": row.pe_ratio,
            "pb_ratio": row.pb_ratio,
            "market_cap": row.market_cap,
            "circulating_market_cap": row.circulating_market_cap,
            # 衍生指标
            "is_profitable": row.is_profitable,
        }
        for row in rows
    ]


@router.get("/search", response_model=list[StockResponse])
async def search_stocks(
    q: str = Query(
        ..., min_length=1, description="Search query (code, name, pinyin, or first letter)"
    ),
    limit: int = Query(default=100, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search stocks by code, name, pinyin, or first letter."""
    # Normalize query: remove spaces for fuzzy matching
    q_normalized = q.replace(" ", "").replace(" ", "")
    q_lower = q_normalized.lower()
    q_original = q  # Keep original for exact name matching

    # First, try database filtering by code and name (fast)
    query = (
        select(Stock)
        .where(
            Stock.is_active,
            (Stock.code.contains(q_lower))
            | (Stock.name.contains(q_original))
            | (Stock.name.contains(q_normalized)),
        )
        .limit(limit)
    )
    result = await db.execute(query)
    matched_stocks = list(result.scalars().all())

    # If we have enough results, return them
    if len(matched_stocks) >= limit:
        return matched_stocks[:limit]

    # If not enough results, try pinyin and first letter matching
    # Load only stocks that haven't been matched yet
    matched_codes = {stock.code for stock in matched_stocks}
    query = select(Stock).where(Stock.is_active, ~Stock.code.in_(matched_codes))
    result = await db.execute(query)
    remaining_stocks = result.scalars().all()

    for stock in remaining_stocks:
        if len(matched_stocks) >= limit:
            break

        # Match by pinyin
        if stock.name:
            stock_pinyin = get_pinyin(stock.name).lower()
            if q_lower in stock_pinyin:
                matched_stocks.append(stock)
                continue

            # Match by first letter
            stock_first_letter = get_first_letter(stock.name).lower()
            if q_lower in stock_first_letter:
                matched_stocks.append(stock)
                continue

    return matched_stocks[:limit]


@router.get("/{code}", response_model=StockResponse)
async def get_stock(
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get stock details."""
    stock = await db.get(Stock, code)
    if not stock:
        raise NotFoundException(f"Stock {code} not found")
    return stock


@router.get("/{code}/quotes", response_model=list[DailyQuoteResponse])
async def get_quotes(
    code: str,
    days: int = Query(default=120, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get daily quotes for a stock (fetch-on-demand: cache from akshare if DB lacks).

    解决"K线无数据"：DB 日K不足时按需从 akshare 拉取该股最近 `days` 个交易日
    并缓存到 daily_quotes，后续直接读 DB。首次访问即有K线，无需预跑采集。
    """
    from app.services.data.cache import ensure_daily_quotes

    await ensure_daily_quotes(db, code, days=days)
    await db.commit()

    result = await db.execute(
        select(DailyQuote)
        .where(DailyQuote.stock_code == code)
        .order_by(DailyQuote.date.desc())
        .limit(days)
    )
    quotes = result.scalars().all()
    return [
        DailyQuoteResponse(
            date=str(q.date),
            open=q.open,
            high=q.high,
            low=q.low,
            close=q.close,
            volume=q.volume,
            amount=q.amount,
            turnover_rate=q.turnover_rate,
        )
        for q in reversed(quotes)
    ]


@router.get("/{code}/financials")
async def get_financials(
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get financial reports for a stock (fetch-on-demand: cache periodic reports if DB lacks).

    解决"财报历史表无数据"：full_basic_collection 只存 'Latest' 快照；首次访问时
    按需从 akshare 拉取该股的周期财报（Q1/H1/Q3/Annual）并缓存到 financial_reports。
    """
    from app.services.data.cache import ensure_financial_reports

    await ensure_financial_reports(db, code)
    await db.commit()

    result = await db.execute(
        select(FinancialReport)
        .where(FinancialReport.stock_code == code)
        .order_by(FinancialReport.report_date.desc())
        .limit(20)
    )
    reports = result.scalars().all()
    return [
        {
            "report_date": str(r.report_date),
            "report_type": r.report_type,
            # All 20 market fields from Sina API
            "symbol": r.symbol,
            "price": r.price,
            "pricechange": r.pricechange,
            "changepercent": r.changepercent,
            "buy": r.buy,
            "sell": r.sell,
            "settlement": r.settlement,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "volume": r.volume,
            "amount": r.amount,
            "ticktime": r.ticktime,
            "per": r.per,
            "pb": r.pb,
            "mktcap": r.mktcap,
            "nmc": r.nmc,
            "turnoverratio": r.turnoverratio,
            # Legacy fields for backward compatibility
            "pe_ratio": r.pe_ratio,
            "pb_ratio": r.pb_ratio,
            "market_cap": r.market_cap,
            "circulating_market_cap": r.circulating_market_cap,
            # 财务报表数据
            "revenue": r.revenue,
            "net_profit": r.net_profit,
            "total_assets": r.total_assets,
            "total_equity": r.total_equity,
            "roe": r.roe,
            # 扩展财务指标
            "eps": r.eps,
            "bps": r.bps,
            "revenue_growth": r.revenue_growth,
            "net_profit_growth": r.net_profit_growth,
            "gross_margin": r.gross_margin,
            "net_margin": r.net_margin,
            "debt_ratio": r.debt_ratio,
            # 衍生指标
            "is_profitable": r.is_profitable,
        }
        for r in reports
    ]


@router.get("/{code}/indicators")
async def get_latest_indicators(
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the latest market indicators for a stock (from the most recent 'Latest' report)."""
    result = await db.execute(
        select(FinancialReport)
        .where(FinancialReport.stock_code == code, FinancialReport.report_type == "Latest")
        .order_by(FinancialReport.report_date.desc())
        .limit(1)
    )
    report = result.scalar_one_or_none()
    if not report:
        return {}

    return {
        "report_date": str(report.report_date),
        # All 20 market fields from Sina API
        "symbol": report.symbol,
        "price": report.price,
        "pricechange": report.pricechange,
        "changepercent": report.changepercent,
        "buy": report.buy,
        "sell": report.sell,
        "settlement": report.settlement,
        "open": report.open,
        "high": report.high,
        "low": report.low,
        "volume": report.volume,
        "amount": report.amount,
        "ticktime": report.ticktime,
        "per": report.per,
        "pb": report.pb,
        "mktcap": report.mktcap,
        "nmc": report.nmc,
        "turnoverratio": report.turnoverratio,
        # Legacy fields for backward compatibility
        "pe_ratio": report.pe_ratio,
        "pb_ratio": report.pb_ratio,
        "market_cap": report.market_cap,
        "circulating_market_cap": report.circulating_market_cap,
        # 衍生指标
        "is_profitable": report.is_profitable,
    }
