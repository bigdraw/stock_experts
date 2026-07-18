"""Scheduler jobs for periodic tasks."""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


async def daily_data_update():
    """Daily stock data update (triggered after market close)."""
    logger.info(f"[{datetime.now()}] Starting daily data update...")
    # Will be implemented in T-008b
    logger.info("Daily data update completed.")


async def alert_check():
    """Check all active alerts."""
    logger.info(f"[{datetime.now()}] Checking alerts...")
    # Will be implemented in T-014
    logger.info("Alert check completed.")


async def backup_reminder():
    """Weekly backup reminder."""
    logger.info(f"[{datetime.now()}] Backup reminder triggered.")
    # Will be implemented in T-014
