"""Measure how faithful the emulator is to the original screenshots of the reference practice.

For every screen it renders the emulator in headless Chrome at the native 842x617 and compares it
with the website area of the original screenshot:
  - pixel difference (raw and after a light blur, which ignores anti-aliasing);
  - per-band drift: the shift (dx, dy) that best aligns each horizontal band, so a layout that is
    off by a pixel or two shows up as a number instead of a vague diff image;
  - optionally (--classify) whether the real page classifier still recognises the page when the
    emulator content sits inside the original window frame.

    python bper-emulator/measure_fidelity.py --out <dir> [--steps 5,6,7] [--classify]
"""

import argparse
from io import BytesIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

import numpy as np
from PIL import Image, ImageFilter

REPO = Path(__file__).resolve().parents[1]
for _p in (REPO, REPO / "src", REPO / "src" / "edge-agent", REPO / "bper-emulator", REPO / "tests"):
    sys.path.insert(0, str(_p))

from bper_simulator_data import SITE_ORIGINS, site_reference_png  # noqa: E402
from serve_bper_simulator import create_server  # noqa: E402

CHROME_CANDIDATES = (
    os.environ.get("CHROME_PATH", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)
BAND = 32
SEARCH = 6


def browser() -> str:
    for candidate in CHROME_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    raise SystemExit("Chrome or Edge not found: set CHROME_PATH")


def render(exe: str, port: int, step: int, target: Path) -> Image.Image:
    target.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
             f"--user-data-dir={profile}", "--window-size=842,617", "--virtual-time-budget=6000",
             f"--screenshot={target}", f"http://127.0.0.1:{port}/?practice=reference&capture=1#{step}"],
            check=True, capture_output=True, timeout=90)
    return Image.open(target).convert("RGB")


def gray(img: Image.Image, blur: float) -> np.ndarray:
    out = img.convert("L")
    if blur:
        out = out.filter(ImageFilter.GaussianBlur(blur))
    return np.asarray(out, dtype=np.float32)


def band_drift(ref: np.ndarray, emu: np.ndarray) -> list[tuple[int, int, int, float, float]]:
    """(y0, dx, dy, diff at zero shift, diff at the best shift) for each horizontal band."""
    rows = []
    height, width = ref.shape
    for y0 in range(SEARCH, height - BAND - SEARCH, BAND):
        target = ref[y0:y0 + BAND, SEARCH:width - SEARCH]
        if target.std() < 3:  # blank band: nothing to align
            continue
        best = (0, 0, 1e9)
        zero = 0.0
        for dy in range(-SEARCH, SEARCH + 1):
            for dx in range(-SEARCH, SEARCH + 1):
                shifted = emu[y0 + dy:y0 + dy + BAND, SEARCH + dx:width - SEARCH + dx]
                score = float(np.abs(target - shifted).mean())
                if dx == 0 and dy == 0:
                    zero = score
                if score < best[2]:
                    best = (dx, dy, score)
        rows.append((y0, best[0], best[1], zero, best[2]))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--steps", default="1,2,3,4,5,6,7,8,9")
    parser.add_argument("--classify", action="store_true")
    args = parser.parse_args()
    steps = [int(n) for n in args.steps.split(",")]
    args.out.mkdir(parents=True, exist_ok=True)
    exe = browser()

    with create_server(port=0, db_path=args.out / "fidelity.sqlite3", include_reference=True) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        renders = {n: render(exe, server.server_port, n, args.out / f"emu_{n}.png") for n in steps}
        server.shutdown()

    print("step  raw|diff|  blur|diff|  px>24   drift bands (y: dx,dy)")
    for n in steps:
        ref = Image.open(BytesIO(site_reference_png(n))).convert("RGB")
        emu = renders[n]
        if emu.size != ref.size:
            print(f"{n:>4}  size {emu.size} != {ref.size}")
            continue
        raw = np.abs(np.asarray(ref, dtype=np.float32) - np.asarray(emu, dtype=np.float32)).mean(axis=2)
        blurred = np.abs(gray(ref, 1.2) - gray(emu, 1.2))
        drift = band_drift(gray(ref, 1.0), gray(emu, 1.0))
        moved = " ".join(f"{y}:{dx:+d},{dy:+d}" for y, dx, dy, zero, best in drift if (dx, dy) != (0, 0) and zero - best > 1.0)
        print(f"{n:>4}  {raw.mean():>8.2f}  {blurred.mean():>9.2f}  {(raw > 24).mean() * 100:>5.1f}%  {moved or 'aligned'}")
        side = Image.new("RGB", (842 * 3, 617), "white")
        side.paste(ref, (0, 0))
        side.paste(emu, (842, 0))
        side.paste(Image.fromarray(np.clip(raw * 4, 0, 255).astype(np.uint8)).convert("RGB"), (1684, 0))
        side.save(args.out / f"side_{n}.png")

    if not args.classify:
        return
    import pytest

    pytest.importorskip("torch")
    import test_page_classifier as tpc
    from page_classifier import BPERPagePrototypeClassifier, DEFAULT_CROP_ROI, DEFAULT_SIMILARITY_THRESHOLD
    from tools.reference_screens import reference_screens

    classifier = BPERPagePrototypeClassifier(
        templates_dir=tpc.TEMPLATES, crop_roi=DEFAULT_CROP_ROI,
        similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD, device="cpu")
    shots = reference_screens()
    recognised = 0
    for n in steps:
        composed = Image.open(shots[f"screen {n}"]).convert("RGB")
        composed.paste(renders[n], SITE_ORIGINS[n])
        path = args.out / f"composed_{n}.png"
        composed.save(path)
        label, score = classifier.classify(tpc._as_worker_sees_it(tpc._live_frame(path)))
        recognised += label == f"screen {n}"
        print(f"screen {n}: emulator -> {label} ({score:.3f}) {'OK' if label == f'screen {n}' else 'MISS'}")
    print(f"recognised: {recognised}/{len(steps)}")


main()
