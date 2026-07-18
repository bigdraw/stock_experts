"""Book analyzer: extract investment principles and generate agent definitions."""

import json
import logging

from app.services.book.parser import BookContent
from app.services.llm.provider import LLMMessage, LLMProvider

logger = logging.getLogger(__name__)

CHUNK_SIZE = 8000  # characters per chunk


class BookAnalyzer:
    """Analyze book content and generate investment agent definitions."""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def analyze(self, content: BookContent) -> dict:
        """Analyze entire book and generate agent definition."""
        chunks = self._split_chunks(content.text, CHUNK_SIZE)
        logger.info(f"Analyzing book '{content.title}' ({len(chunks)} chunks)")

        # Analyze each chunk
        chunk_analyses = []
        for i, chunk in enumerate(chunks):
            logger.info(f"  Analyzing chunk {i+1}/{len(chunks)}")
            analysis = await self._analyze_chunk(chunk, i, len(chunks))
            chunk_analyses.append(analysis)

        # Synthesize into agent definition
        agent_def = await self._synthesize(chunk_analyses, content.title)
        logger.info(f"Agent definition generated for '{content.title}'")
        return agent_def

    async def _analyze_chunk(self, text: str, index: int, total: int) -> str:
        """Analyze a single text chunk."""
        response = await self.llm.chat([
            LLMMessage(role="system", content="""你是一位投资书籍分析专家。请从以下文本中提取：
1. 核心投资理念和哲学
2. 具体的投资策略和规则
3. 风险管理和仓位控制方法
4. 选股标准和评估框架
5. 关键的投资纪律和禁忌

以结构化 JSON 输出，如果某项在本文本段中未涉及则留空。"""),
            LLMMessage(role="user", content=f"[第 {index+1}/{total} 部分]\n{text}"),
        ])
        return response.content

    async def _synthesize(self, analyses: list[str], book_title: str) -> dict:
        """Synthesize all chunk analyses into a final agent definition."""
        response = await self.llm.chat([
            LLMMessage(role="system", content=f"""你是投资 Agent 定义专家。基于以下对《{book_title}》的分析结果，
生成一个完整的投资 Agent 定义。

输出格式（JSON）：
{{
    "name": "agent 名称（基于书中作者/理念）",
    "description": "一句话描述投资风格",
    "system_prompt": "完整的 system prompt，包含投资理念、策略框架、决策规则、风险管理、选股标准",
    "config": {{
        "style": "价值投资/成长投资/趋势跟踪/...",
        "risk_tolerance": "low/medium/high",
        "holding_period": "short/medium/long",
        "key_metrics": ["ROE", "PE", ...],
        "decision_rules": ["规则1", "规则2", ...]
    }}
}}

只输出 JSON，不要解释。"""),
            LLMMessage(role="user", content="\n\n---\n\n".join(analyses)),
        ])
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            match = re.search(r"\{.*\}", response.content, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError("Failed to parse agent definition from LLM response")

    @staticmethod
    def _split_chunks(text: str, chunk_size: int) -> list[str]:
        """Split text into chunks."""
        chunks = []
        for i in range(0, len(text), chunk_size):
            chunks.append(text[i:i + chunk_size])
        return chunks
