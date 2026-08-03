"""分析结果缓存（idea: 数据+结论复用，带时效性检查）。

缓存策略：
- value_analysis 数据：24 小时有效（行情每日变，但估值/盈利等变化慢）
- debate 结果：7 天有效（辩论结论不需要每次都重新跑，除非财报季）
- 缓存 key：stock_code + agent_ids 排序后的 hash
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import SystemSettings

logger = logging.getLogger(__name__)

# 缓存时效
VALUE_ANALYSIS_TTL_HOURS = 24
DEBATE_TTL_DAYS = 7


def _cache_key(stock_code: str, agent_ids: list[int]) -> str:
    """生成缓存 key：stock_code + 排序后 agent_ids 的 hash。"""
    ids_str = ",".join(str(i) for i in sorted(agent_ids))
    raw = f"{stock_code}:{ids_str}"
    return hashlib.md5(raw.encode()).hexdigest()


async def get_cached_analysis(
    db: AsyncSession, stock_code: str, agent_ids: list[int], analysis_type: str = "debate"
) -> dict | None:
    """读取缓存的分析结果。如果过期或不存在返回 None。

    analysis_type: 'debate' 或 'value_analysis'，决定 TTL。
    """
    ttl = timedelta(days=DEBATE_TTL_DAYS) if analysis_type == "debate" else timedelta(hours=VALUE_ANALYSIS_TTL_HOURS)
    key = f"analysis_cache:{analysis_type}:{_cache_key(stock_code, agent_ids)}"

    result = await db.execute(
        select(SystemSettings).where(SystemSettings.key == key)
    )
    setting = result.scalar_one_or_none()
    if not setting:
        return None

    try:
        cached = json.loads(setting.value)
        created_at = datetime.fromisoformat(cached.get("created_at", ""))
        if datetime.now() - created_at > ttl:
            logger.info(f"Analysis cache expired for {stock_code} ({analysis_type}), age={(datetime.now() - created_at).total_seconds()/3600:.1f}h")
            return None
        logger.info(f"Analysis cache hit for {stock_code} ({analysis_type}), age={(datetime.now() - created_at).total_seconds()/3600:.1f}h")
        return cached.get("data")
    except Exception as e:
        logger.warning(f"Analysis cache read error: {e}")
        return None


async def set_cached_analysis(
    db: AsyncSession, stock_code: str, agent_ids: list[int], data: dict, analysis_type: str = "debate"
) -> None:
    """写入分析结果到缓存。"""
    key = f"analysis_cache:{analysis_type}:{_cache_key(stock_code, agent_ids)}"
    value = json.dumps({
        "created_at": datetime.now().isoformat(),
        "stock_code": stock_code,
        "agent_ids": sorted(agent_ids),
        "data": data,
    }, ensure_ascii=False, default=str)

    result = await db.execute(select(SystemSettings).where(SystemSettings.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        db.add(SystemSettings(key=key, value=value))
    await db.flush()
    logger.info(f"Analysis cache stored for {stock_code} ({analysis_type})")
