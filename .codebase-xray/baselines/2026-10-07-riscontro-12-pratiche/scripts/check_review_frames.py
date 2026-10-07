"""Check the frames of the review workbook without looking at them: what the OCR reads inside each one.

Usage (cwd = repo root): python check_review_frames.py <input_dir> <baseline_dir> [frames.json]

For every value with a red frame (notes excluded) the OCR words whose centre falls inside the frame
are joined and compared with the transcribed value, the small 6 and 8 counted as the same digit:
  uguale        the frame holds the value and nothing else
  quasi         same text but for one or two characters the OCR read differently
  testo in piu  the frame also holds something else (an icon between two letters, a label)
  manca testo   part of the value is outside the frame: a wrong frame
It also lists, per page and field, the frames far from where the same field sits on the other
practices. Exit code 1 when a frame misses text. Optionally writes every frame to a JSON file.
"""
import csv
import difflib
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image

input_dir, baseline_dir = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
frames_path = sys.argv[3] if len(sys.argv) > 3 else None
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0], input_dir, baseline_dir, "unused.xlsx", "unused"]  # the module reads its paths at import
import make_review_workbook as review  # noqa: E402

with open(os.path.join(input_dir, "dati.csv"), encoding="utf-8-sig", newline="") as fh:
    gt_rows = list(csv.DictReader(fh, delimiter=";"))
with open(os.path.join(baseline_dir, "prove", "ocr-locale-rapidocr", "rapid_v6_small_1x.json"), encoding="utf-8") as fh:
    ocr = json.load(fh)
by_screen: Dict[str, List[dict]] = {}
for row in gt_rows:
    by_screen.setdefault(row["Fotogramma"], []).append(row)

frames: List[dict] = []
verdicts: Counter = Counter()
flagged: List[Tuple[str, str, str, str, str]] = []
places: Dict[Tuple[str, str], List[Tuple[str, float, float]]] = defaultdict(list)
for screen, rows in sorted(by_screen.items()):
    arr = np.asarray(Image.open(os.path.join(input_dir, screen + ".png")).convert("RGB"))
    lines = [{"text": t, "score": s, "box": b} for t, s, b in ocr[screen]["items"]]
    stem = screen.split("__", 1)[1]
    located = review.locate_screen(stem, [(r["Denominazione da attribuire"], r["Valore rilevato"]) for r in rows], lines, arr)
    words, _ = review.build_words(lines, arr)
    for row in rows:
        field, value = row["Denominazione da attribuire"], row["Valore rilevato"]
        box, how = located[field]
        frames.append({"screen": screen, "field": field, "value": value, "how": how, "box": None if box is None else list(box)})
        verdicts["riquadro " + how] += 1
        if how != "esatta" or field in review.NOTE_FIELDS or box is None:
            continue
        x0, y0, x1, y1 = box
        places[(review.kind_of(stem), field)].append((screen, x0, (y0 + y1) / 2))
        inside = [w for w in words if x0 - 1 <= (w["x0"] + w["x1"]) / 2 <= x1 + 1 and y0 - 1 <= (w["y0"] + w["y1"]) / 2 <= y1 + 1]
        inside.sort(key=lambda w: (round((w["y0"] + w["y1"]) / 16), w["x0"]))
        got = review.norm(review.fold("".join(w["text"] for w in inside)))
        want = review.norm(review.fold(value))
        if got == want:
            verdict = "uguale"
        elif sorted(got) == sorted(want) or difflib.SequenceMatcher(None, want, got).ratio() >= 0.88:
            verdict = "quasi"
        else:
            verdict = "manca testo" if len(got) < len(want) else "testo in piu"
        verdicts[verdict] += 1
        if verdict != "uguale":
            flagged.append((verdict, screen, field, value, " ".join(w["text"] for w in inside)))

print(dict(verdicts))
for verdict, screen, field, value, read in sorted(flagged):
    print(f"  {verdict:12s} {screen[:34]:34s} {field[:24]:24s} valore={value[:34]!r} dentro={read[:44]!r}")
print("posizioni lontane dalla mediana del campo sulla stessa pagina (oltre 50 px in orizzontale o 60 in verticale):")
for (kind, field), items in sorted(places.items()):
    mx, my = statistics.median(x for _, x, _ in items), statistics.median(y for _, _, y in items)
    for screen, x, y in items:
        if abs(x - mx) > 50 or abs(y - my) > 60:
            print(f"  {kind:22s} {field[:26]:26s} {screen[:36]:36s} x={x:5.0f} (mediana {mx:5.0f}) y={y:5.0f} (mediana {my:5.0f})")
if frames_path:
    with open(frames_path, "w", encoding="utf-8") as fh:
        json.dump(frames, fh, ensure_ascii=False)
sys.exit(1 if verdicts["manca testo"] else 0)
