"""Strategy code generator from natural language."""

import json
import logging
import re

from app.services.filter.sandbox import FilterSandbox
from app.services.llm.provider import LLMMessage, LLMProvider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个量化交易策略开发者。根据用户的自然语言描述，生成 Python 策略代码。

规则：
1. 必须实现以下函数（按需）：
   - `init_strategy(params=None) -> dict`: 返回策略配置（initial_capital, max_positions 等）
   - `select_stocks(df, context) -> list[str]`: 选股逻辑，返回股票代码列表
   - `generate_signals(stock_data, context) -> list[dict]`: 交易信号，返回 [{"action": "buy"/"sell", "code": "...", "shares": N}]
2. df/stock_data 是 pandas DataFrame，包含: code, date, open, high, low, close, volume, amount
3. context 包含: date, holdings (list), current_position (dict)
4. 只使用 pandas 和 numpy
5. 禁止网络/文件/系统操作
6. 只输出代码，不要解释

示例输入：'均线交叉策略：5日均线上穿20日均线买入，下穿卖出，每次买入100股'
"""


class StrategyCodeGenerator:
    """Generate strategy code from natural language."""

    def __init__(self, llm: LLMProvider):
        self.llm = llm
        self.sandbox = FilterSandbox()

    async def generate(self, nl_description: str) -> str:
        """Generate strategy code, retry up to 3 times."""
        current_desc = nl_description
        for attempt in range(3):
            response = await self.llm.chat([
                LLMMessage(role="system", content=SYSTEM_PROMPT),
                LLMMessage(role="user", content=current_desc),
            ])
            code = self._extract_code(response.content)

            # Basic syntax check
            try:
                compile(code, "<strategy>", "exec")
                logger.info(f"Strategy code generated (attempt {attempt + 1})")
                return code
            except SyntaxError as e:
                logger.warning(f"Strategy code syntax error (attempt {attempt + 1}): {e}")
                current_desc = f"{nl_description}\n\n上次代码有语法错误：{e}，请修正。"

        raise ValueError("Strategy code generation failed after 3 attempts")

    @staticmethod
    def _extract_code(text: str) -> str:
        code_block = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
        if code_block:
            return code_block.group(1).strip()
        return text.strip()
