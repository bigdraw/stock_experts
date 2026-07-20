"""交易日志 ORM 模型（移植自 maverick-mcp，MIT License Copyright (c) 2024）。

源文件：`maverick_mcp/services/journal/models.py`。
适配点：原版基于 maverick 的同步 `Base` + `TimestampMixin`；本平台用 async 栈
（`app.database.Base`），时间戳内联为 `created_at`/`updated_at`（与 User 模型一致）。
字段语义（symbol/side/entry/exit/shares/tags/pnl/r_multiple/status）逐字保留。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class JournalEntry(Base):
    """单笔交易记录（开仓或已平仓）。tag 化便于策略聚合。"""

    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # "long" | "short"
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares: Mapped[float] = mapped_column(Float, nullable=False)
    entry_date: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    exit_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    r_multiple: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class StrategyPerformance(Base):
    """某 strategy_tag 的聚合表现：胜率/期望/盈亏比。"""

    __tablename__ = "strategy_performance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_tag: Mapped[str] = mapped_column(String(100), nullable=False, index=True, unique=True)
    period: Mapped[str] = mapped_column(String(20), nullable=False, default="all_time")
    win_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    loss_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_win: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_loss: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    expectancy: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    profit_factor: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
