"""Tab per la cattura degli screenshot."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

from PyQt6 import QtCore, QtGui
from PyQt6 import QtWidgets
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QSpinBox,
    QComboBox,
    QMessageBox,
    QAbstractSpinBox,
)
from config import AgentConfig
from workers.capture import (
    BaseCaptureWorker,
    DefaultCaptureWorker,
    BPERCaptureWorker,
)

from . import icons
from .navigation_card import NavigationCard
from .overlay import CaptureBorderOverlay
from .widgets import Card, CollapsiblePanel
from .workbook_export import WorkbookExport


class CaptureTab(QWidget):
    """
    Tab di controllo per la cattura degli screenshot.

    - selezione modalità (BPER vs generico)
    - configurazione FPS e filtro finestra
    - avvio/arresto worker di cattura
    - export CSV
    - forza scatto manuale (solo BPER)
    - log testuale in tempo reale

    Avvia/Ferma vive nella barra di stato della finestra: la tab possiede il
    worker ed espone start_capture()/stop_capture()/is_running() più i segnali.
    """

    running_changed = QtCore.pyqtSignal(bool)        # cattura avviata / fermata
    stopping = QtCore.pyqtSignal()
    counters_changed = QtCore.pyqtSignal(int, int)   # (frame inviati, risultati elaborati)
    resume_selected = QtCore.pyqtSignal(bool)

    def __init__(
            self,
            config: AgentConfig,
            api_client: Any,
            parent: Optional[QtWidgets.QWidget] = None,
            debug_tab: Optional[QtWidgets.QWidget] = None,
            workbook_export: Optional[WorkbookExport] = None,
    ) -> None:
        super().__init__(parent)

        self.config = config
        self.api_client = api_client
        self._export = workbook_export or WorkbookExport(api_client, self)

        self.worker: Optional[BaseCaptureWorker] = None
        self._stopping = False
        self.job_id: Optional[str] = None
        self._overlay: Optional[CaptureBorderOverlay] = None
        self._debug_tab: Optional[QtWidgets.QWidget] = debug_tab
        self._n_results: int = 0
        self._n_queued: int = 0
        self._error_messages: set[str] = set()  # distinct errors since the capture started
        self._manual_page: str = ""
        self._manual_timer = QtCore.QTimer(self)
        self._manual_timer.setSingleShot(True)
        self._manual_timer.timeout.connect(self._submit_manual_capture)

        self._init_ui()
        self._export.bind_button(self.export_button)
        if getattr(self.api_client, "has_recovery", False):
            for job_id in self.api_client.recovered_jobs:
                self.session_combo.addItem(self.api_client.session_label(job_id), job_id)
            self.session_combo.setCurrentIndex(self.session_combo.count() - 1)
        # Settings are read when a capture starts: they are locked while it runs.
        self.running_changed.connect(lambda running: self.settings_card.setEnabled(not running))
        self.running_changed.connect(self.navigation_card.set_live)

        # Connessioni uniche al client (vive quanto la finestra): i contatori
        # filtrano per job_id, quindi nessun connect/disconnect per sessione.
        if hasattr(self.api_client, "frame_finished"):
            self.api_client.frame_finished.connect(self._on_result_ready_count)
        if hasattr(self.api_client, "frame_queued"):
            self.api_client.frame_queued.connect(self._on_frame_queued)

    # ------------------------------------------------------------------ UI setup

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        # --- Settings card (locked while capturing) ---
        self.settings_card = Card("Impostazioni", self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)

        # Modalità (BPER / default)
        self.mode_combo = QComboBox(self.settings_card)
        self.mode_combo.addItem("BPER", userData="bper")
        self.mode_combo.addItem("Generico", userData="default")
        self.mode_combo.setCurrentIndex(0)

        # FPS: no up/down buttons (hard to read); type the number or use the arrow keys
        self.fps_spin = QSpinBox(self.settings_card)
        self.fps_spin.setRange(1, 10)
        self.fps_spin.setValue(self.config.fps)
        self.fps_spin.setSuffix(" fps")
        self.fps_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.fps_spin.setToolTip("Fotogrammi al secondo da acquisire (1-10). Digita il numero o usa le frecce su/giù.")

        # Filtro finestra (titolo contiene)
        self.window_filter_edit = QLineEdit(self.settings_card)
        self.window_filter_edit.setText(self.config.window_title_contains)
        self.window_filter_edit.setPlaceholderText("Parte del titolo della finestra")

        settings = [
            ("Modalità", self.mode_combo),
            ("Velocità di acquisizione", self.fps_spin),
            ("Titolo della finestra", self.window_filter_edit),
        ]
        self.session_combo = QComboBox(self.settings_card)
        self.session_combo.addItem("Nuova sessione", None)
        self.session_combo.currentIndexChanged.connect(self._select_capture_session)
        if getattr(self.api_client, "has_recovery", False):
            settings.insert(0, ("Sessione di cattura", self.session_combo))
        else:
            self.session_combo.hide()
        for row, (text, field) in enumerate(settings):
            label = QLabel(text, self.settings_card)
            label.setBuddy(field)
            grid.addWidget(label, row, 0)
            grid.addWidget(field, row, 1)
        self.settings_card.content.addLayout(grid)
        layout.addWidget(self.settings_card)

        # --- Azioni: acquisizione manuale a sinistra, export a destra ---
        actions = QHBoxLayout()
        actions.setSpacing(10)

        # self.requeue_button = QPushButton("Requeue job", self) # Inutile in locale
        manual_label = QLabel("Acquisizione manuale", self)
        manual_label.setProperty("muted", True)
        self.force_page_combo = QComboBox(self)
        self.force_page_combo.setEditable(False)
        self.force_page_combo.setEnabled(False)
        self.force_page_combo.setMinimumWidth(220)
        self.force_page_combo.setToolTip("Pagina da acquisire subito")
        self.force_capture_button = QPushButton("Acquisisci ora", self)
        icons.bind_icon(self.force_capture_button, "camera", "text", 18)
        self.force_capture_button.setToolTip("Se l’agent copre il monitor di cattura, si riduce a icona e lascia tre secondi per mostrare la pagina BPER.")
        self.force_capture_button.setEnabled(False)

        self.export_button = QPushButton("Esporta Excel", self)
        icons.bind_icon(self.export_button, "download", "text", 18)
        self.export_button.setShortcut(QtGui.QKeySequence("Ctrl+E"))
        self.export_button.setToolTip("Esporta in Excel le pratiche della sessione (Ctrl+E)")

        # actions.addWidget(self.requeue_button)
        actions.addWidget(manual_label)
        actions.addWidget(self.force_page_combo)
        actions.addWidget(self.force_capture_button)
        actions.addStretch(1)
        actions.addWidget(self.export_button)
        layout.addLayout(actions)

        self.navigation_card = NavigationCard(self)
        self.navigation_card.hide()
        self.navigation_card.availability_requested.connect(self._set_view_available)
        self.navigation_card.reopen_requested.connect(self._reopen_view)
        layout.addWidget(self.navigation_card)

        # --- Log: closed, showing its last line and the error count ---
        self.log_text = QTextEdit(self)
        self.log_text.setReadOnly(True)
        self.log_text.document().setMaximumBlockCount(1000)
        self.log_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.log_text.setFont(QtGui.QFont("Consolas", 9))
        self.log_panel = CollapsiblePanel("Registro attività", self.log_text, self)
        layout.addWidget(self.log_panel, stretch=1)
        layout.addStretch(0)

        # Collegamenti segnali UI
        # self.requeue_button.clicked.connect(self._on_requeue_job)
        self.export_button.clicked.connect(self._on_export_excel)
        self.force_capture_button.clicked.connect(self._on_force_capture)

    # ------------------------------------------------------------------ Helpers

    @staticmethod
    def _load_bper_page_names(router_mode: str) -> list:
        """Nomi pagina acquisibili dal registro (per il combo 'Acquisisci ora')."""
        try:
            import app_paths
            from page_registry import PageRegistry
            registry = PageRegistry.load(app_paths.templates_dir() / "prompts.json")
            return registry.names(router_mode)
        except Exception:
            return []

    def _log(self, message: str, summary: Optional[str] = None) -> None:
        """Append a technical line to the log; `summary` is what the closed panel shows."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {message}")
        self.log_text.ensureCursorVisible()
        if "[ERROR]" in message or message.startswith("[WORKER ERROR]"):
            # Distinct messages: a failing backend repeats itself every loop.
            self._error_messages.add(message)
        self.log_panel.set_summary(self._summary_line(message if summary is None else summary))

    def _summary_line(self, text: str) -> str:
        line = text if len(text) <= 90 else text[:87] + "…"
        if self._error_messages:
            word = "errore" if len(self._error_messages) == 1 else "errori"
            line += f"  ·  {len(self._error_messages)} {word}"
        return line

    def log_error_count(self) -> int:
        return len(self._error_messages)

    def log_warning(self, message: str) -> None:
        self._log(f"[AVVISO] {message}")

    def _create_job_id(self) -> Optional[str]:
        """Avvia un nuovo job locale e ritorna il job_id."""
        job_id = self.api_client.start_job()
        if not job_id:
            self._log("[ERROR] Impossibile creare un nuovo job.")
            return None
        self._log(f"Nuovo job avviato: {job_id}")
        return job_id

    def _select_capture_session(self, _index: int) -> None:
        self.job_id = self.session_combo.currentData()
        self.navigation_card.hide()
        self.resume_selected.emit(self.job_id is not None)
        self.refresh_counters()

    def refresh_counters(self) -> None:
        # Worker signals can predate the window or arrive after a newer snapshot.
        self._n_queued, self._n_results = (
            self.api_client.capture_counts(self.job_id) if self.job_id else (0, 0)
        )
        self.counters_changed.emit(self._n_queued, self._n_results)

    @QtCore.pyqtSlot(str, dict)
    def _on_navigation(self, job_id: str, progress: dict[str, Any]) -> None:
        if self.sender() is self.worker and job_id == self.job_id:
            self.navigation_card.show_progress(progress)

    def _set_view_available(self, ndg: str, name: str, available: bool) -> None:
        if isinstance(self.worker, BPERCaptureWorker):
            self.worker.set_page_available(ndg, name, available)

    def _reopen_view(self, ndg: str, name: str) -> None:
        if isinstance(self.worker, BPERCaptureWorker):
            self.worker.reopen_page(ndg, name)

    def _make_job_id_getter(self) -> Callable[[], Optional[str]]:
        return lambda: self.job_id

    # ------------------------------------------------------------------ Gestione worker

    def start_capture(self) -> None:
        if self.worker is not None:
            QMessageBox.warning(self, "Avviso", "Cattura già in corso.")
            return

        job_id = self.session_combo.currentData() or self._create_job_id()
        if not job_id:
            QMessageBox.critical(
                self,
                "Avvio non riuscito",
                "Non riesco ad avviare la sessione. Chiudi e riapri l'app; "
                "se succede ancora, contatta l'assistenza.",
            )
            return

        self.job_id = job_id
        self._error_messages.clear()
        if self.session_combo.currentData():
            self._log(f"Ripresa della sessione: {self.api_client.session_label(job_id)}")
            self.refresh_counters()
        else:
            self._n_queued = self._n_results = 0
            self.counters_changed.emit(0, 0)

        # Aggiorna la config dai controlli UI
        self.config.update_from_ui(
            fps=self.fps_spin.value(),
            window_filter=self.window_filter_edit.text(),
        )

        # Instanzia il worker in base alla modalità scelta
        mode = self.mode_combo.currentData()
        self.navigation_card.show_progress({})
        self.navigation_card.setVisible(mode == "bper")
        job_id_getter = self._make_job_id_getter()

        if mode == "bper":
            worker: BaseCaptureWorker = BPERCaptureWorker(
                config=self.config,
                job_id_getter=job_id_getter,
                api_client=self.api_client,
                parent=self,
            )
            worker.navigation_changed.connect(self._on_navigation)
            self._log("Avvio cattura in modalità BPER.")
            # Popola combo pagine dal registro (prompts.json, source of truth)
            pages = self._load_bper_page_names(self.config.router_mode)
            self.force_page_combo.clear()
            for name in pages:
                self.force_page_combo.addItem(name)
            can_force = len(pages) > 0 and hasattr(worker, "force_capture")
            self.force_page_combo.setEnabled(can_force)
            self.force_capture_button.setEnabled(can_force)
        else:
            worker = DefaultCaptureWorker(
                config=self.config,
                job_id_getter=job_id_getter,
                parent=self,
            )
            self._log("Avvio cattura in modalità generica.")
            self.force_page_combo.setEnabled(False)
            self.force_capture_button.setEnabled(False)

        # Collega segnali del worker
        worker.tick.connect(self._on_worker_tick)
        worker.error.connect(self._on_worker_error)
        worker.finished.connect(self._on_worker_finished)
        # Debug LLM: collega se tab presente
        try:
            if self._debug_tab is not None:
                if hasattr(self._debug_tab, "append_json"):
                    worker.llm_debug.connect(self._debug_tab.append_json)
                if hasattr(self._debug_tab, "append_log"):
                    worker.tick.connect(self._debug_tab.append_log)
        except Exception:
            pass

        self.worker = worker
        self.worker.start_capture()

        # Mostra overlay bordo rosso sul monitor selezionato (se abilitato)
        try:
            if self.config.show_capture_border:
                screens = QtGui.QGuiApplication.screens()
                idx = max(1, int(self.config.monitor_index)) - 1
                if 0 <= idx < len(screens):
                    geo = screens[idx].geometry()
                    self._overlay = CaptureBorderOverlay(geo)
                    self._overlay.show()
                else:
                    # fallback primo schermo
                    if screens:
                        geo = screens[0].geometry()
                        self._overlay = CaptureBorderOverlay(geo)
                        self._overlay.show()
        except Exception:
            # l'overlay non è critico; ignora errori
            self._overlay = None

        self.running_changed.emit(True)
        # Aggiorna stato bottoni forza scatto (se non settato sopra)
        if isinstance(self.worker, BPERCaptureWorker):
            has_pages = self.force_page_combo.count() > 0
            self.force_page_combo.setEnabled(has_pages)
            self.force_capture_button.setEnabled(has_pages)

    def stop_capture(self) -> None:
        if self.worker is None or self._stopping:
            return

        self._stopping = True
        self._manual_timer.stop()
        self._log("Richiesta arresto cattura...")
        self.navigation_card.set_live(False)
        self.force_page_combo.setEnabled(False)
        self.force_capture_button.setEnabled(False)
        self.stopping.emit()
        self.worker.stop()

    @QtCore.pyqtSlot()
    def _on_worker_finished(self) -> None:
        worker = self.worker
        if worker is None or worker is not self.sender():
            return
        self.worker = None
        self._manual_timer.stop()
        self.navigation_card.finish_capture()
        worker.deleteLater()
        self._stopping = False
        self.force_page_combo.setEnabled(False)
        self.force_capture_button.setEnabled(False)
        if self._overlay is not None:
            self._overlay.hide()
            self._overlay.deleteLater()
            self._overlay = None
        in_flight = self._n_queued - self._n_results
        if in_flight > 0:
            self._log(f"Cattura arrestata. Estrazioni ancora in corso: {in_flight} (proseguono in background).")
        else:
            self._log("Cattura arrestata.")
        self.running_changed.emit(False)

    def _on_worker_tick(self, message: str) -> None:
        self._log(message)

    def _on_worker_error(self, exc: Exception) -> None:
        # Technical line in the log; whoever keeps it closed reads a plain sentence.
        self._log(
            f"[WORKER ERROR] {type(exc).__name__}: {exc}",
            # The capture goes on: the worker reports the error every loop and retries.
            summary="Errore durante la cattura. Apri il registro per i dettagli.",
        )

    # ------------------------------------------------------------------ Azioni backend

    def _on_export_excel(self) -> None:
        self._export.start(self, self.job_id, self._log)

    def _on_frame_queued(self, job_id: str, _page_type: str) -> None:
        if job_id == self.job_id:
            if getattr(self.api_client, "has_recovery", False) and self.session_combo.findData(job_id) < 0:
                with QtCore.QSignalBlocker(self.session_combo):
                    self.session_combo.addItem(self.api_client.session_label(job_id), job_id)
                    self.session_combo.setCurrentIndex(self.session_combo.findData(job_id))
                self.resume_selected.emit(True)
            self.refresh_counters()

    def _on_result_ready_count(self, job_id: str, page: str, status: str) -> None:
        if job_id == self.job_id:
            self.refresh_counters()
            self._log(f"Elaborazione terminata: «{page}» (stato: {status})")

    # ------------------------------------------------------------------ API pubblica

    def get_current_job_id(self) -> Optional[str]:
        return self.job_id

    def is_running(self) -> bool:
        return self.worker is not None

    # ------------------------------------------------------------------ Forza scatto handler
    def _on_force_capture(self) -> None:
        if self._stopping or self._manual_timer.isActive():
            return
        if not self.worker:
            QMessageBox.warning(self, "Nessun worker", "Avvia prima la cattura.")
            return
        page = self.force_page_combo.currentText().strip()
        if not page:
            QMessageBox.warning(self, "Selezione mancante", "Seleziona una pagina da forzare.")
            return
        if not isinstance(self.worker, BPERCaptureWorker):
            QMessageBox.warning(self, "Modalità non supportata", "La forzatura è disponibile solo in modalità BPER.")
            return
        self._manual_page = page
        if self._covers_capture_monitor():
            self._log("Scatto manuale tra tre secondi. Porta in primo piano la pagina BPER.")
            self.window().showMinimized()
            self._manual_timer.start(3000)
        else:
            self._submit_manual_capture()

    def _covers_capture_monitor(self) -> bool:
        window = self.window()
        screens = QtGui.QGuiApplication.screens()
        index = int(self.config.monitor_index or 1) - 1
        target = screens[index] if 0 <= index < len(screens) else QtGui.QGuiApplication.primaryScreen()
        return bool(window.isVisible() and not window.isMinimized() and target
                    and target.geometry().intersects(window.frameGeometry()))

    def _submit_manual_capture(self) -> None:
        if self._stopping or not isinstance(self.worker, BPERCaptureWorker):
            return
        if self._covers_capture_monitor():
            self._log("Scatto manuale annullato. L’edge-agent copre il monitor da acquisire.")
            return
        # Only the capture thread touches the camera.
        self.worker.force_capture(self._manual_page)
        self._log(f"[UI] Forza scatto richiesto per pagina: {self._manual_page}")
