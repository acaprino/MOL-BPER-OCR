"""Write enlarged crops of each screenshot so small on-screen text can be read reliably.

Usage: python -I make_zoom.py <source_root> <out_root>
Detail pages -> one crop of the left application panel, 2x.
Elenco pages -> left and right halves of the results row band, 2x.
Scheda Privati pages -> left and right halves of the page, 1.6x.
"""
import os
import sys
from typing import List, Tuple

from PIL import Image

Box = Tuple[int, int, int, int]


def _save(img: Image.Image, box: Box, scale: float, path: str) -> None:
    x0, y0, x1, y1 = box
    x1, y1 = min(x1, img.width), min(y1, img.height)
    crop = img.crop((x0, y0, x1, y1))
    crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS)
    crop.save(path)


def crops_for(name: str, size: Tuple[int, int]) -> List[Tuple[str, Box, float]]:
    w, h = size
    low = name.lower()
    if low.startswith("elenco"):
        return [("L", (0, 330, 1010, 660), 2.0), ("R", (900, 330, w, 660), 2.0)]
    if low.startswith("scheda_privati"):
        return [("L", (210, 110, 1090, h), 1.6), ("R", (1040, 110, w, h), 1.6)]
    return [("panel", (150, 255, 1100, h), 2.0)]


def main(src_root: str, out_root: str) -> None:
    count = 0
    for practice in sorted(os.listdir(src_root)):
        src_dir = os.path.join(src_root, practice)
        if not os.path.isdir(src_dir):
            continue
        out_dir = os.path.join(out_root, practice)
        os.makedirs(out_dir, exist_ok=True)
        for fname in sorted(os.listdir(src_dir)):
            stem, ext = os.path.splitext(fname)
            if ext.lower() != ".png":
                continue
            with Image.open(os.path.join(src_dir, fname)) as img:
                img = img.convert("RGB")
                for tag, box, scale in crops_for(stem, img.size):
                    _save(img, box, scale, os.path.join(out_dir, f"{stem}__{tag}.png"))
                    count += 1
    print(f"wrote {count} crops under {out_root}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
