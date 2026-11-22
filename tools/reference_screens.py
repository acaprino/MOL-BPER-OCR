"""The nine screenshots behind the page catalog's labels, read from the practice archive (ADR 0030).

The page catalog and the classifier name the nine BPER pages "screen 1" .. "screen 9". The screenshots
those labels came from are the pages of the reference practice in data/pratiche; fotogrammi.json of its
lot says which page each label is.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_LOT = ROOT / "data" / "revisione" / "riferimento-2025-09-09"


def reference_screens() -> dict[str, Path]:
    """Page-catalog label ("screen N") -> its screenshot in data/pratiche."""
    frames = json.loads((REFERENCE_LOT / "fotogrammi.json").read_text(encoding="utf-8"))
    folder = ROOT / "data" / "pratiche" / frames["pratica"]
    return {label: folder / f"{page}.png" for label, page in frames["fotogrammi"].items()}
