"""Data acquisition engine with dual-layer self-healing."""

import asyncio
import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import DailyQuote as DailyQuoteModel
from app.models.stock import FinancialReport as FinancialReportModel
from app.models.stock import Stock
from app.models.system import DataAcquisitionLog
from app.services.data.provider import DataProvider

logger = logging.getLogger(__name__)


class DataAcquisitionEngine:
    """Orchestrates data collection with self-healing."""

    def __init__(self, provider: DataProvider, db: AsyncSession):
        self.provider = provider
        self.db = db

    async def full_basic_collection(self, batch_size: int = 50):
        """Full collection of basic indicators (can run overnight)."""
        log = DataAcquisitionLog(
            task_type="full_basic",
            status="running",
            started_at=datetime.now(),
        )
        self.db.add(log)
        await self.db.flush()

        try:
            # 1. Get stock list
            stocks = await self.provider.get_stock_list()
            logger.info(f"Starting full collection for {len(stocks)} stocks")

            # 2. Upsert stocks
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

            # 3. Batch collect indicators
            processed = 0
            for i in range(0, len(stocks), batch_size):
                batch = stocks[i:i + batch_size]
                codes = [s.code for s in batch]
                try:
                    indicators = await self.provider.get_basic_indicators(codes)
                    # Update stocks with indicators (stored in financial_reports table for now)
                    for ind in indicators:
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
                    logger.info(f"Processed {processed}/{len(stocks)} stocks")
                except Exception as e:
                    logger.error(f"Failed to process batch {i//batch_size + 1}: {e}")
                    # Self-healing: log and continue
                    continue

            log.status = "success"
            log.completed_at = datetime.now()
            log.details = json.dumps({"total_stocks": len(stocks), "processed": processed})
            await self.db.commit()
            logger.info(f"Full collection completed: {processed}/{len(stocks)} stocks")

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            log.completed_at = datetime.now()
            await self.db.commit()
            logger.error(f"Full collection failed: {e}")
            raise

    async def incremental_update(self):
        """Daily incremental update: today's quotes + basic indicators."""
        log = DataAcquisitionLog(
            task_type="incremental",
            status="running",
            started_at=datetime.now(),
        )
        self.db.add(log)
        await self.db.flush()

        try:
            # Get all active stocks
            result = await self.db.execute(select(Stock).where(Stock.is_active == True))
            stocks = result.scalars().all()
            today = datetime.now().strftime("%Y-%m-%d")

            processed = 0
            for stock in stocks:
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
                        logger.info(f"Incremental update: {processed}/{len(stocks)}")
                except Exception as e:
                    logger.warning(f"Failed to update {stock.code}: {e}")
                    continue

            log.status = "success"
            log.stocks_processed = processed
            log.completed_at = datetime.now()
            await self.db.commit()
            logger.info(f"Incremental update completed: {processed} stocks")

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            log.completed_at = datetime.now()
            await self.db.commit()
            logger.error(f"Incremental update failed: {e}")
            raise

    async def deep_data_on_demand(self, stock_codes: list[str]):
        """Fetch deep data (financial reports) for specific stocks."""
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

            log.status = "success"
            log.stocks_processed = processed
            log.completed_at = datetime.now()
            await self.db.commit()
            logger.info(f"Deep data fetch completed: {processed} stocks")

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            log.completed_at = datetime.now()
            await self.db.commit()
            logger.error(f"Deep data fetch failed: {e}")
            raise
