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
import theme
from workers.capture import (
    BaseCaptureWorker,
    DefaultCaptureWorker,
    BPERCaptureWorker,
)

from . import icons
from .overlay import CaptureBorderOverlay
from .widgets import Card, CollapsiblePanel, default_export_name


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
    counters_changed = QtCore.pyqtSignal(int, int)   # (frame inviati, risultati elaborati)

    def __init__(
            self,
            config: AgentConfig,
            api_client: Any,
            parent: Optional[QtWidgets.QWidget] = None,
            debug_tab: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.config = config
        self.api_client = api_client

        self.worker: Optional[BaseCaptureWorker] = None
        self.job_id: Optional[str] = None
        self._overlay: Optional[CaptureBorderOverlay] = None
        self._debug_tab: Optional[QtWidgets.QWidget] = debug_tab
        self._n_results: int = 0
        self._n_queued: int = 0
        self._error_count: int = 0

        self._init_ui()
        # Le impostazioni valgono all'avvio: mentre si cattura non si toccano.
        self.running_changed.connect(lambda running: self.settings_card.setEnabled(not running))

        # Connessioni uniche al client (vive quanto la finestra): i contatori
        # filtrano per job_id, quindi nessun connect/disconnect per sessione.
        try:
            self.api_client.result_ready.connect(self._on_result_ready_count)
            self.api_client.frame_queued.connect(self._on_frame_queued)
        except Exception:
            pass

    # ------------------------------------------------------------------ UI setup

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)
        tokens = theme.current_tokens()

        # --- Card impostazioni (si blocca mentre si cattura) ---
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

        # FPS: niente pulsanti su/giù (poco leggibili); si digita o si usano le frecce
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

        for row, (text, field) in enumerate((
            ("Modalità", self.mode_combo),
            ("Velocità di acquisizione", self.fps_spin),
            ("Titolo della finestra", self.window_filter_edit),
        )):
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
        self.force_capture_button.setIcon(icons.icon("camera", tokens.text, 18))
        self.force_capture_button.setToolTip("Acquisisci subito la pagina scelta (solo in modalità BPER)")
        self.force_capture_button.setEnabled(False)

        self.export_button = QPushButton("Esporta Excel", self)
        self.export_button.setIcon(icons.icon("download", tokens.text, 18))
        self.export_button.setShortcut(QtGui.QKeySequence("Ctrl+E"))
        self.export_button.setToolTip("Esporta in Excel le pratiche della sessione (Ctrl+E)")

        # actions.addWidget(self.requeue_button)
        actions.addWidget(manual_label)
        actions.addWidget(self.force_page_combo)
        actions.addWidget(self.force_capture_button)
        actions.addStretch(1)
        actions.addWidget(self.export_button)
        layout.addLayout(actions)

        # --- Registro: chiuso, con l'ultima riga e il numero di errori in vista ---
        self.log_text = QTextEdit(self)
        self.log_text.setReadOnly(True)
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
            self._error_count += 1
        self.log_panel.set_summary(self._summary_line(message if summary is None else summary))

    def _summary_line(self, text: str) -> str:
        line = text if len(text) <= 90 else text[:87] + "…"
        if self._error_count:
            word = "errore" if self._error_count == 1 else "errori"
            line += f"  ·  {self._error_count} {word}"
        return line

    def log_error_count(self) -> int:
        return self._error_count

    def _create_job_id(self) -> Optional[str]:
        """Avvia un nuovo job locale e ritorna il job_id."""
        job_id = self.api_client.start_job()
        if not job_id:
            self._log("[ERROR] Impossibile creare un nuovo job.")
            return None
        self._log(f"Nuovo job avviato: {job_id}")
        return job_id

    def _make_job_id_getter(self) -> Callable[[], Optional[str]]:
        return lambda: self.job_id

    # ------------------------------------------------------------------ Gestione worker

    def start_capture(self) -> None:
        if self.worker is not None:
            QMessageBox.warning(self, "Avviso", "Cattura già in corso.")
            return

        # Creazione job lato backend
        job_id = self._create_job_id()
        if not job_id:
            QMessageBox.critical(
                self,
                "Avvio non riuscito",
                "Non riesco ad avviare la sessione. Chiudi e riapri l'app; "
                "se succede ancora, contatta l'assistenza.",
            )
            return

        self.job_id = job_id
        self._n_results = 0
        self._n_queued = 0
        self.counters_changed.emit(0, 0)

        # Aggiorna la config dai controlli UI
        self.config.update_from_ui(
            fps=self.fps_spin.value(),
            window_filter=self.window_filter_edit.text(),
        )

        # Instanzia il worker in base alla modalità scelta
        mode = self.mode_combo.currentData()
        job_id_getter = self._make_job_id_getter()

        if mode == "bper":
            worker: BaseCaptureWorker = BPERCaptureWorker(
                config=self.config,
                job_id_getter=job_id_getter,
                api_client=self.api_client,
                parent=self,
            )
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

    def _on_stop_capture(self) -> None:
        if self.worker is None:
            return

        self._log("Richiesta arresto cattura...")
        try:
            self.worker.stop()
            if not self.worker.wait(5000):
                # Il loop di cattura non esegue più lavoro lungo: se accade,
                # è un bug da indagare, non da mascherare con terminate().
                self._log("[WARN] Worker di cattura ancora attivo dopo 5s.")
        except Exception as exc:  # noqa: BLE001
            self._log(f"[ERROR] Errore in stop_capture: {exc}")
        finally:
            self.worker = None
            in_flight = self._n_queued - self._n_results
            if in_flight > 0:
                self._log(f"Cattura arrestata. Estrazioni ancora in corso: {in_flight} (proseguono in background).")
            else:
                self._log("Cattura arrestata.")
            self.running_changed.emit(False)
            self.force_page_combo.setEnabled(False)
            self.force_capture_button.setEnabled(False)
            # Nasconde overlay se presente
            try:
                if self._overlay is not None:
                    self._overlay.hide()
                    self._overlay.deleteLater()
            finally:
                self._overlay = None

    def _on_worker_tick(self, message: str) -> None:
        self._log(message)

    def _on_worker_error(self, exc: Exception) -> None:
        # Riga tecnica nel registro; chi lo tiene chiuso legge una frase chiara.
        self._log(
            f"[WORKER ERROR] {type(exc).__name__}: {exc}",
            summary="Cattura interrotta da un errore. Apri il registro per i dettagli.",
        )

    # ------------------------------------------------------------------ Azioni backend

    def _on_export_excel(self) -> None:
        results = self.api_client.get_results(self.job_id) if self.job_id else []
        if not results:
            QMessageBox.warning(
                self,
                "Niente da esportare",
                "Non c'è ancora niente da esportare. Avvia la cattura e attendi almeno un'estrazione.",
            )
            return

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Salva Excel",
            default_export_name(),
            "File Excel (*.xlsx)",
        )
        if not file_path:
            return

        try:
            # Unico percorso di export: correzioni ed etichette incluse.
            written = self.api_client.export_workbook(self.job_id, file_path)
        except Exception as e:  # noqa: BLE001
            self._log(f"[ERROR] Export Excel fallita: {e}")
            QMessageBox.critical(
                self,
                "Salvataggio non riuscito",
                f"Non riesco a salvare il file:\n{e}",
            )
            return

        self._log(f"Export Excel salvata in: {file_path} ({written} pratiche)")
        QMessageBox.information(
            self,
            "Esportazione completata",
            f"{written} pratiche salvate in:\n{file_path}",
        )

    def _on_frame_queued(self, job_id: str, _page_type: str) -> None:
        if job_id == self.job_id:
            self._n_queued += 1
            self.counters_changed.emit(self._n_queued, self._n_results)

    def _on_result_ready_count(self, job_id: str, result: dict) -> None:
        if job_id == self.job_id:
            self._n_results += 1
            self.counters_changed.emit(self._n_queued, self._n_results)
            page = str(result.get("_page_type") or result.get("screen_id") or "?")
            status = str(result.get("_status") or "OK")
            self._log(f"Elaborazione terminata: «{page}» (stato: {status})")

    # ------------------------------------------------------------------ API pubblica

    def get_current_job_id(self) -> Optional[str]:
        return self.job_id

    def is_running(self) -> bool:
        return self.worker is not None

    def stop_capture(self) -> None:
        self._on_stop_capture()

    # ------------------------------------------------------------------ Forza scatto handler
    def _on_force_capture(self) -> None:
        if not self.worker:
            QMessageBox.warning(self, "Nessun worker", "Avvia prima la cattura.")
            return
        page = self.force_page_combo.currentText().strip()
        if not page:
            QMessageBox.warning(self, "Selezione mancante", "Seleziona una pagina da forzare.")
            return
        try:
            # Queue the request; the BPER capture thread owns the camera.
            if isinstance(self.worker, BPERCaptureWorker) and hasattr(self.worker, "force_capture"):
                # type: ignore[attr-defined]
                self.worker.force_capture(page)
                self._log(f"[UI] Forza scatto richiesto per pagina: {page}")
            else:
                QMessageBox.warning(self, "Modalità non supportata", "La forzatura è disponibile solo in modalità BPER.")
        except Exception as exc:  # noqa: BLE001
            self._log(f"[ERROR] Forza scatto fallita: {exc}")
