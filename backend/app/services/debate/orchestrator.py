"""Multi-agent debate orchestrator."""

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
    """Orchestrate multi-agent debates."""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def run_debate(
        self,
        agents: list[dict],  # [{id, name, system_prompt, description}]
        target_info: dict,  # {type, code, name, data}
        max_rounds: int = 3,
    ) -> DebateResult:
        """Run a full debate."""
        history: list[DebateRound] = []

        for round_num in range(max_rounds):
            if round_num == 0:
                debate_round = await self._round_analysis(agents, target_info)
            elif round_num % 2 == 1:
                debate_round = await self._round_challenge(agents, history)
            else:
                debate_round = await self._round_response(agents, history)
            history.append(debate_round)
            logger.info(f"Debate round {round_num + 1} ({debate_round.round_type}) completed")

        summary = await self._summarize(agents, target_info, history)
        return DebateResult(rounds=history, summary=summary)

    async def _round_analysis(self, agents: list[dict], target: dict) -> DebateRound:
        """Round 1: independent analysis (parallel)."""
        tasks = [self._agent_analyze(a, target) for a in agents]
        opinions = await asyncio.gather(*tasks)
        return DebateRound(round_type="analysis", opinions=list(opinions))

    async def _agent_analyze(self, agent: dict, target: dict) -> AgentOpinion:
        response = await self.llm.chat(
            [
                LLMMessage(role="system", content=agent["system_prompt"]),
                LLMMessage(
                    role="user",
                    content=f"""请基于你的投资理念，分析以下投资标的：

标的：{target.get("name", "")}（{target.get("code", "")}）
关键数据：
{json.dumps(target.get("data", {}), ensure_ascii=False, indent=2)}

请给出：1.投资价值判断 2.核心理由 3.主要风险 4.建议操作""",
                ),
            ]
        )
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
            response = await self.llm.chat(
                [
                    LLMMessage(role="system", content=agent["system_prompt"]),
                    LLMMessage(
                        role="user",
                        content=f"以下是其他投资者的观点：\n\n{others_text}\n\n请从你的投资理念出发，对这些观点提出质疑。",
                    ),
                ]
            )
            opinions.append(
                AgentOpinion(
                    agent_id=agent["id"], agent_name=agent["name"], content=response.content
                )
            )
        return DebateRound(round_type="challenge", opinions=opinions)

    async def _round_response(self, agents: list[dict], history: list[DebateRound]) -> DebateRound:
        """Response round: each agent responds to challenges."""
        challenge_round = history[-1]
        opinions = []
        for agent in agents:
            challenges = [op for op in challenge_round.opinions if op.agent_id != agent["id"]]
            text = "\n\n".join([f"【{op.agent_name}的质疑】: {op.content}" for op in challenges])
            response = await self.llm.chat(
                [
                    LLMMessage(role="system", content=agent["system_prompt"]),
                    LLMMessage(
                        role="user",
                        content=f"其他投资者对你的分析提出了以下质疑：\n\n{text}\n\n请回应这些质疑。",
                    ),
                ]
            )
            opinions.append(
                AgentOpinion(
                    agent_id=agent["id"], agent_name=agent["name"], content=response.content
                )
            )
        return DebateRound(round_type="response", opinions=opinions)

    async def _summarize(self, agents: list[dict], target: dict, history: list[DebateRound]) -> str:
        """Neutral agent summarizes the debate."""
        all_content = []
        for r in history:
            round_text = f"\n=== {r.round_type} ===\n"
            for op in r.opinions:
                round_text += f"\n【{op.agent_name}】:\n{op.content}\n"
            all_content.append(round_text)

        response = await self.llm.chat(
            [
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
            ]
        )
        return response.content
