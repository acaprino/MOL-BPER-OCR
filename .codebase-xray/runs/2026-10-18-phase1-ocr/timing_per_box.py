"""Per-screen cost of A1 and A3 against A0, normalized by the number of OCR text boxes.

Usage: python -I timing_per_box.py <phase1_run_dir>
A cost inflated by paging or by a passing load would vary from screen to screen and between
the two chains; a cost intrinsic to the recognizer stays proportional to the boxes it reads.
Exits 1 if the per-box cost of A1 or A3 is not stable within the stated band.
"""
import json
import statistics
import sys
from pathlib import Path

run = Path(sys.argv[1])


def load(name: str) -> dict[str, tuple[float, int]]:
    out = {}
    for path in (run / name / "screens").glob("*.json"):
        if path.name.endswith(".error.json"):
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        out[path.stem] = (record["seconds"], len(record["items"]))
    return out


a0, a1, a3 = load("A0-pc4"), load("A1-pc4"), load("A3-pc4-cost-sample3")
ratios, per_box = [], []
for screen in sorted(a1):
    (s0, n0), (s1, n1) = a0[screen], a1[screen]
    ratios.append(s1 / s0)
    per_box.append(s1 / n1)
    print(f"A1 {screen:40s} A0 {s0:5.2f}s/{n0:3d} boxes  A1 {s1:6.1f}s/{n1:3d} boxes  x{s1 / s0:4.1f}  {s1 / n1:.2f} s/box")
a3_per_box = []
for screen in sorted(a3):
    s3, n3 = a3[screen]
    a3_per_box.append(s3 / n3)
    print(f"A3 {screen:40s} {s3:6.1f}s/{n3:3d} boxes  {s3 / n3:.2f} s/box")
print(f"A1 vs A0 ratio min/median/max: {min(ratios):.1f} {statistics.median(ratios):.1f} {max(ratios):.1f}")
print(f"A1 s/box min/median/max: {min(per_box):.2f} {statistics.median(per_box):.2f} {max(per_box):.2f}")
stable = 0.8 <= min(per_box) and max(per_box) <= 1.4 and all(0.8 <= x <= 1.4 for x in a3_per_box)
print("PASS" if stable else "FAIL", "A1 and A3 per-box cost within 0.8-1.4 s on every screen")
sys.exit(0 if stable else 1)
