"""Read the canonical field vocabulary without loading the extraction runtime."""
from __future__ import annotations

import ast
import re
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
REPOSITORY = SRC_DIR.parent


def vocabulary() -> tuple[list[str], dict[str, str]]:
    """Load only literal domain data from its existing canonical owner."""
    tree = ast.parse((SRC_DIR / "extraction/fields.py").read_text(encoding="utf-8"))
    values: dict[str, object] = {}
    for statement in tree.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            if statement.target.id in ("FIELD_KEYS", "CSV_TO_SCHEMA"):
                values[statement.target.id] = ast.literal_eval(statement.value)
    fields = values.get("FIELD_KEYS")
    mapping = values.get("CSV_TO_SCHEMA")
    if not isinstance(fields, list) or not isinstance(mapping, dict):
        raise ValueError("Il vocabolario canonico non contiene i dati letterali attesi.")
    if set(mapping.values()) != set(fields):
        raise ValueError("Mapping CSV e campi canonici non coincidono.")
    return fields, mapping


def field_role(field: str) -> str:
    """Subject rows share a semantic role; decoding restores their row numbers."""
    subject = re.fullmatch(r"(ndg|denominazione|ruolo)_[1-4]", field)
    return f"sogg_{subject.group(1)}" if subject else field


def role_vocabulary() -> list[str]:
    fields, _ = vocabulary()
    return ["O", *dict.fromkeys(field_role(field) for field in fields)]
