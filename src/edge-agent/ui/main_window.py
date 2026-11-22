"""Finestra principale dell'applicazione Edge Agent."""

from __future__ import annotations

from typing import List, Optional, Sequence

from PyQt6 import QtCore, QtGui, QtWidgets
import theme
from config import AgentConfig
from local_extraction_client import LocalExtractionClient

from .capture_tab import CaptureTab
from .data_table_tab import DataTableTab
from .debug_tab import DebugTab
from .shell import NavRail, StatusHeader
from . import win_effects

# ============================================================
# Closing with unexported data
# ============================================================


def leave_message(labels: Sequence[str], pending: int) -> str:
    """Text of the dialog shown when closing with sessions not exported yet."""
    parts = []
    if labels:
        parts.append("Ci sono dati non ancora esportati:\n" + "\n".join(f"• {label}" for label in labels))
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
        self.extraction_client = extraction_client or LocalExtractionClient(parent=self)

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
        )

        # Tab dati estratti (spreadsheet)
        self.data_tab = DataTableTab(
            extraction_client=self.extraction_client,
            parent=self,
        )

        self.nav = NavRail(self)
        self.header = StatusHeader(self)
        self.stack = QtWidgets.QStackedWidget(self)

        # Capture = 0, Extracted data = 1, Debug LLM = 2 (only with --debug).
        self.stack.addWidget(self.capture_tab)
        self.nav.add_page("Cattura", "scan")
        self.stack.addWidget(self.data_tab)
        self.nav.add_page("Dati estratti", "table")
        if self.debug_tab is not None:
            self.stack.addWidget(self.debug_tab)
            self.nav.add_page("Debug LLM", "bug")

        right = QtWidgets.QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self.header)
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
        self.capture_tab.running_changed.connect(self.header.set_running)
        self.capture_tab.counters_changed.connect(self._on_counters)

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

    def _on_counters(self, queued: int, done: int) -> None:
        job_id = self.capture_tab.get_current_job_id()
        practices = self.extraction_client.practice_count(job_id) if job_id else 0
        self.header.set_counters(queued, done, practices)

    # ------------------------------------------------------------------ Chiusura finestra

    def _ask_leave_unexported(self, labels: List[str], pending: int) -> bool:
        """True if the operator chooses to leave without exporting."""
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        box.setWindowTitle("Dati non esportati")
        box.setText(leave_message(labels, pending))
        back = box.addButton("Torna all'app", QtWidgets.QMessageBox.ButtonRole.RejectRole)
        leave = box.addButton("Esci senza esportare", QtWidgets.QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(back)
        box.setEscapeButton(back)
        box.exec()
        return box.clickedButton() is leave

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        # Before stopping the capture: whoever goes back must lose nothing.
        unexported = self.extraction_client.unexported_jobs()
        # Frames still being extracted count even when nothing is "modified" yet:
        # shutdown() discards them, so their result would be lost without a word.
        pending = self.extraction_client.frames_in_progress()
        if unexported or pending > 0:
            labels = [self.extraction_client.session_label(job_id) for job_id in unexported]
            if not self._ask_leave_unexported(labels, pending):
                event.ignore()
                return
        try:
            if hasattr(self.capture_tab, "stop_capture"):
                self.capture_tab.stop_capture()
        except Exception:
            pass
        try:
            self.extraction_client.shutdown()
        except Exception:
            pass
        super().closeEvent(event)
