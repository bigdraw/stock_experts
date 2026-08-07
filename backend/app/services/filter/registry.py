"""Filter script registry (tool library)."""

import logging
from difflib import SequenceMatcher

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filter import FilterScript
from app.models.stock import FinancialReport, Stock
from app.services.filter.generator import FilterCodeGenerator
from app.services.filter.sandbox import FilterSandbox
from app.services.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


class FilterRegistry:
    """Filter script tool library: save, find, execute."""

    def __init__(self, db: AsyncSession, llm: LLMProvider | None = None):
        self.db = db
        self.generator = FilterCodeGenerator(llm) if llm else None
        self.sandbox = FilterSandbox()

    async def generate_and_save(self, name: str, nl_description: str) -> FilterScript:
        """Generate filter code from NL and save to tool library."""
        if not self.generator:
            raise ValueError("LLM provider not configured. Cannot generate filter scripts.")
        code = await self.generator.generate(nl_description)

        # Try a dry-run validation with empty DataFrame
        test_df = pd.DataFrame(
            columns=[
                "code",
                "name",
                "market_cap",
                "pe_ratio",
                "pb_ratio",
                "roe",
                "is_profitable",
                "close",
                "volume",
                "turnover_rate",
            ]
        )
        try:
            self.sandbox.execute(code, test_df, {})
        except Exception as e:
            logger.warning(f"Dry-run validation warning: {e}")

        script = FilterScript(
            name=name,
            nl_description=nl_description,
            code=code,
            is_verified=True,
        )
        self.db.add(script)
        await self.db.flush()
        await self.db.refresh(script)
        logger.info(f"Filter script saved: {script.id} - {name}")
        return script

    async def find_similar(
        self, nl_description: str, threshold: float = 0.7
    ) -> FilterScript | None:
        """Find similar existing script by NL description (text similarity)."""
        result = await self.db.execute(select(FilterScript).where(FilterScript.is_verified))
        scripts = result.scalars().all()

        best_match = None
        best_score = 0.0
        for script in scripts:
            score = SequenceMatcher(
                None, nl_description.lower(), script.nl_description.lower()
            ).ratio()
            if score > best_score and score >= threshold:
                best_score = score
                best_match = script

        if best_match:
            logger.info(f"Found similar script: {best_match.id} (score={best_score:.2f})")
        return best_match

    async def execute(self, script_id: int, params: dict | None = None) -> pd.DataFrame:
        """Execute a saved filter script against current stock data."""
        script = await self.db.get(FilterScript, script_id)
        if not script:
            raise ValueError(f"Filter script {script_id} not found")

        # Increment usage count
        script.usage_count += 1
        await self.db.flush()

        # Load stock data
        df = await self._load_stock_data()
        return self.sandbox.execute(script.code, df, params)

    async def list_all(self) -> list[FilterScript]:
        """List all verified filter scripts."""
        result = await self.db.execute(
            select(FilterScript)
            .where(FilterScript.is_verified)
            .order_by(FilterScript.usage_count.desc())
        )
        return list(result.scalars().all())

    async def _load_stock_data(self) -> pd.DataFrame:
        """Load all active stocks with their latest indicators (incl. screening columns)."""
        stocks_result = await self.db.execute(select(Stock).where(Stock.is_active))
        stocks = stocks_result.scalars().all()

        columns = [
            "code", "name", "market_cap", "pe_ratio", "pb_ratio", "roe", "is_profitable",
            "close", "volume", "turnover_rate",
            "revenue", "net_profit", "eps", "bps", "revenue_growth", "net_profit_growth",
            "gross_margin", "net_margin", "debt_ratio",
            "ocf", "fcf", "roic", "current_ratio", "interest_coverage",
            "earnings_quality", "cagr_3y_revenue", "cagr_3y_net_profit",
            "dividend_yield", "ps_ratio",
        ]

        if not stocks:
            return pd.DataFrame(columns=columns)

        data = []
        for stock in stocks:
            report_result = await self.db.execute(
                select(FinancialReport)
                .where(FinancialReport.stock_code == stock.code, FinancialReport.report_type == "Latest")
                .order_by(FinancialReport.report_date.desc())
                .limit(1)
            )
            report = report_result.scalar_one_or_none()
            row = {
                "code": stock.code,
                "name": stock.name,
                "market_cap": report.market_cap if report else None,
                "pe_ratio": report.pe_ratio if report else None,
                "pb_ratio": report.pb_ratio if report else None,
                "roe": report.roe if report else None,
                "is_profitable": report.is_profitable if report else None,
                # 行情（FinancialReport Latest 快照已含 Sina 20 字段）
                "close": report.price if report else None,
                "volume": report.volume if report else None,
                "turnover_rate": report.turnoverratio if report else None,
                # 财务报表（已有列，之前没查）
                "revenue": report.revenue if report else None,
                "net_profit": report.net_profit if report else None,
                "eps": report.eps if report else None,
                "bps": report.bps if report else None,
                "revenue_growth": report.revenue_growth if report else None,
                "net_profit_growth": report.net_profit_growth if report else None,
                "gross_margin": report.gross_margin if report else None,
                "net_margin": report.net_margin if report else None,
                "debt_ratio": report.debt_ratio if report else None,
                # 精筛扩展（value_analysis upsert 到 Latest 行）
                "ocf": report.ocf if report else None,
                "fcf": report.fcf if report else None,
                "roic": report.roic if report else None,
                "current_ratio": report.current_ratio if report else None,
                "interest_coverage": report.interest_coverage if report else None,
                "earnings_quality": report.earnings_quality if report else None,
                "cagr_3y_revenue": report.cagr_3y_revenue if report else None,
                "cagr_3y_net_profit": report.cagr_3y_net_profit if report else None,
                "dividend_yield": report.dividend_yield if report else None,
                "ps_ratio": report.ps_ratio if report else None,
            }
            data.append(row)

        return pd.DataFrame(data)
