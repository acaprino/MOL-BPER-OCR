"""Iteration 2 prep: recording frames -> shared-screen area -> dedupe per page class -> PNGs.

Many recordings are Teams meetings: the shared BPER window sits in the middle, participants'
video tiles (faces and names) on the right, black borders around. The registry's app_rect is
wrong on these (it cuts the window's left side), so the area is found here instead: the widest
run of non-black columns is the shared screen; tiles are narrow runs separated by black. A
full-screen capture has one run as wide as the frame and is kept whole. Faces never leave the
machine because they are outside the kept area.
"""

import json
import os
import random
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = HERE / "iter2_frames"
OUT.mkdir(exist_ok=True)

reg = json.load(open(REPO / "tests/fixtures/frames/registry.json", encoding="utf-8"))
files = {}
for p in (REPO / "tests/fixtures/frames").rglob("*"):
    if p.suffix.lower() in (".jpg", ".png"):
        files[p.name] = p

SKIP_DIRS = ("no-tooltip-rita", "tooltips-rita")  # already in the training set
rng = random.Random(11)
process = [f for f in reg["frames"] if str(f["cluster"]) in list("123456789")]
others = [f for f in reg["frames"] if f["cluster"] == "altro-bper"]
rng.shuffle(others)


def runs(mask):
    out, start = [], None
    for i, v in enumerate(list(mask) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i))
            start = None
    return out


def shared_area(im: Image.Image):
    """(x0, y0, x1, y1) of the widest non-black column run, trimmed of dark rows below it."""
    a = np.asarray(im.convert("L"), dtype=np.float32)
    h, w = a.shape
    band = a[int(0.1 * h):int(0.85 * h)]
    col_bright = (band > 40).mean(axis=0)
    cols = [r for r in runs(col_bright > 0.05) if r[1] - r[0] > 50]
    if not cols:
        return 0, 0, w, h
    x0, x1 = max(cols, key=lambda r: r[1] - r[0])
    row_bright = (a[:, x0:x1] > 40).mean(axis=1)
    rows = [r for r in runs(row_bright > 0.05) if r[1] - r[0] > 50]
    y0, y1 = max(rows, key=lambda r: r[1] - r[0]) if rows else (0, h)
    return x0, y0, x1, y1


kept, seen = {}, {}
for group, frames, cap in (("process", process, None), ("negative", others, 45)):
    n = 0
    for f in frames:
        p = files.get(os.path.basename(f["frame"]))
        if p is None or any(d in str(p) for d in SKIP_DIRS):
            continue
        im = Image.open(p).convert("RGB")
        box = shared_area(im)
        im = im.crop(box)
        if im.width < 400 or im.height < 300:
            continue
        h = imagehash.phash(im, hash_size=16)
        bucket = seen.setdefault(str(f["cluster"]), [])
        if any(h - s <= 8 for s in bucket):
            continue
        bucket.append(h)
        fid = f"{group}_{len(kept):04d}"
        im.save(OUT / f"{fid}.png")
        kept[fid] = {"source": f["frame"], "cluster": str(f["cluster"]), "group": group, "rect": list(map(int, box)),
                     "size": im.size}
        n += 1
        if cap and n >= cap:
            break

(HERE / "iter2_index.json").write_text(json.dumps(kept, indent=1), encoding="utf-8")
by = {}
for v in kept.values():
    by[v["cluster"]] = by.get(v["cluster"], 0) + 1
widths = sorted(v["size"][0] for v in kept.values())
print("kept", len(kept), "by cluster", dict(sorted(by.items())), "width min/median/max",
      widths[0], widths[len(widths) // 2], widths[-1])
