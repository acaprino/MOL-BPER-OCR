"""Finestra principale dell'applicazione Edge Agent."""

from __future__ import annotations

from typing import List, Optional, Sequence

from PyQt6 import QtCore, QtGui, QtWidgets
import app_paths
import theme
from config import AgentConfig
from local_extraction_client import LocalExtractionClient

from .capture_tab import CaptureTab
from .data_table_tab import DataTableTab
from .debug_tab import DebugTab
from .queue_tab import QueueTab
from .shell import NavRail, StatusHeader
from .workbook_export import WorkbookExport
from . import win_effects

# ============================================================
# Closing with unexported data
# ============================================================


def leave_message(labels: Sequence[str], pending: int, *, recoverable: bool = False) -> str:
    """Text of the dialog shown when closing with sessions not exported yet."""
    parts = []
    if labels:
        parts.append("Ci sono dati non ancora esportati:\n" + "\n".join(f"• {label}" for label in labels))
    if recoverable:
        if pending:
            parts.append(f"{pending} frame ancora in elaborazione. Il lavoro salvato riprenderà alla riapertura.")
        parts.append("Le sessioni salvate resteranno disponibili alla riapertura, anche per l’esportazione.")
        return "\n\n".join(parts)
    if pending > 0:
        note = "il loro risultato non sarà incluso" if labels else "se esci ora andranno persi"
        parts.append(f"{pending} frame ancora in elaborazione: {note}.")
    if labels:
        parts.append("Se esci ora andranno persi.")
    return "\n\n".join(parts)


# ============================================================
# Window
# ============================================================


class MainWindow(QtWidgets.QMainWindow):
    """
    Finestra principale dell'app Edge Agent.

    Contiene:
        - una barra di navigazione laterale (Cattura, Dati estratti, Debug LLM con --debug);
        - una barra di stato sempre visibile con il pulsante Avvia/Ferma;
        - la tab "Cattura" per gestire job e worker di screenshot;
        - la tab "Dati estratti" con una riga per pratica consolidata.

    Condivide:
        - AgentConfig
        - LocalExtractionClient

    e sincronizza automaticamente il job_id tra le due tab.
    """

    def __init__(
        self,
        config: AgentConfig,
        show_debug: bool = False,
        parent: Optional[QtWidgets.QWidget] = None,
        extraction_client: Optional[LocalExtractionClient] = None,
    ) -> None:
        super().__init__(parent)

        self.config = config
        self._show_debug = show_debug
        self._close_pending = False
        self._close_after_export = False
        self._close_after_write = False
        self._discard_confirmed = False
        self._recovery_failed = False
        self.extraction_client = extraction_client or LocalExtractionClient(
            parent=self, recovery_dir=app_paths.recovery_dir(),
        )
        self.workbook_export = WorkbookExport(self.extraction_client, self)
        self.workbook_export.settled.connect(self._after_export)

        self.setWindowTitle("BPER Edge Agent")
        self.resize(1180, 760)
        self._init_ui()

        # Title bar (and Mica, if enabled) follow the theme, also when Windows switches.
        # A bound method, not a lambda: Qt drops the connection with the window.
        self._effects_applied = False
        QtWidgets.QApplication.instance().styleHints().colorSchemeChanged.connect(self._on_scheme_changed)

    # ------------------------------------------------------------------ UI setup

    def _init_ui(self) -> None:
        # Tab opzionale di debug LLM (visibile solo con --debug)
        self.debug_tab = None
        if self._show_debug:
            self.debug_tab = DebugTab(parent=self)

        # Tab di cattura
        self.capture_tab = CaptureTab(
            config=self.config,
            api_client=self.extraction_client,
            parent=self,
            debug_tab=self.debug_tab,
            workbook_export=self.workbook_export,
        )

        # Tab dati estratti (spreadsheet)
        self.data_tab = DataTableTab(
            extraction_client=self.extraction_client,
            parent=self,
            workbook_export=self.workbook_export,
        )

        self.nav = NavRail(self)
        self.header = StatusHeader(self)
        self.stack = QtWidgets.QStackedWidget(self)

        self.stack.addWidget(self.capture_tab)
        self.nav.add_page("Cattura", "scan")
        self.stack.addWidget(self.data_tab)
        self.nav.add_page("Dati estratti", "table")
        if self.debug_tab is not None:
            self.stack.addWidget(self.debug_tab)
            self.nav.add_page("Debug LLM", "bug")
        self.stack.addWidget(QueueTab(self.extraction_client, self))
        self.nav.add_page("Coda", "refresh-cw")

        right = QtWidgets.QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self.header)
        self.recovery_notice = QtWidgets.QLabel(self)
        self.recovery_notice.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.recovery_notice.setWordWrap(True)
        self.recovery_notice.setMargin(10)
        self.recovery_notice.hide()
        right.addWidget(self.recovery_notice)
        right.addWidget(self.stack, stretch=1)

        root = QtWidgets.QWidget(self)
        layout = QtWidgets.QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.nav)
        layout.addLayout(right, stretch=1)
        self.setCentralWidget(root)

        self.nav.page_selected.connect(self._on_page_selected)
        self.header.toggle_requested.connect(self._toggle_capture)
        self.capture_tab.running_changed.connect(self._on_running_changed)
        self.capture_tab.stopping.connect(self.header.set_stopping)
        self.capture_tab.counters_changed.connect(self._on_counters)
        self.data_tab.writes_pending_changed.connect(self._on_writes_pending)
        self.capture_tab.resume_selected.connect(self.header.set_resume_selected)
        self.header.set_resume_selected(self.capture_tab.get_current_job_id() is not None)
        self.capture_tab.refresh_counters()
        self.extraction_client.history_warning.connect(self._on_history_warning)
        self.extraction_client.recovery_error.connect(self._on_recovery_error)
        if self.extraction_client.recovered_from_backup:
            self._on_history_warning(
                "Sessioni ripristinate dalla copia di riserva. Verifica gli ultimi dati acquisiti."
            )
        if self.extraction_client.history_problem:
            self._on_history_warning(self.extraction_client.history_problem)
        if self.extraction_client.recovery_problem:
            self._on_recovery_error(self.extraction_client.recovery_problem)

    @QtCore.pyqtSlot(str)
    def _on_history_warning(self, message: str) -> None:
        self.capture_tab.log_warning(message)
        if not self._recovery_failed:
            self.recovery_notice.setText(message)
            self.recovery_notice.show()

    @QtCore.pyqtSlot(str)
    def _on_recovery_error(self, message: str) -> None:
        self._recovery_failed = True
        self.capture_tab.stop_capture()
        self.header.toggle_button.setEnabled(False)
        self.recovery_notice.setText(f"Salvataggio della sessione interrotto. {message}")
        self.recovery_notice.show()

    # ------------------------------------------------------------------ Eventi

    def _on_scheme_changed(self, _scheme: QtCore.Qt.ColorScheme) -> None:
        self._apply_window_effects()

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # type: ignore[override]
        super().showEvent(event)
        if not self._effects_applied:
            self._effects_applied = True
            self._apply_window_effects()

    def _apply_window_effects(self) -> None:
        win_effects.apply_window_effects(self, dark=theme.current_tokens().name == "dark")

    def _on_page_selected(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        job_id = None
        if hasattr(self.capture_tab, "get_current_job_id"):
            job_id = self.capture_tab.get_current_job_id()
        # Cattura = 0, Dati Estratti = 1 (era 2 quando esisteva il tab Risultati).
        if job_id and index == 1 and hasattr(self.data_tab, "set_job_id"):
            self.data_tab.set_job_id(job_id)

    def _toggle_capture(self) -> None:
        if self.capture_tab.is_running():
            self.capture_tab.stop_capture()
        else:
            self.capture_tab.start_capture()

    def _on_running_changed(self, running: bool) -> None:
        self.header.set_running(running)
        if self._recovery_failed:
            self.header.toggle_button.setEnabled(False)
        if self._close_pending and not running:
            self._close_pending = False
            self.close()

    def _on_counters(self, queued: int, done: int) -> None:
        job_id = self.capture_tab.get_current_job_id()
        practices = self.extraction_client.practice_count(job_id) if job_id else 0
        self.header.set_counters(queued, done, practices)

    # ------------------------------------------------------------------ Chiusura finestra

    def _on_writes_pending(self, pending: bool) -> None:
        if pending or not self._close_after_write:
            return
        self._close_after_write = False
        self.statusBar().clearMessage()
        if self.data_tab.last_write_failed:
            self.nav.set_current(1)
        else:
            QtCore.QTimer.singleShot(0, self.close)

    def _ask_leave_unexported(self, labels: List[str], pending: int) -> bool:
        """True if the operator chooses to leave without exporting."""
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        box.setWindowTitle("Dati non esportati")
        durable = self.extraction_client.has_recovery
        box.setText(leave_message(labels, pending, recoverable=durable))
        back = box.addButton("Torna all'app", QtWidgets.QMessageBox.ButtonRole.RejectRole)
        if durable:
            leave = box.addButton("Esci e conserva le sessioni", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        else:
            leave = box.addButton("Esci senza esportare", QtWidgets.QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(back)
        box.setEscapeButton(back)
        box.exec()
        return box.clickedButton() is leave

    @QtCore.pyqtSlot(bool)
    def _after_export(self, success: bool) -> None:
        if self._close_after_export:
            self._close_after_export = False
            self.statusBar().clearMessage()
            if success:
                QtCore.QTimer.singleShot(0, self.close)
            else:
                self._discard_confirmed = False

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        if self.workbook_export.busy:
            self._close_after_export = True
            self.statusBar().showMessage("La finestra si chiuderà al termine dell'esportazione.")
            event.ignore()
            return
        if self._close_pending:
            event.ignore()
            return
        if self.data_tab.has_pending_writes():
            self._close_after_write = True
            self.data_tab.leave_draft_open()
            self.statusBar().showMessage("Chiusura in attesa del salvataggio delle modifiche…")
            event.ignore()
            return
        # Before stopping the capture: whoever goes back must lose nothing.
        if not self._discard_confirmed:
            # A frame that finishes during the export check must appear in at least one count.
            pending = self.extraction_client.frames_in_progress()
            unexported = self.extraction_client.unexported_jobs()
            if unexported or pending > 0:
                labels = [self.extraction_client.session_label(job_id) for job_id in unexported]
                if not self._ask_leave_unexported(labels, pending):
                    event.ignore()
                    return
                self._discard_confirmed = True
        self.capture_tab.stop_capture()
        if self.capture_tab.is_running():
            # Keep the QThread and its window alive while an outstanding capture returns.
            self._close_pending = True
            event.ignore()
            return
        self.data_tab.leave_draft_open()
        self.extraction_client.shutdown()
        self._discard_confirmed = False
        super().closeEvent(event)
