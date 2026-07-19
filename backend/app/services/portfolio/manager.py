"""Portfolio management service."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Portfolio, PortfolioItem
from app.models.stock import Stock

logger = logging.getLogger(__name__)


class PortfolioManager:
    """Portfolio CRUD and stock management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: int, name: str, description: str | None = None) -> Portfolio:
        portfolio = Portfolio(user_id=user_id, name=name, description=description)
        self.db.add(portfolio)
        await self.db.flush()
        await self.db.refresh(portfolio)
        return portfolio

    async def list_by_user(self, user_id: int) -> list[Portfolio]:
        result = await self.db.execute(
            select(Portfolio).where(Portfolio.user_id == user_id).order_by(Portfolio.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_detail(self, portfolio_id: int) -> dict:
        portfolio = await self.db.get(Portfolio, portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        items_result = await self.db.execute(
            select(PortfolioItem).where(PortfolioItem.portfolio_id == portfolio_id)
        )
        items = items_result.scalars().all()

        holdings = []
        for item in items:
            stock = await self.db.get(Stock, item.stock_code)
            holdings.append({
                "id": item.id,
                "stock_code": item.stock_code,
                "stock_name": stock.name if stock else "Unknown",
                "shares": item.shares,
                "avg_cost": item.avg_cost,
                "added_at": str(item.added_at),
            })

        return {
            "id": portfolio.id,
            "name": portfolio.name,
            "description": portfolio.description,
            "holdings": holdings,
            "created_at": str(portfolio.created_at),
            "updated_at": str(portfolio.updated_at),
        }

    async def add_stocks(self, portfolio_id: int, stock_codes: list[str], shares: float = 0, avg_cost: float = 0):
        for code in stock_codes:
            # Skip empty codes
            if not code or not code.strip():
                continue
            code = code.strip()
            existing = await self.db.execute(
                select(PortfolioItem).where(
                    PortfolioItem.portfolio_id == portfolio_id,
                    PortfolioItem.stock_code == code,
                )
            )
            if not existing.scalar_one_or_none():
                self.db.add(PortfolioItem(
                    portfolio_id=portfolio_id,
                    stock_code=code,
                    shares=shares,
                    avg_cost=avg_cost,
                ))
        await self.db.flush()

    async def remove_stock(self, portfolio_id: int, stock_code: str):
        result = await self.db.execute(
            select(PortfolioItem).where(
                PortfolioItem.portfolio_id == portfolio_id,
                PortfolioItem.stock_code == stock_code,
            )
        )
        item = result.scalar_one_or_none()
        if item:
            await self.db.delete(item)
            await self.db.flush()

    async def remove_stock_by_id(self, portfolio_id: int, item_id: int):
        """Remove a portfolio item by its ID (more reliable than by stock_code)."""
        result = await self.db.execute(
            select(PortfolioItem).where(
                PortfolioItem.id == item_id,
                PortfolioItem.portfolio_id == portfolio_id,
            )
        )
        item = result.scalar_one_or_none()
        if item:
            await self.db.delete(item)
            await self.db.flush()

    async def delete(self, portfolio_id: int):
        portfolio = await self.db.get(Portfolio, portfolio_id)
        if portfolio:
            await self.db.delete(portfolio)
            await self.db.flush()
