"""NL → Filter code generator using LLM."""

import logging
import re

from app.services.filter.sandbox import FilterSandbox
from app.services.llm.provider import LLMMessage, LLMProvider
from app.utils.exceptions import SandboxValidationError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个 Python 数据筛选专家。根据用户的自然语言描述，生成股票筛选函数。

规则：
1. 函数签名必须是 `def filter_stocks(df: pd.DataFrame, params: dict = None) -> pd.DataFrame`
2. df 包含以下列：

基础：code, name, market_cap, pe_ratio, pb_ratio, roe, is_profitable
行情：close, volume, turnover_rate
财务：revenue, net_profit, eps, bps, revenue_growth, net_profit_growth, gross_margin, net_margin, debt_ratio
精筛：ocf, fcf, roic, current_ratio, interest_coverage, earnings_quality, cagr_3y_revenue, cagr_3y_net_profit, dividend_yield, ps_ratio

3. 只使用 pandas 和 numpy 操作
4. 禁止任何网络/文件/系统操作
5. 如果条件涉及可配置的阈值，使用 params 字典，并提供合理的默认值
6. 返回筛选后的 DataFrame，必须包含 code 和 name 列
7. 只输出 Python 代码，不要解释，不要用 markdown 代码块包裹

投资概念→数据映射（帮助理解用户的自然语言描述）：
- 现金流生意 / 自由现金流为正 → ocf > 0 & fcf > 0 & earnings_quality > 0.8
- 安全边际 / 低估 → pe_ratio < 20 & pb_ratio < 3（或 Graham: eps>0 & bps>0 → np.sqrt(22.5*eps*bps) vs close，折价 30% 即 close < 0.7 * sqrt(22.5*eps*bps)）
- 成长性 / 可算清未来 → cagr_3y_revenue > 0.1 & cagr_3y_net_profit > 0.1 & revenue_growth > 0.1
- 财务安全 / 偿债能力强 → debt_ratio < 50 & current_ratio > 1.5 & interest_coverage > 5
- 盈利质量 / 真金白银 → earnings_quality > 1.0 & roic > 0.1 & roe > 0.1
- 高股息 / 分红稳定 → dividend_yield > 0.03
- 低估 / 便宜 → ps_ratio < 5 & pe_ratio < 15
- 周期韧性 / 抗周期 → debt_ratio < 40 & earnings_quality > 0.8 & current_ratio > 2
- 反脆弱 / 财务韧性 → current_ratio > 2 & interest_coverage > 8 & fcf > 0
- 结构性需求 → gross_margin > 0.3 & revenue_growth > 0.15（高毛利 + 高增长 = 需求旺）
- 管理层诚实 → earnings_quality > 1.0 & ocf > net_profit（现金 > 利润 = 诚实）
- 6维硬指标全过 → roe > 0.1 & pe_ratio < 25 & debt_ratio < 50 & ocf > 0 & fcf > 0 & cagr_3y_revenue > 0.05

示例输入：'现金流生意 + ROE大于15% + 安全边际 30%以上'
示例输出：
import numpy as np

def filter_stocks(df: pd.DataFrame, params: dict = None) -> pd.DataFrame:
    params = params or {}
    min_roe = params.get('min_roe', 0.15)
    min_earnings_quality = params.get('min_eq', 0.8)
    result = df[
        (df['ocf'] > 0) &
        (df['fcf'] > 0) &
        (df['earnings_quality'] > min_earnings_quality) &
        (df['roe'] > min_roe) &
        (df['pe_ratio'] < 20) &
        (df['pb_ratio'] < 3)
    ]
    return result[['code', 'name', 'roe', 'pe_ratio', 'ocf', 'fcf', 'earnings_quality']]
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
            response = await self.llm.chat(
                [
                    LLMMessage(role="system", content=SYSTEM_PROMPT),
                    LLMMessage(role="user", content=current_description),
                ]
            )
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
