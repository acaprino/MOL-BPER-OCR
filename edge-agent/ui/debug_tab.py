from __future__ import annotations

"""
DebugTab: mostra l'output grezzo del router LLM (prompt/risposta/parsed).

Attende stringhe JSON via metodo append_json().
"""

from typing import Optional
from PyQt6 import QtWidgets


class DebugTab(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        self.text = QtWidgets.QTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.text)

        self.setLayout(layout)

    def append_json(self, json_str: str) -> None:
        try:
            # Stampa con separatore per facilitare la lettura
            self.text.append("==== LLM DEBUG ====")
            self.text.append(json_str)
            self.text.ensureCursorVisible()
        except Exception:
            # Non deve mai bloccare l'app
            pass
