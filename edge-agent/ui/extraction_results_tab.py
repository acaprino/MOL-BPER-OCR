"""Tab per visualizzare i risultati dell'estrazione locale."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTextEdit,
    QComboBox,
    QSplitter,
    QFileDialog,
    QMessageBox,
)


class ExtractionResultsTab(QWidget):
    """
    Tab locale per visualizzare i risultati dell'estrazione IE.

    Si connette a LocalExtractionClient.result_ready per aggiornarsi
    automaticamente ad ogni frame processato.
    """

    def __init__(
        self,
        extraction_client: Any,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._client = extraction_client
        self._current_job_id: Optional[str] = None
        self._results: List[Dict[str, Any]] = []

        self._init_ui()

        try:
            self._client.result_ready.connect(self._on_result_ready)
        except Exception:
            pass

    # ------------------------------------------------------------------ UI setup

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Top row: job selector + refresh + export
        top_row = QHBoxLayout()

        top_row.addWidget(QLabel("Job:", self))
        self.job_combo = QComboBox(self)
        self.job_combo.currentTextChanged.connect(self._on_job_changed)
        top_row.addWidget(self.job_combo)

        refresh_btn = QPushButton("🔄 Ricarica", self)
        refresh_btn.clicked.connect(self._refresh)
        top_row.addWidget(refresh_btn)

        export_csv_btn = QPushButton("⬇️ Export CSV", self)
        export_csv_btn.clicked.connect(self._on_export_csv)
        top_row.addWidget(export_csv_btn)

        top_row.addStretch(1)
        layout.addLayout(top_row)

        # Splitter: pages list (left) | fields + raw JSON (right)
        splitter = QSplitter(self)
        splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)

        # Left: captured pages
        self.pages_tree = QTreeWidget(self)
        self.pages_tree.setHeaderLabels(["Screen", "Tipo pagina", "Status", "NDG"])
        self.pages_tree.setColumnWidth(0, 150)
        self.pages_tree.setColumnWidth(1, 130)
        self.pages_tree.setColumnWidth(2, 80)
        self.pages_tree.setColumnWidth(3, 120)
        self.pages_tree.itemActivated.connect(self._on_page_activated)
        splitter.addWidget(self.pages_tree)

        # Right: fields table + raw JSON
        right = QWidget(self)
        right_layout = QVBoxLayout(right)

        self.fields_tree = QTreeWidget(right)
        self.fields_tree.setHeaderLabels(["Campo", "Valore", "Confidence"])
        self.fields_tree.setColumnWidth(0, 220)
        self.fields_tree.setColumnWidth(1, 200)
        right_layout.addWidget(self.fields_tree, stretch=2)

        self.raw_text = QTextEdit(right)
        self.raw_text.setReadOnly(True)
        self.raw_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        right_layout.addWidget(self.raw_text, stretch=1)

        right.setLayout(right_layout)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)

    # ------------------------------------------------------------------ Slots

    def _on_result_ready(self, job_id: str, result: dict) -> None:
        """Called from LocalExtractionClient when a new result is available."""
        if self.job_combo.findText(job_id) == -1:
            self.job_combo.addItem(job_id)

        if self._current_job_id is None:
            self._current_job_id = job_id
            self.job_combo.setCurrentText(job_id)

        if job_id == self._current_job_id:
            self._load_pages(job_id)

    def _on_job_changed(self, job_id: str) -> None:
        self._current_job_id = job_id.strip() or None
        if self._current_job_id:
            self._load_pages(self._current_job_id)
        else:
            self.pages_tree.clear()
            self.fields_tree.clear()
            self.raw_text.clear()

    def _refresh(self) -> None:
        for job_id in self._client.get_all_job_ids():
            if self.job_combo.findText(job_id) == -1:
                self.job_combo.addItem(job_id)
        if self._current_job_id:
            self._load_pages(self._current_job_id)

    def _load_pages(self, job_id: str) -> None:
        self._results = self._client.get_results(job_id)
        self.pages_tree.clear()
        for r in self._results:
            screen_id = str(r.get("screen_id") or "?")
            page_type = str(r.get("_page_type") or "")
            status = str(r.get("_status") or "")
            ndg = str(((r.get("fields") or {}).get("ndg") or {}).get("value") or "")
            item = QTreeWidgetItem([screen_id, page_type, status, ndg])
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, r)
            self.pages_tree.addTopLevelItem(item)

    def _on_page_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        result = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(result, dict):
            self._show_result(result)

    def _show_result(self, result: dict) -> None:
        # Populate fields table
        self.fields_tree.clear()
        for key, field_data in (result.get("fields") or {}).items():
            if not isinstance(field_data, dict):
                continue
            value = str(field_data.get("value") or "")
            conf = field_data.get("confidence")
            conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else ""
            self.fields_tree.addTopLevelItem(QTreeWidgetItem([key, value, conf_str]))

        # Show meta summary + raw JSON
        meta = result.get("_meta_agg") or {}
        cost = meta.get("estimated_cost_usd", 0.0)
        tokens = meta.get("total_tokens", 0)
        latency = meta.get("latency_ms", 0)
        self.raw_text.setPlainText(
            f"Cost: ${cost:.6f}  |  Tokens: {tokens}  |  Latency: {latency}ms\n\n"
            + json.dumps(result, indent=2, ensure_ascii=False, default=str)
        )

    def _on_export_csv(self) -> None:
        job_id = self._current_job_id or self.job_combo.currentText().strip()
        if not job_id:
            QMessageBox.warning(self, "Export CSV", "Nessun job selezionato.")
            return
        csv_text = self._client.export_csv(job_id)
        if not csv_text:
            QMessageBox.warning(self, "Export CSV", "Nessun risultato disponibile per questo job.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Salva CSV", f"extraction_{job_id}.csv", "CSV (*.csv)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(csv_text)
        QMessageBox.information(self, "Export CSV", f"Salvato in:\n{path}")

    # ------------------------------------------------------------------ Public API

    def set_job_id(self, job_id: Optional[str]) -> None:
        """Called by MainWindow when switching to this tab."""
        if not job_id:
            return
        if self.job_combo.findText(job_id) == -1:
            self.job_combo.addItem(job_id)
        self.job_combo.setCurrentText(job_id)
