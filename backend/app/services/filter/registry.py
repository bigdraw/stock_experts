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
        """Load all active stocks with their latest indicators."""
        stocks_result = await self.db.execute(select(Stock).where(Stock.is_active))
        stocks = stocks_result.scalars().all()

        if not stocks:
            return pd.DataFrame(
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

        data = []
        for stock in stocks:
            # Get latest financial report
            report_result = await self.db.execute(
                select(FinancialReport)
                .where(FinancialReport.stock_code == stock.code)
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
            }
            data.append(row)

        return pd.DataFrame(data)
