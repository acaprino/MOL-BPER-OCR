"""Finestra principale dell'applicazione Edge Agent."""

from __future__ import annotations

from typing import List, Optional, Sequence

from PyQt6 import QtWidgets
import theme
from config import AgentConfig
from extraction.normalization import is_nullish
from local_extraction_client import LocalExtractionClient
from practice_consolidation import consolidate

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
    lines = ["Ci sono dati non ancora esportati:"]
    lines += [f"• {label}" for label in labels]
    lines.append("")
    if pending > 0:
        lines.append(f"{pending} frame ancora in elaborazione: il loro risultato non sarà incluso.")
        lines.append("")
    lines.append("Se esci ora andranno persi.")
    return "\n".join(lines)


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
    ):
        super().__init__(parent)

        self.config = config
        self._show_debug = show_debug
        self.extraction_client = extraction_client or LocalExtractionClient(parent=self)

        self.setWindowTitle("BPER Edge Agent")
        self.resize(1180, 760)
        self._init_ui()

        # Barra del titolo (ed eventuale Mica) coerenti col tema, anche se Windows cambia.
        self._effects_applied = False
        QtWidgets.QApplication.instance().styleHints().colorSchemeChanged.connect(
            lambda _scheme: self._apply_window_effects()
        )

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

        # Cattura = 0, Dati estratti = 1, Debug LLM = 2 (solo con --debug).
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

    def showEvent(self, event) -> None:  # type: ignore[override]
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
        practices = 0
        if job_id:
            records = consolidate(self.extraction_client.get_results(job_id))
            practices = sum(
                1 for record in records
                if any(not is_nullish(field["value"]) for field in record.fields.values())
            )
        self.header.set_counters(queued, done, practices)

    # ------------------------------------------------------------------ Chiusura finestra

    def _ask_leave_unexported(self, labels: List[str], pending: int) -> bool:
        """True se l'operatore sceglie di uscire senza esportare."""
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

    def closeEvent(self, event) -> None:  # type: ignore[override]
        # Prima di fermare la cattura: chi torna indietro non deve perdere nulla.
        unexported = self.extraction_client.unexported_jobs()
        if unexported:
            labels = [self.extraction_client.session_label(job_id) for job_id in unexported]
            pending = self.extraction_client.pending_extractions()
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
