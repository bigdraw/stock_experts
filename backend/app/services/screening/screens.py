"""三策略可解释选股打分（移植自 maverick-mcp，MIT License Copyright (c) 2024）。

源文件：`maverick/screening/screens.py`。
适配点：
  - 列名从美股 yfinance 风格 (Close/High/Low/Volume) 改为本平台小写
    (close/high/low/volume)，与 akshare/DailyQuote 约定一致。
  - 导入指向本平台 `app.services.technical.indicators` 与 `app.services.screening.{config,types}`。
三套 flag+score+reason 打分：bullish / bearish / supply_demand。每条结果带
人类可读 reason（`_FLAG_LABELS` 集中文案），可审计可解释，作 NL 筛选的结构化兜底。
"""

import pandas as pd

from app.services.screening.config import ScreeningSettings
from app.services.screening.types import ScreeningResult, ScreenName
from app.services.technical.indicators import atr, macd, rsi, sma

_FLAG_LABELS: dict[ScreenName, dict[str, str]] = {
    "bullish": {
        "close_above_sma50": "close above SMA50",
        "close_above_sma150": "close above SMA150",
        "close_above_sma200": "close above SMA200",
        "ma_aligned": "moving averages aligned (SMA50 > SMA150 > SMA200)",
        "volume_surge": "volume surge",
        "rsi_not_overbought": "RSI not overbought",
    },
    "bearish": {
        "close_below_sma50": "close below SMA50",
        "close_below_sma200": "close below SMA200",
        "rsi_oversold": "RSI oversold",
        "rsi_weak": "RSI weak (below 40)",
        "macd_bearish": "MACD below signal",
        "volume_decline": "high-volume down day",
        "atr_contraction": "ATR contraction",
    },
    "supply_demand": {
        "close_above_sma150": "close above SMA150",
        "close_above_sma200": "close above SMA200",
        "sma150_above_sma200": "SMA150 above SMA200",
        "sma200_rising": "SMA200 trending up",
        "sma50_above_sma150": "SMA50 above SMA150",
        "sma50_above_sma200": "SMA50 above SMA200",
        "close_above_sma50": "close above SMA50",
        "volume_surge": "volume above 1.2x average",
        "near_52w_high": "within 25% of the 252-day high",
    },
}


def _build_reason(screen: ScreenName, flags: dict[str, bool]) -> str:
    """从触发的 flags 渲染人类可读 reason（三策略共享）。"""
    labels = _FLAG_LABELS[screen]
    fired = [labels[name] for name in labels if flags.get(name)]
    title = screen.replace("_", " ")
    if not fired:
        return f"{title} screen: no criteria fired"
    return f"{title} screen: " + ", ".join(fired)


def _last_date(df: pd.DataFrame) -> str:
    """把 frame 末行索引渲染为 ISO 日期字符串。"""
    timestamp: pd.Timestamp = df.index[-1]
    naive = timestamp.tz_localize(None) if timestamp.tzinfo is not None else timestamp
    return naive.date().isoformat()


def score_bullish(
    symbol: str, df: pd.DataFrame, settings: ScreeningSettings
) -> ScreeningResult | None:
    """多头动量打分。

    close 在 SMA50/150/200 之上各 +25，均线对齐(SMA50>SMA150>SMA200) +25，
    量能放大(> volume_surge_multiplier × 30日均量) +10，RSI(14) 未超买 +10。
    combined_score >= bullish_min_score 才入选。
    """
    if len(df) < settings.min_history_days:
        return None

    close_s = df["close"]
    volume_s = df["volume"]
    sma50 = sma(close_s, 50).iloc[-1]
    sma150 = sma(close_s, 150).iloc[-1]
    sma200 = sma(close_s, 200).iloc[-1]
    rsi14 = rsi(close_s, 14).iloc[-1]
    avg_volume_30d = volume_s.rolling(window=30, min_periods=30).mean().iloc[-1]
    close = float(close_s.iloc[-1])
    volume = float(volume_s.iloc[-1])

    flags = {
        "close_above_sma50": bool(close > sma50),
        "close_above_sma150": bool(close > sma150),
        "close_above_sma200": bool(close > sma200),
        "ma_aligned": bool(sma50 > sma150 > sma200),
        "volume_surge": bool(volume > settings.volume_surge_multiplier * avg_volume_30d),
        "rsi_not_overbought": bool(rsi14 < settings.rsi_overbought),
    }
    combined_score = (
        25 * flags["close_above_sma50"]
        + 25 * flags["close_above_sma150"]
        + 25 * flags["close_above_sma200"]
        + 25 * flags["ma_aligned"]
        + 10 * flags["volume_surge"]
        + 10 * flags["rsi_not_overbought"]
    )
    if combined_score < settings.bullish_min_score:
        return None

    indicators: dict[str, int | float | None] = {
        "close": close,
        "sma50": float(sma50),
        "sma150": float(sma150),
        "sma200": float(sma200),
        "rsi14": float(rsi14),
        "volume": volume,
        "avg_volume_30d": float(avg_volume_30d),
    }
    return ScreeningResult(
        symbol=symbol,
        screen="bullish",
        date_analyzed=_last_date(df),
        close=close,
        combined_score=combined_score,
        momentum_score=None,
        indicators=indicators,
        flags=flags,
        reason=_build_reason("bullish", flags),
    )


def score_bearish(
    symbol: str, df: pd.DataFrame, settings: ScreeningSettings
) -> ScreeningResult | None:
    """空头打分。

    close<SMA50 +20，close<SMA200 +20，RSI(14)<超卖 +15 否则 <40 +10，
    MACD<signal +15，高量下跌日(量>volume_decline_multiplier×30日均量且收跌) +20，
    ATR(14)<atr_contraction_multiplier×20日均ATR +10。
    combined_score >= bear_min_score 才入选。
    """
    if len(df) < settings.min_history_days:
        return None

    close_s = df["close"]
    volume_s = df["volume"]
    sma50 = sma(close_s, 50).iloc[-1]
    sma200 = sma(close_s, 200).iloc[-1]
    rsi14 = rsi(close_s, 14).iloc[-1]
    macd_frame = macd(close_s)
    macd_line = macd_frame["macd"].iloc[-1]
    macd_signal = macd_frame["signal"].iloc[-1]
    atr14_s = atr(df["high"], df["low"], close_s, 14)
    atr_now = atr14_s.iloc[-1]
    atr_avg_20d = atr14_s.rolling(window=20, min_periods=20).mean().iloc[-1]
    avg_volume_30d = volume_s.rolling(window=30, min_periods=30).mean().iloc[-1]
    close = float(close_s.iloc[-1])
    prior_close = float(close_s.iloc[-2])
    volume = float(volume_s.iloc[-1])
    down_day = close < prior_close

    rsi_oversold = bool(rsi14 < settings.rsi_oversold)
    flags = {
        "close_below_sma50": bool(close < sma50),
        "close_below_sma200": bool(close < sma200),
        "rsi_oversold": rsi_oversold,
        "rsi_weak": bool((not rsi_oversold) and rsi14 < 40),
        "macd_bearish": bool(macd_line < macd_signal),
        "volume_decline": bool(
            volume > settings.volume_decline_multiplier * avg_volume_30d and down_day
        ),
        "atr_contraction": bool(atr_now < settings.atr_contraction_multiplier * atr_avg_20d),
    }
    combined_score = (
        20 * flags["close_below_sma50"]
        + 20 * flags["close_below_sma200"]
        + 15 * flags["rsi_oversold"]
        + 10 * flags["rsi_weak"]
        + 15 * flags["macd_bearish"]
        + 20 * flags["volume_decline"]
        + 10 * flags["atr_contraction"]
    )
    if combined_score < settings.bear_min_score:
        return None

    indicators: dict[str, int | float | None] = {
        "close": close,
        "sma50": float(sma50),
        "sma200": float(sma200),
        "rsi14": float(rsi14),
        "macd": float(macd_line),
        "macd_signal": float(macd_signal),
        "atr14": float(atr_now),
        "atr_avg_20d": float(atr_avg_20d),
        "volume": volume,
        "avg_volume_30d": float(avg_volume_30d),
        "prior_close": prior_close,
    }
    return ScreeningResult(
        symbol=symbol,
        screen="bearish",
        date_analyzed=_last_date(df),
        close=close,
        combined_score=combined_score,
        momentum_score=None,
        indicators=indicators,
        flags=flags,
        reason=_build_reason("bearish", flags),
    )


def score_supply_demand(
    symbol: str, df: pd.DataFrame, settings: ScreeningSettings
) -> ScreeningResult | None:
    """供需突破打分。

    布尔门：ALL of close>SMA150, close>SMA200, SMA150>SMA200, SMA200 上升(今>22日前),
    SMA50>SMA150, SMA50>SMA200, close>SMA50。
    入门后 breakout_strength：基础 50 + 量能放大(>1.2×30日均量) 25 + 接近52周高(>252日高×0.75) 25。
    momentum_score = clip((close/sma200-1)×100×5, 0, 100)。
    """
    if len(df) < settings.min_history_days:
        return None

    close_s = df["close"]
    volume_s = df["volume"]
    sma50_s = sma(close_s, 50)
    sma150_s = sma(close_s, 150)
    sma200_s = sma(close_s, 200)
    sma50 = sma50_s.iloc[-1]
    sma150 = sma150_s.iloc[-1]
    sma200 = sma200_s.iloc[-1]
    sma200_22_ago = sma200_s.iloc[-22]
    avg_volume_30d = volume_s.rolling(window=30, min_periods=30).mean().iloc[-1]
    high_252d = df["high"].rolling(window=252, min_periods=1).max().iloc[-1]
    close = float(close_s.iloc[-1])
    volume = float(volume_s.iloc[-1])

    flags = {
        "close_above_sma150": bool(close > sma150),
        "close_above_sma200": bool(close > sma200),
        "sma150_above_sma200": bool(sma150 > sma200),
        "sma200_rising": bool(sma200 > sma200_22_ago),
        "sma50_above_sma150": bool(sma50 > sma150),
        "sma50_above_sma200": bool(sma50 > sma200),
        "close_above_sma50": bool(close > sma50),
    }
    if not all(flags.values()):
        return None

    volume_surge = bool(volume > 1.2 * avg_volume_30d)
    near_52w_high = bool(close > high_252d * 0.75)
    flags["volume_surge"] = volume_surge
    flags["near_52w_high"] = near_52w_high

    breakout_strength = 50 + 25 * volume_surge + 25 * near_52w_high
    momentum_score = min(100.0, max(0.0, (close / sma200 - 1) * 100 * 5))

    indicators: dict[str, int | float | None] = {
        "close": close,
        "sma50": float(sma50),
        "sma150": float(sma150),
        "sma200": float(sma200),
        "sma200_22_bars_ago": float(sma200_22_ago),
        "volume": volume,
        "avg_volume_30d": float(avg_volume_30d),
        "high_252d": float(high_252d),
    }
    return ScreeningResult(
        symbol=symbol,
        screen="supply_demand",
        date_analyzed=_last_date(df),
        close=close,
        combined_score=breakout_strength,
        momentum_score=momentum_score,
        indicators=indicators,
        flags=flags,
        reason=_build_reason("supply_demand", flags),
    )
