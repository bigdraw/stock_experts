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
        *,
        resume: dict | None = None,
    ):
        """流式辩论生成器：yield 结构化事件 dict。

        事件类型：
          {"type":"factbook","content"}                                   # 共享事实基础
          {"type":"agent_start","round_num","round_type","agent_id","agent_name"}
          {"type":"agent_token","round_num","agent_id","delta"}            # token 逐字回流
          {"type":"agent_done","round_num","round_type","agent_id","agent_name","content","finish_reason"}
          {"type":"agent_failed","round_num","round_type","agent_id","agent_name","error"}  # 失败→暂停等重试
          {"type":"summary_start"} / {"type":"summary_token","delta"} / {"type":"summary_done","content"}
          {"type":"summary_failed","error"}                                # 总结失败→暂停

        状态管理：每个 agent 先 agent_start（前端显示"思考中"），首 token 到达转内容流，
        完成 agent_done；失败（重试3次仍错）发 agent_failed 后 **return 暂停**——不自动跳过，
        等前端原地点重试（调 resume-stream 端点，从失败点继续，已完成的 agent 跳过）。
        """
        if resume:
            history: list[DebateRound] = list(resume.get("history") or [])
            completed: set = resume.get("completed") or set()
            context_data: str = resume.get("context") or ""
            summary_done_flag: bool = resume.get("summary_done", False)
            if not context_data:
                context_data = await self._collect_raw_factbook(target_info)
        else:
            # 阶段1：事实 agent 消化原始 FactBook → 归类精炼的 digest（流式产出）
            raw = await self._collect_raw_factbook(target_info)
            context_data = ""
            async for ev in self._stream_fact_agent(raw, target_info):
                yield ev
                if ev.get("type") in ("factbook_done", "factbook"):
                    context_data = ev.get("content", "")
            if not context_data:
                context_data = FactBook().format(raw)  # 兜底
            history, completed, summary_done_flag = [], set(), False

        # 轮次模型：第 1..N-1 轮 = 辩论（analysis → challenge/response 交替），
        # 第 N 轮（最后一轮）= 中立 agent 综合总结。max_rounds=3 → 分析/质疑/总结。
        for round_num in range(max_rounds):
            if round_num == max_rounds - 1:
                # 最后一轮：中立总结（resume 时若已完成则跳过）
                if summary_done_flag:
                    return
                yield {"type": "summary_start"}
                summary = ""
                try:
                    async for chunk in self.llm.chat_stream(
                        self._summarize_messages(agents, target_info, history, context_data), max_tokens=8192
                    ):
                        if chunk.content:
                            summary += chunk.content
                            yield {"type": "summary_token", "delta": chunk.content}
                except Exception as e:
                    logger.exception("Debate summary failed; emit summary_failed + pause")
                    yield {"type": "summary_failed", "error": f"{e!r}"}
                    return
                yield {"type": "summary_done", "content": summary}
                self._stream_history = history
                self._stream_summary = summary
                return

            # 辩论轮（非最后）
            round_type = "analysis" if round_num == 0 else ("challenge" if round_num % 2 == 1 else "response")
            # 确保 history 对应槽位存在（resume 时已完成轮可能已预填）
            if len(history) <= round_num:
                history.append(DebateRound(round_type=round_type, opinions=[]))
            elif history[round_num].round_type != round_type:
                history[round_num] = DebateRound(round_type=round_type, opinions=history[round_num].opinions)
            for agent in agents:
                if (round_num + 1, agent["id"]) in completed:
                    continue  # resume 跳过已完成
                yield {
                    "type": "agent_start", "round_num": round_num + 1, "round_type": round_type,
                    "agent_id": agent["id"], "agent_name": agent["name"],
                }
                # challenge/response 引用**上一轮**（history[round_num-1]）的全部发言，
                # 不是 history[-1]（那会是当前正在建的轮，只有前面 agent 的发言）。
                messages = self._build_agent_messages(agent, round_type, round_num, target_info, context_data, history)
                content, finish_reason, last_err = "", None, None
                for attempt in range(3):
                    content, finish_reason = "", None
                    try:
                        async for chunk in self.llm.chat_stream(messages, max_tokens=8192):
                            if chunk.content:
                                content += chunk.content
                                yield {"type": "agent_token", "round_num": round_num + 1,
                                       "agent_id": agent["id"], "delta": chunk.content}
                            if chunk.finish_reason:
                                finish_reason = chunk.finish_reason
                        last_err = None
                        break
                    except Exception as e:
                        last_err = e
                        logger.warning(f"Agent {agent['name']} {round_type} attempt {attempt + 1}/3 failed: {e!r}")
                        if content:
                            break
                        continue
                if last_err and not content:
                    logger.exception(f"Agent {agent['name']} {round_type} gave up; emit agent_failed + pause")
                    yield {
                        "type": "agent_failed", "round_num": round_num + 1, "round_type": round_type,
                        "agent_id": agent["id"], "agent_name": agent["name"],
                        "error": f"{last_err!r}",
                    }
                    return
                yield {
                    "type": "agent_done", "round_num": round_num + 1, "round_type": round_type,
                    "agent_id": agent["id"], "agent_name": agent["name"],
                    "content": content, "finish_reason": finish_reason,
                }
                history[round_num].opinions.append(AgentOpinion(agent_id=agent["id"], agent_name=agent["name"], content=content))
            logger.info(f"Debate round {round_num + 1} ({round_type}) completed")

    async def _collect_raw_factbook(self, target: dict) -> dict:
        """阶段1：调 FactBook.collect() 拉全量原始数据 + 客观校验。

        返回 raw dict（不格式化、不截断）——交给事实 agent（_stream_fact_agent）消化精炼。
        """
        if target.get("type") == "stock" and self.db:
            code = target.get("code", "")
            try:
                factbook = await FactBook().collect(code, self.db)
                await self.db.commit()
                logger.info(f"Debate: FactBook collected for {code} (status={factbook.get('validation', {}).get('status')})")
                return factbook
            except Exception as e:
                logger.warning(f"Debate: FactBook collection failed for {code}: {e}")
                name = target.get("name", code)
                return {"_error": str(e), "stock_name": name, "stock_code": code}
        name = target.get("name", "")
        return {"stock_name": name, "stock_code": target.get("code", ""), "_error": "非个股标的"}

    async def _stream_fact_agent(self, raw: dict, target: dict):
        """阶段2：事实 agent（LLM，客观无投资观点）消化全部原始数据 → 归类精炼 digest。

        流式产出 factbook_start / factbook_token(delta) / factbook_done(content=digest)。
        digest 注入每个投资 agent 的每一轮，确保"标的+FactBook+关键信息"贯穿全程
        （修 challenge/response/summary 轮丢 FactBook 的 bug）。LLM 失败兜底用 FactBook.format。
        """
        yield {"type": "factbook_start"}
        digest = ""
        try:
            messages = self._fact_agent_messages(raw, target)
            async for chunk in self.llm.chat_stream(messages, max_tokens=4096):
                if chunk.content:
                    digest += chunk.content
                    yield {"type": "factbook_token", "delta": chunk.content}
        except Exception as e:
            logger.exception(f"Fact agent digest failed: {e!r}, fallback to FactBook.format")
            digest = FactBook().format(raw)
        if not digest:
            digest = FactBook().format(raw)
        yield {"type": "factbook_done", "content": digest}

    def _fact_agent_messages(self, raw: dict, target: dict) -> list[LLMMessage]:
        """事实 agent 的 LLM 消息：客观消化原始数据 → 分类关键信息。"""
        system = (
            "你是一位客观中立的**事实分析 agent**——不持任何投资观点，不做买卖判断。"
            "你的任务是消化以下原始数据（可能含估值/财报trend/K线/行业/宏观/市场状态，部分可能缺失），"
            "提炼出**投资决策最关键的信息**，分类输出，供后续投资大师辩论引用。\n\n"
            "输出格式（markdown，每类给关键数字 + 一句话客观解读，不评价买卖）：\n"
            "## 标的\n## 估值（PE/PB/PS/FCF yield/Graham number 等关键数）\n"
            "## 盈利能力（ROE/ROIC/毛利率/趋势）\n## 财务安全（负债率/流动比/利息保障）\n"
            "## 现金流（OCF/FCF/盈利质量）\n## 成长性（3y/5y CAGR）\n"
            "## 技术面（近 1/3/6/12 月涨跌、5 年年化、最大回撤、是否新高/新低、量比）\n"
            "## 行业动态（竞争格局/增速/政策）\n## 宏观（利率/CPI/货币政策）\n"
            "## 市场状态（沪深300 regime）\n## 数据缺失与存疑（哪些没取到/可能过期）\n\n"
            "重要：只陈述事实与数据，不做投资建议；引用具体数字；缺失项明确标注。"
        )
        user = f"标的：{target.get('name','')}（{target.get('code','')}）\n\n原始数据（JSON）：\n{json.dumps(raw, ensure_ascii=False, default=str)}"
        return [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)]

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
        self, agent: dict, round_type: str, round_num: int, target: dict, context_data: str, history: list[DebateRound],
    ) -> list[LLMMessage]:
        """按轮次类型构造单个 agent 的 LLM 消息（分析/质疑/回应）。

        challenge/response 引用**上一轮**（history[round_num-1]）的全部 *其他* agent 发言，
        不是 history[-1]——后者在流式顺序执行时是当前正在建的轮（只含前面 agent 的发言），
        会导致"只回应排在自己前面的 agent"。用 history[round_num-1] 确保看到上一轮所有人。
        """
        system = self._build_system_prompt(agent)
        # 每轮共享的头部：标的 + FactBook digest（修后续轮丢 FactBook 的 bug）
        header = (
            f"标的：{target.get('name', '')}（{target.get('code', '')}）\n\n"
            f"--- FactBook（事实 agent 消化的关键信息，每轮共享，必须引用其中数据）---\n"
            f"{context_data}\n--- FactBook 结束 ---\n"
        )
        if round_type == "analysis":
            user_content = (
                f"{header}\n请基于你的投资理念 + 上述 FactBook，分析该标的（每部分3-5句，"
                "**必须引用 FactBook 具体数据**）：\n1. 投资价值判断\n2. 核心理由（≥3条）"
                "\n3. 主要风险\n4. 建议操作"
            )
        elif round_type == "challenge":
            prev_round = history[round_num - 1] if round_num - 1 < len(history) else history[-1]
            others = [op for op in prev_round.opinions if op.agent_id != agent["id"]]
            others_text = "\n\n".join([f"【{op.agent_name}】: {op.content}" for op in others]) or "（无其他 agent 观点）"
            user_content = (
                f"{header}\n上一轮（{prev_round.round_type}）其他投资者的观点：\n\n{others_text}\n\n"
                "请从你的投资理念出发，**围绕事实**对这些观点提出质疑。引导要求：\n"
                "- 优先指出对方论据与 FactBook 数据的矛盾（如估值/ROE/现金流/K线趋势/行业/宏观对不上）。\n"
                "- 质疑逻辑链条（因果跳跃、以偏概全、忽略周期/风险），引用具体数字支撑。\n"
                "- 少做空泛观点、理念之争、人物/流派驳斥；不评价对方「对错」，只戳事实与逻辑漏洞。\n"
                "- 若对方忽略了 FactBook 中某关键风险（如最大回撤/财报过期/分红不可持续），指出之。"
            )
        else:  # response
            prev_round = history[round_num - 1] if round_num - 1 < len(history) else history[-1]
            challenges = [op for op in prev_round.opinions if op.agent_id != agent["id"]]
            text = "\n\n".join([f"【{op.agent_name}的质疑】: {op.content}" for op in challenges]) or "（无质疑）"
            user_content = (
                f"{header}\n上一轮其他投资者对你的分析提出了以下质疑：\n\n{text}\n\n"
                "请回应这些质疑，用 FactBook 数据论证。"
            )
        return [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user_content)]

    def _summarize_messages(self, agents: list[dict], target: dict, history: list[DebateRound], context_data: str = "") -> list[LLMMessage]:
        """构造总结 agent 的 LLM 消息（含 FactBook + 标的 + 全部辩论）。"""
        all_content = []
        for r in history:
            round_text = f"\n=== {r.round_type} ===\n"
            for op in r.opinions:
                round_text += f"\n【{op.agent_name}】:\n{op.content}\n"
            all_content.append(round_text)
        return [
            LLMMessage(
                role="system",
                content="""你是一位客观中立的投资分析总结专家。请综合辩论内容 + FactBook 事实，输出分析报告：
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
                content=(
                    f"标的：{target.get('name', '')}（{target.get('code', '')}）\n\n"
                    f"--- FactBook 关键信息 ---\n{context_data}\n--- FactBook 结束 ---\n\n"
                    f"辩论内容：\n{''.join(all_content)}"
                ),
            ),
        ]
