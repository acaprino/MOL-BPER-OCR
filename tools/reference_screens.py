"""The nine screenshots behind the page catalog's labels, read from the clean practice archive (ADR 0032).

The page catalog and the classifier name the nine BPER pages "screen 1" .. "screen 9". The screenshots
those labels came from are the pages of the reference practice in data/dataset; tools/reference/fotogrammi.json
says which page each label is.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tools" / "reference"


def reference_screens() -> dict[str, Path]:
    """Page-catalog label ("screen N") -> its screenshot in data/dataset."""
    frames = json.loads((REFERENCE / "fotogrammi.json").read_text(encoding="utf-8"))
    folder = ROOT / "data" / "dataset" / "pratiche" / frames["pratica"]
    return {label: folder / f"{name}.png" for label, name in frames["fotogrammi"].items()}
