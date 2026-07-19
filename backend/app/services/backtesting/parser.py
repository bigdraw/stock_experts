"""自然语言 → 策略解析器（移植自 maverick-mcp，MIT License Copyright (c) 2024）。

源文件：`maverick_mcp/backtesting/strategies/parser.py`。
适配点：原版 LLM 路径用 `langchain_anthropic.ChatAnthropic`（本平台无）；
本平台 `parse_simple`（纯 Python 规则解析，核心价值）逐字保留，`parse_with_llm`
改为可选——接本平台 `llm_manager`，无配置则回退 `parse_simple`。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.backtesting.strategies import STRATEGY_TEMPLATES

logger = logging.getLogger(__name__)


class StrategyParser:
    """NL → 策略类型 + 参数解析器。"""

    def __init__(self, llm=None) -> None:
        """Args:
            llm: 可选 LLM provider（本平台 `llm_manager.get()` 返回的对象，需有
                 `complete(prompt) -> str` 或兼容 OpenAI chat completion 接口）。
                 为 None 时 `parse_with_llm` 回退 `parse_simple`。
        """
        self.llm = llm
        self.templates = STRATEGY_TEMPLATES

    def parse_simple(self, description: str) -> dict[str, Any]:
        """纯规则解析，不调 LLM。"""
        d = description.lower()
        if "sma" in d or "moving average cross" in d:
            return self._parse_sma_strategy(description)
        if "rsi" in d:
            return self._parse_rsi_strategy(description)
        if "macd" in d:
            return self._parse_macd_strategy(description)
        if "bollinger" in d or "band" in d:
            return self._parse_bollinger_strategy(description)
        if "momentum" in d:
            return self._parse_momentum_strategy(description)
        if "ema" in d or "exponential" in d:
            return self._parse_ema_strategy(description)
        if "breakout" in d or "channel" in d:
            return self._parse_breakout_strategy(description)
        if "mean reversion" in d or "reversion" in d:
            return self._parse_mean_reversion_strategy(description)
        return {
            "strategy_type": "momentum",
            "parameters": dict(self.templates["momentum"]["parameters"]),
        }

    def _parse_sma_strategy(self, description: str) -> dict[str, Any]:
        numbers = re.findall(r"\d+", description)
        params = dict(self.templates["sma_cross"]["parameters"])
        if len(numbers) >= 2:
            params["fast_period"] = int(numbers[0])
            params["slow_period"] = int(numbers[1])
        elif len(numbers) == 1:
            params["fast_period"] = int(numbers[0])
        return {"strategy_type": "sma_cross", "parameters": params}

    def _parse_rsi_strategy(self, description: str) -> dict[str, Any]:
        numbers = re.findall(r"\d+", description)
        params = dict(self.templates["rsi"]["parameters"])
        for num in numbers:
            v = int(num)
            if 5 <= v <= 30 and "period" not in params:
                params["period"] = v
            elif 15 <= v <= 35:
                params["oversold"] = v
            elif 65 <= v <= 85:
                params["overbought"] = v
        return {"strategy_type": "rsi", "parameters": params}

    def _parse_macd_strategy(self, description: str) -> dict[str, Any]:
        numbers = re.findall(r"\d+", description)
        params = dict(self.templates["macd"]["parameters"])
        if len(numbers) >= 3:
            params["fast_period"] = int(numbers[0])
            params["slow_period"] = int(numbers[1])
            params["signal_period"] = int(numbers[2])
        return {"strategy_type": "macd", "parameters": params}

    def _parse_bollinger_strategy(self, description: str) -> dict[str, Any]:
        numbers = re.findall(r"\d+\.?\d*", description)
        params = dict(self.templates["bollinger"]["parameters"])
        for num in numbers:
            v = float(num)
            if v == int(v) and 5 <= v <= 50:
                params["period"] = int(v)
            elif 1.0 <= v <= 4.0:
                params["std_dev"] = v
        return {"strategy_type": "bollinger", "parameters": params}

    def _parse_momentum_strategy(self, description: str) -> dict[str, Any]:
        numbers = re.findall(r"\d+\.?\d*", description)
        params = dict(self.templates["momentum"]["parameters"])
        for num in numbers:
            v = float(num)
            if v == int(v) and 5 <= v <= 100:
                params["lookback"] = int(v)
            elif 0.001 <= v <= 0.5:
                params["threshold"] = v
        return {"strategy_type": "momentum", "parameters": params}

    def _parse_ema_strategy(self, description: str) -> dict[str, Any]:
        numbers = re.findall(r"\d+", description)
        params = dict(self.templates["ema_cross"]["parameters"])
        if len(numbers) >= 2:
            params["fast_period"] = int(numbers[0])
            params["slow_period"] = int(numbers[1])
        elif len(numbers) == 1:
            params["fast_period"] = int(numbers[0])
        return {"strategy_type": "ema_cross", "parameters": params}

    def _parse_breakout_strategy(self, description: str) -> dict[str, Any]:
        numbers = re.findall(r"\d+", description)
        params = dict(self.templates["breakout"]["parameters"])
        if len(numbers) >= 2:
            params["lookback"] = int(numbers[0])
            params["exit_lookback"] = int(numbers[1])
        elif len(numbers) == 1:
            params["lookback"] = int(numbers[0])
        return {"strategy_type": "breakout", "parameters": params}

    def _parse_mean_reversion_strategy(self, description: str) -> dict[str, Any]:
        numbers = re.findall(r"\d+\.?\d*", description)
        params = dict(self.templates["mean_reversion"]["parameters"])
        for num in numbers:
            v = float(num)
            if v == int(v) and 5 <= v <= 100:
                params["ma_period"] = int(v)
            elif 0.001 <= v <= 0.2:
                low = description.lower()
                if "entry" in low:
                    params["entry_threshold"] = v
                elif "exit" in low:
                    params["exit_threshold"] = v
        return {"strategy_type": "mean_reversion", "parameters": params}

    async def parse_with_llm(self, description: str) -> dict[str, Any]:
        """复杂描述用 LLM 解析；无 LLM 或解析失败则回退 parse_simple。"""
        if not self.llm:
            return self.parse_simple(description)

        available = "\n".join(
            f"- {k}: {v['description']}" for k, v in self.templates.items()
        )
        prompt = (
            "Convert this trading strategy description into JSON.\n"
            f"Description: {description}\n\n"
            f"Available strategy types:\n{available}\n\n"
            'Return ONLY a JSON object: {"strategy_type": <one of available>, '
            '"parameters": {...}, "entry_logic": "...", "exit_logic": "..."}'
        )
        try:
            text = await self.llm.complete(prompt)  # type: ignore[attr-defined]
            # 容错：取首个 JSON 对象
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                result = json.loads(text[start : end + 1])
                if "strategy_type" in result:
                    return result
        except Exception as e:
            logger.warning(f"LLM strategy parse failed, falling back: {e}")
        return self.parse_simple(description)

    def validate_strategy(self, config: dict[str, Any]) -> bool:
        """校验配置：strategy_type 合法且含全部必需参数。"""
        st = config.get("strategy_type")
        if st not in self.templates:
            return False
        required = set(self.templates[st]["parameters"].keys())
        provided = set(config.get("parameters", {}).keys())
        return required.issubset(provided)
