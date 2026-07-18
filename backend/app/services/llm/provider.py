"""LLM Provider abstraction layer."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class LLMMessage:
    """Single message in a conversation."""
    role: str  # system / user / assistant
    content: str


@dataclass
class LLMResponse:
    """Complete LLM response."""
    content: str
    model: str
    usage: dict  # {prompt_tokens, completion_tokens, total_tokens}
    finish_reason: str


@dataclass
class LLMStreamChunk:
    """Streaming chunk from LLM."""
    content: str
    finish_reason: str | None = None


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> LLMResponse:
        """Synchronous chat (returns complete response)."""
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> AsyncIterator[LLMStreamChunk]:
        """Streaming chat (yields chunks)."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is available."""
        ...
