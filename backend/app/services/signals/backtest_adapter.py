"""信号↔回测适配（移植自 maverick-mcp，MIT License Copyright (c) 2024）。

源文件：`maverick_mcp/services/signals/backtest_adapter.py`。
适配点：原版继承 `maverick_mcp.backtesting.strategies.base.Strategy` 抽象基类；
本平台无该基类，改为独立函数。**核心算法保留**：逐 bar 调
`evaluate_condition` 并跨 bar 传递 `previous_state`（crosses_* 有状态算子必须），
对 triggered 序列做边沿检测生成 entries/exits。再喂给本平台 `run_backtest`。

打通"告警条件设计 → 历史复盘"：把已保存的信号条件当策略回放，
产出 total_return/sharpe/max_dd/win_rate。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.backtesting.engine import BacktestMetrics, run_backtest
from app.services.signals.conditions import evaluate_condition


def normalize_ohlcv_columns(data: pd.DataFrame) -> pd.DataFrame:
    """把 Close/Volume 等标题大小写列名规范为小写 close/volume。

    OHLCV 来自不同数据源可能标题大小写不一；signals 引擎只认小写。
    """
    rename: dict[str, str] = {}
    for col in data.columns:
        lower = str(col).lower()
        if lower in {"close", "volume"} and col != lower:
            rename[col] = lower
    if rename:
        return data.rename(columns=rename)
    return data


def generate_signal_condition_signals(
    condition: dict[str, Any], data: pd.DataFrame, *, label: str | None = None
) -> tuple[pd.Series, pd.Series]:
    """把信号 condition dict 转 (entries, exits) 布尔 Series，与 data.index 对齐。

    逐 bar 用到当前为止的窗口调 evaluate_condition，跨 bar 传 previous_state
    （crosses_above/crosses_below 必须如此）。triggered 序列边沿检测：
    - entry：本 bar triggered 且上 bar 未 triggered
    - exit：本 bar 未 triggered 且上 bar triggered

    stateful 算子在 bar 0 不触发（首次仅播种状态）；stateless 算子若 bar 0
    即满足条件则 bar 0 即 entry（与 live SignalService 一致）。
    """
    normalized = normalize_ohlcv_columns(data)

    triggered_mask: list[bool] = []
    previous_state: dict[str, Any] | None = None

    for i in range(len(normalized)):
        window = normalized.iloc[: i + 1]
        result = evaluate_condition(condition, window, previous_state=previous_state)
        triggered_mask.append(bool(result.get("triggered", False)))
        new_state = result.get("new_state")
        if new_state is not None:
            previous_state = new_state

    triggered = pd.Series(triggered_mask, index=normalized.index)
    prior = triggered.shift(fill_value=False).astype(bool)
    entries = triggered & ~prior
    exits = ~triggered & prior
    return entries, exits


def backtest_signal_condition(
    condition: dict[str, Any],
    data: pd.DataFrame,
    *,
    initial_capital: float = 100_000.0,
    fees: float = 0.001,
    label: str | None = None,
) -> BacktestMetrics:
    """把信号条件当策略回放，跑本平台回测引擎，返回指标。

    用于"此告警历史复盘"：先设计告警条件，回测验证其在历史数据上的
    return/sharpe/max_drawdown/win_rate，再决定是否部署为 live signal。
    """
    entries, exits = generate_signal_condition_signals(condition, data, label=label)
    return run_backtest(data, entries, exits, initial_capital=initial_capital, fees=fees)
