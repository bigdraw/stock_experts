"""策略模板 + 纯 pandas 信号生成器（移植自 maverick-mcp，MIT License Copyright (c) 2024）。

源文件：`maverick_mcp/backtesting/strategies/templates.py`。
适配点：原版 STRATEGY_TEMPLATES 的 `code` 字段是 `vbt.*` 调用串（依赖 vectorbtpro，
免费版在 Python 3.12 装不上）。本平台把每策略实现为**纯 pandas 的
`generate_signals(df, params) -> (entries, exits)`**，去掉 vbt 依赖。
ML/regime_aware/ensemble 三策略为高级形态，标 needs_* 注记，结构化部分保留。

9 个可直接生成信号的策略：sma_cross / ema_cross / macd / rsi / bollinger /
momentum / mean_reversion / breakout / volume_momentum。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.technical.indicators import ema as _ema
from app.services.technical.indicators import macd as _macd
from app.services.technical.indicators import rsi as _rsi
from app.services.technical.indicators import sma as _sma


def _crosses_above(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """fast 上穿 slow：今 fast>slow 且 昨 fast<=slow。"""
    return (fast > slow) & (fast.shift(1) <= slow.shift(1))


def _crosses_below(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """fast 下穿 slow。"""
    return (fast < slow) & (fast.shift(1) >= slow.shift(1))


def _close_col(df: pd.DataFrame) -> pd.Series:
    return df["close"] if "close" in df.columns else df["Close"]


# ---------------------------------------------------------------------------
# 每策略纯 pandas 信号生成器
# ---------------------------------------------------------------------------


def _gen_sma_cross(df: pd.DataFrame, p: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    close = _close_col(df)
    fast = _sma(close, p["fast_period"])
    slow = _sma(close, p["slow_period"])
    return _crosses_above(fast, slow).fillna(False), _crosses_below(fast, slow).fillna(False)


def _gen_ema_cross(df: pd.DataFrame, p: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    close = _close_col(df)
    fast = _ema(close, p["fast_period"])
    slow = _ema(close, p["slow_period"])
    return _crosses_above(fast, slow).fillna(False), _crosses_below(fast, slow).fillna(False)


def _gen_macd(df: pd.DataFrame, p: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    close = _close_col(df)
    m = _macd(close, fast=p["fast_period"], slow=p["slow_period"], signal=p["signal_period"])
    return (
        _crosses_above(m["macd"], m["signal"]).fillna(False),
        _crosses_below(m["macd"], m["signal"]).fillna(False),
    )


def _gen_rsi(df: pd.DataFrame, p: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    close = _close_col(df)
    r = _rsi(close, p["period"])
    entries = (r < p["oversold"]) & (r.shift(1) >= p["oversold"])
    exits = (r > p["overbought"]) & (r.shift(1) <= p["overbought"])
    return entries.fillna(False), exits.fillna(False)


def _gen_bollinger(df: pd.DataFrame, p: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    close = _close_col(df)
    ma = close.rolling(p["period"]).mean()
    std = close.rolling(p["period"]).std()
    upper = ma + p["std_dev"] * std
    lower = ma - p["std_dev"] * std
    entries = (close <= lower) & (close.shift(1) > lower.shift(1))
    exits = (close >= upper) & (close.shift(1) < upper.shift(1))
    return entries.fillna(False), exits.fillna(False)


def _gen_momentum(df: pd.DataFrame, p: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    close = _close_col(df)
    rets = close.pct_change(p["lookback"])
    return (rets > p["threshold"]).fillna(False), (rets < -p["threshold"]).fillna(False)


def _gen_mean_reversion(df: pd.DataFrame, p: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    close = _close_col(df)
    ma = _sma(close, p["ma_period"])
    dev = (close - ma) / ma
    return (dev < -p["entry_threshold"]).fillna(False), (dev > p["exit_threshold"]).fillna(False)


def _gen_breakout(df: pd.DataFrame, p: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    close = _close_col(df)
    upper = close.rolling(p["lookback"]).max()
    lower = close.rolling(p["exit_lookback"]).min()
    return (close > upper.shift(1)).fillna(False), (close < lower.shift(1)).fillna(False)


def _gen_volume_momentum(df: pd.DataFrame, p: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    close = _close_col(df)
    volume = df["volume"] if "volume" in df.columns else df["Volume"]
    rets = close.pct_change(p["momentum_period"])
    avg_vol = volume.rolling(p["volume_period"]).mean()
    surge = volume > avg_vol * p["volume_multiplier"]
    entries = (rets > p["momentum_threshold"]) & surge
    exits = (rets < -p["momentum_threshold"]) | (volume < avg_vol * 0.8)
    return entries.fillna(False), exits.fillna(False)


# ---------------------------------------------------------------------------
# 模板注册表
# ---------------------------------------------------------------------------

_GENERATORS = {
    "sma_cross": _gen_sma_cross,
    "ema_cross": _gen_ema_cross,
    "macd": _gen_macd,
    "rsi": _gen_rsi,
    "bollinger": _gen_bollinger,
    "momentum": _gen_momentum,
    "mean_reversion": _gen_mean_reversion,
    "breakout": _gen_breakout,
    "volume_momentum": _gen_volume_momentum,
}

STRATEGY_TEMPLATES: dict[str, dict[str, Any]] = {
    "sma_cross": {
        "name": "SMA Crossover",
        "description": "快线上穿慢线买入，下穿卖出",
        "parameters": {"fast_period": 10, "slow_period": 20},
        "optimization_ranges": {
            "fast_period": [5, 10, 15, 20],
            "slow_period": [20, 30, 50, 100],
        },
    },
    "ema_cross": {
        "name": "EMA Crossover",
        "description": "指数均线交叉，比 SMA 反应更快",
        "parameters": {"fast_period": 12, "slow_period": 26},
        "optimization_ranges": {
            "fast_period": [8, 12, 16, 20],
            "slow_period": [20, 26, 35, 50],
        },
    },
    "macd": {
        "name": "MACD Signal",
        "description": "MACD 上穿信号线买入，下穿卖出",
        "parameters": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
        "optimization_ranges": {
            "fast_period": [8, 10, 12, 14],
            "slow_period": [21, 24, 26, 30],
            "signal_period": [7, 9, 11],
        },
    },
    "rsi": {
        "name": "RSI Mean Reversion",
        "description": "RSI 超卖买入，超买卖出",
        "parameters": {"period": 14, "oversold": 30, "overbought": 70},
        "optimization_ranges": {
            "period": [7, 14, 21],
            "oversold": [20, 25, 30, 35],
            "overbought": [65, 70, 75, 80],
        },
    },
    "bollinger": {
        "name": "Bollinger Bands",
        "description": "触及下轨买入，触及上轨卖出",
        "parameters": {"period": 20, "std_dev": 2.0},
        "optimization_ranges": {
            "period": [10, 15, 20, 25],
            "std_dev": [1.5, 2.0, 2.5, 3.0],
        },
    },
    "momentum": {
        "name": "Momentum",
        "description": "动量为正超阈值买入，为负卖出",
        "parameters": {"lookback": 20, "threshold": 0.05},
        "optimization_ranges": {
            "lookback": [10, 15, 20, 25, 30],
            "threshold": [0.02, 0.03, 0.05, 0.07, 0.10],
        },
    },
    "mean_reversion": {
        "name": "Mean Reversion",
        "description": "价格低于均线阈值买入，高于卖出",
        "parameters": {"ma_period": 20, "entry_threshold": 0.02, "exit_threshold": 0.01},
        "optimization_ranges": {
            "ma_period": [15, 20, 30, 50],
            "entry_threshold": [0.01, 0.02, 0.03, 0.05],
            "exit_threshold": [0.00, 0.01, 0.02],
        },
    },
    "breakout": {
        "name": "Channel Breakout",
        "description": "突破滚动高点买入，跌破滚动低点卖出",
        "parameters": {"lookback": 20, "exit_lookback": 10},
        "optimization_ranges": {
            "lookback": [10, 20, 30, 50],
            "exit_lookback": [5, 10, 15, 20],
        },
    },
    "volume_momentum": {
        "name": "Volume-Weighted Momentum",
        "description": "放量上涨买入，缩量或下跌卖出",
        "parameters": {
            "momentum_period": 20,
            "volume_period": 20,
            "momentum_threshold": 0.05,
            "volume_multiplier": 1.5,
        },
        "optimization_ranges": {
            "momentum_period": [10, 20, 30],
            "volume_period": [10, 20, 30],
            "momentum_threshold": [0.03, 0.05, 0.07],
            "volume_multiplier": [1.2, 1.5, 2.0],
        },
    },
    # 高级形态（信号生成需 ML/regime/集成，仅保留元数据，generate_signals 抛 NotImplementedError）
    "online_learning": {
        "name": "Online Learning Strategy",
        "description": "在线学习自适应预测（needs ML：SGD 分类器 + 技术特征流式更新）",
        "parameters": {"lookback": 20, "learning_rate": 0.01, "update_frequency": 5},
        "optimization_ranges": {
            "lookback": [10, 20, 30, 50],
            "learning_rate": [0.001, 0.01, 0.1],
            "update_frequency": [1, 5, 10, 20],
        },
    },
    "regime_aware": {
        "name": "Regime-Aware Strategy",
        "description": "按市场 regime 切换 momentum/mean_reversion（needs regime detector）",
        "parameters": {
            "regime_window": 50,
            "threshold": 0.02,
            "trend_strategy": "momentum",
            "range_strategy": "mean_reversion",
        },
        "optimization_ranges": {
            "regime_window": [20, 50, 100],
            "threshold": [0.01, 0.02, 0.05],
        },
    },
    "ensemble": {
        "name": "Ensemble Strategy",
        "description": "SMA/RSI/MACD 加权投票（needs 投票/权重聚合）",
        "parameters": {
            "fast_period": 10,
            "slow_period": 20,
            "rsi_period": 14,
            "weight_method": "equal",
        },
        "optimization_ranges": {
            "fast_period": [5, 10, 15],
            "slow_period": [20, 30, 50],
            "rsi_period": [7, 14, 21],
        },
    },
}


def get_strategy_template(strategy_type: str) -> dict[str, Any]:
    """按类型取策略模板。未知抛 ValueError 列出可用项。"""
    if strategy_type not in STRATEGY_TEMPLATES:
        raise ValueError(
            f"Unknown strategy type: {strategy_type}. Available: {', '.join(STRATEGY_TEMPLATES)}"
        )
    return STRATEGY_TEMPLATES[strategy_type]


def list_available_strategies() -> list[str]:
    """所有可用策略类型。"""
    return list(STRATEGY_TEMPLATES.keys())


def get_strategy_info(strategy_type: str) -> dict[str, Any]:
    """策略信息（type/name/description/default_parameters/optimization_ranges）。"""
    t = get_strategy_template(strategy_type)
    return {
        "type": strategy_type,
        "name": t["name"],
        "description": t["description"],
        "default_parameters": t["parameters"],
        "optimization_ranges": t["optimization_ranges"],
    }


def generate_signals(
    strategy_type: str, parameters: dict[str, Any] | None, df: pd.DataFrame
) -> tuple[pd.Series, pd.Series]:
    """生成 (entries, exits) 布尔 Series。纯 pandas，无 vectorbt。

    高级策略（online_learning/regime_aware/ensemble）抛 NotImplementedError，
    因需 ML/regime/投票聚合，超出纯 pandas 范围。
    """
    tpl = get_strategy_template(strategy_type)
    params = {**tpl["parameters"], **(parameters or {})}

    gen = _GENERATORS.get(strategy_type)
    if gen is None:
        raise NotImplementedError(
            f"策略 '{strategy_type}' 为高级形态（{tpl['description']}），"
            f"纯 pandas 生成器未实现，需 ML/regime/集成模块。"
        )
    return gen(df, params)
