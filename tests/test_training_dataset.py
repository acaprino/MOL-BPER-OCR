from pathlib import Path

import pytest
from openpyxl import Workbook

from training.dataset import apply_supervision, audit_splits, read_reviewed_truth


def _review(tmp_path: Path, rows: list[list[object]]) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Revisione"
    sheet.append(["Pratica", "ID schermata", "Campo", "Valore letto", "Valore aggiornato v3.1", "Stato v3.1"])
    for row in rows:
        sheet.append(row)
    path = tmp_path / "review.xlsx"
    workbook.save(path)
    return path


def test_uses_reviewed_value_instead_of_original(tmp_path: Path) -> None:
    path = _review(tmp_path, [["1", "1__Elenco", "Evidenze", "B P", "B", "Corretto da Rita"]])
    records = read_reviewed_truth(path, {"Evidenze": "evidenze"})
    assert records[0]["value"] == "B"


def test_preserves_literal_not_available_label(tmp_path: Path) -> None:
    path = _review(tmp_path, [["1", "1__Scheda", "SCORE CGS", "N/D", "N/D", "Confermato da Rita"]])
    assert read_reviewed_truth(path, {"SCORE CGS": "score_cgs"})[0]["value"] == "N/D"


def test_rejects_pending_review(tmp_path: Path) -> None:
    path = _review(tmp_path, [["1", "1__Soggetti", "NDG 4", "(vuoto)", None, "Da confermare"]])
    with pytest.raises(ValueError, match="confermat|complet|revis"):
        read_reviewed_truth(path, {"NDG 4": "ndg_4"})


def test_rejects_duplicate_field_in_same_screenshot(tmp_path: Path) -> None:
    row = ["1", "1__Elenco", "NDG", "123", "123", "Confermato da Rita"]
    with pytest.raises(ValueError, match="duplic"):
        read_reviewed_truth(_review(tmp_path, [row, row]), {"NDG": "ndg"})


def test_rejects_formula_as_ground_truth(tmp_path: Path) -> None:
    path = _review(tmp_path, [["1", "1__Elenco", "NDG", "123", "=1+2", "Confermato da Rita"]])
    with pytest.raises(ValueError, match="formul"):
        read_reviewed_truth(path, {"NDG": "ndg"})


def test_rejects_mismatched_practice_metadata(tmp_path: Path) -> None:
    path = _review(tmp_path, [["2", "1__Elenco", "NDG", "123", "123", "Confermato da Rita"]])
    with pytest.raises(ValueError, match="pratic"):
        read_reviewed_truth(path, {"NDG": "ndg"})


def test_masks_misread_ocr_without_rewriting_input() -> None:
    words = [{"text": "21310980", "x0": 0, "y0": 0, "x1": 80, "y1": 10, "fitted": True}]
    alignments = {"NDG": {"indices": [0], "bbox": (0, 0, 80, 10), "status": "aligned", "exact_text": False}}
    labels, _ = apply_supervision(words, alignments, {"NDG": "ndg"})
    assert labels == ["IGNORE"]
    assert words[0]["text"] == "21310980"


def test_masks_unlocated_positive_instead_of_teaching_background() -> None:
    words = [{"text": "unknown", "x0": 0, "y0": 0, "x1": 80, "y1": 10, "fitted": True}]
    alignments = {"NDG": {"indices": [], "bbox": None, "status": "unresolved", "exact_text": False}}
    assert apply_supervision(words, alignments, {"NDG": "ndg"})[0] == ["IGNORE"]


def test_conflicting_positive_labels_are_masked() -> None:
    words = [{"text": "123", "x0": 0, "y0": 0, "x1": 30, "y1": 10, "fitted": True}]
    alignment = {"indices": [0], "bbox": (0, 0, 30, 10), "status": "aligned", "exact_text": True}
    labels, _ = apply_supervision(words, {"NDG": alignment, "NDG 1": alignment}, {"NDG": "ndg", "NDG 1": "sogg_ndg"})
    assert labels == ["IGNORE"]


def test_supervises_only_verified_words_of_partially_read_note() -> None:
    words = [{"text": text, "x0": index*30, "y0": 0, "x1": index*30+20, "y1": 10, "fitted": True}
             for index, text in enumerate(["richiesta", "import0", "euro"])]
    alignment = {"indices": [0, 1, 2], "verified_indices": [0, 2], "bbox": (0, 0, 80, 10),
                 "status": "aligned", "exact_text": False}
    labels, states = apply_supervision(words, {"Note della richiesta": alignment},
                                      {"Note della richiesta": "note_della_richiesta"})
    assert labels == ["note_della_richiesta", "IGNORE", "note_della_richiesta"]
    assert states["Note della richiesta"] == "partial_supervision"


def test_supervises_verified_validation_date_without_ocr_typo() -> None:
    words = [{"text": text, "x0": index*30, "y0": 0, "x1": index*30+20, "y1": 10, "fitted": True}
             for index, text in enumerate(["30/09/2026", "glorni"])]
    alignment = {"indices": [0, 1], "verified_indices": [0], "bbox": (0, 0, 50, 10),
                 "status": "aligned", "exact_text": False}
    labels, _ = apply_supervision(words, {"Ultima validazione scheda privati": alignment},
                                 {"Ultima validazione scheda privati": "ultima_validazione_scheda"})
    assert labels == ["ultima_validazione_scheda", "IGNORE"]


def test_rejects_same_practice_across_training_and_test() -> None:
    examples = [{"id": "1__A", "practice": "1", "split": "train", "values": {}, "image_sha256": "a"},
                {"id": "1__B", "practice": "1", "split": "test", "values": {}, "image_sha256": "b"}]
    with pytest.raises(ValueError, match="pratic"):
        audit_splits(examples)


def test_rejects_same_subject_identifier_across_splits() -> None:
    examples = [{"id": "1__A", "practice": "1", "split": "train", "values": {"ndg_2": "000123"}, "image_sha256": "a"},
                {"id": "2__B", "practice": "2", "split": "test", "values": {"ndg_3": "123"}, "image_sha256": "b"}]
    with pytest.raises(ValueError, match="NDG|identit"):
        audit_splits(examples)


def test_rejects_identical_image_across_splits() -> None:
    examples = [{"id": "1__A", "practice": "1", "split": "train", "values": {}, "image_sha256": "same"},
                {"id": "2__B", "practice": "2", "split": "test", "values": {}, "image_sha256": "same"}]
    with pytest.raises(ValueError, match="immagin|image"):
        audit_splits(examples)
