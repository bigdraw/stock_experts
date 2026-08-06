"""Security sandbox for executing LLM-generated code (filters, strategies, alerts).

Hardened with RestrictedPython. Three LLM-generated-code execution surfaces
(filters, backtest strategies, alert conditions) all route through this module
so they share the same guards (ISSUE-018):

  1. AST-level static pre-check: forbidden imports/builtins, dunder attribute
     access, IO method calls (``pd.read_csv`` / ``df.to_csv`` / ``np.load``),
     and required entry symbols — for clear, early error messages.
  2. ``RestrictedPython.compile_restricted`` transforms the AST so dunder
     attribute access, attribute writes, and item access route through guarded
     hooks (closes ``().__class__.__subclasses__()`` introspection escapes).
  3. ``_getattr_`` = ``safer_getattr`` (blocks any ``_``-prefixed attr),
     ``_getitem_``/``_write_`` guards, a minimal ``safe_builtins`` set with
     ``getattr``/``setattr``/``delattr``/``exec``/``eval``/``__import__`` removed.

Residual risk (documented): a separate process + seccomp/container is true
isolation. This hardening raises the bar substantially — dunder escapes are
blocked AND pandas/numpy IO (file read/write, SQL, pickle RCE) is AST-blocked
so the classic ``pd.read_pickle``/``np.load(pickle)`` RCE chain is closed at
validation time. Filter execution is also admin-gated (api/v1/filters.py) and
alert/strategy generation are admin/user-scoped as defence-in-depth.
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
    "os",
    "sys",
    "subprocess",
    "socket",
    "http",
    "urllib",
    "requests",
    "pathlib",
    "shutil",
    "io",
    "builtins",
    "ctypes",
    "importlib",
    "pickle",
    "marshal",
}
FORBIDDEN_BUILTINS = {
    "open",
    "exec",
    "eval",
    "compile",
    "__import__",
    "input",
    "breakpoint",
    "exit",
    "quit",
    "globals",
    "locals",
    "vars",
    "getattr",  # blocks getattr(obj, '__class__')-style escapes
    "setattr",
    "delattr",
}

# Pandas/numpy IO method names — reachable because pd/np are injected for legit
# compute. AST-blocking these closes file read/write, SQL access, SSRF, and the
# pickle RCE chain (pd.read_pickle / np.load(allow_pickle=True)).
_PANDAS_IO = {
    "read_csv", "read_json", "read_sql", "read_sql_query", "read_sql_table",
    "read_pickle", "read_parquet", "read_feather", "read_hdf", "read_excel",
    "read_html", "read_stata", "read_sas", "read_clipboard", "read_fwf",
    "read_table", "read_orc", "read_spss", "read_gbq", "read_xml", "read_eq",
    "to_csv", "to_json", "to_sql", "to_pickle", "to_parquet", "to_feather",
    "to_hdf", "to_excel", "to_html", "to_stata", "to_clipboard", "to_orc",
    "to_latex", "to_markdown",
}
_NP_IO = {
    "load", "save", "savez", "savez_compressed", "loadtxt", "savetxt",
    "fromfile", "tofile", "memmap",
}
IO_DENYLIST = _PANDAS_IO | _NP_IO

# Extra builtins allowed in LLM-generated code (data manipulation only).
_EXTRA_BUILTINS = {
    "len": len,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "sorted": sorted,
    "reversed": reversed,
    "sum": sum,
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "all": all,
    "any": any,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "True": True,
    "False": False,
    "None": None,
}


class SandboxError(Exception):
    """Raised when sandboxed code fails validation or execution."""


def validate_restricted(code: str, required_symbols: tuple[str, ...], require_all: bool = False) -> tuple[bool, str]:
    """Static validation: syntax + security + required entry symbols.

    ``required_symbols`` are the legitimate entry function names the caller will
    invoke. ``require_all=True`` requires every name to be defined; otherwise at
    least one must be defined (e.g. a backtest strategy defines any subset of
    ``init_strategy``/``select_stocks``/``generate_signals``).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_IMPORTS:
                    return False, f"Forbidden import: {alias.name}"
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in FORBIDDEN_IMPORTS:
                return False, f"Forbidden import: {node.module}"
        if isinstance(node, ast.Call):
            # Forbidden builtin direct call: exec(...)/eval(...)
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_BUILTINS:
                return False, f"Forbidden builtin: {node.func.id}"
            # IO method call: pd.read_csv(...) / df.to_csv(...) / np.load(...)
            if isinstance(node.func, ast.Attribute) and node.func.attr in IO_DENYLIST:
                return False, f"Forbidden IO call: {node.func.attr}"
        # Block dunder attribute access (redundant with compile_restricted but
        # gives a clearer, earlier error).
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return False, f"Forbidden attribute access: {node.attr}"

    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if require_all:
        missing = [s for s in required_symbols if s not in defined]
        if missing:
            return False, f"Missing required function(s): {missing}"
    else:
        if not any(s in defined for s in required_symbols):
            return False, f"Missing required function (need at least one of): {list(required_symbols)}"
    return True, "OK"


def build_restricted_globals() -> dict[str, Any]:
    """Build the restricted globals dict with RestrictedPython guards + pd/np.

    Shared by the filter, backtest, and alert execution paths so they all get
    the same dunder/IO protection.
    """
    builtins = {**safe_builtins, **_EXTRA_BUILTINS}
    for name in FORBIDDEN_BUILTINS:
        builtins.pop(name, None)
    return {
        "__builtins__": builtins,
        "_getattr_": safer_getattr,  # blocks _-prefixed attrs
        "_getitem_": default_guarded_getitem,  # blocks dunder subscripts
        "_write_": full_write_guard,  # guards attribute writes
        "pd": pd,
        "np": np,
    }


class FilterSandbox:
    """Safe execution environment for LLM-generated code.

    Three entry points share one guard set:
      - ``execute``: filter scripts (``filter_stocks(df, params) -> DataFrame``).
      - ``exec_namespace``: backtest strategies (define ``init_strategy`` /
        ``select_stocks`` / ``generate_signals``); caller fetches the symbols.
      - ``run_function``: alert conditions (``check(data) -> bool``).
    """

    def validate(self, code: str) -> tuple[bool, str]:
        """Filter-script validation (requires ``filter_stocks``)."""
        return validate_restricted(code, ("filter_stocks",), require_all=True)

    def exec_namespace(
        self,
        code: str,
        required_symbols: tuple[str, ...],
        require_all: bool = False,
    ) -> dict[str, Any]:
        """Validate + compile_restricted + exec, returning the populated namespace.

        Raises ``SandboxError`` on any validation/compile/exec failure.
        """
        ok, msg = validate_restricted(code, required_symbols, require_all=require_all)
        if not ok:
            raise SandboxError(f"Validation failed: {msg}")

        try:
            bytecode = compile_restricted(code, filename="<sandbox>", mode="exec")
        except SyntaxError as e:
            raise SandboxError(f"compile_restricted syntax error: {e}") from e

        safe_globals = build_restricted_globals()
        errors = getattr(bytecode, "errors", None)
        if errors:
            raise SandboxError(f"compile_restricted blocked: {errors}")

        try:
            exec(bytecode, safe_globals)  # noqa: S102 — intentionally executing
        except Exception as e:
            raise SandboxError(f"Execution error during def: {e}") from e

        return safe_globals

    def execute(self, code: str, df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
        """Execute a filter script (``filter_stocks(df, params) -> DataFrame``)."""
        safe_globals = self.exec_namespace(code, ("filter_stocks",), require_all=True)
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

    def run_function(self, code: str, fn_name: str, args: tuple, required_symbols: tuple[str, ...] = ()) -> Any:
        """Exec restricted code and call ``fn_name(*args)``.

        Used by alert conditions (``check(data) -> bool``). ``required_symbols``
        defaults to just ``fn_name`` so the entry function must exist.
        """
        required = required_symbols or (fn_name,)
        safe_globals = self.exec_namespace(code, required, require_all=True)
        fn = safe_globals.get(fn_name)
        if not callable(fn):
            raise SandboxError(f"{fn_name} is not callable")
        try:
            return fn(*args)
        except Exception as e:
            raise SandboxError(f"{fn_name} raised: {e}") from e
