"""FastAPI application entry point."""

import logging
import sys
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.api.admin import router as admin_router
from app.config import settings
from app.database import init_db
from app.scheduler.jobs import alert_check, backup_reminder, daily_data_update
from app.services.llm.manager import llm_manager

# Force UTF-8 encoding for stdout/stderr to fix Chinese character display issues
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    # Startup
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized.")

    # Initialize proxy cache
    from app.services.data.akshare_provider import get_proxy_enabled
    proxy_enabled = await get_proxy_enabled()
    logger.info(f"Proxy cache initialized: proxy_enabled={proxy_enabled}")

    # Initialize LLM providers
    logger.info("Initializing LLM providers...")
    await llm_manager.init_from_config()
    logger.info(f"LLM providers ready: {llm_manager.list_providers()}")

    # Start scheduler
    _hour, _minute = map(int, settings.scheduler.daily_update_time.split(":"))
    scheduler.add_job(daily_data_update, "cron", hour=_hour, minute=_minute, id="daily_data_update")
    scheduler.add_job(alert_check, "interval", minutes=30, id="alert_check")
    scheduler.add_job(backup_reminder, "cron", day_of_week=settings.scheduler.backup_day[:3], hour=9, id="backup_reminder")
    scheduler.start()
    logger.info("Scheduler started.")

    yield

    # Shutdown
    scheduler.shutdown(wait=False)
    await llm_manager.close_all()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Stock Analysis Platform",
    description="A股分析平台后端 API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(api_router)
app.include_router(admin_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
