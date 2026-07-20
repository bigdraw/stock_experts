"""策略表现聚合（移植自 maverick-mcp，MIT License Copyright (c) 2024）。

源文件：`maverick_mcp/services/journal/analytics.py`。
适配点：原版用同步 `Session` + `db.query(...)`；本平台用 async `AsyncSession`
+ `select(...)`。**纯数学核心**（win/loss/expectancy/profit_factor）提取为
`compute_strategy_metrics()`，无需 DB 即可单测，是移植的核心价值。
"""

from __future__ import annotations

import logging
import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.journal.models import JournalEntry, StrategyPerformance

logger = logging.getLogger(__name__)


def compute_strategy_metrics(tagged_entries: list[JournalEntry]) -> dict[str, Any]:
    """对一批已平仓、含某 tag 的 entries 计算聚合表现（纯数学，无 DB）。

    - win/loss：pnl>0 为胜，pnl<0 为负；pnl==0 不计入胜负（保本）
    - win_rate = win_count / (win+loss)
    - expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
      —— 每笔交易的期望盈亏
    - profit_factor = total_wins / abs(total_losses)；无亏损时 +inf（有盈利）/0
    """
    wins = [e for e in tagged_entries if (e.pnl or 0.0) > 0]
    losses = [e for e in tagged_entries if (e.pnl or 0.0) < 0]

    win_count = len(wins)
    loss_count = len(losses)
    total_trades = win_count + loss_count

    total_pnl = sum(e.pnl or 0.0 for e in tagged_entries)
    total_win_pnl = sum(e.pnl or 0.0 for e in wins)
    total_loss_pnl = sum(e.pnl or 0.0 for e in losses)

    avg_win = total_win_pnl / win_count if win_count > 0 else 0.0
    avg_loss = abs(total_loss_pnl / loss_count) if loss_count > 0 else 0.0

    if total_trades > 0:
        win_rate = win_count / total_trades
        loss_rate = loss_count / total_trades
        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    else:
        win_rate = 0.0
        expectancy = 0.0

    if total_loss_pnl != 0.0:
        profit_factor = total_win_pnl / abs(total_loss_pnl)
    else:
        profit_factor = math.inf if total_win_pnl > 0 else 0.0

    return {
        "win_count": win_count,
        "loss_count": loss_count,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": expectancy,
        "profit_factor": profit_factor,
    }


class StrategyTracker:
    """异步重算并持久化某 strategy_tag 的聚合表现。

    闭仓交易触发 recompute(tag)：查所有含该 tag 的已平仓 entries，按
    :func:`compute_strategy_metrics` 算指标，upsert 到 StrategyPerformance。
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session

    async def recompute(self, strategy_tag: str) -> StrategyPerformance:
        """重算某 tag 的指标并 upsert。"""
        result = await self._db.execute(select(JournalEntry).where(JournalEntry.status == "closed"))
        closed_entries: list[JournalEntry] = list(result.scalars().all())

        tagged = [e for e in closed_entries if isinstance(e.tags, list) and strategy_tag in e.tags]

        m = compute_strategy_metrics(tagged)

        perf_result = await self._db.execute(
            select(StrategyPerformance).where(StrategyPerformance.strategy_tag == strategy_tag)
        )
        perf = perf_result.scalar_one_or_none()
        if perf is None:
            perf = StrategyPerformance(strategy_tag=strategy_tag)
            self._db.add(perf)

        perf.period = "all_time"
        perf.win_count = m["win_count"]
        perf.loss_count = m["loss_count"]
        perf.total_pnl = m["total_pnl"]
        perf.avg_win = m["avg_win"]
        perf.avg_loss = m["avg_loss"]
        # inf 不友好，序列化为大数（无亏损且盈利时给一个可显示的极大值）
        pf = m["profit_factor"]
        perf.profit_factor = 1e9 if pf == math.inf else pf
        perf.expectancy = m["expectancy"]

        await self._db.flush()
        return perf

    async def get_performance(self, strategy_tag: str) -> StrategyPerformance | None:
        """取某 tag 的持久化表现记录。"""
        result = await self._db.execute(
            select(StrategyPerformance).where(StrategyPerformance.strategy_tag == strategy_tag)
        )
        return result.scalar_one_or_none()

    async def compare_strategies(self) -> list[StrategyPerformance]:
        """所有策略按 expectancy 降序排名。"""
        result = await self._db.execute(
            select(StrategyPerformance).order_by(StrategyPerformance.expectancy.desc())
        )
        return list(result.scalars().all())
