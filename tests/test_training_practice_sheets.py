"""A lot delivered as one sheet per practice: what the reader makes of the reviewer's cells."""

from pathlib import Path

import pytest
from practice_sheet_fixture import FIDI_TOOLTIP, GARANZIE_TOOLTIP, SHEET, write_sheets

from training.practice_sheets import read_practice_sheets, screen_name


def _workbook(tmp_path: Path, rows: list[tuple[object, object]] = SHEET, practice: str = "60000001") -> Path:
    return write_sheets(tmp_path / "lotto.xlsx", {practice: rows})


def _changed(label: str, value: object) -> list[tuple[object, object]]:
    """The sheet with the first row of that label holding another value."""
    index = next(i for i, row in enumerate(SHEET) if row[0] == label)
    return [*SHEET[:index], (label, value), *SHEET[index + 1:]]


def _fields(path: Path) -> dict[str, dict]:
    return {record["field"]: record for record in read_practice_sheets(path) if record["field"]}


def _outside(path: Path) -> dict[str, dict]:
    return {record["display_name"]: record for record in read_practice_sheets(path) if not record["field"]}


def test_number_becomes_text(tmp_path: Path) -> None:
    assert _fields(_workbook(tmp_path))["ndg"]["value"] == "60000001"


def test_date_is_written_as_on_the_screen(tmp_path: Path) -> None:
    assert _fields(_workbook(tmp_path))["creazione"]["value"] == "15/09/2026"


def test_amount_is_written_as_on_the_screen(tmp_path: Path) -> None:
    assert _fields(_workbook(tmp_path))["importo_euro"]["value"] == "125.000"


def test_literal_vuoto_is_an_empty_outcome(tmp_path: Path) -> None:
    record = _fields(_workbook(tmp_path))["fase"]
    assert (record["value"], record["outcome"]) == (None, "VUOTO")


def test_written_value_is_a_transcription(tmp_path: Path) -> None:
    assert _fields(_workbook(tmp_path))["stato"]["outcome"] == "TRASCRITTO"


def test_surrounding_spaces_are_dropped(tmp_path: Path) -> None:
    assert _fields(_workbook(tmp_path))["evidenze"]["value"] == "BC"


def test_line_break_inside_a_value_becomes_a_space(tmp_path: Path) -> None:
    assert _fields(_workbook(tmp_path))["denominazione_1"]["value"] == "ROSSI MARIO, BIANCHI ANNA"


def test_subject_row_not_listed_is_empty(tmp_path: Path) -> None:
    record = _fields(_workbook(tmp_path))["ruolo_4"]
    assert (record["value"], record["outcome"]) == (None, "VUOTO")


def test_description_of_the_fidi_table_is_not_taken_from_a_guarantee(tmp_path: Path) -> None:
    assert _fields(_workbook(tmp_path))["descrizione"]["value"] == "M.CONSAP >=80%"


def test_fidi_tooltip_with_the_consap_code_is_the_m_consap_field(tmp_path: Path) -> None:
    fields = _fields(_workbook(tmp_path))
    assert fields["tooltip_descrizione_m_consap"]["value"] == "340176 - MUTUO FOND PRIV CONSAP >=80%"


def test_fidi_tooltip_with_another_code_leaves_the_m_consap_field_empty(tmp_path: Path) -> None:
    path = _workbook(tmp_path, _changed(FIDI_TOOLTIP, "340170 - MUTUO FONDIARIO PRIVATI"))
    assert _fields(path)["tooltip_descrizione_m_consap"]["outcome"] == "VUOTO"


def test_fidi_tooltip_with_another_code_stays_in_the_truth(tmp_path: Path) -> None:
    path = _workbook(tmp_path, _changed(FIDI_TOOLTIP, "340170 - MUTUO FONDIARIO PRIVATI"))
    assert _outside(path)["Fido: tooltip Descrizione"]["value"] == "340170 - MUTUO FONDIARIO PRIVATI"


def test_guarantee_tooltip_with_the_mortgage_code_is_the_mortgage_field(tmp_path: Path) -> None:
    assert _fields(_workbook(tmp_path))["tooltip_descrizione_ipoteca"]["value"] == "55-IPOTECA DI PRIMO GRADO"


def test_guarantee_tooltip_with_the_dr_bis_code_is_the_dr_bis_field(tmp_path: Path) -> None:
    fields = _fields(_workbook(tmp_path))
    assert fields["tooltip_descrizione_consap_dr_bis"]["value"] == "457-IMP. FID. F.DO 1 CASA DR SOSTEGNI BIS"


def test_guarantee_values_stay_outside_the_vocabulary(tmp_path: Path) -> None:
    assert _outside(_workbook(tmp_path))["Garanzia 2: NDG"]["value"] == "11153238"


def test_section_without_a_title_is_the_note_page(tmp_path: Path) -> None:
    assert _fields(_workbook(tmp_path))["note_della_richiesta"]["page"] == "Note"


def test_branch_on_the_note_page_is_the_relationship_branch(tmp_path: Path) -> None:
    assert _fields(_workbook(tmp_path))["filiale_relazione"]["value"] == "230 - BO XXI APRIL"


def test_proposing_agent_stays_outside_the_vocabulary(tmp_path: Path) -> None:
    assert _outside(_workbook(tmp_path))["Agente proponente"]["value"] == "Anna Verdi"


def test_record_names_its_sheet_and_row(tmp_path: Path) -> None:
    assert _fields(_workbook(tmp_path))["ndg"]["excel_row"] == "60000001!3"


def test_description_sheet_is_not_a_practice(tmp_path: Path) -> None:
    assert {record["practice"] for record in read_practice_sheets(_workbook(tmp_path))} == {"60000001"}


def test_refuses_unknown_label(tmp_path: Path) -> None:
    path = _workbook(tmp_path, [*SHEET[:3], ("Campo inventato", "x"), *SHEET[3:]])
    with pytest.raises(ValueError, match="Campo inventato"):
        read_practice_sheets(path)


def test_refuses_label_without_a_value(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="senza valore"):
        read_practice_sheets(_workbook(tmp_path, _changed("Stato", None)))


def test_refuses_formula(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="formula"):
        read_practice_sheets(_workbook(tmp_path, _changed("Stato", "=1+1")))


def test_refuses_second_loan(tmp_path: Path) -> None:
    index = SHEET.index(("n° Gar.", "G1"))
    with pytest.raises(ValueError, match="n° Fido"):
        read_practice_sheets(_workbook(tmp_path, [*SHEET[:index], ("n° Fido", "F2"), *SHEET[index:]]))


def test_refuses_two_guarantees_with_the_same_tooltip_code(tmp_path: Path) -> None:
    rows = [*SHEET]
    rows[len(SHEET) - 1 - SHEET[::-1].index((GARANZIE_TOOLTIP, "457-IMP. FID. F.DO 1 CASA DR SOSTEGNI BIS "))] = (
        GARANZIE_TOOLTIP, "55-IPOTECA DI PRIMO GRADO")
    with pytest.raises(ValueError, match="doppio"):
        read_practice_sheets(_workbook(tmp_path, rows))


def test_refuses_sheet_without_all_the_pages(tmp_path: Path) -> None:
    title = SHEET.index(("Soggetti", None))
    end = SHEET.index(("Gestione fidi e garanzie", None))
    with pytest.raises(ValueError, match="Soggetti"):
        read_practice_sheets(_workbook(tmp_path, [*SHEET[:title], *SHEET[end:]]))


def test_refuses_page_without_one_of_its_fields(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Stato"):
        read_practice_sheets(_workbook(tmp_path, [row for row in SHEET if row[0] != "Stato"]))


def test_refuses_value_without_a_label(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="senza campo"):
        read_practice_sheets(_workbook(tmp_path, [*SHEET, (None, "testo")]))


def test_refuses_sheet_not_named_as_a_practice(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Riepilogo"):
        read_practice_sheets(_workbook(tmp_path, practice="Riepilogo"))


@pytest.mark.parametrize(("file_name", "expected"), [
    ("elenco1.png", "Elenco"), ("ELENCO1.png", "Elenco"), ("elenco2.png", "Elenco2"), ("soggetti.png", "Soggetti"),
    ("gestionefidi1.png", "GestioneFidi"), ("gestionefidi4.png", "GestioneFidi4"),
    ("note.png", "Note"), ("note1.png", "Note"), ("note2.png", "Note2"),
])
def test_delivered_file_gets_the_screen_name_of_its_page(file_name: str, expected: str) -> None:
    assert screen_name(file_name) == expected


def test_refuses_delivered_file_of_an_unknown_page() -> None:
    with pytest.raises(ValueError, match="offtopic"):
        screen_name("offtopic.png")


# ============================================================
# From the values of a page to the rows of each screen
# ============================================================

M_CONSAP = "tooltip su valore campo Descrizione (riga 1): M. CONSAP >= 80%"
DR_BIS = "tooltip su valore campo Descrizione (riga 1): CONSAP DR BIS"
MORTGAGE = "tooltip su valore campo Descrizione (riga 2): IPOTECA I GR."
SCREENS = {"Elenco": {}, "Elenco2": {"non_visibili": ["Tipo"]}, "Soggetti": {}, "GestioneFidi": {},
           "GestioneFidi2": {"tooltip": M_CONSAP}, "GestioneFidi3": {"tooltip": MORTGAGE},
           "GestioneFidi4": {"tooltip": DR_BIS}, "Note": {"parziali": ["Note della richiesta"]},
           "Note2": {"non_visibili": ["Filiale relazione"]}}


def _review(path: Path, screens: dict | None = None, corrections: list | None = None, sha256: str | None = None) -> Path:
    import hashlib
    import json

    review = path.with_name("correzioni.json")
    review.write_text(json.dumps({"workbook_sha256": sha256 or hashlib.sha256(path.read_bytes()).hexdigest(),
                                  "schermate": {"60000001": SCREENS if screens is None else screens},
                                  "correzioni": corrections or []}), encoding="utf-8")
    return review


def _rows(tmp_path: Path, screens: dict | None = None, corrections: list | None = None) -> dict[tuple[str, str], dict]:
    path = _workbook(tmp_path)
    records = read_practice_sheets(path, _review(path, screens, corrections))
    return {(record["screen"].split("__", 1)[1], record["display_name"]): record for record in records}


def test_value_of_a_page_is_on_every_screen_of_the_page(tmp_path: Path) -> None:
    assert _rows(tmp_path)[("Elenco2", "Stato")]["value"] == "APP"


def test_field_out_of_a_screen_is_not_visible_there(tmp_path: Path) -> None:
    record = _rows(tmp_path)[("Elenco2", "Tipo")]
    assert (record["value"], record["outcome"]) == (None, "NON VISIBILE")


def test_field_out_of_a_screen_keeps_its_value_on_the_others(tmp_path: Path) -> None:
    assert _rows(tmp_path)[("Elenco", "Tipo")]["value"] == "BMB"


def test_note_cut_by_the_screen_keeps_its_text_as_partial(tmp_path: Path) -> None:
    record = _rows(tmp_path)[("Note", "Note della richiesta")]
    assert record["outcome"] == "PARZIALE"
    assert record["value"].startswith("Numero Finanziamento")


def test_tooltip_is_on_the_screen_that_shows_it(tmp_path: Path) -> None:
    assert _rows(tmp_path)[("GestioneFidi2", M_CONSAP)]["value"] == "340176 - MUTUO FOND PRIV CONSAP >=80%"


def test_tooltip_is_not_on_the_other_screens(tmp_path: Path) -> None:
    assert ("GestioneFidi3", M_CONSAP) not in _rows(tmp_path)


def test_value_outside_the_vocabulary_stays_on_the_first_screen_of_the_page(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    assert ("Note", "Agente proponente") in rows
    assert ("Note2", "Agente proponente") not in rows


def test_tooltip_of_another_product_has_no_row_on_the_screens(tmp_path: Path) -> None:
    screens = {**SCREENS, "GestioneFidi2": {"tooltip": "Fido: tooltip Descrizione"}}
    path = _workbook(tmp_path, _changed(FIDI_TOOLTIP, "340170 - MUTUO FONDIARIO PRIVATI"))
    records = read_practice_sheets(path, _review(path, screens))
    assert not [record for record in records if record["display_name"] == M_CONSAP]


def test_practice_without_screens_keeps_its_values_on_the_page(tmp_path: Path) -> None:
    path = _workbook(tmp_path)
    records = read_practice_sheets(path, _review(path, {}))
    assert {record["screen"] for record in records} == {f"60000001__{page}" for page in
                                                        ("Elenco", "Soggetti", "GestioneFidi", "Note")}


def test_refuses_screen_of_an_unknown_page(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Riepilogo"):
        _rows(tmp_path, {**SCREENS, "Riepilogo": {}})


def test_refuses_practice_without_the_first_screen_of_a_page(tmp_path: Path) -> None:
    screens = {name: view for name, view in SCREENS.items() if name != "Soggetti"}
    with pytest.raises(ValueError, match="Soggetti"):
        _rows(tmp_path, screens)


def test_refuses_hidden_field_that_the_page_does_not_have(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Rapporto"):
        _rows(tmp_path, {**SCREENS, "Elenco2": {"non_visibili": ["Rapporto"]}})


def test_refuses_tooltip_that_the_sheet_does_not_have(tmp_path: Path) -> None:
    path = _workbook(tmp_path, _changed(FIDI_TOOLTIP, "340170 - MUTUO FONDIARIO PRIVATI"))
    with pytest.raises(ValueError, match="M. CONSAP"):
        read_practice_sheets(path, _review(path))


def test_refuses_tooltip_of_the_sheet_on_no_screen(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="IPOTECA"):
        _rows(tmp_path, {**SCREENS, "GestioneFidi3": {}})


def test_refuses_review_of_another_workbook(tmp_path: Path) -> None:
    path = _workbook(tmp_path)
    with pytest.raises(ValueError, match="workbook"):
        read_practice_sheets(path, _review(path, sha256="altro"))


# ============================================================
# Corrections checked against the screen
# ============================================================

FIX = {"riga_excel": "60000001!6", "campo": "Stato", "revisione": {"esito": "TRASCRITTO", "trascrizione": "APP"},
       "corretto": {"esito": "TRASCRITTO", "trascrizione": "ABB"}}


def test_correction_replaces_the_value_on_every_screen(tmp_path: Path) -> None:
    rows = _rows(tmp_path, corrections=[FIX])
    assert (rows[("Elenco", "Stato")]["value"], rows[("Elenco2", "Stato")]["value"]) == ("ABB", "ABB")


def test_correction_keeps_the_reviewed_value(tmp_path: Path) -> None:
    assert _rows(tmp_path, corrections=[FIX])[("Elenco", "Stato")]["correction"]["revisione"]["trascrizione"] == "APP"


def test_refuses_correction_that_does_not_match_the_cell(tmp_path: Path) -> None:
    other = {**FIX, "revisione": {"esito": "TRASCRITTO", "trascrizione": "LAV"}}
    with pytest.raises(ValueError, match="correzione"):
        _rows(tmp_path, corrections=[other])


def test_refuses_correction_of_a_row_that_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="60000001!99"):
        _rows(tmp_path, corrections=[{**FIX, "riga_excel": "60000001!99"}])
