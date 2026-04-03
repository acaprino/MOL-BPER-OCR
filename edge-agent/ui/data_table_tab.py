"""Tab con vista a spreadsheet dei dati estratti."""

from __future__ import annotations

import csv
import io
import re
from typing import Any, Dict, List, Optional

from PyQt6 import QtCore
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
    QMessageBox,
    QHeaderView,
)


def _friendly_name(key: str) -> str:
    """Converte una field key in un'etichetta leggibile."""
    s = key.strip()
    s = re.sub(r'^[0-9][0-9A-Za-z\.]*[_\s]+', '', s)
    s = s.replace('_', ' ').replace('-', ' ')
    s = re.sub(r'\s+', ' ', s).strip().title()
    return s or key


# Colonne fisse visualizzate all'inizio della tabella (non field key)
_FIXED_COLUMNS = ["Schermata"]

# Ordine preferito delle field key (quelle più importanti vengono prima)
_PRIORITY_FIELDS = [
    "ndg", "denominazione", "tipo", "stato", "fase", "creazione", "evidenze",
    "filiale_relazione", "n_fido", "rapporto", "descrizione", "scadenza",
    "importo_euro", "tipo_op", "note_della_richiesta",
]


class DataTableTab(QWidget):
    """
    Tab spreadsheet: una riga per schermata acquisita, una colonna per campo estratto.

    Mostra tutti i valori estratti in formato tabellare, con export CSV e Excel.
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
        self._field_keys: List[str] = []

        self._init_ui()

        try:
            self._client.result_ready.connect(self._on_result_ready)
        except Exception:
            pass

    # ------------------------------------------------------------------ UI setup

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Top row: sessione + azioni
        top_row = QHBoxLayout()

        top_row.addWidget(QLabel("Sessione:", self))
        self.job_combo = QComboBox(self)
        self.job_combo.currentTextChanged.connect(self._on_job_changed)
        top_row.addWidget(self.job_combo)

        refresh_btn = QPushButton("🔄 Ricarica", self)
        refresh_btn.clicked.connect(self._refresh)
        top_row.addWidget(refresh_btn)

        export_csv_btn = QPushButton("⬇️ Esporta CSV", self)
        export_csv_btn.clicked.connect(self._on_export_csv)
        top_row.addWidget(export_csv_btn)

        export_xlsx_btn = QPushButton("⬇️ Esporta Excel", self)
        export_xlsx_btn.clicked.connect(self._on_export_excel)
        top_row.addWidget(export_xlsx_btn)

        top_row.addStretch(1)
        layout.addLayout(top_row)

        # Tabella principale
        self.table = QTableWidget(self)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

    # ------------------------------------------------------------------ Slots

    def _on_result_ready(self, job_id: str, result: dict) -> None:
        if self.job_combo.findText(job_id) == -1:
            self.job_combo.addItem(job_id)

        if self._current_job_id is None:
            self._current_job_id = job_id
            self.job_combo.setCurrentText(job_id)

        if job_id == self._current_job_id:
            self._load_table(job_id)

    def _on_job_changed(self, job_id: str) -> None:
        self._current_job_id = job_id.strip() or None
        if self._current_job_id:
            self._load_table(self._current_job_id)
        else:
            self.table.clearContents()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)

    def _refresh(self) -> None:
        try:
            for job_id in self._client.get_all_job_ids():
                if self.job_combo.findText(job_id) == -1:
                    self.job_combo.addItem(job_id)
        except Exception:
            pass
        if self._current_job_id:
            self._load_table(self._current_job_id)

    # ------------------------------------------------------------------ Table population

    def _load_table(self, job_id: str) -> None:
        self._results = self._client.get_results(job_id)
        if not self._results:
            self.table.clearContents()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return

        # Raccoglie tutte le field key presenti nei risultati, mantenendo l'ordine priorità
        all_keys: List[str] = []
        seen = set()
        for key in _PRIORITY_FIELDS:
            all_keys.append(key)
            seen.add(key)
        for r in self._results:
            for k in (r.get("fields") or {}).keys():
                if k not in seen:
                    all_keys.append(k)
                    seen.add(k)
        self._field_keys = all_keys

        # Imposta dimensioni tabella
        n_cols = len(_FIXED_COLUMNS) + len(self._field_keys)
        self.table.setRowCount(len(self._results))
        self.table.setColumnCount(n_cols)

        # Intestazioni colonne
        headers = list(_FIXED_COLUMNS) + [_friendly_name(k) for k in self._field_keys]
        self.table.setHorizontalHeaderLabels(headers)

        # Popola righe
        for row_idx, result in enumerate(self._results):
            page_type = str(result.get("_page_type") or result.get("screen_id") or "?")
            self._set_cell(row_idx, 0, page_type)

            fields = result.get("fields") or {}
            for col_offset, key in enumerate(self._field_keys):
                col_idx = len(_FIXED_COLUMNS) + col_offset
                field_data = fields.get(key) or {}
                value = str(field_data.get("value") or "") if isinstance(field_data, dict) else ""
                self._set_cell(row_idx, col_idx, value if value else "–")

    def _set_cell(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col, item)

    # ------------------------------------------------------------------ Export

    def _build_rows(self) -> tuple[list[str], list[list[str]]]:
        """Restituisce (headers, rows) come liste di stringhe."""
        headers = list(_FIXED_COLUMNS) + [_friendly_name(k) for k in self._field_keys]
        rows: List[List[str]] = []
        for result in self._results:
            page_type = str(result.get("_page_type") or result.get("screen_id") or "?")
            row: List[str] = [page_type]
            fields = result.get("fields") or {}
            for key in self._field_keys:
                field_data = fields.get(key) or {}
                value = str(field_data.get("value") or "") if isinstance(field_data, dict) else ""
                row.append(value)
            rows.append(row)
        return headers, rows

    def _on_export_csv(self) -> None:
        job_id = self._current_job_id or self.job_combo.currentText().strip()
        if not job_id or not self._results:
            QMessageBox.warning(self, "Esporta CSV", "Nessun dato disponibile da esportare.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Salva CSV", f"dati_{job_id}.csv", "CSV (*.csv)"
        )
        if not path:
            return

        headers, rows = self._build_rows()
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
            QMessageBox.information(self, "Esporta CSV", f"File salvato in:\n{path}")
        except OSError as e:
            QMessageBox.critical(self, "Errore", f"Errore durante la scrittura:\n{e}")

    def _on_export_excel(self) -> None:
        job_id = self._current_job_id or self.job_combo.currentText().strip()
        if not job_id or not self._results:
            QMessageBox.warning(self, "Esporta Excel", "Nessun dato disponibile da esportare.")
            return

        try:
            import pandas as pd  # type: ignore
        except ImportError:
            QMessageBox.critical(
                self, "Libreria mancante",
                "pandas non è installato. Esegui:\n\npip install pandas openpyxl"
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Salva Excel", f"dati_{job_id}.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return

        headers, rows = self._build_rows()
        try:
            df = pd.DataFrame(rows, columns=headers)
            df.to_excel(path, index=False, engine="openpyxl")
            QMessageBox.information(self, "Esporta Excel", f"File salvato in:\n{path}")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Errore", f"Errore durante la scrittura:\n{e}")

    # ------------------------------------------------------------------ Public API

    def set_job_id(self, job_id: Optional[str]) -> None:
        """Chiamato da MainWindow quando si passa a questa tab."""
        if not job_id:
            return
        if self.job_combo.findText(job_id) == -1:
            self.job_combo.addItem(job_id)
        self.job_combo.setCurrentText(job_id)
