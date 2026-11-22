"""CLAUDE.md: every function has full annotations on parameters and return type (UI modules of the redesign)."""

import ast
from pathlib import Path

EDGE_AGENT = Path(__file__).resolve().parent.parent / "src" / "edge-agent"
FILES = [
    "error_report.py",
    "theme.py",
    "ui/capture_tab.py",
    "ui/data_table_tab.py",
    "ui/frozen_table.py",
    "ui/icons.py",
    "ui/main_window.py",
    "ui/shell.py",
    "ui/widgets.py",
    "ui/win_effects.py",
]


def _incomplete(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
        missing = [a.arg for a in args if a.annotation is None and a.arg not in ("self", "cls")]
        if node.returns is None:
            missing.append("return")
        if missing:
            found.append(f"{path.name}:{node.lineno} {node.name} lacks {missing}")
    return found


def test_ui_modules_annotate_every_function_fully() -> None:
    assert [line for name in FILES for line in _incomplete(EDGE_AGENT / name)] == []
