"""Compare LiLT runs on the extended validation, with the decoder and the truth of the current bundle.

Run from the repository root with src on the path:
    python data/training/validazione-estesa/confronta.py RUN [RUN ...]

A run is a directory under data/training/runs with extended_predictions.json. Several runs that held out different
practices (cross-validation folds) are read together when joined by a comma: each practice is then scored once, by
the fold that did not train on it. Reads text files only: no model and no image.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from training.evaluation import evaluate_predictions

ROOT = Path(__file__).resolve().parents[3]
FIDI = {"n_fido", "importo_euro", "scadenza", "tipo_op", "rapporto"}
SUBJECTS = {f"{name}_{slot}" for name in ("ndg", "denominazione", "ruolo") for slot in range(1, 5)}
CORRECT = {"correct", "correct_null"}


def _good(records: list[dict[str, Any]]) -> str:
    return f"{sum(r['status'] in CORRECT for r in records)}/{len(records)}"


def _non_null(records: list[dict[str, Any]], fields: set[str]) -> str:
    return _good([r for r in records if r["field"] in fields and r["expected"] is not None])


def compare(specs: list[str], examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One summary per run, in the population of the first: runs differ only by what they predict."""
    results = []
    for spec in specs:
        predictions: dict[str, Any] = {}
        for run in spec.split(","):
            found = json.loads((ROOT / "data/training/runs" / run / "extended_predictions.json").read_text(encoding="utf-8"))
            overlap = set(found) & set(predictions)
            if overlap:
                raise ValueError(f"Schermate previste da due fold: {sorted(overlap)[:3]}.")
            predictions.update(found)
        chosen = [example for example in examples if example["id"] in predictions]
        records = evaluate_predictions(chosen, predictions)["records"]
        by_practice = {}
        for practice in sorted({r["practice"] for r in records}):
            by_practice[practice] = _good([r for r in records if r["practice"] == practice])
        results.append({"run": spec, "strict": _good(records), "fidi_non_null": _non_null(records, FIDI),
                        "soggetti_non_null": _non_null(records, SUBJECTS), "per_pratica": by_practice,
                        "errori": Counter(r["field"] for r in records if r["status"] not in CORRECT).most_common(12),
                        "stati": dict(Counter(r["status"] for r in records))})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--bundle", type=Path, default=ROOT / "data/training/ground-truth-v3.4")
    parser.add_argument("--out", type=Path)
    arguments = parser.parse_args()
    examples = [example for example in json.loads((arguments.bundle / "examples.json").read_text(encoding="utf-8"))
                if example["split"] == "val_ext"]
    results = compare(arguments.runs, examples)
    if arguments.out:
        arguments.out.write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for result in results:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
