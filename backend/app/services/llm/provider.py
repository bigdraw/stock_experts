"""LLM Provider abstraction layer."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class LLMMessage:
    """Single message in a conversation.

    role: system / user / assistant / tool。
    tool_calls: assistant 调用工具（function-calling）时的调用列表。
    tool_call_id: role=tool 的结果消息对应的调用 id（回灌给模型）。
    """

    role: str
    content: str
    tool_calls: list | None = None
    tool_call_id: str | None = None


@dataclass
class LLMResponse:
    """Complete LLM response."""

    content: str
    model: str
    usage: dict  # {prompt_tokens, completion_tokens, total_tokens}
    finish_reason: str


@dataclass
class LLMStreamChunk:
    """Streaming chunk from LLM.

    content: 最终答案增量；reasoning: 思考链增量（qwen3 等模型的 delta.reasoning_content，
    enable_thinking=True 时产出，与 content 分开流）。
    tool_calls: 本轮工具调用（function-calling）；流式增量累积后，流结束时一次性给出
    完整 tool_calls 供调用方执行（见 openai_compatible.chat_stream）。
    """

    content: str
    finish_reason: str | None = None
    reasoning: str = ""
    tool_calls: list = None


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    async def chat(
        self, messages: list[LLMMessage], temperature: float = 0.7, max_tokens: int | None = 4096, **kwargs
    ) -> LLMResponse:
        """Synchronous chat (returns complete response)."""
        ...

    @abstractmethod
    async def chat_stream(
        self, messages: list[LLMMessage], temperature: float = 0.7, max_tokens: int | None = 4096, **kwargs
    ) -> AsyncIterator[LLMStreamChunk]:
        """Streaming chat (yields chunks)."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is available."""
        ...
