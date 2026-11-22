"""Evaluator-facing CSV from the single-practice website, at its native viewport."""
from pathlib import Path

import pytest

from extraction.evaluation import eval_outputs, load_ground_truth
from extraction.fields import CSV_TO_SCHEMA
from bper_simulator_truth import available_steps, practice_truth_csv


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
    assert "creazione" not in truth["screen 2"]
    assert "ndg" not in truth["screen 3"]
    assert "denominazione" not in truth["screen 3"]
    assert truth["screen 3"]["tooltip_evidenze_b"] == practice["evidenceTooltip"]


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
