"""Data acquisition API routes."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, require_admin
from app.database import async_session_factory, get_db
from app.models.user import User
from app.services.data.akshare_provider import AkShareProvider
from app.services.data.engine import DataAcquisitionEngine

router = APIRouter(prefix="/data", tags=["data"])


async def _run_full_collection(task_id: str):
    """Background task: full basic collection."""
    async with async_session_factory() as db:
        provider = AkShareProvider()
        engine = DataAcquisitionEngine(provider, db)
        await engine.full_basic_collection(task_id=task_id)


async def _run_incremental_update(task_id: str):
    """Background task: incremental update."""
    async with async_session_factory() as db:
        provider = AkShareProvider()
        engine = DataAcquisitionEngine(provider, db)
        await engine.incremental_update(task_id=task_id)


async def _run_deep_fetch(stock_codes: list[str], task_id: str):
    """Background task: deep data fetch."""
    async with async_session_factory() as db:
        provider = AkShareProvider()
        engine = DataAcquisitionEngine(provider, db)
        await engine.deep_data_on_demand(stock_codes, task_id=task_id)


async def _run_financial_update(task_id: str):
    """Background task: full financial data update."""
    async with async_session_factory() as db:
        provider = AkShareProvider()
        engine = DataAcquisitionEngine(provider, db)
        await engine.full_financial_update(task_id=task_id)


@router.post("/collect/full")
async def start_full_collection(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
):
    """Start full basic indicator collection (background task)."""
    task_id = f"full_{uuid.uuid4().hex[:8]}"
    background_tasks.add_task(_run_full_collection, task_id)
    return {"status": "started", "message": "Full collection started", "task_id": task_id}


@router.post("/collect/incremental")
async def start_incremental_update(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
):
    """Start incremental update (background task)."""
    task_id = f"incr_{uuid.uuid4().hex[:8]}"
    background_tasks.add_task(_run_incremental_update, task_id)
    return {"status": "started", "message": "Incremental update started", "task_id": task_id}


@router.post("/collect/deep")
async def start_deep_fetch(
    stock_codes: list[str],
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
):
    """Fetch deep data for specific stocks (background task)."""
    task_id = f"deep_{uuid.uuid4().hex[:8]}"
    background_tasks.add_task(_run_deep_fetch, stock_codes, task_id)
    return {
        "status": "started",
        "message": f"Deep fetch started for {len(stock_codes)} stocks",
        "task_id": task_id,
    }


@router.post("/collect/financial")
async def start_financial_update(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
):
    """Start full financial data update for all stocks (background task).

    This fetches comprehensive financial indicators including ROE, EPS, profit margins,
    growth rates, and other key financial ratios.
    """
    task_id = f"financial_{uuid.uuid4().hex[:8]}"
    background_tasks.add_task(_run_financial_update, task_id)
    return {"status": "started", "message": "Financial data update started", "task_id": task_id}


@router.get("/collect/status")
async def get_collection_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get recent data acquisition logs."""
    from sqlalchemy import select

    from app.models.system import DataAcquisitionLog

    result = await db.execute(
        select(DataAcquisitionLog).order_by(DataAcquisitionLog.started_at.desc()).limit(10)
    )
    logs = result.scalars().all()
    return [
        {
            "id": log.id,
            "task_type": log.task_type,
            "status": log.status,
            "started_at": str(log.started_at) if log.started_at else None,
            "completed_at": str(log.completed_at) if log.completed_at else None,
            "stocks_processed": log.stocks_processed,
            "error_message": log.error_message,
        }
        for log in logs
    ]
