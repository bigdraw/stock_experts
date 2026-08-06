"""FilterSandbox hardening tests: legitimate filter works, introspection
escapes are blocked. Run via ``python -m tests.test_sandbox`` or pytest."""

import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

import pandas as pd  # noqa: E402

from app.services.filter.sandbox import (  # noqa: E402
    FilterSandbox,
    SandboxError,
    validate_restricted,
)


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "code": ["600000", "600519", "000001"],
        "price": [10.0, 1800.0, 16.0],
        "pe_ratio": [8.0, 30.0, 6.0],
    })


def main() -> int:
    sb = FilterSandbox()
    failures: list[str] = []

    def check(label, cond):
        print(f"  {'PASS' if cond else 'FAIL'}: {label}")
        if not cond:
            failures.append(label)

    # 1. Legitimate filter works
    good = """
def filter_stocks(df, params):
    threshold = params.get('pe_max', 20)
    return df[df['pe_ratio'] < threshold].copy()
"""
    res = sb.execute(good, _sample_df(), {"pe_max": 20})
    check("legit filter runs + returns correct rows", len(res) == 2 and set(res['code']) == {"600000", "000001"})

    # 2. Forbidden import blocked at validate
    ok, msg = sb.validate("import os\ndef filter_stocks(df,p):\n  return df\n")
    check("import os blocked", not ok and "os" in msg)

    # 3. exec/eval forbidden
    ok, msg = sb.validate("def filter_stocks(df,p):\n  exec('x')\n  return df\n")
    check("exec blocked", not ok and "exec" in msg)

    # 4. __dunder__ attribute access blocked (introspection escape)
    ok, msg = sb.validate("def filter_stocks(df,p):\n  x = ().__class__\n  return df\n")
    check("().__class__ blocked at validate", not ok and "class" in msg.lower())

    # 5. compile_restricted blocks escape that slips past AST (subscript-based)
    #    e.g. obj.__class__ via getattr-like — verify exec path raises.
    sneaky = "def filter_stocks(df,p):\n  x = getattr(df, '__class__')\n  return df\n"
    try:
        sb.execute(sneaky, _sample_df())
        # safer_getattr should have blocked it; if it ran, that's a FAIL.
        check("getattr(df,'__class__') blocked at runtime", False)
    except (SandboxError, Exception):
        check("getattr(df,'__class__') blocked at runtime", True)

    # 6. Forbidden attribute on dunder blocked
    ok, msg = sb.validate("def filter_stocks(df,p):\n  x = df.__class__\n  return df\n")
    check("df.__class__ blocked", not ok)

    # 7. pandas IO blocked (ISSUE-018): pd.read_csv / df.to_pickle / np.load
    ok, msg = sb.validate("def filter_stocks(df,p):\n  return pd.read_csv('/etc/passwd')\n")
    check("pd.read_csv blocked", not ok and "read_csv" in msg)
    ok, msg = sb.validate("def filter_stocks(df,p):\n  df.to_pickle('/tmp/x')\n  return df\n")
    check("df.to_pickle blocked", not ok and "to_pickle" in msg)
    ok, msg = sb.validate("def filter_stocks(df,p):\n  np.load('/tmp/x', allow_pickle=True)\n  return df\n")
    check("np.load blocked", not ok and "load" in msg)

    # 8. alert check() via run_function works + dunder escape blocked (ISSUE-018)
    good_alert = "def check(data):\n  return data.get('close', 0) > data.get('threshold', 10)\n"
    res2 = sb.run_function(good_alert, "check", ({"close": 20, "threshold": 10},))
    check("alert check() returns True when condition met", res2 is True)
    res3 = sb.run_function(good_alert, "check", ({"close": 5, "threshold": 10},))
    check("alert check() returns False otherwise", res3 is False)

    evil_alert = "def check(data):\n  return ().__class__.__bases__[0].__subclasses__()\n"
    try:
        sb.run_function(evil_alert, "check", ({},))
        check("alert dunder escape blocked", False)
    except Exception:
        check("alert dunder escape blocked", True)

    # 9. backtest strategy via exec_namespace: legit symbols extracted; missing
    #    all of init/select/generate is rejected.
    strat = """
def generate_signals(hist, ctx):
    return [{'code': ctx['code'], 'action': 'buy', 'shares': 100}]
"""
    ns = sb.exec_namespace(strat, ("init_strategy", "select_stocks", "generate_signals"), require_all=False)
    check("strategy exec_namespace exposes generate_signals", callable(ns.get("generate_signals")))
    ok, msg = validate_restricted(
        "def unrelated():\n  pass\n", ("init_strategy", "select_stocks", "generate_signals"), require_all=False
    )
    check("strategy with no entry symbol rejected", not ok)

    print(f"\n{'ALL PASSED' if not failures else 'FAILURES: '+str(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())


# pytest entrypoint (asyncio_mode = "auto").
def test_sandbox_hardening():
    assert main() == 0
