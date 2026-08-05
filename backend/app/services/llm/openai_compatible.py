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
        # 分层超时：连接/池快速失败（10s），读超时给到 300s——LLM 慢生成（如 qwen
        # ~28 tok/s，辩论 challenge/response 单次可达 1m45s+）不能卡在 120s 默认值
        # 触发 ReadTimeout 中断整轮辩论。流式（chat_stream）因 token 持续回流不触发读超时。
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0),
        )

    async def chat(
        self, messages: list[LLMMessage], temperature: float = 0.7, max_tokens: int | None = 4096, **kwargs
    ) -> LLMResponse:
        """Synchronous chat call. max_tokens=None 时不传（不截断）。"""
        try:
            body: dict = {
                "model": self.model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": temperature,
                "stream": False,
                **kwargs,
            }
            if max_tokens is not None:
                body["max_tokens"] = max_tokens
            resp = await self.client.post("/chat/completions", json=body)
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
            logger.error(f"LLM provider error: {e!r}")
            raise LLMProviderError(f"Failed to call LLM: {e!r}") from e

    async def chat_stream(
        self, messages: list[LLMMessage], temperature: float = 0.7, max_tokens: int | None = 4096, **kwargs
    ) -> AsyncIterator[LLMStreamChunk]:
        """Streaming chat call.

        max_tokens=None 时不传该字段（不截断，模型用自身上限；思考链 enable_thinking=True
        时思考可能很长，None 避免思考吃满 cap 导致答案空）。
        同时捕获 delta.reasoning_content（qwen3 思考链）。
        """
        try:
            body: dict = {
                "model": self.model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": temperature,
                "stream": True,
                **kwargs,
            }
            if max_tokens is not None:
                body["max_tokens"] = max_tokens
            async with self.client.stream(
                "POST",
                "/chat/completions",
                json=body,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    if line == "data: [DONE]":
                        break
                    try:
                        chunk_data = json.loads(line[6:])
                        choices = chunk_data.get("choices") or []
                        if not choices:
                            # 空 choices chunk（usage 统计/心跳/末尾统计，qwen3/dashscope 偶发），
                            # 无内容 delta——静默跳过（debug），不告警吓人。
                            continue
                        delta = choices[0].get("delta", {}) or {}
                        yield LLMStreamChunk(
                            content=delta.get("content", "") or "",
                            finish_reason=choices[0].get("finish_reason"),
                            reasoning=delta.get("reasoning_content", "") or "",
                        )
                    except (json.JSONDecodeError, KeyError, IndexError) as e:
                        logger.warning(f"Failed to parse stream chunk: {e}")
                        continue
        except httpx.HTTPError as e:
            logger.error(f"LLM provider stream error: {e!r}")
            raise LLMProviderError(f"Failed to stream from LLM: {e!r}") from e

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
