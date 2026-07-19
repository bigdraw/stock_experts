"""Pure pandas/numpy technical indicators.

直接复用自 wshobson/maverick-mcp (MIT License, Copyright (c) 2024)，源文件
`maverick/technical/indicators.py`。逐项复刻 pandas-ta 的非 TA-Lib 公式
(``talib=False``)，行为可复现且无编译依赖（本平台不引入 pandas_ta/TA-Lib）。

约定（每个函数共享）：
- 输入为 tz-naive ``pd.Series``（high/low/close，每行一个价格）；输出与输入等长同索引，
  带与 pandas-ta 形状一致的 NaN 预热段。
- 历史不足周期时，结果整段为 NaN 而非部分计算。
"""

import numpy as np
import pandas as pd


def sma(close: pd.Series, period: int) -> pd.Series:
    """Simple moving average：普通滚动均值，前 ``period - 1`` 行为 NaN。"""
    return close.rolling(window=period, min_periods=period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    """Exponential moving average，pandas ``ewm(span=period, adjust=False)``。

    匹配 pandas-ta 默认（TA-Lib 风格）种子：前 ``period - 1`` 行 NaN，
    第 ``period`` 行用前 ``period`` 个 close 的简单均值播种，EMA 递推
    (``y_t = alpha * x_t + (1 - alpha) * y_{t-1}``) 从此处运行。
    """
    if len(close) < period:
        return pd.Series(np.nan, index=close.index, dtype=float)
    seeded = close.astype(float).copy()
    seeded.iloc[: period - 1] = np.nan
    seeded.iloc[period - 1] = close.iloc[:period].mean()
    return seeded.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative strength index，Wilder 平滑 (``ewm(alpha=1/period, adjust=False)``)。

    持平序列（平均增益与平均损失均为 0）定义为 50.0（中性）而非字面 0/0 的 NaN。
    """
    if len(close) < period:
        return pd.Series(np.nan, index=close.index, dtype=float)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    total = avg_gain + avg_loss
    safe_total = total.replace(0, np.nan)
    result = 100 * avg_gain / safe_total
    return result.mask(total == 0, 50.0)


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    """Moving average convergence/divergence。

    返回 DataFrame：``macd``（快 EMA - 慢 EMA）、``signal``（macd 的 EMA）、
    ``histogram``（macd - signal）。基于本模块 :func:`ema`，共享种子与 NaN 预热。
    """
    if slow < fast:
        fast, slow = slow, fast
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    macd_line = fast_ema - slow_ema
    first_valid = macd_line.first_valid_index()
    if first_valid is None:
        signal_line = pd.Series(np.nan, index=close.index, dtype=float)
    else:
        signal_line = ema(macd_line.loc[first_valid:], signal).reindex(close.index)
    histogram = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "histogram": histogram}
    )


def atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Average true range：真实波幅用 Wilder 法平滑。

    第一行 true range 用 ``high - low``（无前收可差分）；前 ``period`` 个 true range
    均值播种 Wilder 递推，匹配 pandas-ta 默认 ATR 形状。
    """
    if len(close) < period:
        return pd.Series(np.nan, index=close.index, dtype=float)
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    seeded = true_range.astype(float).copy()
    seeded.iloc[: period - 1] = np.nan
    seeded.iloc[period - 1] = true_range.iloc[:period].mean()
    return seeded.ewm(alpha=1 / period, adjust=False).mean()
