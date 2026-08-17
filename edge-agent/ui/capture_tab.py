"""Tab per la cattura degli screenshot."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

from PyQt6 import QtGui
from PyQt6 import QtWidgets
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QSpinBox,
    QComboBox,
    QMessageBox,
)
from config import AgentConfig
from workers.capture import (
    BaseCaptureWorker,
    DefaultCaptureWorker,
    BPERCaptureWorker,
)

from .overlay import CaptureBorderOverlay

# Pagine catch-all da escludere dal combo "Acquisisci ora"
_SKIP_PAGE_TYPES_UI: frozenset = frozenset({"Altro / Non riconosciuto"})


class CaptureTab(QWidget):
    """
    Tab di controllo per la cattura degli screenshot.

    - selezione modalità (BPER vs generico)
    - configurazione FPS e filtro finestra
    - avvio/arresto worker di cattura
    - export CSV
    - forza scatto manuale (solo BPER)
    - log testuale in tempo reale
    """

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

        self._init_ui()

    # ------------------------------------------------------------------ UI setup

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- Box configurazione ---
        config_group = QGroupBox("Impostazioni", self)
        config_layout = QGridLayout(config_group)

        # Modalità (BPER / default)
        mode_label = QLabel("Modalità:", config_group)
        self.mode_combo = QComboBox(config_group)
        self.mode_combo.addItem("BPER", userData="bper")
        self.mode_combo.addItem("Generico", userData="default")
        self.mode_combo.setCurrentIndex(0)

        # FPS
        fps_label = QLabel("Velocità acquisizione (fps):", config_group)
        self.fps_spin = QSpinBox(config_group)
        self.fps_spin.setRange(1, 10)
        self.fps_spin.setValue(self.config.fps)

        # Filtro finestra (titolo contiene)
        win_label = QLabel("Titolo finestra da monitorare:", config_group)
        self.window_filter_edit = QLineEdit(config_group)
        self.window_filter_edit.setText(self.config.window_title_contains)

        config_layout.addWidget(mode_label, 0, 0)
        config_layout.addWidget(self.mode_combo, 0, 1)

        config_layout.addWidget(fps_label, 1, 0)
        config_layout.addWidget(self.fps_spin, 1, 1)

        config_layout.addWidget(win_label, 2, 0)
        config_layout.addWidget(self.window_filter_edit, 2, 1)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # Box job (sostituiti pulsanti inutili per locale)
        controls_layout = QHBoxLayout()

        self.start_button = QPushButton("▶  Avvia", self)
        self.stop_button = QPushButton("■  Ferma", self)
        # self.requeue_button = QPushButton("Requeue job", self) # Inutile in locale
        self.export_button = QPushButton("⬇️  Esporta CSV", self)

        # Forza scatto: selezione pagina + bottone
        self.force_page_combo = QComboBox(self)
        self.force_page_combo.setEditable(False)
        self.force_page_combo.setEnabled(False)
        self.force_capture_button = QPushButton("📷  Acquisisci ora", self)
        self.force_capture_button.setEnabled(False)

        self.job_label = QLabel("Sessione: –", self)

        controls_layout.addWidget(self.start_button)
        controls_layout.addWidget(self.stop_button)
        # controls_layout.addWidget(self.requeue_button)
        controls_layout.addWidget(self.export_button)
        controls_layout.addWidget(self.force_page_combo)
        controls_layout.addWidget(self.force_capture_button)
        controls_layout.addStretch(1)
        controls_layout.addWidget(self.job_label)

        layout.addLayout(controls_layout)

        # --- Box log ---
        layout.addWidget(QLabel("Registro attività:", self))
        self.log_text = QTextEdit(self)
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.log_text, stretch=1)

        # Collegamenti segnali UI
        self.start_button.clicked.connect(self._on_start_capture)
        self.stop_button.clicked.connect(self._on_stop_capture)
        # self.requeue_button.clicked.connect(self._on_requeue_job)
        self.export_button.clicked.connect(self._on_export_csv)
        self.force_capture_button.clicked.connect(self._on_force_capture)

        # Stato iniziale
        self.stop_button.setEnabled(False)

    # ------------------------------------------------------------------ Helpers

    @staticmethod
    def _load_bper_page_names() -> list:
        """Legge i nomi delle pagine BPER direttamente da prompts.json."""
        try:
            import json
            import app_paths
            prompts_path = app_paths.templates_dir() / "prompts.json"
            spec = json.loads(prompts_path.read_text(encoding="utf-8"))
            return [
                p["name"]
                for p in spec.get("pages", [])
                if isinstance(p.get("name"), str) and p["name"] not in _SKIP_PAGE_TYPES_UI
            ]
        except Exception:
            return []

    def _log(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {message}")
        self.log_text.ensureCursorVisible()

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

    def _on_start_capture(self) -> None:
        if self.worker is not None:
            QMessageBox.warning(self, "Avviso", "Cattura già in corso.")
            return

        # Creazione job lato backend
        job_id = self._create_job_id()
        if not job_id:
            QMessageBox.critical(
                self,
                "Errore creazione job",
                "Impossibile creare un nuovo job via API.\n"
                "Verifica che il servizio sia attivo.",
            )
            return

        self.job_id = job_id
        self._n_results = 0
        self.job_label.setText("Sessione attiva  |  Acquisite: 0")
        # Connetti result_ready per aggiornare il contatore
        try:
            self.api_client.result_ready.connect(self._on_result_ready_count)
        except Exception:
            pass

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
            # Popola combo pagine da prompts.json (source of truth),
            # con fallback a page_sequence del worker se prompts.json non è leggibile
            pages = self._load_bper_page_names()
            if not pages:
                pages = [
                    p for p in list(getattr(worker, "page_sequence", []) or [])
                    if p not in _SKIP_PAGE_TYPES_UI
                ]
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

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
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
                # Worker bloccato in una chiamata lunga (es. estrazione VLM):
                # senza terminate il processo sopravvive headless alla finestra.
                self._log("[WARN] Worker ancora attivo dopo 5s: chiusura forzata.")
                self.worker.terminate()
                self.worker.wait(2000)
        except Exception as exc:  # noqa: BLE001
            self._log(f"[ERROR] Errore in stop_capture: {exc}")
        finally:
            self.worker = None
            try:
                self.api_client.result_ready.disconnect(self._on_result_ready_count)
            except Exception:
                pass
            self._log("Cattura arrestata.")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
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
        self._log(f"[WORKER ERROR] {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------ Azioni backend

    def _on_export_csv(self) -> None:
        if not self.job_id:
            QMessageBox.warning(
                self,
                "Nessun job",
                "Non è presente alcun job corrente da esportare.",
            )
            return

        csv_text = self.api_client.export_csv(self.job_id)
        if csv_text is None:
            self._log(f"[ERROR] Export CSV fallita per job {self.job_id}.")
            return

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Salva CSV",
            f"export-{self.job_id}.csv",
            "File CSV (*.csv)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8", newline="") as f:
                f.write(csv_text)
            self._log(f"Export CSV salvata in: {file_path}")
            QMessageBox.information(
                self,
                "Export completata",
                f"Export CSV salvata in:\n{file_path}",
            )
        except OSError as e:
            self._log(f"[ERROR] Errore scrittura file CSV: {e}")
            QMessageBox.critical(
                self,
                "Errore scrittura",
                f"Errore durante la scrittura del file:\n{e}",
            )

    def _on_result_ready_count(self, job_id: str, _result: dict) -> None:
        if job_id == self.job_id:
            self._n_results += 1
            self.job_label.setText(f"Sessione attiva  |  Acquisite: {self._n_results}")

    # ------------------------------------------------------------------ API pubblica

    def get_current_job_id(self) -> Optional[str]:
        return self.job_id

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
            # Solo per BPER worker
            if isinstance(self.worker, BPERCaptureWorker) and hasattr(self.worker, "force_capture"):
                # type: ignore[attr-defined]
                self.worker.force_capture(page)
                self._log(f"[UI] Forza scatto richiesto per pagina: {page}")
            else:
                QMessageBox.warning(self, "Modalità non supportata", "La forzatura è disponibile solo in modalità BPER.")
        except Exception as exc:  # noqa: BLE001
            self._log(f"[ERROR] Forza scatto fallita: {exc}")
