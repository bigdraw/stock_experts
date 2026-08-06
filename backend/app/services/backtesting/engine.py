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
    equity_curve: list  # [(date_str, equity), ...] 供前端画权益曲线

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
            "equity_curve": self.equity_curve,
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
    """按 entries/exits 模拟一个 always-in 策略的权益曲线（T+1 成交，无 look-ahead）。

    ISSUE-021: 信号在 bar i 收盘生成（entries/exits 是基于 close 算的 bool
    Series）→ 必须在 bar i+1 的开盘成交，不能在 bar i 收盘成交（那会用未来
    数据：信号当日收盘才确定，现实只能次日开盘买）。旧实现同 bar 收盘成交，
    系统性高估趋势/均值回归策略收益。现在 T+1：bar i 信号 → bar i+1 open
    成交；无 open 列时退回 bar i+1 close（仍 T+1，无未来函数）。
    bar i+1 不存在（信号在最后一天）则不成交（无法在次日成交）。

    语义（与 vectorbt from_signals orders=False 一致）：
    - 始终满仓（all-in）；未持仓时 entry 触发建仓，持仓时 exit 触发平仓。
    - 每笔成交按成交额收 fees 单边费。
    - 末笔未平仓不计入 trade_returns（仅按末价 mark-to-close 进 equity），
      避免把浮盈当已实现虚增 win_rate/profit_factor（ISSUE-030 M3）。
    """
    close = df[close_col] if close_col in df.columns else df["Close"]
    n = len(close)
    if n == 0:
        return BacktestMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, initial_capital, 0)

    # 对齐索引
    entries = entries.reindex(close.index).fillna(False).astype(bool)
    exits = exits.reindex(close.index).fillna(False).astype(bool)
    # T+1 成交价：信号日的次日开盘（无 open 列退回次日 close）。
    open_col = "open" if "open" in df.columns else close_col
    fill_px_series = df[open_col] if open_col in df.columns else close

    position = False
    cash = float(initial_capital)
    shares = 0.0
    entry_price = 0.0
    pending_entry = False
    pending_exit = False
    equity_curve = np.empty(n)
    trade_returns: list[float] = []

    for i in range(n):
        px_close = float(close.iloc[i])

        # 1) 成交上一根信号（bar i-1 的 entry/exit）于 bar i 开盘
        if i > 0:
            fill_px = float(fill_px_series.iloc[i])
            if fill_px > 0:
                if pending_exit and position:
                    proceeds = shares * fill_px
                    cash += proceeds * (1 - fees)
                    ret = (fill_px - entry_price) / entry_price if entry_price > 0 else 0.0
                    trade_returns.append(ret)
                    shares = 0.0
                    position = False
                elif pending_entry and not position:
                    shares = (cash * (1 - fees)) / fill_px
                    cash = 0.0
                    entry_price = fill_px
                    position = True
            pending_entry = False
            pending_exit = False

        # 2) 评估 bar i 收盘信号 → 安排 bar i+1 开盘成交（T+1，无 look-ahead）
        if position and exits.iloc[i]:
            pending_exit = True
        elif (not position) and entries.iloc[i]:
            pending_entry = True

        # 3) mark-to-close 权益
        equity_curve[i] = cash + (shares * px_close if position else 0.0)

    # 末笔未平仓：仅 mark-to-close 已进 equity_curve[-1]，不计入 trade_returns
    # （避免浮盈当已实现虚增 win_rate/profit_factor，ISSUE-030 M3）。

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
    profit_factor = (
        gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    )
    profit_factor = 1e9 if profit_factor == float("inf") else profit_factor

    # 权益曲线供前端绘制（date, equity）；长序列降采样到 ~200 点避免 payload 过大
    eq_index = equity.index
    eq_values = equity.tolist()
    if len(eq_values) > 200:
        step = max(1, len(eq_values) // 200)
        idxs = list(range(0, len(eq_values), step)) + [len(eq_values) - 1]
        eq_pairs = [
            (str(eq_index[i].date()) if hasattr(eq_index[i], "date") else str(eq_index[i]), round(eq_values[i], 2))
            for i in idxs
        ]
    else:
        eq_pairs = [
            (str(t.date()) if hasattr(t, "date") else str(t), round(v, 2))
            for t, v in zip(eq_index, eq_values, strict=False)
        ]

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
        equity_curve=eq_pairs,
    )
