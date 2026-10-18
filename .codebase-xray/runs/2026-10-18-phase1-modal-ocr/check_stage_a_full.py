"""Recount the full stage A comparison (A0-A4) from each run's derived alignment report.

Usage: python -I check_stage_a_full.py
Independent of ocr_selection_metrics(): counts exact non-null OCR text on validation, the
6->8 readings and the identifier fields on train+val, and the validation values that no
configuration reads exactly (the ceiling of any choice or combination of A0-A4 for G1).
Exits 1 if a recount differs from the figures quoted in report.md.
"""
import csv
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
RUNS = {"A0": HERE.parent / "2026-10-18-phase1-ocr/A0-pc4", "A1": HERE / "medium/A1/run",
        "A2": HERE / "medium/A2/run", "A3": HERE / "medium/A3/run", "A4": HERE.parent / "2026-10-18-phase1-ocr/A4-pc4"}
QUOTED = {"A0": (124, 21, 28, 11), "A1": (126, 26, 29, 0), "A2": (124, 26, 29, 0),
          "A3": (121, 26, 28, 0), "A4": (120, 21, 18, 19)}
QUOTED_CEILING = 130
NDG = {f"ndg_{i}" for i in range(1, 5)}


def six_as_eight(expected: str, ocr: str) -> bool:
    want, got = re.sub(r"\D", "", expected), re.sub(r"\D", "", ocr)
    return bool(want) and len(want) == len(got) and want != got and all(
        (a, b) == ("6", "8") for a, b in zip(want, got) if a != b)


results, exact_val = [], {}
for config, run in RUNS.items():
    with open(run / "dataset" / "alignment_report.csv", encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.DictReader(fh, delimiter=";") if r["split"] in ("train", "val") and r["expected"].strip()]
    val = [r for r in rows if r["split"] == "val"]
    exact_val[config] = {(r["screen"], r["field"]) for r in val if r["exact_text"] == "True"}
    got = (len(exact_val[config]),
           sum(r["exact_text"] == "True" for r in rows if r["field"] in NDG),
           sum(r["exact_text"] == "True" for r in rows if r["field"] == "rapporto"),
           sum(six_as_eight(r["expected"], r["ocr_text"]) for r in rows))
    results.append((f"{config} val OCR, train+val NDG, rapporto, 6->8 = {got}", got == QUOTED[config], str(QUOTED[config])))
    results.append((f"{config} validation population is 133", len(val) == 133, str(len(val))))

ceiling = len(set().union(*exact_val.values()))
results.append((f"values read exactly by at least one configuration: {ceiling}/133", ceiling == QUOTED_CEILING, str(QUOTED_CEILING)))
with open(RUNS["A0"] / "dataset" / "alignment_report.csv", encoding="utf-8-sig", newline="") as fh:
    never = [(r["screen"], r["field"]) for r in csv.DictReader(fh, delimiter=";")
             if r["split"] == "val" and r["expected"].strip()
             and (r["screen"], r["field"]) not in set().union(*exact_val.values())]
for name, ok, detail in results:
    print("PASS" if ok else "FAIL", name, "" if ok else f"-> expected {detail}")
print("never read exactly on validation:", never)
print(f"{sum(ok for _, ok, _ in results)}/{len(results)} checks passed")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
