"""Recount the stage A comparison directly from each run's derived alignment report.

Usage: python -I check_stage_a.py <runs_dir>
Independent of ocr_selection_metrics(): counts exact non-null OCR text per split from
dataset/alignment_report.csv and compares with stage-a-compare.json. Exits 1 on mismatch.
"""
import csv
import json
import sys
from pathlib import Path

runs = Path(sys.argv[1])
compare = json.loads((runs / "stage-a-compare.json").read_text(encoding="utf-8"))
results: list[tuple[str, bool, str]] = []
NDG = {f"ndg_{i}" for i in range(1, 5)}

for config in ("A0", "A4"):
    with open(runs / f"{config}-pc4" / "dataset" / "alignment_report.csv", encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.DictReader(fh, delimiter=";") if r["expected"].strip()]
    for split in ("train", "val"):
        chosen = [r for r in rows if r["split"] == split]
        got = f"{sum(r['exact_text'] == 'True' for r in chosen)}/{len(chosen)}"
        results.append((f"{config} {split} OCR non-null {got}", got == compare[config][split]["ocr_non_null"],
                        compare[config][split]["ocr_non_null"]))
    tv = [r for r in rows if r["split"] in ("train", "val")]
    for label, fields in (("subject_ndg", NDG), ("rapporto", {"rapporto"})):
        chosen = [r for r in tv if r["field"] in fields]
        got = f"{sum(r['exact_text'] == 'True' for r in chosen)}/{len(chosen)}"
        results.append((f"{config} train+val {label} {got}", got == compare[config]["train_val"][label],
                        compare[config]["train_val"][label]))
    results.append((f"{config} has no historical test row in the comparison",
                    all(r["split"] != "test" for r in tv), ""))

expected = {"A0": ("562/613", "124/133", "28/29"), "A4": ("553/613", "120/133", "18/29")}
for config, (train, val, rap) in expected.items():
    got = (compare[config]["train"]["ocr_non_null"], compare[config]["val"]["ocr_non_null"], compare[config]["train_val"]["rapporto"])
    results.append((f"{config} figures quoted in the report {expected[config]}", got == expected[config], str(got)))

for name, ok, detail in results:
    print("PASS" if ok else "FAIL", name, "" if ok else f"-> {detail}")
print(f"{sum(ok for _, ok, _ in results)}/{len(results)} checks passed")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
