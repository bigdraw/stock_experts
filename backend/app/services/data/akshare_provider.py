"""AkShare data provider implementation."""

import asyncio
import logging
import os
from datetime import datetime

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
_proxy_enabled_cache: bool | None = None


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
    original_http = os.environ.get("HTTP_PROXY")
    original_https = os.environ.get("HTTPS_PROXY")
    original_http_lower = os.environ.get("http_proxy")
    original_https_lower = os.environ.get("https_proxy")
    original_no_proxy = os.environ.get("NO_PROXY")
    original_no_proxy_lower = os.environ.get("no_proxy")

    # Remove proxy settings
    for key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
        if key in os.environ:
            del os.environ[key]

    # Also set NO_PROXY to bypass all proxies
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"

    return {
        "HTTP_PROXY": original_http,
        "HTTPS_PROXY": original_https,
        "http_proxy": original_http_lower,
        "https_proxy": original_https_lower,
        "NO_PROXY": original_no_proxy,
        "no_proxy": original_no_proxy_lower,
    }


def _restore_proxy(original_settings: dict):
    """Restore original proxy settings."""
    for key, value in original_settings.items():
        if value is not None:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]


def _parse_cn_number(v) -> float | None:
    """解析 akshare 财务数值字符串（中文量级）为 float。

    akshare 的 stock_financial_abstract_ths 返回 '6.28亿' / '3.2万亿' /
    '12.5万' / '0.5' / '5.2%' / '-' / '--' 等。裸 float() 在 '6.28亿' 上崩溃，
    导致整条财报拉取报错（财务历史表无数据根因）。
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s or s in ("-", "--", "nan", "None", "null"):
        return None
    pct = False
    if s.endswith("%"):
        pct = True
        s = s[:-1].strip()
    mult = 1.0
    if s.endswith("万亿"):
        mult = 1e12
        s = s[:-2]
    elif s.endswith("亿"):
        mult = 1e8
        s = s[:-1]
    elif s.endswith("万"):
        mult = 1e4
        s = s[:-1]
    try:
        f = float(s) * mult
        return f / 100 if pct else f
    except ValueError:
        return None


def _valid_bar(prev_close: float | None, close: float, high: float | None = None, low: float | None = None) -> bool:
    """Sanity-check a daily-quote bar before persisting/summarizing.

    Rejects akshare glitch bars (e.g. a 0.24 close for 宇通客车 whose real price
    is ~15). A-share daily limit is ±10% (±20% for 创业板/科创板), so a one-day
    move to <5% or >20× of the prior close is impossible outside 退市整理期 —
    treat as a data glitch and skip. Pure function so it's unit-testable.
    """
    if close is None or close <= 0 or close < 0.10:
        return False
    if prev_close and prev_close > 0:
        if close < prev_close * 0.05 or close > prev_close * 20:
            return False
    if high is not None and low is not None and high >= 0 and low >= 0:
        if not (high >= low):
            return False
    return True


def _normalize_per_share(payout: float | None, src_col_name: str) -> float | None:
    """Normalize a dividend payout to per-share, based on the ACTUAL source column
    name (not a fragile row.index heuristic).

    Columns named 每10股派息/派息比例/分红金额 carry 每10股 amounts → divide by 10.
    Columns named 每股派息/每股派息额 are already per-share → keep as-is.
    """
    if payout is None or payout <= 0:
        return None
    name = src_col_name or ""
    if "每股" in name:
        return round(payout, 4)
    # 每10股 / 派息比例 / 分红金额 → 每10股口径，除以 10
    return round(payout / 10, 4)


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
                    if code.startswith(
                        ("600", "601", "603", "605", "000", "001", "002", "003", "300")
                    ):
                        market = "SH" if code.startswith(("600", "601", "603", "605")) else "SZ"
                        stocks.append(
                            StockBasic(
                                code=code,
                                name=row["name"],
                                market=market,
                            )
                        )
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
                    code = item["code"]
                    if code in code_set:
                        market_cap = float(item.get("mktcap", 0)) if item.get("mktcap") else None
                        pe_ratio = float(item.get("per", 0)) if item.get("per") else None
                        pb_ratio = float(item.get("pb", 0)) if item.get("pb") else None

                        results.append(
                            StockBasicIndicators(
                                code=code,
                                date=datetime.now().strftime("%Y-%m-%d"),
                                market_cap=market_cap,
                                pe_ratio=pe_ratio,
                                pb_ratio=pb_ratio,
                                is_profitable=pe_ratio is not None and pe_ratio > 0
                                if pe_ratio is not None
                                else None,
                            )
                        )

                logger.info(f"Fetched indicators for {len(results)} stocks")

            except Exception as e:
                logger.error(f"Failed to fetch indicators: {e}")
                return []

        return results

    async def get_all_basic_indicators(
        self, code_prefixes: list[str] = None
    ) -> list[StockBasicIndicators]:
        """Get basic indicators for ALL A-share stocks in a single API call.

        Args:
            code_prefixes: List of code prefixes to filter (e.g., ['000', '600', '300']).
                          If None, fetch all stocks.
        """
        results = []

        async with self._semaphore:
            try:
                # Run synchronous call in thread pool
                all_data = await asyncio.to_thread(self._fetch_all_indicators_sina, code_prefixes)

                # Convert to StockBasicIndicators
                for item in all_data:
                    code = item["code"]

                    # 提取全部 20 个行情指标
                    symbol = item.get("symbol")
                    price = float(item.get("trade", 0)) if item.get("trade") else None
                    pricechange = (
                        float(item.get("pricechange", 0)) if item.get("pricechange") else None
                    )
                    changepercent = (
                        float(item.get("changepercent", 0)) if item.get("changepercent") else None
                    )
                    buy = float(item.get("buy", 0)) if item.get("buy") else None
                    sell = float(item.get("sell", 0)) if item.get("sell") else None
                    settlement = (
                        float(item.get("settlement", 0)) if item.get("settlement") else None
                    )
                    open_price = float(item.get("open", 0)) if item.get("open") else None
                    high = float(item.get("high", 0)) if item.get("high") else None
                    low = float(item.get("low", 0)) if item.get("low") else None
                    volume = float(item.get("volume", 0)) if item.get("volume") else None
                    amount = float(item.get("amount", 0)) if item.get("amount") else None
                    ticktime = item.get("ticktime")
                    per = float(item.get("per", 0)) if item.get("per") else None
                    pb = float(item.get("pb", 0)) if item.get("pb") else None
                    mktcap = float(item.get("mktcap", 0)) if item.get("mktcap") else None
                    nmc = float(item.get("nmc", 0)) if item.get("nmc") else None
                    turnoverratio = (
                        float(item.get("turnoverratio", 0)) if item.get("turnoverratio") else None
                    )

                    results.append(
                        StockBasicIndicators(
                            code=code,
                            date=datetime.now().strftime("%Y-%m-%d"),
                            # 20 个行情指标
                            symbol=symbol,
                            price=price,
                            pricechange=pricechange,
                            changepercent=changepercent,
                            buy=buy,
                            sell=sell,
                            settlement=settlement,
                            open=open_price,
                            high=high,
                            low=low,
                            volume=volume,
                            amount=amount,
                            ticktime=ticktime,
                            per=per,
                            pb=pb,
                            mktcap=mktcap,
                            nmc=nmc,
                            turnoverratio=turnoverratio,
                            # Legacy fields for backward compatibility
                            pe_ratio=per,
                            pb_ratio=pb,
                            market_cap=mktcap,
                            circulating_market_cap=nmc,
                            is_profitable=per is not None and per > 0 if per is not None else None,
                        )
                    )

                logger.info(
                    f"Fetched indicators for {len(results)} stocks (filtered by {code_prefixes if code_prefixes else 'all'})"
                )

            except Exception as e:
                logger.error(f"Failed to fetch all indicators: {e}")
                return []

        return results

    def _fetch_all_indicators_sina(self, code_prefixes: list[str] = None) -> list[dict]:
        """Fetch all A-share indicators from Sina API.

        Args:
            code_prefixes: List of code prefixes to filter (e.g., ['000', '600', '300']).
                          If None, fetch all stocks.
        """
        import json

        import requests

        s = requests.Session()
        s.trust_env = False

        all_data = []
        page = 1
        page_size = 80  # Sina API max per page
        MAX_PAGES = 200  # safety guard against runaway pagination

        while page <= MAX_PAGES:
            try:
                r = s.get(
                    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData",
                    params={
                        "page": str(page),
                        "num": str(page_size),
                        "sort": "symbol",
                        "asc": "1",
                        "node": "hs_a",
                        "symbol": "",
                        "_s_r_a": "page",
                    },
                    timeout=10,
                )
            except requests.RequestException as e:
                logger.error(f"Sina request failed on page {page}: {e}")
                break

            # Validate HTTP status — Sina returns an HTML error page (not JSON)
            # on failures; without this guard we'd raise JSONDecodeError and
            # discard everything already collected this run.
            if r.status_code != 200 or not r.text or not r.text.strip().startswith("["):
                logger.warning(
                    f"Sina page {page} returned status {r.status_code}, "
                    f"non-JSON body (len={len(r.text)}) — stopping pagination"
                )
                break

            try:
                data = json.loads(r.text)
            except json.JSONDecodeError as e:
                logger.error(f"Sina page {page} JSON decode failed: {e}")
                break

            if not data:
                break

            # Filter by code prefixes if specified
            if code_prefixes:
                filtered = [
                    item
                    for item in data
                    if any(item["code"].startswith(prefix) for prefix in code_prefixes)
                ]
                all_data.extend(filtered)
            else:
                all_data.extend(data)

            # A short page means we've reached the end; stop cleanly.
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
        """Get daily OHLCV data for a stock.

        主源 stock_zh_a_hist（东方财富），失败（某些码如 000036 会被断连）则降级
        stock_zh_a_daily（新浪），并带 1 次重试应对瞬时 ConnectionError。这样保证
        基础数据全面——不因单一数据源对个别码的抽风而缺K线。
        """
        async with self._semaphore:
            # 主源（东方财富），重试 1 次
            df = None
            source = "eastmoney"
            for attempt in range(2):
                try:
                    df = await asyncio.to_thread(self._fetch_daily_quotes_sync, code, start_date, end_date)
                    break
                except Exception as e:
                    if attempt == 0:
                        logger.warning(f"stock_zh_a_hist {code} attempt1 failed ({str(e)[:60]}), retry/fallback...")
                    else:
                        logger.warning(f"stock_zh_a_hist {code} failed twice, fallback to 新浪 stock_zh_a_daily")

            # 降级：新浪源（symbol 需 sz/sh 前缀）
            if df is None or len(df) == 0:
                try:
                    df = await asyncio.to_thread(self._fetch_daily_quotes_sina_sync, code, start_date, end_date)
                    source = "sina"
                except Exception as e:
                    logger.error(f"All daily-quote sources failed for {code}: {e}")
                    return []

            quotes = []
            prev_close = None
            if source == "sina":
                # 新浪 stock_zh_a_daily 列: date/open/high/low/close/volume/(outstanding_share/turnover)
                for _, row in df.iterrows():
                    try:
                        c = float(row["close"])
                        o = float(row["open"])
                        h = float(row["high"])
                        lo = float(row["low"])
                        v = float(row["volume"])
                    except (TypeError, ValueError):
                        continue
                    if not _valid_bar(prev_close, c, h, lo):
                        logger.warning(f"akshare bad bar rejected {code} {row['date']} close={c}")
                        continue
                    quotes.append(
                        DailyQuote(
                            code=code,
                            date=str(row["date"]),
                            open=o, high=h, low=lo, close=c,
                            volume=v,
                            amount=float(row.get("turnover")) if pd.notna(row.get("turnover")) else None,
                            turnover_rate=None,
                        )
                    )
                    prev_close = c
            else:
                for _, row in df.iterrows():
                    try:
                        c = float(row["收盘"])
                        o = float(row["开盘"])
                        h = float(row["最高"])
                        lo = float(row["最低"])
                        v = float(row["成交量"])
                    except (TypeError, ValueError):
                        continue
                    if not _valid_bar(prev_close, c, h, lo):
                        logger.warning(f"akshare bad bar rejected {code} {row['日期']} close={c}")
                        continue
                    quotes.append(
                        DailyQuote(
                            code=code,
                            date=str(row["日期"]),
                            open=o, high=h, low=lo, close=c,
                            volume=v,
                            amount=float(row["成交额"]),
                            turnover_rate=float(row.get("换手率"))
                            if pd.notna(row.get("换手率"))
                            else None,
                        )
                    )
                    prev_close = c
            return quotes

    def _fetch_daily_quotes_sync(self, code: str, start_date: str, end_date: str):
        """Synchronous wrapper for fetching daily quotes (主源：东方财富)."""
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

    def _fetch_daily_quotes_sina_sync(self, code: str, start_date: str, end_date: str):
        """备选源：新浪 stock_zh_a_daily（东方财富对个别码会断连，新浪兜底）。

        symbol 需 sz/sh 前缀：0/3 开头=sz，6/9 开头=sh。
        """
        prefix = "sh" if code[:1] in ("6", "9") else "sz"
        original_proxy = _bypass_proxy()
        try:
            return ak.stock_zh_a_daily(
                symbol=f"{prefix}{code}",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="qfq",
            )
        finally:
            _restore_proxy(original_proxy)

    async def get_financial_reports(self, code: str) -> list[FinancialReport]:
        """Get financial reports for a stock."""
        async with self._semaphore:
            try:
                # Run synchronous akshare call in thread pool to avoid blocking event loop
                df = await asyncio.to_thread(self._fetch_financial_reports_sync, code)

                reports = []
                for _, row in df.iterrows():
                    # akshare 财务值常带中文量级（'6.28亿'），用 _parse_cn_number 解析
                    revenue = _parse_cn_number(row.get("营业总收入"))
                    net_profit = _parse_cn_number(row.get("净利润"))
                    roe = _parse_cn_number(row.get("净资产收益率"))
                    eps = _parse_cn_number(row.get("基本每股收益"))
                    bps = _parse_cn_number(row.get("每股净资产"))
                    revenue_growth = _parse_cn_number(row.get("营业总收入同比增长率"))
                    net_profit_growth = _parse_cn_number(row.get("净利润同比增长率"))
                    gross_margin = _parse_cn_number(row.get("销售毛利率"))
                    net_margin = _parse_cn_number(row.get("销售净利率"))
                    debt_ratio = _parse_cn_number(row.get("资产负债率"))

                    reports.append(
                        FinancialReport(
                            code=code,
                            report_date=str(row.get("报告期", "")),
                            report_type=self._infer_report_type(str(row.get("报告期", ""))),
                            revenue=revenue,
                            net_profit=net_profit,
                            roe=roe,
                            eps=eps,
                            bps=bps,
                            revenue_growth=revenue_growth,
                            net_profit_growth=net_profit_growth,
                            gross_margin=gross_margin,
                            net_margin=net_margin,
                            debt_ratio=debt_ratio,
                            raw_data=row.to_dict(),
                        )
                    )
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

    async def get_financial_analysis_indicators(
        self, code: str, start_year: str = None
    ) -> list[FinancialReport]:
        """Get comprehensive financial analysis indicators for a stock.

        This method fetches detailed financial metrics including ROE, EPS, profit margins,
        growth rates, and other key financial ratios.

        Args:
            code: Stock code (e.g., '600519')
            start_year: Optional start year (e.g., '2020'). If None, fetches all available data.

        Returns:
            List of FinancialReport objects with comprehensive financial data
        """
        async with self._semaphore:
            try:
                # Run synchronous akshare call in thread pool
                df = await asyncio.to_thread(
                    self._fetch_financial_analysis_indicators_sync, code, start_year
                )

                reports = []
                for _, row in df.iterrows():
                    # Extract key metrics
                    report_date = str(row.get("日期", ""))

                    def _num(key: str, _row=row) -> float | None:
                        """Coerce a cell to float, None if missing/NaN.

                        ``_row=row`` binds the current loop iteration's row
                        (B023: closures over loop vars capture by reference)."""
                        v = _row.get(key)
                        return float(v) if pd.notna(v) else None

                    # ROE - prefer weighted, fall back to diluted
                    roe = _num("加权净资产收益率(%)")
                    if roe is None:
                        roe = _num("摊薄净资产收益率(%)")

                    eps = _num("摊薄每股收益(元)")
                    bps = _num("每股净资产_调整后(元)") or _num("每股净资产(元)")
                    # Profit margins — 销售净利率 is the true net margin;
                    # 主营业务利润率 is a related but distinct ratio (used as
                    # gross_margin proxy when 销售毛利率 is absent).
                    gross_margin = _num("销售毛利率(%)") or _num("主营业务利润率(%)")
                    net_margin = _num("销售净利率(%)")
                    # Growth rates — 净利润增长率 is net-profit GROWTH, not margin.
                    # (Previous code mis-assigned it to net_margin.)
                    revenue_growth = _num("主营业务收入增长率(%)")
                    net_profit_growth = _num("净利润增长率(%)")
                    debt_ratio = _num("资产负债率(%)")

                    reports.append(
                        FinancialReport(
                            code=code,
                            report_date=report_date,
                            report_type=self._infer_report_type(report_date),
                            roe=roe,
                            eps=eps,
                            bps=bps,
                            gross_margin=gross_margin,
                            net_margin=net_margin,
                            revenue_growth=revenue_growth,
                            net_profit_growth=net_profit_growth,
                            debt_ratio=debt_ratio,
                            # Keep full payload for traceability / future fields.
                            raw_data={
                                "eps": eps,
                                "bps": bps,
                                "roe": roe,
                                "gross_margin": gross_margin,
                                "net_margin": net_margin,
                                "revenue_growth": revenue_growth,
                                "net_profit_growth": net_profit_growth,
                                "debt_ratio": debt_ratio,
                                "full_data": row.to_dict(),
                            },
                        )
                    )
                return reports
            except Exception as e:
                logger.error(f"Failed to fetch financial analysis indicators for {code}: {e}")
                raise

    def _fetch_financial_analysis_indicators_sync(self, code: str, start_year: str = None):
        """Synchronous wrapper for fetching financial analysis indicators."""
        original_proxy = _bypass_proxy()
        try:
            if start_year:
                return ak.stock_financial_analysis_indicator(symbol=code, start_year=start_year)
            else:
                return ak.stock_financial_analysis_indicator(symbol=code)
        finally:
            _restore_proxy(original_proxy)

    async def get_financial_statements(self, code: str) -> list[dict]:
        """取三大报表（资产负债表/利润表/现金流量表）的关键字段，按报告期返回。

        复用 _bypass_proxy/_parse_cn_number。code 须为 'sh600519'/'sz000001' 形式。
        返回每期 dict：report_date(YYYYMMDD) + total_assets/current_assets/
        current_liab/total_liab/equity/cash/revenue/cost/op_profit/net_profit/
        interest_exp/ocf/capex/div_paid（无法解析的为 None）。
        用于价值投资指标（ROIC/OCF/FCF/流动比率/利息保障等）—— 这些字段
        不在 financial_reports 缓存的 abstract 里，需从三大报表取。
        """
        import pandas as _pd

        async with self._semaphore:
            try:
                b, i, c = await asyncio.to_thread(self._fetch_statements_sync, code)
            except Exception as e:
                logger.error(f"Failed to fetch financial statements for {code}: {e}")
                return []

            def _row(df: _pd.DataFrame, rd: str) -> _pd.Series:
                m = df[df["报告日"] == rd]
                return m.iloc[0] if len(m) else _pd.Series(dtype=object)

            # 以利润表报告日为基准（最全）
            dates = sorted(i["报告日"].unique().tolist())
            # 现金流重复检测：同一 OFC 值在连续两期完全相同→数据源 bug，第二期置 None
            prev_ocf = prev_capex = None
            out = []
            for rd in dates:
                irow, brow, crow = i[i["报告日"] == rd].iloc[0], _row(b, rd), _row(c, rd)
                ocf = _parse_cn_number(crow.get("经营活动产生的现金流量净额"))
                capex = _parse_cn_number(
                    crow.get("购建固定资产、无形资产和其他长期资产所支付的现金")
                    or crow.get("购建固定资产、无形资产和其他长期资产支付的现金")
                )
                # 检测现金流重复（星徽股份 bug：2023Q1 与 2022Q1 OFC/FCF/capex 完全相同）
                if ocf is not None and prev_ocf is not None and ocf == prev_ocf:
                    logger.warning(f"Duplicate OCF detected for {code} at {rd} (same as prev period), setting to None")
                    ocf = None
                if capex is not None and prev_capex is not None and capex == prev_capex:
                    logger.warning(f"Duplicate capex detected for {code} at {rd}, setting to None")
                    capex = None
                prev_ocf, prev_capex = ocf, capex
                out.append({
                    "report_date": str(rd),
                    "total_assets": _parse_cn_number(brow.get("资产总计")),
                    "current_assets": _parse_cn_number(brow.get("流动资产合计")),
                    "current_liab": _parse_cn_number(brow.get("流动负债合计")),
                    "total_liab": _parse_cn_number(brow.get("负债合计")),
                    "equity": _parse_cn_number(
                        brow.get("归属于母公司股东权益合计")
                        or brow.get("所有者权益(或股东权益)合计")
                        or brow.get("所有者权益合计")
                    ),
                    # 所有者权益合计（含少数股东）——供 debt_ratio 反推勾稽：
                    # (total_assets − total_equity)/total_assets == 资产负债率。
                    # equity 是归母口径，用它反推会把少数股东权益算进负债、偏高。
                    "total_equity": _parse_cn_number(
                        brow.get("所有者权益(或股东权益)合计")
                        or brow.get("所有者权益合计")
                        or brow.get("归属于母公司股东权益合计")
                    ),
                    "cash": _parse_cn_number(brow.get("货币资金")),
                    "revenue": _parse_cn_number(irow.get("营业总收入") or irow.get("营业收入")),
                    "cost": _parse_cn_number(irow.get("营业成本")),
                    "op_profit": _parse_cn_number(irow.get("营业利润")),
                    "net_profit": _parse_cn_number(
                        irow.get("归属于母公司所有者的净利润") or irow.get("净利润")
                    ),
                    "interest_exp": _parse_cn_number(irow.get("利息费用") or irow.get("财务费用")),
                    "ocf": ocf,
                    "capex": capex,
                    "div_paid": _parse_cn_number(
                        crow.get("分配股利、利润或偿付利息所支付的现金")
                    ),
                })
            return out

    def _fetch_statements_sync(self, code: str):
        """Synchronous wrapper: fetch the three Sina statements."""
        original_proxy = _bypass_proxy()
        try:
            b = ak.stock_financial_report_sina(stock=code, symbol="资产负债表")
            i = ak.stock_financial_report_sina(stock=code, symbol="利润表")
            c = ak.stock_financial_report_sina(stock=code, symbol="现金流量表")
            return b, i, c
        finally:
            _restore_proxy(original_proxy)

    async def get_dividends(self, code: str) -> list[dict]:
        """取分红历史（派息比例等）。code 为 '600519' 形式。

        三源递进：cninfo → stock_history_dividend_detail → stock_history_dividend。
        """
        async with self._semaphore:
            try:
                df = await asyncio.to_thread(self._fetch_dividends_sync, code)
            except Exception as e:
                logger.error(f"Failed to fetch dividends(cninfo) for {code}: {e}")
                df = None
            if df is None or len(df) == 0:
                # 备选源1：stock_history_dividend_detail
                try:
                    df = await asyncio.to_thread(self._fetch_dividends_detail_sync, code)
                except Exception as e:
                    logger.warning(f"Failed to fetch dividends(detail) for {code}: {e}")
                    df = None
                if df is not None and len(df) > 0:
                    out = []
                    for _, row in df.iterrows():
                        # Pick the actual source column; normalize by name, not row.index.
                        src_col, payout = None, None
                        for col in ("每10股派息(税前)", "每股派息额"):
                            if col in row.index:
                                payout = _parse_cn_number(row.get(col))
                                if payout:
                                    src_col = col
                                    break
                        per_share = _normalize_per_share(payout, src_col)
                        out.append({
                            "announce_date": str(row.get("公告日", "")),
                            "dividend_per_share": per_share,
                            "stock_div_ratio": None,
                            "convert_ratio": None,
                            "ex_date": str(row.get("除权除息日", "")),
                        })
                    if out:
                        return out
            if df is None or len(df) == 0:
                # 备选源2：stock_history_dividend（汇总形式，列名不同）
                try:
                    df2 = await asyncio.to_thread(self._fetch_dividends_summary_sync, code)
                except Exception as e:
                    logger.warning(f"Failed to fetch dividends(summary) for {code}: {e}")
                    return []
                if df2 is None or len(df2) == 0:
                    return []
                out = []
                for _, row in df2.iterrows():
                    # 分红金额=每10股派息额 → /10；每股派息=已每股 → 原值
                    src_col, payout = None, None
                    for col in ("分红金额", "每股派息"):
                        if col in row.index:
                            payout = _parse_cn_number(row.get(col))
                            if payout:
                                src_col = col
                                break
                    per_share = _normalize_per_share(payout, src_col)
                    out.append({
                        "announce_date": str(row.get("公告日期", "")),
                        "dividend_per_share": per_share,
                        "stock_div_ratio": _parse_cn_number(row.get("送股")),
                        "convert_ratio": _parse_cn_number(row.get("转增")),
                        "ex_date": str(row.get("除权除息日", "")),
                    })
                return out
            out = []
            for _, row in df.iterrows():
                # akshare stock_dividend_cninfo 的"派息比例"= 每10股派息额（税前，元）
                # 始终 /10 归一化为每股派息（之前用 >=1 启发式，0.66元每10股 会被当每股）
                payout = _parse_cn_number(row.get("派息比例"))
                per_share = round(payout / 10, 4) if payout else None
                out.append({
                    "announce_date": str(row.get("实施方案公告日期", "")),
                    "dividend_per_share": per_share,
                    "stock_div_ratio": _parse_cn_number(row.get("送股比例")),
                    "convert_ratio": _parse_cn_number(row.get("转增比例")),
                    "ex_date": str(row.get("除权日", "")),
                })
            return out

    def _fetch_dividends_sync(self, code: str):
        original_proxy = _bypass_proxy()
        try:
            return ak.stock_dividend_cninfo(symbol=code)
        finally:
            _restore_proxy(original_proxy)

    def _fetch_dividends_detail_sync(self, code: str):
        """备选分红源：stock_history_dividend_detail（部分公司 cninfo 无数据但有）。"""
        original_proxy = _bypass_proxy()
        try:
            prefix = "sh" if code[:1] in ("6", "9") else "sz"
            return ak.stock_history_dividend_detail(symbol=f"{prefix}{code}")
        finally:
            _restore_proxy(original_proxy)

    def _fetch_dividends_summary_sync(self, code: str):
        """第三备选分红源：stock_history_dividend（汇总形式，兜底）。"""
        original_proxy = _bypass_proxy()
        try:
            prefix = "sh" if code[:1] in ("6", "9") else "sz"
            return ak.stock_history_dividend(symbol=f"{prefix}{code}")
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
