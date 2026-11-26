"""Visible practice selection, ordered OCR and the operator's workbook."""

from pathlib import Path

from openpyxl import load_workbook

from capture_navigation import CaptureNavigation
from excel_export import build_columns, write_workbook
from page_registry import PageDef
from practice_consolidation import PracticeEngine


def shot(role: str, number: str | None, page: str, **values: str) -> dict:
    return {"_practice_view": role, "_practice_number": number, "_page_type": page,
            "fields": {key: {"value": value, "confidence": 1.0} for key, value in values.items()}}


def test_browsing_results_keeps_the_current_practice_until_a_detail_opens() -> None:
    engine = PracticeEngine()
    frames = [shot("selection", "31", "Fidi", ndg="100"),
              shot("list", "42", "Elenco", ndg="200"),
              shot("list", "42", "Colonne", creazione="oggi")]
    engine.merge(frames, {})
    assert [row.ndg for row in engine.records(exportable_only=True)] == ["100"]
    engine.merge([shot("selection", "42", "Soggetti", ndg="200")], {})
    assert [row.fields["creazione"]["value"] for row in engine.records()] == [None, "oggi"]


def test_anonymous_note_after_failed_new_selection_waits_for_its_own_header(tmp_path: Path) -> None:
    engine = PracticeEngine()
    engine.merge([shot("selection", "31", "Fidi", ndg="100"),
                  dict(shot("selection", None, "Soggetti"), _status="ERROR"),
                  shot("detail", None, "Note", note_della_richiesta="Solo B")], {})
    path = tmp_path / "pratiche.xlsx"
    write_workbook(engine.records(exportable_only=True), build_columns(), str(path))
    workbook = load_workbook(path)
    try:
        assert "Solo B" not in next(workbook.active.iter_rows(min_row=3, values_only=True))
    finally:
        workbook.close()
    engine.merge([shot("detail", "42", "Soggetti", ndg="200")], {})
    assert [(row.ndg, row.fields["note_della_richiesta"]["value"]) for row in engine.records()] == [
        ("100", None), ("200", "Solo B")]


def test_a_third_selection_cannot_claim_an_unidentified_previous_note() -> None:
    engine = PracticeEngine()
    engine.merge([shot("selection", None, "Note", note_della_richiesta="Solo B"),
                  shot("selection", "53", "Soggetti", ndg="300")], {})
    assert engine.records()[0].fields["note_della_richiesta"]["value"] is None


def test_two_selected_files_of_one_customer_have_independent_edits() -> None:
    engine = PracticeEngine()
    engine.merge([shot("selection", "31", "Note", ndg="100", tipo="A"),
                  shot("selection", "42", "Note", ndg="100", tipo="B")], {})
    first, second = engine.records()
    engine.refresh(second.edit_key, {second.edit_key: {"tipo": "Corretto"}})
    assert [row.fields["tipo"]["value"] for row in engine.records()] == ["A", "Corretto"]
    assert first.edit_key != second.edit_key


def test_failed_selection_clears_old_checklist_before_any_new_identity() -> None:
    pages = [PageDef(name, i, f"screen {i}", name) for i, name in [(1, "Elenco"), (4, "Soggetti"), (9, "Note")]]
    nav = CaptureNavigation(pages)
    frames = [shot("selection", "31", "Note", ndg="100"), shot("list", "42", "Elenco", ndg="100")]
    nav.update(frames)
    assert nav.captured == {"Note"}
    frames.append(dict(shot("selection", None, "Soggetti"), _status="ERROR"))
    nav.update(frames)
    assert nav.ndg is None and not nav.captured
    frames.append(shot("detail", "42", "Soggetti", ndg="100"))
    nav.update(frames)
    assert nav.captured == {"Elenco", "Soggetti"}


def test_an_unobserved_switch_cannot_assign_an_anonymous_note_to_either_file() -> None:
    engine = PracticeEngine()
    engine.merge([shot("selection", "31", "Fidi", ndg="100"),
                  shot("detail", None, "Note", note_della_richiesta="Incerta")], {})
    assert engine.records()[0].fields["note_della_richiesta"]["value"] is None
    engine.merge([shot("detail", "42", "Soggetti", ndg="100")], {})
    assert [row.fields["note_della_richiesta"]["value"] for row in engine.records()] == [None, None]


def test_return_to_the_same_file_confirms_an_intermediate_note() -> None:
    engine = PracticeEngine()
    engine.merge([shot("selection", "31", "Fidi", ndg="100"),
                  shot("detail", None, "Note", note_della_richiesta="Nota A"),
                  shot("detail", "31", "Fidi", ndg="100")], {})
    assert engine.records()[0].fields["note_della_richiesta"]["value"] == "Nota A"


def test_an_unmapped_live_template_cannot_fall_back_to_an_old_ndg() -> None:
    engine = PracticeEngine()
    engine.merge([{"fields": {"ndg": {"value": "100"}}},
                  shot("unknown", None, "Pagina personalizzata", note_della_richiesta="Incerta")], {})
    assert engine.records()[0].fields["note_della_richiesta"]["value"] is None


def test_reopening_a_file_in_progress_restores_only_its_own_next_step() -> None:
    pages = [PageDef(name, i, f"screen {i}", name) for i, name in [(4, "Soggetti"), (5, "Fidi"), (9, "Note")]]
    nav = CaptureNavigation(pages)
    frames = [shot("selection", "31", "Soggetti", ndg="100"),
              shot("detail", "42", "Note", ndg="100"),
              shot("selection", "31", "Fidi", ndg="100")]
    nav.update(frames)
    state = nav.snapshot("Fidi", "captured", 2)
    assert state["resumed_practice"] == "31" and state["next_page"] == "Note"
    assert state["captured"] == ["Soggetti", "Fidi"]


def test_a_conflicting_customer_in_another_window_cannot_overwrite_a_known_file() -> None:
    engine = PracticeEngine()
    engine.merge([shot("selection", "31", "Soggetti", ndg="100"),
                  shot("selection", "31", "Note", ndg="200", note_della_richiesta="Incerta"),
                  shot("detail", "31", "Note", note_della_richiesta="Ancora incerta")], {})
    assert [(r.ndg, r.fields["note_della_richiesta"]["value"]) for r in engine.records()] == [("100", None)]


def test_partial_headers_from_incompatible_customers_cannot_validate_each_other() -> None:
    engine = PracticeEngine()
    engine.merge([shot("selection", "31", "Fidi", ndg="100"),
                  shot("selection", None, "Soggetti", ndg="200"),
                  shot("detail", None, "Note", note_della_richiesta="Solo B"),
                  shot("detail", "31", "Fidi")], {})
    assert engine.records()[0].fields["note_della_richiesta"]["value"] is None


def test_anonymous_data_cannot_cross_its_capture_context_even_when_the_same_file_reopens() -> None:
    engine = PracticeEngine()
    engine.merge([dict(shot("selection", "31", "Fidi", ndg="100"), _capture_context=0),
                  dict(shot("detail", None, "Note", note_della_richiesta="Incerta"), _capture_context=0),
                  dict(shot("detail", "31", "Fidi", ndg="100"), _capture_context=2)], {})
    assert engine.records()[0].fields["note_della_richiesta"]["value"] is None


def test_a_screenshot_bound_to_another_practice_cannot_write_business_fields() -> None:
    engine = PracticeEngine()
    engine.merge([dict(shot("selection", "31", "Fidi", ndg="100"), _capture_context=0),
                  dict(shot("detail", "42", "Note", note_della_richiesta="Dubbia"),
                       _capture_context=0, _capture_practice="31"),
                  dict(shot("selection", "42", "Fidi", ndg="200"), _capture_context=2)], {})
    assert [r.fields["note_della_richiesta"]["value"] for r in engine.records()] == [None, None]


def test_a_provisional_context_cannot_be_claimed_by_two_headers_from_the_same_vdi() -> None:
    engine = PracticeEngine()
    engine.merge([dict(shot("selection", "31", "Fidi", ndg="100"), _capture_context=0),
                  dict(shot("detail", "42", "Note", note_della_richiesta="Dubbia"), _capture_context=0),
                  dict(shot("detail", None, "Note", note_della_richiesta="Da verificare"), _capture_context=0),
                  dict(shot("detail", "42", "Soggetti", ndg="200"), _capture_context=0)], {})
    assert [(r.practice_number, r.fields["note_della_richiesta"]["value"]) for r in engine.records()] == [("31", None)]
