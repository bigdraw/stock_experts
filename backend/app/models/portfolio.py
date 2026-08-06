"""Portfolio models."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Cash balance for a future transaction-ledger portfolio (ISSUE-029).
    # Currently holdings still live on PortfolioItem; cash_balance is reserved
    # so a full ledger (buy/sell -> cash, holdings derived from txns) can land
    # without a migration later.
    cash_balance: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class PortfolioItem(Base):
    __tablename__ = "portfolio_items"
    __table_args__ = (UniqueConstraint("portfolio_id", "stock_code", name="uq_portfolio_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False)
    shares: Mapped[float] = mapped_column(Float, default=0)
    avg_cost: Mapped[float] = mapped_column(Float, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Transaction(Base):
    """Audit trail of portfolio buy/sell events (ISSUE-029).

    Foundation for a transaction-ledger portfolio. Currently only buys are
    recorded (by PortfolioManager.add_stocks); a full ledger — sells, cash
    movements, dividends, corporate-action adjustments, and holdings *derived*
    from transactions — is tracked as remaining work in ISSUES.md.
    """

    __tablename__ = "portfolio_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # buy / sell
    shares: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str | None] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
