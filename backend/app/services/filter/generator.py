"""NL → Filter code generator using LLM."""

import json
import logging
import re

from app.services.filter.sandbox import FilterSandbox
from app.services.llm.provider import LLMMessage, LLMProvider
from app.utils.exceptions import SandboxValidationError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个 Python 数据筛选专家。根据用户的自然语言描述，生成股票筛选函数。

规则：
1. 函数签名必须是 `def filter_stocks(df: pd.DataFrame, params: dict = None) -> pd.DataFrame`
2. df 包含以下列：code, name, market_cap, pe_ratio, pb_ratio, roe, is_profitable, close, volume, turnover_rate
3. 只使用 pandas 和 numpy 操作
4. 禁止任何网络/文件/系统操作
5. 如果条件涉及可配置的阈值，使用 params 字典，并提供合理的默认值
6. 返回筛选后的 DataFrame，必须包含 code 和 name 列
7. 只输出 Python 代码，不要解释，不要用 markdown 代码块包裹

示例输入：'ROE大于15%且市盈率小于20的盈利股票'
示例输出：
def filter_stocks(df: pd.DataFrame, params: dict = None) -> pd.DataFrame:
    params = params or {}
    min_roe = params.get('min_roe', 15)
    max_pe = params.get('max_pe', 20)
    result = df[
        (df['roe'] > min_roe) &
        (df['pe_ratio'] < max_pe) &
        (df['is_profitable'] == True)
    ]
    return result[['code', 'name', 'roe', 'pe_ratio']]
"""


class FilterCodeGenerator:
    """Generate filter code from natural language descriptions."""

    def __init__(self, llm: LLMProvider):
        self.llm = llm
        self.sandbox = FilterSandbox()

    async def generate(self, nl_description: str) -> str:
        """Generate filter code, retry up to 3 times on validation failure."""
        current_description = nl_description

        for attempt in range(3):
            response = await self.llm.chat([
                LLMMessage(role="system", content=SYSTEM_PROMPT),
                LLMMessage(role="user", content=current_description),
            ])
            code = self._extract_code(response.content)

            is_valid, msg = self.sandbox.validate(code)
            if is_valid:
                logger.info(f"Filter code generated successfully (attempt {attempt + 1})")
                return code

            logger.warning(f"Code validation failed (attempt {attempt + 1}): {msg}")
            current_description = (
                f"{nl_description}\n\n"
                f"上次生成的代码有错误：{msg}\n"
                f"上次代码：\n{code}\n\n"
                f"请修正并重新生成。"
            )

        raise SandboxValidationError("Code generation failed after 3 attempts")

    @staticmethod
    def _extract_code(text: str) -> str:
        """Extract Python code from LLM response."""
        # Remove markdown code blocks if present
        code_block = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
        if code_block:
            return code_block.group(1).strip()
        # Otherwise return the text as-is (should be pure code)
        return text.strip()
