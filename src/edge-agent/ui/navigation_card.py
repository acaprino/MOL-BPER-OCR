"""Display the capture worker's last navigation update for the operator."""

from __future__ import annotations

from typing import Any

from PyQt6 import QtCore, QtWidgets

from .widgets import Card


_VIEW_GROUPS = {
    "missing": "Da acquisire", "optional": "Se presente",
    "unavailable": "Non applicabile", "captured": "Acquisita",
}
_ACTIONS = {"optional": "Non applicabile", "unavailable": "Ripristina", "captured": "Da riacquisire"}


class NavigationCard(Card):
    availability_requested = QtCore.pyqtSignal(str, str, bool)
    reopen_requested = QtCore.pyqtSignal(str, str)

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__("Guida alla pratica", parent)
        self._ndg: str | None = None
        self._decision_key: str | None = None
        self._choices: list[tuple[str, str]] = []
        self._live = False
        self.current = QtWidgets.QLabel(self)
        self.next_step = QtWidgets.QLabel(self)
        for label in (self.current, self.next_step):
            label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            self.content.addWidget(label)

        row = QtWidgets.QHBoxLayout()
        self.view_count = QtWidgets.QLabel(self)
        self.views = QtWidgets.QComboBox(self)
        self.views.setAccessibleName("Stato delle viste della pratica")
        self.views.setMinimumContentsLength(12)
        self.views.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.availability_button = QtWidgets.QPushButton(self)
        row.addWidget(self.view_count)
        row.addWidget(self.views, 1)
        row.addWidget(self.availability_button)
        self.content.addLayout(row)
        self.views.currentIndexChanged.connect(self._update_choice)
        self.availability_button.clicked.connect(self._change_availability)
        self.show_progress({})

    def show_progress(self, progress: dict[str, Any]) -> None:
        ndg = progress.get("practice_ndg")
        page = progress.get("current_page")
        identity = f"NDG {ndg}" if ndg else "NDG da identificare"
        if progress.get("new_selection"):
            identity = ("Numero pratica da verificare" if progress.get("verifying_previous")
                        else "Nuova selezione · pratica da identificare")
        elif progress.get("browsing"):
            identity = "Elenco Pratiche"
        elif progress.get("practice_number"):
            identity = f"Pratica {progress['practice_number']} · {identity}"
        if ndg and progress.get("identity_source") == "preceding":
            identity += " (dalla cattura precedente)"
        status = {
            "recognizing": "riconoscimento in corso",
            "observed": "vista rilevata", "pending": "estrazione in corso",
            "captured": "acquisita", "error": "da riprovare", "review": "da riacquisire",
            "unrecognized": "vista non riconosciuta",
        }.get(progress.get("status"), "")
        self.current.setText(" · ".join(filter(None, (identity, page, status))))
        target = progress.get("next_page")
        action = progress.get("action") or ""
        self.next_step.setText(f"Prossima vista · {target}\n{action}".rstrip() if target else action)
        self.next_step.setVisible(bool(self.next_step.text()))
        coverage_ndg = progress.get("coverage_ndg") or ndg
        if progress and not coverage_ndg and self._ndg and not (
            progress.get("new_selection") or "decision_key" in progress
        ):
            self.view_count.setText(f"Viste ultimo NDG {self._ndg}")
            return
        decision_key = progress.get("decision_key", coverage_ndg)
        same_practice = decision_key == self._decision_key
        self._decision_key = decision_key
        previous = self.views.currentData() if same_practice else None
        self._ndg = coverage_ndg
        missing = progress.get("missing", [])
        if progress.get("browsing") and progress.get("practice_number"):
            self.view_count.setText(f"Viste pratica {progress['practice_number']}")
        elif coverage_ndg and not ndg:
            self.view_count.setText(f"Viste ultimo NDG {coverage_ndg}")
        else:
            self.view_count.setText(f"Da acquisire ({len(missing)})" if ndg or progress.get("new_selection") else "Viste")
        choices = [(key, name) for key in _VIEW_GROUPS for name in progress.get(key, [])]
        if not same_practice or choices != self._choices:
            with QtCore.QSignalBlocker(self.views):
                self.views.clear()
                for index, (key, name) in enumerate(choices):
                    self.views.addItem(f"{_VIEW_GROUPS[key]} · {name}", (key, name))
                    if previous and previous[1] == name:
                        self.views.setCurrentIndex(index)
            self._choices = choices
        self.views.setEnabled(bool(self.views.count()))
        self._update_choice()

    def set_live(self, live: bool) -> None:
        self._live = live
        self._update_choice()

    def finish_capture(self) -> None:
        self.set_live(False)
        identity = f" · ultimo NDG {self._ndg}" if self._ndg else ""
        self.current.setText(f"Cattura terminata{identity}")
        self.next_step.setText("Elenco delle viste all’arresto. Consulta Dati estratti per i risultati finali.")
        self.next_step.show()

    def _update_choice(self) -> None:
        choice = self.views.currentData()
        action = _ACTIONS.get(choice[0], "") if choice else ""
        editable = bool(self._live and self._decision_key and action)
        self.availability_button.setVisible(editable)
        self.availability_button.setEnabled(editable)
        self.availability_button.setText(action)
        self.views.setToolTip(self.views.currentText())

    def _change_availability(self) -> None:
        choice = self.views.currentData()
        if self.availability_button.isEnabled() and self._decision_key and choice:
            if choice[0] == "captured":
                self.reopen_requested.emit(self._decision_key, choice[1])
            else:
                self.availability_requested.emit(self._decision_key, choice[1], choice[0] == "unavailable")
