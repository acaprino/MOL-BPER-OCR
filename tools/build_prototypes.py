"""Materialize prototype folders from the labelled frame registry.

The classifier builds a prototype per subdirectory of its templates directory.
This writes those subdirectories: one per process page, plus one per reject type.

Crops are written *as the classifier expects to receive an image*, which is a
window screenshot with its browser chrome, not the application area alone. The
classifier applies DEFAULT_CROP_ROI itself, dropping the top 20%; writing an
already-cropped prototype means that ROI lands a second time and shaves 20% of real
content off. Measured: with pre-cropped prototypes, the only class that survived
was the one built from an uncropped reference, and reference recognition fell to
2 of 9. The rectangle is therefore widened upward to include the chrome the ROI
will remove.

Two further choices worth stating, both measured in docs/adr/0008:

The nine reference screenshots go in alongside the real crops. They were once
excluded as "a different distribution", which was wrong on the merits: the
recordings are Teams screen-shares with participant tiles and a shrunken window,
which is the lecture case, while an operator working full-screen produces exactly
the framing of those PNGs. Without them, pages 3, 6, 7 and 8 have no prototype at
all, appearing at most twice each across 2098 frames.

Rejects are split by type rather than averaged into one. altro-bper (right
application, wrong screen), altro-app and altro-nulla are categories distinguished
by eye during review, and keeping them apart takes false positives from 44% to 20%
at no cost in page accuracy; k-means over the same negatives buys a few more points
of rejection and pays 10 to 50 points of accuracy.

    python tools/build_prototypes.py --out edge-agent/assets/templates/bper
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image

FRAMES = Path("tests/fixtures/frames")
REFERENCES = Path("mnt/data")
REJECT_PREFIX = "SCARTO"

# The classifier drops this fraction off the top before embedding (DEFAULT_CROP_ROI).
# A prototype must therefore carry that much expendable content above the application
# area, or the ROI eats into the page itself.
ROI_TOP_DROP = 0.20

# Reject folders, and which registry clusters feed each.
REJECT_GROUPS = {
    f"{REJECT_PREFIX}-fuori-processo": ("altro-bper",),
    f"{REJECT_PREFIX}-altro-applicativo": ("altro-app",),
    f"{REJECT_PREFIX}-vuoto": ("altro-nulla",),
}

PAGE_SLUGS = {
    "1": "screen 1", "2": "screen 2", "3": "screen 3", "4": "screen 4", "5": "screen 5",
    "6": "screen 6", "7": "screen 7", "8": "screen 8", "9": "screen 9",
}


def widen_for_roi(rect: Optional[Tuple[int, int, int, int]],
                  size: Tuple[int, int]) -> Optional[Tuple[int, int, int, int]]:
    """Grow the rectangle upward so the classifier's own ROI has chrome to remove.

    Returns None when the frame cannot supply that headroom, in which case the whole
    frame is used: better an untrimmed prototype than a decapitated one.
    """
    if not rect:
        return None
    x1, y1, x2, y2 = rect
    height = y2 - y1
    # after the ROI drops ROI_TOP_DROP of the crop, what remains must still be the page
    needed = int(height * ROI_TOP_DROP / (1 - ROI_TOP_DROP))
    if y1 - needed < 0:
        return None
    return (x1, y1 - needed, x2, y2)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="edge-agent/assets/templates/bper")
    ap.add_argument("--per-class", type=int, default=25,
                    help="cap on crops per class; prototypes are means, so more images "
                         "past a point only slow the build")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pages", action="store_true",
                    help="also build page prototypes from real crops. OFF by default: "
                         "measured, adding real crops alongside the reference screenshots "
                         "drops reference recognition from 9/9 to 1/9, while the reject "
                         "classes alone leave it at 9/9. See docs/adr/0008.")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    registry = json.loads((FRAMES / "registry.json").read_text(encoding="utf-8"))
    relocalized_path = FRAMES / "relocalized.json"
    relocalized = json.loads(relocalized_path.read_text(encoding="utf-8")) \
        if relocalized_path.exists() else {}

    by_cluster: Dict[str, List[dict]] = defaultdict(list)
    for entry in registry["frames"]:
        cluster = entry.get("cluster")
        if cluster and (FRAMES / entry["frame"]).exists():
            by_cluster[cluster].append(entry)

    plan: Dict[str, List[tuple]] = defaultdict(list)

    # process pages: real crops, capped and sampled deterministically
    for cluster, folder in (PAGE_SLUGS.items() if args.pages else ()):
        rows = by_cluster.get(cluster, [])
        if len(rows) > args.per_class:
            rows = rng.sample(rows, args.per_class)
        for row in rows:
            rect = relocalized.get(row["frame"], {}).get("rect") or row.get("app_rect")
            plan[folder].append((FRAMES / row["frame"], rect))

    # The nine reference screenshots are NOT copied here. They already sit in the
    # templates root as "screen N.png", and _scan_dataset_images() merges a root file
    # with the same-named subdirectory under one key: copying them in would count each
    # reference twice and weight it against the real crops. Leaving them in the root is
    # what makes them part of the prototype without duplication.

    # rejects, one folder per type
    for folder, clusters in REJECT_GROUPS.items():
        rows = [r for c in clusters for r in by_cluster.get(c, [])]
        if len(rows) > args.per_class:
            rows = rng.sample(rows, args.per_class)
        for row in rows:
            rect = relocalized.get(row["frame"], {}).get("rect") or row.get("app_rect")
            plan[folder].append((FRAMES / row["frame"], rect))

    out = Path(args.out)
    print(f"destinazione: {out}\n")
    for folder in sorted(plan):
        sources = plan[folder]
        kind = "scarto " if folder.startswith(REJECT_PREFIX) else "pagina "
        print(f"  {kind}{folder:34} {len(sources):3} immagini")
        if args.dry_run:
            continue
        target = out / folder
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        for i, (src, rect) in enumerate(sources):
            img = Image.open(src).convert("RGB")
            widened = widen_for_roi(rect, img.size) if rect else None
            if widened:
                img = img.crop(widened)
            elif rect:
                pass  # not enough headroom above: keep the whole frame
            img.save(target / f"{i:03d}.png")

    thin = [f for f, s in plan.items() if not f.startswith(REJECT_PREFIX) and len(s) < 3]
    if thin:
        print(f"\nclassi con meno di 3 immagini (prototipo fragile): {sorted(thin)}")
    if args.dry_run:
        print("\n--dry-run: nulla e' stato scritto")


if __name__ == "__main__":
    main()
