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
        """Initialize providers from config.yaml."""
        for name, cfg in settings.llm.providers.items():
            # Resolve environment variables in api_key
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

    async def close_all(self):
        """Close all providers."""
        for name, provider in self._providers.items():
            if hasattr(provider, "close"):
                await provider.close()
            logger.info(f"Closed LLM provider: {name}")


# Global manager instance
llm_manager = LLMManager()
