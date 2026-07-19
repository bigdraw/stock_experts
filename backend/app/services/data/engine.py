"""Data acquisition engine with dual-layer self-healing and task management."""

import asyncio
import json
import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import DailyQuote as DailyQuoteModel
from app.models.stock import FinancialReport as FinancialReportModel
from app.models.stock import Stock
from app.models.system import DataAcquisitionLog
from app.services.data.provider import DataProvider
from app.services.task_manager import task_manager, TaskStatus

logger = logging.getLogger(__name__)


class DataAcquisitionEngine:
    """Orchestrates data collection with self-healing and progress tracking."""

    def __init__(self, provider: DataProvider, db: AsyncSession):
        self.provider = provider
        self.db = db

    async def full_basic_collection(self, batch_size: int = 100, task_id: str = None) -> str:
        """Full collection of basic indicators. Fetches all data in one API call, then batches DB writes."""
        if task_id is None:
            task_id = f"full_basic_{uuid.uuid4().hex[:8]}"
        task_manager.create_task(task_id, "full_basic", total=0)
        task_manager.update_progress(task_id, message="Initializing...")

        log = DataAcquisitionLog(
            task_type="full_basic",
            status="running",
            started_at=datetime.now(),
        )
        self.db.add(log)
        await self.db.flush()

        try:
            # 1. Get stock list
            task_manager.update_progress(task_id, message="Fetching stock list...")
            stocks = await self.provider.get_stock_list()
            total = len(stocks)
            
            # Update task with total count
            task = task_manager.get_task(task_id)
            if task:
                task.total = total
            task_manager.update_progress(task_id, message=f"Found {total} stocks")
            logger.info(f"Found {total} stocks")

            # 2. Upsert stocks
            task_manager.update_progress(task_id, message="Updating stock list in database...")
            for stock_data in stocks:
                existing = await self.db.get(Stock, stock_data.code)
                if existing:
                    existing.name = stock_data.name
                    existing.market = stock_data.market
                    existing.industry = stock_data.industry
                    existing.updated_at = datetime.now()
                else:
                    self.db.add(Stock(
                        code=stock_data.code,
                        name=stock_data.name,
                        market=stock_data.market,
                        industry=stock_data.industry,
                        is_active=True,
                        updated_at=datetime.now(),
                    ))
            await self.db.flush()

            # 3. Fetch ALL indicators in one API call (Sina API)
            task_manager.update_progress(task_id, message="Fetching all indicators from data source...")
            all_indicators = await self.provider.get_all_basic_indicators()
            
            if not all_indicators:
                raise Exception("Failed to fetch indicators from data source")
            
            logger.info(f"Fetched {len(all_indicators)} indicators")

            # 4. Batch write indicators to database
            processed = 0
            total_indicators = len(all_indicators)
            
            for i in range(0, total_indicators, batch_size):
                # Check for pause/stop
                if not task_manager.wait_if_paused(task_id):
                    task_manager.stop_task(task_id)
                    log.status = "stopped"
                    log.stocks_processed = processed
                    log.completed_at = datetime.now()
                    await self.db.commit()
                    logger.info(f"Full collection stopped by user: {processed}/{total_indicators} stocks")
                    return task_id

                batch = all_indicators[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (total_indicators + batch_size - 1) // batch_size
                
                task_manager.update_progress(
                    task_id,
                    current=processed,
                    message=f"Writing batch {batch_num}/{total_batches} to database ({processed}/{total_indicators})",
                )

                for ind in batch:
                    report = FinancialReportModel(
                        stock_code=ind.code,
                        report_date=datetime.now().date(),
                        report_type="Latest",
                        market_cap=ind.market_cap,
                        pe_ratio=ind.pe_ratio,
                        pb_ratio=ind.pb_ratio,
                        is_profitable=ind.is_profitable,
                    )
                    self.db.add(report)
                
                processed += len(batch)
                log.stocks_processed = processed
                await self.db.flush()
                logger.info(f"Processed {processed}/{total_indicators} stocks")

            task_manager.complete_task(task_id, f"Completed: {processed}/{total_indicators} stocks")
            log.status = "success"
            log.completed_at = datetime.now()
            log.details = json.dumps({"total_stocks": total_indicators, "processed": processed})
            await self.db.commit()
            logger.info(f"Full collection completed: {processed}/{total_indicators} stocks")
            return task_id

        except Exception as e:
            task_manager.fail_task(task_id, str(e))
            log.status = "failed"
            log.error_message = str(e)
            log.completed_at = datetime.now()
            await self.db.commit()
            logger.error(f"Full collection failed: {e}")
            raise

    async def incremental_update(self, task_id: str = None) -> str:
        """Daily incremental update: today's quotes + basic indicators. Returns task_id."""
        if task_id is None:
            task_id = f"incremental_{uuid.uuid4().hex[:8]}"
        task_manager.create_task(task_id, "incremental", total=0)
        task_manager.update_progress(task_id, message="Initializing...")

        log = DataAcquisitionLog(
            task_type="incremental",
            status="running",
            started_at=datetime.now(),
        )
        self.db.add(log)
        await self.db.flush()

        try:
            # Get all active stocks
            task_manager.update_progress(task_id, message="Loading stock list...")
            result = await self.db.execute(select(Stock).where(Stock.is_active == True))
            stocks = result.scalars().all()
            total = len(stocks)
            
            task = task_manager.get_task(task_id)
            if task:
                task.total = total
            
            today = datetime.now().strftime("%Y-%m-%d")
            task_manager.update_progress(task_id, message=f"Updating {total} stocks for {today}...")

            processed = 0
            for stock in stocks:
                # Check for pause/stop
                if not task_manager.wait_if_paused(task_id):
                    task_manager.stop_task(task_id)
                    log.status = "stopped"
                    log.stocks_processed = processed
                    log.completed_at = datetime.now()
                    await self.db.commit()
                    logger.info(f"Incremental update stopped: {processed}/{total}")
                    return task_id

                task_manager.update_progress(
                    task_id,
                    current=processed,
                    message=f"Updating {stock.code} ({stock.name}) - {processed}/{total}",
                )

                try:
                    # Fetch today's quote
                    quotes = await self.provider.get_daily_quotes(stock.code, today, today)
                    for q in quotes:
                        existing = await self.db.execute(
                            select(DailyQuoteModel).where(
                                DailyQuoteModel.stock_code == q.code,
                                DailyQuoteModel.date == datetime.strptime(q.date, "%Y-%m-%d").date(),
                            )
                        )
                        if not existing.scalar_one_or_none():
                            self.db.add(DailyQuoteModel(
                                stock_code=q.code,
                                date=datetime.strptime(q.date, "%Y-%m-%d").date(),
                                open=q.open,
                                high=q.high,
                                low=q.low,
                                close=q.close,
                                volume=q.volume,
                                amount=q.amount,
                                turnover_rate=q.turnover_rate,
                            ))
                    processed += 1
                    if processed % 100 == 0:
                        await self.db.flush()
                        logger.info(f"Incremental update: {processed}/{total}")
                except Exception as e:
                    logger.warning(f"Failed to update {stock.code}: {e}")
                    continue

            task_manager.complete_task(task_id, f"Completed: {processed}/{total} stocks")
            log.status = "success"
            log.stocks_processed = processed
            log.completed_at = datetime.now()
            await self.db.commit()
            logger.info(f"Incremental update completed: {processed} stocks")
            return task_id

        except Exception as e:
            task_manager.fail_task(task_id, str(e))
            log.status = "failed"
            log.error_message = str(e)
            log.completed_at = datetime.now()
            await self.db.commit()
            logger.error(f"Incremental update failed: {e}")
            raise

    async def deep_data_on_demand(self, stock_codes: list[str], task_id: str = None) -> str:
        """Fetch deep data (financial reports) for specific stocks. Returns task_id."""
        if task_id is None:
            task_id = f"deep_{uuid.uuid4().hex[:8]}"
        total = len(stock_codes)
        task_manager.create_task(task_id, "deep", total=total)
        task_manager.update_progress(task_id, message=f"Fetching deep data for {total} stocks...")

        log = DataAcquisitionLog(
            task_type="deep",
            status="running",
            started_at=datetime.now(),
        )
        self.db.add(log)
        await self.db.flush()

        try:
            processed = 0
            for code in stock_codes:
                # Check for pause/stop
                if not task_manager.wait_if_paused(task_id):
                    task_manager.stop_task(task_id)
                    log.status = "stopped"
                    log.stocks_processed = processed
                    log.completed_at = datetime.now()
                    await self.db.commit()
                    logger.info(f"Deep data fetch stopped: {processed}/{total}")
                    return task_id

                task_manager.update_progress(
                    task_id,
                    current=processed,
                    message=f"Fetching financial reports for {code} ({processed}/{total})",
                )

                try:
                    reports = await self.provider.get_financial_reports(code)
                    for r in reports:
                        self.db.add(FinancialReportModel(
                            stock_code=r.code,
                            report_date=datetime.strptime(r.report_date, "%Y-%m-%d").date() if r.report_date else datetime.now().date(),
                            report_type=r.report_type,
                            revenue=r.revenue,
                            net_profit=r.net_profit,
                            roe=r.roe,
                            pe_ratio=r.pe_ratio,
                            pb_ratio=r.pb_ratio,
                            market_cap=r.market_cap,
                            raw_data=json.dumps(r.raw_data) if r.raw_data else None,
                        ))
                    processed += 1
                    await self.db.flush()
                except Exception as e:
                    logger.warning(f"Failed to fetch deep data for {code}: {e}")
                    continue

            task_manager.complete_task(task_id, f"Completed: {processed}/{total} stocks")
            log.status = "success"
            log.stocks_processed = processed
            log.completed_at = datetime.now()
            await self.db.commit()
            logger.info(f"Deep data fetch completed: {processed} stocks")
            return task_id

        except Exception as e:
            task_manager.fail_task(task_id, str(e))
            log.status = "failed"
            log.error_message = str(e)
            log.completed_at = datetime.now()
            await self.db.commit()
            logger.error(f"Deep data fetch failed: {e}")
            raise
