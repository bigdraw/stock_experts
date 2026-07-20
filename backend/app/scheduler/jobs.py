"""Scheduler jobs — 自动数据采集调度（后台自决策，不依赖用户触发）。

调度策略（idea2）：
- daily_data_update: 每日收盘后跑 full_basic_collection（Sina 批量快照，1 次调用
  覆盖全 A 股的 20 个行情字段 → 更新 Latest 行）。这是"行情每天增量更新"。
- monthly_financial_update: 每月底跑，对最新周期报告已过期（>100 天，新报告季
  到了）的股票重拉周期财报（ensure_financial_reports）。
- startup_check: 服务启动时比对当前时间与数据上次拉取时间，若 Latest 快照过期
  （>1 天）则后台触发一次 full_basic。后台 asyncio.create_task，不阻塞启动。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import func, select

from app.database import async_session_factory
from app.models.stock import FinancialReport, Stock
from app.services.data.akshare_provider import AkShareProvider
from app.services.data.cache import ensure_financial_reports
from app.services.data.engine import DataAcquisitionEngine

logger = logging.getLogger(__name__)


async def daily_data_update():
    """每日行情快照更新：Sina 批量拉全 A 股 20 字段 → upsert Latest。"""
    logger.info("Starting daily data update (full_basic_collection)...")
    try:
        async with async_session_factory() as db:
            provider = AkShareProvider()
            engine = DataAcquisitionEngine(provider, db)
            await engine.full_basic_collection(task_id="scheduled_daily")
            await db.commit()
        logger.info("Daily data update completed.")
    except Exception as e:
        logger.error(f"Daily data update failed: {e}", exc_info=True)


async def monthly_financial_update():
    """月度财报刷新：对最新周期报告已过期（>100 天）的股票重拉周期财报。

    ensure_financial_reports 内部已按"最新周期报告 <100 天则跳过"，所以遍历
    active stocks 调它即可——只拉到期的，不会重复拉本季已拉的。
    """
    logger.info("Starting monthly financial update...")
    try:
        async with async_session_factory() as db:
            result = await db.execute(select(Stock.code).where(Stock.is_active == True))  # noqa: E712
            codes = [r[0] for r in result.all()]
            provider = AkShareProvider()
            refreshed = 0
            for code in codes:
                try:
                    n = await ensure_financial_reports(db, code, provider=provider)
                    if n:
                        refreshed += 1
                        if refreshed % 50 == 0:
                            await db.commit()
                            logger.info(f"monthly financial: refreshed {refreshed}")
                except Exception as e:
                    logger.warning(f"financial refresh failed for {code}: {e}")
            await db.commit()
        logger.info(f"Monthly financial update completed: {refreshed} stocks refreshed.")
    except Exception as e:
        logger.error(f"Monthly financial update failed: {e}", exc_info=True)


async def alert_check():
    """Check all active alerts (placeholder)."""
    logger.info("Checking alerts...")


async def backup_reminder():
    """Weekly backup reminder."""
    logger.info("Backup reminder triggered.")


async def startup_check():
    """启动自决策：比对上次拉取时间，Latest 过期则后台触发 full_basic。"""
    try:
        async with async_session_factory() as db:
            # 最新 Latest 快照日期
            r = await db.execute(
                select(func.max(FinancialReport.report_date)).where(
                    FinancialReport.report_type == "Latest"
                )
            )
            latest = r.scalar_one_or_none()
        if latest is None or (date.today() - latest).days >= 1:
            logger.info(f"Latest snapshot stale (last={latest}), scheduling full_basic in background...")
            asyncio.create_task(daily_data_update())
        else:
            logger.info(f"Latest snapshot fresh ({latest}), no startup collection needed.")
    except Exception as e:
        logger.error(f"startup_check failed: {e}", exc_info=True)
