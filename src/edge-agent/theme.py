"""Visual theme of the edge-agent: design tokens, stylesheet, light/dark.

Top-level on purpose (not in `ui/`): `ui/__init__.py` imports `main_window`, which
pulls in `extraction` and reads the environment at import time. The theme is applied
before `bootstrap.run_preflight()`, so it must not import either.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from string import Template
from typing import Optional

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt

# ============================================================
# Tokens
# ============================================================


@dataclass(frozen=True)
class Tokens:
    """Every colour of the interface, in one place."""

    name: str
    background: str       # window
    surface: str          # cards, inputs, table
    surface_alt: str      # headers, hover
    border: str           # decorative separators
    input_border: str     # boundary of an input or button (>= 3:1 on surface)
    text: str
    text_muted: str
    primary: str
    primary_hover: str
    on_primary: str
    focus: str            # keyboard focus ring
    selection_bg: str
    danger: str
    corrected_bg: str     # cell the operator corrected
    corrected_icon: str


# Starting values come from the design spec; the contrast test is the authority
# (`corrected_icon` and the dark `danger` were moved to pass it).
LIGHT = Tokens(
    name="light",
    background="#F8FAFC",
    surface="#FFFFFF",
    surface_alt="#E9EEF6",
    border="#CBD5E1",
    input_border="#64748B",
    text="#0F172A",
    text_muted="#475569",
    primary="#1E40AF",
    primary_hover="#1E3A8A",
    on_primary="#FFFFFF",
    focus="#1E40AF",
    selection_bg="#DBEAFE",
    danger="#DC2626",
    corrected_bg="#FEF3C7",
    corrected_icon="#B45309",
)

DARK = Tokens(
    name="dark",
    background="#0F172A",
    surface="#1E293B",
    surface_alt="#334155",
    border="#475569",
    input_border="#94A3B8",
    text="#F8FAFC",
    text_muted="#94A3B8",
    primary="#60A5FA",
    primary_hover="#93C5FD",
    on_primary="#0F172A",
    focus="#93C5FD",
    selection_bg="#1E3A8A",
    danger="#F87171",
    corrected_bg="#422006",
    corrected_icon="#FBBF24",
)


# ============================================================
# Contrast (WCAG 2.x)
# ============================================================


def _luminance(color: str) -> float:
    digits = color.lstrip("#")
    red, green, blue = (int(digits[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4

    return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG contrast ratio between two #RRGGBB colours (1.0 to 21.0)."""
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


# ============================================================
# Stylesheet
# ============================================================

# `$name` is a token; string.Template leaves the QSS braces alone.
_QSS = Template("""
QMainWindow, QDialog, QMessageBox { background: $background; }
QWidget { color: $text; }
QLabel { background: transparent; }
QLabel[muted="true"] { color: $text_muted; }

QFrame#card { background: $surface; border: 1px solid $border; border-radius: 8px; }
QGroupBox { border: 1px solid $border; border-radius: 8px; margin-top: 12px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }

QToolTip { background: $surface; color: $text; border: 1px solid $input_border; padding: 4px 6px; }

QPushButton {
    background: $surface; color: $text; border: 1px solid $input_border;
    border-radius: 6px; padding: 6px 14px; min-height: 20px;
}
QPushButton:hover { background: $surface_alt; }
QPushButton:pressed { background: $selection_bg; }
QPushButton:focus { border: 2px solid $focus; padding: 5px 13px; }
QPushButton:disabled { color: $text_muted; background: $background; border-color: $border; }
QPushButton[primary="true"] { background: $primary; color: $on_primary; border: 1px solid $primary; }
QPushButton[primary="true"]:hover { background: $primary_hover; }
QPushButton[primary="true"]:focus { border: 2px solid $focus; }
QPushButton[primary="true"]:disabled { background: $surface_alt; color: $text_muted; border-color: $border; }

QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background: $surface; color: $text; border: 1px solid $input_border;
    border-radius: 6px; padding: 5px 8px;
    selection-background-color: $selection_bg; selection-color: $text;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 2px solid $focus; padding: 4px 7px;
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
    background: $background; color: $text_muted; border-color: $border;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: $surface; color: $text; border: 1px solid $input_border;
    selection-background-color: $selection_bg; selection-color: $text;
}

QTableView {
    background: $surface; alternate-background-color: $background; color: $text;
    gridline-color: $border; border: 1px solid $border;
    selection-background-color: $selection_bg; selection-color: $text;
}
QTableView:focus { border: 2px solid $focus; }
QHeaderView::section {
    background: $surface_alt; color: $text; padding: 6px 8px; font-weight: 600;
    border: none; border-right: 1px solid $border; border-bottom: 1px solid $border;
}

QMenu { background: $surface; color: $text; border: 1px solid $input_border; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 4px; }
QMenu::item:selected { background: $selection_bg; color: $text; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
QScrollBar::handle:vertical { background: $input_border; border-radius: 5px; min-height: 28px; margin: 2px; }
QScrollBar::handle:horizontal { background: $input_border; border-radius: 5px; min-width: 28px; margin: 2px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
""")


def build_stylesheet(tokens: Tokens) -> str:
    """The application stylesheet for one set of tokens."""
    return _QSS.substitute(asdict(tokens))


# ============================================================
# Applying
# ============================================================

_current: Tokens = LIGHT
_pinned: Optional[Qt.ColorScheme] = None
_following: bool = False


def current_tokens() -> Tokens:
    return _current


def _palette(tokens: Tokens) -> QtGui.QPalette:
    """Palette for what the stylesheet does not cover (dialog icons, scroll areas)."""
    palette = QtGui.QPalette()
    roles = {
        QtGui.QPalette.ColorRole.Window: tokens.background,
        QtGui.QPalette.ColorRole.WindowText: tokens.text,
        QtGui.QPalette.ColorRole.Base: tokens.surface,
        QtGui.QPalette.ColorRole.AlternateBase: tokens.background,
        QtGui.QPalette.ColorRole.Text: tokens.text,
        QtGui.QPalette.ColorRole.PlaceholderText: tokens.text_muted,
        QtGui.QPalette.ColorRole.Button: tokens.surface,
        QtGui.QPalette.ColorRole.ButtonText: tokens.text,
        QtGui.QPalette.ColorRole.Highlight: tokens.selection_bg,
        QtGui.QPalette.ColorRole.HighlightedText: tokens.text,
        QtGui.QPalette.ColorRole.ToolTipBase: tokens.surface,
        QtGui.QPalette.ColorRole.ToolTipText: tokens.text,
    }
    for role, color in roles.items():
        palette.setColor(role, QtGui.QColor(color))
    return palette


def _apply(app: QtWidgets.QApplication) -> Tokens:
    global _current
    scheme = _pinned if _pinned is not None else app.styleHints().colorScheme()
    _current = DARK if scheme == Qt.ColorScheme.Dark else LIGHT
    # Fusion: a predictable base for the stylesheet, same on every Windows build.
    app.setStyle("Fusion")
    app.setFont(QtGui.QFont("Segoe UI", 10))
    app.setPalette(_palette(_current))
    app.setStyleSheet(build_stylesheet(_current))
    return _current


def apply_theme(app: QtWidgets.QApplication, scheme: Optional[Qt.ColorScheme] = None) -> Tokens:
    """Apply the theme and keep following the system light/dark setting.

    `scheme` pins one scheme (review screenshots, tests); None follows Windows.
    """
    global _pinned, _following
    _pinned = scheme
    tokens = _apply(app)
    if not _following:
        _following = True
        app.styleHints().colorSchemeChanged.connect(lambda _scheme: _apply(app))
    return tokens
