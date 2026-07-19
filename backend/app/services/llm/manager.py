"""LLM Provider manager."""

import logging
import os
from typing import Any

from app.config import settings
from app.services.llm.openai_compatible import OpenAICompatibleProvider
from app.services.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


class LLMManager:
    """Manages multiple LLM providers with default/named switching."""

    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}
        self._default: str = ""

    def register(self, name: str, provider: LLMProvider, is_default: bool = False):
        """Register a provider."""
        self._providers[name] = provider
        if is_default or not self._default:
            self._default = name
        logger.info(f"Registered LLM provider: {name} (default={is_default})")

    def get(self, name: str | None = None) -> LLMProvider:
        """Get a provider by name (or default)."""
        key = name or self._default
        if key not in self._providers:
            available = list(self._providers.keys())
            raise ValueError(f"LLM provider '{key}' not found. Available: {available}")
        return self._providers[key]

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    async def init_from_config(self):
        """Initialize providers from config.yaml.

        ``${VAR}`` placeholders are resolved against os.environ; an unset var
        yields an empty string and the provider is skipped with a warning.
        """
        for name, cfg in settings.llm.providers.items():
            api_key = cfg.api_key
            if api_key.startswith("${") and api_key.endswith("}"):
                env_var = api_key[2:-1]
                api_key = os.environ.get(env_var, "")
                if not api_key:
                    logger.warning(f"Environment variable {env_var} not set for provider {name}")
                    continue

            provider = OpenAICompatibleProvider(
                base_url=cfg.base_url,
                api_key=api_key,
                model=cfg.model,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
            )
            self.register(name, provider, is_default=(name == settings.llm.default_provider))

        if not self._providers:
            logger.warning("No LLM providers configured")

    async def reload(self, db=None) -> None:
        """Reload providers from the DB system_settings (single source of truth).

        Previously the LLM manager only read config.yaml at startup, while the
        /settings/llm PUT endpoint wrote a separate copy to the DB — so admin
        edits to api_key appeared to save but never took effect at runtime. This
        method unifies the two: the DB is authoritative when it carries a real
        api_key; otherwise we fall back to config.yaml (init_from_config).
        Call this after set_llm_config() and on app startup.
        """
        await self.close_all()
        self._providers.clear()
        self._default = ""

        db_config = None
        if db is not None:
            try:
                from app.services import settings_service
                db_config = await settings_service.get_llm_config(db)
            except Exception as e:
                logger.warning(f"Could not load LLM config from DB: {e}")
                db_config = None

        if db_config and db_config.get("api_key"):
            try:
                provider = OpenAICompatibleProvider(
                    base_url=db_config["base_url"],
                    api_key=db_config["api_key"],
                    model=db_config["model"],
                    max_tokens=int(db_config.get("max_tokens", 4096)),
                    temperature=float(db_config.get("temperature", 0.7)),
                )
                self.register(db_config.get("provider", "qwen"), provider, is_default=True)
                logger.info("LLM provider reloaded from DB settings")
                return
            except Exception as e:
                logger.error(f"Failed to build provider from DB config, falling back to yaml: {e}")

        # Fall back to config.yaml.
        await self.init_from_config()

    async def close_all(self):
        """Close all providers."""
        for name, provider in self._providers.items():
            if hasattr(provider, "close"):
                await provider.close()
            logger.info(f"Closed LLM provider: {name}")


# Global manager instance
llm_manager = LLMManager()
