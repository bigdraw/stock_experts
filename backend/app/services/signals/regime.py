"""市场状态（regime）识别器（移植自 maverick-mcp，MIT License Copyright (c) 2024）。

源文件：`maverick_mcp/services/signals/regime.py`。
适配点：原版 `import pandas_ta as ta` 是 vestigial（仅 noqa F401 注册 accessor，
代码未实际调用 ta.*，全用 pandas .mean()/.iloc）。本平台直接删除该导入，纯 pandas。

RegimeDetector 把市场环境分为四态——bull / bear / choppy / transitional——
由四个加权因子合成：trend(0.35) / volatility(0.25) / momentum(0.25) / breadth(0.15)。
A 股可用沪深 300/中证 500 价格序列 + 等效 VIX（或 ATR 派生波动率）+ 涨跌家数比。
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_WEIGHT_TREND = 0.35
_WEIGHT_VOLATILITY = 0.25
_WEIGHT_MOMENTUM = 0.25
_WEIGHT_BREADTH = 0.15

# 置信度低于此值标记为 transitional（方向不明）
_TRANSITIONAL_THRESHOLD = 0.45


class RegimeDetector:
    """从价格序列 + 宏观信号分类市场状态。

    Attributes:
        short_window: 短期 SMA 周期（默认 20）。
        long_window: 长期 SMA 周期（默认 50）。
        momentum_window: 动量回看周期（默认 10）。
    """

    def __init__(
        self,
        short_window: int = 20,
        long_window: int = 50,
        momentum_window: int = 10,
    ) -> None:
        self.short_window = short_window
        self.long_window = long_window
        self.momentum_window = momentum_window

    def classify(
        self,
        market_prices: pd.Series,
        vix_level: float,
        breadth_ratio: float | None = None,
    ) -> dict[str, Any]:
        """分类市场状态。

        Args:
            market_prices: 市场收盘价序列（最新在末尾）。
            vix_level: 当前 VIX 水平（A 股可用波动率代理）。
            breadth_ratio: 上涨家数/总家数（0–1），None 则中性。

        Returns:
            ``{regime, confidence, drivers, votes}``。
            regime ∈ {bull, bear, choppy, transitional}；confidence 0–1。
        """
        trend_score, trend_vote = self._score_trend(market_prices)
        vol_score, vol_vote = self._score_volatility(vix_level)
        mom_score, mom_vote = self._score_momentum(market_prices)
        breadth_score, breadth_vote = self._score_breadth(breadth_ratio)

        composite = (
            _WEIGHT_TREND * trend_score
            + _WEIGHT_VOLATILITY * vol_score
            + _WEIGHT_MOMENTUM * mom_score
            + _WEIGHT_BREADTH * breadth_score
        )
        # composite ∈ [-1, +1]；confidence 为归一化绝对值
        confidence = min(abs(composite), 1.0)

        if confidence < _TRANSITIONAL_THRESHOLD:
            regime = "transitional"
        elif composite > 0:
            # 趋势弱但合成为正 → choppy
            if trend_score < 0.15 and vol_score < 0.1:
                regime = "choppy"
            else:
                regime = "bull"
        else:
            regime = "bear"

        # 低波动 + 无方向 → choppy
        if regime != "bear" and trend_score < 0.05 and vol_score < 0.05:
            regime = "choppy"

        return {
            "regime": regime,
            "confidence": round(confidence, 4),
            "drivers": {
                "trend": round(trend_score, 4),
                "volatility": round(vol_score, 4),
                "momentum": round(mom_score, 4),
                "breadth": round(breadth_score, 4),
            },
            "votes": {
                "trend": trend_vote,
                "volatility": vol_vote,
                "momentum": mom_vote,
                "breadth": breadth_vote,
            },
        }

    def _score_trend(self, prices: pd.Series) -> tuple[float, str]:
        """基于价格 vs 短/长 SMA + 斜率打分。score ∈ [-1,+1]。"""
        if len(prices) < self.long_window + 1:
            return 0.0, "neutral"

        short_sma = float(prices.iloc[-self.short_window:].mean())
        long_sma = float(prices.iloc[-self.long_window:].mean())
        current = float(prices.iloc[-1])

        pct_vs_long = (current - long_sma) / long_sma if long_sma != 0 else 0.0
        sma_cross = 1.0 if short_sma > long_sma else -1.0

        start_price = float(prices.iloc[-(self.short_window + 1)])
        slope = (current - start_price) / start_price if start_price != 0 else 0.0

        raw = 0.5 * sma_cross + 0.3 * _clip(pct_vs_long * 10) + 0.2 * _clip(slope * 20)
        return _clip(raw), "bull" if raw > 0 else "bear"

    def _score_volatility(self, vix: float) -> tuple[float, str]:
        """基于 VIX：高波动→bearish，低波动→bullish。"""
        if vix < 16:
            return 0.8, "bull"
        if vix < 22:
            return 0.0, "neutral"
        if vix < 30:
            return -0.6, "bear"
        return -1.0, "bear"

    def _score_momentum(self, prices: pd.Series) -> tuple[float, str]:
        """动量窗口内的变化率。"""
        if len(prices) < self.momentum_window + 1:
            return 0.0, "neutral"
        start = float(prices.iloc[-(self.momentum_window + 1)])
        end = float(prices.iloc[-1])
        roc = (end - start) / start if start != 0 else 0.0
        # ±10% 映射到 ±1.0
        score = _clip(roc * 10)
        return score, "bull" if score > 0 else ("bear" if score < 0 else "neutral")

    def _score_breadth(self, breadth_ratio: float | None) -> tuple[float, str]:
        """涨跌广度（0–1）。>0.6 牛，<0.4 熊。"""
        if breadth_ratio is None:
            return 0.0, "neutral"
        if breadth_ratio > 0.6:
            score = _clip((breadth_ratio - 0.5) * 5)
            return score, "bull"
        if breadth_ratio < 0.4:
            score = _clip((breadth_ratio - 0.5) * 5)
            return score, "bear"
        return 0.0, "neutral"


def _clip(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    """clip 到 [lo, hi]。"""
    return max(lo, min(hi, float(value)))
