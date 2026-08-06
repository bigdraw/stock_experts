"""Kline summary + data-validation tests.

- bad close bar (0.24) filtered in-memory (DB path); low_5y/max_drawdown not corrupted
- low_5y/high_5y use intraday low/high columns (not close min/max)
- daily change_6m uses a calendar anchor (aligned with monthly 近6月)
- _valid_bar / _normalize_per_share pure helpers
"""

import os
import sys
import tempfile

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

import pandas as pd  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base  # noqa: E402
from app.models.stock import DailyQuote, Stock  # noqa: E402
from app.services.data.akshare_provider import _normalize_per_share, _valid_bar  # noqa: E402
from app.services.debate.factbook import FactBook  # noqa: E402


async def _fresh():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory, tmp.name


def _df(n: int, base: float = 15.0, start: str = "2021-01-01") -> pd.DataFrame:
    """n daily bars as a DataFrame with date/close/low/high/volume; close oscillates."""
    idx = pd.date_range(start, periods=n, freq="B")
    rows = []
    for i, d in enumerate(idx):
        c = base + (i % 10 - 5) * 0.2
        rows.append({"date": d, "close": round(c, 4), "low": c - 0.5, "high": c + 0.5, "volume": 1000.0})
    return pd.DataFrame(rows)


# ---- pure helper tests ----

def test_valid_bar_rejects_glitch():
    """0.24 close (real ~15) rejected; valid bars accepted."""
    assert _valid_bar(None, 15.0) is True
    assert _valid_bar(15.0, 0.24) is False       # < prev*0.05 (0.75)
    assert _valid_bar(15.0, 15.5) is True
    assert _valid_bar(15.0, 400.0) is False       # > prev*20 (300)
    assert _valid_bar(None, 0.05) is False        # < 0.10 floor
    assert _valid_bar(None, -1.0) is False


def test_valid_bar_ohlc_consistency():
    assert _valid_bar(15.0, 15.5, high=16.0, low=15.0) is True
    assert _valid_bar(15.0, 15.5, high=14.0, low=16.0) is False  # high < low


def test_normalize_per_share_by_column_name():
    assert abs(_normalize_per_share(2.692, "每10股派息(税前)") - 0.2692) < 1e-9
    assert abs(_normalize_per_share(2.692, "派息比例") - 0.2692) < 1e-9
    assert abs(_normalize_per_share(2.692, "分红金额") - 0.2692) < 1e-9
    assert abs(_normalize_per_share(0.2692, "每股派息额") - 0.2692) < 1e-9
    assert abs(_normalize_per_share(0.2692, "每股派息") - 0.2692) < 1e-9
    assert _normalize_per_share(None, "每10股派息(税前)") is None
    assert _normalize_per_share(0, "每10股派息(税前)") is None


# ---- kline summary tests ----

async def test_kline_filters_bad_close_bar():
    """A 0.24 glitch bar filtered in-memory (DB path); low_5y/max_drawdown sane."""
    engine, factory, db_path = await _fresh()
    try:
        df = _df(1300, base=15.0)
        df.loc[500, "close"] = 0.24
        df.loc[500, "low"] = 0.24
        async with factory() as db:
            db.add(Stock(code="600066", name="宇通客车", market="SH", is_active=True))
            for _, r in df.iterrows():
                db.add(DailyQuote(stock_code="600066", date=r["date"].date(),
                                  open=float(r["close"]) - 0.1, high=float(r["high"]),
                                  low=float(r["low"]), close=float(r["close"]),
                                  volume=float(r["volume"]), amount=10000.0))
            await db.commit()
            summary = await FactBook()._kline_summarize("600066", db)
            daily = summary["daily"]["summary"]
            assert daily["low_5y"] != 0.24, f"bad bar leaked into low_5y: {daily['low_5y']}"
            assert daily["max_drawdown_5y_pct"] > -90, f"bad drawdown: {daily['max_drawdown_5y_pct']}"
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_kline_low_high_uses_intraday_columns():
    """low_5y/high_5y must use the low/high columns (intraday), not close min/max."""
    df = _df(1300, base=15.0)
    # one bar whose low dips well below its close (intraday wick)
    df.loc[700, "low"] = 9.0
    df.loc[700, "close"] = 15.2
    daily = FactBook()._kline_daily_summary(df)
    assert daily["low_5y"] <= 9.0, f"low_5y should reflect intraday low, got {daily['low_5y']}"


def test_kline_change_6m_uses_calendar_anchor():
    """daily change_6m must use a calendar ~6-month anchor (aligned with monthly
    近6月), not trading-day-backtrack iloc[-133]."""
    df = _df(300, base=15.0, start="2024-01-01")
    daily = FactBook()._kline_daily_summary(df)
    last_close = daily["last_close"]
    last_date = df["date"].iloc[-1]
    target = last_date - pd.DateOffset(months=6)
    expected_base = float(df.loc[df["date"] <= target, "close"].iloc[-1])
    expected = round((last_close / expected_base - 1) * 100, 2)
    assert abs(daily["change_6m"] - expected) < 1e-6, f"change_6m {daily['change_6m']} vs expected {expected}"
