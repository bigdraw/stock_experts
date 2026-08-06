"""LLM Provider manager."""

import asyncio
import logging
import os

from app.config import settings
from app.services.llm.openai_compatible import OpenAICompatibleProvider
from app.services.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

# Grace period before closing retired clients after a reload (ISSUE-023). A
# debate/chat stream can hold a provider's httpx client for 1m45s+; closing it
# the instant admin saves new settings would mid-flight the in-use client with
# "Cannot send a request, as the client has been closed". Retired clients are
# swapped out atomically and closed only after this delay so in-flight requests
# finish on the old client while new requests use the new one.
RELOAD_CLOSE_GRACE_SECONDS = 60.0


class LLMManager:
    """Manages multiple LLM providers with default/named switching."""

    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}
        self._default: str = ""
        # Serializes reload so concurrent /settings/llm PUTs can't interleave
        # (ISSUE-023) and so a reload can't swap providers mid-get.
        self._reload_lock = asyncio.Lock()
        # Retired clients awaiting delayed close + their close tasks.
        self._retired: list[LLMProvider] = []
        self._close_tasks: set[asyncio.Task] = set()

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
        """Initialize providers from config.yaml into the live map.

        ``${VAR}`` placeholders are resolved against os.environ; an unset var
        yields an empty string and the provider is skipped with a warning.
        """
        built = self._build_yaml_providers()
        for name, provider in built.items():
            self.register(name, provider, is_default=(name == settings.llm.default_provider))
        if not self._providers:
            logger.warning("No LLM providers configured")

    def _build_yaml_providers(self) -> dict[str, LLMProvider]:
        """Build providers from config.yaml into a fresh dict (no registration)."""
        result: dict[str, LLMProvider] = {}
        for name, cfg in settings.llm.providers.items():
            api_key = cfg.api_key
            if api_key.startswith("${") and api_key.endswith("}"):
                env_var = api_key[2:-1]
                api_key = os.environ.get(env_var, "")
                if not api_key:
                    logger.warning(f"Environment variable {env_var} not set for provider {name}")
                    continue
            result[name] = OpenAICompatibleProvider(
                base_url=cfg.base_url,
                api_key=api_key,
                model=cfg.model,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
            )
        return result

    async def reload(self, db=None) -> None:
        """Reload providers from the DB system_settings (single source of truth).

        The DB is authoritative when it carries a real api_key; otherwise fall
        back to config.yaml. Build the new provider set first, then atomically
        swap it in and schedule a *delayed* close of the retired clients
        (RELOAD_CLOSE_GRACE_SECONDS) so an admin save mid-stream doesn't kill
        the httpx client a long debate/chat request is still using (ISSUE-023).
        Serialized by ``_reload_lock`` so concurrent PUTs can't interleave.
        """
        async with self._reload_lock:
            new_providers: dict[str, LLMProvider] = {}
            new_default = ""

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
                    name = db_config.get("provider", "qwen")
                    new_providers[name] = OpenAICompatibleProvider(
                        base_url=db_config["base_url"],
                        api_key=db_config["api_key"],
                        model=db_config["model"],
                        max_tokens=int(db_config.get("max_tokens", 4096)),
                        temperature=float(db_config.get("temperature", 0.7)),
                    )
                    new_default = name
                    logger.info("LLM provider reloaded from DB settings")
                except Exception as e:
                    logger.error(f"Failed to build provider from DB config, falling back to yaml: {e}")

            if not new_providers:
                new_providers = self._build_yaml_providers()
                new_default = settings.llm.default_provider if new_providers else ""

            if not new_providers:
                logger.warning("No LLM providers configured")

            # Atomic swap: new requests now use new_providers; the old clients
            # stay alive for in-flight streams until the grace close fires.
            retired = self._providers
            self._providers = new_providers
            self._default = new_default or (next(iter(new_providers), ""))

            if retired:
                self._retired.extend(retired.values())
                task = asyncio.create_task(
                    self._close_after_delay(
                        list(retired.values()), RELOAD_CLOSE_GRACE_SECONDS
                    )
                )
                self._close_tasks.add(task)
                task.add_done_callback(self._close_tasks.discard)

    async def _close_after_delay(self, providers: list[LLMProvider], delay: float) -> None:
        """Close retired clients after ``delay`` seconds (ISSUE-023).

        ``delay`` is captured at reload time so a later change to
        RELOAD_CLOSE_GRACE_SECONDS (e.g. a test restoring it) doesn't alter an
        already-scheduled close.
        """
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            # Shutdown path: close immediately rather than leak.
            await self._close_now(providers)
            raise
        await self._close_now(providers)
        for p in providers:
            try:
                self._retired.remove(p)
            except ValueError:
                pass

    @staticmethod
    async def _close_now(providers: list[LLMProvider]) -> None:
        for provider in providers:
            try:
                if hasattr(provider, "close"):
                    await provider.close()
            except Exception as e:  # pragma: no cover - best-effort cleanup
                logger.warning(f"Error closing retired LLM provider: {e}")

    async def close_all(self):
        """Close all live + retired providers and cancel pending close tasks."""
        for task in list(self._close_tasks):
            task.cancel()
        self._close_tasks.clear()
        live = list(self._providers.values())
        self._providers.clear()
        self._default = ""
        retired = list(self._retired)
        self._retired.clear()
        await self._close_now(live + retired)
        if live or retired:
            logger.info(f"Closed LLM providers (live={len(live)} retired={len(retired)})")


# Global manager instance
llm_manager = LLMManager()
