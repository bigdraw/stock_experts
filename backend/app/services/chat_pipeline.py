"""Chat context pipeline — 参考 LobeChat 的 provider/processor 管线模式。

LobeChat 用 7 个 phase + 20+ provider 组装 system prompt。我们简化为 4 个
Provider + 1 个 Processor：
- HistoryTruncateProcessor: 按轮截断历史
- SystemRoleProvider: 注入 agent system_prompt
- HistorySummaryProvider: 注入压缩摘要
- StockDataProvider: 股票代码自动取数，追加到 user 消息
"""

from __future__ import annotations

import json
import logging
import math
import re
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

# 压缩阈值（参考 LobeChat tokenCounter.ts）
DEFAULT_MAX_CONTEXT = 128_000
DEFAULT_THRESHOLD_RATIO = 0.5
DEFAULT_DRIFT_MULTIPLIER = 1.25
PRESERVE_RECENT_TURNS = 4  # 压缩时保留最近几轮


class ChatProvider(ABC):
    """注入内容的 provider（对应 LobeChat BaseProvider）。"""

    name: str
    inject_position: str  # "system" | "last_user"

    @abstractmethod
    async def build_content(self, ctx: dict[str, Any]) -> str | None:
        ...

    def should_inject(self, ctx: dict[str, Any]) -> bool:
        return True


class ChatProcessor(ABC):
    """消息变换 processor（对应 LobeChat ContextProcessor）。"""

    name: str

    @abstractmethod
    async def process(self, messages: list[dict], ctx: dict[str, Any]) -> list[dict]:
        ...


# --- Providers ---


class SystemRoleProvider(ChatProvider):
    """注入 agent 的 system_prompt（对应 LobeChat SystemRoleInjector）。"""

    name = "SystemRole"
    inject_position = "system"

    async def build_content(self, ctx: dict[str, Any]) -> str | None:
        parts = ["你是一个投资分析助手。基于以下投资理念回答用户问题。"]
        agents = ctx.get("agents", [])
        if agents:
            for a in agents:
                parts.append(f"\n--- Agent: {a.name} ---\n{a.system_prompt}")
        else:
            # 无指定 agent → 用默认
            default = ctx.get("default_agent")
            if default:
                parts.append(f"\n--- {default.name} ---\n{default.system_prompt}")
        return "\n".join(parts)


class HistorySummaryProvider(ChatProvider):
    """注入压缩摘要（对应 LobeChat HistorySummaryProvider）。"""

    name = "HistorySummary"
    inject_position = "system"

    async def build_content(self, ctx: dict[str, Any]) -> str | None:
        summary = ctx.get("session_summary")
        if not summary:
            return None
        return f"<chat_history_summary>\n{summary}\n</chat_history_summary>"


class StockDataProvider(ChatProvider):
    """股票代码自动取数，包 <stock_data> 追加到 user 消息（对应 LobeChat BaseLastUserContentProvider）。"""

    name = "StockData"
    inject_position = "last_user"

    async def build_content(self, ctx: dict[str, Any]) -> str | None:
        message = ctx.get("message", "")
        db = ctx.get("db")
        if not db or not message:
            return None

        stock_codes = re.findall(r"\b(\d{6})\b", message)
        if not stock_codes:
            return None

        context_parts = []
        for code in stock_codes[:3]:
            try:
                from app.services.data.cache import ensure_financial_reports
                from app.services.data.value_analysis import analyze

                await ensure_financial_reports(db, code)
                await db.commit()
                va = await analyze(db, code)
                if "error" not in va:
                    context_parts.append(
                        f"--- {code} ---\n"
                        + json.dumps(va.get("latest", {}), ensure_ascii=False, default=str)[:800]
                        + f"\n估值: {json.dumps(va.get('valuation', {}), ensure_ascii=False, default=str)}"
                        + f"\n成长: {json.dumps(va.get('growth', {}), ensure_ascii=False, default=str)}"
                    )
            except Exception:
                pass

        if not context_parts:
            return None
        return f"<stock_data>\n{''.join(context_parts)}\n</stock_data>"


# --- Processors ---


class HistoryTruncateProcessor(ChatProcessor):
    """按轮截断历史（对应 LobeChat HistoryTruncateProcessor，简化版）。

    1 user + 1 assistant = 1 轮。保留最近 N 轮 + 最新未回复 user。
    """

    name = "HistoryTruncate"

    async def process(self, messages: list[dict], ctx: dict[str, Any]) -> list[dict]:
        max_turns = ctx.get("max_history_turns", 20)
        if len(messages) <= max_turns * 2:
            return messages
        # 从末尾往前取 max_turns 轮（每轮 user+assistant）
        cut = len(messages) - max_turns * 2
        # 确保不切在 assistant 消息中间（切点必须是 user 消息前）
        while cut < len(messages) and messages[cut].get("role") != "user":
            cut += 1
        return messages[cut:]


# --- Pipeline ---


class ChatPipeline:
    """管线执行器（对应 LobeChat ContextEngine）。"""

    def __init__(
        self,
        providers: list[ChatProvider] | None = None,
        processors: list[ChatProcessor] | None = None,
    ):
        self.providers = providers or [
            SystemRoleProvider(),
            HistorySummaryProvider(),
            StockDataProvider(),
        ]
        self.processors = processors or [HistoryTruncateProcessor()]

    async def run(self, messages: list[dict], ctx: dict[str, Any]) -> list[dict]:
        """执行管线：先 processors 变换消息，再 providers 注入内容。"""
        # Phase 1: processors
        for proc in self.processors:
            messages = await proc.process(messages, ctx)

        # Phase 2-4: providers
        system_parts: list[str] = []
        last_user_injection: list[str] = []

        for prov in self.providers:
            if not prov.should_inject(ctx):
                continue
            content = await prov.build_content(ctx)
            if not content:
                continue
            if prov.inject_position == "system":
                system_parts.append(content)
            elif prov.inject_position == "last_user":
                last_user_injection.append(content)

        # 组装：system 消息
        if system_parts:
            sys_content = "\n\n".join(system_parts)
            # 找或创建 system 消息
            has_system = False
            for msg in messages:
                if msg["role"] == "system":
                    msg["content"] = msg["content"] + "\n\n" + sys_content
                    has_system = True
                    break
            if not has_system:
                messages.insert(0, {"role": "system", "content": sys_content})

        # 追加到最后一条 user 消息
        if last_user_injection:
            for msg in reversed(messages):
                if msg["role"] == "user":
                    msg["content"] = msg["content"] + "\n\n" + "\n\n".join(last_user_injection)
                    break

        return messages


# --- 上下文压缩 ---


def estimate_tokens(text: str) -> int:
    """粗略 token 估算：4 char ≈ 1 token（英文）/ 1.5 char ≈ 1 token（中文）。取折中。"""
    return max(1, len(text) // 4)


def should_compress(messages: list[dict]) -> bool:
    """判断是否需要压缩（参考 LobeChat shouldCompress）。"""
    raw_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
    adjusted = math.ceil(raw_tokens * DEFAULT_DRIFT_MULTIPLIER)
    threshold = math.floor(DEFAULT_MAX_CONTEXT * DEFAULT_THRESHOLD_RATIO)
    return adjusted > threshold


async def compress_context(
    messages: list[dict],
    session,
    db,
    llm_manager,
) -> str | None:
    """压缩上下文：取前 N-4 条调 LLM 生成摘要，保留最近 4 条。

    参考 LobeChat compressContext.ts 的 createGroup → buildPrompt → stream → finalize 四步，
    简化为：取旧消息 → 调 LLM 摘要 → 返回摘要文本（调用方负责存 session.summary + 标记 is_compressed）。
    """
    if len(messages) <= PRESERVE_RECENT_TURNS * 2:
        return None

    to_compress = messages[:-PRESERVE_RECENT_TURNS * 2]
    if not to_compress:
        return None

    # buildPrompt（对应 LobeChat compression.buildPrompt）
    conversation_text = "\n".join(
        f"[{m['role']}]: {m.get('content', '')[:500]}" for m in to_compress
    )
    existing_summary = session.summary or ""

    prompt_messages = [
        {"role": "system", "content": "请总结以下对话的关键信息，包括涉及的股票代码、分析结论、用户偏好。保持简洁（300字以内）。"},
        {"role": "user", "content": f"已有摘要：{existing_summary}\n\n新对话内容：\n{conversation_text}"},
    ]

    try:
        from app.services.llm.provider import LLMMessage

        llm = llm_manager.get()
        response = await llm.chat([
            LLMMessage(role=m["role"], content=m["content"]) for m in prompt_messages
        ])
        return response.content
    except Exception as e:
        logger.error(f"Context compression failed: {e}")
        return None
