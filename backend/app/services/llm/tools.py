"""LLM 工具（function-calling）：tavily_search 等供 agent 原生调用的工具。

agent 通过 OpenAI 兼容 function-calling 调用这些工具（不再是 ReAct 文本幻觉）：
模型返回 tool_calls → execute_tool 执行 → 结果以 role=tool 回灌 → 模型继续到最终答案。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# tavily_search 工具 schema（OpenAI function 格式）
TAVILY_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "tavily_search",
        "description": (
            "联网搜索最新信息（公司新闻/行业动态/宏观政策/分红/财报/价格等）。"
            "当问题需要实时或最新数据、或上下文 FactBook 缺失的信息时调用。"
            "返回搜索摘要 + 结果列表。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询（中文/英文均可，尽量具体）"},
                "max_results": {"type": "integer", "description": "返回结果数（默认 5）", "default": 5},
            },
            "required": ["query"],
        },
    },
}

# 供 agent 调用的全部工具（chat/debate 注入 LLM 的 tools 参数）
DEBATE_TOOLS = [TAVILY_SEARCH_TOOL]


async def tavily_search(query: str, max_results: int = 5) -> str:
    """联网搜索：tavily 优先（有 key），DuckDuckGo 备选。返回摘要 + 结果文本。

    不截断——交给 agent 自己消化。远端偶发断连 → 重试 2 次。
    """
    tavily_key = os.environ.get("TAVILY_API_KEY")
    if tavily_key:
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.post(
                        "https://api.tavily.com/search",
                        json={"api_key": tavily_key, "query": query,
                              "max_results": max_results, "include_answer": True},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        return (data.get("answer", "") or "") + "\n" + "\n".join(
                            f"- {r.get('title', '')}: {r.get('content', '')}"
                            for r in data.get("results", [])
                        )
            except Exception as e:
                logger.warning(f"tavily_search attempt {attempt + 1}/2 failed: {e!r}")
    # DuckDuckGo fallback
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = []
                    if data.get("AbstractText"):
                        results.append(data["AbstractText"])
                    for topic in (data.get("RelatedTopics") or [])[:max_results]:
                        if isinstance(topic, dict) and topic.get("Text"):
                            results.append(topic["Text"])
                    if results:
                        return "\n".join(results)
        except Exception as e:
            logger.warning(f"duckduckgo attempt {attempt + 1}/2 failed: {e!r}")
    return ""


async def execute_tool(name: str, arguments: dict[str, Any] | str) -> str:
    """按工具名执行，返回结果字符串（回灌 role=tool 消息）。"""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            arguments = {"query": arguments}
    if name == "tavily_search":
        q = arguments.get("query", "") or (arguments.get("q", "") if isinstance(arguments, dict) else "")
        n = arguments.get("max_results", 5)
        try:
            n = int(n)
        except Exception:
            n = 5
        result = await tavily_search(q, n)
        return result or f"（搜索为空：{q}）"
    return f"（未知工具：{name}）"
