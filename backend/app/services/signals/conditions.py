"""结构化信号条件引擎（移植自 maverick-mcp，MIT License Copyright (c) 2024）。

源文件：`maverick_mcp/services/signals/conditions.py`。
适配点：原版 `import pandas_ta as ta`（注册 pandas accessor，提供 ta.rsi/ta.sma）
在本平台替换为纯 pandas/numpy 的 `app.services.technical.indicators`（无编译依赖）。

把"告警"从单一"价格<X"升级为统一条件模型 + 跨次状态（crosses_above/crosses_below）。
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from app.services.technical.indicators import rsi as _rsi
from app.services.technical.indicators import sma as _sma

logger = logging.getLogger(__name__)


def evaluate_condition(
    condition: dict[str, Any],
    data: pd.DataFrame,
    previous_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """对市场数据求值一个信号条件。

    Args:
        condition: 描述条件的 dict。必需键：
            - ``indicator``: ``price`` / ``rsi`` / ``volume`` / ``sma``
            - ``operator``: ``lt`` / ``gt`` / ``lte`` / ``gte`` / ``spike`` /
              ``crosses_above`` / ``crosses_below``
            - ``threshold``: 数值阈值（``spike`` 不需要）
            - ``period``: RSI/SMA 计算周期（RSI 默认 14，SMA 默认 20）
            - ``std_devs``: spike 的标准差倍数（默认 2.0）
        data: 至少含 ``close`` 列、可选 ``volume`` 列的 DataFrame。
        previous_state: 跨次状态（如 ``was_above``），给 crosses_* 有状态算子用。

    Returns:
        ``{triggered, current_value, new_state, error}``。``new_state`` 需持久化
        以供下次 crosses_* 求值。
    """
    empty: dict[str, Any] = {
        "triggered": False,
        "current_value": 0.0,
        "new_state": None,
        "error": None,
    }

    if data is None or data.empty:
        return {**empty, "error": "No data provided"}

    indicator = condition.get("indicator", "price")
    operator = condition.get("operator", "gt")
    threshold = condition.get("threshold")
    period = condition.get("period")
    std_devs = float(condition.get("std_devs", 2.0))

    try:
        current_value = _compute_indicator(data, indicator, period)
    except Exception as exc:
        return {**empty, "error": f"Unknown indicator '{indicator}': {exc}"}

    try:
        triggered, new_state = _apply_operator(
            operator=operator,
            current_value=current_value,
            threshold=threshold,
            data=data,
            indicator=indicator,
            period=period,
            std_devs=std_devs,
            previous_state=previous_state,
        )
    except ValueError as exc:
        return {**empty, "current_value": float(current_value), "error": str(exc)}

    return {
        "triggered": triggered,
        "current_value": float(current_value),
        "new_state": new_state,
        "error": None,
    }


def _compute_indicator(data: pd.DataFrame, indicator: str, period: int | None) -> float:
    """返回 *indicator* 在 *data* 上的最新值。"""
    if indicator == "price":
        return float(data["close"].iloc[-1])

    if indicator == "volume":
        return float(data["volume"].iloc[-1])

    if indicator == "rsi":
        rsi_period = period or 14
        rsi_series = _rsi(data["close"], rsi_period)
        if rsi_series is None or rsi_series.dropna().empty:
            raise ValueError("Not enough data to compute RSI")
        return float(rsi_series.dropna().iloc[-1])

    if indicator == "sma":
        sma_period = period or 20
        sma_series = _sma(data["close"], sma_period)
        if sma_series is None or sma_series.dropna().empty:
            raise ValueError("Not enough data to compute SMA")
        return float(sma_series.dropna().iloc[-1])

    raise ValueError(f"Unknown indicator: {indicator!r}")


def _apply_operator(
    *,
    operator: str,
    current_value: float,
    threshold: float | None,
    data: pd.DataFrame,
    indicator: str,
    period: int | None,
    std_devs: float,
    previous_state: dict[str, Any] | None,
) -> tuple[bool, dict[str, Any] | None]:
    """对给定 operator 返回 (triggered, new_state)。"""
    if operator == "lt":
        thr = _require_threshold(threshold, operator)
        return current_value < thr, None

    if operator == "gt":
        thr = _require_threshold(threshold, operator)
        return current_value > thr, None

    if operator == "lte":
        thr = _require_threshold(threshold, operator)
        return current_value <= thr, None

    if operator == "gte":
        thr = _require_threshold(threshold, operator)
        return current_value >= thr, None

    if operator == "spike":
        return _evaluate_spike(current_value, data, indicator, period, std_devs), None

    if operator in ("crosses_above", "crosses_below"):
        return _evaluate_crossing(
            operator=operator,
            current_value=current_value,
            threshold=threshold,
            previous_state=previous_state,
        )

    raise ValueError(f"Unknown operator: {operator!r}")


def _require_threshold(threshold: float | None, operator: str) -> float:
    """校验 threshold 已设。"""
    if threshold is None:
        raise ValueError(f"Operator '{operator}' requires a threshold value")
    return float(threshold)


def _evaluate_spike(
    current_value: float,
    data: pd.DataFrame,
    indicator: str,
    period: int | None,
    std_devs: float,
) -> bool:
    """current_value 高于历史均值 N 个标准差则 True。"""
    if indicator == "volume":
        series = data["volume"].dropna()
    elif indicator == "price":
        series = data["close"].dropna()
    elif indicator == "rsi":
        rsi_period = period or 14
        series = _rsi(data["close"], rsi_period).dropna()
    elif indicator == "sma":
        sma_period = period or 20
        series = _sma(data["close"], sma_period).dropna()
    else:
        raise ValueError(f"Unknown indicator for spike: {indicator!r}")

    if len(series) < 2:
        return False

    mean = float(series.mean())
    std = float(series.std())
    if std == 0:
        return False
    return current_value > mean + std_devs * std


def _evaluate_crossing(
    *,
    operator: str,
    current_value: float,
    threshold: float | None,
    previous_state: dict[str, Any] | None,
) -> tuple[bool, dict[str, Any]]:
    """用 previous_state 求值 crosses_above / crosses_below（有状态）。"""
    if threshold is None:
        raise ValueError(f"Operator '{operator}' requires a threshold value")

    is_above_now = current_value > threshold
    new_state = {"was_above": is_above_now, "last_value": current_value}

    if previous_state is None:
        # 无历史——记录状态但不触发
        return False, new_state

    was_above = bool(previous_state.get("was_above", not is_above_now))

    if operator == "crosses_above":
        triggered = not was_above and is_above_now
    else:  # crosses_below
        triggered = was_above and not is_above_now

    return triggered, new_state
