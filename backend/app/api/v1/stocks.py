"""Stock API routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pypinyin import pinyin, Style
from sqlalchemy import select, func
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
    query = select(func.count()).select_from(Stock).where(Stock.is_active == True)
    if market:
        query = query.where(Stock.market == market)
    result = await db.execute(query)
    count = result.scalar()
    return {"count": count}


@router.get("", response_model=list[StockResponse])
async def list_stocks(
    market: str | None = None,
    search: str | None = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List stocks with optional filtering."""
    query = select(Stock).where(Stock.is_active == True)
    if market:
        query = query.where(Stock.market == market)
    if search:
        query = query.where(Stock.name.contains(search) | Stock.code.contains(search))
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/search", response_model=list[StockResponse])
async def search_stocks(
    q: str = Query(..., min_length=1, description="Search query (code, name, pinyin, or first letter)"),
    limit: int = Query(default=100, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search stocks by code, name, pinyin, or first letter."""
    q_lower = q.lower()
    
    # First, try database filtering by code and name (fast)
    query = select(Stock).where(
        Stock.is_active == True,
        (Stock.code.contains(q_lower)) | (Stock.name.contains(q))
    ).limit(limit)
    result = await db.execute(query)
    matched_stocks = list(result.scalars().all())
    
    # If we have enough results, return them
    if len(matched_stocks) >= limit:
        return matched_stocks[:limit]
    
    # If not enough results, try pinyin and first letter matching
    # Load only stocks that haven't been matched yet
    matched_codes = {stock.code for stock in matched_stocks}
    query = select(Stock).where(
        Stock.is_active == True,
        ~Stock.code.in_(matched_codes)
    )
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
    """Get daily quotes for a stock."""
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
    """Get financial reports for a stock."""
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
            "revenue": r.revenue,
            "net_profit": r.net_profit,
            "total_assets": r.total_assets,
            "total_equity": r.total_equity,
            "roe": r.roe,
            "pe_ratio": r.pe_ratio,
            "pb_ratio": r.pb_ratio,
            "market_cap": r.market_cap,
            "is_profitable": r.is_profitable,
        }
        for r in reports
    ]
