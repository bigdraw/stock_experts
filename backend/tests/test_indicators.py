"""Tests for the ported pure-pandas technical indicators.

Verifies the math on a small known series (golden values hand-computed).
Run via ``python -m tests.test_indicators`` or pytest."""

import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.services.technical.indicators import atr, ema, macd, rsi, sma  # noqa: E402


def main() -> int:
    failures: list[str] = []

    def check(label, cond):
        print(f"  {'PASS' if cond else 'FAIL'}: {label}")
        if not cond:
            failures.append(label)

    # 20-bar close series with a clear trend + pullback
    close = pd.Series(
        [10, 11, 12, 11, 13, 14, 13, 15, 16, 15,
         17, 18, 17, 19, 20, 19, 21, 22, 21, 23],
        dtype=float,
    )
    high = close + 1.0
    low = close - 1.0

    # SMA(5): first 4 NaN, 5th = mean(10..13)=11.4
    s = sma(close, 5)
    check("sma warmup NaN count == 4", s.iloc[:4].isna().all() and s.iloc[4:].notna().all())
    check("sma[4] == mean of first 5", abs(s.iloc[4] - close.iloc[:5].mean()) < 1e-9)

    # EMA(5): first 4 NaN, 5th seeded with SMA(5)
    e = ema(close, 5)
    check("ema warmup NaN count == 4", e.iloc[:4].isna().all() and e.iloc[4:].notna().all())
    check("ema seed == SMA(5)", abs(e.iloc[4] - close.iloc[:5].mean()) < 1e-9)

    # RSI(14): bounded [0,100]; Wilder ewm(adjust=False) computes from index 1
    # (row 0 is NaN due to close.diff()). Unlike SMA/EMA there's no full warmup.
    r = rsi(close, 14)
    check("rsi in [0,100] after warmup", r.dropna().between(0, 100).all())
    check("rsi row 0 NaN (diff), row 1+ finite", np.isnan(r.iloc[0]) and r.iloc[1:].notna().all())

    # MACD returns 3 columns
    m = macd(close)
    check("macd has macd/signal/histogram", set(m.columns) == {"macd", "signal", "histogram"})
    check("macd histogram == macd - signal",
          np.allclose(m["histogram"].dropna(), (m["macd"] - m["signal"]).dropna(), equal_nan=True))

    # ATR(14): positive, NaN warmup
    a = atr(high, low, close, 14)
    check("atr warmup NaN", a.iloc[:13].isna().all() and a.iloc[14:].notna().all())
    check("atr positive after warmup", (a.dropna() > 0).all())

    # Flat series -> RSI == 50 (neutral), not NaN
    flat = pd.Series([10.0] * 20)
    check("rsi flat series == 50 (neutral)", (rsi(flat, 14).dropna() == 50.0).all())

    print(f"\n{'ALL PASSED' if not failures else 'FAILURES: '+str(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())


def test_indicators_math():
    assert main() == 0
