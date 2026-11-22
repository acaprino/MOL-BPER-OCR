"""Small building blocks shared by the tabs."""

from __future__ import annotations

from datetime import datetime

from PyQt6 import QtCore, QtWidgets

import theme

from . import icons


def default_export_name() -> str:
    """File name proposed when exporting: readable, unlike a session id."""
    return f"pratiche_{datetime.now():%Y%m%d_%H%M}.xlsx"


class Card(QtWidgets.QFrame):
    """A rounded panel grouping related controls, with an optional title."""

    def __init__(self, title: str = "", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.content = QtWidgets.QVBoxLayout(self)
        self.content.setContentsMargins(16, 14, 16, 16)
        self.content.setSpacing(10)
        if title:
            label = QtWidgets.QLabel(title, self)
            label.setObjectName("cardTitle")
            self.content.addWidget(label)


class CollapsiblePanel(QtWidgets.QFrame):
    """A titled section that starts closed and says in one line what is inside."""

    def __init__(self, title: str, content: QtWidgets.QWidget, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self._title = title
        self._content = content

        self.toggle_button = QtWidgets.QToolButton(self)
        self.toggle_button.setObjectName("panelToggle")
        self.toggle_button.setText(title)
        self.toggle_button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setToolTip("Mostra o nascondi il registro")
        self.summary_label = QtWidgets.QLabel(self)
        self.summary_label.setProperty("muted", True)

        header = QtWidgets.QHBoxLayout()
        header.addWidget(self.toggle_button)
        header.addWidget(self.summary_label, stretch=1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addWidget(content, stretch=1)

        self.toggle_button.toggled.connect(self.set_expanded)
        self.set_expanded(False)

    def is_expanded(self) -> bool:
        return self.toggle_button.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        if self.toggle_button.isChecked() != expanded:
            self.toggle_button.setChecked(expanded)  # re-enters here through toggled
            return
        self._content.setVisible(expanded)
        self.toggle_button.setIcon(
            icons.icon("chevron-down" if expanded else "chevron-right", theme.current_tokens().text, 16)
        )
        # Closed, the panel hugs its header; open, it takes the room that is left.
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding if expanded else QtWidgets.QSizePolicy.Policy.Maximum,
        )

    def set_summary(self, text: str) -> None:
        self.summary_label.setText(text)
