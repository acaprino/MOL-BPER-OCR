"""Measure how faithful the emulated Scheda Privati is to the five screenshots of practice 52062600.

The screenshots are VDI captures of a maximised 1920 px browser (page viewport 1903 x 945 px plus a
17 px scrollbar); the VDI shows only part of it. For every screenshot this renders the emulator in headless Chrome at that viewport,
scrolled as in the screenshot, and compares the visible page area:
  - pixel difference (raw and after a light blur, which ignores anti-aliasing);
  - per-band drift: the shift (dx, dy) that best aligns each horizontal band.

    python bper-emulator/measure_scheda.py --out <dir> [--shots 1,2]
"""

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

import numpy as np
from PIL import Image, ImageFilter

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "bper-emulator"))

from serve_bper_simulator import SCHEDA_PAGE, create_server  # noqa: E402

SOURCE = REPO / "data" / "dataset" / "pratiche" / "52062600"
ROUTE = "#/schede/036214640/00027783639"
VIEWPORT = (1920, 945)
# Per screenshot: page origin (x, y) inside the PNG, visible page height, page scroll, note scroll.
# Calibrated by hand on the sidebar edge and on the text lines, then fixed so drift stays visible.
SHOTS = {
    1: ((2, 118), 889, 0, 0),
    2: ((-1, 118), 889, 662, 42),
    3: ((-4, 115), 889, 662, 123),
    4: ((-2, 118), 889, 662, 213),
    5: ((-1, 55), 945, 662, 254),
}
LEFT, RIGHT = 4, 1886  # page columns visible in all five screenshots
# Windows Task View overlay covering the note in screenshot 5 (page coordinates).
MASKS = {5: (718, 760, 1246, 935)}
CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)
BAND = 32
SEARCH = 6


def browser() -> str:
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise SystemExit("Chrome or Edge not found")


def render(exe: str, port: int, scroll: int, note: int, target: Path) -> Image.Image:
    target.unlink(missing_ok=True)
    url = f"http://127.0.0.1:{port}{SCHEDA_PAGE}?scroll={scroll}&noteScroll={note}{ROUTE}"
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [exe, "--headless=new", "--disable-gpu", "--force-device-scale-factor=1",
             f"--user-data-dir={profile}", f"--window-size={VIEWPORT[0]},{VIEWPORT[1]}",
             "--virtual-time-budget=6000", f"--screenshot={target}", url],
            check=True, capture_output=True, timeout=90)
    return Image.open(target).convert("RGB")


def reference(shot: int) -> Image.Image:
    (x, y), height, _, _ = SHOTS[shot]
    with Image.open(SOURCE / f"scheda-privati-0{shot}.png") as source:
        return source.convert("RGB").crop((x, y, x + VIEWPORT[0], y + height))


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
        if target.std() < 3:
            continue
        best, zero = (0, 0, 1e9), 0.0
        for dy in range(-SEARCH, SEARCH + 1):
            for dx in range(-SEARCH, SEARCH + 1):
                score = float(np.abs(target - emu[y0 + dy:y0 + dy + BAND, SEARCH + dx:width - SEARCH + dx]).mean())
                if dx == 0 and dy == 0:
                    zero = score
                if score < best[2]:
                    best = (dx, dy, score)
        rows.append((y0, best[0], best[1], zero, best[2]))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--shots", default="1,2,3,4,5")
    args = parser.parse_args()
    shots = [int(n) for n in args.shots.split(",")]
    args.out.mkdir(parents=True, exist_ok=True)
    exe = browser()
    with create_server(port=0, db_path=args.out / "fidelity.sqlite3", include_reference=True) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        renders = {n: render(exe, server.server_port, SHOTS[n][2], SHOTS[n][3], args.out / f"emu_{n}.png")
                   for n in shots}
        server.shutdown()

    print("shot  raw|diff|  blur|diff|  px>24   drift bands (y: dx,dy)")
    for n in shots:
        ref = reference(n)
        emu = renders[n].crop((0, 0) + ref.size)
        if n in MASKS:
            ref.paste(emu.crop(MASKS[n]), MASKS[n][:2])
        ref, emu = ref.crop((LEFT, 0, RIGHT, ref.height)), emu.crop((LEFT, 0, RIGHT, ref.height))
        raw = np.abs(np.asarray(ref, dtype=np.float32) - np.asarray(emu, dtype=np.float32)).mean(axis=2)
        blurred = np.abs(gray(ref, 1.2) - gray(emu, 1.2))
        drift = band_drift(gray(ref, 1.0), gray(emu, 1.0))
        moved = " ".join(f"{y}:{dx:+d},{dy:+d}" for y, dx, dy, zero, best in drift if (dx, dy) != (0, 0) and zero - best > 1.0)
        print(f"{n:>4}  {raw.mean():>8.2f}  {blurred.mean():>9.2f}  {(raw > 24).mean() * 100:>5.1f}%  {moved or 'aligned'}")
        side = Image.new("RGB", (ref.width * 3, ref.height), "white")
        side.paste(ref, (0, 0))
        side.paste(emu, (ref.width, 0))
        side.paste(Image.fromarray(np.clip(raw * 4, 0, 255).astype(np.uint8)).convert("RGB"), (ref.width * 2, 0))
        side.save(args.out / f"side_{n}.png")


main()
