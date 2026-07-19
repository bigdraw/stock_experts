"""Data acquisition engine with dual-layer self-healing and task management."""

import asyncio
import json
import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.stock import DailyQuote as DailyQuoteModel
from app.models.stock import FinancialReport as FinancialReportModel
from app.models.stock import Stock
from app.models.system import DataAcquisitionLog
from app.services.data.provider import DataProvider
from app.services.data.validator import IndicatorValidator
from app.services.task_manager import task_manager, TaskStatus

logger = logging.getLogger(__name__)


class DataAcquisitionEngine:
    """Orchestrates data collection with self-healing and task management."""

    # Default stock code prefixes to collect. Covers main board (600/601/603/605),
    # SZ main + SME (000/001/002/003), ChiNext (300) and STAR/科创板 (688).
    # Note: 北交所 (920-prefix) is NOT served by Sina's 'hs_a' node and needs a
    # separate 'bj_a' fetch — currently a known gap; those rows stay null.
    DEFAULT_CODE_PREFIXES = ['000', '001', '002', '003', '300', '600', '601', '603', '605', '688']

    def __init__(self, provider: DataProvider, db: AsyncSession):
        self.provider = provider
        self.db = db

    async def _persist_log_outcome(self, log_id: int | None, status: str,
                                   error_message: str | None = None,
                                   stocks_processed: int | None = None,
                                   details: dict | None = None) -> None:
        """Persist a log row's terminal status in a FRESH session.

        The work session may be rolled back on failure, which would also roll
        back the in-flight log row (it was only flushed, not committed). To
        guarantee the failure/stop status survives, we open an independent
        session, reload the row by id, and commit the terminal state there.
        This replaces the previous (broken) pattern of
        ``await db.rollback(); await db.commit()`` which committed an empty
        transaction and silently dropped the failure log.
        """
        if log_id is None:
            return
        try:
            async with async_session_factory() as s2:
                log2 = await s2.get(DataAcquisitionLog, log_id)
                if log2 is None:
                    return
                log2.status = status
                if error_message is not None:
                    log2.error_message = error_message
                if stocks_processed is not None:
                    log2.stocks_processed = stocks_processed
                if details is not None:
                    log2.details = json.dumps(details)
                log2.completed_at = datetime.now()
                await s2.commit()
        except Exception as e:
            logger.error(f"Failed to persist log outcome (id={log_id}): {e}")

    @staticmethod
    def _apply_indicator(report: FinancialReportModel, ind) -> None:
        """Copy all 20 market + legacy fields from a StockBasicIndicators onto a
        FinancialReportModel row. Single source for the field mapping so update
        and insert paths can't drift apart."""
        report.symbol = ind.symbol
        report.price = ind.price
        report.pricechange = ind.pricechange
        report.changepercent = ind.changepercent
        report.buy = ind.buy
        report.sell = ind.sell
        report.settlement = ind.settlement
        report.open = ind.open
        report.high = ind.high
        report.low = ind.low
        report.volume = ind.volume
        report.amount = ind.amount
        report.ticktime = ind.ticktime
        report.per = ind.per
        report.pb = ind.pb
        report.mktcap = ind.mktcap
        report.nmc = ind.nmc
        report.turnoverratio = ind.turnoverratio
        # Legacy / derived aliases
        report.pe_ratio = ind.pe_ratio
        report.pb_ratio = ind.pb_ratio
        report.market_cap = ind.market_cap
        report.circulating_market_cap = ind.circulating_market_cap
        report.is_profitable = ind.is_profitable

    async def full_basic_collection(self, batch_size: int = 100, task_id: str = None, code_prefixes: list[str] = None) -> str:
        """Full collection of basic indicators. Fetches all data in one API call, then batches DB writes.
        
        Args:
            batch_size: Number of stocks to process per batch
            task_id: Optional task ID for progress tracking
            code_prefixes: List of code prefixes to filter (e.g., ['000', '600', '300']).
                          If None, uses DEFAULT_CODE_PREFIXES.
        """
        if task_id is None:
            task_id = f"full_basic_{uuid.uuid4().hex[:8]}"
        
        # Use default prefixes if not specified
        if code_prefixes is None:
            code_prefixes = self.DEFAULT_CODE_PREFIXES
        
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
            task_manager.update_progress(task_id, message=f"Fetching indicators for {code_prefixes} stocks...")
            all_indicators = await self.provider.get_all_basic_indicators(code_prefixes=code_prefixes)
            
            if not all_indicators:
                raise Exception("Failed to fetch indicators from data source")
            
            logger.info(f"Fetched {len(all_indicators)} indicators")

            # 4. Validate and batch write indicators to database
            processed = 0
            total_indicators = len(all_indicators)
            
            # Validate all indicators first
            task_manager.update_progress(task_id, message="Validating data...")
            validation_summary = IndicatorValidator.validate_batch(all_indicators)
            logger.info(f"Validation complete: {validation_summary}")
            
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

                # Pre-fetch all existing 'Latest' reports for this batch in ONE
                # query (keyed by stock_code) instead of one query per stock —
                # this is the N+1 fix (batch_size=100 → ~50 queries for 5000
                # stocks instead of 5000).
                today = datetime.now().date()
                batch_codes = [ind.code for ind in batch]
                existing_res = await self.db.execute(
                    select(FinancialReportModel).where(
                        FinancialReportModel.stock_code.in_(batch_codes),
                        FinancialReportModel.report_date == today,
                        FinancialReportModel.report_type == "Latest",
                    )
                )
                existing_by_code = {r.stock_code: r for r in existing_res.scalars().all()}

                for ind in batch:
                    # Validate individual indicator
                    validation_result = IndicatorValidator.validate(ind)
                    if not validation_result.is_valid:
                        logger.warning(f"Skipping invalid data for {ind.code}: {validation_result.errors}")
                        continue  # Skip invalid data

                    report = existing_by_code.get(ind.code)
                    if report is None:
                        report = FinancialReportModel(
                            stock_code=ind.code,
                            report_date=today,
                            report_type="Latest",
                        )
                        self.db.add(report)
                        existing_by_code[ind.code] = report  # dedupe within batch
                    self._apply_indicator(report, ind)

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
            await self.db.rollback()
            await self._persist_log_outcome(
                log.id, "failed", error_message=str(e),
                stocks_processed=locals().get("processed", 0),
            )
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
            await self.db.rollback()
            await self._persist_log_outcome(
                log.id, "failed", error_message=str(e),
                stocks_processed=locals().get("processed", 0),
            )
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
                        report_date = datetime.strptime(r.report_date, "%Y-%m-%d").date() if r.report_date else datetime.now().date()
                        
                        # Check if record already exists
                        existing = await self.db.execute(
                            select(FinancialReportModel).where(
                                FinancialReportModel.stock_code == r.code,
                                FinancialReportModel.report_date == report_date
                            )
                        )
                        report = existing.scalar_one_or_none()
                        
                        if report:
                            # Update existing record
                            report.report_type = r.report_type
                            report.revenue = r.revenue
                            report.net_profit = r.net_profit
                            report.roe = r.roe
                            report.pe_ratio = r.pe_ratio
                            report.pb_ratio = r.pb_ratio
                            report.market_cap = r.market_cap
                            report.raw_data = json.dumps(r.raw_data) if r.raw_data else None
                        else:
                            # Insert new record
                            self.db.add(FinancialReportModel(
                                stock_code=r.code,
                                report_date=report_date,
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
            await self.db.rollback()
            await self._persist_log_outcome(
                log.id, "failed", error_message=str(e),
                stocks_processed=locals().get("processed", 0),
            )
            logger.error(f"Deep data fetch failed: {e}")
            raise

    async def full_financial_update(self, task_id: str = None) -> str:
        """Full update of financial analysis indicators for all stocks.
        
        This method fetches comprehensive financial data including ROE, EPS, profit margins,
        growth rates, and other key financial ratios for all active stocks.
        
        Args:
            task_id: Optional task ID for progress tracking
        
        Returns:
            task_id: The task ID for tracking progress
        """
        if task_id is None:
            task_id = f"financial_{uuid.uuid4().hex[:8]}"
        
        task_manager.create_task(task_id, "financial", total=0)
        task_manager.update_progress(task_id, message="Initializing financial data update...")

        log = DataAcquisitionLog(
            task_type="financial",
            status="running",
            started_at=datetime.now(),
        )
        self.db.add(log)
        await self.db.flush()

        try:
            # Get all active stocks (no prefix filtering for financial updates)
            task_manager.update_progress(task_id, message="Loading stock list...")
            result = await self.db.execute(select(Stock).where(Stock.is_active == True))
            stocks = result.scalars().all()
            total = len(stocks)
            
            task = task_manager.get_task(task_id)
            if task:
                task.total = total
            
            task_manager.update_progress(task_id, message=f"Updating financial data for {total} stocks...")

            processed = 0
            for stock in stocks:
                # Check for pause/stop
                if not task_manager.wait_if_paused(task_id):
                    task_manager.stop_task(task_id)
                    log.status = "stopped"
                    log.stocks_processed = processed
                    log.completed_at = datetime.now()
                    await self.db.commit()
                    logger.info(f"Financial update stopped: {processed}/{total}")
                    return task_id

                task_manager.update_progress(
                    task_id,
                    current=processed,
                    message=f"Fetching financial indicators for {stock.code} ({stock.name}) - {processed}/{total}",
                )

                try:
                    # Fetch comprehensive financial indicators
                    reports = await self.provider.get_financial_analysis_indicators(stock.code)
                    
                    for r in reports:
                        report_date = datetime.strptime(r.report_date, "%Y-%m-%d").date() if r.report_date else datetime.now().date()
                        
                        # Check if record already exists
                        existing = await self.db.execute(
                            select(FinancialReportModel).where(
                                FinancialReportModel.stock_code == r.code,
                                FinancialReportModel.report_date == report_date
                            )
                        )
                        report = existing.scalar_one_or_none()
                        
                        if report:
                            # Update existing record with ALL parsed financial fields
                            report.report_type = r.report_type
                            report.roe = r.roe
                            report.eps = r.eps
                            report.bps = r.bps
                            report.revenue_growth = r.revenue_growth
                            report.net_profit_growth = r.net_profit_growth
                            report.gross_margin = r.gross_margin
                            report.net_margin = r.net_margin
                            report.debt_ratio = r.debt_ratio
                            report.raw_data = json.dumps(r.raw_data) if r.raw_data else None
                        else:
                            # Insert new record with ALL parsed financial fields
                            self.db.add(FinancialReportModel(
                                stock_code=r.code,
                                report_date=report_date,
                                report_type=r.report_type,
                                roe=r.roe,
                                eps=r.eps,
                                bps=r.bps,
                                revenue_growth=r.revenue_growth,
                                net_profit_growth=r.net_profit_growth,
                                gross_margin=r.gross_margin,
                                net_margin=r.net_margin,
                                debt_ratio=r.debt_ratio,
                                raw_data=json.dumps(r.raw_data) if r.raw_data else None,
                            ))
                    
                    processed += 1
                    if processed % 50 == 0:
                        await self.db.flush()
                        logger.info(f"Financial update: {processed}/{total}")
                        
                except Exception as e:
                    logger.warning(f"Failed to update financial data for {stock.code}: {e}")
                    continue

            task_manager.complete_task(task_id, f"Completed: {processed}/{total} stocks")
            log.status = "success"
            log.stocks_processed = processed
            log.completed_at = datetime.now()
            await self.db.commit()
            logger.info(f"Financial update completed: {processed} stocks")
            return task_id

        except Exception as e:
            task_manager.fail_task(task_id, str(e))
            await self.db.rollback()
            await self._persist_log_outcome(
                log.id, "failed", error_message=str(e),
                stocks_processed=locals().get("processed", 0),
            )
            logger.error(f"Financial update failed: {e}")
            raise
