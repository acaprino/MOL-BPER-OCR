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
    path = _review(tmp_path, [["1", "1__Elenco", "Evidenze", "B P", "B", "Corretto"]])
    records = read_reviewed_truth(path, {"Evidenze": "evidenze"})
    assert records[0]["value"] == "B"


def test_preserves_literal_not_available_label(tmp_path: Path) -> None:
    path = _review(tmp_path, [["1", "1__Scheda", "SCORE CGS", "N/D", "N/D", "Confermato"]])
    assert read_reviewed_truth(path, {"SCORE CGS": "score_cgs"})[0]["value"] == "N/D"


def test_rejects_pending_review(tmp_path: Path) -> None:
    path = _review(tmp_path, [["1", "1__Soggetti", "NDG 4", "(vuoto)", None, "Da confermare"]])
    with pytest.raises(ValueError, match="confermat|complet|revis"):
        read_reviewed_truth(path, {"NDG 4": "ndg_4"})


def test_accepts_review_confirmed_by_named_reviewer(tmp_path: Path) -> None:
    path = _review(tmp_path, [["1", "1__Elenco", "NDG", "123", "123", "Confermato da Rossi"]])
    assert read_reviewed_truth(path, {"NDG": "ndg"})[0]["reviewer_status"] == "Confermato da Rossi"


def test_accepts_review_corrected_by_named_reviewer(tmp_path: Path) -> None:
    path = _review(tmp_path, [["1", "1__Elenco", "NDG", "123", "999", "Corretto da Rossi"]])
    assert read_reviewed_truth(path, {"NDG": "ndg"})[0]["value"] == "999"


def test_rejects_duplicate_field_in_same_screenshot(tmp_path: Path) -> None:
    row = ["1", "1__Elenco", "NDG", "123", "123", "Confermato"]
    with pytest.raises(ValueError, match="duplic"):
        read_reviewed_truth(_review(tmp_path, [row, row]), {"NDG": "ndg"})


def test_rejects_formula_as_ground_truth(tmp_path: Path) -> None:
    path = _review(tmp_path, [["1", "1__Elenco", "NDG", "123", "=1+2", "Confermato"]])
    with pytest.raises(ValueError, match="formul"):
        read_reviewed_truth(path, {"NDG": "ndg"})


def test_rejects_mismatched_practice_metadata(tmp_path: Path) -> None:
    path = _review(tmp_path, [["2", "1__Elenco", "NDG", "123", "123", "Confermato"]])
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


def test_resolves_screenshot_from_per_practice_folder(tmp_path: Path) -> None:
    from training.dataset import resolve_screenshot_path

    practice_dir = tmp_path / "pratiche" / "51185037"
    practice_dir.mkdir(parents=True)
    expected = practice_dir / "Elenco.png"
    expected.write_bytes(b"png")
    assert resolve_screenshot_path(tmp_path, "51185037__Elenco") == expected



# ============================================================
# Transcribed lots (the 2026-08-21 protocol: Trascrizione + Esito)
# ============================================================


def _transcribed(tmp_path: Path, rows: list[list[object]], corrections: list[dict] | None = None) -> tuple[Path, Path | None]:
    import hashlib
    import json

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Revisione"
    sheet.append(["N.", "Pratica", "Schermata completa", "Campo", "Valore da leggere", "Trascrizione", "Esito", "Note",
                  "ID schermata"])
    for number, row in enumerate(rows, 1):
        practice, screen, display, text, outcome = row
        sheet.append([number, practice, screen.split("__", 1)[1] + ".png", display, None, text, outcome, None, screen])
    path = tmp_path / "lotto.xlsx"
    workbook.save(path)
    if corrections is None:
        return path, None
    fixes = tmp_path / "correzioni.json"
    fixes.write_text(json.dumps({"workbook": path.name, "workbook_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                 "correzioni": corrections}), encoding="utf-8")
    return path, fixes


def test_transcribed_value_becomes_the_truth(tmp_path: Path) -> None:
    from training.dataset import read_transcribed_truth

    path, _ = _transcribed(tmp_path, [["1", "1__Elenco", "NDG", "123", "TRASCRITTO"]])
    record = read_transcribed_truth(path, mapping={"NDG": "ndg"})[0]
    assert (record["value"], record["outcome"], record["field"], record["practice"]) == ("123", "TRASCRITTO", "ndg", "1")


def test_empty_and_not_visible_outcomes_are_absences(tmp_path: Path) -> None:
    from training.dataset import read_transcribed_truth

    path, _ = _transcribed(tmp_path, [["1", "1__Elenco", "NDG", None, "VUOTO"],
                                      ["1", "1__Elenco", "Tipo", None, "NON VISIBILE"]])
    records = read_transcribed_truth(path, mapping={"NDG": "ndg", "Tipo": "tipo"})
    assert [(r["value"], r["outcome"]) for r in records] == [(None, "VUOTO"), (None, "NON VISIBILE")]


def test_partial_transcription_keeps_its_text_and_outcome(tmp_path: Path) -> None:
    from training.dataset import read_transcribed_truth

    path, _ = _transcribed(tmp_path, [["1", "1__Fidi", "Descrizione", "M.CONSAP >80", "PARZIALE"]])
    record = read_transcribed_truth(path, mapping={"Descrizione": "descrizione"})[0]
    assert (record["value"], record["outcome"]) == ("M.CONSAP >80", "PARZIALE")


def test_rejects_unknown_outcome(tmp_path: Path) -> None:
    from training.dataset import read_transcribed_truth

    path, _ = _transcribed(tmp_path, [["1", "1__Elenco", "NDG", "123", "FORSE"]])
    with pytest.raises(ValueError, match="[Ee]sito"):
        read_transcribed_truth(path, mapping={"NDG": "ndg"})


def test_rejects_transcription_without_text(tmp_path: Path) -> None:
    from training.dataset import read_transcribed_truth

    path, _ = _transcribed(tmp_path, [["1", "1__Elenco", "NDG", None, "TRASCRITTO"]])
    with pytest.raises(ValueError, match="incoer"):
        read_transcribed_truth(path, mapping={"NDG": "ndg"})


def test_applies_recorded_correction_and_keeps_the_original(tmp_path: Path) -> None:
    from training.dataset import read_transcribed_truth

    fix = {"riga_excel": 2, "schermata": "1__Tooltip", "campo": "NDG", "field_key": "ndg",
           "revisione": {"esito": "VUOTO", "trascrizione": None}, "corretto": {"esito": "NON VISIBILE", "trascrizione": None}}
    path, fixes = _transcribed(tmp_path, [["1", "1__Tooltip", "NDG", None, "VUOTO"]], [fix])
    record = read_transcribed_truth(path, fixes, mapping={"NDG": "ndg"})[0]
    assert (record["value"], record["outcome"]) == (None, "NON VISIBILE")
    assert record["correction"]["revisione"]["esito"] == "VUOTO"


def test_refuses_corrections_recorded_for_another_workbook(tmp_path: Path) -> None:
    from training.dataset import read_transcribed_truth

    path, fixes = _transcribed(tmp_path, [["1", "1__Tooltip", "NDG", None, "VUOTO"]], [])
    other, _ = _transcribed(tmp_path / "other", [["1", "1__Tooltip", "NDG", "9", "TRASCRITTO"]]) if (tmp_path / "other").mkdir() is None else (None, None)
    with pytest.raises(ValueError, match="workbook"):
        read_transcribed_truth(other, fixes, mapping={"NDG": "ndg"})


def test_refuses_correction_that_does_not_match_the_reviewed_row(tmp_path: Path) -> None:
    from training.dataset import read_transcribed_truth

    fix = {"riga_excel": 2, "schermata": "1__Tooltip", "campo": "NDG", "field_key": "ndg",
           "revisione": {"esito": "TRASCRITTO", "trascrizione": "5"}, "corretto": {"esito": "NON VISIBILE", "trascrizione": None}}
    path, fixes = _transcribed(tmp_path, [["1", "1__Tooltip", "NDG", None, "VUOTO"]], [fix])
    with pytest.raises(ValueError, match="correzione"):
        read_transcribed_truth(path, fixes, mapping={"NDG": "ndg"})


def test_records_subject_overlap_between_training_and_extended_validation() -> None:
    examples = [{"id": "1__A", "practice": "1", "split": "train", "values": {"ndg_2": "11153238"}, "image_sha256": "a"},
                {"id": "2__B", "practice": "2", "split": "val_ext", "values": {"ndg_2": "11153238"}, "image_sha256": "b"}]
    audit = audit_splits(examples)
    assert audit["status"] == "passed"
    assert audit["recorded_overlaps"] == [{"tipo": "NDG", "valore": "11153238", "split": ["train", "val_ext"]}]


# ============================================================
# Bundles: one truth table over every reviewed lot, examples only where OCR is allowed
# ============================================================

V3_1 = ["51185037", "52062600", "52067184", "52068422", "52080223", "52102599", "52130861", "52135039",
        "51659595", "52126316", "51531667", "52060489"]
BOX = [[10, 10], [40, 10], [40, 30], [10, 30]]


def _png(path: Path, shade: int) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (200, 100), (shade, shade, shade)).save(path)


def _digests(path: Path) -> dict[str, str]:
    import hashlib

    from PIL import Image

    with Image.open(path) as image:
        pixels = image.convert("RGB").tobytes()
    return {"path": path.as_posix(), "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "pixel_sha256": hashlib.sha256(pixels).hexdigest()}


def _corpus(tmp_path: Path, sealed_ocr: bool = False):
    """Twelve v3.1 practices plus a lot with one extended-validation and one sealed practice."""
    import json

    from training.dataset import Lot

    shots = tmp_path / "pratiche"
    for shade, practice in enumerate(V3_1 + ["60000001", "60000002"], 1):
        _png(shots / practice / "Elenco.png", shade)
    workbook = _review(tmp_path, [[p, f"{p}__Elenco", "NDG", p, p, "Confermato"] for p in V3_1])
    ocr = tmp_path / "ocr.json"
    ocr.write_text(json.dumps({f"{p}__Elenco": {"items": [[p, 0.99, BOX]]} for p in V3_1}), encoding="utf-8")
    lot_dir = tmp_path / "lotto"
    lot_dir.mkdir()
    lot_workbook, _ = _transcribed(lot_dir, [["60000001", "60000001__Elenco", "NDG", "7", "TRASCRITTO"],
                                            ["60000001", "60000001__Elenco", "Tipo", "BPI Mut", "PARZIALE"],
                                            ["60000002", "60000002__Elenco", "NDG", "8", "TRASCRITTO"]])
    assignment = lot_dir / "g8_assegnazione.json"
    assignment.write_text(json.dumps({"lotto": "lotto-2026-08-21",
                                      "gruppi": {"validazione_estesa": ["60000001"], "conferma": ["60000002"]},
                                      "schermate": {f"{p}__Elenco": _digests(shots / p / "Elenco.png")
                                                    for p in ("60000001", "60000002")}}), encoding="utf-8")
    lot_ocr = lot_dir / "ocr.json"
    read = ["60000001__Elenco"] + (["60000002__Elenco"] if sealed_ocr else [])
    lot_ocr.write_text(json.dumps({s: {"items": [["7", 0.99, BOX]]} for s in read}), encoding="utf-8")
    return workbook, shots, ocr, Lot(lot_workbook, assignment, None, lot_ocr)


def _csv_rows(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=";"))


def test_single_workbook_bundle_stays_v3_1(tmp_path: Path) -> None:
    from training.dataset import build_dataset

    workbook, shots, ocr, _ = _corpus(tmp_path)
    manifest = build_dataset(workbook, shots, ocr, tmp_path / "out")
    assert manifest["dataset_version"] == "ground-truth-v3.1"
    assert list(_csv_rows(tmp_path / "out" / "ground_truth.csv")[0])[:3] == ["Fotogramma", "Denominazione da attribuire",
                                                                                "Valore rilevato"]


def test_lot_bundle_is_v3_2_with_examples_only_outside_the_sealed_group(tmp_path: Path) -> None:
    import json

    from training.dataset import build_dataset

    workbook, shots, ocr, lot = _corpus(tmp_path)
    manifest = build_dataset(workbook, shots, ocr, tmp_path / "out", lots=[lot])
    examples = json.loads((tmp_path / "out" / "examples.json").read_text(encoding="utf-8"))
    assert manifest["dataset_version"] == "ground-truth-v3.2"
    assert {e["id"]: e["split"] for e in examples if e["practice"].startswith("6")} == {"60000001__Elenco": "val_ext"}
    assert manifest["practice_splits"]["conferma"] == ["60000002"]
    assert manifest["truth_counts"] == {"rows": 15, "screens": 14, "practices": 14}


def test_partial_transcription_is_in_the_truth_but_not_a_target(tmp_path: Path) -> None:
    import json

    from training.dataset import build_dataset

    workbook, shots, ocr, lot = _corpus(tmp_path)
    build_dataset(workbook, shots, ocr, tmp_path / "out", lots=[lot])
    example = next(e for e in json.loads((tmp_path / "out" / "examples.json").read_text(encoding="utf-8"))
                   if e["id"] == "60000001__Elenco")
    assert example["values"] == {"ndg": "7"}
    rows = {(r["Fotogramma"], r["Denominazione da attribuire"]): r for r in _csv_rows(tmp_path / "out" / "ground_truth.csv")}
    assert rows[("60000001__Elenco", "Tipo")]["Esito"] == "PARZIALE"
    assert rows[("60000002__Elenco", "NDG")]["Gruppo"] == "conferma"


def test_sealed_screens_are_listed_without_examples(tmp_path: Path) -> None:
    from training.dataset import build_dataset

    workbook, shots, ocr, lot = _corpus(tmp_path)
    build_dataset(workbook, shots, ocr, tmp_path / "out", lots=[lot])
    screens = {r["Schermata"]: r for r in _csv_rows(tmp_path / "out" / "screens.csv")}
    assert (screens["60000002__Elenco"]["Gruppo"], screens["60000002__Elenco"]["Esempio"]) == ("conferma", "no")
    assert screens["60000002__Elenco"]["SHA256 immagine"] == _digests(shots / "60000002" / "Elenco.png")["image_sha256"]
    assert screens["60000001__Elenco"]["Esempio"] == "sì"


def test_refuses_ocr_of_a_sealed_screen(tmp_path: Path) -> None:
    from training.dataset import build_dataset

    workbook, shots, ocr, lot = _corpus(tmp_path, sealed_ocr=True)
    with pytest.raises(ValueError, match="sigillat"):
        build_dataset(workbook, shots, ocr, tmp_path / "out", lots=[lot])


def test_rejects_subject_shared_by_extended_validation_and_sealed_group() -> None:
    examples = [{"id": "1__A", "practice": "1", "split": "val_ext", "values": {"ndg_2": "123"}, "image_sha256": "a"},
                {"id": "2__B", "practice": "2", "split": "conferma", "values": {"ndg_1": "123"}, "image_sha256": "b"}]
    with pytest.raises(ValueError, match="NDG"):
        audit_splits(examples)
