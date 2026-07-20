"""Backtest strategy and result models."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BacktestStrategy(Base):
    __tablename__ = "backtest_strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    nl_description: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_code: Mapped[str] = mapped_column(Text, nullable=False)
    friction_config: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    parameters: Mapped[str | None] = mapped_column(Text)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("backtest_strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_params: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    total_return: Mapped[float | None] = mapped_column(Float)
    annualized_return: Mapped[float | None] = mapped_column(Float)
    max_drawdown: Mapped[float | None] = mapped_column(Float)
    sharpe_ratio: Mapped[float | None] = mapped_column(Float)
    win_rate: Mapped[float | None] = mapped_column(Float)
    total_trades: Mapped[int | None] = mapped_column(Integer)
    final_capital: Mapped[float | None] = mapped_column(Float)
    equity_curve: Mapped[str | None] = mapped_column(Text)  # JSON array
    trade_log: Mapped[str | None] = mapped_column(Text)  # JSON array
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
