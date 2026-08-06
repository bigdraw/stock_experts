"""Configuration management using pydantic-settings."""

import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings

# 从 backend/.env 加载环境变量（.env 已 gitignore，密钥不入 git）。
# 放模块顶部，确保后续 os.environ.get / _expand_env_vars 能读到 .env 值。
# 本模块被 main.py 首先导入，时机早于任何 env 读取。
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # python-dotenv 未装时静默跳过（不影响 ${VAR} 注入路径）
    pass

# Match ${VAR_NAME} references in config values. We deliberately do NOT use
# os.path.expandvars here because it silently turns an undefined ${VAR} into
# an empty string — which would wipe api_key/secret_key placeholders without
# any warning. Instead we keep the literal "${VAR}" when the env var is unset,
# so downstream code (e.g. llm/manager.py) can still detect the placeholder and
# emit a clear "provider not configured" warning.
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env_vars(text: str) -> str:
    """Replace ${VAR} with os.environ['VAR']; leave literal ${VAR} if unset."""

    def _repl(match: re.Match[str]) -> str:
        name = match.group(1)
        value = os.environ.get(name)
        return value if value is not None else match.group(0)

    return _ENV_PATTERN.sub(_repl, text)


# Shipped placeholder. A publicly-known default secret lets any attacker forge
# an admin JWT and fully take over the platform — ensure_secret_configured()
# refuses to start the server while this (or any <32-char secret) is in effect.
DEFAULT_SECRET_KEY = "change-me-in-production-use-a-real-secret"


def ensure_secret_configured(cfg: "Settings | None" = None) -> None:
    """Fail-fast at startup if the JWT secret is the shipped default or too weak.

    Production must set ``AUTH_SECRET_KEY`` (env or config.yaml). Called from
    the FastAPI lifespan so it blocks an insecure boot without breaking tests,
    which import the app module but don't run the lifespan.
    """
    cfg = cfg or settings
    secret = cfg.auth.secret_key
    if secret == DEFAULT_SECRET_KEY or len(secret) < 32:
        raise RuntimeError(
            "AUTH_SECRET_KEY is not securely configured (still the shipped default "
            "or shorter than 32 chars). Set a strong AUTH_SECRET_KEY in backend/.env "
            "or config.yaml before starting the server — a public default lets "
            "attackers forge admin JWTs."
        )


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///./data/stock.db"


class AuthConfig(BaseModel):
    secret_key: str = DEFAULT_SECRET_KEY
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
    stamp_tax: float = 0.0005  # 0.05% sell-side only
    commission: float = 0.00025  # 0.025% both sides
    commission_min: float = 5.0  # minimum 5 CNY
    slippage: float = 0.001  # 0.1%


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
    """Load configuration from YAML file with environment variable overrides.

    Supports ``${VAR}`` interpolation against os.environ. Undefined vars are
    left as the literal ``${VAR}`` (see _expand_env_vars) so missing secrets
    are detectable rather than silently emptied.
    """
    path = Path(config_path)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        data = yaml.safe_load(_expand_env_vars(raw)) or {}
        settings_ = Settings(**data)
    else:
        settings_ = Settings()

    # Explicit env overrides for secrets — take precedence over file/defaults.
    if os.environ.get("AUTH_SECRET_KEY"):
        settings_.auth.secret_key = os.environ["AUTH_SECRET_KEY"]
    if os.environ.get("LLM_API_KEY") and not _is_resolved(settings_.llm):
        # If the file still holds a ${LLM_API_KEY} placeholder (env was unset
        # at load time), inject AUTH/LLM key now that it may be present.
        for provider in settings_.llm.providers.values():
            if provider.api_key.startswith("${") and provider.api_key.endswith("}"):
                provider.api_key = os.environ["LLM_API_KEY"]

    return settings_


def _is_resolved(llm_cfg: "LLMConfig") -> bool:
    """True if at least one provider's api_key is a concrete value (no ${} placeholder)."""
    return any(
        not (p.api_key.startswith("${") and p.api_key.endswith("}"))
        for p in llm_cfg.providers.values()
    )


# Global settings instance
settings = load_config()
