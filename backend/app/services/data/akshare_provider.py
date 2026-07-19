"""AkShare data provider implementation."""

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

import akshare as ak
import pandas as pd
from sqlalchemy import select

from app.services.data.provider import (
    DailyQuote,
    DataProvider,
    FinancialReport,
    StockBasic,
    StockBasicIndicators,
)

logger = logging.getLogger(__name__)

# Proxy enabled cache (None means not loaded yet)
_proxy_enabled_cache: Optional[bool] = None


async def get_proxy_enabled() -> bool:
    """Get proxy enabled setting from database."""
    global _proxy_enabled_cache
    if _proxy_enabled_cache is not None:
        return _proxy_enabled_cache
    
    from app.database import async_session_factory
    from app.models.system import SystemSettings
    
    async with async_session_factory() as db:
        result = await db.execute(
            select(SystemSettings).where(SystemSettings.key == "proxy_enabled")
        )
        setting = result.scalar_one_or_none()
        if setting:
            _proxy_enabled_cache = setting.value.lower() == "true"
        else:
            # Default to False (bypass proxy)
            _proxy_enabled_cache = False
    return _proxy_enabled_cache


async def set_proxy_enabled(enabled: bool):
    """Set proxy enabled setting in database."""
    global _proxy_enabled_cache
    
    from app.database import async_session_factory
    from app.models.system import SystemSettings
    
    async with async_session_factory() as db:
        result = await db.execute(
            select(SystemSettings).where(SystemSettings.key == "proxy_enabled")
        )
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = str(enabled).lower()
        else:
            db.add(SystemSettings(key="proxy_enabled", value=str(enabled).lower()))
        await db.commit()
    _proxy_enabled_cache = enabled


def _bypass_proxy():
    """Temporarily bypass proxy settings for akshare requests."""
    # Check if proxy is enabled (use cache, sync version)
    if _proxy_enabled_cache is True:
        return {}  # Don't bypass, use proxy
    
    # Save original proxy settings
    original_http = os.environ.get('HTTP_PROXY')
    original_https = os.environ.get('HTTPS_PROXY')
    original_http_lower = os.environ.get('http_proxy')
    original_https_lower = os.environ.get('https_proxy')
    original_no_proxy = os.environ.get('NO_PROXY')
    original_no_proxy_lower = os.environ.get('no_proxy')
    
    # Remove proxy settings
    for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
        if key in os.environ:
            del os.environ[key]
    
    # Also set NO_PROXY to bypass all proxies
    os.environ['NO_PROXY'] = '*'
    os.environ['no_proxy'] = '*'
    
    return {
        'HTTP_PROXY': original_http,
        'HTTPS_PROXY': original_https,
        'http_proxy': original_http_lower,
        'https_proxy': original_https_lower,
        'NO_PROXY': original_no_proxy,
        'no_proxy': original_no_proxy_lower,
    }


def _restore_proxy(original_settings: dict):
    """Restore original proxy settings."""
    for key, value in original_settings.items():
        if value is not None:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]


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
        """Get basic indicators for given stock codes using Sina API."""
        results = []
        
        # Fetch all A-share data from Sina (eastmoney is broken)
        async with self._semaphore:
            try:
                # Run synchronous call in thread pool
                all_data = await asyncio.to_thread(self._fetch_all_indicators_sina)
                
                # Filter by codes
                code_set = set(codes)
                for item in all_data:
                    code = item['code']
                    if code in code_set:
                        market_cap = float(item.get('mktcap', 0)) if item.get('mktcap') else None
                        pe_ratio = float(item.get('per', 0)) if item.get('per') else None
                        pb_ratio = float(item.get('pb', 0)) if item.get('pb') else None
                        
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
                logger.error(f"Failed to fetch indicators: {e}")
                return []
        
        return results
    
    async def get_all_basic_indicators(self) -> list[StockBasicIndicators]:
        """Get basic indicators for ALL A-share stocks in a single API call."""
        results = []
        
        async with self._semaphore:
            try:
                # Run synchronous call in thread pool
                all_data = await asyncio.to_thread(self._fetch_all_indicators_sina)
                
                # Convert to StockBasicIndicators
                for item in all_data:
                    code = item['code']
                    market_cap = float(item.get('mktcap', 0)) if item.get('mktcap') else None
                    pe_ratio = float(item.get('per', 0)) if item.get('per') else None
                    pb_ratio = float(item.get('pb', 0)) if item.get('pb') else None
                    
                    results.append(StockBasicIndicators(
                        code=code,
                        date=datetime.now().strftime("%Y-%m-%d"),
                        market_cap=market_cap,
                        pe_ratio=pe_ratio,
                        pb_ratio=pb_ratio,
                        is_profitable=pe_ratio is not None and pe_ratio > 0 if pe_ratio is not None else None,
                    ))
                
                logger.info(f"Fetched indicators for {len(results)} stocks (all)")
                
            except Exception as e:
                logger.error(f"Failed to fetch all indicators: {e}")
                return []
        
        return results
    
    def _fetch_all_indicators_sina(self) -> list[dict]:
        """Fetch all A-share indicators from Sina API."""
        import requests
        import json
        
        s = requests.Session()
        s.trust_env = False
        
        all_data = []
        page = 1
        page_size = 80  # Sina API max per page
        
        while True:
            r = s.get(
                'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData',
                params={
                    'page': str(page),
                    'num': str(page_size),
                    'sort': 'symbol',
                    'asc': '1',
                    'node': 'hs_a',
                    'symbol': '',
                    '_s_r_a': 'page'
                },
                timeout=10
            )
            
            data = json.loads(r.text)
            if not data:
                break
            
            all_data.extend(data)
            
            if len(data) < page_size:
                break
            
            page += 1
        
        return all_data

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
