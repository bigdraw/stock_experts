"""纯 pandas/numpy 回测引擎（替代 maverick 的 vectorbt 引擎层）。

maverick 的 `vectorbt_engine.py` 依赖 **vectorbtpro（付费，免费版在 Python 3.12
因 numba/llvmlite 装不上）**——不可直接移植。本模块用纯 pandas/numpy 重写
**等价的最小组合模拟器**：按 entries/exits 信号在收盘价上模拟持仓，含摩擦成本，
产出与 vectorbt 同名的核心指标（total_return / sharpe / max_drawdown /
win_rate / trade_count / avg_win / profit_factor）。

不算 vectorbt 的全量能力（参数寻优/ML），但足以驱动 walk_forward/monte_carlo。
对齐 maverick 的指标语义便于对照。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class BacktestMetrics:
    total_return: float
    annualized_return: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    trade_count: int
    avg_win: float
    avg_loss: float
    profit_factor: float
    final_equity: float
    n_bars: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_return": round(self.total_return, 4),
            "annualized_return": round(self.annualized_return, 4),
            "sharpe": round(self.sharpe, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "win_rate": round(self.win_rate, 4),
            "trade_count": self.trade_count,
            "avg_win": round(self.avg_win, 4),
            "avg_loss": round(self.avg_loss, 4),
            "profit_factor": round(self.profit_factor, 4),
            "final_equity": round(self.final_equity, 4),
            "n_bars": self.n_bars,
        }


def run_backtest(
    df: pd.DataFrame,
    entries: pd.Series,
    exits: pd.Series,
    initial_capital: float = 100_000.0,
    fees: float = 0.001,  # 单边手续费率
    annualization: int = 252,
    close_col: str = "close",
) -> BacktestMetrics:
    """按 entries/exits 在 close 上模拟一个 always-in 策略的权益曲线。

    简化语义（与 vectorbt from_signals 的 orders=False 一致）：
    - entry 信号日次根开盘建仓（这里近似用当日 close 建仓），exit 信号日 close 平仓。
    - 始终满仓（all-in）；未持仓时 entry 触发建仓，持仓时 exit 触发平仓。
    - 每笔交易按成交额收 fees 单边费。
    """
    close = df[close_col] if close_col in df.columns else df["Close"]
    n = len(close)
    if n == 0:
        return BacktestMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, initial_capital, 0)

    # 对齐索引
    entries = entries.reindex(close.index).fillna(False).astype(bool)
    exits = exits.reindex(close.index).fillna(False).astype(bool)

    position = False
    cash = float(initial_capital)
    shares = 0.0
    entry_price = 0.0
    equity_curve = np.empty(n)
    trade_returns: list[float] = []

    for i in range(n):
        px = float(close.iloc[i])
        # 平仓（先处理 exit）
        if position and exits.iloc[i]:
            proceeds = shares * px
            cash += proceeds * (1 - fees)
            ret = (px - entry_price) / entry_price if entry_price > 0 else 0.0
            trade_returns.append(ret)
            shares = 0.0
            position = False

        # 建仓
        if (not position) and entries.iloc[i]:
            shares = (cash * (1 - fees)) / px if px > 0 else 0.0
            cash = 0.0
            entry_price = px
            position = True

        equity_curve[i] = cash + (shares * px if position else 0.0)

    # 若末尾仍持仓，按末价平仓记账（不收手续费，仅估值）
    if position and entry_price > 0:
        px = float(close.iloc[-1])
        trade_returns.append((px - entry_price) / entry_price)

    equity = pd.Series(equity_curve, index=close.index)
    final_equity = float(equity.iloc[-1])
    total_return = (final_equity - initial_capital) / initial_capital

    # Sharpe：日收益率均值/标准差 * sqrt(年化)
    rets = equity.pct_change().dropna()
    if len(rets) > 1 and rets.std() > 0:
        sharpe = float(rets.mean() / rets.std() * math.sqrt(annualization))
    else:
        sharpe = 0.0

    annualized_return = (1 + total_return) ** (annualization / max(n, 1)) - 1 if n > 0 else 0.0

    # 最大回撤
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_drawdown = float(abs(drawdown.min())) if len(drawdown) > 0 else 0.0

    # 交易统计
    wins = [r for r in trade_returns if r > 0]
    losses = [r for r in trade_returns if r < 0]
    win_rate = len(wins) / len(trade_returns) if trade_returns else 0.0
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    profit_factor = 1e9 if profit_factor == float("inf") else profit_factor

    return BacktestMetrics(
        total_return=total_return,
        annualized_return=annualized_return,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        trade_count=len(trade_returns),
        avg_win=avg_win,
        avg_loss=avg_loss,
        profit_factor=profit_factor,
        final_equity=final_equity,
        n_bars=n,
    )
