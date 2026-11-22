"""Tests for src/edge-agent/ui/icons.py (bundled SVG icons, tinted at render time)."""

import os

import pytest

pytest.importorskip("PyQt6.QtSvg")

# Must be set before ui/__init__ pulls in extraction.config (read at import time).
os.environ.setdefault("LLM_API_KEY", "test-key")

from ui import icons


def test_every_icon_name_has_an_svg_file() -> None:
    missing = [name for name in icons.ICON_NAMES if not (icons.ICONS_DIR / f"{name}.svg").is_file()]
    assert missing == []


def test_icon_renders_pixels_in_the_requested_color(qapp) -> None:
    image = icons.icon("play", "#1E40AF", 20).pixmap(20, 20).toImage()
    solid = [
        image.pixelColor(x, y)
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() > 200
    ]
    assert solid, "the icon rendered nothing"
    assert all(abs(c.red() - 0x1E) <= 3 and abs(c.green() - 0x40) <= 3 and abs(c.blue() - 0xAF) <= 3 for c in solid)


def test_unknown_icon_name_raises_key_error(qapp) -> None:
    with pytest.raises(KeyError):
        icons.icon("does-not-exist", "#000000")
