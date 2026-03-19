"""Tab per visualizzare i risultati dell'estrazione IE."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTextEdit,
    QComboBox,
    QTabWidget,
    QMessageBox,
    QSplitter,
    QFileDialog,
)
from api_client import APIClient
from config import AgentConfig


class ResultsTab(QWidget):
    """
    Tab per esplorare i risultati IE:

        - selezione job
        - selezione documento
        - lista oggetti (albero)
        - dettaglio oggetto
        - links documento
        - manifest documento
    """

    def __init__(
            self,
            config: AgentConfig,
            api_client: APIClient,
            parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.config = config
        self.api_client = api_client

        self._current_job_id: Optional[str] = None
        self._current_doc_id: Optional[str] = None

        self._init_ui()
        self._load_jobs()

    # ------------------------------------------------------------------ UI

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- Riga superiore: job, doc, search, reload, export ---
        top_row = QGridLayout()

        job_label = QLabel("Job:", self)
        self.job_combo = QComboBox(self)
        self.job_combo.setEditable(False)
        self.job_combo.currentTextChanged.connect(self._on_job_changed)

        doc_label = QLabel("Documento:", self)
        self.doc_combo = QComboBox(self)
        self.doc_combo.setEditable(False)
        self.doc_combo.currentTextChanged.connect(self._on_doc_changed)

        search_label = QLabel("Filtro oggetti:", self)
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("es. type:subject, label:nome, ecc.")

        reload_btn = QPushButton("🔄 Ricarica", self)
        reload_btn.clicked.connect(self._on_reload_with_check)

        export_csv_btn = QPushButton("⬇️ Export CSV", self)
        export_csv_btn.clicked.connect(self._on_export_csv)

        export_xlsx_btn = QPushButton("⬇️ Export Excel", self)
        export_xlsx_btn.clicked.connect(self._on_export_xlsx)

        rerun_btn = QPushButton("🔁 Rerun Job", self)
        rerun_btn.setToolTip("Rielabora i TXT già presenti per questo job (salta la cattura)")
        rerun_btn.clicked.connect(self._on_rerun_job)

        process_btn = QPushButton("⚙️ Processa Job", self)
        process_btn.setToolTip("Assegna i numeri di pagina migliori basandosi sulla qualità dell'estrazione")
        process_btn.clicked.connect(self._on_process_job)

        top_row.addWidget(job_label, 0, 0)
        top_row.addWidget(self.job_combo, 0, 1)

        top_row.addWidget(doc_label, 0, 2)
        top_row.addWidget(self.doc_combo, 0, 3)

        top_row.addWidget(search_label, 1, 0)
        top_row.addWidget(self.search_edit, 1, 1)
        top_row.addWidget(reload_btn, 1, 2)
        top_row.addWidget(export_csv_btn, 1, 3)
        top_row.addWidget(export_xlsx_btn, 1, 4)
        top_row.addWidget(rerun_btn, 1, 5)
        top_row.addWidget(process_btn, 1, 6)

        layout.addLayout(top_row)

        # --- Splitter centrale: albero oggetti + pannello destro ---
        splitter = QSplitter(self)
        splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)

        # Albero oggetti
        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)

        self.objects_tree = QTreeWidget(left_widget)
        self.objects_tree.setHeaderLabels(["Type", "Label", "Preview"])
        self.objects_tree.setColumnWidth(0, 120)
        self.objects_tree.setColumnWidth(1, 160)
        self.objects_tree.setColumnWidth(2, 240)
        self.objects_tree.itemActivated.connect(self._on_object_activated)
        left_layout.addWidget(self.objects_tree)

        # Pulsanti sotto l'albero
        buttons_row = QHBoxLayout()

        detail_btn = QPushButton("Dettaglio oggetto", left_widget)
        detail_btn.clicked.connect(self._on_show_detail)
        buttons_row.addWidget(detail_btn)

        links_btn = QPushButton("Links documento", left_widget)
        links_btn.clicked.connect(self._on_show_links)
        buttons_row.addWidget(links_btn)

        manifest_btn = QPushButton("Manifest documento", left_widget)
        manifest_btn.clicked.connect(self._on_show_manifest)
        buttons_row.addWidget(manifest_btn)

        fixed_btn = QPushButton("Fixed Fields", left_widget)
        fixed_btn.clicked.connect(self._on_show_fixed_fields)
        buttons_row.addWidget(fixed_btn)

        buttons_row.addStretch(1)
        left_layout.addLayout(buttons_row)

        left_widget.setLayout(left_layout)
        splitter.addWidget(left_widget)

        # Pannello destro: tab Dettaglio / Links / Manifest
        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)

        self.detail_tabs = QTabWidget(right_widget)

        # Tab dettaglio oggetto
        self.detail_text = QTextEdit(self.detail_tabs)
        self.detail_text.setReadOnly(True)
        self.detail_tabs.addTab(self.detail_text, "Dettaglio")

        # Tab links documento
        self.links_text = QTextEdit(self.detail_tabs)
        self.links_text.setReadOnly(True)
        self.detail_tabs.addTab(self.links_text, "Links")

        # Tab manifest documento
        self.manifest_text = QTextEdit(self.detail_tabs)
        self.manifest_text.setReadOnly(True)
        self.detail_tabs.addTab(self.manifest_text, "Manifest")

        # Tab BPER Fixed Fields
        self.fixed_tab = QWidget(self.detail_tabs)
        self.fixed_layout = QVBoxLayout(self.fixed_tab)
        self.fixed_header = QLabel("", self.fixed_tab)
        self.fixed_tree = QTreeWidget(self.fixed_tab)
        self.fixed_tree.setHeaderLabels(["Campo", "Valore"])
        self.fixed_tree.setColumnWidth(0, 260)
        self.fixed_layout.addWidget(self.fixed_header)
        self.fixed_layout.addWidget(self.fixed_tree)
        self.fixed_tab.setLayout(self.fixed_layout)
        self.detail_tabs.addTab(self.fixed_tab, "BPER Fixed Fields")

        right_layout.addWidget(self.detail_tabs)
        right_widget.setLayout(right_layout)

        splitter.addWidget(right_widget)

        # Imposta proporzioni iniziali del splitter
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

    # ------------------------------------------------------------------ Caricamento dati

    def _load_jobs(self) -> None:
        """Carica la lista dei job dal backend."""
        self.job_combo.blockSignals(True)
        self.job_combo.clear()

        jobs = self.api_client.get_jobs()
        for job in jobs:
            # Extract job_id if it's a dict, otherwise use the value directly
            job_id = job.get("job_id") if isinstance(job, dict) else job
            if job_id:
                self.job_combo.addItem(str(job_id))

        self.job_combo.blockSignals(False)

        # Normalize the jobs list for the selection logic below
        job_ids = [j.get("job_id") if isinstance(j, dict) else j for j in jobs]
        job_ids = [str(jid) for jid in job_ids if jid]

        if job_ids:
            # Se abbiamo già un job corrente preferito, selezionalo
            if self._current_job_id and self._current_job_id in job_ids:
                self.job_combo.setCurrentText(self._current_job_id)
            else:
                self.job_combo.setCurrentIndex(0)
                self._current_job_id = self.job_combo.currentText()
                self._load_documents(self._current_job_id)
        else:
            self._current_job_id = None
            self.doc_combo.clear()
            self.objects_tree.clear()
            self._clear_detail_panels()

    def _load_documents(self, job_id: str) -> None:
        """Carica la lista dei documenti per il job indicato."""
        self.doc_combo.blockSignals(True)
        self.doc_combo.clear()

        docs = self.api_client.get_job_documents(job_id)
        for doc_id in docs:
            self.doc_combo.addItem(doc_id)

        self.doc_combo.blockSignals(False)

        if docs:
            if self._current_doc_id and self._current_doc_id in docs:
                self.doc_combo.setCurrentText(self._current_doc_id)
            else:
                self.doc_combo.setCurrentIndex(0)
            self._current_doc_id = self.doc_combo.currentText()
            self._load_objects(job_id, self._current_doc_id)
        else:
            self._current_doc_id = None
            self.objects_tree.clear()
            self._clear_detail_panels()

    def _load_objects(self, job_id: str, doc_id: str) -> None:
        """Carica la lista di oggetti per job/documento (eventualmente filtrati)."""
        search_query = self.search_edit.text().strip() or None

        self.objects_tree.clear()
        objects = self.api_client.get_document_objects(job_id, doc_id, search_query)

        for obj in objects:
            item = self._create_object_item(obj)
            self.objects_tree.addTopLevelItem(item)

        self._clear_detail_panels()
        
    # ------------------------------------------------------------------ Export helpers

    def _on_export_csv(self) -> None:
        job_id = self._current_job_id or self.job_combo.currentText().strip()
        if not job_id:
            QMessageBox.warning(self, "Export CSV", "Seleziona un job prima di esportare.")
            return

        # Scegli dove salvare
        default_name = f"export_flat_{job_id}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Salva CSV", default_name, "CSV (*.csv)")
        if not path:
            return

        # Disabilita UI minima durante il lavoro
        self.setEnabled(False)
        try:
            csv_text = self.api_client.export_csv(job_id, schema="flat")
            if not isinstance(csv_text, str):
                QMessageBox.critical(self, "Export CSV", "Errore durante l'esportazione CSV.")
                return
            # Scrivi file
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(csv_text)
            QMessageBox.information(self, "Export CSV", f"CSV salvato in:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export CSV", f"Errore: {e}")
        finally:
            self.setEnabled(True)

    def _on_export_xlsx(self) -> None:
        job_id = self._current_job_id or self.job_combo.currentText().strip()
        if not job_id:
            QMessageBox.warning(self, "Export Excel", "Seleziona un job prima di esportare.")
            return

        default_name = f"export_flat_{job_id}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Salva Excel", default_name, "Excel (*.xlsx)"
        )
        if not path:
            return

        self.setEnabled(False)
        try:
            data = self.api_client.export_xlsx(job_id, schema="flat")
            if not isinstance(data, (bytes, bytearray)):
                QMessageBox.critical(self, "Export Excel", "Errore durante l'esportazione Excel.")
                return
            with open(path, "wb") as f:
                f.write(data)
            QMessageBox.information(self, "Export Excel", f"Excel salvato in:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Excel", f"Errore: {e}")
        finally:
            self.setEnabled(True)

    def _on_rerun_job(self) -> None:
        """Forza il rerun del worker IE per il job corrente, senza ricattura."""
        job_id = self._current_job_id or self.job_combo.currentText().strip()
        if not job_id:
            QMessageBox.warning(self, "Rerun IE", "Seleziona un job prima di procedere.")
            return

        # Conferma
        ret = QMessageBox.question(
            self,
            "Rerun IE",
            (
                "Vuoi rilanciare l'estrazione IE per il job selezionato?\n\n"
                "Questo comando forza il worker IE a rielaborare i TXT già presenti, "
                "senza effettuare nuova cattura."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        self.setEnabled(False)
        try:
            resp = self.api_client.rerun_ie(job_id, delete_outputs=False)
            if not resp:
                QMessageBox.critical(self, "Rerun IE", "Errore durante il rerun.")
                return
            cleared = resp.get("cleared") if isinstance(resp, dict) else None
            QMessageBox.information(
                self,
                "Rerun IE",
                f"Rerun avviato. TXT sbloccati: {cleared if cleared is not None else '?'}\n"
                "Il worker IE ripartirà automaticamente nei prossimi cicli."
            )
            # Ricarica lista oggetti dopo un breve delay (il worker potrebbe non aver finito)
            self._load_objects(job_id, self._current_doc_id or self.doc_combo.currentText())
        except Exception as e:
            QMessageBox.critical(self, "Rerun IE", f"Errore: {e}")
        finally:
            self.setEnabled(True)

    def _on_process_job(self) -> None:
        """Assegna i numeri di pagina migliori basandosi sulla qualità dell'estrazione."""
        job_id = self._current_job_id or self.job_combo.currentText().strip()
        if not job_id:
            QMessageBox.warning(self, "Processa Job", "Seleziona un job prima di procedere.")
            return

        self.setEnabled(False)
        try:
            resp = self.api_client.process_job(job_id)
            if not resp or (isinstance(resp, dict) and resp.get("status") != "ok"):
                msg = resp.get("message", "Errore sconosciuto") if isinstance(resp, dict) else "Nessuna risposta"
                QMessageBox.critical(self, "Processa Job", f"Errore durante il processamento:\n{msg}")
                return
            
            QMessageBox.information(
                self,
                "Processa Job",
                resp.get("message", "Processamento completato.")
            )
            # Ricarica per vedere i nuovi numeri di pagina
            self._load_objects(job_id, self._current_doc_id or self.doc_combo.currentText())
        except Exception as e:
            QMessageBox.critical(self, "Processa Job", f"Errore: {e}")
        finally:
            self.setEnabled(True)

    # ------------------------------------------------------------------ Helpers UI / dati

    def _create_object_item(self, obj: Dict[str, Any]) -> QTreeWidgetItem:
        """Crea un QTreeWidgetItem a partire da un dict oggetto."""
        # Estrazione campi principali in modo difensivo
        obj_type = (
                str(obj.get("type"))
                or str(obj.get("object_type"))
                or obj.get("kind")
                or ""
        )
        label = (
                str(obj.get("label"))
                or str(obj.get("field"))
                or obj.get("name")
                or ""
        )
        preview = self._build_preview(obj)

        item = QTreeWidgetItem([obj_type, label, preview])

        # Conserva il dict completo in data(UserRole)
        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, obj)
        return item

    @staticmethod
    def _build_preview(obj: Dict[str, Any], max_len: int = 80) -> str:
        """Costruisce una stringa di preview per la terza colonna."""
        for key in ("preview", "text", "value", "content"):
            if key in obj and isinstance(obj[key], str):
                s = obj[key].replace("\n", " ")
                return s[:max_len] + ("…" if len(s) > max_len else "")
        # Fallback: prime chiavi/valori rilevanti
        try:
            summary = {k: obj[k] for k in list(obj.keys())[:3]}
            s = json.dumps(summary, ensure_ascii=False)
            return s[:max_len] + ("…" if len(s) > max_len else "")
        except Exception:
            return ""

    def _clear_detail_panels(self) -> None:
        """Pulisce i pannelli di dettaglio (oggetto, links, manifest)."""
        self.detail_text.clear()
        self.links_text.clear()
        self.manifest_text.clear()
        if hasattr(self, "fixed_tree"):
            self.fixed_tree.clear()
        if hasattr(self, "fixed_header"):
            self.fixed_header.setText("")

    def _ensure_job_and_doc(self) -> bool:
        """Verifica che job_id e doc_id siano presenti, altrimenti mostra un warning."""
        job_id = self.job_combo.currentText().strip()
        doc_id = self.doc_combo.currentText().strip()

        if not job_id:
            QMessageBox.warning(self, "Nessun job", "Seleziona un job.")
            return False
        if not doc_id:
            QMessageBox.warning(self, "Nessun documento", "Seleziona un documento.")
            return False

        self._current_job_id = job_id
        self._current_doc_id = doc_id
        return True

    # ------------------------------------------------------------------ Eventi UI

    def _on_job_changed(self, job_id: str) -> None:
        """Handler per cambio job nella combo."""
        job_id = job_id.strip()
        self._current_job_id = job_id or None
        if job_id:
            self._load_documents(job_id)
        else:
            self.doc_combo.clear()
            self.objects_tree.clear()
            self._clear_detail_panels()

    def _on_doc_changed(self, doc_id: str) -> None:
        """Handler per cambio documento nella combo."""
        doc_id = doc_id.strip()
        self._current_doc_id = doc_id or None
        if doc_id and self._current_job_id:
            self._load_objects(self._current_job_id, doc_id)
        else:
            self.objects_tree.clear()
            self._clear_detail_panels()

    def _on_reload_with_check(self) -> None:
        """Handler per pulsante Ricarica: ricarica oggetti per job/doc correnti."""
        if not self._ensure_job_and_doc():
            return
        self._load_objects(self._current_job_id, self._current_doc_id)  # type: ignore[arg-type]

    def _on_object_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        """Doppio click su un oggetto nell'albero → mostra il dettaglio."""
        self._on_show_detail()

    def _get_selected_object(self) -> Optional[Dict[str, Any]]:
        """
        Recupera il dict oggetto relativo alla riga selezionata nell'albero.

        Returns:
            Dizionario oggetto oppure None se non c'è selezione.
        """
        items = self.objects_tree.selectedItems()
        if not items:
            return None

        item = items[0]
        obj = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(obj, dict):
            return obj
        return None

    # ------------------------------------------------------------------ Azioni: dettaglio / links / manifest

    def _on_show_detail(self) -> None:
        """Mostra il dettaglio JSON dell'oggetto selezionato."""
        obj = self._get_selected_object()
        if obj is None:
            QMessageBox.information(
                self,
                "Nessun oggetto",
                "Seleziona un oggetto dall'elenco.",
            )
            return

        # Se l'oggetto ha un ID, potremmo voler recuperare il dettaglio aggiornato
        # dal backend. In caso contrario, usiamo il dict presente.
        detail = obj
        obj_id = None
        for key in ("id", "object_id", "oid"):
            if key in obj:
                obj_id = str(obj[key])
                break

        if obj_id and self._ensure_job_and_doc():
            api_detail = self.api_client.get_object_detail(
                self._current_job_id,  # type: ignore[arg-type]
                self._current_doc_id,  # type: ignore[arg-type]
                obj_id,
            )
            if api_detail:
                detail = api_detail

        self.detail_text.setPlainText(
            json.dumps(detail, indent=2, ensure_ascii=False)
        )
        self.detail_tabs.setCurrentWidget(self.detail_text)

    def _on_show_links(self) -> None:
        """Mostra il JSON dei links del documento corrente."""
        if not self._ensure_job_and_doc():
            return

        data = self.api_client.get_document_links(
            self._current_job_id,  # type: ignore[arg-type]
            self._current_doc_id,  # type: ignore[arg-type]
        )

        if not data:
            self.links_text.setPlainText("(Nessun link disponibile)")
        else:
            self.links_text.setPlainText(
                json.dumps(data, indent=2, ensure_ascii=False)
            )

        self.detail_tabs.setCurrentWidget(self.links_text)

    def _on_show_manifest(self) -> None:
        """Mostra il JSON del manifest del documento corrente."""
        if not self._ensure_job_and_doc():
            return

        data = self.api_client.get_document_manifest(
            self._current_job_id,  # type: ignore[arg-type]
            self._current_doc_id,  # type: ignore[arg-type]
        )

        if not data:
            self.manifest_text.setPlainText("(Manifest non disponibile)")
        else:
            self.manifest_text.setPlainText(
                json.dumps(data, indent=2, ensure_ascii=False)
            )

        self.detail_tabs.setCurrentWidget(self.manifest_text)

    def _on_show_fixed_fields(self) -> None:
        """Mostra i campi fissi BPER per la pagina dell'oggetto selezionato."""
        obj = self._get_selected_object()
        if obj is None:
            QMessageBox.information(
                self,
                "Nessun oggetto",
                "Seleziona un oggetto per determinare la pagina.",
            )
            return

        if not self._ensure_job_and_doc():
            return

        # I dati completi dell'oggetto sono in obj["data"] (API lato server li include)
        data = obj.get("data") if isinstance(obj, dict) else None
        metadata = {}
        if isinstance(data, dict):
            metadata = data.get("metadata") or {}
        # fallback: alcuni oggetti potrebbero avere metadata al primo livello
        if not metadata and isinstance(obj, dict):
            metadata = obj.get("metadata") or {}

        page_no = metadata.get("page_no") or metadata.get("page") or 0
        page_type = metadata.get("page_type") or metadata.get("pageType")

        try:
            page_no_int = int(page_no)
        except Exception:
            page_no_int = 0

        # Chiamata API per fixed fields
        try:
            ff = self.api_client.get_page_fixed_fields(
                self._current_job_id,  # type: ignore[arg-type]
                self._current_doc_id,  # type: ignore[arg-type]
                page_no_int,
                page_type=page_type,
            )
        except Exception as e:
            ff = None

        self.fixed_tree.clear()

        if not ff:
            self.fixed_header.setText("(Fixed fields non disponibili per questa pagina)")
            self.detail_tabs.setCurrentWidget(self.fixed_tab)
            return

        # Header qualità più leggibile
        needs_review = bool(ff.get("needs_review"))
        quality = ff.get("quality") or {}
        validator = ff.get("validator") or {}
        page_no_v = ff.get("page_no", page_no_int)
        page_type_v = ff.get("page_type", page_type) or "?"
        sent_total = quality.get("sentinels_total")
        sent_ok = quality.get("sentinels_ok")
        failed_rules_list = quality.get("rules_failed", []) or []
        rules_failed = ", ".join(failed_rules_list[:3])
        img_used = bool(validator.get("image_used"))
        status_emoji = "✅" if not needs_review else "⚠️"
        img_emoji = "🖼️" if img_used else "🖼️✖"

        header = (
            f"{status_emoji} Pagina {page_no_v:02d}-{page_type_v}  •  "
            f"Qualità: {sent_ok}/{sent_total}  •  {img_emoji} immagine"
        )
        if rules_failed:
            header += f"  •  Regole KO: {rules_failed}"
        self.fixed_header.setText(header)
        # Tooltip con dettagli completi
        img_bucket = validator.get("image_bucket") or "?"
        img_key = validator.get("image_key") or "?"
        self.fixed_header.setToolTip(
            f"needs_review={needs_review}\n"
            f"sentinels_ok={sent_ok} / sentinels_total={sent_total}\n"
            f"image_used={img_used} (bucket={img_bucket}, key={img_key})\n"
            f"rules_failed={failed_rules_list}"
        )

        # Popola tabella con fields
        fields = ff.get("fields") or {}
        for k, v in fields.items():
            val = v
            if isinstance(val, (dict, list)):
                try:
                    val = json.dumps(val, ensure_ascii=False)
                except Exception:
                    val = str(val)
            item = QTreeWidgetItem([str(k), "" if val is None else str(val)])
            self.fixed_tree.addTopLevelItem(item)

        self.detail_tabs.setCurrentWidget(self.fixed_tab)

    # ------------------------------------------------------------------ API pubblica

    def set_job_id(self, job_id: Optional[str]) -> None:
        """
        Imposta il job_id corrente (chiamato da MainWindow quando si passa
        dai tab di cattura ai risultati).

        Se il job_id non è presente in lista, viene aggiunto.
        """
        if not job_id:
            return

        job_id = job_id.strip()
        if not job_id:
            return

        # Aggiungi alla combo se non presente
        if self.job_combo.findText(job_id) == -1:
            self.job_combo.addItem(job_id)

        # Seleziona e forza il caricamento dei documenti
        self.job_combo.setCurrentText(job_id)
        self._on_job_changed(job_id)
