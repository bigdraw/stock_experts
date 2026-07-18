"""Settings service for managing system configuration."""

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import SystemSettings

logger = logging.getLogger(__name__)

# In-memory cache for settings
_settings_cache: dict[str, Any] = {}


async def get_setting(db: AsyncSession, key: str, default: Any = None) -> Any:
    """Get a setting value from database with caching."""
    # Check cache first
    if key in _settings_cache:
        return _settings_cache[key]
    
    # Query database
    result = await db.execute(
        select(SystemSettings).where(SystemSettings.key == key)
    )
    setting = result.scalar_one_or_none()
    
    if setting:
        # Try to parse as JSON
        try:
            value = json.loads(setting.value)
        except json.JSONDecodeError:
            value = setting.value
        
        # Cache the value
        _settings_cache[key] = value
        return value
    
    return default


async def set_setting(db: AsyncSession, key: str, value: Any) -> None:
    """Set a setting value in database and update cache."""
    # Serialize value to JSON if it's not a string
    if isinstance(value, str):
        serialized = value
    else:
        serialized = json.dumps(value)
    
    # Query existing setting
    result = await db.execute(
        select(SystemSettings).where(SystemSettings.key == key)
    )
    setting = result.scalar_one_or_none()
    
    if setting:
        setting.value = serialized
    else:
        new_setting = SystemSettings(key=key, value=serialized)
        db.add(new_setting)
    
    await db.commit()
    
    # Update cache
    _settings_cache[key] = value
    
    logger.info(f"Setting '{key}' updated")


def clear_cache(key: Optional[str] = None) -> None:
    """Clear settings cache."""
    if key:
        _settings_cache.pop(key, None)
    else:
        _settings_cache.clear()


# Convenience functions for specific settings

async def get_llm_config(db: AsyncSession) -> dict:
    """Get LLM configuration."""
    default = {
        "provider": "qwen",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "",
        "model": "qwen3.7-max",
        "max_tokens": 65536,
        "temperature": 0.7
    }
    return await get_setting(db, "llm_config", default)


async def set_llm_config(db: AsyncSession, config: dict) -> None:
    """Set LLM configuration."""
    await set_setting(db, "llm_config", config)


async def get_data_source_config(db: AsyncSession) -> dict:
    """Get data source configuration."""
    default = {
        "provider": "akshare",
        "rate_limit": 10,
        "retry_max": 3
    }
    return await get_setting(db, "data_source_config", default)


async def set_data_source_config(db: AsyncSession, config: dict) -> None:
    """Set data source configuration."""
    await set_setting(db, "data_source_config", config)


async def get_friction_config(db: AsyncSession) -> dict:
    """Get backtest friction configuration."""
    default = {
        "stamp_tax": 0.0005,
        "commission": 0.00025,
        "commission_min": 5.0,
        "slippage": 0.001
    }
    return await get_setting(db, "friction_config", default)


async def set_friction_config(db: AsyncSession, config: dict) -> None:
    """Set backtest friction configuration."""
    await set_setting(db, "friction_config", config)
