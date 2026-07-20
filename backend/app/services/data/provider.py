"""Data provider abstraction layer."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


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
    # 行情指标 (20 fields from Sina API)
    symbol: str | None = None  # 股票代码（带市场前缀）
    price: float | None = None  # 当前价格（元）
    pricechange: float | None = None  # 涨跌额（元）
    changepercent: float | None = None  # 涨跌幅（%）
    buy: float | None = None  # 买一价（元）
    sell: float | None = None  # 卖一价（元）
    settlement: float | None = None  # 昨收价（元）
    open: float | None = None  # 开盘价（元）
    high: float | None = None  # 最高价（元）
    low: float | None = None  # 最低价（元）
    volume: float | None = None  # 成交量（股）
    amount: float | None = None  # 成交额（元）
    ticktime: str | None = None  # 时间戳
    per: float | None = None  # 市盈率
    pb: float | None = None  # 市净率
    mktcap: float | None = None  # 总市值（万元）
    nmc: float | None = None  # 流通市值（万元）
    turnoverratio: float | None = None  # 换手率（%）

    # Legacy fields for backward compatibility
    pe_ratio: float | None = None  # 市盈率
    pb_ratio: float | None = None  # 市净率
    market_cap: float | None = None  # 总市值（万元）
    circulating_market_cap: float | None = None  # 流通市值（万元）
    is_profitable: bool | None = None  # 是否盈利


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
    # Extended financial metrics
    eps: float | None = None  # 基本每股收益
    bps: float | None = None  # 每股净资产
    revenue_growth: float | None = None  # 营业收入同比增长率
    net_profit_growth: float | None = None  # 净利润同比增长率
    gross_margin: float | None = None  # 销售毛利率
    net_margin: float | None = None  # 销售净利率
    debt_ratio: float | None = None  # 资产负债率
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
