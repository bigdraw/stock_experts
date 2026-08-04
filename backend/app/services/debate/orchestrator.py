"""Multi-agent debate orchestrator（两阶段辩论）。

阶段1（纯代码，FactBook）：拉取全量数据 + 客观校验，所有 agent 共享同一份事实基础。
阶段2（LLM agent，基于 FactBook）：投资大师分析 → 质疑 → 回应 → 总结。

agent 仍可在 system_prompt 里追加工具清单，按自己风格获取关注的其他信息。
"""

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
        """流式辩论生成器：yield 结构化事件 dict（不再是 DebateRound/str）。

        事件类型：
          {"type":"factbook","content": str}                          # 共享事实基础（用户也可见）
          {"type":"agent_start","round_num","round_type","agent_id","agent_name"}
          {"type":"agent_token","round_num","agent_id","delta"}        # token 增量（逐字回流）
          {"type":"agent_done","round_num","round_type","agent_id","agent_name","content","finish_reason"}
          {"type":"summary_start"}
          {"type":"summary_token","delta"}
          {"type":"summary_done","content"}

        每个 agent 顺序发言、token 实时回流——用户逐字看到每个 agent 的回答，
        不必等整轮全部答完。单个 agent 调用失败（超时/LLM 错误）替换为错误占位、
        不中断整场辩论。
        """
        context_data = await self._prepare_context(target_info)
        yield {"type": "factbook", "content": context_data}

        history: list[DebateRound] = []
        for round_num in range(max_rounds):
            round_type = "analysis" if round_num == 0 else ("challenge" if round_num % 2 == 1 else "response")
            opinions: list[AgentOpinion] = []
            for agent in agents:
                yield {
                    "type": "agent_start", "round_num": round_num + 1, "round_type": round_type,
                    "agent_id": agent["id"], "agent_name": agent["name"],
                }
                messages = self._build_agent_messages(agent, round_type, target_info, context_data, history)
                content, finish_reason = "", None
                try:
                    async for chunk in self.llm.chat_stream(messages, max_tokens=8192):
                        if chunk.content:
                            content += chunk.content
                            yield {"type": "agent_token", "round_num": round_num + 1,
                                   "agent_id": agent["id"], "delta": chunk.content}
                        if chunk.finish_reason:
                            finish_reason = chunk.finish_reason
                except Exception as e:
                    logger.exception(f"Agent {agent['name']} {round_type} failed")
                    content = f"[本 agent 此轮调用失败: {e}]"
                yield {
                    "type": "agent_done", "round_num": round_num + 1, "round_type": round_type,
                    "agent_id": agent["id"], "agent_name": agent["name"],
                    "content": content, "finish_reason": finish_reason,
                }
                opinions.append(AgentOpinion(agent_id=agent["id"], agent_name=agent["name"], content=content))
            history.append(DebateRound(round_type=round_type, opinions=opinions))
            logger.info(f"Debate round {round_num + 1} ({round_type}) completed")

        yield {"type": "summary_start"}
        summary = ""
        try:
            async for chunk in self.llm.chat_stream(
                self._summarize_messages(agents, target_info, history), max_tokens=8192
            ):
                if chunk.content:
                    summary += chunk.content
                    yield {"type": "summary_token", "delta": chunk.content}
        except Exception as e:
            logger.exception("Debate summary failed")
            summary = f"[总结失败: {e}]"
        yield {"type": "summary_done", "content": summary}
        self._stream_history = history
        self._stream_summary = summary

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
        """追加 FactBook 说明 + 反 ReAct 幻觉约束到 agent system_prompt。

        关键：不向 agent 宣称"可调用工具"——orchestrator 没有真正的 tool-calling
        循环，宣称工具会诱导 agent 把 tavily_search(...) 等调用语法写成文本输出
        （ReAct 幻觉），最终分析结论缺失。行业/宏观数据已由 FactBook 在代码层
        自动采集注入，agent 直接引用即可。
        """
        system = agent["system_prompt"]
        tool_desc = (
            "\n\n--- 共享事实基础（FactBook，已自动采集，注入下方 user 消息）---\n"
            "<data_warnings>: 数据质量告警（财报时效/K线缺口/字段缺失）——先看再引用\n"
            "<value_analysis>: 6维估值/盈利/财务安全/现金流/成长性 + trend 20期财报序列 + dividends\n"
            "<kline_summary>: 5年K线趋势（涨跌/年化/最大回撤/高低点/量比/周月线方向）\n"
            "<industry>: 行业动态与竞争格局（已自动联网采集）\n"
            "<macro>: 宏观政策/利率/CPI（已自动联网采集）\n"
            "<market_regime>: 沪深300市场状态（bull/bear/choppy/transitional）\n"
            "--- 以上为统一事实基础，所有 agent 看到相同数据 ---\n"
            "--- 重要：行业/宏观/新闻数据已由 FactBook 自动采集，你无需也无法调用外部工具。"
            "直接基于已注入数据分析，禁止输出工具调用语法（如 tavily_search(...)、"
            "web_search(...)），禁止模拟搜索/调用过程，直接给出分析结论。 ---"
        )
        return system + tool_desc

    def _build_agent_messages(
        self, agent: dict, round_type: str, target: dict, context_data: str, history: list[DebateRound],
    ) -> list[LLMMessage]:
        """按轮次类型构造单个 agent 的 LLM 消息（分析/质疑/回应）。

        合并原 _agent_analyze / _round_challenge / _round_response 的消息构造逻辑。
        """
        system = self._build_system_prompt(agent)
        if round_type == "analysis":
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
        elif round_type == "challenge":
            last_round = history[-1]
            others = [op for op in last_round.opinions if op.agent_id != agent["id"]]
            others_text = "\n\n".join([f"【{op.agent_name}】: {op.content}" for op in others])
            user_content = f"以下是其他投资者的观点：\n\n{others_text}\n\n请从你的投资理念出发，对这些观点提出质疑。引用数据支撑你的反驳。"
        else:  # response
            challenge_round = history[-1]
            challenges = [op for op in challenge_round.opinions if op.agent_id != agent["id"]]
            text = "\n\n".join([f"【{op.agent_name}的质疑】: {op.content}" for op in challenges])
            user_content = f"其他投资者对你的分析提出了以下质疑：\n\n{text}\n\n请回应这些质疑。用数据论证。"
        return [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user_content)]

    def _summarize_messages(self, agents: list[dict], target: dict, history: list[DebateRound]) -> list[LLMMessage]:
        """构造总结 agent 的 LLM 消息。"""
        all_content = []
        for r in history:
            round_text = f"\n=== {r.round_type} ===\n"
            for op in r.opinions:
                round_text += f"\n【{op.agent_name}】:\n{op.content}\n"
            all_content.append(round_text)
        return [
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
