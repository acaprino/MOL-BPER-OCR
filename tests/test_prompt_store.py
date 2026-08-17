"""Tests for prompt_store.py (JSON prompt catalog)."""

import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

import prompt_store
from prompt_store import (
    CATALOG,
    PromptStoreError,
    catalog_candidates,
    catalog_source,
    get_part,
    get_prompt,
    get_text,
    load_prompts,
)

REAL_CATALOG = Path(__file__).resolve().parent.parent / "prompts"


def _copy_catalog(destination: Path) -> Path:
    """A private, valid copy of the real catalog to mutate one file at a time."""
    destination.mkdir(parents=True, exist_ok=True)
    for src in REAL_CATALOG.glob("*.json"):
        shutil.copyfile(src, destination / src.name)
    return destination


def _write(directory: Path, name: str, doc: Dict[str, Any]) -> Path:
    path = directory / f"{name}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


def _patch(directory: Path, name: str, **changes: Any) -> Path:
    """Rewrite one field of an existing catalog file."""
    path = directory / f"{name}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc.update(changes)
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


# ============================================================
# Real catalog
# ============================================================

def test_real_catalog_satisfies_the_contract(tmp_path: Path) -> None:
    # load_prompts() enforces CATALOG (ids, parts, placeholders): the assertion
    # here is that the shipped files pass it, and that none was skipped.
    loaded = load_prompts(REAL_CATALOG)
    assert sorted(loaded) == sorted(p.stem for p in REAL_CATALOG.glob("*.json"))
    assert CATALOG.keys() <= loaded.keys()


def test_every_prompt_documents_itself() -> None:
    for prompt_id, prompt in load_prompts(REAL_CATALOG).items():
        assert prompt.text or prompt.parts, f"{prompt_id} is empty"
        assert prompt.description, f"{prompt_id} has no description"


def test_catalog_source_is_the_repo_catalog() -> None:
    assert catalog_source() == REAL_CATALOG


# ============================================================
# Directory resolution
# ============================================================

def test_env_override_is_the_only_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An explicit override must fail closed, never fall back to the bundle.
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
    assert catalog_candidates() == [tmp_path]


def test_source_layout_looks_next_to_the_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROMPTS_DIR", raising=False)
    assert catalog_candidates() == [REAL_CATALOG]


def test_frozen_prefers_the_editable_copy_next_to_the_exe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PROMPTS_DIR", raising=False)
    exe_dir = tmp_path / "app"
    bundle = tmp_path / "bundle"
    (exe_dir).mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "EdgeAgent.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)

    assert catalog_candidates() == [exe_dir / "prompts", bundle / "prompts"]


def test_a_broken_first_candidate_falls_back_to_the_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = _copy_catalog(tmp_path / "broken")
    (broken / "extraction_main.json").write_text("{not json", encoding="utf-8")
    good = _copy_catalog(tmp_path / "good")
    monkeypatch.setattr(prompt_store, "catalog_candidates", lambda: [broken, good])

    source, loaded = prompt_store._load_first_usable()

    assert source == good
    assert loaded["extraction_main"].text


def test_all_candidate_failures_are_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        prompt_store, "catalog_candidates", lambda: [tmp_path / "a", tmp_path / "b"]
    )
    with pytest.raises(PromptStoreError) as excinfo:
        prompt_store._load_first_usable()
    assert "a" in str(excinfo.value) and "b" in str(excinfo.value)


# ============================================================
# File format
# ============================================================

def test_line_list_is_joined_with_newlines(tmp_path: Path) -> None:
    catalog = _copy_catalog(tmp_path)
    _write(catalog, "extraction_main", {"text": ["prima", "", "seconda"]})
    assert load_prompts(catalog)["extraction_main"].text == "prima\n\nseconda"


def test_plain_string_body_is_kept_verbatim(tmp_path: Path) -> None:
    catalog = _copy_catalog(tmp_path)
    _write(catalog, "extraction_main", {"text": "  spazi ai bordi  "})
    assert load_prompts(catalog)["extraction_main"].text == "  spazi ai bordi  "


def test_parts_accept_lines_too(tmp_path: Path) -> None:
    catalog = _copy_catalog(tmp_path)
    _patch(catalog, "page_router_user", parts={
        "header": ["a", "b"],
        "expected_page": "PAGINA ATTESA: {expected_page}",
        "page_line": "- {name}: {hints}",
        "footer": "fine",
    })
    assert load_prompts(catalog)["page_router_user"].parts["header"] == "a\nb"


def test_loaded_parts_are_read_only() -> None:
    prompt = load_prompts(REAL_CATALOG)["page_router_user"]
    with pytest.raises(TypeError):
        prompt.parts["header"] = "tampered"  # type: ignore[index]


def test_utf8_bom_is_accepted(tmp_path: Path) -> None:
    # Notepad on Windows writes a BOM; that must not read as invalid JSON.
    catalog = _copy_catalog(tmp_path)
    (catalog / "extraction_main.json").write_text(
        json.dumps({"text": "con BOM", "description": "d"}, ensure_ascii=False),
        encoding="utf-8-sig",
    )
    assert load_prompts(catalog)["extraction_main"].text == "con BOM"


def test_non_utf8_file_is_reported_as_a_catalog_error(tmp_path: Path) -> None:
    catalog = _copy_catalog(tmp_path)
    (catalog / "extraction_main.json").write_text(
        json.dumps({"text": "FEDELTÀ", "description": "d"}, ensure_ascii=False),
        encoding="cp1252",
    )
    with pytest.raises(PromptStoreError, match="cannot read"):
        load_prompts(catalog)


# ============================================================
# Contract validation
# ============================================================

def test_literal_brace_in_a_formatted_template_is_rejected(tmp_path: Path) -> None:
    # The failure this validation exists for: an example JSON added by hand used
    # to load fine and raise KeyError mid-capture.
    catalog = _copy_catalog(tmp_path)
    doc = json.loads((catalog / "page_router_system.json").read_text(encoding="utf-8"))
    doc["parts"]["base"] += ' Esempio: {"page_type": "x"}'
    (catalog / "page_router_system.json").write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(PromptStoreError, match="unknown placeholder"):
        load_prompts(catalog)


def test_escaped_braces_are_allowed(tmp_path: Path) -> None:
    catalog = _copy_catalog(tmp_path)
    doc = json.loads((catalog / "page_router_system.json").read_text(encoding="utf-8"))
    doc["parts"]["base"] += " Esempio: {{page_type}}"
    (catalog / "page_router_system.json").write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8"
    )
    assert "{{page_type}}" in load_prompts(catalog)["page_router_system"].parts["base"]


def test_braces_are_not_checked_in_verbatim_prompts(tmp_path: Path) -> None:
    # extraction_main is never formatted: a brace there is just text.
    catalog = _copy_catalog(tmp_path)
    _write(catalog, "extraction_main", {"text": 'Esempio: {"ndg": "123"}', "description": "d"})
    assert load_prompts(catalog)["extraction_main"].text.endswith('{"ndg": "123"}')


def test_positional_placeholder_is_rejected(tmp_path: Path) -> None:
    catalog = _copy_catalog(tmp_path)
    _patch(catalog, "extraction_json_schema_instruction", text="Schema: {} {schema}")
    with pytest.raises(PromptStoreError, match="positional"):
        load_prompts(catalog)


def test_missing_required_part_is_rejected(tmp_path: Path) -> None:
    catalog = _copy_catalog(tmp_path)
    doc = json.loads((catalog / "page_router_system.json").read_text(encoding="utf-8"))
    del doc["parts"]["expected_page"]
    doc["placeholders"] = ["pages"]
    (catalog / "page_router_system.json").write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(PromptStoreError, match="missing part"):
        load_prompts(catalog)


def test_declared_placeholders_must_match_what_the_code_substitutes(tmp_path: Path) -> None:
    catalog = _copy_catalog(tmp_path)
    _patch(catalog, "page_router_user", placeholders=["expected_page"])
    with pytest.raises(PromptStoreError, match="placeholders"):
        load_prompts(catalog)


def test_placeholders_declared_on_a_verbatim_prompt_are_rejected(tmp_path: Path) -> None:
    catalog = _copy_catalog(tmp_path)
    _patch(catalog, "extraction_main", placeholders=["ndg"])
    with pytest.raises(PromptStoreError, match="never formats it"):
        load_prompts(catalog)


# ============================================================
# Failure modes
# ============================================================

def test_missing_directory_is_reported(tmp_path: Path) -> None:
    with pytest.raises(PromptStoreError, match="prompt directory not found"):
        load_prompts(tmp_path / "nope")


def test_missing_required_prompt_is_reported(tmp_path: Path) -> None:
    catalog = _copy_catalog(tmp_path)
    (catalog / "extraction_anchor.json").unlink()
    with pytest.raises(PromptStoreError, match="extraction_anchor"):
        load_prompts(catalog)


def test_id_must_match_file_name(tmp_path: Path) -> None:
    catalog = _copy_catalog(tmp_path)
    _patch(catalog, "extraction_main", id="altro")
    with pytest.raises(PromptStoreError, match="file name"):
        load_prompts(catalog)


def test_empty_body_is_rejected(tmp_path: Path) -> None:
    catalog = _copy_catalog(tmp_path)
    _write(catalog, "extraction_main", {"description": "vuoto", "parts": {}})
    with pytest.raises(PromptStoreError, match="non-empty"):
        load_prompts(catalog)


def test_wrong_body_type_is_rejected(tmp_path: Path) -> None:
    catalog = _copy_catalog(tmp_path)
    _write(catalog, "extraction_main", {"text": 42})
    with pytest.raises(PromptStoreError, match="must be a string or a list"):
        load_prompts(catalog)


def test_invalid_json_is_reported(tmp_path: Path) -> None:
    catalog = _copy_catalog(tmp_path)
    (catalog / "extraction_main.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PromptStoreError, match="cannot read"):
        load_prompts(catalog)


# ============================================================
# In-memory registry
# ============================================================

def test_unknown_prompt_id_is_reported() -> None:
    with pytest.raises(PromptStoreError, match="unknown prompt"):
        get_prompt("non_esiste")


def test_unknown_part_is_reported() -> None:
    with pytest.raises(PromptStoreError, match="has no part"):
        get_part("page_router_user", "non_esiste")


def test_get_text_rejects_a_parts_only_prompt() -> None:
    with pytest.raises(PromptStoreError, match="no 'text' body"):
        get_text("page_router_user")


# ============================================================
# Wiring: the code reads its prompts from the catalog
# ============================================================

def test_extraction_constants_come_from_the_catalog() -> None:
    pytest.importorskip("langchain_core")
    from extraction import prompts

    assert prompts.PROMPT == get_text("extraction_main")
    assert prompts.ANCHOR_PROMPT == get_text("extraction_anchor")
    assert prompts.FIELD_RETRY_PROMPTS == {
        "HEADER": get_text("extraction_retry_header"),
        "BODY": get_text("extraction_retry_body"),
        "FOOTER": get_text("extraction_retry_footer"),
    }


def test_page_router_builds_its_prompts_from_the_catalog(tmp_path: Path) -> None:
    # No importorskip: the router reads the catalog through prompt_store, which
    # is stdlib-only, so this no longer needs the whole extraction stack.
    from llm_router import LLMPageRouter

    spec = tmp_path / "prompts.json"
    spec.write_text(
        json.dumps({"pages": [{"name": "Pagina A", "hints": "hint A"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    router = LLMPageRouter(prompts_path=spec, api_key="")

    system = router._build_system_prompt()
    assert system == get_part("page_router_system", "base").format(pages="Pagina A")

    user = router._build_user_prompt()
    assert user.splitlines() == [
        get_part("page_router_user", "header"),
        get_part("page_router_user", "page_line").format(name="Pagina A", hints="hint A"),
        get_part("page_router_user", "footer"),
    ]

    router.set_expected_page("Pagina A")
    assert router._build_system_prompt() == system + get_part(
        "page_router_system", "expected_page"
    ).format(expected_page="Pagina A")
    assert get_part("page_router_user", "expected_page").format(
        expected_page="Pagina A"
    ) in router._build_user_prompt().splitlines()
