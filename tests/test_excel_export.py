"""Tests for src/edge-agent/excel_export.py (formatted workbook writer)."""

from pathlib import Path
from typing import Any, Dict, Optional

from openpyxl import load_workbook

from excel_export import build_columns, export_results, write_workbook
from practice_consolidation import consolidate


def _frame(ndg: Optional[str], **fields: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if ndg is not None:
        payload["ndg"] = {"value": ndg, "confidence": 1.0}
    for key, spec in fields.items():
        value, confidence = spec
        payload[key] = {"value": value, "confidence": confidence}
    return {"fields": payload, "_page_type": "Risultato ricerca", "_status": "OK"}


def test_ndg_and_denominazione_are_pinned_first() -> None:
    columns = build_columns()
    assert [c.schema_key for c in columns[:2]] == ["ndg", "denominazione"]


def test_all_45_canonical_fields_are_columns() -> None:
    columns = build_columns()
    assert len(columns) == 45
    assert len({c.schema_key for c in columns}) == 45


def test_columns_are_grouped_by_page_without_gaps() -> None:
    seen = []
    for column in build_columns():
        if not seen or seen[-1] != column.page_key:
            seen.append(column.page_key)
    assert seen == [
        "risultato_ricerca",
        "elenco_soggetti",
        "gestione_fidi_e_garanzie",
        "note_da_richiesta",
    ]


def test_user_label_overrides_the_display_name() -> None:
    columns = build_columns({"ndg": "Codice cliente"})
    assert columns[0].label == "Codice cliente"


def test_header_row_one_holds_merged_page_bands(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    write_workbook(consolidate([_frame("12345")]), build_columns(), str(path))
    ws = load_workbook(path).active
    assert ws.cell(row=1, column=1).value == "Risultato ricerca"
    merged = {str(r) for r in ws.merged_cells.ranges}
    assert "A1:I1" in merged  # 9 risultato_ricerca fields


def test_header_row_two_holds_field_labels(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    write_workbook(consolidate([_frame("12345")]), build_columns(), str(path))
    ws = load_workbook(path).active
    assert ws.cell(row=2, column=1).value == "NDG"
    assert ws.cell(row=2, column=2).value == "DENOMINAZIONE"


def test_data_starts_at_row_three_one_row_per_practice(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    records = consolidate([_frame("12345"), _frame("67890")])
    write_workbook(records, build_columns(), str(path))
    ws = load_workbook(path).active
    assert ws.max_row == 4
    # Column 1 holds the ndg *field value* as extracted, not the group key.
    assert ws.cell(row=3, column=1).value == "12345"
    assert ws.cell(row=4, column=1).value == "67890"


def test_panes_are_frozen_below_the_two_header_rows(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    write_workbook(consolidate([_frame("12345")]), build_columns(), str(path))
    assert load_workbook(path).active.freeze_panes == "C3"


def test_autofilter_covers_the_label_row_and_the_data(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    write_workbook(consolidate([_frame("12345")]), build_columns(), str(path))
    ws = load_workbook(path).active
    assert ws.auto_filter.ref == "A2:AS3"


def test_a_value_starting_with_equals_is_inert_text(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    records = consolidate([_frame("12345", tipo=("=1+1", 0.9))])
    columns = build_columns()
    write_workbook(records, columns, str(path))
    ws = load_workbook(path).active
    col = next(i for i, c in enumerate(columns, start=1) if c.schema_key == "tipo")
    cell = ws.cell(row=3, column=col)
    assert cell.data_type == "s"
    assert cell.value == "=1+1"  # preserved verbatim, no apostrophe


def test_a_negative_amount_keeps_its_minus_sign(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    records = consolidate([_frame("12345", importo_euro=("-1.234,00", 0.9))])
    columns = build_columns()
    write_workbook(records, columns, str(path))
    ws = load_workbook(path).active
    col = next(i for i, c in enumerate(columns, start=1) if c.schema_key == "importo_euro")
    assert ws.cell(row=3, column=col).value == "-1.234,00"


def test_unextracted_field_leaves_the_cell_empty(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    columns = build_columns()
    write_workbook(consolidate([_frame("12345")]), columns, str(path))
    ws = load_workbook(path).active
    col = next(i for i, c in enumerate(columns, start=1) if c.schema_key == "fase")
    assert ws.cell(row=3, column=col).value is None


def test_export_results_consolidates_and_returns_the_practice_count(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    written = export_results([_frame("12345"), _frame("12345")], str(path))
    assert written == 1
    assert load_workbook(path).active.max_row == 3


def test_export_results_applies_renamed_labels(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    export_results([_frame("12345")], str(path), labels={"ndg": "Codice cliente"})
    assert load_workbook(path).active.cell(row=2, column=1).value == "Codice cliente"


def test_all_column_positions_keep_the_legacy_workbook_contract() -> None:
    assert [column.schema_key for column in build_columns()] == [
        "ndg", "denominazione", "creazione", "evidenze", "fase", "filiale_relazione",
        "stato", "tipo", "tooltip_evidenze_b",
        "denominazione_1", "denominazione_2", "denominazione_3", "denominazione_4",
        "ndg_1", "ndg_2", "ndg_3", "ndg_4", "ruolo_1", "ruolo_2", "ruolo_3", "ruolo_4",
        "descrizione", "importo_euro", "rapporto", "scadenza", "tipo_op", "n_fido",
        "tooltip_descrizione_consap_dr_bis", "tooltip_descrizione_m_consap",
        "tooltip_descrizione_ipoteca", "tooltip_descrizione_bmb",
        "dal", "datore_di_lavoro_anagrafica", "di_cui_percepiscono_reddito",
        "importo_totale_annuo_nucleo", "note_scheda_privati", "note_della_richiesta",
        "nr_altri_componenti_nucleo", "numero_mensilita", "professione_principale",
        "rating_ufficiale", "retribuzione_annua_netta", "score_cgs", "tipo_contratto",
        "ultima_validazione_scheda",
    ]


def test_workbook_keeps_the_four_legacy_band_ranges(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    write_workbook(consolidate([_frame("12345")]), build_columns(), str(path))
    ws = load_workbook(path).active

    assert {str(merged) for merged in ws.merged_cells.ranges} == {
        "A1:I1", "J1:U1", "V1:AE1", "AF1:AS1"
    }
    assert [ws[address].value for address in ("A1", "J1", "V1", "AF1")] == [
        "Risultato ricerca", "Elenco Soggetti", "Gestione Fidi e Garanzie", "Note da Richiesta"
    ]


def test_export_results_applies_corrections(tmp_path: Path) -> None:
    path = tmp_path / "corrected.xlsx"
    export_results(
        [_frame("12345", tipo=("BPI Mutui", 0.9))],
        str(path),
        corrections={"12345": {"tipo": "Mutuo"}},
    )
    column = [c.schema_key for c in build_columns()].index("tipo") + 1
    assert load_workbook(path).active.cell(row=3, column=column).value == "Mutuo"
