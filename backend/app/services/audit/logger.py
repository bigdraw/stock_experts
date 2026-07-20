"""async DecisionLogger（移植自 maverick-mcp，MIT License Copyright (c) 2024）。

源：`maverick_mcp/utils/decision_logger.py`。适配：同步 SessionLocal → 本平台
`async_session_factory` + `select`。**核心保证保留**：所有方法捕获全部异常，
审计写入永不阻塞/崩溃主流程（agent 工作流不被审计拖垮）。
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.database import async_session_factory
from app.services.audit.models import DecisionLog

logger = logging.getLogger("app.services.audit.logger")


class DecisionLogger:
    """async-safe 决策审计写入器。每个方法都不抛异常。"""

    @staticmethod
    async def log_decision(
        *,
        session_id: str | None = None,
        request_id: str | None = None,
        query_text: str | None = None,
        query_classification: str | None = None,
        routing_decision: list[str] | None = None,
        models_used: list[str] | None = None,
        tokens_input: int = 0,
        tokens_output: int = 0,
        estimated_cost_usd: float = 0.0,
        confidence_score: float = 0.0,
        response_summary: str | None = None,
        duration_ms: int = 0,
        status: str = "success",
        error_category: str | None = None,
    ) -> None:
        """写一条决策记录到 DB。永不抛异常。"""
        try:
            if response_summary and len(response_summary) > 500:
                response_summary = response_summary[:497] + "..."

            record = DecisionLog(
                timestamp=datetime.now(UTC),
                session_id=session_id,
                request_id=request_id or str(uuid.uuid4())[:8],
                query_text=query_text,
                query_classification=query_classification,
                routing_decision=routing_decision,
                models_used=models_used,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                estimated_cost_usd=Decimal(str(estimated_cost_usd)),
                confidence_score=Decimal(str(confidence_score)),
                response_summary=response_summary,
                duration_ms=duration_ms,
                status=status,
                error_category=error_category,
            )
            async with async_session_factory() as db:
                db.add(record)
                await db.commit()

            logger.debug(
                "Decision logged: classification=%s, status=%s, duration=%dms",
                query_classification,
                status,
                duration_ms,
            )
        except SQLAlchemyError:
            logger.warning("Failed to write decision log to database", exc_info=True)
        except Exception:
            logger.warning("Unexpected error in decision logger", exc_info=True)

    @staticmethod
    async def get_decisions(session_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """取最近决策记录。失败返回 []。"""
        try:
            async with async_session_factory() as db:
                stmt = select(DecisionLog).order_by(DecisionLog.timestamp.desc()).limit(limit)
                if session_id:
                    stmt = (
                        select(DecisionLog)
                        .where(DecisionLog.session_id == session_id)
                        .order_by(DecisionLog.timestamp.desc())
                        .limit(limit)
                    )
                rows = (await db.execute(stmt)).scalars().all()
                return [_row_to_dict(r) for r in rows]
        except Exception:
            logger.warning("Failed to read decision log", exc_info=True)
            return []

    @staticmethod
    async def get_cost_summary(days: int = 7) -> dict[str, Any]:
        """聚合最近 days 天的成本与用量统计。失败返回 {error}。"""
        try:
            cutoff = datetime.now(UTC) - timedelta(days=days)
            async with async_session_factory() as db:
                stmt = select(
                    func.count(DecisionLog.id).label("total_requests"),
                    func.sum(DecisionLog.tokens_input).label("total_tokens_input"),
                    func.sum(DecisionLog.tokens_output).label("total_tokens_output"),
                    func.sum(DecisionLog.estimated_cost_usd).label("total_cost_usd"),
                    func.avg(DecisionLog.duration_ms).label("avg_duration_ms"),
                ).where(DecisionLog.timestamp >= cutoff)
                row = (await db.execute(stmt)).one()

                status_stmt = (
                    select(DecisionLog.status, func.count(DecisionLog.id))
                    .where(DecisionLog.timestamp >= cutoff)
                    .group_by(DecisionLog.status)
                )
                status_breakdown = {s: c for s, c in (await db.execute(status_stmt)).all()}

                class_stmt = (
                    select(DecisionLog.query_classification, func.count(DecisionLog.id))
                    .where(
                        DecisionLog.timestamp >= cutoff,
                        DecisionLog.query_classification.is_not(None),
                    )
                    .group_by(DecisionLog.query_classification)
                )
                classification_breakdown = {c: n for c, n in (await db.execute(class_stmt)).all()}

            return {
                "period_days": days,
                "total_requests": row.total_requests or 0,
                "total_tokens_input": int(row.total_tokens_input or 0),
                "total_tokens_output": int(row.total_tokens_output or 0),
                "total_cost_usd": float(row.total_cost_usd or 0),
                "avg_duration_ms": float(row.avg_duration_ms or 0),
                "status_breakdown": status_breakdown,
                "classification_breakdown": classification_breakdown,
            }
        except Exception:
            logger.warning("Failed to compute cost summary", exc_info=True)
            return {"error": "Failed to compute cost summary", "period_days": days}


def _row_to_dict(r: DecisionLog) -> dict[str, Any]:
    """把 DecisionLog 行转 dict（Decimal → float 便于 JSON）。"""
    return {
        "id": r.id,
        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        "session_id": r.session_id,
        "request_id": r.request_id,
        "query_classification": r.query_classification,
        "models_used": r.models_used,
        "tokens_input": r.tokens_input,
        "tokens_output": r.tokens_output,
        "estimated_cost_usd": float(r.estimated_cost_usd)
        if r.estimated_cost_usd is not None
        else 0.0,
        "confidence_score": float(r.confidence_score) if r.confidence_score is not None else 0.0,
        "response_summary": r.response_summary,
        "duration_ms": r.duration_ms,
        "status": r.status,
        "error_category": r.error_category,
    }


# 模块级单例
decision_logger = DecisionLogger()
