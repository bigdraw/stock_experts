"""OpenAI-compatible LLM provider implementation."""

import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.services.llm.provider import LLMMessage, LLMProvider, LLMResponse, LLMStreamChunk
from app.utils.exceptions import LLMProviderError

logger = logging.getLogger(__name__)


def _msg_dict(m: LLMMessage) -> dict:
    """LLMMessage → OpenAI API 消息 dict（支持 tool_calls / role=tool 回灌）。"""
    d: dict = {"role": m.role, "content": m.content}
    if m.tool_calls:
        d["tool_calls"] = m.tool_calls
    if m.tool_call_id:
        d["tool_call_id"] = m.tool_call_id
    return d


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
                "messages": [_msg_dict(m) for m in messages],
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
                "messages": [_msg_dict(m) for m in messages],
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
                # 流式 tool_calls 按 index 累积（args 跨多个 delta 分片到达）
                tool_buffers: dict[int, dict] = {}
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    if line == "data: [DONE]":
                        break
                    try:
                        chunk_data = json.loads(line[6:])
                        choices = chunk_data.get("choices") or []
                        if not choices:
                            continue  # usage/心跳/末尾统计 chunk，静默跳过
                        delta = choices[0].get("delta", {}) or {}
                        # 累积 tool_calls 分片（function-calling 流式）
                        for tc in delta.get("tool_calls", []) or []:
                            idx = tc.get("index", 0)
                            buf = tool_buffers.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                            if tc.get("id"):
                                buf["id"] = tc["id"]
                            fn = tc.get("function", {}) or {}
                            if fn.get("name"):
                                buf["name"] = fn["name"]
                            if fn.get("arguments"):
                                buf["arguments"] += fn["arguments"]
                        yield LLMStreamChunk(
                            content=delta.get("content", "") or "",
                            finish_reason=choices[0].get("finish_reason"),
                            reasoning=delta.get("reasoning_content", "") or "",
                        )
                    except (json.JSONDecodeError, KeyError, IndexError) as e:
                        logger.warning(f"Failed to parse stream chunk: {e}")
                        continue
                # 流结束：若本轮有 tool_calls（模型要调工具），一次性给出完整列表供调用方执行
                if tool_buffers:
                    tcs = [
                        {"id": b["id"], "type": "function",
                         "function": {"name": b["name"], "arguments": b["arguments"]}}
                        for b in tool_buffers.values()
                    ]
                    yield LLMStreamChunk(content="", finish_reason="tool_calls", tool_calls=tcs)
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
