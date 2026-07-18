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
    __table_args__ = (UniqueConstraint("stock_code", "report_date", name="uq_financial_report"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    report_type: Mapped[str | None] = mapped_column(String(10))  # Q1/H1/Q3/Annual
    revenue: Mapped[float | None] = mapped_column(Float)
    net_profit: Mapped[float | None] = mapped_column(Float)
    total_assets: Mapped[float | None] = mapped_column(Float)
    total_equity: Mapped[float | None] = mapped_column(Float)
    roe: Mapped[float | None] = mapped_column(Float)
    pe_ratio: Mapped[float | None] = mapped_column(Float)
    pb_ratio: Mapped[float | None] = mapped_column(Float)
    market_cap: Mapped[float | None] = mapped_column(Float)
    is_profitable: Mapped[bool | None] = mapped_column(Boolean)
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
