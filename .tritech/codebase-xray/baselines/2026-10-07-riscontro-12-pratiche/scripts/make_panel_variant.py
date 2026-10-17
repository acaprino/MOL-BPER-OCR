"""Build a variant of an input folder where practice-detail screenshots are cropped to the app panel.

Usage: python -I make_panel_variant.py <input_dir> <out_dir> [name-filter-regex]
Elenco and Scheda Privati pages fill the window, so they are left out: the variant isolates the
effect of framing on the detail pages, whose panel occupies the left half of a maximized browser.
No resampling here: the pipeline's own normalize_image() scales the crop to its usual long side.
"""
import csv
import os
import re
import sys

from PIL import Image

PANEL = (150, 255, 1100)  # x0, y0, x1 in source pixels; bottom edge is the image height
src, out = sys.argv[1], sys.argv[2]
name_filter = re.compile(sys.argv[3], re.I) if len(sys.argv) > 3 else None
os.makedirs(out, exist_ok=True)
kept = set()
for fname in sorted(os.listdir(src)):
    stem, ext = os.path.splitext(fname)
    kind = stem.split("__", 1)[-1].lower()
    if ext.lower() != ".png" or kind.startswith(("elenco", "scheda")):
        continue
    if name_filter and not name_filter.search(stem):
        continue
    with Image.open(os.path.join(src, fname)) as img:
        img.convert("RGB").crop((PANEL[0], PANEL[1], min(PANEL[2], img.width), img.height)).save(os.path.join(out, fname))
    kept.add(stem)
with open(os.path.join(src, "dati.csv"), encoding="utf-8-sig", newline="") as fh:
    rows = list(csv.reader(fh, delimiter=";"))
with open(os.path.join(out, "dati.csv"), "w", encoding="utf-8-sig", newline="") as fh:
    writer = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(rows[0])
    writer.writerows(r for r in rows[1:] if r and r[0] in kept)
print(f"{len(kept)} cropped screenshots in {out}")
