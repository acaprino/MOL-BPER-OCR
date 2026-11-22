"""Windows window effects through DWM: a title bar that follows the theme, and Mica.

No new dependency (not `pywinstyles`): two documented DWM attributes set with ctypes.
Everything is a no-op off Windows or on a build that does not know the attribute, and a
failing call never raises: these are finishing touches, not features.
"""

from __future__ import annotations

import ctypes
import sys

from PyQt6 import QtWidgets

# ============================================================
# DWM constants
# ============================================================

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38
BACKDROP_MICA = 2

MIN_BUILD_DARK_TITLE_BAR = 19041  # Windows 10 2004
MIN_BUILD_MICA = 22621            # Windows 11 22H2

# shortcut: Mica stays off until a real capture shows the captured frames unchanged;
# flip to True after that check. The dark title bar has no such doubt and is always on.
USE_MICA = False


def _windows_build() -> int:
    return sys.getwindowsversion().build if sys.platform == "win32" else 0  # type: ignore[attr-defined]


def _set_attribute(hwnd: int, attribute: int, value: int) -> bool:
    """DwmSetWindowAttribute; True when Windows accepted the value."""
    data = ctypes.c_int(value)
    result = ctypes.windll.dwmapi.DwmSetWindowAttribute(  # type: ignore[attr-defined]
        ctypes.c_void_p(hwnd), ctypes.c_uint(attribute), ctypes.byref(data), ctypes.sizeof(data)
    )
    return result == 0


def apply_window_effects(window: QtWidgets.QWidget, dark: bool) -> bool:
    """Apply what this Windows build supports; True if anything was applied."""
    if sys.platform != "win32":
        return False
    build = _windows_build()
    try:
        hwnd = int(window.winId())
        applied = False
        if build >= MIN_BUILD_DARK_TITLE_BAR:
            applied |= _set_attribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, int(dark))
        if USE_MICA and build >= MIN_BUILD_MICA:
            applied |= _set_attribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, BACKDROP_MICA)
        return applied
    except OSError:
        return False
