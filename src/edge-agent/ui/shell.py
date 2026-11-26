"""Window chrome: the side navigation and the status header."""

from __future__ import annotations

from typing import List

from PyQt6 import QtCore, QtGui, QtWidgets

import theme

from . import icons

# ============================================================
# Navigation
# ============================================================


class NavRail(QtWidgets.QFrame):
    """Vertical list of pages; one is always selected."""

    page_selected = QtCore.pyqtSignal(int)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("navRail")
        self.setFixedWidth(176)

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(8, 12, 8, 12)
        self._layout.setSpacing(4)
        self._layout.addStretch(1)

        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: List[QtWidgets.QToolButton] = []

    def add_page(self, label: str, icon_name: str) -> int:
        """Append a page and return its index; the first one starts selected."""
        index = len(self._buttons)
        button = QtWidgets.QToolButton(self)
        button.setText(label)
        icons.bind_icon(button, icon_name, "text", 20)
        button.setIconSize(QtCore.QSize(20, 20))
        button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        button.setCheckable(True)
        button.setProperty("nav", True)
        self._group.addButton(button, index)
        self._layout.insertWidget(index, button)
        button.clicked.connect(lambda _checked=False, i=index: self.page_selected.emit(i))
        self._buttons.append(button)
        if index == 0:
            button.setChecked(True)
        return index

    def set_current(self, index: int) -> None:
        self._buttons[index].setChecked(True)
        self.page_selected.emit(index)


# ============================================================
# Status header
# ============================================================


class StatusHeader(QtWidgets.QFrame):
    """What the capture is doing, always visible, with the one primary action."""

    toggle_requested = QtCore.pyqtSignal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusHeader")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(16)

        self.state_label = QtWidgets.QLabel(self)
        self.state_label.setObjectName("headerState")
        self.counters_label = QtWidgets.QLabel(self)
        self.counters_label.setProperty("muted", True)
        self.toggle_button = QtWidgets.QPushButton(self)
        self.toggle_button.setProperty("primary", True)
        self.toggle_button.setAccessibleName("Avvia o ferma la cattura")
        # Not setShortcut() on the button: QAbstractButton.setText() replaces it, and the
        # text changes with the state (Avvia/Ferma). A window-level shortcut survives.
        QtGui.QShortcut(QtGui.QKeySequence("F9"), self, activated=self.toggle_button.click)
        self.toggle_button.clicked.connect(self.toggle_requested)

        layout.addWidget(self.state_label)
        layout.addWidget(self.counters_label)
        layout.addStretch(1)
        layout.addWidget(self.toggle_button)

        self._running = False
        self._resume = False
        theme.notifier().changed.connect(self._retint)
        self.set_running(False)
        self.set_counters(0, 0, 0)

    def _retint(self) -> None:
        self.toggle_button.setIcon(
            icons.icon("square" if self._running else "play", theme.current_tokens().on_primary, 16)
        )

    def set_stopping(self) -> None:
        self.state_label.setText("Arresto della cattura in corso")
        self.toggle_button.setEnabled(False)
        self.toggle_button.setText("Arresto…")
        self.toggle_button.setToolTip("Attendi il termine della cattura")

    def set_running(self, running: bool) -> None:
        self._running = running
        self.toggle_button.setEnabled(True)
        # State is spelled out in words, never carried by the glyph alone.
        self.state_label.setText("● Cattura in corso" if running else "○ Cattura ferma")
        self.toggle_button.setText("Ferma" if running else ("Riprendi" if self._resume else "Avvia"))
        self._retint()
        self.toggle_button.setToolTip("Ferma la cattura (F9)" if running else "Avvia la cattura (F9)")

    def set_resume_selected(self, selected: bool) -> None:
        self._resume = selected
        if not self._running:
            self.toggle_button.setText("Riprendi" if selected else "Avvia")

    def set_counters(self, queued: int, done: int, practices: int) -> None:
        self.counters_label.setText(f"{done} elaborati su {queued} · {practices} pratiche")
