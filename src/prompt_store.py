"""Prompt store — loads the JSON prompt catalog once and keeps it in memory.

Every prompt the project sends to an LLM lives in `prompts/`, one JSON file per
prompt. This module is the single loader, shared by the extraction engine and by
the edge-agent page router. It sits at the repo root, outside both, and imports
nothing beyond the stdlib: reading a prompt must not drag in LangChain, which
`src/extraction/__init__.py` would.

Directory resolution — `PROMPTS_DIR` when set (strict, no fallback), otherwise
`<repo root>/prompts` from source; when frozen, `<exe dir>/prompts` first with the
copy inside the PyInstaller bundle as fallback. Candidates are tried in order and
the first one that *loads* wins, so a damaged editable copy next to the exe falls
back to the packaged one instead of killing the app at startup. `catalog_source()`
reports which one was used: log it, or a redirected catalog stays invisible.

Why fail-fast — a corrupt prompt is worse than a missing file: the pipeline would
keep running and produce wrong fields that look right. The page catalog
(`src/edge-agent/assets/templates/bper/prompts.json`) deliberately does the opposite
and degrades to an empty spec, because a missed page detection is visible to the
operator. Keep that asymmetry when adding a third catalog.

File format — `text` is the prompt body, `parts` holds named fragments for prompts
the code assembles conditionally; both accept a string or a list of lines joined
with newlines. `CATALOG` below declares what the code requires of each entry: the
parts it looks up and the `{placeholder}` fields it substitutes. Templates are
validated at load, so a stray brace fails at startup instead of raising KeyError
mid-capture; write `{{` for a literal brace.
"""

from __future__ import annotations

import json
import os
import string
import sys
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Set, Tuple

# ============================================================
# Catalog contract
# ============================================================


@dataclass(frozen=True)
class PromptSpec:
    """What the code requires of one catalog entry.

    `parts` are the fragments the code looks up by name. `placeholders` are the
    `{field}` names it substitutes with str.format(); `None` marks a prompt sent
    verbatim, where braces carry no meaning and are left unchecked.
    """

    parts: FrozenSet[str] = frozenset()
    placeholders: Optional[FrozenSet[str]] = None


# Every id the code looks up, with the shape it expects. A missing id, a missing
# part or a template whose braces disagree with this table is a startup error,
# not a silently degraded prompt.
CATALOG: Mapping[str, PromptSpec] = MappingProxyType({
    "extraction_main": PromptSpec(),
    "extraction_anchor": PromptSpec(),
    "extraction_retry_header": PromptSpec(),
    "extraction_retry_body": PromptSpec(),
    "extraction_retry_footer": PromptSpec(),
    "extraction_user_instruction": PromptSpec(),
    "extraction_json_schema_instruction": PromptSpec(
        placeholders=frozenset({"schema"}),
    ),
    "extraction_anchor_hints": PromptSpec(
        parts=frozenset({"ndg", "denominazione"}),
        placeholders=frozenset({"value"}),
    ),
    "page_router_system": PromptSpec(
        parts=frozenset({"base", "expected_page"}),
        placeholders=frozenset({"pages", "expected_page"}),
    ),
    "page_router_user": PromptSpec(
        parts=frozenset({"header", "expected_page", "page_line", "footer"}),
        placeholders=frozenset({"expected_page", "name", "hints"}),
    ),
})


class PromptStoreError(RuntimeError):
    """Raised when the prompt catalog is missing, malformed or incomplete."""


@dataclass(frozen=True)
class Prompt:
    """One prompt as loaded from disk."""

    id: str
    text: str
    parts: Mapping[str, str]
    description: str
    source: Path


# ============================================================
# Parsing and validation
# ============================================================

def _as_text(value: Any, prompt_id: str, key: str) -> str:
    """Accept a string or a list of lines; anything else is a catalog error."""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(line, str) for line in value):
        return "\n".join(value)
    raise PromptStoreError(
        f"prompt '{prompt_id}': '{key}' must be a string or a list of strings"
    )


def _format_fields(template: str, prompt_id: str, where: str) -> Set[str]:
    """Return the `{field}` names of a format template, rejecting odd ones."""
    fields: Set[str] = set()
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as exc:
        raise PromptStoreError(
            f"prompt '{prompt_id}' ({where}): unbalanced braces ({exc}); "
            "write '{{' or '}}' for a literal brace"
        ) from exc
    for _literal, name, _format_spec, _conversion in parsed:
        if name is None:
            continue
        if name == "" or name.isdigit():
            raise PromptStoreError(
                f"prompt '{prompt_id}' ({where}): positional placeholder "
                "'{}' is not supported, name it"
            )
        fields.add(name.split(".")[0].split("[")[0])
    return fields


def _validate_against_spec(prompt: Prompt, spec: PromptSpec, declared: Any) -> None:
    """Check one prompt against what the code expects of it."""
    missing_parts = sorted(spec.parts - prompt.parts.keys())
    if missing_parts:
        raise PromptStoreError(
            f"prompt '{prompt.id}' is missing part(s): {', '.join(missing_parts)}"
        )

    if spec.placeholders is None:
        if declared:
            raise PromptStoreError(
                f"prompt '{prompt.id}' declares placeholders {sorted(declared)}, "
                "but the code never formats it"
            )
        return

    if declared is not None and set(declared) != set(spec.placeholders):
        raise PromptStoreError(
            f"prompt '{prompt.id}': 'placeholders' says {sorted(declared)} "
            f"but the code substitutes {sorted(spec.placeholders)}"
        )

    found: Set[str] = set()
    if prompt.text:
        found |= _format_fields(prompt.text, prompt.id, "text")
    for name, value in prompt.parts.items():
        found |= _format_fields(value, prompt.id, f"parts.{name}")

    unknown = sorted(found - set(spec.placeholders))
    if unknown:
        raise PromptStoreError(
            f"prompt '{prompt.id}': unknown placeholder(s) {unknown}; "
            f"the code only substitutes {sorted(spec.placeholders)} "
            "(write '{{' for a literal brace)"
        )


def _load_file(path: Path) -> Tuple[Prompt, Any]:
    """Parse and structurally validate one prompt file."""
    try:
        # utf-8-sig: a BOM from a Windows editor must not read as invalid JSON.
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise PromptStoreError(f"cannot read {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise PromptStoreError(f"{path}: expected a JSON object")

    prompt_id = path.stem
    declared_id = raw.get("id")
    if declared_id is not None and declared_id != prompt_id:
        raise PromptStoreError(
            f"{path}: 'id' is '{declared_id}' but the file name says '{prompt_id}'"
        )

    text = _as_text(raw["text"], prompt_id, "text") if "text" in raw else ""

    parts: Dict[str, str] = {}
    if "parts" in raw:
        if not isinstance(raw["parts"], dict):
            raise PromptStoreError(f"{path}: 'parts' must be an object")
        for name, value in raw["parts"].items():
            parts[name] = _as_text(value, prompt_id, f"parts.{name}")

    if not text and not any(parts.values()):
        raise PromptStoreError(f"{path}: needs a non-empty 'text' or 'parts' entry")

    prompt = Prompt(
        id=prompt_id,
        text=text,
        parts=MappingProxyType(parts),
        description=str(raw.get("description", "")),
        source=path,
    )
    return prompt, raw.get("placeholders")


# ============================================================
# Loading
# ============================================================

def catalog_candidates() -> List[Path]:
    """Directories to try, most specific first."""
    override = os.getenv("PROMPTS_DIR")
    if override:
        # An explicit override fails closed: never silently fall back elsewhere.
        return [Path(override).expanduser()]

    if bool(getattr(sys, "frozen", False)):
        # Portable layout: a prompts/ folder next to the exe wins, so the packaged
        # texts stay editable without a rebuild; the bundled copy is the safety net.
        candidates = [Path(sys.executable).resolve().parent / "prompts"]
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "prompts")
        return candidates

    return [Path(__file__).resolve().parent.parent / "prompts"]


def load_prompts(directory: Path) -> Dict[str, Prompt]:
    """Read and validate every `*.json` in one catalog directory."""
    base = Path(directory)
    if not base.is_dir():
        raise PromptStoreError(f"prompt directory not found: {base}")

    loaded: Dict[str, Prompt] = {}
    declarations: Dict[str, Any] = {}
    for path in sorted(base.glob("*.json")):
        prompt, declared = _load_file(path)
        loaded[prompt.id] = prompt
        declarations[prompt.id] = declared

    missing = sorted(CATALOG.keys() - loaded.keys())
    if missing:
        raise PromptStoreError(f"{base} is missing prompt(s): {', '.join(missing)}")

    for prompt_id, spec in CATALOG.items():
        _validate_against_spec(loaded[prompt_id], spec, declarations[prompt_id])

    return loaded


def _load_first_usable() -> Tuple[Path, Dict[str, Prompt]]:
    """Try the candidates in order and keep the first catalog that loads."""
    problems: List[str] = []
    for candidate in catalog_candidates():
        try:
            return candidate, load_prompts(candidate)
        except PromptStoreError as exc:
            problems.append(str(exc))
    raise PromptStoreError(
        "no usable prompt catalog (set PROMPTS_DIR to point at a valid one):\n  "
        + "\n  ".join(problems)
    )


# ============================================================
# In-memory registry
# ============================================================

# Read once per process at import, then served from memory, like the rest of the
# import-time configuration. There is deliberately no reload: the consumers bind
# their prompts to module constants at import, so a reload would update some of
# them and not others.
_SOURCE, _REGISTRY = _load_first_usable()


def catalog_source() -> Path:
    """Directory the in-memory catalog was loaded from."""
    return _SOURCE


def get_prompt(prompt_id: str) -> Prompt:
    """Return a loaded prompt, or raise if the id is unknown."""
    try:
        return _REGISTRY[prompt_id]
    except KeyError:
        raise PromptStoreError(
            f"unknown prompt '{prompt_id}'; loaded: {', '.join(sorted(_REGISTRY))}"
        ) from None


def get_text(prompt_id: str) -> str:
    """Return the body of a prompt."""
    prompt = get_prompt(prompt_id)
    if not prompt.text:
        raise PromptStoreError(f"prompt '{prompt_id}' has no 'text' body")
    return prompt.text


def get_part(prompt_id: str, part: str) -> str:
    """Return one named fragment of a prompt."""
    prompt = get_prompt(prompt_id)
    try:
        return prompt.parts[part]
    except KeyError:
        raise PromptStoreError(
            f"prompt '{prompt_id}' has no part '{part}'; "
            f"available: {', '.join(sorted(prompt.parts)) or 'none'}"
        ) from None
