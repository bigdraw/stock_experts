"""Backtesting engine."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import DailyQuote
from app.services.filter.sandbox import FilterSandbox

logger = logging.getLogger(__name__)


@dataclass
class FrictionConfig:
    stamp_tax: float = 0.0005
    commission: float = 0.00025
    commission_min: float = 5.0
    slippage: float = 0.001


@dataclass
class BacktestResult:
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int
    final_capital: float
    equity_curve: list[dict]
    trade_log: list[dict]


class BacktestEngine:
    """Execute backtest with generated strategy code."""

    def __init__(self, db: AsyncSession, friction: FrictionConfig | None = None):
        self.db = db
        self.friction = friction or FrictionConfig()
        self.sandbox = FilterSandbox()

    async def run(
        self,
        strategy_code: str,
        stock_codes: list[str],
        start_date: str,
        end_date: str,
        initial_capital: float = 1_000_000,
    ) -> BacktestResult:
        """Execute backtest."""
        # 1. Load historical data
        market_data = await self._load_market_data(stock_codes, start_date, end_date)
        if market_data.empty:
            raise ValueError("No market data available for the given stocks and date range")

        trading_dates = sorted(market_data["date"].unique())

        # 2. Compile strategy
        safe_globals = {
            "__builtins__": {"len": len, "range": range, "enumerate": enumerate, "zip": zip,
                            "map": map, "filter": filter, "sorted": sorted, "sum": sum,
                            "min": min, "max": max, "abs": abs, "round": round,
                            "int": int, "float": float, "str": str, "bool": bool,
                            "list": list, "dict": dict, "set": set, "tuple": tuple,
                            "True": True, "False": False, "None": None},
            "pd": pd,
            "np": np,
        }
        exec(strategy_code, safe_globals)
        init_fn = safe_globals.get("init_strategy")
        select_fn = safe_globals.get("select_stocks")
        signal_fn = safe_globals.get("generate_signals")

        config = init_fn() if init_fn else {}

        # 3. Simulate day by day
        cash = initial_capital
        portfolio: dict[str, dict] = {}  # {code: {shares, avg_cost}}
        equity_curve = []
        trade_log = []

        for date in trading_dates:
            day_data = market_data[market_data["date"] == date]

            # Update portfolio value
            for code, pos in portfolio.items():
                stock_data = day_data[day_data["code"] == code]
                if not stock_data.empty:
                    pos["current_price"] = float(stock_data.iloc[0]["close"])

            # Select stocks (if function exists)
            if select_fn:
                try:
                    context = {"date": date, "holdings": list(portfolio.keys())}
                    selected = select_fn(day_data, context)
                except Exception as e:
                    logger.warning(f"select_stocks error on {date}: {e}")
                    selected = []
            else:
                selected = stock_codes

            # Generate signals
            if signal_fn:
                for code in set(list(portfolio.keys()) + list(selected)):
                    stock_hist = market_data[(market_data["code"] == code) & (market_data["date"] <= date)]
                    try:
                        context = {
                            "code": code,
                            "current_position": portfolio.get(code, {"shares": 0, "avg_cost": 0}),
                        }
                        signals = signal_fn(stock_hist, context)
                        for signal in signals:
                            trade = self._execute_trade(
                                signal, portfolio, cash, day_data, date
                            )
                            if trade:
                                cash = trade["remaining_cash"]
                                trade_log.append(trade["record"])
                    except Exception as e:
                        logger.warning(f"generate_signals error for {code} on {date}: {e}")

            # Record equity
            portfolio_value = sum(
                pos.get("shares", 0) * pos.get("current_price", 0)
                for pos in portfolio.values()
            )
            equity_curve.append({"date": str(date), "value": cash + portfolio_value})

        # 4. Calculate metrics
        metrics = self._calculate_metrics(equity_curve, trade_log, initial_capital)
        return BacktestResult(
            equity_curve=equity_curve,
            trade_log=trade_log,
            **metrics,
        )

    def _execute_trade(self, signal: dict, portfolio: dict, cash: float, day_data: pd.DataFrame, date) -> dict | None:
        """Execute a single trade with friction costs."""
        code = signal.get("code")
        action = signal.get("action")
        shares = signal.get("shares", 0)

        stock_data = day_data[day_data["code"] == code]
        if stock_data.empty:
            return None
        price = float(stock_data.iloc[0]["close"])

        if action == "buy":
            actual_price = price * (1 + self.friction.slippage)
            amount = shares * actual_price
            commission = max(amount * self.friction.commission, self.friction.commission_min)
            total_cost = amount + commission

            if cash < total_cost:
                return None

            cash -= total_cost
            if code in portfolio:
                old = portfolio[code]
                total_shares = old["shares"] + shares
                avg_cost = (old["avg_cost"] * old["shares"] + actual_price * shares) / total_shares
                portfolio[code] = {"shares": total_shares, "avg_cost": avg_cost, "current_price": price}
            else:
                portfolio[code] = {"shares": shares, "avg_cost": actual_price, "current_price": price}

            return {
                "remaining_cash": cash,
                "record": {"date": str(date), "action": "buy", "code": code, "price": actual_price,
                          "shares": shares, "cost": commission, "reason": signal.get("reason", "")},
            }

        elif action == "sell":
            if code not in portfolio:
                return None
            pos = portfolio[code]
            sell_shares = min(shares, pos["shares"]) if shares != "all" else pos["shares"]
            actual_price = price * (1 - self.friction.slippage)
            amount = sell_shares * actual_price
            commission = max(amount * self.friction.commission, self.friction.commission_min)
            stamp_tax = amount * self.friction.stamp_tax
            net_proceeds = amount - commission - stamp_tax

            cash += net_proceeds
            pnl = (actual_price - pos["avg_cost"]) * sell_shares - commission - stamp_tax

            if sell_shares >= pos["shares"]:
                del portfolio[code]
            else:
                portfolio[code]["shares"] -= sell_shares

            return {
                "remaining_cash": cash,
                "record": {"date": str(date), "action": "sell", "code": code, "price": actual_price,
                          "shares": sell_shares, "cost": commission + stamp_tax, "pnl": pnl,
                          "reason": signal.get("reason", "")},
            }
        return None

    def _calculate_metrics(self, equity_curve: list[dict], trade_log: list[dict], initial_capital: float) -> dict:
        """Calculate backtest performance metrics."""
        if not equity_curve:
            return {
                "total_return": 0, "annualized_return": 0, "max_drawdown": 0,
                "sharpe_ratio": 0, "win_rate": 0, "total_trades": 0, "final_capital": initial_capital,
            }

        values = [e["value"] for e in equity_curve]
        final = values[-1]
        total_return = (final - initial_capital) / initial_capital
        days = len(values)
        annualized_return = (1 + total_return) ** (252 / max(days, 1)) - 1

        # Max drawdown
        peak = values[0]
        max_dd = 0
        for v in values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd

        # Sharpe ratio (risk-free rate 3%)
        daily_returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]
        if daily_returns:
            avg_ret = np.mean(daily_returns)
            std_ret = np.std(daily_returns)
            sharpe = (avg_ret - 0.03/252) / std_ret * np.sqrt(252) if std_ret > 0 else 0
        else:
            sharpe = 0

        # Win rate
        sell_trades = [t for t in trade_log if t.get("action") == "sell" and "pnl" in t]
        winning = [t for t in sell_trades if t["pnl"] > 0]
        win_rate = len(winning) / len(sell_trades) if sell_trades else 0

        return {
            "total_return": round(total_return, 4),
            "annualized_return": round(annualized_return, 4),
            "max_drawdown": round(max_dd, 4),
            "sharpe_ratio": round(sharpe, 2),
            "win_rate": round(win_rate, 4),
            "total_trades": len(trade_log),
            "final_capital": round(final, 2),
        }

    async def _load_market_data(self, stock_codes: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        """Load market data into DataFrame."""
        result = await self.db.execute(
            select(DailyQuote).where(
                DailyQuote.stock_code.in_(stock_codes),
                DailyQuote.date >= datetime.strptime(start_date, "%Y-%m-%d").date(),
                DailyQuote.date <= datetime.strptime(end_date, "%Y-%m-%d").date(),
            )
        )
        quotes = result.scalars().all()
        if not quotes:
            return pd.DataFrame()

        data = [{
            "code": q.stock_code,
            "date": q.date,
            "open": q.open,
            "high": q.high,
            "low": q.low,
            "close": q.close,
            "volume": q.volume,
            "amount": q.amount,
        } for q in quotes]
        return pd.DataFrame(data)
