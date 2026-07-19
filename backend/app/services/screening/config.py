"""选股域设置（移植自 maverick-mcp，MIT License Copyright (c) 2024）。

源文件：`maverick/screening/config.py`。
适配点：原版 `from maverick.platform.config import _env_int`，本平台内联同名 helper。
"""

import os
from functools import lru_cache

from pydantic import BaseModel, Field


def _env_int(name: str, default: int) -> int:
    """从环境变量读 int，缺失用 default。"""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class ScreeningSettings(BaseModel):
    """三策略打分的可调阈值（均可经环境变量覆盖）。"""

    bullish_min_score: int = Field(
        default_factory=lambda: _env_int("SCR_BULLISH_MIN_SCORE", 50)
    )
    bear_min_score: int = Field(
        default_factory=lambda: _env_int("SCR_BEAR_MIN_SCORE", 40)
    )
    min_history_days: int = Field(
        default_factory=lambda: _env_int("SCR_MIN_HISTORY_DAYS", 200)
    )
    universe_max: int = Field(default_factory=lambda: _env_int("SCR_UNIVERSE_MAX", 200))
    volume_surge_multiplier: float = 1.5
    volume_decline_multiplier: float = 1.2
    atr_contraction_multiplier: float = 0.8
    rsi_overbought: float = 80.0
    rsi_oversold: float = 30.0
    default_limit: int = 20
    max_limit: int = 100


@lru_cache(maxsize=1)
def get_screening_settings() -> ScreeningSettings:
    """进程级缓存设置单例。"""
    return ScreeningSettings()


def reset_screening_settings() -> None:
    """清缓存（测试用）。"""
    get_screening_settings.cache_clear()
