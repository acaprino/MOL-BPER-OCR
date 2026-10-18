"""Compare a fresh RapidOCR cache with the historic one the v3.1 bundle is built from.

Usage: python -I compare_a0.py <historic.json> <rerun.json> [<rebuilt_alignment_report.csv> <bundle_alignment_report.csv>]
Reports token-level identity per screen, box and score deltas, timing and, when the
two alignment reports are given, the effect on exact OCR availability per split.
"""
import csv
import json
import statistics
import sys
from collections import Counter

old = json.load(open(sys.argv[1], encoding="utf-8"))
new = json.load(open(sys.argv[2], encoding="utf-8"))
print("screens:", len(old), len(new), "same ids:", set(old) == set(new))

identical_text = identical_all = 0
box_deltas: list[float] = []
score_deltas: list[float] = []
text_diffs = []
for sid in sorted(old):
    a, b = old[sid]["items"], new[sid]["items"]
    ta, tb = [i[0] for i in a], [i[0] for i in b]
    if ta == tb:
        identical_text += 1
        for x, y in zip(a, b):
            score_deltas.append(abs(x[1] - y[1]))
            box_deltas.extend(abs(p - q) for pa, pb in zip(x[2], y[2]) for p, q in zip(pa, pb))
        if a == b:
            identical_all += 1
    else:
        sa, sb = Counter(ta), Counter(tb)
        text_diffs.append((sid, len(ta), len(tb), sorted((sa - sb).elements())[:6], sorted((sb - sa).elements())[:6]))
print(f"screens with identical token texts and order: {identical_text}/{len(old)}; fully identical items: {identical_all}")
if box_deltas:
    print(f"on identical-text screens: max box delta {max(box_deltas):.4f}px, max score delta {max(score_deltas):.6f}")
for sid, na, nb, only_old, only_new in text_diffs:
    print(f"  {sid}: tokens {na} -> {nb}; only historic {only_old}; only rerun {only_new}")

times = [new[s]["seconds"] for s in sorted(new)][1:]
hist = [old[s]["seconds"] for s in sorted(old)][1:]
print(f"seconds per screen (first excluded): rerun mean {statistics.mean(times):.2f} max {max(times):.2f}; "
      f"historic mean {statistics.mean(hist):.2f} max {max(hist):.2f}")

if len(sys.argv) > 4:
    def load(path: str) -> dict:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            return {(r["screen"], r["field"]): r for r in csv.DictReader(fh, delimiter=";")}
    ra, rb = load(sys.argv[3]), load(sys.argv[4])
    for split in ("train", "val", "test"):
        keys = [k for k, r in rb.items() if r["split"] == split and r["expected"].strip()]
        ea = sum(ra[k]["exact_text"] == "True" for k in keys)
        eb = sum(rb[k]["exact_text"] == "True" for k in keys)
        print(f"{split}: exact non-null OCR text rerun {ea}/{len(keys)} vs bundle {eb}/{len(keys)}")
    changed = [(k, rb[k]["ocr_text"], ra[k]["ocr_text"]) for k in rb if ra[k]["exact_text"] != rb[k]["exact_text"]]
    for (screen, field), before, after in sorted(changed):
        print(f"  changed {screen} {field}: {before!r} -> {after!r}")
    print("supervision rerun:", dict(Counter(r["supervision"] for r in ra.values())))
