"""Backtest API routes."""

import json

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models.strategy import BacktestResult as BacktestResultModel
from app.models.strategy import BacktestStrategy
from app.models.user import User
from app.schemas import BacktestGenerateRequest, BacktestResultResponse, BacktestRunRequest
from app.services.backtest.engine import BacktestEngine, FrictionConfig
from app.services.backtest.generator import StrategyCodeGenerator
from app.services.llm.manager import llm_manager
from app.utils.exceptions import BadRequestException, NotFoundException

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("/generate")
async def generate_strategy(
    req: BacktestGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate strategy code from natural language."""
    llm = llm_manager.get()
    generator = StrategyCodeGenerator(llm)
    code = await generator.generate(req.nl_description)

    strategy = BacktestStrategy(
        user_id=current_user.id,
        name=req.name,
        nl_description=req.nl_description,
        strategy_code=code,
        friction_config=json.dumps(settings.backtest.friction.model_dump()),
    )
    db.add(strategy)
    await db.flush()
    await db.refresh(strategy)
    return {"id": strategy.id, "name": strategy.name, "code": code}


@router.post("/run")
async def run_backtest(
    req: BacktestRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute backtest."""
    strategy = await db.get(BacktestStrategy, req.strategy_id)
    if not strategy:
        raise NotFoundException(f"Strategy {req.strategy_id} not found")

    friction = FrictionConfig(**(req.friction_config or settings.backtest.friction.model_dump()))
    engine = BacktestEngine(db, friction)

    stock_codes = req.stock_codes or ["600519"]  # Default to Moutai for testing
    try:
        result = await engine.run(
            strategy_code=strategy.strategy_code,
            stock_codes=stock_codes,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=req.initial_capital,
        )
    except Exception as e:
        raise BadRequestException(f"Backtest failed: {e}")

    # Save result
    bt_result = BacktestResultModel(
        strategy_id=req.strategy_id,
        run_params=json.dumps({
            "stock_codes": stock_codes,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "initial_capital": req.initial_capital,
        }),
        total_return=result.total_return,
        annualized_return=result.annualized_return,
        max_drawdown=result.max_drawdown,
        sharpe_ratio=result.sharpe_ratio,
        win_rate=result.win_rate,
        total_trades=result.total_trades,
        final_capital=result.final_capital,
        equity_curve=json.dumps(result.equity_curve),
        trade_log=json.dumps(result.trade_log),
    )
    db.add(bt_result)
    await db.flush()
    await db.refresh(bt_result)
    return bt_result


@router.get("/strategies")
async def list_strategies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List user's strategies."""
    from sqlalchemy import select
    result = await db.execute(
        select(BacktestStrategy).where(BacktestStrategy.user_id == current_user.id)
    )
    strategies = result.scalars().all()
    return [
        {"id": s.id, "name": s.name, "nl_description": s.nl_description, "created_at": str(s.created_at)}
        for s in strategies
    ]


@router.get("/results")
async def list_results(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List backtest results."""
    from sqlalchemy import select
    result = await db.execute(
        select(BacktestResultModel).order_by(BacktestResultModel.created_at.desc()).limit(50)
    )
    results = result.scalars().all()
    return [
        {
            "id": r.id, "strategy_id": r.strategy_id,
            "total_return": r.total_return, "max_drawdown": r.max_drawdown,
            "sharpe_ratio": r.sharpe_ratio, "win_rate": r.win_rate,
            "total_trades": r.total_trades, "created_at": str(r.created_at),
        }
        for r in results
    ]
