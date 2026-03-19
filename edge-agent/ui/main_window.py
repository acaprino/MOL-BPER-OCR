"""Finestra principale dell'applicazione Edge Agent."""

from __future__ import annotations

from typing import Optional

from PyQt6 import QtWidgets
from config import AgentConfig
from local_extraction_client import LocalExtractionClient

from .capture_tab import CaptureTab
from .debug_tab import DebugTab
from .extraction_results_tab import ExtractionResultsTab


class MainWindow(QtWidgets.QMainWindow):
    """
    Finestra principale dell'app Edge Agent.

    Contiene:
        - una tab "Cattura" per gestire job e worker di screenshot;
        - una tab "Risultati" per consultare i risultati dell'estrazione locale.

    Condivide:
        - AgentConfig
        - LocalExtractionClient

    e sincronizza automaticamente il job_id tra le due tab.
    """

    def __init__(self, config: AgentConfig, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)

        self.config = config
        self.extraction_client = LocalExtractionClient(parent=self)

        self.setWindowTitle("Edge Agent – Cattura & IE")
        self._init_ui()

    # ------------------------------------------------------------------ UI setup

    def _init_ui(self) -> None:
        self.tabs = QtWidgets.QTabWidget(self)
        self.setCentralWidget(self.tabs)

        # Tab opzionale di debug LLM
        self.debug_tab = None
        if getattr(self.config, "show_llm_debug_tab", False):
            self.debug_tab = DebugTab(parent=self)

        # Tab di cattura
        self.capture_tab = CaptureTab(
            config=self.config,
            api_client=self.extraction_client,
            parent=self,
            debug_tab=self.debug_tab,
        )

        # Tab di risultati locali
        self.results_tab = ExtractionResultsTab(
            extraction_client=self.extraction_client,
            parent=self,
        )

        self.tabs.addTab(self.capture_tab, "Cattura")
        self.tabs.addTab(self.results_tab, "Risultati")
        if self.debug_tab is not None:
            self.tabs.addTab(self.debug_tab, "Debug LLM")

        self.tabs.currentChanged.connect(self._on_tab_changed)

    # ------------------------------------------------------------------ Eventi

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            job_id = None
            if hasattr(self.capture_tab, "get_current_job_id"):
                job_id = self.capture_tab.get_current_job_id()
            if job_id and hasattr(self.results_tab, "set_job_id"):
                self.results_tab.set_job_id(job_id)

    # ------------------------------------------------------------------ Chiusura finestra

    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            if hasattr(self.capture_tab, "stop_capture"):
                self.capture_tab.stop_capture()
        except Exception:
            pass
        super().closeEvent(event)
