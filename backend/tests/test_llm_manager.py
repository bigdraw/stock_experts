"""LLM manager reload tests (ISSUE-023).

reload() must swap providers atomically and defer closing retired clients by
RELOAD_CLOSE_GRACE_SECONDS so an admin save doesn't kill the httpx client an
in-flight debate/chat stream is still using.
"""

import asyncio
import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.services.llm import manager as mgr_mod  # noqa: E402
from app.services.llm.manager import LLMManager  # noqa: E402


class _FakeProvider:
    """Minimal provider stub that records when close() runs."""

    def __init__(self, name: str):
        self.name = name
        self.closed = False
        self.close_calls = 0

    async def close(self):
        self.closed = True
        self.close_calls += 1


async def test_reload_defers_close_of_retired_client():
    mgr = LLMManager()
    old = _FakeProvider("old")
    mgr.register("old", old, is_default=True)
    assert mgr.get() is old

    # Shrink the grace so the test doesn't wait a full minute.
    mgr_mod.RELOAD_CLOSE_GRACE_SECONDS = 0.05
    try:
        # No config.yaml + db=None -> reload produces an empty provider map,
        # retiring `old` and scheduling its delayed close.
        await mgr.reload(db=None)
    finally:
        mgr_mod.RELOAD_CLOSE_GRACE_SECONDS = 60.0

    # Immediately after reload: old client NOT closed (in-flight stream safe),
    # and it's no longer the live provider (live map is empty).
    assert old.closed is False, "retired client closed immediately — would break in-flight stream"
    assert mgr.list_providers() == []

    # After the grace, the retired client is closed.
    await asyncio.sleep(0.2)
    assert old.closed is True, "retired client never closed after grace"
    assert old not in mgr._retired


async def test_close_all_cancels_pending_and_closes_now():
    mgr = LLMManager()
    p = _FakeProvider("p")
    mgr.register("p", p, is_default=True)

    mgr_mod.RELOAD_CLOSE_GRACE_SECONDS = 10.0  # long; close_all must cancel it
    try:
        await mgr.reload(db=None)  # retires p, schedules close in 10s
    finally:
        mgr_mod.RELOAD_CLOSE_GRACE_SECONDS = 60.0

    assert p.closed is False
    await mgr.close_all()
    assert p.closed is True  # close_all force-closed the retired client
    assert mgr._close_tasks == set()


async def test_concurrent_reloads_serialized():
    """Two reloads at once must not raise and must serialize via the lock."""
    mgr = LLMManager()
    mgr.register("a", _FakeProvider("a"), is_default=True)
    mgr_mod.RELOAD_CLOSE_GRACE_SECONDS = 0.01
    try:
        await asyncio.gather(mgr.reload(db=None), mgr.reload(db=None), mgr.reload(db=None))
    finally:
        mgr_mod.RELOAD_CLOSE_GRACE_SECONDS = 60.0
    await asyncio.sleep(0.1)
