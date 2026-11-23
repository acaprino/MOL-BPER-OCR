"""Measure how faithful the Home, Ricerca Pratica and the "pratica già in lavorazione" dialog are to the video.

The frames are crops of the meeting recording (1350x1080, the operator's 1280x1024 desktop enlarged 1.0547
times, spec section 16.1): one video pixel is 0.948 CSS px at 100% zoom and the page viewport is y=92..1038.
For every page this renders the emulator in headless Chrome at native scale in a 1280x897 window, resizes the
frame's page area to that size and compares them like measure_fidelity.py does:
  - pixel difference (raw and after a light blur, which ignores anti-aliasing);
  - per-band drift: the shift (dx, dy) that best aligns each horizontal band.
The frames show another operator and practice and a mouse pointer: those boxes are reported both as they are
and masked (copied from the render into the frame).

    python bper-emulator/measure_video_pages.py --frames <dir of the video frames> --out <dir> [--pages home]
"""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))

from serve_bper_simulator import create_server  # noqa: E402

VIEWPORT = (1280, 897)
PAGE_AREA = (0, 92, 1350, 1038)  # the page viewport inside a frame, video px
SCALE = VIEWPORT[0] / PAGE_AREA[2]  # 0.948
OPERATOR = (1040, 105, 1285, 165)  # name and codes of the operator in the header, video px
# Per page: frame, emulator route, boxes to mask (video px, frame coordinates).
PAGES = {
    "home": ("01m35s_npef_home.png", "/", [OPERATOR, (1226, 396, 1258, 432)]),
    "search": ("01m39s_ricerca_pratica_form.png", "/#ricerca", [OPERATOR, (142, 596, 167, 630)]),
    "modal": ("18m13s_modal_pratica_gia_in_lavorazione.png", "/?practice=demo&modal=1#4",
              [OPERATOR, (1158, 432, 1188, 464), (818, 210, 912, 238)]),
}
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


def render(exe: str, port: int, route: str, target: Path) -> Image.Image:
    # Headless --screenshot can fire before the catalogue arrives: a render without the operator's name in the
    # header is taken again.
    for _ in range(4):
        target.unlink(missing_ok=True)
        with tempfile.TemporaryDirectory() as profile:
            subprocess.run(
                [exe, "--headless=new", "--disable-gpu", "--force-device-scale-factor=1",
                 f"--user-data-dir={profile}", f"--window-size={VIEWPORT[0]},{VIEWPORT[1]}",
                 "--virtual-time-budget=8000", f"--screenshot={target}", f"http://127.0.0.1:{port}{route}"],
                check=True, capture_output=True, timeout=90)
        if target.exists():
            image = Image.open(target).convert("RGB")
            if np.asarray(image.convert("L"))[20:60, 1000:1215].min() < 120:
                return image
    raise SystemExit(f"no complete render of {route}")


def video_page(frame: Image.Image) -> Image.Image:
    return frame.convert("RGB").crop(PAGE_AREA).resize(VIEWPORT, Image.Resampling.LANCZOS)


def to_page(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return (round(x0 * SCALE), round((y0 - PAGE_AREA[1]) * SCALE),
            round(x1 * SCALE), round((y1 - PAGE_AREA[1]) * SCALE))


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


def compare(ref: Image.Image, emu: Image.Image) -> tuple[np.ndarray, float]:
    raw = np.abs(np.asarray(ref, dtype=np.float32) - np.asarray(emu, dtype=np.float32)).mean(axis=2)
    return raw, float(np.abs(gray(ref, 1.2) - gray(emu, 1.2)).mean())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pages", default=",".join(PAGES))
    args = parser.parse_args()
    pages = args.pages.split(",")
    args.out.mkdir(parents=True, exist_ok=True)
    exe = browser()
    with create_server(port=0, db_path=args.out / "video.sqlite3") as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        renders = {name: render(exe, server.server_port, PAGES[name][1], args.out / f"emu_{name}.png") for name in pages}
        server.shutdown()

    print("page     raw|diff|  blur|diff|  masked blur  px>24   drift bands (y: dx,dy)")
    for name in pages:
        frame_name, _, masks = PAGES[name]
        with Image.open(args.frames / frame_name) as frame:
            ref = video_page(frame)
        emu = renders[name]
        raw, blurred = compare(ref, emu)
        masked = ref.copy()
        for box in map(to_page, masks):
            masked.paste(emu.crop(box), box[:2])
        _, blurred_masked = compare(masked, emu)
        drift = band_drift(gray(masked, 1.0), gray(emu, 1.0))
        moved = " ".join(f"{y}:{dx:+d},{dy:+d}" for y, dx, dy, zero, best in drift if (dx, dy) != (0, 0) and zero - best > 1.0)
        print(f"{name:<7}  {raw.mean():>8.2f}  {blurred:>9.2f}  {blurred_masked:>11.2f}  {(raw > 24).mean() * 100:>5.1f}%  {moved or 'aligned'}")
        side = Image.new("RGB", (VIEWPORT[0] * 3, VIEWPORT[1]), "white")
        side.paste(masked, (0, 0))
        side.paste(emu, (VIEWPORT[0], 0))
        side.paste(Image.fromarray(np.clip(raw * 4, 0, 255).astype(np.uint8)).convert("RGB"), (VIEWPORT[0] * 2, 0))
        side.save(args.out / f"side_{name}.png")


main()
