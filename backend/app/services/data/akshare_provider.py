"""AkShare data provider implementation."""

import asyncio
import logging
import os
from datetime import datetime

import akshare as ak
import pandas as pd

from app.services.data.provider import (
    DailyQuote,
    DataProvider,
    FinancialReport,
    StockBasic,
    StockBasicIndicators,
)

logger = logging.getLogger(__name__)


def _bypass_proxy():
    """Temporarily bypass proxy settings for akshare requests."""
    # Save original proxy settings
    original_http = os.environ.get('HTTP_PROXY')
    original_https = os.environ.get('HTTPS_PROXY')
    original_http_lower = os.environ.get('http_proxy')
    original_https_lower = os.environ.get('https_proxy')
    
    # Remove proxy settings
    for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
        if key in os.environ:
            del os.environ[key]
    
    return {
        'HTTP_PROXY': original_http,
        'HTTPS_PROXY': original_https,
        'http_proxy': original_http_lower,
        'https_proxy': original_https_lower,
    }


def _restore_proxy(original_settings: dict):
    """Restore original proxy settings."""
    for key, value in original_settings.items():
        if value is not None:
            os.environ[key] = value


class AkShareProvider(DataProvider):
    """Free data provider using AkShare."""

    def __init__(self, rate_limit: int = 10, retry_max: int = 3):
        self.rate_limit = rate_limit
        self.retry_max = retry_max
        self._semaphore = asyncio.Semaphore(rate_limit)

    async def get_stock_list(self) -> list[StockBasic]:
        """Get all A-share stocks (600/000/300 prefix)."""
        async with self._semaphore:
            try:
                # Run synchronous akshare call in thread pool to avoid blocking event loop
                df = await asyncio.to_thread(self._fetch_stock_list_sync)
                
                stocks = []
                for _, row in df.iterrows():
                    code = str(row["code"]).zfill(6)
                    # Filter: 600xxx (SH), 000xxx/001xxx/002xxx/003xxx (SZ), 300xxx (SZ)
                    if code.startswith(("600", "601", "603", "605", "000", "001", "002", "003", "300")):
                        market = "SH" if code.startswith(("600", "601", "603", "605")) else "SZ"
                        stocks.append(StockBasic(
                            code=code,
                            name=row["name"],
                            market=market,
                        ))
                logger.info(f"Fetched {len(stocks)} stocks from AkShare")
                return stocks
            except Exception as e:
                logger.error(f"Failed to fetch stock list: {e}")
                raise

    def _fetch_stock_list_sync(self):
        """Synchronous wrapper for fetching stock list."""
        original_proxy = _bypass_proxy()
        try:
            return ak.stock_info_a_code_name()
        finally:
            _restore_proxy(original_proxy)

    async def get_basic_indicators(self, codes: list[str]) -> list[StockBasicIndicators]:
        """Get basic indicators for given stock codes using stock_zh_a_spot_em."""
        results = []
        
        # Fetch all A-share spot data in one call (more efficient)
        async with self._semaphore:
            try:
                # Run synchronous akshare call in thread pool to avoid blocking event loop
                df = await asyncio.to_thread(self._fetch_spot_data_sync)
                
                # Filter by codes and extract indicators
                df['代码'] = df['代码'].astype(str).str.zfill(6)
                filtered_df = df[df['代码'].isin(codes)]
                
                for _, row in filtered_df.iterrows():
                    code = row['代码']
                    
                    # Extract indicators from spot data
                    # 总市值 (total market cap), 市盈率-动态 (PE ratio), 市净率 (PB ratio)
                    market_cap = float(row.get('总市值', 0)) if pd.notna(row.get('总市值')) else None
                    pe_ratio = float(row.get('市盈率-动态', 0)) if pd.notna(row.get('市盈率-动态')) else None
                    pb_ratio = float(row.get('市净率', 0)) if pd.notna(row.get('市净率')) else None
                    
                    results.append(StockBasicIndicators(
                        code=code,
                        date=datetime.now().strftime("%Y-%m-%d"),
                        market_cap=market_cap,
                        pe_ratio=pe_ratio,
                        pb_ratio=pb_ratio,
                        is_profitable=pe_ratio is not None and pe_ratio > 0 if pe_ratio is not None else None,
                    ))
                
                logger.info(f"Fetched indicators for {len(results)} stocks")
                
            except Exception as e:
                logger.error(f"Failed to fetch batch indicators: {e}")
                # Return empty list, let caller handle it
                return []
        
        return results

    def _fetch_spot_data_sync(self):
        """Synchronous wrapper for fetching spot data."""
        original_proxy = _bypass_proxy()
        try:
            return ak.stock_zh_a_spot_em()
        finally:
            _restore_proxy(original_proxy)

    async def get_daily_quotes(self, code: str, start_date: str, end_date: str) -> list[DailyQuote]:
        """Get daily OHLCV data for a stock."""
        async with self._semaphore:
            try:
                # Run synchronous akshare call in thread pool to avoid blocking event loop
                df = await asyncio.to_thread(
                    self._fetch_daily_quotes_sync,
                    code, start_date, end_date
                )
                
                quotes = []
                for _, row in df.iterrows():
                    quotes.append(DailyQuote(
                        code=code,
                        date=str(row["日期"]),
                        open=float(row["开盘"]),
                        high=float(row["最高"]),
                        low=float(row["最低"]),
                        close=float(row["收盘"]),
                        volume=float(row["成交量"]),
                        amount=float(row["成交额"]),
                        turnover_rate=float(row.get("换手率")) if pd.notna(row.get("换手率")) else None,
                    ))
                return quotes
            except Exception as e:
                logger.error(f"Failed to fetch daily quotes for {code}: {e}")
                raise

    def _fetch_daily_quotes_sync(self, code: str, start_date: str, end_date: str):
        """Synchronous wrapper for fetching daily quotes."""
        original_proxy = _bypass_proxy()
        try:
            return ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="qfq",  # Forward-adjusted
            )
        finally:
            _restore_proxy(original_proxy)

    async def get_financial_reports(self, code: str) -> list[FinancialReport]:
        """Get financial reports for a stock."""
        async with self._semaphore:
            try:
                # Run synchronous akshare call in thread pool to avoid blocking event loop
                df = await asyncio.to_thread(
                    self._fetch_financial_reports_sync,
                    code
                )
                
                reports = []
                for _, row in df.iterrows():
                    reports.append(FinancialReport(
                        code=code,
                        report_date=str(row.get("报告期", "")),
                        report_type=self._infer_report_type(str(row.get("报告期", ""))),
                        revenue=float(row.get("营业总收入")) if pd.notna(row.get("营业总收入")) else None,
                        net_profit=float(row.get("净利润")) if pd.notna(row.get("净利润")) else None,
                        roe=float(row.get("净资产收益率")) if pd.notna(row.get("净资产收益率")) else None,
                        raw_data=row.to_dict(),
                    ))
                return reports
            except Exception as e:
                logger.error(f"Failed to fetch financial reports for {code}: {e}")
                raise

    def _fetch_financial_reports_sync(self, code: str):
        """Synchronous wrapper for fetching financial reports."""
        original_proxy = _bypass_proxy()
        try:
            return ak.stock_financial_abstract_ths(symbol=code)
        finally:
            _restore_proxy(original_proxy)

    async def get_research_reports(self, code: str) -> list[dict]:
        """Get research reports for a stock (placeholder)."""
        # AkShare has limited research report data; this is a placeholder
        logger.warning(f"Research reports not fully supported for {code}")
        return []

    async def health_check(self) -> bool:
        """Check if AkShare is available."""
        try:
            ak.stock_info_a_code_name()
            return True
        except Exception:
            return False

    @staticmethod
    def _infer_report_type(report_date: str) -> str:
        """Infer report type from date string."""
        if "03-31" in report_date or "一季" in report_date:
            return "Q1"
        elif "06-30" in report_date or "中报" in report_date or "半年" in report_date:
            return "H1"
        elif "09-30" in report_date or "三季" in report_date:
            return "Q3"
        elif "12-31" in report_date or "年报" in report_date:
            return "Annual"
        return "Unknown"
