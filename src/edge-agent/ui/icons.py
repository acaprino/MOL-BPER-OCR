"""Bundled SVG icons (Lucide, ISC licence), tinted at render time.

One style for the whole app: an icon is a file in `assets/icons/` drawn with
`currentColor`, so a theme change only needs another colour, not other files.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Final, Tuple

from PyQt6 import QtCore, QtGui
from PyQt6.QtSvg import QSvgRenderer

import app_paths

# The names Lucide gives the files; `assets/icons/LICENSE-lucide.txt` is the licence.
ICON_NAMES: Final[Tuple[str, ...]] = (
    "play",
    "square",
    "download",
    "camera",
    "search",
    "refresh-cw",
    "pencil",
    "undo-2",
    "chevron-down",
    "chevron-right",
    "table",
    "scan",
    "bug",
    "check",
    "triangle-exclamation-point",
)

ICONS_DIR = app_paths.bundled_assets_dir() / "icons"


@lru_cache(maxsize=None)
def _svg_source(name: str) -> str:
    if name not in ICON_NAMES:
        raise KeyError(f"Unknown icon: {name!r}")
    return (ICONS_DIR / f"{name}.svg").read_text(encoding="utf-8")


def icon(name: str, color: str, size: int = 20) -> QtGui.QIcon:
    """The icon `name` drawn in `color` (#RRGGBB), `size` logical pixels square."""
    svg = _svg_source(name).replace("currentColor", color)
    renderer = QSvgRenderer(QtCore.QByteArray(svg.encode("utf-8")))

    screen = QtGui.QGuiApplication.primaryScreen()
    ratio = screen.devicePixelRatio() if screen is not None else 1.0
    pixmap = QtGui.QPixmap(round(size * ratio), round(size * ratio))
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return QtGui.QIcon(pixmap)
