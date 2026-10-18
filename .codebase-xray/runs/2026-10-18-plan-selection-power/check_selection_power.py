"""Recompute every figure added to docs/next-ver-plan.md in this run.

Usage: python -I check_selection_power.py <alignment_report.csv> <plan-before.md> <plan-after.md>
Exits 1 if any check fails.
"""
import csv
import math
import re
import sys
from collections import defaultdict

csv_path, before_path, after_path = sys.argv[1:4]
with open(csv_path, encoding="utf-8-sig", newline="") as fh:
    rows = list(csv.DictReader(fh, delimiter=";"))

FIDI = {"n_fido", "importo_euro", "scadenza", "tipo_op", "rapporto"}
SUBJECT_NDG = {f"ndg_{i}" for i in range(1, 5)}
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def six_to_eight(row: dict[str, str]) -> bool:
    """True when the OCR text differs from the expected value only by 6 read as 8."""
    if not row["expected"].strip() or row["exact_text"] == "True":
        return False
    exp, ocr = digits(row["expected"]), digits(row["ocr_text"])
    if not exp or len(exp) != len(ocr) or exp == ocr:
        return False
    return all((a, b) == ("6", "8") for a, b in zip(exp, ocr) if a != b)


hits = defaultdict(list)
for r in rows:
    if six_to_eight(r):
        hits[r["split"]].append(r)

train = hits["train"]
check("train 6->8 observations = 10", len(train) == 10, str(len(train)))
check("train 6->8 practices = 4", len({r["practice"] for r in train}) == 4,
      str(sorted({r["practice"] for r in train})))
distinct = {(r["practice"], r["field"], r["expected"]) for r in train}
check("train 6->8 distinct values = 8", len(distinct) == 8, str(len(distinct)))
ndg_obs = [r for r in train if r["field"] in SUBJECT_NDG]
check("train 6->8 subject NDG observations = 5", len(ndg_obs) == 5, str(len(ndg_obs)))
rap = [r for r in train if r["field"] == "rapporto"]
check("train 6->8 rapporto observations = 1", len(rap) == 1, str(len(rap)))
sca = [r for r in train if r["field"] == "scadenza"]
sca_ok = (len(sca) == 4
          and all(r["expected"] == "361 mesi" and r["ocr_text"] == "381 mesi" for r in sca)
          and sorted({r["practice"] for r in sca}) == ["52068422", "52135039"]
          and all(sum(1 for x in sca if x["practice"] == p) == 2 for p in ("52068422", "52135039")))
check("train 6->8 scadenza '361 mesi'->'381 mesi', 2 screens in 52068422 and 52135039", sca_ok,
      str([(r["screen"], r["ocr_text"]) for r in sca]))

val = hits["val"]
val_ok = (len(val) == 1 and val[0]["screen"] == "52126316__GestioneFidi_Tooltip1"
          and val[0]["field"] == "importo_euro" and val[0]["expected"] == "160.000"
          and val[0]["ocr_text"] == "180,000")
check("val 6->8 = one importo_euro 160.000 -> 180,000 in 52126316__GestioneFidi_Tooltip1", val_ok,
      str([(r["screen"], r["field"], r["expected"], r["ocr_text"]) for r in val]))

test = hits["test"]
test_fields = sorted(r["field"] for r in test)
check("test 6->8 = rapporto + ndg_1 + ndg_2", test_fields == ["ndg_1", "ndg_2", "rapporto"], str(test_fields))
test_rap = [r for r in rows if r["split"] == "test" and r["field"] == "rapporto" and r["expected"].strip()]
test_rap_ok = sum(r["exact_text"] == "True" for r in test_rap)
check("test rapporto exact = 11/12", (test_rap_ok, len(test_rap)) == (11, 12), f"{test_rap_ok}/{len(test_rap)}")

six = eight = 0
for r in rows:
    if (r["split"] == "val" and r["expected"].strip() and r["exact_text"] == "True"
            and r["field"] in FIDI | SUBJECT_NDG):
        six += r["expected"].count("6")
        eight += r["expected"].count("8")
check("val correctly read 6 and 8 digits in Fidi + subject NDG = 15 and 12", (six, eight) == (15, 12),
      f"{six} and {eight}")

fidi_val = [r for r in rows if r["split"] == "val" and r["field"] in FIDI and r["expected"].strip()]
check("val Fidi non-null = 25", len(fidi_val) == 25, str(len(fidi_val)))
uniq = {(r["practice"], r["field"], r["expected"]) for r in fidi_val}
check("val Fidi unique values = 10", len(uniq) == 10, str(len(uniq)))
for practice, n_screens in (("51659595", 2), ("52126316", 3)):
    pr = [r for r in fidi_val if r["practice"] == practice]
    n_vals = len({(r["field"], r["expected"]) for r in pr})
    screens = len({r["screen"] for r in pr})
    repeated = all(sum(1 for r in pr if (r["field"], r["expected"]) == v) == n_screens
                   for v in {(r["field"], r["expected"]) for r in pr})
    check(f"val Fidi {practice}: 5 values on {n_screens} screens each", (n_vals, screens, repeated) == (5, n_screens, True),
          f"values={n_vals} screens={screens} every value on every screen={repeated}")

need = math.ceil(0.90 * 25)
check("G5 Fidi minimum ceil(0.90*25) = 23", need == 23, str(need))
check("one wrong value in 52126316 -> 22/25 fails, in 51659595 -> 23/25 passes",
      25 - 3 < need <= 25 - 2, f"{25 - 3} vs {25 - 2} against {need}")

for split, (ndg, rap_) in (("val", ((5, 5), (5, 5))),):
    n = [r for r in rows if r["split"] == split and r["field"] in SUBJECT_NDG and r["expected"].strip()]
    p = [r for r in rows if r["split"] == split and r["field"] == "rapporto" and r["expected"].strip()]
    got = ((sum(r["exact_text"] == "True" for r in n), len(n)), (sum(r["exact_text"] == "True" for r in p), len(p)))
    check("val G3 saturated: subject NDG 5/5, rapporto 5/5", got == (ndg, rap_), str(got))

practices = {s: {r["practice"] for r in rows if r["split"] == s} for s in ("train", "val")}
check("train + val practices = 10", len(practices["train"] | practices["val"]) == 10,
      str(len(practices["train"] | practices["val"])))

with open(before_path, encoding="utf-8") as fh:
    before = fh.read()
with open(after_path, encoding="utf-8") as fh:
    after = fh.read()
check("no em dash added", after.count("—") == before.count("—"),
      f"before={before.count(chr(0x2014))} after={after.count(chr(0x2014))}")
check("code fences balanced", after.count("```") % 2 == 0, str(after.count("```")))
check("no conflict markers", not re.search(r"^(<<<<<<<|=======|>>>>>>>)", after, re.M), "")
check("no trailing whitespace on added lines",
      all(not line.endswith((" ", "\t")) or line in before.splitlines() for line in after.splitlines()), "")
check("validation-only selection phrase removed from Phase 1",
      "rendere disponibili alla selezione soltanto i risultati di validazione" not in after, "")

failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("PASS" if ok else "FAIL"), name, ("" if ok else f"-> {detail}"))
print(f"{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
