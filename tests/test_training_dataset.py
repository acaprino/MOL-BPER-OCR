"""The dataset builder: the archive in, supervised examples out, with the test practices left unread."""

import csv
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from training.dataset import (alignment_name, apply_supervision, audit_splits, build_dataset, ocr_screens, read_archive,
                              screen_id)

PRATICHE_HEAD = ["Pratica", "Ruolo", "Schermate", "Valori"]
SCHERMATE_HEAD = ["Schermata", "Pratica", "Pagina", "Numero", "Variante", "File", "SHA256", "Larghezza", "Altezza"]
VALORI_HEAD = ["Schermata", "Campo", "Chiave", "Valore", "Esito"]
BOX = [[10, 10], [40, 10], [40, 30], [10, 30]]


# ============================================================
# Supervision and split isolation
# ============================================================


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


# ============================================================
# The archive
# ============================================================


def _write(path: Path, head: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(head)
        writer.writerows(rows)


def _png(path: Path, shade: int) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (200, 100), (shade, shade, shade))
    for ink in ((14, 14, 34, 26), (56, 14, 104, 26)):
        ImageDraw.Draw(image).rectangle(ink, fill=(0, 0, 0))
    image.save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _archive(tmp_path: Path, roles: dict[str, str], values: list[list[str]] | None = None,
             screens: dict[str, list[tuple[str, str, str]]] | None = None) -> Path:
    """A miniature data/dataset: one `elenco-01` screen per practice unless `screens` says otherwise."""
    root = tmp_path / "dataset"
    root.mkdir()
    screens = screens or {practice: [("elenco-01", "elenco", "")] for practice in roles}
    rows = []
    for shade, (practice, entries) in enumerate(screens.items(), 1):
        for name, page, variant in entries:
            sha = _png(root / "pratiche" / practice / f"{name}.png", 200 + shade)
            rows.append([f"{practice}/{name}", practice, page, name[-2:], variant, f"pratiche/{practice}/{name}.png", sha, "200", "100"])
    if values is None:
        values = [[f"{practice}/elenco-01", "NDG", "ndg", practice, "TRASCRITTO"] for practice in roles]
    _write(root / "pratiche.csv", PRATICHE_HEAD, [[p, role, "1", "1"] for p, role in roles.items()])
    _write(root / "schermate.csv", SCHERMATE_HEAD, rows)
    _write(root / "valori.csv", VALORI_HEAD, values)
    return root


def _ocr(tmp_path: Path, words: dict[str, str]) -> Path:
    path = tmp_path / "ocr.json"
    path.write_text(json.dumps({screen: {"items": [[text, 0.99, BOX]]} for screen, text in words.items()}), encoding="utf-8")
    return path


ROLES = {"111": "addestramento", "222": "controllo", "333": "test"}


def test_the_archive_is_read_with_its_roles_and_screens(tmp_path: Path) -> None:
    archive = read_archive(_archive(tmp_path, ROLES))
    assert archive.roles == ROLES
    assert sorted(archive.screens) == ["111/elenco-01", "222/elenco-01", "333/elenco-01"]
    assert [(r["screen"], r["field"], r["value"]) for r in archive.records][0] == ("111__elenco-01", "ndg", "111")


def test_an_unknown_role_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Ruolo"):
        read_archive(_archive(tmp_path, {"111": "sigillata"}))


def test_a_changed_image_is_refused(tmp_path: Path) -> None:
    root = _archive(tmp_path, ROLES)
    _png(root / "pratiche" / "111" / "elenco-01.png", 250)
    with pytest.raises(ValueError, match="differisce"):
        read_archive(root)


def test_a_value_on_an_unknown_screen_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="sconosciuta"):
        read_archive(_archive(tmp_path, ROLES, [["111/soggetti-01", "NDG", "ndg", "1", "TRASCRITTO"]]))


@pytest.mark.parametrize("row", [["111/elenco-01", "NDG", "ndg", "", "TRASCRITTO"],
                                 ["111/elenco-01", "NDG", "ndg", "5", "VUOTO"],
                                 ["111/elenco-01", "NDG", "ndg", "5", "CHISSA"]])
def test_an_outcome_that_disagrees_with_its_value_is_refused(tmp_path: Path, row: list[str]) -> None:
    with pytest.raises(ValueError, match="Esito"):
        read_archive(_archive(tmp_path, ROLES, [row]))


def test_a_key_that_is_not_the_field_of_its_column_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Campo"):
        read_archive(_archive(tmp_path, ROLES, [["111/elenco-01", "NDG", "tipo", "1", "TRASCRITTO"]]))


def test_the_same_field_twice_on_a_screen_is_refused(tmp_path: Path) -> None:
    row = ["111/elenco-01", "NDG", "ndg", "1", "TRASCRITTO"]
    with pytest.raises(ValueError, match="duplicato"):
        read_archive(_archive(tmp_path, ROLES, [row, row]))


@pytest.mark.parametrize("page, variant, name", [("elenco", "", "elenco"), ("elenco", "destra", "elenco_dx"),
                                                 ("elenco", "tooltip", "elenco_tooltip"), ("soggetti", "", "soggetti"),
                                                 ("gestione-fidi", "", "gestionefidi"),
                                                 ("gestione-fidi", "basso", "gestionefidi_down"),
                                                 ("gestione-fidi", "tooltip", "gestionefidi_tooltip"),
                                                 ("note", "chiuso", "note"), ("scheda-privati", "", "scheda_privati")])
def test_the_aligner_reads_the_page_kind_from_page_and_variant(page: str, variant: str, name: str) -> None:
    assert alignment_name(page, variant) == name


def test_a_screen_id_has_no_slash() -> None:
    assert screen_id("51350695/elenco-01") == "51350695__elenco-01"


def test_ocr_screens_are_the_scored_ones_of_the_practices_that_may_be_read(tmp_path: Path) -> None:
    archive = read_archive(_archive(tmp_path, ROLES))
    assert ocr_screens(archive) == ["111__elenco-01", "222__elenco-01"]
    assert ocr_screens(archive, include_test=True) == ["111__elenco-01", "222__elenco-01", "333__elenco-01"]


# ============================================================
# The bundle
# ============================================================


def _bundle(tmp_path: Path, include_test: bool = False, values: list[list[str]] | None = None,
            words: dict[str, str] | None = None) -> dict:
    root = _archive(tmp_path, ROLES, values)
    words = words or {"111__elenco-01": "111", "222__elenco-01": "222", **({"333__elenco-01": "333"} if include_test else {})}
    return build_dataset(root, _ocr(tmp_path, words), tmp_path / "out", include_test)


def _examples(tmp_path: Path) -> list[dict]:
    return json.loads((tmp_path / "out" / "examples.json").read_text(encoding="utf-8"))


def test_the_roles_become_the_splits_and_the_test_practice_stays_unread(tmp_path: Path) -> None:
    manifest = _bundle(tmp_path)
    assert {e["id"]: e["split"] for e in _examples(tmp_path)} == {"111__elenco-01": "train", "222__elenco-01": "val"}
    assert manifest["practice_splits"] == {"train": ["111"], "val": ["222"], "test": ["333"]}
    assert manifest["dataset_version"] == "dataset" and manifest["include_test"] is False
    assert manifest["truth_counts"] == {"rows": 3, "screens": 3, "practices": 3}


def test_a_value_is_aligned_to_its_word_on_the_page_kind_of_its_screen(tmp_path: Path) -> None:
    roles = {"111": "addestramento", "222": "controllo"}
    values = [["111/soggetti-01", "NDG", "ndg", "70000011", "TRASCRITTO"], ["222/elenco-01", "NDG", "ndg", "222", "TRASCRITTO"]]
    root = _archive(tmp_path, roles, values, {"111": [("soggetti-01", "soggetti", "")], "222": [("elenco-01", "elenco", "")]})
    header = [["NDG:", 0.99, BOX], ["70000011", 0.99, [[50, 10], [120, 10], [120, 30], [50, 30]]]]
    ocr = tmp_path / "ocr.json"
    ocr.write_text(json.dumps({"111__soggetti-01": {"items": header}, "222__elenco-01": {"items": [["222", 0.99, BOX]]}}),
                   encoding="utf-8")
    build_dataset(root, ocr, tmp_path / "out")
    example = next(e for e in _examples(tmp_path) if e["id"] == "111__soggetti-01")
    assert example["values"] == {"ndg": "70000011"}
    assert dict(zip((w["text"] for w in example["words"]), example["labels"]))["70000011"] == "ndg"


def test_include_test_reads_the_test_practice_too(tmp_path: Path) -> None:
    manifest = _bundle(tmp_path, include_test=True)
    assert {e["split"] for e in _examples(tmp_path)} == {"train", "val", "test"}
    assert manifest["include_test"] is True


def test_an_ocr_reading_of_a_test_screen_is_refused_without_include_test(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="test"):
        _bundle(tmp_path, words={"111__elenco-01": "111", "222__elenco-01": "222", "333__elenco-01": "333"})


def test_a_scored_screen_without_an_ocr_reading_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non coincidono"):
        _bundle(tmp_path, words={"111__elenco-01": "111"})


def test_a_value_outside_the_vocabulary_is_not_a_target(tmp_path: Path) -> None:
    values = [["111/elenco-01", "NDG", "ndg", "111", "TRASCRITTO"], ["111/elenco-01", "Agente proponente", "", "Rossi", "TRASCRITTO"],
              ["222/elenco-01", "NDG", "ndg", "222", "TRASCRITTO"], ["333/elenco-01", "NDG", "ndg", "333", "TRASCRITTO"]]
    _bundle(tmp_path, values=values)
    assert _examples(tmp_path)[0]["values"] == {"ndg": "111"}


def test_a_partial_transcription_is_not_a_target(tmp_path: Path) -> None:
    values = [["111/elenco-01", "NDG", "ndg", "111", "TRASCRITTO"], ["111/elenco-01", "Tipo", "tipo", "BPI Mut", "PARZIALE"],
              ["222/elenco-01", "NDG", "ndg", "222", "TRASCRITTO"], ["333/elenco-01", "NDG", "ndg", "333", "TRASCRITTO"]]
    _bundle(tmp_path, values=values)
    assert _examples(tmp_path)[0]["values"] == {"ndg": "111"}


def test_a_derived_header_is_not_a_target(tmp_path: Path) -> None:
    values = [["111/elenco-01", "NDG", "ndg", "111", "DERIVATO"], ["111/elenco-01", "Tipo", "tipo", "BMM", "TRASCRITTO"],
              ["222/elenco-01", "NDG", "ndg", "222", "TRASCRITTO"], ["333/elenco-01", "NDG", "ndg", "333", "TRASCRITTO"]]
    _bundle(tmp_path, values=values, words={"111__elenco-01": "BMM", "222__elenco-01": "222"})
    assert "ndg" not in _examples(tmp_path)[0]["values"]


def test_the_same_subject_in_two_splits_is_refused(tmp_path: Path) -> None:
    values = [["111/elenco-01", "NDG", "ndg", "777", "TRASCRITTO"], ["222/elenco-01", "NDG", "ndg", "777", "TRASCRITTO"],
              ["333/elenco-01", "NDG", "ndg", "333", "TRASCRITTO"]]
    with pytest.raises(ValueError, match="Contaminazione"):
        _bundle(tmp_path, values=values, words={"111__elenco-01": "777", "222__elenco-01": "777"})


def test_the_bundle_is_sealed_and_accepted_by_the_trainer(tmp_path: Path) -> None:
    from training.model import validate_reviewed_dataset

    manifest = _bundle(tmp_path)
    roles = json.loads((tmp_path / "out" / "roles.json").read_text(encoding="utf-8"))
    validate_reviewed_dataset(_examples(tmp_path), roles, manifest)
    assert len(manifest["dataset_content_sha256"]) == 64


def test_a_modified_example_no_longer_matches_its_seal(tmp_path: Path) -> None:
    from training.model import validate_reviewed_dataset

    manifest = _bundle(tmp_path)
    examples = _examples(tmp_path)
    examples[0]["values"]["ndg"] = "999"
    roles = json.loads((tmp_path / "out" / "roles.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="fingerprint"):
        validate_reviewed_dataset(examples, roles, manifest)


def test_the_guarantee_fund_in_two_splits_is_not_an_overlap() -> None:
    examples = [{"id": "1__A", "practice": "1", "split": "train", "values": {"ndg_2": "11153238"}, "image_sha256": "a"},
                {"id": "2__B", "practice": "2", "split": "test", "values": {"ndg_2": "11153238"}, "image_sha256": "b"}]
    assert audit_splits(examples)["status"] == "passed"


def test_the_screens_of_a_practice_without_a_role_are_refused(tmp_path: Path) -> None:
    root = _archive(tmp_path, ROLES)
    (root / "pratiche.csv").write_text("Pratica;Ruolo;Schermate;Valori\r\n111;addestramento;1;1\r\n222;controllo;1;1\r\n",
                                      encoding="utf-8-sig")
    with pytest.raises(ValueError, match="senza ruolo"):
        read_archive(root)
