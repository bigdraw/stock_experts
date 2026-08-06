"""Analysis cache tests (ISSUE-024).

A debate/value-analysis payload easily exceeds 500 chars; it must round-trip
through the dedicated analysis_cache table (Text payload) without truncation or
DataError. Previously it was stuffed into SystemSettings.value (String(500)).
"""

import os
import sys
import tempfile

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base  # noqa: E402
from app.services.analysis_cache import get_cached_analysis, set_cached_analysis  # noqa: E402


async def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory, tmp.name


async def test_large_payload_round_trips():
    """A multi-KB debate payload (>> 500 chars) must store + read back intact."""
    engine, factory, db_path = await _fresh_db()
    try:
        # ~8 KB payload — far beyond String(500). Includes unicode + nested JSON.
        big_text = "辩论结论：" + "PE/ROE/股息率分析；" * 400
        data = {
            "rounds": [{"round_type": "analysis", "opinions": [{"agent_name": "巴菲特", "content": big_text}]}],
            "summary": big_text,
        }
        assert len(repr(data)) > 5000  # sanity: this would overflow String(500)

        async with factory() as db:
            await set_cached_analysis(db, "600519", [1, 9], data, "debate")
            await db.commit()

        async with factory() as db:
            got = await get_cached_analysis(db, "600519", [1, 9], "debate")

        assert got is not None, "cache miss — payload likely truncated/failed to store"
        assert got["summary"] == big_text
        assert got["rounds"][0]["opinions"][0]["agent_name"] == "巴菲特"
        assert got["rounds"][0]["opinions"][0]["content"] == big_text
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass


async def test_cache_key_is_agent_order_independent():
    engine, factory, db_path = await _fresh_db()
    try:
        async with factory() as db:
            await set_cached_analysis(db, "000001", [9, 1], {"x": 1}, "value_analysis")
            await db.commit()
        async with factory() as db:
            # Same agents, different order -> same key -> hit.
            got = await get_cached_analysis(db, "000001", [1, 9], "value_analysis")
        assert got == {"x": 1}
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass


async def test_different_stock_is_miss():
    engine, factory, db_path = await _fresh_db()
    try:
        async with factory() as db:
            await set_cached_analysis(db, "600519", [1, 9], {"x": 1}, "debate")
            await db.commit()
        async with factory() as db:
            got = await get_cached_analysis(db, "000001", [1, 9], "debate")
        assert got is None
    finally:
        await engine.dispose()
        try:
            os.unlink(db_path)
        except OSError:
            pass
