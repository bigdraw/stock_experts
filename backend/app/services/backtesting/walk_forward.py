"""滚动样本外（walk-forward）回测（移植 maverick 算法层，纯 numpy/pandas）。

maverick 的 walk_forward_analysis 依赖 vectorbt；本模块用纯 pandas 重写
**等价算法**：把价格序列切成滚动窗口，每个窗口用前段参数/信号在样本外段
回测，聚合窗口收益的均值与稳定性。无 vectorbt 依赖。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.services.backtesting.engine import run_backtest


def walk_forward(
    df: pd.DataFrame,
    entries: pd.Series,
    exits: pd.Series,
    window: int = 252,
    step: int = 63,
    initial_capital: float = 100_000.0,
    fees: float = 0.001,
) -> dict[str, Any]:
    """滚动样本外回测，聚合每窗 total_return/sharpe/max_dd 的分布。

    Args:
        window: 每窗 bar 数（默认 252≈1 年）。
        step: 滚动步长（默认 63≈季度）。
    返回 ``{windows, returns, mean_return, std_return, positive_pct, ...}``。
    """
    n = len(df)
    if n < window:
        return {"windows": 0, "error": f"数据不足（{n} < window {window}）"}

    results: list[dict[str, Any]] = []
    returns: list[float] = []
    sharpes: list[float] = []
    max_dds: list[float] = []

    for start in range(0, n - window + 1, step):
        end = start + window
        sub_df = df.iloc[start:end]
        sub_e = entries.iloc[start:end]
        sub_x = exits.iloc[start:end]
        m = run_backtest(sub_df, sub_e, sub_x, initial_capital, fees)
        results.append({"start": start, "end": end, "metrics": m.to_dict()})
        returns.append(m.total_return)
        sharpes.append(m.sharpe)
        max_dds.append(m.max_drawdown)

    returns_arr = np.array(returns) if returns else np.array([])
    return {
        "windows": len(results),
        "window_size": window,
        "step": step,
        "returns": returns,
        "mean_return": float(returns_arr.mean()) if len(returns_arr) else 0.0,
        "std_return": float(returns_arr.std()) if len(returns_arr) > 1 else 0.0,
        "min_return": float(returns_arr.min()) if len(returns_arr) else 0.0,
        "max_return": float(returns_arr.max()) if len(returns_arr) else 0.0,
        "positive_pct": float((returns_arr > 0).mean()) if len(returns_arr) else 0.0,
        "mean_sharpe": float(np.mean(sharpes)) if sharpes else 0.0,
        "mean_max_drawdown": float(np.mean(max_dds)) if max_dds else 0.0,
        "per_window": results,
    }
