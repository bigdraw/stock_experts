"""OpenAI-compatible provider reasoning field-reading tests (Part 2).

The provider must read thinking/reasoning from multiple delta field names
(qwen3=reasoning_content, OpenAI o-series=reasoning, DeepSeek/Qwen-thinking=thinking),
first non-empty wins. A 2nd turn after a tool-call may switch fields — only
reading reasoning_content misses it → 思维链不恢复.
"""

import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.services.llm.openai_compatible import OpenAICompatibleProvider  # noqa: E402
from app.services.llm.provider import LLMMessage  # noqa: E402


class _FakeResp:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamCM:
    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return _FakeResp(self._lines)

    async def __aexit__(self, *a):
        return False


class _FakeClient:
    def __init__(self, lines):
        self._lines = lines

    def stream(self, method, url, json=None):
        return _FakeStreamCM(self._lines)


def _provider_with_lines(lines):
    p = OpenAICompatibleProvider(base_url="http://x", api_key="k", model="m")
    p.client = _FakeClient(lines)
    return p


async def _collect(p):
    out = []
    async for chunk in p.chat_stream([LLMMessage(role="user", content="hi")]):
        out.append(chunk)
    return out


async def test_reasoning_from_reasoning_content_field():
    """qwen3 default field — no regression."""
    lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"qwen think","content":""}}]}',
        "data: [DONE]",
    ]
    chunks = await _collect(_provider_with_lines(lines))
    assert chunks[0].reasoning == "qwen think", chunks[0].reasoning


async def test_reasoning_from_reasoning_field():
    """OpenAI o-series / generic 'reasoning' field (no reasoning_content)."""
    lines = [
        'data: {"choices":[{"delta":{"reasoning":"o-series think","content":""}}]}',
        "data: [DONE]",
    ]
    chunks = await _collect(_provider_with_lines(lines))
    assert chunks[0].reasoning == "o-series think", chunks[0].reasoning


async def test_reasoning_from_thinking_field():
    """DeepSeek / Qwen-thinking 'thinking' field."""
    lines = [
        'data: {"choices":[{"delta":{"thinking":"deep think","content":""}}]}',
        "data: [DONE]",
    ]
    chunks = await _collect(_provider_with_lines(lines))
    assert chunks[0].reasoning == "deep think", chunks[0].reasoning


async def test_reasoning_content_takes_priority_over_reasoning():
    """If both present, reasoning_content wins (qwen3 native)."""
    lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"primary","reasoning":"secondary"}}]}',
        "data: [DONE]",
    ]
    chunks = await _collect(_provider_with_lines(lines))
    assert chunks[0].reasoning == "primary"


async def test_content_still_streamed():
    """content field unaffected by reasoning change."""
    lines = [
        'data: {"choices":[{"delta":{"reasoning":"think","content":"hello"}}]}',
        "data: [DONE]",
    ]
    chunks = await _collect(_provider_with_lines(lines))
    assert chunks[0].content == "hello"
