"""Contact sheets for human validation of machine-proposed page labels.

The corpus labels are proposed by a VLM, and a label set meant to judge a
classifier cannot itself be machine truth: scoring one model against another
model's labels measures agreement, not accuracy. These sheets exist so a human
can *correct* rather than annotate from scratch: one sheet per proposed label,
every tile numbered, so a correction is "sheet X, tile 12 is actually page Y".

    python tools/make_contact_sheets.py --labels <labels.json> --crops <dir> --out <dir>
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from PIL import Image, ImageDraw

TILE_W = 300
COLS = 6
MAX_TILES = 48  # per sheet; longer groups paginate


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "senza-nome"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", required=True, help="labels.json from the labelling run")
    ap.add_argument("--crops", required=True, help="directory holding the cropped frames")
    ap.add_argument("--out", required=True, help="output directory for the sheets")
    args = ap.parse_args()

    records = [r for r in json.loads(Path(args.labels).read_text(encoding="utf-8"))
               if r.get("file")]
    crops = Path(args.crops)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    groups: Dict[str, List[dict]] = defaultdict(list)
    for r in records:
        groups[r.get("label") or "(senza etichetta)"].append(r)

    index_lines = ["# Fogli di validazione", ""]
    for label in sorted(groups, key=lambda k: -len(groups[k])):
        entries = groups[label]
        for page_no in range(0, len(entries), MAX_TILES):
            chunk = entries[page_no:page_no + MAX_TILES]
            tile_h = None
            tiles = []
            for rec in chunk:
                img = Image.open(crops / rec["file"]).convert("RGB")
                h = int(TILE_W * img.height / img.width)
                tiles.append((rec, img, h))
                tile_h = max(tile_h or 0, h)
            tile_h = (tile_h or TILE_W) + 18  # caption strip

            rows = (len(tiles) + COLS - 1) // COLS
            sheet = Image.new("RGB", (COLS * TILE_W, rows * tile_h), (24, 24, 28))
            draw = ImageDraw.Draw(sheet)
            for i, (rec, img, h) in enumerate(tiles):
                x, y = (i % COLS) * TILE_W, (i // COLS) * tile_h
                sheet.paste(img.resize((TILE_W, h), Image.Resampling.LANCZOS), (x, y))
                n = page_no + i + 1
                draw.rectangle([x, y + tile_h - 18, x + TILE_W, y + tile_h], fill=(24, 24, 28))
                draw.text((x + 4, y + tile_h - 16),
                          f"{n:3}  {rec['file'][:34]}", fill=(230, 230, 230))

            suffix = f"_{page_no // MAX_TILES + 1}" if len(entries) > MAX_TILES else ""
            name = f"{_slug(label)}{suffix}.png"
            sheet.save(out / name)
            index_lines.append(f"- `{name}`: **{label}**, "
                               f"riquadri {page_no + 1}-{page_no + len(chunk)} di {len(entries)}")

    (out / "INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    print(f"{len(groups)} etichette, {len(records)} ritagli -> {out}")


if __name__ == "__main__":
    main()
