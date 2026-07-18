"""Portfolio API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas import PortfolioCreateRequest, PortfolioItemAddRequest, PortfolioResponse
from app.services.portfolio.manager import PortfolioManager
from app.utils.exceptions import NotFoundException

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.post("", response_model=PortfolioResponse)
async def create_portfolio(
    req: PortfolioCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mgr = PortfolioManager(db)
    return await mgr.create(current_user.id, req.name, req.description)


@router.get("", response_model=list[PortfolioResponse])
async def list_portfolios(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mgr = PortfolioManager(db)
    return await mgr.list_by_user(current_user.id)


@router.get("/{portfolio_id}")
async def get_portfolio(
    portfolio_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mgr = PortfolioManager(db)
    try:
        return await mgr.get_detail(portfolio_id)
    except ValueError as e:
        raise NotFoundException(str(e))


@router.post("/{portfolio_id}/items")
async def add_stocks(
    portfolio_id: int,
    req: PortfolioItemAddRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mgr = PortfolioManager(db)
    await mgr.add_stocks(portfolio_id, [req.stock_code], req.shares, req.avg_cost)
    return {"status": "added"}


@router.post("/{portfolio_id}/items/filter")
async def add_by_filter(
    portfolio_id: int,
    filter_id: int,
    params: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add stocks to portfolio using a filter script."""
    from app.services.filter.registry import FilterRegistry
    from app.services.llm.manager import llm_manager

    registry = FilterRegistry(db, llm_manager.get())
    result_df = await registry.execute(filter_id, params)
    codes = result_df["code"].tolist()

    mgr = PortfolioManager(db)
    await mgr.add_stocks(portfolio_id, codes)
    return {"status": "added", "count": len(codes)}


@router.delete("/{portfolio_id}/items/{stock_code}")
async def remove_stock(
    portfolio_id: int,
    stock_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mgr = PortfolioManager(db)
    await mgr.remove_stock(portfolio_id, stock_code)
    return {"status": "removed"}


@router.delete("/{portfolio_id}")
async def delete_portfolio(
    portfolio_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mgr = PortfolioManager(db)
    await mgr.delete(portfolio_id)
    return {"status": "deleted"}
