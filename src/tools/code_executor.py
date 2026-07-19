"""Restricted execution tool for generated, dataframe-only analysis code."""

import ast
import subprocess
import sys
import tempfile
from pathlib import Path

from ..config import settings


class UnsafeCodeError(ValueError):
    pass


_ALLOWED_MODULES = {"math", "numpy", "pandas", "statistics"}
_BANNED_NAMES = {
    "open",
    "exec",
    "eval",
    "compile",
    "__import__",
    "input",
    "globals",
    "locals",
    "getattr",
    "setattr",
}
_BANNED_ATTRIBUTES = {
    "read_clipboard",
    "read_feather",
    "read_html",
    "read_json",
    "read_orc",
    "read_parquet",
    "read_pickle",
    "read_sas",
    "read_spss",
    "read_sql",
    "read_stata",
    "read_xml",
    "to_clipboard",
    "to_csv",
    "to_excel",
    "to_feather",
    "to_json",
    "to_parquet",
    "to_pickle",
    "to_sql",
}


def validate_analysis_code(code: str) -> None:
    if len(code) > 8_000:
        raise UnsafeCodeError("Generated code is too long.")
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        raise UnsafeCodeError(f"Generated code has invalid syntax: {error.msg}") from error
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name.split(".")[0] for alias in node.names]
            disallowed = sorted(set(names).difference(_ALLOWED_MODULES))
            if disallowed:
                raise UnsafeCodeError(f"Generated code imports unsupported modules: {', '.join(disallowed)}.")
        if isinstance(node, ast.Name) and node.id in _BANNED_NAMES:
            raise UnsafeCodeError(f"Generated code uses blocked operation: {node.id}")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                raise UnsafeCodeError("Generated code uses a blocked dunder attribute.")
            if node.attr in _BANNED_ATTRIBUTES:
                raise UnsafeCodeError(f"Generated code uses blocked I/O method: {node.attr}.")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "read_csv":
                if not node.args or not isinstance(node.args[0], ast.Name) or node.args[0].id != "CSV_PATH":
                    raise UnsafeCodeError("pd.read_csv must read only from CSV_PATH.")


def execute_analysis(code: str, csv_path: str) -> str:
    """Run validated code in a separate process; its only input is CSV_PATH."""
    validate_analysis_code(code)
    with tempfile.TemporaryDirectory(prefix="csv-agent-") as temp_dir:
        script = Path(temp_dir) / "analysis.py"
        script.write_text(f"CSV_PATH = {str(Path(csv_path).resolve())!r}\n" + code, encoding="utf-8")
        try:
            result = subprocess.run(
                [sys.executable, "-I", str(script)],
                cwd=temp_dir,
                env={"PATH": "/usr/bin:/bin"},
                capture_output=True,
                text=True,
                timeout=settings.execution_timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"Analysis timed out after {settings.execution_timeout_seconds} seconds.") from error
    if result.returncode:
        raise RuntimeError(result.stderr[-1_500:] or "Analysis code failed without an error message.")
    return result.stdout[-6_000:]
