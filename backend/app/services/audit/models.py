"""DecisionLog 审计 ORM（移植自 maverick-mcp，MIT License Copyright (c) 2024）。

源：`maverick_mcp/data.models.DecisionLog`。本平台 async 栈，挂在 `app.database.Base`。
用途：记录每次 agent 路由/LLM 调用的决策与成本，永不阻塞主流程。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DecisionLog(Base):
    """单条 agent 决策/成本审计行。"""

    __tablename__ = "decision_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
    session_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    routing_decision: Mapped[list | None] = mapped_column(JSON, nullable=True)
    models_used: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tokens_input: Mapped[int] = mapped_column(Integer, default=0)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    confidence_score: Mapped[float] = mapped_column(Numeric(6, 4), default=0)
    response_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="success")
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
