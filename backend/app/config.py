"""Configuration management using pydantic-settings."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///./data/stock.db"


class AuthConfig(BaseModel):
    secret_key: str = "change-me-in-production-use-a-real-secret"
    algorithm: str = "HS256"
    token_expire_minutes: int = 1440  # 24 hours


class LLMProviderConfig(BaseModel):
    base_url: str
    api_key: str
    model: str
    max_tokens: int = 4096
    temperature: float = 0.7


class LLMConfig(BaseModel):
    default_provider: str = "qwen"
    providers: dict[str, LLMProviderConfig] = {}


class DataSourceProviderConfig(BaseModel):
    rate_limit: int = 10
    retry_max: int = 3


class DataSourceConfig(BaseModel):
    default_provider: str = "akshare"
    providers: dict[str, DataSourceProviderConfig] = {}


class FrictionConfig(BaseModel):
    stamp_tax: float = 0.0005       # 0.05% sell-side only
    commission: float = 0.00025     # 0.025% both sides
    commission_min: float = 5.0     # minimum 5 CNY
    slippage: float = 0.001         # 0.1%


class BacktestConfig(BaseModel):
    friction: FrictionConfig = FrictionConfig()


class SchedulerConfig(BaseModel):
    daily_update_time: str = "16:30"
    backup_day: str = "sunday"


class Settings(BaseSettings):
    server: ServerConfig = ServerConfig()
    database: DatabaseConfig = DatabaseConfig()
    auth: AuthConfig = AuthConfig()
    llm: LLMConfig = LLMConfig()
    data_source: DataSourceConfig = DataSourceConfig()
    backtest: BacktestConfig = BacktestConfig()
    scheduler: SchedulerConfig = SchedulerConfig()


def load_config(config_path: str = "config.yaml") -> Settings:
    """Load configuration from YAML file with environment variable overrides."""
    path = Path(config_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return Settings(**data)
    return Settings()


# Global settings instance
settings = load_config()
