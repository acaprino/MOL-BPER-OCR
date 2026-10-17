"""Tests for src/edge-agent/page_registry.py."""

import json
from pathlib import Path

import pytest

from page_registry import PageDef, PageRegistry, slugify

REAL_PROMPTS = (
    Path(__file__).resolve().parent.parent
    / "src" / "edge-agent" / "assets" / "templates" / "bper" / "prompts.json"
)


def _write_spec(tmp_path: Path, pages: list) -> Path:
    p = tmp_path / "prompts.json"
    p.write_text(json.dumps({"pages": pages}), encoding="utf-8")
    return p


def test_slugify_flattens_punctuation() -> None:
    assert (
        slugify("Gestione Fidi e Garanzie - Tooltip Descrizione Garanzie (riga 1)")
        == "gestione_fidi_e_garanzie_tooltip_descrizione_garanzie_riga_1"
    )
    assert slugify("Note da Richiesta") == "note_da_richiesta"


def test_load_real_prompts_json() -> None:
    reg = PageRegistry.load(REAL_PROMPTS)
    assert len(reg.pages) == 9
    assert reg.catchall_name == "Altro / Non riconosciuto"
    assert [p.order for p in reg.pages] == list(range(1, 10))
    assert reg.pages[0].name == "Risultato ricerca"
    assert reg.pages[8].name == "Note da Richiesta"


def test_resolve_template_and_name_case_insensitive() -> None:
    reg = PageRegistry.load(REAL_PROMPTS)
    fidi_tooltip = "Gestione Fidi e Garanzie - Tooltip Descrizione Fidi"
    assert reg.resolve("screen 6").name == fidi_tooltip
    assert reg.resolve("Screen 6").name == fidi_tooltip
    assert reg.resolve(fidi_tooltip).template == "screen 6"
    assert reg.resolve("elenco soggetti").template == "screen 4"


def test_resolve_catchall_unknown_and_empty_return_none() -> None:
    reg = PageRegistry.load(REAL_PROMPTS)
    assert reg.resolve("Altro / Non riconosciuto") is None
    assert reg.resolve("pagina inventata") is None
    assert reg.resolve(None) is None
    assert reg.resolve("") is None


def test_acquirable_ml_mode_counts_only_templated_pages(tmp_path: Path) -> None:
    spec = [
        {"name": "Pagina A", "order": 1, "template": "screen 1"},
        {"name": "Pagina B", "order": 2, "template": None},
        {"name": "Altro", "catchall": True},
    ]
    reg = PageRegistry.load(_write_spec(tmp_path, spec))
    assert [p.name for p in reg.acquirable("ml")] == ["Pagina A"]
    assert [p.name for p in reg.acquirable("llm")] == ["Pagina A", "Pagina B"]
    assert reg.names("hybrid") == ["Pagina A", "Pagina B"]


def test_real_prompts_ml_total_is_nine() -> None:
    reg = PageRegistry.load(REAL_PROMPTS)
    assert len(reg.acquirable("ml")) == 9


def test_duplicate_template_raises(tmp_path: Path) -> None:
    spec = [
        {"name": "A", "order": 1, "template": "screen 1"},
        {"name": "B", "order": 2, "template": "screen 1"},
    ]
    with pytest.raises(ValueError):
        PageRegistry.load(_write_spec(tmp_path, spec))


def test_missing_order_raises(tmp_path: Path) -> None:
    spec = [{"name": "A", "template": "screen 1"}]
    with pytest.raises(ValueError):
        PageRegistry.load(_write_spec(tmp_path, spec))


def test_empty_registry_is_permissive() -> None:
    reg = PageRegistry.empty()
    page = reg.resolve("screen 3")
    assert isinstance(page, PageDef)
    assert page.name == "screen 3"
    assert page.order == 0
    assert page.slug == "screen_3"
    assert reg.acquirable("ml") == []
    assert reg.resolve(None) is None
