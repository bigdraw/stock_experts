"""Data provider abstraction layer."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass
class StockBasic:
    """Basic stock information."""
    code: str
    name: str
    market: str  # SH / SZ
    industry: str | None = None
    sector: str | None = None
    list_date: str | None = None


@dataclass
class StockBasicIndicators:
    """Basic financial indicators for a stock."""
    code: str
    date: str
    market_cap: float | None = None  # Total market cap (CNY)
    is_profitable: bool | None = None
    pb_ratio: float | None = None  # Price-to-book
    roe: float | None = None  # Return on equity
    pe_ratio: float | None = None  # Price-to-earnings


@dataclass
class DailyQuote:
    """Daily OHLCV data."""
    code: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float  # shares
    amount: float  # CNY
    turnover_rate: float | None = None


@dataclass
class FinancialReport:
    """Financial report data."""
    code: str
    report_date: str
    report_type: str  # Q1 / H1 / Q3 / Annual
    revenue: float | None = None
    net_profit: float | None = None
    roe: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    market_cap: float | None = None
    raw_data: dict | None = None


class DataProvider(ABC):
    """Abstract data provider interface."""

    @abstractmethod
    async def get_stock_list(self) -> list[StockBasic]:
        """Get all A-share stocks (600/000/300 prefix)."""
        ...

    @abstractmethod
    async def get_basic_indicators(self, codes: list[str]) -> list[StockBasicIndicators]:
        """Get basic indicators for given stock codes."""
        ...

    @abstractmethod
    async def get_all_basic_indicators(self) -> list[StockBasicIndicators]:
        """Get basic indicators for ALL A-share stocks in a single call."""
        ...

    @abstractmethod
    async def get_daily_quotes(self, code: str, start_date: str, end_date: str) -> list[DailyQuote]:
        """Get daily OHLCV data for a stock."""
        ...

    @abstractmethod
    async def get_financial_reports(self, code: str) -> list[FinancialReport]:
        """Get financial reports for a stock (deep data)."""
        ...

    @abstractmethod
    async def get_research_reports(self, code: str) -> list[dict]:
        """Get research reports for a stock (deep data)."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if data source is available."""
        ...
