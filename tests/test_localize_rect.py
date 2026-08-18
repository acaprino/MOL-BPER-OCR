"""Localization must return a window, not a fragment of one."""

import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "frames"
REGISTRY = FRAMES / "registry.json"
RELOCALIZED = FRAMES / "relocalized.json"

# A browser window holding the application covers a large part of a 1920x1080
# desktop. Anything under a fifth of the frame is a panel or a table, not a window:
# the crop that produced it had already discarded the URL bar, the BPER logo and the
# navigator, which are exactly the marks that identify the application.
MIN_AREA_FRACTION = 0.20


def _rects():
    """Rectangles under test: the recomputed ones when present, else the registry's.

    relocalized.json is written by tools/relocalize.py after a geometry change, and
    covers whatever has been recomputed so far. Preferring it means the test
    measures the current localizer rather than the rectangles some earlier version
    happened to store.
    """
    if RELOCALIZED.exists():
        for frame, payload in json.loads(RELOCALIZED.read_text(encoding="utf-8")).items():
            rect = payload["rect"]
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w > 0 and h > 0:
                yield frame, w * h
        return
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for entry in registry["frames"]:
        rect = entry.get("app_rect")
        if not rect:
            continue
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        if w > 0 and h > 0:
            yield entry["frame"], w * h


@pytest.mark.skipif(not REGISTRY.exists(), reason="frame registry not present")
def test_localization_does_not_return_fragments():
    """A fragment crop is not a near miss, it is a different failure.

    Measured before this constraint existed: 36% of rectangles were under 0.6 Mpx
    against a median of 1.10, the worst being 249x203 on a 1920x1080 frame. Those
    crops made the classifier answer about a table it had been handed rather than
    about the page, and the answer was then recorded as a classification error.
    """
    frame_area = 1920 * 1080
    fragments = [(f, a) for f, a in _rects() if a < frame_area * MIN_AREA_FRACTION]
    total = sum(1 for _ in _rects())

    assert not fragments, (
        f"{len(fragments)}/{total} rettagli sotto il {MIN_AREA_FRACTION:.0%} del frame; "
        f"il piu' piccolo e' {min(a for _, a in fragments)/1e6:.3f} Mpx"
    )
