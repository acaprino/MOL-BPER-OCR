"""Re-evaluate the saved lilt-v3.1-20261016 predictions on the current v3.1 examples.

Usage (from the repository root):
    python -I reconcile_lilt_run.py <repo_root> <out_dir>

Writes validation/test field metrics recomputed with the current
src/training/evaluation.py and a per-record comparison with the saved run reports.
Reads only; never rewrites the saved run or the dataset bundle.
"""
import json
import sys
from collections import Counter
from pathlib import Path

root, out = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(root / "src"))
from training.evaluation import evaluate_predictions  # noqa: E402

RUN = root / "data/training/runs/lilt-v3.1-20261016"
examples = json.loads((root / "data/training/ground-truth-v3.1/examples.json").read_text(encoding="utf-8"))
SPLITS = {"validation": "val", "test": "test"}
summary: dict[str, dict] = {}

for name, split in SPLITS.items():
    predictions = json.loads((RUN / f"{name}_predictions.json").read_text(encoding="utf-8"))
    saved = json.loads((RUN / f"{name}_field_metrics.json").read_text(encoding="utf-8"))
    selected = [e for e in examples if e["split"] == split]
    if {e["id"] for e in selected} != set(predictions):
        raise SystemExit(f"{name}: prediction ids differ from current {split} examples")
    for e in selected:
        if len(predictions[e["id"]]["pred"]) != len(e["words"]):
            raise SystemExit(f"{name}: word count differs for {e['id']}")
    current = evaluate_predictions(selected, predictions)
    (out / f"{name}_field_metrics_current_examples.json").write_text(
        json.dumps(current, ensure_ascii=False, indent=1), encoding="utf-8")

    old = {(r["id"], r["field"]): r for r in saved["records"]}
    new = {(r["id"], r["field"]): r for r in current["records"]}
    keys_equal = set(old) == set(new)
    changes: Counter[str] = Counter()
    rows = []
    for key in sorted(set(old) | set(new)):
        o, n = old.get(key), new.get(key)
        if o is None or n is None:
            changes["record_only_in_" + ("current" if o is None else "saved")] += 1
            continue
        for attr in ("expected", "predicted", "status", "content_available"):
            if o[attr] != n[attr]:
                changes[attr] += 1
                rows.append({"id": key[0], "field": key[1], "attr": attr, "saved": o[attr], "current": n[attr]})
    (out / f"{name}_record_diff.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    def brief(report: dict) -> dict:
        overall = report["overall"]
        return {
            "accuracy": overall["accuracy"], "counts": overall["counts"],
            "content_availability": overall["content_availability"],
        }

    summary[name] = {
        "record_keys_equal": keys_equal, "records": len(new), "changed_attributes": dict(changes),
        "saved": brief(saved), "current_examples": brief(current),
    }

(out / "reconciliation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=1))
