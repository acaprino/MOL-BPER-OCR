"""Build supervised examples from the clean practice archive (data/dataset) and untouched OCR observations."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, NamedTuple

from PIL import Image

from training.schema import DATASET_VERSION, field_role, role_vocabulary, vocabulary

# The role of a practice in the archive (ADR 0027) is the split its screens belong to.
SPLIT_OF_ROLE = {"addestramento": "train", "controllo": "val", "test": "test"}
TEST_SPLIT = "test"
KNOWN_SPLITS = ("train", "val", TEST_SPLIT)
# NDGs of institutions, not of clients. The Fondo di garanzia per la prima casa guarantees first-home mortgages and
# is a subject of a large share of the practices: finding it in two of them says nothing about the two (ADR 0024).
INSTITUTIONAL_NDGS = frozenset({"11153238"})
# Outcomes of a reviewed value. Text goes with TRASCRITTO, PARZIALE and DERIVATO; the others record an absence.
OUTCOMES = ("TRASCRITTO", "VUOTO", "NON VISIBILE", "PARZIALE", "NON LEGGIBILE", "DERIVATO")
OUTCOMES_WITH_TEXT = ("TRASCRITTO", "PARZIALE", "DERIVATO")
# Outcomes that give an example a target: the value, or its absence. The others leave the field unscored.
SCORED_OUTCOMES = ("TRASCRITTO", "VUOTO", "NON VISIBILE")
# Outcomes that label the words they find without being measured: a partial text, a header derived from other pages.
# Without them those words would count as background, and teach the model to skip them.
LABEL_ONLY_OUTCOMES = ("PARZIALE", "DERIVATO")
POLICY = ("Exact aligned fields and ordered exact words within reviewed notes and validation-date text use fitted geometry. "
          "Uncertain background and conflicting roles are masked; independently verified exact positives are retained. "
          "Whole-field exactness is measured separately. Original OCR text and all reviewed targets are preserved.")

# The aligner reads the kind of a page from its name. The archive names pages `<pagina>-<NN>` and keeps the
# variant in schermate.csv, so the name the aligner sees is rebuilt from the two.
PAGE_NAMES = {"elenco": "elenco", "soggetti": "soggetti", "gestione-fidi": "gestionefidi", "note": "note",
              "scheda-privati": "scheda_privati"}
VARIANT_NAMES = {("elenco", "tooltip"): "elenco_tooltip", ("elenco", "destra"): "elenco_dx",
                 ("gestione-fidi", "tooltip"): "gestionefidi_tooltip", ("gestione-fidi", "basso"): "gestionefidi_down"}


def alignment_name(page: str, variant: str) -> str:
    """The page name the aligner reads its kind from: `elenco_dx`, `gestionefidi_tooltip`, `note`, ..."""
    return VARIANT_NAMES.get((page, variant), PAGE_NAMES[page])


def screen_id(archive_screen: str) -> str:
    """`51350695/elenco-01` in the archive is `51350695__elenco-01` in examples and OCR caches."""
    return archive_screen.replace("/", "__")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    def scalar(item: Any) -> Any:
        if hasattr(item, "item"):
            return item.item()
        raise TypeError(f"Tipo non serializzabile: {type(item).__name__}")

    path.write_text(json.dumps(value, ensure_ascii=False, default=scalar, separators=(",", ":")), encoding="utf-8")


# ============================================================
# The archive
# ============================================================

class Archive(NamedTuple):
    root: Path
    roles: dict[str, str]                 # practice -> role
    screens: dict[str, dict[str, str]]    # archive screen id -> its row of schermate.csv
    records: list[dict[str, Any]]         # the values with a canonical field: screen (OCR id), practice, field, value...


def _read_table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=";"))


def read_archive(root: Path) -> Archive:
    """Read data/dataset, refusing a changed image, an unknown role, screen or field, and an outcome without its text."""
    fields, mapping = vocabulary()
    roles = {row["Pratica"]: row["Ruolo"] for row in _read_table(root / "pratiche.csv")}
    unknown = sorted({role for role in roles.values() if role not in SPLIT_OF_ROLE})
    if unknown:
        raise ValueError(f"Ruolo non riconosciuto: {unknown}.")
    screens: dict[str, dict[str, str]] = {}
    for row in _read_table(root / "schermate.csv"):
        if row["Pratica"] not in roles:
            raise ValueError(f"Schermata di una pratica senza ruolo: {row['Schermata']}.")
        if row["Pagina"] not in PAGE_NAMES:
            raise ValueError(f"Pagina non riconosciuta: {row['Schermata']}.")
        path = root / row["File"]
        if not path.is_file() or _sha256(path) != row["SHA256"]:
            raise ValueError(f"{row['File']} manca o differisce dall'immagine registrata.")
        screens[row["Schermata"]] = row
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for number, row in enumerate(_read_table(root / "valori.csv"), 2):
        if row["Schermata"] not in screens:
            raise ValueError(f"Valore su una schermata sconosciuta alla riga {number}: {row['Schermata']}.")
        if row["Esito"] not in OUTCOMES:
            raise ValueError(f"Esito non riconosciuto alla riga {number}: {row['Esito']!r}.")
        if (row["Esito"] in OUTCOMES_WITH_TEXT) != bool(row["Valore"]):
            raise ValueError(f"Esito incoerente con il valore alla riga {number}: {row['Esito']!r}.")
        key = (row["Schermata"], row["Campo"])
        if key in seen:
            raise ValueError(f"Campo duplicato: {key}.")
        seen.add(key)
        if not row["Chiave"]:
            continue                                  # outside the 45 fields: in the truth, never a target
        if row["Chiave"] not in fields or mapping.get(row["Campo"]) != row["Chiave"]:
            raise ValueError(f"Campo non riconosciuto alla riga {number}: {row['Campo']} / {row['Chiave']}.")
        records.append({"screen": screen_id(row["Schermata"]), "archive_screen": row["Schermata"],
                        "practice": screens[row["Schermata"]]["Pratica"], "display_name": row["Campo"],
                        "field": row["Chiave"], "value": row["Valore"] or None, "outcome": row["Esito"]})
    return Archive(root, roles, screens, records)


def ocr_screens(archive: Archive, include_test: bool = False) -> list[str]:
    """The screens (OCR ids) an OCR cache must cover: those of the readable practices with a scored value."""
    readable = {"train", "val"} | ({TEST_SPLIT} if include_test else set())
    return sorted({record["screen"] for record in archive.records
                   if SPLIT_OF_ROLE[archive.roles[record["practice"]]] in readable and record["outcome"] in SCORED_OUTCOMES})


# ============================================================
# Supervision
# ============================================================

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

    An institution's NDG is not an identity: it relates no practice to another (ADR 0024).
    """
    from extraction.normalization import normalize_ndg

    seen: dict[str, dict[str, str]] = {kind: {} for kind in ("pratica", "NDG", "immagine", "pixel")}
    counts: Counter[str] = Counter()
    for example in examples:
        split = example["split"]
        if split not in KNOWN_SPLITS:
            raise ValueError(f"Split non valido: {split}.")
        counts[split] += 1
        identifiers = {normalize_ndg(value) for key, value in example["values"].items()
                       if key == "ndg" or key.startswith("ndg_")}
        identifiers.discard(None)
        identifiers -= INSTITUTIONAL_NDGS
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


# ============================================================
# The bundle
# ============================================================

def build_dataset(archive_dir: Path, ocr_path: Path, output_dir: Path, include_test: bool = False) -> dict[str, Any]:
    """Create the bundle from the archive and an OCR cache of its screens, without any provider call.

    Examples exist for the screens of the training and control practices. The test practices are read only when
    ``include_test`` asks for it, which only a frozen candidate does: an OCR reading of a test screen is refused
    otherwise, and a missing one is refused when asked for.
    """
    from training.alignment import align_screen

    archive = read_archive(archive_dir)
    splits = {practice: SPLIT_OF_ROLE[role] for practice, role in archive.roles.items()}
    readable = {"train", "val"} | ({TEST_SPLIT} if include_test else set())
    raw_ocr = json.loads(ocr_path.read_text(encoding="utf-8"))
    refused = sorted(screen for screen in raw_ocr if splits.get(screen.split("__", 1)[0]) not in readable)
    if refused:
        raise ValueError(f"Schermate di pratiche che non si leggono ancora (test senza include_test) o sconosciute: {refused}.")
    by_screen: dict[str, list[dict[str, Any]]] = defaultdict(list)
    label_only: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in archive.records:
        if splits[record["practice"]] not in readable:
            continue
        if record["outcome"] in SCORED_OUTCOMES:
            by_screen[record["screen"]].append(record)
        elif record["outcome"] in LABEL_ONLY_OUTCOMES:
            label_only[record["screen"]].append(record)
    if set(by_screen) != set(raw_ocr):
        raise ValueError("Le schermate del cache OCR non coincidono con la verità dell'archivio.")
    row_of = {screen_id(archive_screen): row for archive_screen, row in archive.screens.items()}
    examples: list[dict[str, Any]] = []
    alignment_rows: list[dict[str, Any]] = []
    for number, (screen, fields) in enumerate(sorted(by_screen.items()), 1):
        row = row_of[screen]
        raw = raw_ocr[screen]
        lines = [{"text": item[0], "score": item[1], "box": item[2]} for item in raw["items"]]
        labelling = [*fields, *label_only.get(screen, [])]
        with Image.open(archive.root / row["File"]) as image:
            rgb = image.convert("RGB")
            image_size = list(rgb.size)
            pixel_hash = hashlib.sha256(rgb.tobytes()).hexdigest()
            located = align_screen(alignment_name(row["Pagina"], row["Variante"]),
                                   [(record["display_name"], record["value"] or "") for record in labelling], lines, rgb)
        words = located["words"]
        for word in words:
            word["x0"], word["x1"] = max(0.0, float(word["x0"])), min(float(image_size[0]), float(word["x1"]))
            word["y0"], word["y1"] = max(0.0, float(word["y0"])), min(float(image_size[1]), float(word["y1"]))
            if word["x1"] <= word["x0"] or word["y1"] <= word["y0"]:
                raise ValueError(f"Coordinate OCR non valide in {screen}: {word}.")
        scored = {record["display_name"] for record in fields}
        # A label-only row with no region says nothing about the page: it must not mask the whole screen.
        alignments = {name: detail for name, detail in located["fields"].items()
                      if name in scored or detail.get("bbox") is not None}
        labels, supervision = apply_supervision(words, alignments,
                                               {record["display_name"]: field_role(record["field"]) for record in labelling})
        practice = fields[0]["practice"]
        field_alignment = {record["field"]: dict(located["fields"][record["display_name"]],
                                                 supervision=supervision[record["display_name"]]) for record in fields}
        examples.append({"id": screen, "practice": practice, "split": splits[practice],
                         "image_size": image_size, "image_sha256": row["SHA256"], "pixel_sha256": pixel_hash,
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

    example_splits = [split for split in KNOWN_SPLITS if any(e["split"] == split for e in examples)]
    coverage: dict[str, Any] = {}
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
    practice_splits = {split: sorted(p for p, s in splits.items() if s == split) for split in KNOWN_SPLITS}
    heldout = TEST_SPLIT if include_test else "val"
    manifest = {"schema_version": 1, "dataset_version": DATASET_VERSION,
                "reviewed_rows": sum(len(example["values"]) for example in examples),
                "screens": len(examples), "practices": len({example["practice"] for example in examples}),
                "truth_counts": {"rows": len(archive.records), "screens": len(archive.screens), "practices": len(archive.roles)},
                "roles": roles, "include_test": include_test,
                "archive": {name: {"path": str((archive.root / name).resolve()), "sha256": _sha256(archive.root / name)}
                            for name in ("pratiche.csv", "schermate.csv", "valori.csv")},
                "ocr": {"path": str(ocr_path.resolve()), "sha256": _sha256(ocr_path), "scale": "1x", "words_rewritten": False},
                "practice_splits": practice_splits, "leakage_audit": leakage,
                "institutional_ndgs": sorted(INSTITUTIONAL_NDGS),
                "supervision_counts": dict(counts), "training_role_words": dict(training_roles),
                "fields_without_heldout_positive_examples": [key for key, value in coverage.items()
                                                             if not value.get(heldout, {}).get("nonempty")],
                "fields_without_supervised_training_examples": [key for key, value in coverage.items()
                                                                if not value.get("train", {}).get("supervised")],
                "policy": POLICY,
                "code_sha256": {path.name: _sha256(path) for path in sorted(Path(__file__).parent.glob("*.py"))}}
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "examples.json", examples)
    _write_json(output_dir / "roles.json", roles)
    _write_json(output_dir / "coverage.json", coverage)
    _write_json(output_dir / "manifest.json", manifest)
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
    manifest["policy"] = POLICY
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the BPER LiLT training dataset from data/dataset.")
    parser.add_argument("--archive", type=Path, required=True, help="the archive folder, data/dataset")
    parser.add_argument("--ocr", type=Path, required=True, help="an OCR cache (cache.json) of the screens to read")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-test", action="store_true", help="read the test practices too: only for a frozen candidate")
    arguments = parser.parse_args()
    result = build_dataset(arguments.archive, arguments.ocr, arguments.output, arguments.include_test)
    print(json.dumps({key: result[key] for key in ("dataset_version", "reviewed_rows", "screens", "practices", "truth_counts",
                                                   "supervision_counts", "leakage_audit")}, indent=2))


if __name__ == "__main__":
    main()
