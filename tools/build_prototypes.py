"""Build the page prototypes the edge-agent ships: one vector per page and per reject type.

The app never computes them (ADR 0030): it loads bper_page_prototypes.json from its
templates folder. This tool writes that file. The nine page prototypes come from the
screenshots of the reference practice in data/pratiche (tools/reference_screens.py); the
reject prototypes from crops of the labelled frame registry, cut in a temporary folder.

A rebuild is a behaviour change. The shipped file was built on 2026-08-18; the registry grew
on 2026-08-21, so today the same sampling picks other reject crops (16 of 75 identical).
Rebuild only to change the prototypes, then run the slow tests of test_page_classifier.py.

Crops are written *as the classifier expects to receive an image*, which is a
window screenshot with its browser chrome, not the application area alone. The
classifier applies DEFAULT_CROP_ROI itself, dropping the top 20%; writing an
already-cropped prototype means that ROI lands a second time and shaves 20% of real
content off. Measured: with pre-cropped prototypes, the only class that survived
was the one built from an uncropped reference, and reference recognition fell to
2 of 9. The rectangle is therefore widened upward to include the chrome the ROI
will remove.

Two further choices worth stating, both measured in docs/adr/0008:

The nine reference screenshots go in alongside the real crops (with --pages). They were once
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

    python tools/build_prototypes.py --out src/edge-agent/assets/templates/bper
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), "src/edge-agent"]
from tools.reference_screens import reference_screens  # noqa: E402

FRAMES = Path("tests/fixtures/frames")
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


def cut_crops(crops: Path, per_class: int = 25, seed: int = 0, pages: bool = False) -> Dict[str, int]:
    """Write the crops of the labelled frames under crops/<class>/NNN.png; return the count per class."""
    rng = random.Random(seed)
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
    for cluster, folder in (PAGE_SLUGS.items() if pages else ()):
        rows = by_cluster.get(cluster, [])
        if len(rows) > per_class:
            rows = rng.sample(rows, per_class)
        for row in rows:
            rect = relocalized.get(row["frame"], {}).get("rect") or row.get("app_rect")
            plan[folder].append((FRAMES / row["frame"], rect))

    # The nine reference screenshots join their page's class once, read from the archive
    # by main(): copying them into the crop folders as well would count each one twice.

    # rejects, one folder per type
    for folder, clusters in REJECT_GROUPS.items():
        rows = [r for c in clusters for r in by_cluster.get(c, [])]
        if len(rows) > per_class:
            rows = rng.sample(rows, per_class)
        for row in rows:
            rect = relocalized.get(row["frame"], {}).get("rect") or row.get("app_rect")
            plan[folder].append((FRAMES / row["frame"], rect))

    for folder in sorted(plan):
        target = crops / folder
        target.mkdir(parents=True)
        for i, (src, rect) in enumerate(plan[folder]):
            img = Image.open(src).convert("RGB")
            widened = widen_for_roi(rect, img.size) if rect else None
            if widened:
                img = img.crop(widened)
            img.save(target / f"{i:03d}.png")  # without headroom above, the whole frame
    return {folder: len(sources) for folder, sources in plan.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="src/edge-agent/assets/templates/bper")
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

    out = Path(args.out)
    print(f"destinazione: {out / 'bper_page_prototypes.json'}\n")
    with tempfile.TemporaryDirectory() as work:
        crops = Path(work)
        counts = cut_crops(crops, args.per_class, args.seed, args.pages)
        for folder in sorted(counts):
            kind = "scarto " if folder.startswith(REJECT_PREFIX) else "pagina "
            print(f"  {kind}{folder:34} {counts[folder]:3} immagini")
        thin = [f for f, n in counts.items() if not f.startswith(REJECT_PREFIX) and n < 3]
        if thin:
            print(f"\nclassi con meno di 3 immagini (prototipo fragile): {sorted(thin)}")
        if args.dry_run:
            print("\n--dry-run: nulla e' stato scritto")
            return

        from page_classifier import (BPERPagePrototypeClassifier, DEFAULT_CROP_ROI,
                                     DEFAULT_SIMILARITY_THRESHOLD, _scan_dataset_images)

        page_images = _scan_dataset_images(crops) if counts else {}
        for label, screenshot in reference_screens().items():
            page_images.setdefault(label, []).append(screenshot)
        BPERPagePrototypeClassifier(templates_dir=out, crop_roi=DEFAULT_CROP_ROI,
                                    similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD,
                                    device="cpu", build_from=page_images)
    print(f"\nscritti {len(page_images)} prototipi")


if __name__ == "__main__":
    main()
