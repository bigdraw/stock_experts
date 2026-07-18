"""Data acquisition API routes."""

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.database import async_session_factory, get_db
from app.models.user import User
from app.services.data.akshare_provider import AkShareProvider
from app.services.data.engine import DataAcquisitionEngine

router = APIRouter(prefix="/data", tags=["data"])


async def _run_full_collection():
    """Background task: full basic collection."""
    async with async_session_factory() as db:
        provider = AkShareProvider()
        engine = DataAcquisitionEngine(provider, db)
        await engine.full_basic_collection()


async def _run_incremental_update():
    """Background task: incremental update."""
    async with async_session_factory() as db:
        provider = AkShareProvider()
        engine = DataAcquisitionEngine(provider, db)
        await engine.incremental_update()


async def _run_deep_fetch(stock_codes: list[str]):
    """Background task: deep data fetch."""
    async with async_session_factory() as db:
        provider = AkShareProvider()
        engine = DataAcquisitionEngine(provider, db)
        await engine.deep_data_on_demand(stock_codes)


@router.post("/collect/full")
async def start_full_collection(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Start full basic indicator collection (background task)."""
    background_tasks.add_task(_run_full_collection)
    return {"status": "started", "message": "Full collection started in background"}


@router.post("/collect/incremental")
async def start_incremental_update(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Start incremental update (background task)."""
    background_tasks.add_task(_run_incremental_update)
    return {"status": "started", "message": "Incremental update started in background"}


@router.post("/collect/deep")
async def start_deep_fetch(
    stock_codes: list[str],
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Fetch deep data for specific stocks (background task)."""
    background_tasks.add_task(_run_deep_fetch, stock_codes)
    return {"status": "started", "message": f"Deep fetch started for {len(stock_codes)} stocks"}


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
