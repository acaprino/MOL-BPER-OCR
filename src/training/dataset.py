"""Build supervised examples from reviewed values and untouched OCR observations."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence

from openpyxl import load_workbook
from PIL import Image

from training.schema import REPOSITORY, field_role, role_vocabulary, vocabulary

DEFAULT_PRACTICES = {
    "train": ["51185037", "52062600", "52067184", "52068422", "52080223", "52102599", "52130861", "52135039"],
    "val": ["51659595", "52126316"],
    "test": ["51531667", "52060489"],
}
# G8 groups of a transcribed lot (docs/next-ver-plan.md §5.4): the extended validation gets examples,
# the confirmation group is sealed and keeps only its reviewed values and image digests.
EXTENDED_SPLIT = "val_ext"
SEALED_SPLIT = "conferma"
GROUP_SPLITS = {"validazione_estesa": EXTENDED_SPLIT, "conferma": SEALED_SPLIT}
V3_1_LOT = "riscontro-2026-10-07"
# Which lots compose each dataset version. The manifest names the version; a directory name never does.
DATASET_VERSIONS = {"ground-truth-v3.1": (), "ground-truth-v3.2": ("lotto-2026-08-21",)}
GROUND_TRUTH_COLUMNS = ["Fotogramma", "Denominazione da attribuire", "Valore rilevato", "Esito", "Stato revisione",
                        "Pratica", "Lotto", "Gruppo", "Riga Excel", "Correzione"]


class Lot(NamedTuple):
    """A lot reviewed by transcription and assigned to the G8 groups (data/revisione/<lotto>/assegnazione_g8.py)."""

    workbook: Path
    assignment: Path
    corrections: Path | None = None
    ocr: Path | None = None
REVIEW_STATES = re.compile(r"^(Confermato|Corretto)(\s+da\s+.+|\s+dall['’]utente)?$")
# Outcomes of a lot reviewed by transcription (lotto-2026-08-21 onwards); the v3.1 workbook has no outcome column.
TRANSCRIPTION_OUTCOMES = ("TRASCRITTO", "VUOTO", "NON VISIBILE", "PARZIALE", "NON LEGGIBILE")
OUTCOMES_WITH_TEXT = ("TRASCRITTO", "PARZIALE")
# Outcomes that give an example a target: the value, or its absence. The others leave the field unscored.
SCORED_OUTCOMES = ("TRASCRITTO", "VUOTO", "NON VISIBILE")


def _cell_text(value: Any) -> str | None:
    return None if value is None or not str(value).strip() else str(value).strip()


def _review_rows(path: Path, required: tuple[str, ...], mapping: Mapping[str, str]):
    """Yield (excel_row, cells) of the Revisione sheet, refusing missing columns, formulas and odd keys."""
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        rows = workbook["Revisione"].iter_rows()
        header = {str(cell.value): index for index, cell in enumerate(next(rows))}
        if any(name not in header for name in required):
            raise ValueError(f"Il file non è una revisione completata: mancano le colonne {required}.")
        keys: set[tuple[str, str]] = set()
        for number, row in enumerate(rows, 2):
            if not any(cell.value is not None for cell in row):
                continue
            if any(row[header[name]].data_type == "f" for name in required):
                raise ValueError(f"Il ground truth contiene una formula alla riga {number}.")
            cells = {name: row[index].value for name, index in header.items()}
            screen = str(cells["ID schermata"] or "").strip()
            display = str(cells["Campo"] or "").strip()
            if not screen or "__" not in screen or display not in mapping:
                raise ValueError(f"Schermata o campo non riconosciuto alla riga {number}.")
            practice = screen.split("__", 1)[0]
            if "Pratica" in header and str(cells["Pratica"] or "").strip() != practice:
                raise ValueError(f"Numero pratica incoerente alla riga {number}.")
            key = (screen, mapping[display])
            if key in keys:
                raise ValueError(f"Campo duplicato: {key}.")
            keys.add(key)
            yield number, {"screen": screen, "practice": practice, "display_name": display, "field": mapping[display],
                           "cells": cells}
    finally:
        workbook.close()


def read_reviewed_truth(path: Path, mapping: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """Read effective values, refusing drafts, ambiguous keys and executable cells."""
    mapping = vocabulary()[1] if mapping is None else mapping
    result: list[dict[str, Any]] = []
    for number, row in _review_rows(path, ("ID schermata", "Campo", "Valore aggiornato v3.1", "Stato v3.1"), mapping):
        state = str(row["cells"]["Stato v3.1"] or "").strip()
        if not REVIEW_STATES.match(state):
            raise ValueError(f"Revisione non completata alla riga {number}: {state!r}.")
        value = _cell_text(row["cells"]["Valore aggiornato v3.1"])
        result.append({"screen": row["screen"], "practice": row["practice"], "display_name": row["display_name"],
                       "field": row["field"], "value": value, "outcome": "TRASCRITTO" if value is not None else "VUOTO",
                       "reviewer_status": state, "excel_row": number, "correction": None})
    if not result:
        raise ValueError("La revisione non contiene valori.")
    return result


def read_transcribed_truth(path: Path, corrections_path: Path | None = None,
                           mapping: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """Read a lot reviewed by transcription (Trascrizione + Esito), applying its recorded corrections.

    A correction replaces the reviewed outcome and text of one Excel row; the original stays in the record.
    """
    mapping = vocabulary()[1] if mapping is None else mapping
    corrections: dict[int, dict[str, Any]] = {}
    if corrections_path is not None:
        recorded = json.loads(corrections_path.read_text(encoding="utf-8"))
        if recorded["workbook_sha256"] != _sha256(path):
            raise ValueError("Le correzioni si riferiscono a un altro workbook.")
        corrections = {fix["riga_excel"]: fix for fix in recorded["correzioni"]}
    result: list[dict[str, Any]] = []
    for number, row in _review_rows(path, ("ID schermata", "Campo", "Trascrizione", "Esito"), mapping):
        outcome = str(row["cells"]["Esito"] or "").strip()
        text = _cell_text(row["cells"]["Trascrizione"])
        fix = corrections.pop(number, None)
        if fix is not None:
            if (fix["schermata"], fix["campo"], fix["revisione"]["esito"]) != (row["screen"], row["display_name"], outcome):
                raise ValueError(f"La correzione della riga {number} non corrisponde alla revisione.")
            outcome, text = fix["corretto"]["esito"], fix["corretto"]["trascrizione"]
        if outcome not in TRANSCRIPTION_OUTCOMES:
            raise ValueError(f"Esito non riconosciuto alla riga {number}: {outcome!r}.")
        if (outcome in OUTCOMES_WITH_TEXT) != (text is not None):
            raise ValueError(f"Esito incoerente con la trascrizione alla riga {number}: {outcome!r}.")
        result.append({"screen": row["screen"], "practice": row["practice"], "display_name": row["display_name"],
                       "field": row["field"], "value": text, "outcome": outcome, "reviewer_status": outcome,
                       "excel_row": number, "correction": fix})
    if corrections:
        raise ValueError(f"Correzioni senza riga nel workbook: {sorted(corrections)}.")
    if not result:
        raise ValueError("La revisione non contiene valori.")
    return result


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
    """Fail closed if related practices, identities or images cross a split boundary.

    Between the v3.1 splits and the G8 extended validation an identity in common is recorded,
    not refused (docs/next-ver-plan.md §5.4, rule 3): no reviewed practice is excluded.
    """
    from extraction.normalization import normalize_ndg

    seen: dict[str, dict[str, str]] = {kind: {} for kind in ("pratica", "NDG", "immagine", "pixel")}
    counts: Counter[str] = Counter()
    overlaps: dict[tuple[str, str], dict[str, Any]] = {}
    for example in examples:
        split = example["split"]
        if split not in ("train", "val", "test", EXTENDED_SPLIT, SEALED_SPLIT):
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
                pair = {old, split}
                if not pair & {EXTENDED_SPLIT, SEALED_SPLIT} or pair == {EXTENDED_SPLIT, SEALED_SPLIT}:
                    raise ValueError(f"Contaminazione fra split per {kind}: {identity} ({old}, {split}).")
                overlaps[(kind, identity)] = {"tipo": kind, "valore": identity, "split": sorted({old, split})}
                continue
            seen[kind][identity] = split
    return {"status": "passed", "screens_by_split": dict(counts),
            "unique_practices": len(seen["pratica"]), "unique_ndgs": len(seen["NDG"]),
            "checks": ["whole_practice", "all_subject_ndgs", "source_image_bytes", "decoded_image_pixels"],
            "recorded_overlaps": list(overlaps.values())}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    def scalar(item: Any) -> Any:
        if hasattr(item, "item"):
            return item.item()
        raise TypeError(f"Tipo non serializzabile: {type(item).__name__}")

    path.write_text(json.dumps(value, ensure_ascii=False, default=scalar, separators=(",", ":")), encoding="utf-8")


def resolve_screenshot_path(screenshots_dir: Path, screen: str) -> Path:
    """Resolve `<practice>__<page>` from per-practice folders or flat layout."""
    practice, page = screen.split("__", 1)
    for candidate in (
        screenshots_dir / practice / f"{page}.png",
        screenshots_dir / "pratiche" / practice / f"{page}.png",
        screenshots_dir.parent / "pratiche" / practice / f"{page}.png",
        screenshots_dir / "pratiche" / practice / f"{screen}.png",
        screenshots_dir / practice / f"{screen}.png",
        screenshots_dir / f"{screen}.png",
    ):
        if candidate.is_file():
            return candidate
    return screenshots_dir / practice / f"{page}.png"


def _source(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": _sha256(path)}


def _collect_truth(workbook_path: Path, lots: Sequence[Lot]) -> tuple[list[dict[str, Any]], dict[str, str],
                                                                      dict[str, dict[str, str]], list[dict[str, Any]]]:
    """Read every reviewed lot: records with their lot, the split of each practice, the digests the sealed
    screens were assigned with, and the sources for the manifest."""
    records = [dict(record, lot=V3_1_LOT) for record in read_reviewed_truth(workbook_path)]
    splits = {practice: split for split, practices in DEFAULT_PRACTICES.items() for practice in practices}
    if {record["practice"] for record in records} != set(splits):
        raise ValueError("Le pratiche non coincidono con il piano di separazione verificato.")
    sources = [{"lotto": V3_1_LOT, "workbook": _source(workbook_path)}]
    sealed_digests: dict[str, dict[str, str]] = {}
    for lot in lots:
        assignment = json.loads(lot.assignment.read_text(encoding="utf-8"))
        name = assignment["lotto"]
        groups = {practice: GROUP_SPLITS[group] for group, practices in assignment["gruppi"].items()
                  for practice in practices}
        lot_records = read_transcribed_truth(lot.workbook, lot.corrections)
        unassigned = {record["practice"] for record in lot_records} - set(groups)
        if unassigned:
            raise ValueError(f"Pratiche del lotto {name} senza gruppo G8: {sorted(unassigned)}.")
        if set(groups) & set(splits):
            raise ValueError(f"Pratiche del lotto {name} già presenti: {sorted(set(groups) & set(splits))}.")
        splits.update(groups)
        records += [dict(record, lot=name) for record in lot_records]
        for screen, digests in assignment["schermate"].items():
            if groups.get(screen.split("__", 1)[0]) == SEALED_SPLIT:
                sealed_digests[screen] = digests
        source = {"lotto": name, "workbook": _source(lot.workbook), "assignment": _source(lot.assignment)}
        if lot.corrections is not None:
            source["corrections"] = _source(lot.corrections)
        if lot.ocr is not None:
            source["ocr"] = _source(lot.ocr)
        sources.append(source)
    return records, splits, sealed_digests, sources


def build_dataset(workbook_path: Path, screenshots_dir: Path, ocr_path: Path,
                  output_dir: Path, lots: Sequence[Lot] = ()) -> dict[str, Any]:
    """Create the versioned bundle without any provider call.

    The truth tables (ground_truth.csv, screens.csv, practices.csv) cover every reviewed lot. Examples exist
    only for the screens with an OCR reading: the v3.1 splits and the G8 extended validation. The sealed
    confirmation group keeps its values and image digests, and an OCR reading of its screens is refused.
    """
    from training.alignment import align_screen

    records, splits, sealed_digests, sources = _collect_truth(workbook_path, lots)
    lot_names = tuple(source["lotto"] for source in sources[1:])
    version = next((name for name, composition in DATASET_VERSIONS.items() if composition == lot_names), None)
    if version is None:
        raise ValueError(f"Nessuna versione del dataset è composta dai lotti {lot_names}.")
    raw_ocr = json.loads(ocr_path.read_text(encoding="utf-8"))
    for lot in lots:
        if lot.ocr is not None:
            extra = json.loads(lot.ocr.read_text(encoding="utf-8"))
            if set(extra) & set(raw_ocr):
                raise ValueError(f"Schermate lette in due cache OCR: {sorted(set(extra) & set(raw_ocr))}.")
            raw_ocr.update(extra)
    sealed_read = sorted(screen for screen in raw_ocr if splits.get(screen.split("__", 1)[0]) == SEALED_SPLIT)
    if sealed_read:
        raise ValueError(f"Schermate sigillate con una lettura OCR: {sealed_read}.")
    by_screen: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if splits[record["practice"]] != SEALED_SPLIT and record["outcome"] in SCORED_OUTCOMES:
            by_screen[record["screen"]].append(record)
    if set(by_screen) != set(raw_ocr):
        raise ValueError("Le schermate del cache OCR non coincidono con il ground truth revisionato.")
    assigned_digests = {screen: digests for lot in lots
                        for screen, digests in json.loads(lot.assignment.read_text(encoding="utf-8"))["schermate"].items()}
    examples: list[dict[str, Any]] = []
    alignment_rows: list[dict[str, Any]] = []
    for number, (screen, fields) in enumerate(sorted(by_screen.items()), 1):
        image_path = resolve_screenshot_path(screenshots_dir, screen)
        raw = raw_ocr[screen]
        lines = [{"text": item[0], "score": item[1], "box": item[2]} for item in raw["items"]]
        with Image.open(image_path) as image:
            rgb = image.convert("RGB")
            image_size = list(rgb.size)
            pixel_hash = hashlib.sha256(rgb.tobytes()).hexdigest()
            located = align_screen(screen.split("__", 1)[1],
                                   [(record["display_name"], record["value"] or "") for record in fields], lines, rgb)
        image_hash = _sha256(image_path)
        if screen in assigned_digests and assigned_digests[screen]["image_sha256"] != image_hash:
            raise ValueError(f"{screen} differisce dall'immagine assegnata ai gruppi G8.")
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
                         "image_size": image_size, "image_sha256": image_hash, "pixel_sha256": pixel_hash,
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

    # The truth tables: every screen of every lot, hashed from the file; the sealed ones keep the digests
    # they were assigned with, so no pixel of theirs is decoded here.
    by_id = {example["id"]: example for example in examples}
    lot_of = {record["screen"]: record["lot"] for record in records}
    screen_rows: list[dict[str, Any]] = []
    for screen in sorted(lot_of):
        practice = screen.split("__", 1)[0]
        image_path = resolve_screenshot_path(screenshots_dir, screen)
        example = by_id.get(screen)
        if example is not None:
            image_hash, pixel_hash, image_size = example["image_sha256"], example["pixel_sha256"], example["image_size"]
        else:
            image_hash = _sha256(image_path)
            with Image.open(image_path) as image:
                image_size = list(image.size)
                pixel_hash = (sealed_digests[screen]["pixel_sha256"] if screen in sealed_digests
                              else hashlib.sha256(image.convert("RGB").tobytes()).hexdigest())
            if screen in sealed_digests and sealed_digests[screen]["image_sha256"] != image_hash:
                raise ValueError(f"{screen} differisce dall'immagine assegnata ai gruppi G8.")
        screen_rows.append({"Schermata": screen, "Pratica": practice, "Lotto": lot_of[screen], "Gruppo": splits[practice],
                            "Percorso": Path(os.path.relpath(image_path, screenshots_dir)).as_posix(),
                            "SHA256 immagine": image_hash, "SHA256 pixel": pixel_hash,
                            "Larghezza": image_size[0], "Altezza": image_size[1], "Esempio": "sì" if example else "no"})
    truth_isolation = audit_splits([
        {"id": row["Schermata"], "practice": row["Pratica"], "split": row["Gruppo"],
         "image_sha256": row["SHA256 immagine"], "pixel_sha256": row["SHA256 pixel"],
         "values": {record["field"]: record["value"] for record in records
                    if record["screen"] == row["Schermata"] and record["outcome"] == "TRASCRITTO"}}
        for row in screen_rows])
    lot_of_practice = {record["practice"]: record["lot"] for record in records}
    practice_rows = [{"Pratica": practice, "Lotto": lot_of_practice[practice], "Gruppo": split,
                      "Schermate": sum(row["Pratica"] == practice for row in screen_rows),
                      "Righe": sum(record["practice"] == practice for record in records)}
                     for practice, split in sorted(splits.items(), key=lambda item: int(item[0]))]

    coverage: dict[str, Any] = {}
    example_splits = [split for split in ("train", "val", "test", EXTENDED_SPLIT) if any(e["split"] == split for e in examples)]
    for field in vocabulary()[0]:
        coverage[field] = {split: {"reviewed": 0, "nonempty": 0, "supervised": 0} for split in example_splits}
    for record in alignment_rows:
        cell = coverage[record["field"]][record["split"]]
        cell["reviewed"] += 1
        cell["nonempty"] += record["expected"] is not None
        cell["supervised"] += record["supervision"] in {"supervised", "partial_supervision"}
    counts = Counter(row["supervision"] for row in alignment_rows)
    roles = role_vocabulary()
    training_roles = Counter(label for example in examples if example["split"] == "train" for label in example["labels"])
    practice_splits = {split: sorted(p for p, s in splits.items() if s == split)
                       for split in ("train", "val", "test", EXTENDED_SPLIT, SEALED_SPLIT) if split in splits.values()}
    manifest = {"schema_version": 1, "dataset_version": version,
                "reviewed_rows": sum(len(example["values"]) for example in examples),
                "screens": len(examples), "practices": len({example["practice"] for example in examples}),
                "truth_counts": {"rows": len(records), "screens": len(screen_rows), "practices": len(splits)},
                "roles": roles, "workbook": sources[0]["workbook"],
                "ocr": {"path": str(ocr_path.resolve()), "sha256": _sha256(ocr_path), "scale": "1x", "words_rewritten": False},
                "sources": sources, "practice_splits": practice_splits, "leakage_audit": leakage,
                "truth_isolation": truth_isolation,
                "supervision_counts": dict(counts), "training_role_words": dict(training_roles),
                "fields_without_heldout_positive_examples": [key for key, value in coverage.items()
                                                             if not value["test"]["nonempty"]],
                "fields_without_supervised_training_examples": [key for key, value in coverage.items()
                                                                if not value["train"]["supervised"]],
                "policy": "Exact aligned fields and ordered exact words within reviewed notes and validation-date text use fitted geometry. Uncertain background and conflicting roles are masked; independently verified exact positives are retained. Whole-field exactness is measured separately. Original OCR text and all reviewed targets are preserved.",
                "code_sha256": {path.name: _sha256(path) for path in sorted(Path(__file__).parent.glob("*.py"))}}
    if SEALED_SPLIT in practice_splits:
        manifest["sealed"] = {"split": SEALED_SPLIT, "practices": practice_splits[SEALED_SPLIT],
                              "screens": sum(row["Gruppo"] == SEALED_SPLIT for row in screen_rows),
                              "policy": "Reviewed values and image digests only: no OCR, metrics or inspection until the candidate is frozen (docs/next-ver-plan.md §5.4, rule 4)."}
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "examples.json", examples)
    _write_json(output_dir / "roles.json", roles)
    _write_json(output_dir / "coverage.json", coverage)
    _write_json(output_dir / "manifest.json", manifest)
    with (output_dir / "ground_truth.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(GROUND_TRUTH_COLUMNS)
        writer.writerows((record["screen"], record["display_name"], record["value"] or "", record["outcome"],
                          record["reviewer_status"], record["practice"], record["lot"], splits[record["practice"]],
                          record["excel_row"],
                          json.dumps(record["correction"]["revisione"], ensure_ascii=False) if record["correction"] else "")
                         for record in records)
    for name, rows in (("screens.csv", screen_rows), ("practices.csv", practice_rows)):
        with (output_dir / name).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=";")
            writer.writeheader()
            writer.writerows(rows)
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
    parser.add_argument("--lot", nargs=4, action="append", default=[], metavar=("WORKBOOK", "ASSIGNMENT", "CORRECTIONS", "OCR"),
                        help="a lot reviewed by transcription; write - for a missing corrections file or OCR cache")
    arguments = parser.parse_args()
    lots = [Lot(Path(workbook), Path(assignment), None if corrections == "-" else Path(corrections),
                None if ocr == "-" else Path(ocr)) for workbook, assignment, corrections, ocr in arguments.lot]
    result = build_dataset(arguments.workbook, arguments.screenshots, arguments.ocr, arguments.output, lots)
    print(json.dumps({key: result[key] for key in ("dataset_version", "reviewed_rows", "screens", "practices", "truth_counts",
                                                   "supervision_counts", "leakage_audit", "truth_isolation")}, indent=2))


if __name__ == "__main__":
    main()
