"""Score a frozen LiLT run on the G8 extended-validation practices of the 2026-08-21 batch.

Run from the repository root with the project .venv, after the OCR cache of the same configuration exists:
    python data/training/validazione-estesa/valuta.py --ocr data/training/validazione-estesa/ocr-A1 \
        --model data/training/runs/lilt-v3.1-20261018-A1-ocr-e16p4-seed7/cpu_model --out <report.json>

Only the practices of g8_assegnazione.json "validazione_estesa" are read: the confirmation group stays sealed.
Reviewed outcomes become expected values as follows: TRASCRITTO is the text, VUOTO and NON VISIBILE are an
absent value (nothing to read on that screen), NON LEGGIBILE and PARZIALE are left out of the score.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from training.alignment import align_screen  # noqa: E402
from training.dataset import apply_supervision  # noqa: E402
from training.evaluation import evaluate_predictions  # noqa: E402
from training.schema import field_role  # noqa: E402

LOT = ROOT / "data" / "revisione" / "lotto-2026-08-21"
SCORED = {"TRASCRITTO", "VUOTO", "NON VISIBILE"}


def _review_rows() -> list[dict[str, Any]]:
    spec = importlib.util.spec_from_file_location("assegnazione_g8", LOT / "assegnazione_g8.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_review()


def build_examples(ocr_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return examples shaped like the v3.1 bundle, plus the rows left out of the score."""
    assignment = json.loads((LOT / "g8_assegnazione.json").read_text(encoding="utf-8"))
    practices = set(assignment["gruppi"]["validazione_estesa"])
    cache = json.loads((ocr_dir / "cache.json").read_text(encoding="utf-8"))
    by_screen: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped = []
    for row in _review_rows():
        if row["practice"] not in practices:
            continue
        if row["outcome"] in SCORED:
            by_screen[row["screen"]].append(row)
        else:
            skipped.append(row)
    if set(by_screen) != set(cache):
        raise ValueError("La cache OCR non copre esattamente le schermate di validazione estesa.")
    examples = []
    for screen, rows in sorted(by_screen.items()):
        hashes = assignment["schermate"][screen]
        path = ROOT / hashes["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes["image_sha256"]:
            raise ValueError(f"{screen} differisce dall'immagine revisionata.")
        lines = [{"text": item[0], "score": item[1], "box": item[2]} for item in cache[screen]["items"]]
        fields = [(row["display_name"], row["value"] or "") for row in rows]
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            located = align_screen(screen.split("__", 1)[1], fields, lines, rgb)
            size = list(rgb.size)
        words = located["words"]
        for word in words:
            word["x0"], word["x1"] = max(0.0, float(word["x0"])), min(float(size[0]), float(word["x1"]))
            word["y0"], word["y1"] = max(0.0, float(word["y0"])), min(float(size[1]), float(word["y1"]))
        labels, _ = apply_supervision(words, located["fields"], {r["display_name"]: field_role(r["field"]) for r in rows})
        examples.append({"id": screen, "practice": rows[0]["practice"], "split": "val_ext", "image_size": size,
                         "words": words, "labels": labels, "values": {r["field"]: r["value"] for r in rows},
                         "field_alignment": {r["field"]: located["fields"][r["display_name"]] for r in rows}})
    return examples, skipped


def predict_all(model_dir: Path, examples: list[dict[str, Any]]) -> dict[str, Any]:
    import torch
    from transformers import AutoTokenizer, LiltForTokenClassification

    from training.model import predict

    torch.set_num_threads(4)
    roles = json.loads((model_dir / "labelmap.json").read_text(encoding="utf-8"))["roles"]
    tokenizer = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
    model = LiltForTokenClassification.from_pretrained(model_dir).eval()
    result = {}
    for example in examples:
        roles_out, probabilities = predict(model, tokenizer, example, roles)
        result[example["id"]] = {"pred": roles_out, "prob": probabilities}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ocr", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    examples, skipped = build_examples(args.ocr)
    predictions = predict_all(args.model, examples)
    report = evaluate_predictions(examples, predictions)
    report["skipped_rows"] = skipped
    report["model"] = args.model.resolve().relative_to(ROOT).as_posix()
    report["ocr_cache_sha256"] = hashlib.sha256((args.ocr / "cache.json").read_bytes()).hexdigest()
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    overall = report["by_split"]["val_ext"]
    print(json.dumps({"strict": f"{overall['correct']}/{overall['total']}", "counts": overall["counts"],
                      "content_availability": overall["content_availability"], "skipped": len(skipped)}, indent=1))


if __name__ == "__main__":
    main()
