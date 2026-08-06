"""Backtesting port tests: signals -> engine -> walk_forward -> monte_carlo -> parser.

Run via ``python -m tests.test_backtesting`` or pytest."""

import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.services.backtesting.engine import run_backtest  # noqa: E402
from app.services.backtesting.monte_carlo import monte_carlo  # noqa: E402
from app.services.backtesting.parser import StrategyParser  # noqa: E402
from app.services.backtesting.strategies import (  # noqa: E402
    generate_signals,
    list_available_strategies,
)
from app.services.backtesting.walk_forward import walk_forward  # noqa: E402


def _trending_df(n: int = 300, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    # mild uptrend with noise so SMA crossover fires
    close = pd.Series(np.cumsum(rng.normal(0.05, 1.0, n)) + 100, index=idx)
    high = close + rng.uniform(0.5, 1.5, n)
    low = close - rng.uniform(0.5, 1.5, n)
    volume = pd.Series(rng.integers(1000, 5000, n), index=idx)
    df = pd.concat({"close": close, "high": high, "low": low, "volume": volume}, axis=1)
    return df


def main() -> int:
    failures: list[str] = []

    def check(label, cond):
        print(f"  {'PASS' if cond else 'FAIL'}: {label}")
        if not cond:
            failures.append(label)

    # 1. strategies list + signal generation
    check(">=9 strategies available", len(list_available_strategies()) >= 9)
    df = _trending_df()
    entries, exits = generate_signals("sma_cross", {"fast_period": 10, "slow_period": 30}, df)
    check("sma_cross signals are bool Series", entries.dtype == bool and exits.dtype == bool)
    check("sma_cross fires some entries", entries.sum() > 0)

    # ML/regime/ensemble raise NotImplementedError
    try:
        generate_signals("ensemble", None, df)
        check("ensemble raises NotImplementedError", False)
    except NotImplementedError:
        check("ensemble raises NotImplementedError", True)

    # 2. engine
    m = run_backtest(df, entries, exits, initial_capital=100_000, fees=0.001)
    d = m.to_dict()
    check("backtest produces metrics", "total_return" in d and "sharpe" in d)
    check("trade_count >= 0", m.trade_count >= 0)
    check("final_equity > 0", m.final_equity > 0)
    check("max_drawdown in [0,1]", 0 <= m.max_drawdown <= 1)

    # 3. walk_forward
    wf = walk_forward(df, entries, exits, window=120, step=60)
    check("walk_forward ran windows", wf["windows"] >= 1 and "mean_return" in wf)
    check("walk_forward positive_pct in [0,1]", 0 <= wf["positive_pct"] <= 1)

    # 4. monte_carlo
    trades = [0.02, -0.01, 0.03, 0.01, -0.02, 0.04, 0.01, -0.005]
    mc = monte_carlo(trades, n_sims=200, seed=7)
    check("monte_carlo returns percentiles", all(k in mc for k in ("p5", "p95", "median_return")))
    check("monte_carlo p5 <= median <= p95", mc["p5"] <= mc["median_return"] <= mc["p95"])

    # 5. parser (rule-based)
    sp = StrategyParser()
    cfg = sp.parse_simple("用 10 和 30 的 SMA 金叉策略")
    check("parser sma_cross + periods", cfg["strategy_type"] == "sma_cross"
          and cfg["parameters"]["fast_period"] == 10
          and cfg["parameters"]["slow_period"] == 30)
    cfg2 = sp.parse_simple("RSI 14 超卖 30 买入超买 70 卖出")
    check("parser rsi", cfg2["strategy_type"] == "rsi"
          and cfg2["parameters"]["period"] == 14
          and cfg2["parameters"]["oversold"] == 30)
    check("validate_strategy valid config", sp.validate_strategy(cfg))
    check("validate_strategy rejects bad", not sp.validate_strategy({"strategy_type": "nope", "parameters": {}}))

    print(f"\n{'ALL PASSED' if not failures else 'FAILURES: '+str(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())


def test_backtesting_port():
    assert main() == 0


def test_no_lookahead_last_bar_signal_does_not_fill():
    """ISSUE-021: a signal on the LAST bar cannot fill (no next bar to trade
    at), proving T+1 execution. Old same-bar code would fill at the last close.
    """
    idx = pd.date_range("2024-01-01", periods=3, freq="B")
    df = pd.DataFrame({"close": [10.0, 11.0, 12.0]}, index=idx)
    entries = pd.Series([True, False, False], index=idx)
    exits = pd.Series([False, False, True], index=idx)  # exit signal on last bar
    m = run_backtest(df, entries, exits, initial_capital=100_000, fees=0.0)
    # Entry signal bar0 -> fills at bar1 (close=11, no open col). Exit signal
    # bar2 (last) -> no bar3 -> NOT filled. So 0 realized trades, position
    # held to end, final equity = shares * close[-1] = (100000/11)*12.
    assert m.trade_count == 0, "last-bar exit must not fill (T+1, no look-ahead)"
    assert m.final_equity > 0
    assert abs(m.final_equity - (100_000 / 11.0) * 12.0) < 1e-6


def test_no_lookahead_entry_fills_next_bar_open():
    """ISSUE-021: entry signal at bar i fills at bar i+1 open, not bar i close.
    With close=[10,11,12] and open=[10,20,12], a bar-0 entry must fill at
    open[1]=20 (next bar), not close[0]=10 (same bar = look-ahead)."""
    idx = pd.date_range("2024-01-01", periods=3, freq="B")
    df = pd.DataFrame({"open": [10.0, 20.0, 12.0], "close": [10.0, 11.0, 12.0]}, index=idx)
    entries = pd.Series([True, False, False], index=idx)
    exits = pd.Series([False, True, False], index=idx)  # exit bar1 -> fills bar2 open
    m = run_backtest(df, entries, exits, initial_capital=100_000, fees=0.0)
    # Entry fills at open[1]=20; exit fills at open[2]=12 -> loss. trade_count=1.
    assert m.trade_count == 1
    # ret = (12 - 20)/20 = -0.4 -> final = 100000 * (1 - 0.4) = 60000
    assert abs(m.final_equity - 60_000.0) < 1e-6, m.final_equity


async def test_parser_llm_fallback():
    # No LLM configured -> falls back to parse_simple (no exception)
    sp = StrategyParser(llm=None)
    res = await sp.parse_with_llm("sma crossover 5 and 20")
    assert res["strategy_type"] == "sma_cross"
