"""Stock-related models."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Stock(Base):
    __tablename__ = "stocks"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)  # '600519', '000001'
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    market: Mapped[str] = mapped_column(String(5), nullable=False)  # SH / SZ
    industry: Mapped[str | None] = mapped_column(String(50))
    sector: Mapped[str | None] = mapped_column(String(50))
    list_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)


class DailyQuote(Base):
    __tablename__ = "daily_quotes"
    __table_args__ = (UniqueConstraint("stock_code", "date", name="uq_daily_quote"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)  # shares
    amount: Mapped[float | None] = mapped_column(Float)  # CNY
    turnover_rate: Mapped[float | None] = mapped_column(Float)


class FinancialReport(Base):
    __tablename__ = "financial_reports"
    __table_args__ = (UniqueConstraint("stock_code", "report_date", "report_type", name="uq_financial_report"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    report_type: Mapped[str | None] = mapped_column(String(10))  # Q1/H1/Q3/Annual/Latest
    
    # 行情指标 (20 fields from Sina API)
    symbol: Mapped[str | None] = mapped_column(String(20))  # 股票代码（带市场前缀）
    price: Mapped[float | None] = mapped_column(Float)  # 当前价格（元）
    pricechange: Mapped[float | None] = mapped_column(Float)  # 涨跌额（元）
    changepercent: Mapped[float | None] = mapped_column(Float)  # 涨跌幅（%）
    buy: Mapped[float | None] = mapped_column(Float)  # 买一价（元）
    sell: Mapped[float | None] = mapped_column(Float)  # 卖一价（元）
    settlement: Mapped[float | None] = mapped_column(Float)  # 昨收价（元）
    open: Mapped[float | None] = mapped_column(Float)  # 开盘价（元）
    high: Mapped[float | None] = mapped_column(Float)  # 最高价（元）
    low: Mapped[float | None] = mapped_column(Float)  # 最低价（元）
    volume: Mapped[float | None] = mapped_column(Float)  # 成交量（股）
    amount: Mapped[float | None] = mapped_column(Float)  # 成交额（元）
    ticktime: Mapped[str | None] = mapped_column(String(20))  # 时间戳
    per: Mapped[float | None] = mapped_column(Float)  # 市盈率
    pb: Mapped[float | None] = mapped_column(Float)  # 市净率
    mktcap: Mapped[float | None] = mapped_column(Float)  # 总市值（万元）
    nmc: Mapped[float | None] = mapped_column(Float)  # 流通市值（万元）
    turnoverratio: Mapped[float | None] = mapped_column(Float)  # 换手率（%）
    
    # Legacy fields for backward compatibility
    pe_ratio: Mapped[float | None] = mapped_column(Float)  # 市盈率
    pb_ratio: Mapped[float | None] = mapped_column(Float)  # 市净率
    market_cap: Mapped[float | None] = mapped_column(Float)  # 总市值（万元）
    circulating_market_cap: Mapped[float | None] = mapped_column(Float)  # 流通市值（万元）
    
    # 财务报表数据
    revenue: Mapped[float | None] = mapped_column(Float)
    net_profit: Mapped[float | None] = mapped_column(Float)
    total_assets: Mapped[float | None] = mapped_column(Float)
    total_equity: Mapped[float | None] = mapped_column(Float)
    roe: Mapped[float | None] = mapped_column(Float)
    
    # 扩展财务指标
    eps: Mapped[float | None] = mapped_column(Float)  # 基本每股收益
    bps: Mapped[float | None] = mapped_column(Float)  # 每股净资产
    revenue_growth: Mapped[float | None] = mapped_column(Float)  # 营业收入同比增长率（%）
    net_profit_growth: Mapped[float | None] = mapped_column(Float)  # 净利润同比增长率（%）
    gross_margin: Mapped[float | None] = mapped_column(Float)  # 销售毛利率（%）
    net_margin: Mapped[float | None] = mapped_column(Float)  # 销售净利率（%）
    debt_ratio: Mapped[float | None] = mapped_column(Float)  # 资产负债率（%）
    
    # 衍生指标
    is_profitable: Mapped[bool | None] = mapped_column(Boolean)
    
    # 完整原始数据（JSON 格式，存储所有 196 个财务字段）
    raw_data: Mapped[str | None] = mapped_column(Text)  # JSON


class ResearchReport(Base):
    __tablename__ = "research_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str | None] = mapped_column(String(100))
    publish_date: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[str | None] = mapped_column(String(20))
    url: Mapped[str | None] = mapped_column(String(1000))
    raw_data: Mapped[str | None] = mapped_column(Text)  # JSON
