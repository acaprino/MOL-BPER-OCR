"""Do Rita's window-grade shots work as prototypes for the tooltip pages?

The earlier failure is the reference point: adding Teams-recording CROPS to the
page classes collapsed reference recognition from 9/9 to 1/9, because prototypes
averaged across two populations resemble neither. Rita's screenshots are the
same population as the nine references (full-window direct captures), so this
is the first legitimate attempt to give classes 3/6/7/8 more than one image.

Split: per class, half the shots become prototypes, half are held out as test.
Class 7 has a single exemplar: it goes into the prototype and the class stays
untested, stated rather than hidden.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "edge-agent")
from PIL import Image

REPO = Path(".")
TPL = REPO / "edge-agent/assets/templates/bper"
RITA = REPO / "tests/fixtures/frames/tooltips-rita"

PROTO = {
    "screen 3": ["rita-tooltip-1a.png", "rita-tooltip-1c.png"],
    "screen 6": ["rita-tooltip-2a.png", "rita-tooltip-2c.png", "rita-tooltip-2e.png"],
    "screen 7": ["rita-tooltip-3b.png"],
    "screen 8": ["rita-tooltip-3a.png", "rita-tooltip-3d.png", "rita-tooltip-4b.png"],
}
TEST = {
    "screen 3": ["rita-tooltip-1b.png", "rita-tooltip-1d.png"],
    "screen 6": ["rita-tooltip-2b.png", "rita-tooltip-2d.png"],
    "screen 7": [],
    "screen 8": ["rita-tooltip-3c.png", "rita-tooltip-4a.png",
                 "rita-tooltip-4c.png", "rita-tooltip-4d.png"],
}

work = Path(tempfile.mkdtemp()) / "bper"
work.mkdir(parents=True)
for n in range(1, 10):
    shutil.copy(TPL / f"screen {n}.png", work / f"screen {n}.png")
for d in TPL.glob("SCARTO-*"):
    shutil.copytree(d, work / d.name)
for cls, files in PROTO.items():
    (work / cls).mkdir()
    for f in files:
        shutil.copy(RITA / f, work / cls / f)

from page_classifier import (BPERPagePrototypeClassifier, DEFAULT_CROP_ROI,
                             DEFAULT_SIMILARITY_THRESHOLD)

clf = BPERPagePrototypeClassifier(templates_dir=work, crop_roi=DEFAULT_CROP_ROI,
                                  similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD,
                                  device="cpu")
info = clf.info()
print(f"prototipi: {info['num_prototypes']} classi\n")

print("--- i 9 riferimenti devono restare 9/9 ---")
ok = 0
for n in range(1, 10):
    r = clf.classify_detailed(Image.open(REPO / f"mnt/data/screen {n}.png"))
    good = r.label == f"screen {n}"
    ok += good
    flag = "OK " if good else "!! "
    print(f"  {flag}screen {n} -> {str(r.label):10} margine {r.margin:5.3f}")
print(f"  {ok}/9\n")

print("--- scatti tenuti fuori (mai visti dai prototipi) ---")
tot = good_n = 0
for cls, files in TEST.items():
    for f in files:
        r = clf.classify_detailed(Image.open(RITA / f))
        good = r.label == cls
        tot += 1
        good_n += good
        flag = "OK " if good else "!! "
        print(f"  {flag}{f:24} atteso {cls:9} -> {str(r.label):10} margine {r.margin:5.3f}")
print(f"  {good_n}/{tot} corretti")
print("  (screen 7: un solo esemplare, nel prototipo; classe non testabile)\n")

print("--- i negativi devono restare scartati ---")
for nome, im in (("desktop", Image.new("RGB", (1920, 1080), (32, 34, 38))),
                 ("grigio", Image.new("RGB", (1920, 1080), (128, 128, 128)))):
    r = clf.classify_detailed(im)
    print(f"  {nome:9} label={r.label} scartato_da={r.rejected_by}")

print(f"\ndir di lavoro (per ispezione): {work}")
