"""One background Excel export at a time for both tabs of an Edge Agent window."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6 import QtCore, QtWidgets

from local_extraction_client import LocalExtractionClient
from .widgets import default_export_name


class WorkbookExport(QtCore.QObject):
    settled = QtCore.pyqtSignal(bool)
    _enabled = QtCore.pyqtSignal(bool)
    _caption = QtCore.pyqtSignal(str)
    _completed = QtCore.pyqtSignal(str, int, str)

    def __init__(self, client: LocalExtractionClient, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self._client = client
        self._owner: QtWidgets.QWidget | None = None
        self._log: Callable[[str], None] | None = None
        self._pending_edits = False
        self._edit_failed = False
        self._selected: tuple[str, str] | None = None
        self._completed.connect(self._finish, QtCore.Qt.ConnectionType.QueuedConnection)

    @property
    def busy(self) -> bool:
        return self._owner is not None

    def bind_button(self, button: QtWidgets.QPushButton) -> None:
        self._enabled.connect(button.setEnabled)
        self._caption.connect(button.setText)
        self._update_buttons()

    def set_edits_pending(self, pending: bool, failed: bool) -> None:
        self._pending_edits = pending
        if self.busy and failed:
            self._edit_failed = True
        self._update_buttons()
        self._start_selected()

    def _update_buttons(self) -> None:
        self._enabled.emit(not self.busy and not self._pending_edits)
        self._caption.emit("Esportazione in corso…" if self.busy else "Esporta Excel")

    def start(self, owner: QtWidgets.QWidget, job_id: str | None,
              log: Callable[[str], None] | None = None) -> None:
        if self.busy or self._pending_edits:
            return
        if not job_id or self._client.practice_count(job_id) == 0:
            QtWidgets.QMessageBox.warning(
                owner, "Niente da esportare",
                "Non c'è ancora niente da esportare. Avvia la cattura e attendi almeno un'estrazione.",
            )
            return
        self._owner, self._log = owner, log
        self._edit_failed = False
        self._update_buttons()
        try:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                owner, "Salva Excel", default_export_name(), "File Excel (*.xlsx)",
            )
            if not path:
                self._release(False)
                return
            # Choosing a file can move focus and submit the current editor.
            self._selected = job_id, path
            self._start_selected()
        except Exception as exc:
            self._finish("", 0, str(exc) or type(exc).__name__)

    def _start_selected(self) -> None:
        if self._selected is None or self._pending_edits:
            return
        job_id, path = self._selected
        self._selected = None
        if self._edit_failed:
            self._finish(path, 0, "La modifica della cella non è stata salvata. "
                         "Verifica i dati prima di ripetere l'esportazione.")
            return
        try:
            QtCore.QThreadPool.globalInstance().start(lambda: self._save(job_id, path))
        except Exception as exc:
            self._finish(path, 0, str(exc) or type(exc).__name__)

    def _save(self, job_id: str, path: str) -> None:
        try:
            written = self._client.export_workbook(job_id, path)
        except Exception as exc:
            self._completed.emit(path, 0, str(exc) or type(exc).__name__)
        else:
            self._completed.emit(path, written, "")

    @QtCore.pyqtSlot(str, int, str)
    def _finish(self, path: str, written: int, error: str) -> None:
        try:
            if error:
                if self._log:
                    self._log(f"[ERROR] Export Excel fallita: {error}")
                QtWidgets.QMessageBox.critical(
                    self._owner, "Salvataggio non riuscito", f"Non riesco a salvare il file:\n{error}",
                )
            else:
                if self._log:
                    self._log(f"Export Excel salvata in: {path} ({written} pratiche)")
                QtWidgets.QMessageBox.information(
                    self._owner, "Esportazione completata", f"{written} pratiche salvate in:\n{path}",
                )
        finally:
            self._release(not error)

    def _release(self, success: bool) -> None:
        self._owner = None
        self._log = None
        self._update_buttons()
        self.settled.emit(success)
