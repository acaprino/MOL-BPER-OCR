"""Throwaway probe: can classic OCR read the 9 BPER screens? Speed and GT recall per config.

Recall: a GT value counts as found when its whitespace-free lowercase form is a
substring of the whitespace-free lowercase OCR text of that screen. The long
request note is scored by word recall instead (words of 3+ chars).
"""

import csv
import json
import re
import sys
import time
from pathlib import Path

from PIL import Image

REPO = Path(r"D:\Projects\poc-data-extraction")
OUT = Path(__file__).resolve().parent / "ocr_probe_out"
OUT.mkdir(exist_ok=True)


def load_gt():
    gt = {}
    with open(REPO / "mnt/data/dati.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            value = row["Valore rilevato"].strip()
            if value:
                gt.setdefault(row["Fotogramma"].strip(), []).append((row["Denominazione da attribuire"].strip(), value))
    return gt


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def score(gt_rows, lines):
    text = " ".join(t for t, _, _ in lines)
    flat = squash(text)
    words = set(re.findall(r"\w{3,}", text.lower()))
    found, missing, note_recall = 0, [], None
    for key, value in gt_rows:
        if len(value) > 120:
            gw = re.findall(r"\w{3,}", value.lower())
            note_recall = sum(w in words for w in gw) / len(gw)
            continue
        if squash(value) in flat:
            found += 1
        else:
            missing.append((key, value))
    return found, missing, note_recall


def images(scale):
    for i in range(1, 10):
        im = Image.open(REPO / f"mnt/data/screen {i}.png").convert("RGB")
        if scale != 1:
            im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
        yield f"screen {i}", im


def run(label, ocr_fn, scales=(1, 2)):
    gt = load_gt()
    report = {}
    for scale in scales:
        ims = list(images(scale))
        ocr_fn(ims[0][1])  # warm-up: model load, first-run allocations
        tot_found = tot = 0
        times, all_missing, notes, dump = [], {}, [], {}
        for sid, im in ims:
            t0 = time.perf_counter()
            lines = ocr_fn(im)
            times.append(time.perf_counter() - t0)
            rows = gt.get(sid, [])
            found, missing, nr = score(rows, lines)
            tot_found += found
            tot += sum(1 for _, v in rows if len(v) <= 120)
            if missing:
                all_missing[sid] = missing
            if nr is not None:
                notes.append(round(nr, 3))
            dump[sid] = [{"text": t, "score": round(float(s), 3), "box": b} for t, s, b in lines]
        key = f"{label} @{scale}x"
        report[key] = {
            "found": tot_found, "total": tot,
            "sec_per_screen_mean": round(sum(times) / len(times), 2),
            "sec_per_screen_max": round(max(times), 2),
            "note_word_recall": notes, "missing": all_missing,
        }
        (OUT / f"{label}_{scale}x.json").write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{key:45s} found {tot_found}/{tot}  mean {report[key]['sec_per_screen_mean']}s  max {report[key]['sec_per_screen_max']}s  note {notes}")
        sys.stdout.flush()
    return report
