"""Security sandbox for executing LLM-generated filter code.

Hardened with RestrictedPython (already declared in pyproject.toml but
previously unused). The original implementation called plain ``exec(code, ...)``
with a hand-rolled filtered ``__builtins__`` while injecting full ``pd``/``np`` —
classic introspection escapes such as
``().__class__.__bases__[0].__subclasses__()`` were completely unblocked.

This version:
  1. Keeps the fast AST-level static pre-check (forbidden imports/builtins,
     required ``filter_stocks`` symbol) for clear error messages.
  2. Compiles via ``RestrictedPython.compile_restricted`` which transforms the
     AST so that dunder attribute access, attribute writes, and item access are
     routed through guarded hooks.
  3. Wires ``_getattr_`` = ``safer_getattr`` (blocks any name starting with ``_``)
     and ``_getitem_``/``_write_`` guards, plus a minimal ``safe_builtins`` set.

Residual risk (documented): ``pd``/``np`` are still injected because filter
scripts operate on the provided DataFrame, so ``pd.read_csv``-style IO remains
reachable. True isolation needs a separate process + seccomp/container; this
hardening raises the bar substantially against introspection-based RCE escapes
but is not a complete OS-level sandbox. Filter execution is also admin-gated
(see api/v1/filters.py) as defence-in-depth.
"""

import ast
import logging
from typing import Any

import numpy as np
import pandas as pd
from RestrictedPython import compile_restricted, safe_builtins
from RestrictedPython.Eval import default_guarded_getitem
from RestrictedPython.Guards import full_write_guard, safer_getattr

logger = logging.getLogger(__name__)

FORBIDDEN_IMPORTS = {
    "os", "sys", "subprocess", "socket", "http", "urllib",
    "requests", "pathlib", "shutil", "io", "builtins",
    "ctypes", "importlib", "pickle", "marshal",
}
FORBIDDEN_BUILTINS = {
    "open", "exec", "eval", "compile", "__import__",
    "input", "breakpoint", "exit", "quit", "globals", "locals", "vars",
}

# Extra builtins allowed in filter scripts (data manipulation only).
_EXTRA_BUILTINS = {
    "len": len, "range": range, "enumerate": enumerate, "zip": zip,
    "map": map, "filter": filter, "sorted": sorted, "reversed": reversed,
    "sum": sum, "min": min, "max": max, "abs": abs, "round": round,
    "all": all, "any": any,
    "int": int, "float": float, "str": str, "bool": bool,
    "list": list, "dict": dict, "set": set, "tuple": tuple,
    "True": True, "False": False, "None": None,
}


class SandboxError(Exception):
    """Raised when sandboxed code fails validation or execution."""


class FilterSandbox:
    """Safe execution environment for generated filter scripts."""

    def validate(self, code: str) -> tuple[bool, str]:
        """Static validation: syntax + security + required filter_stocks symbol."""
        # 1. Syntax check
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

        # 2. Security check on imports / forbidden builtins
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in FORBIDDEN_IMPORTS:
                        return False, f"Forbidden import: {alias.name}"
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in FORBIDDEN_IMPORTS:
                    return False, f"Forbidden import: {node.module}"
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_BUILTINS:
                    return False, f"Forbidden builtin: {node.func.id}"
            # Block attribute access on dunder names (redundant with compile_restricted
            # but gives a clearer, earlier error).
            if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                return False, f"Forbidden attribute access: {node.attr}"

        # 3. Required filter_stocks symbol
        has_filter_fn = any(
            isinstance(node, ast.FunctionDef) and node.name == "filter_stocks"
            for node in ast.walk(tree)
        )
        if not has_filter_fn:
            return False, "Missing required function: filter_stocks(df, params)"

        return True, "OK"

    def _build_safe_globals(self) -> dict[str, Any]:
        """Build the restricted globals dict with RestrictedPython guards."""
        builtins = {**safe_builtins, **_EXTRA_BUILTINS}
        # Strip forbidden builtins defensively even from safe_builtins.
        for name in FORBIDDEN_BUILTINS:
            builtins.pop(name, None)
        return {
            "__builtins__": builtins,
            "_getattr_": safer_getattr,            # blocks _-prefixed attrs
            "_getitem_": default_guarded_getitem,  # blocks dunder subscripts
            "_write_": full_write_guard,           # guards attribute writes
            "pd": pd,
            "np": np,
        }

    def execute(self, code: str, df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
        """Execute filter script in restricted environment.

        Uses RestrictedPython's compile_restricted so attribute/item access is
        routed through guarded hooks (preventing __class__/__subclasses__ escapes).
        """
        ok, msg = self.validate(code)
        if not ok:
            raise SandboxError(f"Validation failed: {msg}")

        try:
            bytecode = compile_restricted(code, filename="<filter>", mode="exec")
        except SyntaxError as e:
            raise SandboxError(f"compile_restricted syntax error: {e}") from e

        safe_globals = self._build_safe_globals()
        # RestrictedPython may emit a list of compilation issues on `bytecode.errors`.
        errors = getattr(bytecode, "errors", None)
        if errors:
            raise SandboxError(f"compile_restricted blocked: {errors}")

        try:
            exec(bytecode, safe_globals)  # noqa: S102 — intentionally executing
        except Exception as e:
            raise SandboxError(f"Execution error during def: {e}") from e

        filter_fn = safe_globals.get("filter_stocks")
        if not callable(filter_fn):
            raise SandboxError("filter_stocks is not callable")

        try:
            result = filter_fn(df, params or {})
        except Exception as e:
            raise SandboxError(f"filter_stocks raised: {e}") from e

        if not isinstance(result, pd.DataFrame):
            raise SandboxError(f"filter_stocks must return DataFrame, got {type(result)}")
        if "code" not in result.columns:
            raise SandboxError("Result must contain 'code' column")
        return result
