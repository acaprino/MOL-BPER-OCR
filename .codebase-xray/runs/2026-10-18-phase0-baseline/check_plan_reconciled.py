"""Recompute every figure the reconciliation added to docs/next-ver-plan.md.

Usage: python -I check_plan_reconciled.py <repo_root> <plan-before.md> <plan-after.md>
Exits 1 if any check fails.
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

root, before_path, after_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
REC = root / ".codebase-xray/runs/2026-10-18-phase0-reconciliation"
RUN = root / "data/training/runs/lilt-v3.1-20261016"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


val = load(REC / "validation_field_metrics_current_examples.json")
test = load(REC / "test_field_metrics_current_examples.json")
saved_test = load(RUN / "test_field_metrics.json")
result = load(RUN / "result.json")
current_manifest = load(root / "data/training/ground-truth-v3.1/manifest.json")

run_manifest = result["manifest"]["dataset_manifest"]
check("run and bundle share OCR e261c05b",
      run_manifest["ocr"]["sha256"] == current_manifest["ocr"]["sha256"] and run_manifest["ocr"]["sha256"].startswith("e261c05b"),
      f"{run_manifest['ocr']['sha256']} vs {current_manifest['ocr']['sha256']}")
rs, cs = run_manifest["supervision_counts"], current_manifest["supervision_counts"]
check("supervision 844/55 in run, 863/31 now",
      (rs["supervised"], rs["ignored_ocr_mismatch"], cs["supervised"], cs["ignored_ocr_mismatch"]) == (844, 55, 863, 31),
      f"{rs} / {cs}")

summary = load(REC / "reconciliation_summary.json")
changed = sum(len(load(REC / f"{n}_record_diff.json")) for n in ("validation", "test"))
check("338 records, only content_available changed",
      summary["validation"]["records"] + summary["test"]["records"] == 338
      and all(set(summary[n]["changed_attributes"]) <= {"content_available"} for n in ("validation", "test")),
      f"{summary['validation']['changed_attributes']} {summary['test']['changed_attributes']} rows={changed}")


def frac(report: dict, key: str, total: str) -> tuple[int, int]:
    a = report["overall"]["content_availability"]
    return a[key], a[total]


check("strict 115/146 and 127/192",
      (round(val["overall"]["accuracy"] * 146), round(test["overall"]["accuracy"] * 192)) == (115, 127), "")
check("non-null availability 124/133 and 178/183",
      (frac(val, "non_null_available", "non_null_total"), frac(test, "non_null_available", "non_null_total")) == ((124, 133), (178, 183)),
      "")
avail, total = frac(test, "available", "total")
check("test availability 187/192 = 97,40%", (avail, total) == (187, 192) and f"{avail / total * 100:.2f}" == "97.40",
      f"{avail}/{total}")

saved_unavail = [r for r in saved_test["records"] if r["content_available"] is False]
saved_rap = [r for r in saved_unavail if r["field"] == "rapporto"]
check("saved test: 13 unavailable, 9 rapporto", (len(saved_unavail), len(saved_rap)) == (13, 9), f"{len(saved_unavail)}, {len(saved_rap)}")
now = {(r["id"], r["field"]): r for r in test["records"]}
flipped = [r for r in saved_rap if now[(r["id"], r["field"])]["content_available"]]
check("8 of those 9 rapporto are available now", len(flipped) == 8, str(len(flipped)))
p51 = [r for r in flipped if r["id"].startswith("51531667__GestioneFidi_Tooltip")]
check("6 flipped are 034 0744 0017 05502254 on 51531667 Tooltip1..6",
      len(p51) == 6 and {r["expected"] for r in p51} == {"034 0744 0017 05502254"}
      and sorted(r["id"][-1] for r in p51) == list("123456"), str([r["id"] for r in p51]))
p52 = [r for r in flipped if r["id"].startswith("52060489__")]
check("2 flipped on 52060489 already correct", len(p52) == 2 and all(now[(r["id"], "rapporto")]["status"] == "correct" for r in p52),
      str([(r["id"], now[(r['id'], 'rapporto')]['status']) for r in p52]))
still = sorted((r["id"], r["field"]) for r in test["records"] if r["expected"] is not None and not r["content_available"])
check("test still unavailable: rapporto GestioneFidi, ndg_1, ndg_2, two notes",
      still == sorted([("52060489__GestioneFidi", "rapporto"), ("52060489__Soggetti", "ndg_1"), ("52060489__Soggetti", "ndg_2"),
                       ("51531667__Note", "note_della_richiesta"), ("52060489__Note", "note_della_richiesta")]), str(still))

with open(root / "data/training/ground-truth-v3.1/alignment_report.csv", encoding="utf-8-sig", newline="") as fh:
    rows = list(csv.DictReader(fh, delimiter=";"))
fidi52 = sorted({r["screen"] for r in rows if r["practice"] == "52060489" and r["screen"].startswith("52060489__GestioneFidi")})
check("52060489 has 4 GestioneFidi screens", len(fidi52) == 4, str(fidi52))

rap = [r for r in test["records"] if r["field"] == "rapporto" and r["status"] != "correct"]
stage_b = [r for r in rap if r["content_available"]]
merged = [r for r in stage_b if r["predicted"] and r["predicted"].count("0744") > 1]
down = [r for r in stage_b if r["id"] == "51531667__GestioneFidi_down" and r["predicted"] is None]
check("rapporto: 9 errors, 8 with OCR available, all on 51531667 (7 merged, _down missing)",
      len(rap) == 9 and len(stage_b) == 8 and all(r["practice"] == "51531667" for r in stage_b)
      and len(merged) == 7 and len(down) == 1, f"errors={len(rap)} stage_b={len(stage_b)} merged={len(merged)} down={len(down)}")
rap_av = sum(1 for r in test["records"] if r["field"] == "rapporto" and r["content_available"])
check("test rapporto availability 11/12", rap_av == 11, str(rap_av))

val_missing = sorted((r["id"], r["field"], r["expected"]) for r in val["records"] if r["expected"] is not None and not r["content_available"])
check("validation: 9 non-null unavailable", len(val_missing) == 9, str(len(val_missing)))
ids = {(i, f) for i, f, _ in val_missing}
check("validation gaps match the plan list", ids == {
    ("51659595__GestioneFidi_Tooltip1", "scadenza"), ("51659595__GestioneFidi_Tooltip2", "scadenza"),
    ("51659595__GestioneFidi_Tooltip2", "tipo_op"), ("51659595__Soggetti", "filiale_relazione"),
    ("51659595__Soggetti", "denominazione"), ("52126316__GestioneFidi_Tooltip1", "importo_euro"),
    ("51659595__Elenco_dx", "tipo"), ("51659595__Note", "note_della_richiesta"), ("52126316__Note", "note_della_richiesta")},
    str(sorted(ids)))
ocr_text = {(r["screen"], r["field"]): r for r in rows}
spot = {
    ("51659595__GestioneFidi_Tooltip2", "tipo_op"): "Nuova Fnanza",
    ("51659595__Soggetti", "filiale_relazione"): "21 - STELFRANCO",
    ("51659595__Soggetti", "denominazione"): "-LANDOGNA CORRADO",
    ("52126316__GestioneFidi_Tooltip1", "importo_euro"): "180,000",
}
check("validation OCR texts as quoted", all(ocr_text[k]["ocr_text"] == v for k, v in spot.items()),
      str({k: ocr_text[k]["ocr_text"] for k in spot}))
check("301 mesi has no OCR text and BMB is ignored_alignment",
      all(ocr_text[(s, "scadenza")]["ocr_text"] == "" for s in ("51659595__GestioneFidi_Tooltip1", "51659595__GestioneFidi_Tooltip2"))
      and ocr_text[("51659595__Elenco_dx", "tipo")]["supervision"] == "ignored_alignment", "")

before, after = before_path.read_text(encoding="utf-8"), after_path.read_text(encoding="utf-8")

b0 = load(root / ".codebase-xray/runs/2026-10-18-phase0-baseline/lilt-compare.json")
new, old = b0["new_lilt-v3.1-20261018-current-bundle"], b0["old_lilt-v3.1-20261016"]
check("B0 val strict 124/146, per practice 52/72 and 72/74, test 144/192",
      (new["val"]["strict"], new["val"]["per_practice"], new["test"]["strict"])
      == ("124/146", {"51659595": "52/72", "52126316": "72/74"}, "144/192"), str(new["val"]["per_practice"]))
check("B0 Fidi val 19/25 (5/10 unique), test 25/60; Soggetti val 15/15, test 19/21",
      (new["val"]["fidi"]["non_null"], new["val"]["fidi"]["unique_values_all_correct"], new["test"]["fidi"]["non_null"],
       new["val"]["soggetti"]["non_null"], new["test"]["soggetti"]["non_null"]) == ("19/25", "5/10", "25/60", "15/15", "19/21"), "")
check("old run Fidi 13/25 and 20/60, Soggetti 10/15 and 10/21",
      (old["val"]["fidi"]["non_null"], old["test"]["fidi"]["non_null"], old["val"]["soggetti"]["non_null"],
       old["test"]["soggetti"]["non_null"]) == ("13/25", "20/60", "10/15", "10/21"), "")
check("plan G4 and G5 rows cite the current-bundle B0",
      "B0 sul bundle corrente: validazione **124/146**" in after and "Fidi val **19/25**" in after
      and "`lilt-v3.1-20261018-current-bundle`" in after, "")
a0 = (root / ".codebase-xray/runs/2026-10-18-phase0-baseline/a0-compare.txt").read_text(encoding="utf-8")
check("A0 113/113 identical", "identical token texts and order: 113/113; fully identical items: 113" in a0, "")
new_run = load(RUN.parent / "lilt-v3.1-20261018-current-bundle/result.json")["manifest"]
check("B0 checkpoint rule is validation whole-field accuracy",
      new_run["checkpoint_selection"].startswith("validation whole-field accuracy")
      and result["manifest"]["checkpoint_selection"] == "validation word micro F1 only", new_run["checkpoint_selection"])
check("no em dash added", after.count("—") == before.count("—"), f"{before.count(chr(0x2014))} -> {after.count(chr(0x2014))}")
check("old 9-on-9-screens claim removed", "ripetuto sulle 9 schermate" not in after, "")
check("code fences balanced", after.count("```") % 2 == 0, "")
check("no trailing whitespace on new lines",
      all(not l.endswith((" ", "\t")) or l in before.splitlines() for l in after.splitlines()), "")

for name, ok, detail in results:
    print("PASS" if ok else "FAIL", name, "" if ok else f"-> {detail}")
print(f"{sum(ok for _, ok, _ in results)}/{len(results)} checks passed")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
