"""DecisionLogger tests: never-raises guarantee + real temp-DB round-trip.

Run via ``python -m tests.test_audit`` or pytest."""

import asyncio
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
from app.services import audit  # noqa: E402  (registers DecisionLog with Base.metadata)
from app.services.audit.logger import DecisionLogger  # noqa: E402


async def _never_raises() -> bool:
    """log_decision must not raise even when the session factory is broken."""

    class _BrokenSession:
        async def __aenter__(self_inner):
            raise RuntimeError("simulated DB down")

        async def __aexit__(self_inner, *a):
            return False

    original = audit.logger.async_session_factory
    audit.logger.async_session_factory = lambda: _BrokenSession()  # type: ignore
    try:
        # Must not raise
        await DecisionLogger.log_decision(query_text="x", status="success")
        rows = await DecisionLogger.get_decisions()
        summary = await DecisionLogger.get_cost_summary()
        return rows == [] and "error" in summary
    finally:
        audit.logger.async_session_factory = original


async def _happy_path() -> bool:
    """Write a record to a temp DB and read it back."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = tmp.name
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}", future=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    original = audit.logger.async_session_factory
    audit.logger.async_session_factory = factory  # type: ignore
    try:
        await DecisionLogger.log_decision(
            session_id="s1",
            query_text="test query",
            query_classification="screening",
            models_used=["qwen"],
            tokens_input=100,
            tokens_output=50,
            estimated_cost_usd=0.001,
            duration_ms=250,
            status="success",
        )
        rows = await DecisionLogger.get_decisions(session_id="s1", limit=10)
        summary = await DecisionLogger.get_cost_summary(days=1)
        return (
            len(rows) == 1
            and rows[0]["query_classification"] == "screening"
            and rows[0]["tokens_input"] == 100
            and summary.get("total_requests") == 1
        )
    finally:
        audit.logger.async_session_factory = original
        await engine.dispose()
        try:
            os.unlink(path)
        except OSError:
            pass


async def main() -> int:
    failures: list[str] = []

    def check(label, cond):
        print(f"  {'PASS' if cond else 'FAIL'}: {label}")
        if not cond:
            failures.append(label)

    check("log_decision never raises on broken DB", await _never_raises())
    check("write + read + cost summary round-trip", await _happy_path())

    print(f"\n{'ALL PASSED' if not failures else 'FAILURES: '+str(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))


async def test_audit_logger():
    assert await main() == 0
