"""Multi-agent debate orchestrator（增强版：注入价值分析数据 + 工具清单 + 联网搜索）。

agent 不再"盲评"——_agent_analyze 前：
1. 调 value_analysis.analyze(db, code) 拿 6 维数据注入 user message（复用 chat.py 管线）
2. 注入 /agent/tools 工具清单到 system_prompt（让 agent 知道可用工具）
3. 如果标的需要新闻/行业动态 → 调 /agent/web-search 联网搜索注入
"""

import asyncio
import json
import logging
from dataclasses import dataclass

from app.services.llm.provider import LLMMessage, LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class AgentOpinion:
    agent_id: int
    agent_name: str
    content: str


@dataclass
class DebateRound:
    round_type: str  # analysis / challenge / response
    opinions: list[AgentOpinion]


@dataclass
class DebateResult:
    rounds: list[DebateRound]
    summary: str


class DebateOrchestrator:
    """Orchestrate multi-agent debates with data injection + tool awareness."""

    def __init__(self, llm: LLMProvider, db=None):
        self.llm = llm
        self.db = db

    async def run_debate(
        self,
        agents: list[dict],
        target_info: dict,
        max_rounds: int = 3,
    ) -> DebateResult:
        """Run a full debate (blocking, returns complete result)."""
        async for _ in self.run_debate_stream(agents, target_info, max_rounds):
            pass  # drain the generator
        return DebateResult(rounds=self._stream_history, summary=self._stream_summary)

    _stream_history: list = []
    _stream_summary: str = ""

    async def run_debate_stream(
        self,
        agents: list[dict],
        target_info: dict,
        max_rounds: int = 3,
    ):
        """Async generator: yields DebateRound after each round, then summary string.

        Usage:
            async for item in orchestrator.run_debate_stream(...):
                if isinstance(item, DebateRound): ...
                elif isinstance(item, str): # summary
        """
        context_data = await self._prepare_context(target_info)
        history: list[DebateRound] = []

        for round_num in range(max_rounds):
            if round_num == 0:
                debate_round = await self._round_analysis(agents, target_info, context_data)
            elif round_num % 2 == 1:
                debate_round = await self._round_challenge(agents, history)
            else:
                debate_round = await self._round_response(agents, history)
            history.append(debate_round)
            logger.info(f"Debate round {round_num + 1} ({debate_round.round_type}) completed")
            yield debate_round

        summary = await self._summarize(agents, target_info, history)
        self._stream_history = history
        self._stream_summary = summary
        yield summary

    async def _prepare_context(self, target: dict) -> str:
        """预取数据：价值分析 + 联网搜索（所有 agent 共享，不重复拉取）。"""
        parts = []

        # 1. 价值分析数据（复用 chat.py / value_analysis 管线）
        if target.get("type") == "stock" and self.db:
            code = target.get("code", "")
            try:
                from app.services.data.cache import ensure_financial_reports
                from app.services.data.value_analysis import analyze

                await ensure_financial_reports(self.db, code)
                await self.db.commit()
                va = await analyze(self.db, code)
                if "error" not in va:
                    parts.append("<stock_data>")
                    parts.append(json.dumps(va.get("latest", {}), ensure_ascii=False, default=str)[:1200])
                    parts.append(f"估值: {json.dumps(va.get('valuation', {}), ensure_ascii=False, default=str)}")
                    parts.append(f"成长: {json.dumps(va.get('growth', {}), ensure_ascii=False, default=str)}")
                    parts.append("</stock_data>")
                    logger.info(f"Debate: injected value_analysis data for {code}")
            except Exception as e:
                logger.warning(f"Debate: value_analysis failed for {code}: {e}")

        # 2. 联网搜索（新闻/行业动态）
        if target.get("type") == "stock":
            code = target.get("code", "")
            name = target.get("name", code)
            try:
                search_result = await self._web_search(f"{name} 股票 最新新闻 行业动态")
                if search_result:
                    parts.append(f"<web_search>\n{search_result}\n</web_search>")
                    logger.info(f"Debate: injected web search for {name}")
            except Exception as e:
                logger.warning(f"Debate: web search failed: {e}")

        return "\n".join(parts)

    async def _web_search(self, query: str) -> str:
        """调 /agent/web-search 逻辑（tavily 优先，DuckDuckGo 备选）。"""
        import os

        import httpx

        tavily_key = os.environ.get("TAVILY_API_KEY")
        if tavily_key:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(
                        "https://api.tavily.com/search",
                        json={"api_key": tavily_key, "query": query, "max_results": 3, "include_answer": True},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        return data.get("answer", "") + "\n" + "\n".join(
                            f"- {r.get('title','')}: {r.get('content','')[:150]}" for r in data.get("results", [])
                        )
            except Exception:
                pass

        # DuckDuckGo fallback
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = []
                    if data.get("AbstractText"):
                        results.append(data["AbstractText"][:300])
                    for topic in (data.get("RelatedTopics") or [])[:3]:
                        if isinstance(topic, dict) and topic.get("Text"):
                            results.append(topic["Text"][:150])
                    return "\n".join(results) if results else ""
        except Exception:
            pass
        return ""

    def _build_system_prompt(self, agent: dict) -> str:
        """注入工具清单到 agent system_prompt（让 agent 知道可用工具）。"""
        system = agent["system_prompt"]
        # 工具描述（精简版，不让 system_prompt 过长）
        tool_desc = (
            "\n\n--- 可用工具（数据已自动获取注入下方，你可以引用这些数据）---\n"
            "value_analysis: 估值/盈利/财务安全/现金流/成长性/分红（6维）\n"
            "web_search: 联网搜索公司新闻/行业动态（已自动搜索注入）\n"
            "quotes_kline: 历史K线（日/周/月/季/年）\n"
            "financials: 周期财报历史\n"
            "quant_backtest_run: 策略回测\n"
            "quant_risk_dashboard: 组合风险看板\n"
            "--- 以上数据已自动获取并注入下方的 <stock_data> / <web_search> 标签中 ---"
        )
        return system + tool_desc

    async def _round_analysis(self, agents: list[dict], target: dict, context_data: str = "") -> DebateRound:
        """Round 1: independent analysis (parallel) with data injection."""
        tasks = [self._agent_analyze(a, target, context_data) for a in agents]
        opinions = await asyncio.gather(*tasks)
        return DebateRound(round_type="analysis", opinions=list(opinions))

    async def _agent_analyze(self, agent: dict, target: dict, context_data: str = "") -> AgentOpinion:
        """分析标的——注入价值分析数据 + 工具清单。"""
        system = self._build_system_prompt(agent)
        user_content = f"""请基于你的投资理念，分析以下投资标的：

标的：{target.get("name", "")}（{target.get("code", "")}）
关键数据：
{json.dumps(target.get("data", {}), ensure_ascii=False, indent=2)}

{context_data}

请给出详细分析（每部分至少3-5句话）：
1. 投资价值判断（引用上方数据）
2. 核心理由（至少3条）
3. 主要风险
4. 建议操作"""

        response = await self.llm.chat([
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=user_content),
        ], max_tokens=8192)
        logger.info(f"Agent {agent['name']}: finish_reason={response.finish_reason}, content_len={len(response.content)}")
        return AgentOpinion(
            agent_id=agent["id"], agent_name=agent["name"], content=response.content
        )

    async def _round_challenge(self, agents: list[dict], history: list[DebateRound]) -> DebateRound:
        """Challenge round: each agent critiques others' views."""
        last_round = history[-1]
        opinions = []
        for agent in agents:
            others = [op for op in last_round.opinions if op.agent_id != agent["id"]]
            others_text = "\n\n".join([f"【{op.agent_name}】: {op.content}" for op in others])
            system = self._build_system_prompt(agent)
            response = await self.llm.chat([
                LLMMessage(role="system", content=system),
                LLMMessage(
                    role="user",
                    content=f"以下是其他投资者的观点：\n\n{others_text}\n\n请从你的投资理念出发，对这些观点提出质疑。引用数据支撑你的反驳。",
                ),
            ], max_tokens=8192)
            opinions.append(AgentOpinion(agent_id=agent["id"], agent_name=agent["name"], content=response.content))
        return DebateRound(round_type="challenge", opinions=opinions)

    async def _round_response(self, agents: list[dict], history: list[DebateRound]) -> DebateRound:
        """Response round: each agent responds to challenges."""
        challenge_round = history[-1]
        opinions = []
        for agent in agents:
            challenges = [op for op in challenge_round.opinions if op.agent_id != agent["id"]]
            text = "\n\n".join([f"【{op.agent_name}的质疑】: {op.content}" for op in challenges])
            system = self._build_system_prompt(agent)
            response = await self.llm.chat([
                LLMMessage(role="system", content=system),
                LLMMessage(
                    role="user",
                    content=f"其他投资者对你的分析提出了以下质疑：\n\n{text}\n\n请回应这些质疑。用数据论证。",
                ),
            ], max_tokens=8192)
            opinions.append(AgentOpinion(agent_id=agent["id"], agent_name=agent["name"], content=response.content))
        return DebateRound(round_type="response", opinions=opinions)

    async def _summarize(self, agents: list[dict], target: dict, history: list[DebateRound]) -> str:
        """Neutral agent summarizes the debate."""
        all_content = []
        for r in history:
            round_text = f"\n=== {r.round_type} ===\n"
            for op in r.opinions:
                round_text += f"\n【{op.agent_name}】:\n{op.content}\n"
            all_content.append(round_text)

        response = await self.llm.chat([
            LLMMessage(
                role="system",
                content="""你是一位客观中立的投资分析总结专家。请综合辩论内容输出分析报告：
## 辩论总结
### 多方观点
### 空方观点
### 共识点
### 分歧点
### 风险提示
### 综合建议""",
            ),
            LLMMessage(
                role="user",
                content=f"标的：{target.get('name', '')}\n\n辩论内容：\n{''.join(all_content)}",
            ),
        ], max_tokens=8192)
        return response.content
