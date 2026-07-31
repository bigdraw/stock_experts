"""Backtest API routes."""

import json

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.database import get_db
from app.models.strategy import BacktestResult as BacktestResultModel
from app.models.strategy import BacktestStrategy
from app.models.user import User
from app.schemas import BacktestGenerateRequest, BacktestRunRequest
from app.services import settings_service
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
    """从自然语言生成策略——先结构化匹配，匹配失败再 LLM 生成代码。

    1. StrategyParser.parse_simple → 匹配 9 个模板之一（无代码生成，安全）
    2. 匹配失败 → StrategyCodeGenerator LLM 生成代码（现有路径）
    """
    from app.services.backtesting.parser import StrategyParser

    parser = StrategyParser()
    parsed = parser.parse_simple(req.nl_description)
    classified = parser.classify(req.nl_description)

    friction_config = await settings_service.get_friction_config(db)
    strategy = BacktestStrategy(
        user_id=current_user.id,
        name=req.name,
        nl_description=req.nl_description,
        friction_config=json.dumps(friction_config),
    )

    # 结构化匹配成功 → 用模板路径（不生成代码，更安全）
    if parsed["strategy_type"] and parsed["strategy_type"] in (
        "sma_cross", "ema_cross", "macd", "rsi", "bollinger",
        "momentum", "mean_reversion", "breakout", "volume_momentum",
    ):
        strategy.strategy_type = parsed["strategy_type"]
        strategy.strategy_params = json.dumps(parsed["parameters"])
        strategy.category = classified.get("category", "未分类")
        strategy.tags = json.dumps(classified.get("tags", []))
        strategy.description = req.nl_description[:200]
        db.add(strategy)
        await db.flush()
        await db.refresh(strategy)
        return {
            "id": strategy.id, "name": strategy.name,
            "strategy_type": parsed["strategy_type"],
            "parameters": parsed["parameters"],
            "category": classified.get("category"),
            "tags": classified.get("tags", []),
            "mode": "structured",
        }

    # 结构化匹配失败 → LLM 生成代码（保留现有路径）
    llm = llm_manager.get()
    generator = StrategyCodeGenerator(llm)
    code = await generator.generate(req.nl_description)

    strategy.strategy_code = code
    strategy.category = classified.get("category", "自定义")
    strategy.tags = json.dumps(classified.get("tags", []))
    strategy.description = req.nl_description[:200]
    db.add(strategy)
    await db.flush()
    await db.refresh(strategy)
    return {"id": strategy.id, "name": strategy.name, "code": code, "category": strategy.category, "mode": "llm_generated"}


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

    # Read friction config: request > DB > defaults
    if req.friction_config:
        friction = FrictionConfig(**req.friction_config)
    else:
        db_friction = await settings_service.get_friction_config(db)
        friction = FrictionConfig(**db_friction)

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
        raise BadRequestException(f"Backtest failed: {e}") from e

    # Save result
    bt_result = BacktestResultModel(
        strategy_id=req.strategy_id,
        run_params=json.dumps(
            {
                "stock_codes": stock_codes,
                "start_date": req.start_date,
                "end_date": req.end_date,
                "initial_capital": req.initial_capital,
            }
        ),
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
        {
            "id": s.id,
            "name": s.name,
            "nl_description": s.nl_description,
            "created_at": str(s.created_at),
        }
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
            "id": r.id,
            "strategy_id": r.strategy_id,
            "total_return": r.total_return,
            "max_drawdown": r.max_drawdown,
            "sharpe_ratio": r.sharpe_ratio,
            "win_rate": r.win_rate,
            "total_trades": r.total_trades,
            "created_at": str(r.created_at),
        }
        for r in results
    ]
