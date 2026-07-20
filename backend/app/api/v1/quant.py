"""Quant API — exposes the maverick-ported modules (signals/screening/journal/
risk/audit/backtesting) as FastAPI endpoints.

Auth policy:
- Read-only compute (indicators/regime/screening/risk/backtest/signals/strategies)
  -> any logged-in user (Depends(get_current_user)).
- DB writes / cost audit (journal trades, strategy recompute, decision log read)
  -> admin only (require_admin). journal/audit 模型写入需 init_db 建表——
  本路由 import 即触发模型注册到 Base.metadata。
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.services.audit.logger import DecisionLogger  # noqa: F401 (registers model)
from app.services.backtesting.engine import run_backtest
from app.services.backtesting.monte_carlo import monte_carlo
from app.services.backtesting.parser import StrategyParser
from app.services.backtesting.strategies import (
    STRATEGY_TEMPLATES,
    generate_signals,
)
from app.services.backtesting.walk_forward import walk_forward
from app.services.journal.analytics import StrategyTracker  # noqa: F401 (registers model)
from app.services.journal.models import JournalEntry
from app.services.risk.service import (
    check_position_risk,
    compute_dashboard,
    generate_alerts,
    get_regime_adjusted_size,
)
from app.services.signals import conditions as _conditions  # noqa: F401
from app.services.signals import regime as _regime  # noqa: F401
from app.services.signals.backtest_adapter import backtest_signal_condition
from app.services.signals.conditions import evaluate_condition
from app.services.signals.regime import RegimeDetector

router = APIRouter(prefix="/quant", tags=["quant"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class OHLCVBar(BaseModel):
    date: str
    close: float
    high: float | None = None
    low: float | None = None
    volume: float | None = None


class OHLCVRequest(BaseModel):
    bars: list[OHLCVBar] = Field(..., min_length=2)


def _to_df(req: OHLCVRequest) -> pd.DataFrame:
    rows = [
        {
            "date": b.date,
            "close": b.close,
            "high": b.high if b.high is not None else b.close,
            "low": b.low if b.low is not None else b.close,
            "volume": b.volume if b.volume is not None else 0.0,
        }
        for b in req.bars
    ]
    df = pd.DataFrame(rows)
    # format='mixed' tolerates slightly-inconsistent date strings; errors='coerce'
    # turns unparseable dates into NaT instead of 500-ing the whole request.
    df.index = pd.to_datetime(df["date"], format="mixed", errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Strategies + parsing (user-level)
# ---------------------------------------------------------------------------


@router.get("/strategies")
async def list_strategies(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """列出所有可用策略模板及其默认参数。"""
    return {
        name: {
            "name": t["name"],
            "description": t["description"],
            "default_parameters": t["parameters"],
            "optimization_ranges": t["optimization_ranges"],
        }
        for name, t in STRATEGY_TEMPLATES.items()
    }


class ParseRequest(BaseModel):
    description: str


@router.post("/strategies/parse")
async def parse_strategy(
    req: ParseRequest, current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """自然语言→策略类型+参数（纯规则解析，不调 LLM）。"""
    return StrategyParser().parse_simple(req.description)


# ---------------------------------------------------------------------------
# Backtesting (user-level, pure compute)
# ---------------------------------------------------------------------------


class BacktestRequest(BaseModel):
    strategy_type: str
    parameters: dict[str, Any] | None = None
    bars: list[OHLCVBar]
    initial_capital: float = 100_000.0
    fees: float = 0.001


@router.post("/backtest")
async def backtest(
    req: BacktestRequest, current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """对给定 OHLCV 跑某策略的回测，返回核心指标。"""
    df = _to_df(OHLCVRequest(bars=req.bars))
    entries, exits = generate_signals(req.strategy_type, req.parameters, df)
    m = run_backtest(df, entries, exits, req.initial_capital, req.fees)
    return {"metrics": m.to_dict(), "n_entries": int(entries.sum()), "n_exits": int(exits.sum())}


class BacktestRunRequest(BaseModel):
    """服务端取数回测：只需股票代码 + 区间 + 策略，后端拉历史K线并跑。"""

    strategy_type: str
    parameters: dict[str, Any] | None = None
    stock_code: str
    days: int = 365  # 回测窗口长度（交易日）
    initial_capital: float = 100_000.0
    fees: float = 0.001


@router.post("/backtest/run")
async def backtest_run(
    req: BacktestRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """平台回测能力：选策略+股票+区间 → 后端按需拉历史日K（缓存）→ 跑移植的纯 pandas 回测。

    用移植模块构造端到端回测：generate_signals(策略模板) + run_backtest(纯 pandas 引擎)，
    返回 total_return/sharpe/max_drawdown/win_rate + equity_curve（前端可直接画权益曲线）。
    """
    from sqlalchemy import select

    from app.models.stock import DailyQuote
    from app.services.data.cache import ensure_daily_quotes

    # 1. 确保该股有足够历史日K（DB 不足则从 akshare 拉取并缓存）
    have = await ensure_daily_quotes(db, req.stock_code, days=req.days)
    await db.commit()
    if have < max(req.days, 30):
        return {"error": f"{req.stock_code} 日K不足（{have}/{req.days}），可能新股或数据源失败"}

    # 2. 取该股最近 days 个交易日 OHLCV
    rows = (
        await db.execute(
            select(DailyQuote)
            .where(DailyQuote.stock_code == req.stock_code)
            .order_by(DailyQuote.date.desc())
            .limit(req.days)
        )
    ).scalars().all()
    rows = list(reversed(rows))  # 时间升序
    df = pd.DataFrame(
        [
            {
                "date": str(r.date),
                "close": r.close,
                "high": r.high if r.high is not None else r.close,
                "low": r.low if r.low is not None else r.close,
                "volume": r.volume if r.volume is not None else 0.0,
            }
            for r in rows
        ]
    )
    df.index = pd.to_datetime(df["date"], format="mixed", errors="coerce")

    # 3. 生成信号 + 跑回测
    entries, exits = generate_signals(req.strategy_type, req.parameters, df)
    metrics = run_backtest(df, entries, exits, req.initial_capital, req.fees)
    return {
        "strategy_type": req.strategy_type,
        "stock_code": req.stock_code,
        "n_bars": len(rows),
        "metrics": metrics.to_dict(),
        "n_entries": int(entries.sum()),
        "n_exits": int(exits.sum()),
    }


class WalkForwardRequest(BaseModel):
    strategy_type: str
    parameters: dict[str, Any] | None = None
    bars: list[OHLCVBar]
    window: int = 252
    step: int = 63
    fees: float = 0.001


@router.post("/walk-forward")
async def walk_forward_endpoint(
    req: WalkForwardRequest, current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """滚动样本外回测，聚合窗口收益分布。"""
    df = _to_df(OHLCVRequest(bars=req.bars))
    entries, exits = generate_signals(req.strategy_type, req.parameters, df)
    return walk_forward(df, entries, exits, req.window, req.step, fees=req.fees)


class MonteCarloRequest(BaseModel):
    trade_returns: list[float]
    n_sims: int = 1000
    seed: int | None = 42


@router.post("/monte-carlo")
async def monte_carlo_endpoint(
    req: MonteCarloRequest, current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """对交易收益序列 bootstrap 重采样，产出 total_return 置信区间。"""
    return monte_carlo(req.trade_returns, req.n_sims, seed=req.seed)


# ---------------------------------------------------------------------------
# Signals (user-level)
# ---------------------------------------------------------------------------


class SignalEvaluateRequest(BaseModel):
    condition: dict[str, Any]
    previous_state: dict[str, Any] | None = None
    bars: list[OHLCVBar]


@router.post("/signals/evaluate")
async def signal_evaluate(
    req: SignalEvaluateRequest, current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """对给定 OHLCV 末根 bar 求值一个信号条件。"""
    df = _to_df(OHLCVRequest(bars=req.bars))
    return evaluate_condition(req.condition, df, previous_state=req.previous_state)


class SignalBacktestRequest(BaseModel):
    condition: dict[str, Any]
    bars: list[OHLCVBar]
    initial_capital: float = 100_000.0
    fees: float = 0.001


@router.post("/signals/backtest")
async def signal_backtest(
    req: SignalBacktestRequest, current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """把信号条件当策略回放，返回回测指标（告警↔回测打通）。"""
    df = _to_df(OHLCVRequest(bars=req.bars))
    m = backtest_signal_condition(
        req.condition, df, initial_capital=req.initial_capital, fees=req.fees
    )
    return m.to_dict()


# ---------------------------------------------------------------------------
# Screening (user-level)
# ---------------------------------------------------------------------------


@router.post("/screening/{screen}")
async def run_screen(
    screen: str,
    req: OHLCVRequest,
    symbol: str = Query("?", description="标的代码，仅用于结果标注"),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """对单只股票的 OHLCV 跑指定 screen（bullish/bearish/supply_demand）。"""
    from app.services.screening.config import get_screening_settings
    from app.services.screening.screens import score_bearish, score_bullish, score_supply_demand

    settings = get_screening_settings()
    df = _to_df(req)
    fn = {"bullish": score_bullish, "bearish": score_bearish, "supply_demand": score_supply_demand}.get(screen)
    if fn is None:
        return {"error": f"unknown screen '{screen}', choose from bullish/bearish/supply_demand"}
    result = fn(symbol, df, settings)
    return result.model_dump() if result else {"qualified": False, "screen": screen}


# ---------------------------------------------------------------------------
# Regime (user-level)
# ---------------------------------------------------------------------------


class RegimeRequest(BaseModel):
    prices: list[float] = Field(..., min_length=10)
    vix_level: float
    breadth_ratio: float | None = None
    short_window: int = 20
    long_window: int = 50
    momentum_window: int = 10


@router.post("/regime")
async def regime_classify(
    req: RegimeRequest, current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """识别市场状态（bull/bear/choppy/transitional）。"""
    prices = pd.Series(req.prices, dtype=float)
    return RegimeDetector(
        short_window=req.short_window,
        long_window=req.long_window,
        momentum_window=req.momentum_window,
    ).classify(prices, req.vix_level, req.breadth_ratio)


# ---------------------------------------------------------------------------
# Risk (user-level, pure compute)
# ---------------------------------------------------------------------------


class RiskDashboardRequest(BaseModel):
    positions: list[dict[str, Any]]


@router.post("/risk/dashboard")
async def risk_dashboard(
    req: RiskDashboardRequest, current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return compute_dashboard(req.positions)


class PretradeRequest(BaseModel):
    positions: list[dict[str, Any]]
    new_ticker: str
    new_shares: int
    new_price: float


@router.post("/risk/pretrade")
async def risk_pretrade(
    req: PretradeRequest, current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return check_position_risk(req.positions, req.new_ticker, req.new_shares, req.new_price)


class SizingRequest(BaseModel):
    account_size: float
    entry_price: float
    stop_loss: float
    risk_pct: float
    regime: str


@router.post("/risk/sizing")
async def risk_sizing(
    req: SizingRequest, current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return get_regime_adjusted_size(
        req.account_size, req.entry_price, req.stop_loss, req.risk_pct, req.regime
    )


@router.post("/risk/alerts")
async def risk_alerts(
    req: RiskDashboardRequest, current_user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return [a.__dict__ for a in generate_alerts(req.positions)]


# ---------------------------------------------------------------------------
# Trade journal (admin — DB writes)
# ---------------------------------------------------------------------------


class JournalTradeRequest(BaseModel):
    symbol: str
    side: str = Field(..., pattern="^(long|short)$")
    entry_price: float
    exit_price: float | None = None
    shares: float
    rationale: str | None = None
    tags: list[str] = []
    pnl: float | None = None
    r_multiple: float | None = None
    notes: str | None = None
    status: str = "open"


@router.post("/journal/trades", dependencies=[Depends(require_admin)])
async def add_trade(
    req: JournalTradeRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """记一笔交易（admin）。"""
    entry = JournalEntry(
        symbol=req.symbol,
        side=req.side,
        entry_price=req.entry_price,
        exit_price=req.exit_price,
        shares=req.shares,
        rationale=req.rationale,
        tags=req.tags,
        pnl=req.pnl,
        r_multiple=req.r_multiple,
        notes=req.notes,
        status=req.status,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return {"id": entry.id, "symbol": entry.symbol, "status": entry.status}


@router.get("/journal/trades", dependencies=[Depends(require_admin)])
async def list_trades(
    tag: str | None = None,
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """列出交易（admin，可按 tag 过滤）。"""
    from sqlalchemy import select

    stmt = select(JournalEntry).order_by(JournalEntry.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    out = [r.__dict__ for r in rows]
    if tag:
        out = [r for r in out if isinstance(r.get("tags"), list) and tag in r["tags"]]
    # strip SQLAlchemy internal state
    return [{k: v for k, v in r.items() if k != "_sa_instance_state"} for r in out]


@router.post("/journal/recompute/{tag}", dependencies=[Depends(require_admin)])
async def recompute_strategy(
    tag: str, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """重算某 tag 的策略聚合表现（admin）。"""
    perf = await StrategyTracker(db).recompute(tag)
    return {
        "strategy_tag": perf.strategy_tag,
        "win_count": perf.win_count,
        "loss_count": perf.loss_count,
        "expectancy": perf.expectancy,
        "profit_factor": perf.profit_factor,
        "win_rate": (
            perf.win_count / (perf.win_count + perf.loss_count)
            if (perf.win_count + perf.loss_count) > 0
            else 0.0
        ),
    }


@router.get("/journal/strategies", dependencies=[Depends(require_admin)])
async def compare_strategies(
    db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    """所有策略按 expectancy 降序排名（admin）。"""
    perfs = await StrategyTracker(db).compare_strategies()
    return [
        {
            "strategy_tag": p.strategy_tag,
            "win_count": p.win_count,
            "loss_count": p.loss_count,
            "total_pnl": p.total_pnl,
            "expectancy": p.expectancy,
            "profit_factor": p.profit_factor,
        }
        for p in perfs
    ]


# ---------------------------------------------------------------------------
# Decision audit (admin — read-only on audit table)
# ---------------------------------------------------------------------------


@router.get("/audit/decisions", dependencies=[Depends(require_admin)])
async def audit_decisions(
    session_id: str | None = None,
    limit: int = Query(default=50, le=500),
) -> list[dict[str, Any]]:
    return await DecisionLogger.get_decisions(session_id=session_id, limit=limit)


@router.get("/audit/cost-summary", dependencies=[Depends(require_admin)])
async def audit_cost_summary(days: int = Query(default=7, le=365)) -> dict[str, Any]:
    summary = await DecisionLogger.get_cost_summary(days=days)
    # json-safe: math.inf already normalized in logger; nothing extra
    return summary
