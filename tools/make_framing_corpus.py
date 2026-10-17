"""Compose a framing test corpus with known ground truth.

Every measurement of page localization so far compared against rectangles
estimated by eye, which is not a measurement. This composes pages into synthetic
desktops itself, so the true rectangle is known to the pixel and IoU can be
computed rather than guessed.

What it proves and what it does not: the compositions vary placement, scale,
screen shape, surrounding clutter and nesting depth, so they test invariance to
*framing*. They do not reproduce real rendering, Citrix compression or a live
browser's antialiasing. Frames pulled from an actual session recording test
those; the two corpora answer different questions and neither replaces the other.

    python tools/make_framing_corpus.py --out <dir> [--per-page 8] [--seed 0]
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

Rect = Tuple[int, int, int, int]

# Screen shapes an operator might actually have, 16:9 through 16:10 and 4:3-ish.
SCREENS: List[Tuple[int, int]] = [
    (1366, 768), (1920, 1080), (1920, 1200), (2560, 1440), (3840, 2160),
]

# Fraction of the screen's shorter side the page is scaled to occupy.
SCALES: List[float] = [0.35, 0.5, 0.7, 0.9]

BACKGROUNDS: List[str] = ["dark-desktop", "light-desktop", "black", "busy"]
NESTINGS: List[str] = ["none", "window", "player"]


def _background(size: Tuple[int, int], kind: str, rng: random.Random) -> Image.Image:
    w, h = size
    if kind == "black":
        return Image.new("RGB", size, (0, 0, 0))

    base = (32, 34, 38) if kind == "dark-desktop" else (222, 226, 232)
    img = Image.new("RGB", size, base)
    draw = ImageDraw.Draw(img)

    if kind in ("dark-desktop", "light-desktop"):
        # Desktop icons: small squares with a caption bar, down the left edge.
        icon = max(24, w // 40)
        for col in range(2):
            for row in range(h // (icon * 3)):
                x, y = 20 + col * icon * 2, 20 + row * icon * 3
                tone = rng.randint(90, 200)
                draw.rectangle([x, y, x + icon, y + icon], fill=(tone, tone, tone // 2 + 60))
                draw.rectangle([x - 4, y + icon + 4, x + icon + 4, y + icon + 12],
                               fill=(base[0] + 18, base[1] + 18, base[2] + 18))
        draw.rectangle([0, h - max(28, h // 30), w, h], fill=(18, 18, 22))  # taskbar
    else:  # busy: other windows lying around
        for _ in range(rng.randint(3, 6)):
            rw, rh = rng.randint(w // 6, w // 2), rng.randint(h // 6, h // 2)
            x, y = rng.randint(0, max(1, w - rw)), rng.randint(0, max(1, h - rh))
            tone = rng.randint(40, 210)
            draw.rectangle([x, y, x + rw, y + rh], fill=(tone, tone, tone))
            draw.rectangle([x, y, x + rw, y + 24], fill=(max(0, tone - 40),) * 3)
    return img


def _wrap(page: Image.Image, nesting: str) -> Tuple[Image.Image, Rect]:
    """Wrap the page in a container. Returns the container and the page's rect inside it."""
    if nesting == "none":
        return page, (0, 0, page.width, page.height)

    border = max(2, page.width // 200)
    title = max(18, page.height // 28)
    bottom = title if nesting == "player" else border  # a player has a control bar

    w = page.width + border * 2
    h = page.height + title + bottom
    box = Image.new("RGB", (w, h), (48, 50, 56))
    draw = ImageDraw.Draw(box)
    draw.rectangle([0, 0, w, title], fill=(64, 66, 74))
    if nesting == "player":
        draw.rectangle([0, h - bottom, w, h], fill=(40, 42, 48))
    box.paste(page, (border, title))
    return box, (border, title, border + page.width, title + page.height)


def compose(
    page: Image.Image,
    screen: Tuple[int, int],
    scale: float,
    background: str,
    nesting: str,
    rng: random.Random,
) -> Tuple[Image.Image, Rect]:
    """Place `page` on a synthetic screen. Returns the frame and the page's true rect."""
    sw, sh = screen
    target_h = int(min(sw, sh) * scale)
    factor = target_h / page.height
    scaled = page.resize((max(1, int(page.width * factor)), max(1, int(page.height * factor))),
                         Image.Resampling.LANCZOS)

    container, inner = _wrap(scaled, nesting)
    if container.width > sw or container.height > sh:
        shrink = min(sw / container.width, sh / container.height) * 0.95
        new = (max(1, int(container.width * shrink)), max(1, int(container.height * shrink)))
        inner = tuple(int(v * shrink) for v in inner)  # type: ignore[assignment]
        container = container.resize(new, Image.Resampling.LANCZOS)

    frame = _background(screen, background, rng)
    x = rng.randint(0, max(0, sw - container.width))
    y = rng.randint(0, max(0, sh - container.height))
    frame.paste(container, (x, y))

    return frame, (x + inner[0], y + inner[1], x + inner[2], y + inner[3])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", default="src/edge-agent/assets/templates/bper",
                    help="directory of source page images (default: the BPER templates)")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--per-page", type=int, default=8, help="compositions per source page")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    sources = sorted(p for p in Path(args.pages).glob("*.png") if p.is_file())
    if not sources:
        raise SystemExit(f"no source pages in {args.pages}")

    manifest: List[Dict[str, object]] = []
    for src in sources:
        page = Image.open(src).convert("RGB")
        for i in range(args.per_page):
            screen = rng.choice(SCREENS)
            scale = rng.choice(SCALES)
            background = rng.choice(BACKGROUNDS)
            nesting = rng.choice(NESTINGS)
            frame, rect = compose(page, screen, scale, background, nesting, rng)

            name = f"{src.stem.replace(' ', '_')}__{i:02d}.png"
            frame.save(out / name)
            manifest.append({
                "file": name,
                "label": src.stem,
                "rect": list(rect),
                "screen": list(screen),
                "scale": scale,
                "background": background,
                "nesting": nesting,
            })

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"{len(manifest)} compositions from {len(sources)} pages -> {out}")


if __name__ == "__main__":
    main()
