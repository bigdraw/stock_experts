"""OpenAI-compatible LLM provider implementation."""

import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.services.llm.provider import LLMMessage, LLMProvider, LLMResponse, LLMStreamChunk
from app.utils.exceptions import LLMProviderError

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible API provider (covers qwen/deepseek/openai etc)."""

    def __init__(self, base_url: str, api_key: str, model: str, **kwargs):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=120.0,
        )

    async def chat(
        self, messages: list[LLMMessage], temperature: float = 0.7, max_tokens: int = 4096, **kwargs
    ) -> LLMResponse:
        """Synchronous chat call."""
        try:
            resp = await self.client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                    **kwargs,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            return LLMResponse(
                content=choice["message"]["content"],
                model=self.model,
                usage=data.get("usage", {}),
                finish_reason=choice.get("finish_reason", "stop"),
            )
        except httpx.HTTPError as e:
            logger.error(f"LLM provider error: {e}")
            raise LLMProviderError(f"Failed to call LLM: {e}") from e

    async def chat_stream(
        self, messages: list[LLMMessage], temperature: float = 0.7, max_tokens: int = 4096, **kwargs
    ) -> AsyncIterator[LLMStreamChunk]:
        """Streaming chat call."""
        try:
            async with self.client.stream(
                "POST",
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True,
                    **kwargs,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    if line == "data: [DONE]":
                        break
                    try:
                        chunk_data = json.loads(line[6:])
                        choice = chunk_data["choices"][0]
                        yield LLMStreamChunk(
                            content=choice["delta"].get("content", ""),
                            finish_reason=choice.get("finish_reason"),
                        )
                    except (json.JSONDecodeError, KeyError, IndexError) as e:
                        logger.warning(f"Failed to parse stream chunk: {e}")
                        continue
        except httpx.HTTPError as e:
            logger.error(f"LLM provider stream error: {e}")
            raise LLMProviderError(f"Failed to stream from LLM: {e}") from e

    async def health_check(self) -> bool:
        """Check provider availability."""
        try:
            await self.chat([LLMMessage(role="user", content="ping")], max_tokens=5)
            return True
        except Exception:
            return False

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
