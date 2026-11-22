"""Test for tools/ui_screenshots.py (the visual review tool)."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from tools.ui_screenshots import main


def test_ui_screenshots_writes_the_six_pngs(tmp_path, qapp) -> None:
    assert main(["--out", str(tmp_path)]) == 0
    written = sorted(p.name for p in tmp_path.glob("*.png"))
    assert written == [
        "dark-capture.png",
        "dark-data-empty.png",
        "dark-data.png",
        "light-capture.png",
        "light-data-empty.png",
        "light-data.png",
    ]
    assert all(p.stat().st_size > 1000 for p in tmp_path.glob("*.png"))
