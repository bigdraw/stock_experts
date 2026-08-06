"""Data value-analysis correctness tests (ISSUE-028).

- ROIC NOPAT must use EBIT = op_profit + interest_exp (not 营业利润, which
  already deducts interest → double deduction). ISSUES-028 H11-2.
- PS must tag ps_basis ('ttm' | 'annualized') instead of silently degrading to
  Q1×4 annualization that misleads valuation. ISSUE-028 H11-1.
"""

import os
import sys
import tempfile
from datetime import date as _date

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base  # noqa: E402
from app.models.stock import FinancialReport, Stock  # noqa: E402
from app.services.data import value_analysis as va  # noqa: E402


class _FakeProvider:
    """Returns canned three-statements + dividends, no network."""

    def __init__(self, statements, dividends=None):
        self._stmts = statements
        self._divs = dividends or []

    async def get_financial_statements(self, code):
        return list(self._stmts)

    async def get_dividends(self, code):
        return list(self._divs)


async def _fresh():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory, tmp.name


async def test_roic_uses_ebit_not_operating_profit():
    """ROIC NOPAT = EBIT*(1-t) = (op_profit+interest_exp)*(1-t), not op_profit*(1-t)."""
    engine, factory, db_path = await _fresh()
    try:
        async with factory() as db:
            db.add(Stock(code="600519", name="贵州茅台", market="SH", is_active=True))
            # Latest snapshot for valuation (not used by ROIC but needed by analyze).
            db.add(FinancialReport(
                stock_code="600519", report_type="Latest", report_date=_date(2024, 3, 31),
                price=10.0, mktcap=10000.0, pb=8.0,
            ))
            await db.commit()

        # One annual period: equity=1000, total_liab=1400, current_liab=200,
        # op_profit=100, interest_exp=20 → EBIT=120, NOPAT=120*0.75=90,
        # invested=equity+(total_liab-current_liab)=1000+1200=2200 → ROIC=90/2200≈0.0409.
        # Buggy old formula: NOPAT=75 → ROIC=75/2200≈0.0341.
        stmts = [{
            "report_date": "2023-12-31", "total_assets": 2400, "total_liab": 1400,
            "current_assets": 800, "current_liab": 200, "equity": 1000,
            "op_profit": 100, "interest_exp": 20, "net_profit": 70,
            "ocf": 50, "capex": 10, "revenue": 500,
        }]
        prov = _FakeProvider(stmts)
        async with factory() as db:
            result = await va.analyze(db, "600519", provider=prov)

        trend = result.get("trend", [])
        assert trend, "trend periods missing"
        roic = trend[-1].get("roic")
        assert roic is not None
        assert abs(roic - 90 / 2200) < 1e-6, f"ROIC {roic} should be EBIT-based ≈0.0409, not op_profit-based 0.0341"
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass


async def test_ps_tags_basis_when_ttm_unavailable():
    """When TTM revenue can't be computed, PS must mark ps_basis (not silently
    annualize Q1×4 as if it were TTM)."""
    engine, factory, db_path = await _fresh()
    try:
        async with factory() as db:
            db.add(Stock(code="000757", name="浩物股份", market="SZ", is_active=True))
            db.add(FinancialReport(
                stock_code="000757", report_type="Latest", report_date=_date(2024, 3, 31),
                price=10.0, mktcap=10000.0, pb=3.0,
            ))
            await db.commit()

        # Only a Q1 statement, no annuals → _ttm('revenue') returns None.
        stmts = [{
            "report_date": "2024-03-31", "revenue": 100, "total_assets": 1000,
            "total_liab": 500, "current_liab": 200, "equity": 500,
            "op_profit": 30, "net_profit": 20, "ocf": 15, "capex": 5,
        }]
        prov = _FakeProvider(stmts)
        async with factory() as db:
            result = await va.analyze(db, "000757", provider=prov)

        val = result.get("valuation", {})
        assert "ps_basis" in val, "ps_basis must be present so silent degradation is flagged"
        assert val["ps_basis"] == "annualized", f"expected 'annualized' basis, got {val.get('ps_basis')}"
        assert val.get("ps") is not None  # annualized value still computed, just flagged
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass


async def test_ps_ttm_when_annuals_available():
    """With annuals, PS uses TTM revenue and tags ps_basis='ttm'."""
    engine, factory, db_path = await _fresh()
    try:
        async with factory() as db:
            db.add(Stock(code="600000", name="浦发银行", market="SH", is_active=True))
            db.add(FinancialReport(
                stock_code="600000", report_type="Latest", report_date=_date(2024, 3, 31),
                price=10.0, mktcap=10000.0, pb=0.5,
            ))
            await db.commit()

        # annual 2023 (400) + same-q-prev 2023-03-31 (80) + latest 2024-03-31 (100)
        # → ttm = 400 - 80 + 100 = 420.
        stmts = [
            {"report_date": "2023-03-31", "revenue": 80, "total_assets": 900, "total_liab": 500,
             "current_liab": 200, "equity": 400, "op_profit": 20, "net_profit": 15, "ocf": 10, "capex": 4},
            {"report_date": "2023-12-31", "revenue": 400, "total_assets": 1000, "total_liab": 500,
             "current_liab": 200, "equity": 500, "op_profit": 30, "net_profit": 20, "ocf": 15, "capex": 5},
            {"report_date": "2024-03-31", "revenue": 100, "total_assets": 1100, "total_liab": 600,
             "current_liab": 250, "equity": 500, "op_profit": 30, "net_profit": 20, "ocf": 15, "capex": 5},
        ]
        prov = _FakeProvider(stmts)
        async with factory() as db:
            result = await va.analyze(db, "600000", provider=prov)

        val = result.get("valuation", {})
        assert val.get("ps_basis") == "ttm", f"expected ttm basis, got {val.get('ps_basis')}"
        # market_cap = 10000 * 10000 = 1e8; ttm_rev=420 → ps = 1e8/420
        assert abs(val["ps"] - 1e8 / 420) < 1e-3
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass


async def test_dividend_yield_ttm_anchored_to_last_ex_date():
    """ISSUE: 600690 dividend yield must count BOTH 2025 dividends (1.2342), not
    just the one within 365 days of today. TTM anchored to latest ex_date, not today."""
    engine, factory, db_path = await _fresh()
    try:
        async with factory() as db:
            db.add(Stock(code="600690", name="海尔", market="SH", is_active=True))
            db.add(FinancialReport(stock_code="600690", report_type="Latest",
                                   report_date=_date(2026, 8, 6), price=22.34, mktcap=10000.0, pb=2.0))
            await db.commit()
        divs = [
            {"ex_date": "2025-05-15", "dividend_per_share": 0.965},
            {"ex_date": "2025-11-20", "dividend_per_share": 0.2692},
            {"ex_date": "2024-06-01", "dividend_per_share": 0.5},  # outside [2024-11-20, 2025-11-20]
        ]
        # one statement so periods is non-empty (analyze early-returns if no periods)
        stmts = [{"report_date": "2025-12-31", "net_profit": 100, "revenue": 1000,
                  "total_assets": 5000, "total_liab": 2000, "current_liab": 800, "equity": 3000}]
        prov = _FakeProvider(stmts, divs)
        async with factory() as db:
            result = await va.analyze(db, "600690", provider=prov)
        val = result.get("valuation", {})
        assert val.get("dividend_yield_basis") == "ttm_trailing_ex_date"
        # ttm_dps = 0.965 + 0.2692 = 1.2342; yield = 1.2342/22.34 ≈ 0.0553
        assert abs(val["dividend_yield"] - 1.2342 / 22.34) < 1e-6, val.get("dividend_yield")
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass


async def test_ttm_returns_none_when_same_q_prev_missing():
    """ISSUE: _ttm must return None (not stale last_annual) when same_q_prev
    missing → PE/graham None instead of wrong value."""
    engine, factory, db_path = await _fresh()
    try:
        async with factory() as db:
            db.add(Stock(code="300244", name="迪安诊断", market="SZ", is_active=True))
            db.add(FinancialReport(stock_code="300244", report_type="Latest",
                                   report_date=_date(2024, 3, 31), price=10.0, mktcap=10000.0, pb=10.44))
            # cached periods with eps/bps: 2023 annual + 2024 Q1, NO 2023Q1 → _ttm can't compute
            db.add(FinancialReport(stock_code="300244", report_type="Annual",
                                   report_date=_date(2023, 12, 31), eps=0.21, bps=10.0))
            db.add(FinancialReport(stock_code="300244", report_type="Q1",
                                   report_date=_date(2024, 3, 31), eps=0.1053, bps=10.44))
            await db.commit()
        prov = _FakeProvider([], [])  # no statements, no dividends
        async with factory() as db:
            result = await va.analyze(db, "300244", provider=prov)
        val = result.get("valuation", {})
        assert val.get("pe") is None, f"pe should be None (no TTM), got {val.get('pe')}"
        assert val.get("graham_number") is None, f"graham should be None, got {val.get('graham_number')}"
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass


async def test_net_margin_computed_from_net_profit_over_revenue():
    """ISSUE: net_margin must be net_profit/revenue (internally consistent), not
    the cached ths 销售净利率 (口径 mismatch)."""
    engine, factory, db_path = await _fresh()
    try:
        async with factory() as db:
            db.add(Stock(code="300244b", name="迪安", market="SZ", is_active=True))
            # cached row with a DIFFERENT net_margin (0.0464) to prove computed wins
            db.add(FinancialReport(stock_code="300244b", report_type="Q1",
                                   report_date=_date(2024, 3, 31), net_margin=0.0464,
                                   net_profit=64.37, revenue=2246.96))
            await db.commit()
        # provider statement with net_profit=70, revenue=500 → 0.14 (not cached 0.0464)
        stmts = [{"report_date": "2024-03-31", "net_profit": 70, "revenue": 500,
                  "total_assets": 1000, "total_liab": 500, "current_liab": 200, "equity": 500}]
        prov = _FakeProvider(stmts, [])
        async with factory() as db:
            result = await va.analyze(db, "300244b", provider=prov)
        latest = result.get("latest", {})
        assert abs(latest["net_margin"] - 70 / 500) < 1e-6, f"net_margin {latest.get('net_margin')} should be 0.14"
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass


async def test_net_profit_growth_none_on_negative_base():
    """ISSUE: net_profit_growth None when same-q-prev base ≤ 0 (meaningless YoY)."""
    engine, factory, db_path = await _fresh()
    try:
        async with factory() as db:
            db.add(Stock(code="300244c", name="迪安c", market="SZ", is_active=True))
            await db.commit()
        # 2024Q1 net_profit=-21 (negative base) + 2025Q1 net_profit=50 → growth None
        stmts = [
            {"report_date": "2024-03-31", "net_profit": -21, "revenue": 100,
             "total_assets": 1000, "total_liab": 500, "current_liab": 200, "equity": 500},
            {"report_date": "2025-03-31", "net_profit": 50, "revenue": 120,
             "total_assets": 1100, "total_liab": 600, "current_liab": 250, "equity": 500},
        ]
        prov = _FakeProvider(stmts, [])
        async with factory() as db:
            result = await va.analyze(db, "300244c", provider=prov)
        latest = result.get("latest", {})
        assert latest["net_profit_growth"] is None, f"negative-base growth should be None, got {latest.get('net_profit_growth')}"

        # Positive base variant: 2024Q1=40, 2025Q1=50 → (50-40)/40 = 0.25
        engine2, factory2, db_path2 = await _fresh()
        try:
            async with factory2() as db:
                db.add(Stock(code="300244d", name="迪安d", market="SZ", is_active=True))
                await db.commit()
            stmts2 = [
                {"report_date": "2024-03-31", "net_profit": 40, "revenue": 100,
                 "total_assets": 1000, "total_liab": 500, "current_liab": 200, "equity": 500},
                {"report_date": "2025-03-31", "net_profit": 50, "revenue": 120,
                 "total_assets": 1100, "total_liab": 600, "current_liab": 250, "equity": 500},
            ]
            prov2 = _FakeProvider(stmts2, [])
            async with factory2() as db:
                result2 = await va.analyze(db, "300244d", provider=prov2)
            assert abs(result2["latest"]["net_profit_growth"] - 0.25) < 1e-6
        finally:
            await engine2.dispose()
            try:
                os.unlink(db_path2)
            except OSError:
                pass
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass


async def test_interest_coverage_none_on_negative_interest_exp():
    """ISSUE: interest_coverage None when interest_exp ≤ 0 (net interest income →
    coverage meaningless)."""
    engine, factory, db_path = await _fresh()
    try:
        async with factory() as db:
            db.add(Stock(code="600066", name="宇通", market="SH", is_active=True))
            await db.commit()
        # op_profit=100, interest_exp=-20 (net interest income) → None
        stmts = [{"report_date": "2025-12-31", "op_profit": 100, "interest_exp": -20,
                  "net_profit": 80, "revenue": 500, "total_assets": 1000, "total_liab": 500,
                  "current_liab": 200, "equity": 500}]
        prov = _FakeProvider(stmts, [])
        async with factory() as db:
            result = await va.analyze(db, "600066", provider=prov)
        latest = result.get("latest", {})
        assert latest["interest_coverage"] is None, f"negative interest_exp → None, got {latest.get('interest_coverage')}"

        # Positive interest_exp=20 → 100/20 = 5
        engine2, factory2, db_path2 = await _fresh()
        try:
            async with factory2() as db:
                db.add(Stock(code="600066b", name="宇通b", market="SH", is_active=True))
                await db.commit()
            stmts2 = [{"report_date": "2025-12-31", "op_profit": 100, "interest_exp": 20,
                       "net_profit": 80, "revenue": 500, "total_assets": 1000, "total_liab": 500,
                       "current_liab": 200, "equity": 500}]
            prov2 = _FakeProvider(stmts2, [])
            async with factory2() as db:
                result2 = await va.analyze(db, "600066b", provider=prov2)
            assert abs(result2["latest"]["interest_coverage"] - 5.0) < 1e-6
        finally:
            await engine2.dispose()
            try:
                os.unlink(db_path2)
            except OSError:
                pass
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass
