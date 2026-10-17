"""Build supervised examples from reviewed values and untouched OCR observations."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from openpyxl import load_workbook
from PIL import Image

from training.schema import REPOSITORY, field_role, role_vocabulary, vocabulary

DEFAULT_PRACTICES = {
    "train": ["51185037", "52062600", "52067184", "52068422", "52080223", "52102599", "52130861", "52135039"],
    "val": ["51659595", "52126316"],
    "test": ["51531667", "52060489"],
}
REVIEW_STATES = {"Confermato da Rita", "Corretto da Rita", "Confermato dall'utente", "Confermato dall’utente"}


def read_reviewed_truth(path: Path, mapping: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """Read effective values, refusing drafts, ambiguous keys and executable cells."""
    mapping = vocabulary()[1] if mapping is None else mapping
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        rows = workbook["Revisione"].iter_rows()
        header = {str(cell.value): index for index, cell in enumerate(next(rows))}
        required = ("ID schermata", "Campo", "Valore aggiornato v3.1", "Stato v3.1")
        if any(name not in header for name in required):
            raise ValueError("Il file non è la revisione 3.1 completata: mancano colonne obbligatorie.")
        result: list[dict[str, Any]] = []
        keys: set[tuple[str, str]] = set()
        for number, row in enumerate(rows, 2):
            if not any(cell.value is not None for cell in row):
                continue
            if any(row[header[name]].data_type == "f" for name in required):
                raise ValueError(f"Il ground truth contiene una formula alla riga {number}.")
            screen = str(row[header[required[0]]].value or "").strip()
            display = str(row[header[required[1]]].value or "").strip()
            state = str(row[header[required[3]]].value or "").strip()
            if state not in REVIEW_STATES:
                raise ValueError(f"Revisione non completata alla riga {number}: {state!r}.")
            if not screen or "__" not in screen or display not in mapping:
                raise ValueError(f"Schermata o campo non riconosciuto alla riga {number}.")
            practice = screen.split("__", 1)[0]
            if "Pratica" in header:
                shown = str(row[header["Pratica"]].value or "").strip()
                if shown != practice:
                    raise ValueError(f"Numero pratica incoerente alla riga {number}.")
            key = (screen, mapping[display])
            if key in keys:
                raise ValueError(f"Campo duplicato: {key}.")
            keys.add(key)
            raw = row[header[required[2]]].value
            value = None if raw is None or not str(raw).strip() else str(raw).strip()
            result.append({"screen": screen, "practice": practice, "display_name": display,
                           "field": mapping[display], "value": value, "reviewer_status": state, "excel_row": number})
        if not result:
            raise ValueError("La revisione non contiene valori.")
        return result
    finally:
        workbook.close()


def apply_supervision(words: list[dict[str, Any]], alignments: Mapping[str, dict[str, Any]],
                      roles: Mapping[str, str]) -> tuple[list[str], dict[str, str]]:
    """Use only exact, located positive labels; uncertain observations carry no loss."""
    labels = ["O"] * len(words)
    owners: dict[int, set[str]] = defaultdict(set)
    statuses: dict[str, str] = {}
    uncertain: set[int] = set()
    for field, detail in alignments.items():
        indices = detail.get("indices", [])
        if any(not isinstance(i, int) or i < 0 or i >= len(words) for i in indices):
            raise ValueError(f"Indici OCR non validi per {field}.")
        if detail["status"] == "empty":
            statuses[field] = "empty"
            continue
        exact = detail["status"] == "aligned" and detail.get("exact_text") and bool(indices)
        fitted = all(words[i].get("fitted", True) for i in indices)
        if exact and fitted:
            for index in indices:
                owners[index].add(field)
            statuses[field] = "supervised"
            continue
        statuses[field] = "ignored_ocr_mismatch" if detail.get("status") == "aligned" and not detail.get("exact_text") else "ignored_alignment"
        uncertain.update(indices)
        box = detail.get("bbox")
        if box is None:
            uncertain.update(range(len(words)))
        else:
            x0, y0, x1, y1 = box
            uncertain.update(i for i, word in enumerate(words)
                             if x0 <= (word["x0"]+word["x1"])/2 <= x1
                             and y0 <= (word["y0"]+word["y1"])/2 <= y1)
        if detail["status"] == "aligned" and roles[field] in {
            "note_della_richiesta", "note_scheda_privati", "ultima_validazione_scheda",
            "scadenza", "tipo_op",
        }:
            verified = detail.get("verified_indices", [])
            if not set(verified).issubset(indices):
                raise ValueError(f"Le parole verificate non appartengono alla nota {field}.")
            fitted_verified = [i for i in verified if words[i].get("fitted", True)]
            for index in fitted_verified:
                owners[index].add(field)
            if fitted_verified:
                statuses[field] = "partial_supervision"
    for index in uncertain:
        labels[index] = "IGNORE"
    for index, fields in owners.items():
        target_roles = {roles[field] for field in fields}
        if len(target_roles) == 1:
            labels[index] = next(iter(target_roles))
        else:
            labels[index] = "IGNORE"
            for field in fields:
                statuses[field] = "ignored_conflict"
    return labels, statuses


def audit_splits(examples: list[dict[str, Any]]) -> dict[str, Any]:
    """Fail closed if related practices, identities or images cross a split boundary."""
    from extraction.normalization import normalize_ndg

    seen: dict[str, dict[str, str]] = {kind: {} for kind in ("pratica", "NDG", "immagine", "pixel")}
    counts: Counter[str] = Counter()
    for example in examples:
        split = example["split"]
        if split not in ("train", "val", "test"):
            raise ValueError(f"Split non valido: {split}.")
        counts[split] += 1
        identifiers = {normalize_ndg(value) for key, value in example["values"].items()
                       if key == "ndg" or key.startswith("ndg_")}
        identifiers.discard(None)
        items = [("pratica", example["practice"]), ("immagine", example.get("image_sha256")),
                 ("pixel", example.get("pixel_sha256")), *[("NDG", value) for value in identifiers]]
        for kind, identity in items:
            if not identity:
                continue
            old = seen[kind].get(identity)
            if old is not None and old != split:
                raise ValueError(f"Contaminazione fra split per {kind}: {identity} ({old}, {split}).")
            seen[kind][identity] = split
    return {"status": "passed", "screens_by_split": dict(counts),
            "unique_practices": len(seen["pratica"]), "unique_ndgs": len(seen["NDG"]),
            "checks": ["whole_practice", "all_subject_ndgs", "source_image_bytes", "decoded_image_pixels"]}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    def scalar(item: Any) -> Any:
        if hasattr(item, "item"):
            return item.item()
        raise TypeError(f"Tipo non serializzabile: {type(item).__name__}")

    path.write_text(json.dumps(value, ensure_ascii=False, default=scalar, separators=(",", ":")), encoding="utf-8")


def build_dataset(workbook_path: Path, screenshots_dir: Path, ocr_path: Path,
                  output_dir: Path) -> dict[str, Any]:
    """Create the versioned train/validation/test bundle without any provider call."""
    from training.alignment import align_screen

    records = read_reviewed_truth(workbook_path)
    by_screen: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_screen[record["screen"]].append(record)
    raw_ocr = json.loads(ocr_path.read_text(encoding="utf-8"))
    if set(by_screen) != set(raw_ocr):
        raise ValueError("Le schermate del cache OCR non coincidono con il ground truth revisionato.")
    splits = {practice: split for split, practices in DEFAULT_PRACTICES.items() for practice in practices}
    if {record["practice"] for record in records} != set(splits):
        raise ValueError("Le pratiche non coincidono con il piano di separazione verificato.")
    examples: list[dict[str, Any]] = []
    alignment_rows: list[dict[str, Any]] = []
    for number, (screen, fields) in enumerate(sorted(by_screen.items()), 1):
        image_path = screenshots_dir / f"{screen}.png"
        raw = raw_ocr[screen]
        lines = [{"text": item[0], "score": item[1], "box": item[2]} for item in raw["items"]]
        with Image.open(image_path) as image:
            rgb = image.convert("RGB")
            image_size = list(rgb.size)
            pixel_hash = hashlib.sha256(rgb.tobytes()).hexdigest()
            located = align_screen(screen.split("__", 1)[1],
                                   [(record["display_name"], record["value"] or "") for record in fields], lines, rgb)
        words = located["words"]
        for word in words:
            word["x0"], word["x1"] = max(0.0, float(word["x0"])), min(float(image_size[0]), float(word["x1"]))
            word["y0"], word["y1"] = max(0.0, float(word["y0"])), min(float(image_size[1]), float(word["y1"]))
            if word["x1"] <= word["x0"] or word["y1"] <= word["y0"]:
                raise ValueError(f"Coordinate OCR non valide in {screen}: {word}.")
        labels, supervision = apply_supervision(words, located["fields"],
                                               {record["display_name"]: field_role(record["field"]) for record in fields})
        practice = fields[0]["practice"]
        field_alignment = {record["field"]: dict(located["fields"][record["display_name"]],
                                                 supervision=supervision[record["display_name"]]) for record in fields}
        examples.append({"id": screen, "practice": practice, "split": splits[practice],
                         "image_size": image_size, "image_sha256": _sha256(image_path), "pixel_sha256": pixel_hash,
                         "words": words, "labels": labels, "values": {record["field"]: record["value"] for record in fields},
                         "field_alignment": field_alignment})
        for record in fields:
            detail = located["fields"][record["display_name"]]
            alignment_rows.append({"screen": screen, "practice": practice, "split": splits[practice],
                                   "field": record["field"], "expected": record["value"],
                                   "ocr_text": detail.get("ocr_text", ""), "exact_text": detail.get("exact_text", False),
                                   "supervision": supervision[record["display_name"]], "status": detail["status"]})
        if number % 10 == 0 or number == len(by_screen):
            print(f"Aligned {number}/{len(by_screen)} screenshots", flush=True)
    leakage = audit_splits(examples)
    coverage: dict[str, Any] = {}
    for field in vocabulary()[0]:
        coverage[field] = {split: {"reviewed": 0, "nonempty": 0, "supervised": 0} for split in DEFAULT_PRACTICES}
    for record in alignment_rows:
        cell = coverage[record["field"]][record["split"]]
        cell["reviewed"] += 1
        cell["nonempty"] += record["expected"] is not None
        cell["supervised"] += record["supervision"] in {"supervised", "partial_supervision"}
    counts = Counter(row["supervision"] for row in alignment_rows)
    roles = role_vocabulary()
    training_roles = Counter(label for example in examples if example["split"] == "train" for label in example["labels"])
    manifest = {"schema_version": 1, "dataset_version": "ground-truth-v3.1", "reviewed_rows": len(records),
                "screens": len(examples), "practices": len(splits), "roles": roles,
                "workbook": {"path": str(workbook_path.resolve()), "sha256": _sha256(workbook_path)},
                "ocr": {"path": str(ocr_path.resolve()), "sha256": _sha256(ocr_path), "scale": "1x", "words_rewritten": False},
                "practice_splits": DEFAULT_PRACTICES, "leakage_audit": leakage,
                "supervision_counts": dict(counts), "training_role_words": dict(training_roles),
                "fields_without_heldout_positive_examples": [key for key, value in coverage.items()
                                                             if not value["test"]["nonempty"]],
                "fields_without_supervised_training_examples": [key for key, value in coverage.items()
                                                                if not value["train"]["supervised"]],
                "policy": "Exact aligned fields and ordered exact words within reviewed notes and validation-date text use fitted geometry. Uncertain background and conflicting roles are masked; independently verified exact positives are retained. Whole-field exactness is measured separately. Original OCR text and all reviewed targets are preserved.",
                "code_sha256": {path.name: _sha256(path) for path in sorted(Path(__file__).parent.glob("*.py"))}}
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "examples.json", examples)
    _write_json(output_dir / "roles.json", roles)
    _write_json(output_dir / "coverage.json", coverage)
    _write_json(output_dir / "manifest.json", manifest)
    with (output_dir / "ground_truth.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(["Fotogramma", "Denominazione da attribuire", "Valore rilevato"])
        writer.writerows((record["screen"], record["display_name"], record["value"] or "") for record in records)
    with (output_dir / "alignment_report.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(alignment_rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(alignment_rows)
    return seal_dataset(output_dir)


def seal_dataset(output_dir: Path) -> dict[str, Any]:
    """Bind the frozen observations and role order to a reproducible content digest."""
    from training.model import dataset_fingerprint

    examples = json.loads((output_dir / "examples.json").read_text(encoding="utf-8"))
    roles = json.loads((output_dir / "roles.json").read_text(encoding="utf-8"))
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["dataset_content_sha256"] = dataset_fingerprint(examples, roles)
    manifest["code_sha256"] = {path.name: _sha256(path) for path in sorted(Path(__file__).parent.glob("*.py"))}
    manifest["policy"] = "Exact aligned fields and ordered exact words within reviewed notes and validation-date text use fitted geometry. Uncertain background and conflicting roles are masked; independently verified exact positives are retained. Whole-field exactness is measured separately. Original OCR text and all reviewed targets are preserved."
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the reviewed BPER LiLT training dataset.")
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--screenshots", type=Path, required=True)
    parser.add_argument("--ocr", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = build_dataset(arguments.workbook, arguments.screenshots, arguments.ocr, arguments.output)
    print(json.dumps({key: result[key] for key in ("reviewed_rows", "screens", "practices", "supervision_counts", "leakage_audit")}, indent=2))


if __name__ == "__main__":
    main()
