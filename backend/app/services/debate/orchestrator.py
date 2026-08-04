"""Multi-agent debate orchestrator（两阶段辩论）。

阶段1（纯代码，FactBook）：拉取全量数据 + 客观校验，所有 agent 共享同一份事实基础。
阶段2（LLM agent，基于 FactBook）：投资大师分析 → 质疑 → 回应 → 总结。

agent 仍可在 system_prompt 里追加工具清单，按自己风格获取关注的其他信息。
"""

import asyncio
import json
import logging
from dataclasses import dataclass

from app.services.debate.factbook import FactBook
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
        """阶段1：调 FactBook.collect() 拉全量数据 + 客观校验，格式化为共享事实基础。

        所有 agent 看到同一份 FactBook（含 trend20期 + dividends + 5年K线趋势 +
        行业动态 + 宏观政策 + 沪深300 regime + 校验结果）。不截断到固定字符数，
        让 LLM 看到全量数据；K线只注入统计摘要而非数千根原始K线。
        """
        if target.get("type") == "stock" and self.db:
            code = target.get("code", "")
            try:
                factbook = await FactBook().collect(code, self.db)
                await self.db.commit()
                logger.info(f"Debate: FactBook collected for {code} (status={factbook.get('validation', {}).get('status')})")
                return FactBook().format(factbook)
            except Exception as e:
                logger.warning(f"Debate: FactBook collection failed for {code}: {e}")
                # 降级：注入最小事实
                name = target.get("name", code)
                return f"<data_warnings>FactBook 采集失败: {e}</data_warnings>\n<target>标的: {name}（{code}）</target>"
        # 非 stock 标的：仅注入基本描述
        name = target.get("name", "")
        return f"<target>标的: {name}</target>\n<data_warnings>非个股标的，未采集 FactBook</data_warnings>"

    def _build_system_prompt(self, agent: dict) -> str:
        """注入工具清单到 agent system_prompt（让 agent 知道可用工具 + 已注入数据）。"""
        system = agent["system_prompt"]
        tool_desc = (
            "\n\n--- 共享事实基础（FactBook，已自动采集注入下方 user 消息）---\n"
            "<data_warnings>: 数据质量告警（财报时效/K线缺口/字段缺失）——先看这个再引用数据\n"
            "<value_analysis>: 6维估值/盈利/财务安全/现金流/成长性 + trend 20期财报序列 + dividends\n"
            "<kline_summary>: 5年K线趋势（涨跌/年化/最大回撤/高低点/量比/周月线方向）\n"
            "<industry>: 行业动态与竞争格局（web_search）\n"
            "<macro>: 宏观政策/利率/CPI（web_search）\n"
            "<market_regime>: 沪深300市场状态（bull/bear/choppy/transitional）\n"
            "--- 以上为统一事实基础，所有 agent 看到相同数据；你可引用其中任何一节 ---\n"
            "--- 如需补充特色数据，仍可调用：quotes_kline（历史K线）/ financials（周期财报）/"
            "quant_backtest_run（回测）/ quant_risk_dashboard（组合风险看板）---"
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
基础信息：{json.dumps(target.get("data", {}), ensure_ascii=False, indent=2)}

以下是本次辩论的共享事实基础（FactBook），所有参与者看到相同数据；请引用其中相关节做论证：

{context_data}

请给出详细分析（每部分至少3-5句话，**必须引用 FactBook 中的数据**——可结合估值/财报trend/K线趋势/行业/宏观/市场状态）：
1. 投资价值判断（引用具体数据）
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
