"""The dependency pins must match what the code uses."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_pyqt6_floor_covers_the_apis_the_theme_uses() -> None:
    # QStyleHints.colorSchemeChanged and Qt.ColorScheme arrived in Qt/PyQt 6.5.
    match = re.search(r"^PyQt6>=(\d+)\.(\d+)", (ROOT / "requirements.txt").read_text(encoding="utf-8"), re.M)
    assert match and (int(match.group(1)), int(match.group(2))) >= (6, 5)


def test_the_modal_image_installs_neither_qt_material_nor_an_old_pyqt6() -> None:
    text = (ROOT / "tools" / "modal_tests.py").read_text(encoding="utf-8")
    assert "qt-material" not in text
    assert "PyQt6>=6.4" not in text
