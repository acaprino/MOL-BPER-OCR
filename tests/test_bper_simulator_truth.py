"""Evaluator-facing CSV from the single-practice website, at its native viewport."""
import csv
import hashlib
from io import StringIO
import json
from pathlib import Path
import re

import pytest

from extraction.evaluation import eval_outputs, load_ground_truth
from extraction.fields import CSV_TO_SCHEMA
from extraction.imaging import screen_id_from_path
from bper_profiles import SCHEDA_FIELDS
from bper_simulator_truth import (
    CSV_LABELS, NOTE_BOX_PX, NOTE_LINE_PX, NOTE_PADDING_PX, OUTGOING_ROW_PX, available_steps, evidence_slots,
    practice_truth_csv, practice_truth_record_csv, scheda_states,
)
from bper_synthetic_db import PENSIONERS, synthetic_practices

STYLESHEET = Path(__file__).resolve().parents[1] / "bper-emulator" / "site" / "scheda" / "scheda.css"
# Screen-row digests of the 64 synthetic practices before the pensioners existed, updated on purpose where the DOM
# audit (bper-emulator/audit_truth.cjs) proved the old rows wrong: screen 2 gains the Creazione row, shown there in
# every practice (the reference's real truth lists it too); screens 1 and 2 lose DENOMINAZIONE for the 11
# practices whose name the list cuts with an ellipsis; screen 3 gains the NDG or DENOMINAZIONE that the
# content-sized list still shows at the end of its scroll, in 39 practices; in 30 practices whose Evidenze marks
# widen the list, screen 3 loses them again and one screen 1 its Creazione; the shorter branch names change the
# Filiale relazione row and the real-looking account tails the Rapporto row of all 64 (see the fixture's _comment).
SNAPSHOT = Path(__file__).resolve().parent / "fixtures" / "bper_truth_snapshot.json"
NOTE_ROW = ("screen 9", "Note della richiesta")
APPLICANT = re.compile(r"Richiedente di \d+ anni, [^.]+\. ")
TOP_FIELDS = {
    "ndg", "denominazione", "professione_principale", "dal", "numero_mensilita", "retribuzione_annua_netta",
    "tipo_contratto", "datore_di_lavoro_anagrafica", "rating_ufficiale", "score_cgs", "ultima_validazione_scheda",
}
BOTTOM_FIELDS = {
    "datore_di_lavoro_anagrafica", "rating_ufficiale", "score_cgs", "nr_altri_componenti_nucleo",
    "di_cui_percepiscono_reddito", "importo_totale_annuo_nucleo", "note_scheda_privati",
}


def scheda_with(note: str, outgoings: tuple[dict, ...] = ()) -> dict:
    return {
        "ndg": "09000001", "schedaId": "00000000001", "name": "D'ARCO MARTINA",
        "fields": {
            "professione_principale": "IMPIEGATO PUBBLICA AMMINISTRAZIONE", "dal": "MARZO 2019",
            "numero_mensilita": "13", "retribuzione_annua_netta": "26.650", "tipo_contratto": "TEMPO INDETERMINATO",
            "datore_di_lavoro_anagrafica": "COMUNE DI PROVA", "rating_ufficiale": "N/D", "score_cgs": "N/D",
            "nr_altri_componenti_nucleo": "2", "di_cui_percepiscono_reddito": "1",
            "importo_totale_annuo_nucleo": "18.000", "note_scheda_privati": note,
            "ultima_validazione_scheda": "12/02/2025 10:15 (6 giorni fa)",
        },
        "details": {"outgoings": list(outgoings)},
    }


@pytest.fixture
def practice() -> dict:
    return {
        "ndg": "09000001", "name": "D'ARCO MARTINA", "created": "10/02/2025", "date": "10/02/2025",
        "state": "LAV", "phase": "IST", "evidence": "B", "evidenceTooltip": "Origination BSTORE",
        "type": "BPI Mutui", "branch": "9901", "branchName": "FILIALE SINTETICA",
        "subjects": [{"ndg": "09000001", "name": "D'ARCO MARTINA", "role": "Richiedente"}],
        "fidi": [
            {"id": "F1", "account": "001 00000001", "description": "M. CASA", "due": "10/02/2055",
             "amount": "81.250,50", "operation": "In Lavoraz.", "tooltip": "Mutuo abitazione", "tooltipField": None},
            {"id": "F2", "account": "001 00000002", "description": "ACCESSORIO", "due": "10/02/2035",
             "amount": "5.000", "operation": "In Lavoraz.", "tooltip": "Credito accessorio", "tooltipField": None},
        ],
        "creditTotal": "86.250,50",
        "guarantees": [
            {"description": "IPOTECA I GR.", "tooltip": "55-IPOTECA DI PRIMO GRADO",
             "tooltipField": "tooltip_descrizione_ipoteca"},
            {"description": "GAR. PERS.", "tooltip": "Garanzia personale", "tooltipField": None},
        ],
        "notes": 'Acquisto, importo 81.250,50 €\nRichiedente "D\'ARCO".',
    }


def loaded(practice: dict, tmp_path: Path) -> dict[str, dict[str, str]]:
    csv_path = tmp_path / "dati.csv"
    csv_path.write_bytes(practice_truth_csv(practice).encode("utf-8-sig"))
    return {
        screen: {CSV_TO_SCHEMA[label]: value for label, value in row.items()}
        for screen, row in load_ground_truth(str(csv_path)).items()
    }


def test_list_truth_changes_with_column_visibility(practice: dict, tmp_path: Path) -> None:
    truth = loaded(practice, tmp_path)
    assert truth["screen 1"]["ndg"] == "09000001"
    assert truth["screen 1"]["creazione"] == "10/02/2025"
    assert "tipo" not in truth["screen 1"]
    assert truth["screen 2"]["denominazione"] == practice["name"]
    assert "fase" not in truth["screen 2"]
    # The DOM audit (audit_truth.cjs) shows the Creazione column at the middle scroll, as the reference's truth does.
    assert truth["screen 2"]["creazione"] == "10/02/2025"
    # At the end of the scroll the identity columns have moved left: the NDG is gone. The list sizes Denom. to the name
    # (spec 19.3), and a name of 97 px is still whole there (audit_truth.cjs); a wider one is not (tests below).
    assert "ndg" not in truth["screen 3"]
    assert truth["screen 3"]["denominazione"] == practice["name"]
    assert truth["screen 3"]["tooltip_evidenze_b"] == practice["evidenceTooltip"]


def test_the_b_tooltip_is_asserted_when_b_is_one_of_several_evidence_codes(practice: dict, tmp_path: Path) -> None:
    # The archive lists codes side by side ("B V"); the tooltip shown is the one of the B code.
    practice["evidence"] = "B V"
    assert loaded(practice, tmp_path)["screen 3"]["tooltip_evidenze_b"] == practice["evidenceTooltip"]


def test_absent_subject_slots_are_explicitly_empty(practice: dict, tmp_path: Path) -> None:
    subjects = loaded(practice, tmp_path)["screen 4"]
    assert subjects["denominazione_1"] == practice["name"]
    assert subjects["ruolo_4"] == ""


def test_financial_fields_use_the_first_credit_line(practice: dict, tmp_path: Path) -> None:
    truth = loaded(practice, tmp_path)
    assert all(truth[f"screen {step}"]["importo_euro"] == "81.250,50" for step in range(5, 9))
    assert truth["screen 7"]["rapporto"] == "001 00000001"


def test_tooltip_follows_product_even_when_guarantees_change_position(practice: dict, tmp_path: Path) -> None:
    truth = loaded(practice, tmp_path)
    assert truth["screen 7"]["tooltip_descrizione_ipoteca"] == "55-IPOTECA DI PRIMO GRADO"
    assert not truth["screen 6"].get("tooltip_descrizione_m_consap")
    assert not truth["screen 8"].get("tooltip_descrizione_ipoteca")


def test_missing_tooltips_remove_only_their_capture_steps(practice: dict, tmp_path: Path) -> None:
    practice.update(evidence="", evidenceTooltip="", guarantees=[])
    practice["fidi"][0]["tooltip"] = " "
    assert available_steps(practice) == [1, 2, 4, 5, 9]
    assert set(loaded(practice, tmp_path)) == {"screen 1", "screen 2", "screen 4", "screen 5", "screen 9"}


def test_existing_evaluator_scores_notes_with_quotes_newlines_and_euros(practice: dict, tmp_path: Path) -> None:
    csv_path = tmp_path / "dati.csv"
    csv_path.write_bytes(practice_truth_csv(practice).encode("utf-8-sig"))
    truth = load_ground_truth(str(csv_path))
    assert truth["screen 9"]["Note della richiesta"] == practice["notes"]
    prediction = {"screen 9": {"fields": {"note_della_richiesta": {"value": practice["notes"]}}}}
    result = eval_outputs(prediction, truth)
    assert result["per_field_filt"]["note_della_richiesta"] == [1, 1]


LIST_NAMES = Path(__file__).resolve().parent / "fixtures" / "bper_profiles_list_names.json"


def list_name_profile(key: str) -> dict:
    return next(p for p in json.loads(LIST_NAMES.read_text(encoding="utf-8"))["profiles"] if p["key"] == key)


def test_a_list_name_just_narrower_than_its_cell_is_asserted_on_the_list(tmp_path: Path) -> None:
    # 126.06 px of the cell's 127 px (Chrome): it shows whole.
    profile = list_name_profile("fittizia-sotto")
    truth = loaded(profile, tmp_path)
    assert truth["screen 1"]["denominazione"] == truth["screen 2"]["denominazione"] == "ROCCAFORTE ROSALBA"


def test_a_list_name_just_wider_than_its_cell_is_left_out_of_the_list(tmp_path: Path) -> None:
    # 127.24 px: Chrome cuts it with an ellipsis, so the list states do not assert it; the detail header shows it whole.
    profile = list_name_profile("fittizia-sopra")
    truth = loaded(profile, tmp_path)
    assert "denominazione" not in truth["screen 1"] and "denominazione" not in truth["screen 2"]
    assert truth["screen 1"]["ndg"] == profile["ndg"]
    assert truth["screen 4"]["denominazione"] == "BELLAVISTA BENEDETTA"


# The list's columns follow their content (spec 19.3), so how far the identity columns have left at the end of the
# scroll (screen 3, 842 px) depends on the width of Denom.: the narrower it is, the longer they stay (list.js).
def test_a_name_narrower_than_its_label_stays_on_screen_3_with_the_ndg(practice: dict, tmp_path: Path) -> None:
    practice["name"] = "NERI ADA"  # 52 px: the column keeps the width of its label
    truth = loaded(practice, tmp_path)
    assert truth["screen 3"]["ndg"] == "09000001"
    assert truth["screen 3"]["denominazione"] == "NERI ADA"


def test_a_cut_name_leaves_only_its_ndg_on_screen_3(tmp_path: Path) -> None:
    # The cut name does not widen the column: the NDG stays whole, the name is cut. Without the other Evidenze marks an
    # invented practice may draw (this one draws four, which take the NDG off too: test_marks_that_widen_...).
    profile = {**list_name_profile("fittizia-sopra"), "role": None}
    truth = loaded(profile, tmp_path)
    assert truth["screen 3"]["ndg"] == profile["ndg"]
    assert "denominazione" not in truth["screen 3"]


def test_a_name_nearly_as_wide_as_the_cell_leaves_screen_3_with_its_ndg(tmp_path: Path) -> None:
    # 126 px, like the reference practice's name: both identity values have left the list (reference screen 3).
    truth = loaded(list_name_profile("fittizia-sotto"), tmp_path)
    assert "ndg" not in truth["screen 3"] and "denominazione" not in truth["screen 3"]


def test_a_checkbox_takes_a_name_off_screen_3_sooner(practice: dict, tmp_path: Path) -> None:
    # 100 px: a LAV row still shows it at the end of the scroll; an APP or ABB row's checkbox widens NDG by 21.7 px
    # (list.js), and the name leaves with the identity columns.
    practice["name"] = "FERRARI ANTONIO"
    assert loaded({**practice, "state": "LAV"}, tmp_path)["screen 3"]["denominazione"] == "FERRARI ANTONIO"
    assert "denominazione" not in loaded({**practice, "state": "APP"}, tmp_path)["screen 3"]
    assert "denominazione" not in loaded({**practice, "state": "ABB"}, tmp_path)["screen 3"]


def test_an_invented_practice_counts_the_marks_its_list_cell_draws() -> None:
    # list.js draws sim-029's cell as clip, note bubble, B, diamond, loop arrow, pink P (bper_directory.cjs pins the
    # same); an archive practice shows its codes alone.
    assert evidence_slots({"key": "sim-029", "role": "sintetica", "evidence": "B"}) == 6
    assert evidence_slots({"key": "sim-029", "role": "addestramento", "evidence": "B V"}) == 2
    assert evidence_slots({"key": "sim-029", "evidence": ""}) == 0
    # At most six, the most a calibration row shows: gen2-024 would draw seven.
    assert evidence_slots({"key": "gen2-024", "role": "sintetica", "evidence": "B V"}) == 6


def test_marks_that_widen_evidenze_take_a_name_off_screen_3_sooner(practice: dict, tmp_path: Path) -> None:
    # Six marks need more than the Evidenze label's width: the table grows and the name leaves at the end of the scroll.
    practice["name"] = "FERRARI ANTONIO"
    assert loaded(practice, tmp_path)["screen 3"]["denominazione"] == "FERRARI ANTONIO"
    assert "denominazione" not in loaded({**practice, "key": "sim-029", "role": "sintetica"}, tmp_path)["screen 3"]


def test_marks_that_widen_evidenze_cover_creazione_on_screen_1(practice: dict, tmp_path: Path) -> None:
    # At the capture window's start offset Creazione ends close to the pinned Evidenze: beside a 110 px name, a cell of
    # six marks covers it.
    practice["name"] = "CONTI ALESSANDRA"
    assert loaded(practice, tmp_path)["screen 1"]["creazione"] == "10/02/2025"
    assert "creazione" not in loaded({**practice, "key": "sim-029", "role": "sintetica"}, tmp_path)["screen 1"]


def test_a_request_note_too_long_for_the_page_is_not_asserted_on_screen_9(practice: dict, tmp_path: Path) -> None:
    # 26 lines of about 135 characters fit above the bottom of the detail window; this note needs about 37.
    practice["notes"] = "Nota della richiesta molto lunga, " * 150
    truth = loaded(practice, tmp_path)
    assert "note_della_richiesta" not in truth["screen 9"]
    assert truth["screen 9"]["ndg"] == "09000001"


def test_a_request_note_that_fits_the_page_is_asserted_on_screen_9(practice: dict, tmp_path: Path) -> None:
    practice["notes"] = "Nota della richiesta, " * 120  # about 20 lines
    assert loaded(practice, tmp_path)["screen 9"]["note_della_richiesta"] == practice["notes"].strip()


def test_scheda_states_scroll_the_note_box_one_paragraph_at_a_time() -> None:
    states = scheda_states(scheda_with("Primo.\n\nSecondo.\n\nTerzo.\n\nQuarto.\n"))
    assert [(s["name"], s["scroll"], s["noteScroll"]) for s in states] == [
        ("scheda-privati-01", 0, 0), ("scheda-privati-02", 662, 0),
        ("scheda-privati-03", 662, 40), ("scheda-privati-04", 662, 77),
    ]


@pytest.mark.parametrize("note", ["Unico paragrafo.\n", "Primo.\n\nSecondo.\n", ""])
def test_a_note_that_fits_the_box_needs_one_bottom_state(note: str) -> None:
    assert [s["name"] for s in scheda_states(scheda_with(note))] == ["scheda-privati-01", "scheda-privati-02"]


def test_scheda_truth_lists_only_the_fields_visible_in_each_state(practice: dict, tmp_path: Path) -> None:
    practice["scheda"] = scheda_with("Primo.\n\nSecondo.\n\nTerzo.\n")
    truth = loaded(practice, tmp_path)
    assert set(truth["scheda-privati-01"]) == TOP_FIELDS
    assert truth["scheda-privati-01"]["ndg"] == "09000001"
    assert truth["scheda-privati-01"]["dal"] == "MARZO 2019"
    for state in ("scheda-privati-02", "scheda-privati-03"):
        assert set(truth[state]) == BOTTOM_FIELDS
        assert truth[state]["datore_di_lavoro_anagrafica"] == "COMUNE DI PROVA"
    assert truth["scheda-privati-02"]["note_scheda_privati"] == "Primo.\n\nSecondo."
    assert truth["scheda-privati-03"]["note_scheda_privati"] == "Secondo.\n\nTerzo."
    assert "scheda-privati-04" not in truth


def test_the_note_box_scrolls_past_leading_blank_lines(practice: dict, tmp_path: Path) -> None:
    # The reference note starts with two blank lines and has no trailing newline.
    practice["scheda"] = scheda_with("\n\nPrimo.\n\nSecondo.\n\nTerzo.")
    assert [s["noteScroll"] for s in scheda_states(practice["scheda"])] == [0, 40, 56]
    truth = loaded(practice, tmp_path)
    assert truth["scheda-privati-02"]["note_scheda_privati"] == "Primo.\n\nSecondo."
    assert truth["scheda-privati-03"]["note_scheda_privati"] == "Secondo.\n\nTerzo."


# Only the number of rows moves the states; the values of a row never do.
OUTGOING = {"description": "PRESTITO AL CONSUMO", "annualAmount": "2.000", "due": "MARZO 2028", "residual": "5.000"}


@pytest.mark.parametrize(("rows", "scroll", "employer"), [
    (0, 662, {"datore_di_lavoro_anagrafica", "rating_ufficiale", "score_cgs"}),
    (1, 752, {"rating_ufficiale", "score_cgs"}),
    (2, 842, set()),
])
def test_bottom_states_drop_the_employer_fields_the_rows_push_out(practice: dict, tmp_path: Path, rows: int,
                                                                   scroll: int, employer: set[str]) -> None:
    # Each row lengthens the page by 90 px and the bottom states scroll as much further, so the family block and the
    # note box stay where they were; an employer value box pushed above the viewport leaves the truth. No rows: the
    # states and truth of before the rows existed.
    practice["scheda"] = scheda_with("Primo.\n\nSecondo.\n\nTerzo.\n", (OUTGOING,) * rows)
    assert [(s["name"], s["scroll"], s["noteScroll"]) for s in scheda_states(practice["scheda"])] == [
        ("scheda-privati-01", 0, 0), ("scheda-privati-02", scroll, 0), ("scheda-privati-03", scroll, 35)]
    truth = loaded(practice, tmp_path)
    household_and_note = {"nr_altri_componenti_nucleo", "di_cui_percepiscono_reddito", "importo_totale_annuo_nucleo",
                          "note_scheda_privati"}
    assert set(truth["scheda-privati-02"]) == set(truth["scheda-privati-03"]) == employer | household_and_note


def test_adding_a_scheda_leaves_the_screen_rows_unchanged(practice: dict) -> None:
    screens = practice_truth_csv(practice)
    practice["scheda"] = scheda_with("Primo.\n")
    combined = practice_truth_csv(practice)
    assert combined.startswith(screens)
    assert combined[len(screens):].startswith("scheda-privati-01,")


def test_scheda_state_ids_are_the_png_stems_the_evaluator_joins_on(practice: dict, tmp_path: Path) -> None:
    practice["scheda"] = scheda_with("Primo.\n\nSecondo.\n\nTerzo.\n")
    csv_path = tmp_path / "dati.csv"
    csv_path.write_bytes(practice_truth_csv(practice).encode("utf-8-sig"))
    truth = load_ground_truth(str(csv_path))
    pngs = [f"cartella/{state['name']}.png" for state in scheda_states(practice["scheda"])]
    assert {screen_id_from_path(png) for png in pngs} == {key for key in truth if key.startswith("scheda-")}


def practice_rows(practice: dict) -> list[dict[str, str]]:
    return list(csv.DictReader(StringIO(practice_truth_record_csv(practice), newline=""), delimiter=";"))


PEF_KEYS = [key for key in CSV_LABELS if key not in SCHEDA_FIELDS]


def test_practice_truth_has_one_row_per_field_in_the_canonical_order(practice: dict) -> None:
    rows = practice_rows(practice)
    assert list(rows[0]) == ["Chiave", "Campo", "Valore"]
    assert [row["Chiave"] for row in rows] == PEF_KEYS
    assert all(row["Campo"] == CSV_LABELS[row["Chiave"]] for row in rows)


def test_practice_truth_holds_the_values_of_the_practice(practice: dict) -> None:
    values = {row["Chiave"]: row["Valore"] for row in practice_rows(practice)}
    assert (values["ndg"], values["denominazione"], values["tipo"]) == ("09000001", "D'ARCO MARTINA", "BPI Mutui")
    assert (values["n_fido"], values["importo_euro"]) == ("F1", "81.250,50")  # the first credit line
    assert values["filiale_relazione"] == "9901 - FILIALE SINTETICA"
    assert values["note_della_richiesta"] == practice["notes"]
    assert values["tooltip_evidenze_b"] == "Origination BSTORE"
    assert values["tooltip_descrizione_ipoteca"] == "55-IPOTECA DI PRIMO GRADO"
    assert (values["ndg_1"], values["ruolo_1"], values["ndg_2"]) == ("09000001", "Richiedente", "")


def test_practice_truth_adds_the_13_scheda_fields_when_there_is_a_scheda(practice: dict) -> None:
    practice["scheda"] = scheda_with("Primo.\n\nSecondo.\n")
    values = {row["Chiave"]: row["Valore"] for row in practice_rows(practice)}
    assert list(values) == list(CSV_LABELS)
    assert values["dal"] == "MARZO 2019" and values["note_scheda_privati"] == "Primo.\n\nSecondo."


def test_practice_truth_lists_only_the_fields_its_source_states(practice: dict) -> None:
    # An archive practice states only what its screenshots showed; the rest is unknown, not empty.
    practice["provenance"] = {"source": "archivio", "filler": [], "stated": ["ndg", "stato", "ndg_2"]}
    assert [(row["Chiave"], row["Valore"]) for row in practice_rows(practice)] == [
        ("ndg", "09000001"), ("stato", "LAV"), ("ndg_2", "")]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def screen_digests(practice: dict) -> dict[str, str]:
    """The digests of SNAPSHOT for the screen rows of one practice, without its Scheda Privati."""
    text = practice_truth_csv({**practice, "scheda": None})
    rows = list(csv.reader(StringIO(text, newline="")))
    note = next(row[2] for row in rows if tuple(row[:2]) == NOTE_ROW)
    return {
        "screens": sha(text),
        "rows_except_note": sha(json.dumps([row for row in rows if tuple(row[:2]) != NOTE_ROW], ensure_ascii=False)),
        "note_except_applicant": sha(APPLICANT.sub("", note, count=1)),
    }


@pytest.fixture(scope="module")
def digests() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    before = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["practices"]
    return before, {p["key"]: screen_digests(p) for p in synthetic_practices()}


def test_only_the_pensioner_practices_change_their_screen_rows(digests: tuple) -> None:
    before, now = digests
    assert now.keys() == before.keys()
    assert {key for key in now if now[key]["screens"] != before[key]["screens"]} == PENSIONERS


def test_a_pensioner_practice_changes_only_the_applicant_sentence_of_its_request_note(digests: tuple) -> None:
    before, now = digests
    for key in now:
        assert now[key]["rows_except_note"] == before[key]["rows_except_note"], key
        assert now[key]["note_except_applicant"] == before[key]["note_except_applicant"], key


def test_note_box_geometry_matches_the_frozen_stylesheet() -> None:
    rule = re.search(r"\.sp-notes textarea \{([^}]*)\}", STYLESHEET.read_text(encoding="utf-8")).group(1)
    assert f"height: {NOTE_BOX_PX}px;" in rule
    assert f"padding: {NOTE_PADDING_PX}px 0 0 5px;" in rule
    assert "border-bottom: 1px solid" in rule
    assert re.search(rf"font: [\d.]+px/{NOTE_LINE_PX}px", rule)


def test_outgoing_row_geometry_matches_the_frozen_stylesheet() -> None:
    css = STYLESHEET.read_text(encoding="utf-8")
    row, rows = re.search(r"\.sp-outgoing \{([^}]*)\}", css), re.search(r"\.sp-outgoings \{([^}]*)\}", css)
    assert row and rows, "the .sp-outgoing and .sp-outgoings rules"
    assert f"height: {OUTGOING_ROW_PX}px;" in row.group(1)
    # A margin or padding would lengthen the page by more than OUTGOING_ROW_PX a row.
    for rule in (row.group(1), rows.group(1)):
        for declaration in filter(str.strip, rule.split(";")):
            name, _, value = declaration.partition(":")
            if name.strip().startswith(("margin", "padding")):
                assert re.fullmatch(r"0(px)?( 0(px)?)*", value.strip()), declaration
