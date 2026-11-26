"""Live, read-only view of screenshot work across capture sessions."""

from __future__ import annotations

from collections import Counter

from PyQt6 import QtCore, QtGui, QtWidgets

from local_extraction_client import LocalExtractionClient
from work_queue import RECENT_LIMIT, QueueRow, QueueSnapshot


_STATES = {
    "queued": "In coda",
    "preparing": "Apertura cattura",
    "reading": "In lettura",
    "retrying": "Secondo tentativo",
    "saving": "Salvataggio",
    "waiting": "In attesa delle precedenti",
    "failed_waiting": "Lettura fallita · in attesa delle precedenti",
    "done": "Elaborata",
    "uncertain": "Elaborata · identificazione incerta",
    "failed": "Lettura fallita",
    "timed_out": "Tempo di lettura scaduto",
    "storage_error": "Archivio non disponibile",
}


class _QueueModel(QtCore.QAbstractTableModel):
    headers = ("Sessione", "Cattura", "Schermata", "Stato")

    def __init__(self, parent: QtCore.QObject) -> None:
        super().__init__(parent)
        self.rows: tuple[QueueRow, ...] = ()

    def replace(self, rows: tuple[QueueRow, ...]) -> None:
        if len(rows) == len(self.rows) and all(
            (old.session, old.sequence) == (new.session, new.sequence) for old, new in zip(self.rows, rows)
        ):
            old_rows, self.rows = self.rows, rows
            for index, (old, new) in enumerate(zip(old_rows, rows)):
                if old is not new:
                    cell = self.index(index, 3)
                    self.dataChanged.emit(cell, cell, [QtCore.Qt.ItemDataRole.DisplayRole])
            return
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = 0) -> str | None:
        if role == QtCore.Qt.ItemDataRole.DisplayRole and orientation == QtCore.Qt.Orientation.Horizontal:
            return self.headers[section]
        return None

    def data(self, index: QtCore.QModelIndex, role: int = 0) -> str | None:
        if not index.isValid() or role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        row = self.rows[index.row()]
        return (row.session, str(row.sequence + 1), row.page, _STATES[row.state])[index.column()]


class QueueTab(QtWidgets.QWidget):
    def __init__(self, client: LocalExtractionClient, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self._client = client
        self._snapshot: QueueSnapshot | None = None
        self._model = _QueueModel(self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        title = QtWidgets.QLabel("Coda di elaborazione", self)
        title.setObjectName("cardTitle")
        layout.addWidget(title)
        self.summary = QtWidgets.QLabel(self)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QtWidgets.QTableView(self)
        self.table.setAccessibleName("Coda di elaborazione di tutte le sessioni")
        self.table.setModel(self._model)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.resizeSection(0, 165)
        header.resizeSection(1, 70)
        for column in (2, 3):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        self.caption = QtWidgets.QLabel(self)
        layout.addWidget(self.caption)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._refresh)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self._refresh()
        self._timer.start()

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _refresh(self) -> None:
        current = self._client.queue_snapshot(self._snapshot)
        if current is self._snapshot:
            return
        self._snapshot = current
        self._model.replace(current.rows)
        count = Counter(row.state for row in current.rows)
        active = count["reading"] + count["retrying"]
        waiting = count["waiting"] + count["failed_waiting"]
        reader = f"Lettore attivo (PID {current.pid})" if current.pid else "Lettore in attesa"
        self.summary.setText(f"{reader}   ·   In lettura {active}/{current.limit}   ·   "
                             f"In coda {count['queued']}   ·   In attesa delle precedenti {waiting}")
        self.caption.setText(f"Tutte le sessioni · Lavori aperti e ultimi {RECENT_LIMIT} esiti."
                             if current.rows else "Nessuna schermata acquisita.")
