"""Evaluate LiLT runs trained on different OCR caches, each on the examples of its own OCR.

Usage: python -I compare_lilt_ocr.py <repo_root> <out_json> LABEL=RUN_DIR=EXAMPLES_JSON [...]
The reviewed values are the same for every OCR; the words differ, so each run is decoded on
the examples it was trained and predicted on. Validation is the selection population; test
is reported only as a seen regression set.
"""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

root, out = Path(sys.argv[1]), Path(sys.argv[2])
runs = [arg.split("=", 2) for arg in sys.argv[3:]]
sys.path.insert(0, str(root / "src"))
from training.evaluation import evaluate_predictions  # noqa: E402

FIDI = {"n_fido", "importo_euro", "scadenza", "tipo_op", "rapporto"}
SOGG = {f"{p}_{i}" for p in ("ndg", "denominazione", "ruolo") for i in range(1, 5)}
OK = {"correct", "correct_null"}


def group(records: list[dict], fields: set[str]) -> dict:
    nn = [r for r in records if r["field"] in fields and r["expected"] is not None]
    hit = sum(r["status"] == "correct" for r in nn)
    uniq: dict[tuple, bool] = {}
    for r in nn:
        key = (r["practice"], r["field"], str(r["expected"]))
        uniq[key] = uniq.get(key, True) and r["status"] == "correct"
    nulls = [r for r in records if r["field"] in fields and r["expected"] is None]
    return {"non_null": f"{hit}/{len(nn)}", "unique_values_all_correct": f"{sum(uniq.values())}/{len(uniq)}",
            "nulls_correct": f"{sum(r['status'] == 'correct_null' for r in nulls)}/{len(nulls)}",
            "hallucinated": sum(r["status"] == "hallucinated" for r in records if r["field"] in fields)}


def summarize(report: dict, split: str) -> dict:
    recs = [r for r in report["records"] if r["split"] == split]
    nn = [r for r in recs if r["expected"] is not None]
    per_practice = defaultdict(lambda: [0, 0])
    for r in recs:
        per_practice[r["practice"]][0] += r["status"] in OK
        per_practice[r["practice"]][1] += 1
    uniq: dict[tuple, bool] = {}
    for r in recs:
        key = (r["practice"], r["field"], str(r["expected"]))
        uniq[key] = uniq.get(key, True) and r["status"] in OK
    avail = report["by_split"][split]["content_availability"]
    return {
        "strict": f"{sum(r['status'] in OK for r in recs)}/{len(recs)}",
        "non_null_correct": f"{sum(r['status'] == 'correct' for r in nn)}/{len(nn)}",
        "counts": report["by_split"][split]["counts"],
        "ocr_available_non_null": f"{avail['non_null_available']}/{avail['non_null_total']}",
        "unique_values_all_correct": f"{sum(uniq.values())}/{len(uniq)}",
        "per_practice": {p: f"{a}/{b}" for p, (a, b) in sorted(per_practice.items())},
        "fidi": group(recs, FIDI), "soggetti": group(recs, SOGG),
        "by_field": {f: f"{sum(r['status'] in OK for r in recs if r['field'] == f)}/{sum(1 for r in recs if r['field'] == f)}"
                     for f in sorted({r["field"] for r in recs})},
    }


result = {}
reference_values = None
for label, run_dir, examples_path in runs:
    run, examples = Path(run_dir), json.loads(Path(examples_path).read_text(encoding="utf-8"))
    values = {e["id"]: e["values"] for e in examples}
    if reference_values is None:
        reference_values = values
    elif values != reference_values:
        raise SystemExit(f"{label}: reviewed values differ from the first run")
    result[label] = {}
    for name, split in (("validation", "val"), ("test", "test")):
        preds = json.loads((run / f"{name}_predictions.json").read_text(encoding="utf-8"))
        selected = [e for e in examples if e["split"] == split]
        if {e["id"] for e in selected} != set(preds):
            raise SystemExit(f"{run}: ids differ for {split}")
        if any(len(preds[e["id"]]["pred"]) != len(e["words"]) for e in selected):
            raise SystemExit(f"{run}: word counts differ for {split}")
        report = evaluate_predictions(selected, preds)
        result[label][split] = summarize(report, split)
        result[label][split]["word_micro_f1"] = report["by_split"][split]["word_metrics"].get("micro", {}).get("f1")
        result[label][split]["records"] = [{k: r[k] for k in ("id", "field", "expected", "predicted", "status", "content_available")}
                                           for r in report["records"]]

gates = {"G4_min_val": math.ceil(0.88 * 146), "G4_target_val": math.ceil(0.92 * 146),
         "G5_fidi_val": math.ceil(0.90 * 25), "G5_soggetti_val": math.ceil(0.92 * 15)}
result["gate_minimums"] = gates
out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
for label, _, _ in runs:
    for split in ("val", "test"):
        s = result[label][split]
        print(f"{label} {split}: strict {s['strict']} non-null {s['non_null_correct']} unique {s['unique_values_all_correct']} "
              f"OCR {s['ocr_available_non_null']} Fidi {s['fidi']['non_null']} (unique {s['fidi']['unique_values_all_correct']}) "
              f"Soggetti {s['soggetti']['non_null']} (unique {s['soggetti']['unique_values_all_correct']}) "
              f"per practice {s['per_practice']} hallucinated {s['counts'].get('hallucinated')}")
print("gate minimums", gates)
