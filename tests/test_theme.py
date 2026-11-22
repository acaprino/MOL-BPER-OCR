"""Tests for src/edge-agent/theme.py (tokens, contrast, stylesheet, light/dark)."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import Qt

import theme

# (foreground token, background token, minimum WCAG contrast)
PAIRS = [
    ("text", "background", 4.5),
    ("text", "surface", 4.5),
    ("text_muted", "surface", 4.5),
    ("text_muted", "background", 4.5),
    ("on_primary", "primary", 4.5),
    ("danger", "surface", 4.5),
    ("text", "corrected_bg", 4.5),
    ("corrected_icon", "corrected_bg", 3.0),
    ("focus", "background", 3.0),
    ("focus", "surface", 3.0),
    ("input_border", "surface", 3.0),
]


@pytest.mark.parametrize("tokens", [theme.LIGHT, theme.DARK], ids=lambda t: t.name)
def test_text_and_component_pairs_meet_wcag_contrast(tokens: theme.Tokens) -> None:
    failures = [
        (fg, bg, round(theme.contrast_ratio(getattr(tokens, fg), getattr(tokens, bg)), 2))
        for fg, bg, minimum in PAIRS
        if theme.contrast_ratio(getattr(tokens, fg), getattr(tokens, bg)) < minimum
    ]
    assert failures == []


def test_contrast_ratio_matches_the_wcag_reference_values() -> None:
    assert theme.contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert theme.contrast_ratio("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.01)


@pytest.mark.parametrize("tokens", [theme.LIGHT, theme.DARK], ids=lambda t: t.name)
def test_stylesheet_has_no_unresolved_placeholders(tokens: theme.Tokens) -> None:
    assert "$" not in theme.build_stylesheet(tokens)


def test_stylesheet_styles_focus_for_every_input_widget() -> None:
    qss = theme.build_stylesheet(theme.LIGHT)
    for selector in ("QPushButton:focus", "QLineEdit:focus", "QComboBox:focus", "QTableView:focus"):
        assert selector in qss


def test_apply_theme_follows_the_system_scheme(qapp) -> None:
    tokens = theme.apply_theme(qapp)
    expected = theme.DARK if qapp.styleHints().colorScheme() == Qt.ColorScheme.Dark else theme.LIGHT
    assert tokens is expected
    assert qapp.styleSheet() != ""
    assert theme.current_tokens() is expected


def test_apply_theme_can_pin_a_scheme(qapp) -> None:
    assert theme.apply_theme(qapp, Qt.ColorScheme.Dark) is theme.DARK
    assert theme.current_tokens() is theme.DARK
    assert theme.apply_theme(qapp, Qt.ColorScheme.Light) is theme.LIGHT


# ============================================================
# Final-review fixes
# ============================================================

from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QPushButton


@pytest.mark.parametrize("scheme", [Qt.ColorScheme.Light, Qt.ColorScheme.Dark], ids=["light", "dark"])
@pytest.mark.parametrize("primary", [False, True], ids=["secondary", "primary"])
def test_keyboard_focus_is_visible_on_every_button(qapp, scheme, primary: bool) -> None:
    theme.apply_theme(qapp, scheme)
    button = QPushButton("Avvia")
    button.setProperty("primary", primary)
    button.show()
    button.activateWindow()
    assert QTest.qWaitForWindowActive(button, 2000), "the window never became active"
    button.clearFocus()  # a lone button takes focus when its window activates
    qapp.processEvents()
    before = button.grab().toImage()
    button.setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()
    after = button.grab().toImage()
    button.hide()
    theme.apply_theme(qapp)
    assert before != after


def test_the_stylesheet_builds_when_the_temp_folder_is_not_writable(monkeypatch, tmp_path) -> None:
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x")
    monkeypatch.setattr(theme.tempfile, "gettempdir", lambda: str(blocker))
    assert "QPushButton" in theme.build_stylesheet(theme.LIGHT)
