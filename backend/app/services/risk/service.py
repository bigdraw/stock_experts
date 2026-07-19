"""风险看板（移植自 maverick-mcp，MIT License Copyright (c) 2024）。

源文件：`maverick_mcp/services/risk/service.py`。
适配点：原版 `RiskService` 注入同步 `Session`、`RiskAlert` 为 ORM 模型。
本平台把**风险数学层**（VaR/集中度/pre-trade/regime 仓位/告警阈值）做成
无 DB 依赖的纯函数 + dataclass，全可单测；持久化由调用方按需接库。
数学（参数法 VaR、组合波动率平方和开方、regime 乘子）逐字保留。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 参数法 VaR z 值
_Z_95 = 1.645
_Z_99 = 2.326

# 告警阈值
_SECTOR_WARN_PCT = 0.30
_SECTOR_CRITICAL_PCT = 0.50
_POSITION_WARN_PCT = 0.20
_PORTFOLIO_LOSS_WARN_PCT = 0.10

# Regime 仓位乘子：bull 全仓、震荡/转换 0.75、熊市 0.5
_REGIME_MULTIPLIERS: dict[str, float] = {
    "bull": 1.0,
    "choppy": 0.75,
    "transitional": 0.75,
    "bear": 0.5,
}


@dataclass
class RiskAlert:
    """风险告警（移植原版字段，dataclass 而非 ORM）。"""

    portfolio_name: str
    alert_type: str  # concentration / sizing / drawdown
    severity: str  # warning / critical
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def compute_dashboard(portfolio_positions: list[dict[str, Any]]) -> dict[str, Any]:
    """计算组合风险指标。

    Args:
        portfolio_positions: 持仓 dict 列表，每项含
            symbol/shares/cost_basis/current_price/sector(可选)。

    Returns:
        total_value / sector_concentration / max_sector_pct /
        portfolio_var_95 / portfolio_var_99 / total_pnl / position_count。
    """
    if not portfolio_positions:
        return {
            "total_value": 0.0,
            "sector_concentration": {},
            "max_sector_pct": 0.0,
            "portfolio_var_95": 0.0,
            "portfolio_var_99": 0.0,
            "total_pnl": 0.0,
            "position_count": 0,
        }

    total_value = sum(
        float(p.get("shares", 0)) * float(p.get("current_price", 0))
        for p in portfolio_positions
    )
    total_pnl = sum(
        (float(p.get("current_price", 0)) - float(p.get("cost_basis", 0)))
        * float(p.get("shares", 0))
        for p in portfolio_positions
    )

    # 行业集中度
    sector_values: dict[str, float] = {}
    for pos in portfolio_positions:
        sector = pos.get("sector") or "Unknown"
        val = float(pos.get("shares", 0)) * float(pos.get("current_price", 0))
        sector_values[sector] = sector_values.get(sector, 0.0) + val

    sector_concentration: dict[str, float] = {}
    if total_value > 0:
        for sector, val in sector_values.items():
            sector_concentration[sector] = val / total_value
    max_sector_pct = max(sector_concentration.values(), default=0.0)

    # 简化参数法 VaR——假设每仓 2% 日波动、零相关
    portfolio_std = _estimate_portfolio_std(portfolio_positions, total_value)
    portfolio_var_95 = _Z_95 * portfolio_std * total_value
    portfolio_var_99 = _Z_99 * portfolio_std * total_value

    return {
        "total_value": round(total_value, 2),
        "sector_concentration": {k: round(v, 4) for k, v in sector_concentration.items()},
        "max_sector_pct": round(max_sector_pct, 4),
        "portfolio_var_95": round(portfolio_var_95, 2),
        "portfolio_var_99": round(portfolio_var_99, 2),
        "total_pnl": round(total_pnl, 2),
        "position_count": len(portfolio_positions),
    }


def check_position_risk(
    portfolio_positions: list[dict[str, Any]],
    new_ticker: str,
    new_shares: int,
    new_price: float,
) -> dict[str, Any]:
    """预交易风险检查：把拟加仓位并入组合，对比 current vs projected。"""
    current = compute_dashboard(portfolio_positions)

    new_position: dict[str, Any] = {
        "symbol": new_ticker.upper(),
        "shares": new_shares,
        "cost_basis": new_price,
        "current_price": new_price,
        "sector": "Unknown",
    }

    # 合并——若 ticker 已存在则累加份额、重算均价
    merged: list[dict[str, Any]] = []
    ticker_found = False
    for pos in portfolio_positions:
        if pos.get("symbol", "").upper() == new_ticker.upper():
            merged_pos = dict(pos)
            existing_shares = float(pos.get("shares", 0))
            existing_cb = float(pos.get("cost_basis", 0))
            total_shares = existing_shares + new_shares
            avg_cb = (
                (existing_shares * existing_cb + new_shares * new_price) / total_shares
                if total_shares > 0
                else new_price
            )
            merged_pos["shares"] = total_shares
            merged_pos["cost_basis"] = avg_cb
            merged_pos["current_price"] = new_price
            merged.append(merged_pos)
            ticker_found = True
        else:
            merged.append(dict(pos))

    if not ticker_found:
        merged.append(new_position)

    projected = compute_dashboard(merged)
    position_value = new_shares * new_price

    return {
        "current": current,
        "projected": projected,
        "new_position": {
            "ticker": new_ticker.upper(),
            "shares": new_shares,
            "price": new_price,
            "position_value": round(position_value, 2),
            "pct_of_projected_portfolio": (
                round(position_value / projected["total_value"], 4)
                if projected["total_value"] > 0
                else 0.0
            ),
        },
    }


def get_regime_adjusted_size(
    account_size: float,
    entry_price: float,
    stop_loss: float,
    risk_pct: float,
    regime: str,
) -> dict[str, Any]:
    """按市场 regime 调整的仓位 sizing。

    risk_per_share = |entry - stop|；risk_amount = account * (risk_pct% * regime乘子)；
    shares = floor(risk_amount / risk_per_share)。bear 市仓位减半。
    """
    multiplier = _REGIME_MULTIPLIERS.get(regime.lower(), 1.0)
    adjusted_risk_pct = risk_pct * multiplier
    risk_amount = account_size * (adjusted_risk_pct / 100.0)

    risk_per_share = abs(entry_price - stop_loss)
    shares = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
    position_value = shares * entry_price

    return {
        "shares": shares,
        "position_value": round(position_value, 2),
        "risk_amount": round(risk_amount, 2),
        "regime_multiplier": multiplier,
        "adjusted_risk_pct": round(adjusted_risk_pct, 4),
        "regime": regime.lower(),
    }


def generate_alerts(
    portfolio_positions: list[dict[str, Any]],
    portfolio_name: str = "default",
) -> list[RiskAlert]:
    """检查组合风险阈值违规并生成告警（不持久化）。"""
    dashboard = compute_dashboard(portfolio_positions)
    alerts: list[RiskAlert] = []
    total_value = dashboard["total_value"]

    # 行业集中度
    for sector, pct in dashboard["sector_concentration"].items():
        if pct > _SECTOR_CRITICAL_PCT:
            alerts.append(
                RiskAlert(
                    portfolio_name=portfolio_name,
                    alert_type="concentration",
                    severity="critical",
                    message=(
                        f"Sector '{sector}' represents {pct:.1%} of portfolio "
                        f"(threshold: {_SECTOR_CRITICAL_PCT:.0%})"
                    ),
                    details={"sector": sector, "pct": pct},
                )
            )
        elif pct > _SECTOR_WARN_PCT:
            alerts.append(
                RiskAlert(
                    portfolio_name=portfolio_name,
                    alert_type="concentration",
                    severity="warning",
                    message=(
                        f"Sector '{sector}' represents {pct:.1%} of portfolio "
                        f"(threshold: {_SECTOR_WARN_PCT:.0%})"
                    ),
                    details={"sector": sector, "pct": pct},
                )
            )

    # 单仓占比
    if total_value > 0:
        for pos in portfolio_positions:
            pos_value = float(pos.get("shares", 0)) * float(pos.get("current_price", 0))
            pos_pct = pos_value / total_value
            ticker = pos.get("symbol", pos.get("ticker", "?"))
            if pos_pct > _POSITION_WARN_PCT:
                alerts.append(
                    RiskAlert(
                        portfolio_name=portfolio_name,
                        alert_type="sizing",
                        severity="warning",
                        message=(
                            f"Position '{ticker}' is {pos_pct:.1%} of portfolio "
                            f"(threshold: {_POSITION_WARN_PCT:.0%})"
                        ),
                        details={"ticker": ticker, "pct": pos_pct},
                    )
                )

    # 组合回撤
    total_cost = sum(
        float(p.get("cost_basis", 0)) * float(p.get("shares", 0))
        for p in portfolio_positions
    )
    if total_cost > 0:
        loss_pct = (total_cost - total_value) / total_cost
        if loss_pct > _PORTFOLIO_LOSS_WARN_PCT:
            alerts.append(
                RiskAlert(
                    portfolio_name=portfolio_name,
                    alert_type="drawdown",
                    severity="warning",
                    message=(
                        f"Portfolio is down {loss_pct:.1%} from cost basis "
                        f"(threshold: {_PORTFOLIO_LOSS_WARN_PCT:.0%})"
                    ),
                    details={"loss_pct": loss_pct, "total_cost": total_cost},
                )
            )

    return alerts


def _estimate_portfolio_std(positions: list[dict[str, Any]], total_value: float) -> float:
    """简化组合日波动率：每仓 2% 日波动、零相关，权重平方和开方（分散化）。"""
    if total_value <= 0 or not positions:
        return 0.02

    daily_vol_per_position = 0.02
    variance = 0.0
    for pos in positions:
        weight = (
            float(pos.get("shares", 0))
            * float(pos.get("current_price", 0))
            / total_value
        )
        variance += (weight * daily_vol_per_position) ** 2
    return math.sqrt(variance)
