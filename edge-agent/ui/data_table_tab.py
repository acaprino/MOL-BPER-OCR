"""Tab con vista a spreadsheet dei dati estratti."""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path
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
    QInputDialog,
    QMessageBox,
    QHeaderView,
)

# ---------------------------------------------------------------------------
# Canonical display names fallback (used when canonical_fields is absent)
# ---------------------------------------------------------------------------

import app_paths

_EXTRACTION_ROOT = app_paths.project_root()
if not app_paths.is_frozen() and str(_EXTRACTION_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXTRACTION_ROOT))

try:
    from extraction.field_definitions import CANONICAL_FIELD_DEFINITIONS  # type: ignore
    _CANONICAL_DISPLAY_NAMES: Dict[str, str] = {
        k: v["display_name"] for k, v in CANONICAL_FIELD_DEFINITIONS.items()
    }
except Exception:
    _CANONICAL_DISPLAY_NAMES = {}


def _friendly_name(key: str) -> str:
    """Ultimo fallback: converte una schema key in etichetta leggibile."""
    import re
    s = key.strip()
    s = re.sub(r'^[0-9][0-9A-Za-z\.]*[_\s]+', '', s)
    s = s.replace('_', ' ').replace('-', ' ')
    s = re.sub(r'\s+', ' ', s).strip().title()
    return s or key


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FIXED_COLUMNS = ["Schermata"]


# ---------------------------------------------------------------------------
# Tab
# ---------------------------------------------------------------------------

class DataTableTab(QWidget):
    """
    Tab spreadsheet: una riga per schermata acquisita, una colonna per campo estratto.

    Le colonne sono ordinate e raggruppate per page_name (dal contratto canonical_fields).
    L'header di ogni colonna mostra il display_name; il tooltip mostra il page_name.
    L'export Excel produce un foglio per ogni page_name.
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

        # Lista ordinata di metadati campo: {schema_key, display_name, page_key, page_name}
        self._field_meta: List[Dict[str, Any]] = []
        # Lookup veloce schema_key -> meta
        self._meta_by_key: Dict[str, Dict[str, Any]] = {}

        # Rinomina colonne: schema_key -> label utente (sovrascrive display_name)
        self._column_labels: Dict[str, str] = {}
        # Indice colonna selezionata via clic header
        self._selected_col_idx: Optional[int] = None

        self._init_ui()

        try:
            self._client.result_ready.connect(self._on_result_ready)
        except Exception:
            pass

    # ------------------------------------------------------------------ UI setup

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()

        top_row.addWidget(QLabel("Sessione:", self))
        self.job_combo = QComboBox(self)
        self.job_combo.currentTextChanged.connect(self._on_job_changed)
        top_row.addWidget(self.job_combo)

        refresh_btn = QPushButton("🔄 Ricarica", self)
        refresh_btn.clicked.connect(self._refresh)
        top_row.addWidget(refresh_btn)

        self.rename_btn = QPushButton("✏️ Rinomina colonna", self)
        self.rename_btn.setEnabled(False)
        self.rename_btn.setToolTip("Clicca un'intestazione di colonna, poi questo pulsante per rinominarla")
        self.rename_btn.clicked.connect(self._on_rename_column)
        top_row.addWidget(self.rename_btn)

        export_csv_btn = QPushButton("⬇️ Esporta CSV", self)
        export_csv_btn.clicked.connect(self._on_export_csv)
        top_row.addWidget(export_csv_btn)

        export_xlsx_btn = QPushButton("⬇️ Esporta Excel", self)
        export_xlsx_btn.clicked.connect(self._on_export_excel)
        top_row.addWidget(export_xlsx_btn)

        top_row.addStretch(1)
        layout.addLayout(top_row)

        self.table = QTableWidget(self)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

        layout.addWidget(self.table)

    # ------------------------------------------------------------------ Label helpers

    def _get_label(self, key: str) -> str:
        """Label attuale per una schema key: override utente > display_name > fallback."""
        if key in self._column_labels:
            return self._column_labels[key]
        meta = self._meta_by_key.get(key)
        if meta and meta.get("display_name"):
            return meta["display_name"]
        if key in _CANONICAL_DISPLAY_NAMES:
            return _CANONICAL_DISPLAY_NAMES[key]
        return _friendly_name(key)

    # ------------------------------------------------------------------ Data helpers

    def _get_values_by_key(self, result: Dict[str, Any]) -> Dict[str, str]:
        """Estrae {schema_key: valore} da canonical_fields, con fallback su fields."""
        values: Dict[str, str] = {}
        for entry in (result.get("canonical_fields") or []):
            key = entry.get("schema_key")
            if key:
                values[key] = str(entry.get("value") or "")
        if not values:
            for key, field_data in (result.get("fields") or {}).items():
                if isinstance(field_data, dict):
                    values[key] = str(field_data.get("value") or "")
        return values

    def _build_field_meta(self) -> List[Dict[str, Any]]:
        """
        Costruisce la lista ordinata di metadati campo scansionando tutti i risultati.
        Usa canonical_fields se disponibile, altrimenti cade su fields + CANONICAL_FIELD_DEFINITIONS.
        """
        seen: set = set()
        meta_list: List[Dict[str, Any]] = []

        for r in self._results:
            for entry in (r.get("canonical_fields") or []):
                key = entry.get("schema_key")
                if key and key not in seen:
                    seen.add(key)
                    meta_list.append({
                        "schema_key": key,
                        "display_name": entry.get("display_name") or _friendly_name(key),
                        "page_key": entry.get("page_key") or "",
                        "page_name": entry.get("page_name") or "",
                    })

        # Fallback se nessun risultato ha canonical_fields
        if not meta_list:
            for r in self._results:
                for key in (r.get("fields") or {}).keys():
                    if key not in seen:
                        seen.add(key)
                        canon = _CANONICAL_DISPLAY_NAMES.get(key)
                        meta_list.append({
                            "schema_key": key,
                            "display_name": canon or _friendly_name(key),
                            "page_key": "",
                            "page_name": "",
                        })

        return meta_list

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

    def _on_header_clicked(self, col_idx: int) -> None:
        if col_idx < len(_FIXED_COLUMNS):
            self._selected_col_idx = None
            self.rename_btn.setEnabled(False)
            self.rename_btn.setText("✏️ Rinomina colonna")
            return

        self._selected_col_idx = col_idx
        item = self.table.horizontalHeaderItem(col_idx)
        label_text = item.text() if item else "?"
        self.rename_btn.setEnabled(True)
        self.rename_btn.setText(f"✏️ Rinomina: {label_text}")

    def _on_rename_column(self) -> None:
        if self._selected_col_idx is None:
            return

        field_idx = self._selected_col_idx - len(_FIXED_COLUMNS)
        if field_idx < 0 or field_idx >= len(self._field_meta):
            return

        key = self._field_meta[field_idx]["schema_key"]
        current_label = self._get_label(key)

        new_label, ok = QInputDialog.getText(
            self,
            "Rinomina colonna",
            "Nuovo nome per la colonna:",
            text=current_label,
        )
        if not ok or not new_label.strip():
            return

        new_label = new_label.strip()
        self._column_labels[key] = new_label
        self._refresh_headers()
        self.rename_btn.setText(f"✏️ Rinomina: {new_label}")

    # ------------------------------------------------------------------ Table population

    def _load_table(self, job_id: str) -> None:
        self._results = self._client.get_results(job_id)
        if not self._results:
            self.table.clearContents()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return

        self._field_meta = self._build_field_meta()
        self._meta_by_key = {m["schema_key"]: m for m in self._field_meta}

        n_cols = len(_FIXED_COLUMNS) + len(self._field_meta)
        self.table.setRowCount(len(self._results))
        self.table.setColumnCount(n_cols)

        self._refresh_headers()

        for row_idx, result in enumerate(self._results):
            page_type = str(result.get("_page_type") or result.get("screen_id") or "?")
            self._set_cell(row_idx, 0, page_type)

            values = self._get_values_by_key(result)
            for col_offset, meta in enumerate(self._field_meta):
                col_idx = len(_FIXED_COLUMNS) + col_offset
                value = values.get(meta["schema_key"], "")
                self._set_cell(row_idx, col_idx, value if value else "–")

    def _refresh_headers(self) -> None:
        """Aggiorna intestazioni: testo = label attuale, tooltip = page_name."""
        headers = list(_FIXED_COLUMNS) + [self._get_label(m["schema_key"]) for m in self._field_meta]
        self.table.setHorizontalHeaderLabels(headers)

        for col_offset, meta in enumerate(self._field_meta):
            col_idx = len(_FIXED_COLUMNS) + col_offset
            item = self.table.horizontalHeaderItem(col_idx)
            if item and meta.get("page_name"):
                item.setToolTip(meta["page_name"])

    def _set_cell(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col, item)

    # ------------------------------------------------------------------ Export

    def _on_export_csv(self) -> None:
        """CSV piatto: una colonna per campo, intestazioni con label correnti."""
        job_id = self._current_job_id or self.job_combo.currentText().strip()
        if not job_id or not self._results:
            QMessageBox.warning(self, "Esporta CSV", "Nessun dato disponibile da esportare.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Salva CSV", f"dati_{job_id}.csv", "CSV (*.csv)"
        )
        if not path:
            return

        headers = list(_FIXED_COLUMNS) + [self._get_label(m["schema_key"]) for m in self._field_meta]
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(headers)
                for result in self._results:
                    page_type = str(result.get("_page_type") or result.get("screen_id") or "?")
                    values = self._get_values_by_key(result)
                    row = [page_type] + [values.get(m["schema_key"], "") for m in self._field_meta]
                    writer.writerow(row)
            QMessageBox.information(self, "Esporta CSV", f"File salvato in:\n{path}")
        except OSError as e:
            QMessageBox.critical(self, "Errore", f"Errore durante la scrittura:\n{e}")

    def _on_export_excel(self) -> None:
        """Excel con un foglio per ogni page_name; colonne filtrate per pagina."""
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

        # Raggruppa campi per page_name (preservando l'ordine di _field_meta)
        pages: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for meta in self._field_meta:
            page_name = meta.get("page_name") or "Altro"
            pages[page_name].append(meta)

        try:
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                for page_name, page_fields in pages.items():
                    headers = list(_FIXED_COLUMNS) + [
                        self._get_label(m["schema_key"]) for m in page_fields
                    ]
                    rows = []
                    for result in self._results:
                        page_type = str(result.get("_page_type") or result.get("screen_id") or "?")
                        values = self._get_values_by_key(result)
                        rows.append(
                            [page_type] + [values.get(m["schema_key"], "") for m in page_fields]
                        )
                    df = pd.DataFrame(rows, columns=headers)
                    df.to_excel(writer, sheet_name=page_name[:31], index=False)

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
