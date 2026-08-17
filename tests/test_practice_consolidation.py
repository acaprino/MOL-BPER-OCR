"""Tests for edge-agent/practice_consolidation.py (frame -> practice grouping)."""

from typing import Any, Dict, Optional

from practice_consolidation import PracticeRecord, consolidate, normalize_ndg


def _frame(
    ndg: Optional[str],
    page_type: str = "Risultato ricerca",
    **fields: Any,
) -> Dict[str, Any]:
    """Build a minimal pipeline result: {key: (value, confidence)} in **fields."""
    payload: Dict[str, Any] = {}
    if ndg is not None:
        payload["ndg"] = {"value": ndg, "confidence": 1.0}
    for key, spec in fields.items():
        value, confidence = spec
        payload[key] = {"value": value, "confidence": confidence}
    return {"fields": payload, "_page_type": page_type, "_status": "OK"}


def test_normalize_ndg_ignores_separators_and_leading_zeros() -> None:
    assert normalize_ndg("12345") == "12345"
    assert normalize_ndg("12.345") == "12345"
    assert normalize_ndg("12 345") == "12345"
    assert normalize_ndg("0012345") == "12345"


def test_normalize_ndg_keeps_a_non_numeric_suffix() -> None:
    # norm_number_str() would drop the suffix and merge this with practice 12345.
    assert normalize_ndg("12345/A") == "12345A"
    assert normalize_ndg("12345/A") != normalize_ndg("12345")


def test_normalize_ndg_returns_none_when_unreadable() -> None:
    assert normalize_ndg(None) is None
    assert normalize_ndg("") is None
    assert normalize_ndg("n/d") is None
    assert normalize_ndg("---") is None


def test_same_ndg_frames_collapse_into_one_record() -> None:
    records = consolidate([
        _frame("12345", tipo=("BPI Mutui", 0.9)),
        _frame("12345", "Elenco Soggetti", ruolo_1=("TITOLARE", 0.9)),
    ])
    assert len(records) == 1
    assert records[0].ndg == "12345"
    assert records[0].frame_count == 2
    assert records[0].fields["tipo"]["value"] == "BPI Mutui"
    assert records[0].fields["ruolo_1"]["value"] == "TITOLARE"


def test_distinct_ndg_produce_records_in_first_appearance_order() -> None:
    records = consolidate([_frame("999"), _frame("111"), _frame("999")])
    assert [r.ndg for r in records] == ["999", "111"]
    assert records[0].frame_count == 2


def test_frame_without_ndg_attaches_to_last_seen_practice() -> None:
    records = consolidate([
        _frame("12345"),
        _frame(None, "Risultato ricerca - Colonne estese", creazione=("01/02/2026", 0.9)),
    ])
    assert len(records) == 1
    assert records[0].fields["creazione"]["value"] == "01/02/2026"


def test_leading_frames_without_ndg_join_the_first_identified_practice() -> None:
    records = consolidate([
        _frame(None, "Risultato ricerca - Tooltip mostrata", evidenze=("B", 0.9)),
        _frame("12345", tipo=("BPI Mutui", 0.9)),
    ])
    assert len(records) == 1
    assert records[0].ndg == "12345"
    assert records[0].fields["evidenze"]["value"] == "B"
    assert records[0].frame_count == 2


def test_session_without_any_readable_ndg_yields_one_anonymous_record() -> None:
    records = consolidate([_frame(None, tipo=("BPI Mutui", 0.9)), _frame(None)])
    assert len(records) == 1
    assert records[0].ndg is None
    assert records[0].fields["tipo"]["value"] == "BPI Mutui"


def test_higher_confidence_wins_on_conflict() -> None:
    records = consolidate([
        _frame("12345", tipo=("SBAGLIATO", 0.4)),
        _frame("12345", tipo=("BPI Mutui", 0.95)),
    ])
    assert records[0].fields["tipo"]["value"] == "BPI Mutui"


def test_non_null_beats_null_even_at_high_confidence() -> None:
    records = consolidate([
        _frame("12345", tipo=(None, 0.99)),
        _frame("12345", tipo=("BPI Mutui", 0.2)),
    ])
    assert records[0].fields["tipo"]["value"] == "BPI Mutui"


def test_ndg_written_in_different_formats_group_together() -> None:
    records = consolidate([_frame("12345"), _frame("12.345")])
    assert len(records) == 1


def test_denominazione_is_exposed_on_the_record() -> None:
    records = consolidate([_frame("12345", denominazione=("ROSSI MARIO", 0.9))])
    assert records[0].denominazione == "ROSSI MARIO"


def test_source_pages_records_every_contributing_frame() -> None:
    records = consolidate([
        _frame("12345", "Risultato ricerca"),
        _frame("12345", "Elenco Soggetti"),
    ])
    assert records[0].source_pages == ("Risultato ricerca", "Elenco Soggetti")


def test_every_canonical_field_is_present_even_when_never_extracted() -> None:
    records = consolidate([_frame("12345")])
    assert len(records[0].fields) == 45
    assert records[0].fields["note_della_richiesta"]["value"] is None


def test_empty_input_yields_no_records() -> None:
    assert consolidate([]) == []


def test_record_is_frozen() -> None:
    record = consolidate([_frame("12345")])[0]
    assert isinstance(record, PracticeRecord)
    try:
        record.ndg = "999"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("PracticeRecord must be frozen")
