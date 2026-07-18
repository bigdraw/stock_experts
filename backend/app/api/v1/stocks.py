"""Stock API routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.database import get_db
from app.models.stock import DailyQuote, FinancialReport, Stock
from app.models.user import User
from app.schemas import DailyQuoteResponse, StockResponse
from app.utils.exceptions import NotFoundException

router = APIRouter(prefix="/stocks", tags=["stocks"])


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
            "roe": r.roe,
            "pe_ratio": r.pe_ratio,
            "pb_ratio": r.pb_ratio,
            "market_cap": r.market_cap,
            "is_profitable": r.is_profitable,
        }
        for r in reports
    ]
