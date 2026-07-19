"""蒙特卡洛（bootstrap 重采样）回测稳健性（移植 maverick 算法层，纯 numpy）。

maverick 的 monte_carlo_simulation 依赖 vectorbt；本模块用纯 numpy 重写
**等价算法**：对回测的交易收益序列做 N 次有放回重采样，重算累计收益，
产出 total_return 的置信区间与中位数。无 vectorbt 依赖。
"""

from __future__ import annotations

from typing import Any

import numpy as np


def monte_carlo(
    trade_returns: list[float] | np.ndarray,
    n_sims: int = 1000,
    initial_capital: float = 100_000.0,
    seed: int | None = 42,
) -> dict[str, Any]:
    """对交易收益序列 bootstrap 重采样，产出 total_return 置信区间。

    每次模拟：从 trade_returns 有放回采样 len(trade_returns) 次，复合成
    等权累计收益（每次按固定 fraction 复合，近似满仓逐笔）。

    返回 ``{n_sims, median_return, mean_return, p5, p25, p75, p95, std}``。
    """
    arr = np.asarray(trade_returns, dtype=float)
    if arr.size == 0:
        return {
            "n_sims": n_sims,
            "median_return": 0.0,
            "mean_return": 0.0,
            "p5": 0.0,
            "p25": 0.0,
            "p75": 0.0,
            "p95": 0.0,
            "std": 0.0,
            "samples": [],
        }

    rng = np.random.default_rng(seed)
    n_trades = arr.size
    # 每次模拟采样 n_trades 笔收益，按乘积累乘（复利）
    samples = rng.choice(arr, size=(n_sims, n_trades), replace=True)
    # 复合收益：(1+r1)*(1+r2)*... - 1，按笔等权（近似每次全仓进出）
    compounded = np.prod(1.0 + samples, axis=1) - 1.0

    return {
        "n_sims": n_sims,
        "median_return": float(np.median(compounded)),
        "mean_return": float(np.mean(compounded)),
        "p5": float(np.percentile(compounded, 5)),
        "p25": float(np.percentile(compounded, 25)),
        "p75": float(np.percentile(compounded, 75)),
        "p95": float(np.percentile(compounded, 95)),
        "std": float(np.std(compounded)),
        "positive_pct": float((compounded > 0).mean()),
    }
