"""Security sandbox for executing LLM-generated code."""

import ast
import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

FORBIDDEN_IMPORTS = {
    "os", "sys", "subprocess", "socket", "http", "urllib",
    "requests", "pathlib", "shutil", "io", "builtins",
}
FORBIDDEN_BUILTINS = {
    "open", "exec", "eval", "compile", "__import__",
    "input", "breakpoint", "exit", "quit",
}


class FilterSandbox:
    """Safe execution environment for generated filter scripts."""

    def validate(self, code: str) -> tuple[bool, str]:
        """Static validation: syntax check + security check."""
        # 1. Syntax check
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

        # 2. Security check
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_module = alias.name.split(".")[0]
                    if root_module in FORBIDDEN_IMPORTS:
                        return False, f"Forbidden import: {alias.name}"
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    root_module = node.module.split(".")[0]
                    if root_module in FORBIDDEN_IMPORTS:
                        return False, f"Forbidden import: {node.module}"
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_BUILTINS:
                    return False, f"Forbidden builtin: {node.func.id}"

        # 3. Check for filter_stocks function
        has_filter_fn = any(
            isinstance(node, ast.FunctionDef) and node.name == "filter_stocks"
            for node in ast.walk(tree)
        )
        if not has_filter_fn:
            return False, "Missing required function: filter_stocks(df, params)"

        return True, "OK"

    def execute(self, code: str, df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
        """Execute filter script in restricted environment."""
        safe_globals: dict[str, Any] = {
            "__builtins__": {
                k: v for k, v in __builtins__.items()
                if k not in FORBIDDEN_BUILTINS
            } if isinstance(__builtins__, dict) else {
                k: getattr(__builtins__, k) for k in dir(__builtins__)
                if k not in FORBIDDEN_BUILTINS
            },
            "pd": pd,
            "np": np,
            "len": len,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "sorted": sorted,
            "sum": sum,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
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

        exec(code, safe_globals)
        filter_fn = safe_globals.get("filter_stocks")
        if not callable(filter_fn):
            raise ValueError("filter_stocks is not callable")

        result = filter_fn(df, params or {})
        if not isinstance(result, pd.DataFrame):
            raise ValueError(f"filter_stocks must return DataFrame, got {type(result)}")
        if "code" not in result.columns:
            raise ValueError("Result must contain 'code' column")
        return result
