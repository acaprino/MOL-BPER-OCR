"""Tab con vista a spreadsheet delle pratiche estratte."""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from PyQt6 import QtCore
from PyQt6.QtGui import QBrush, QColor, QFont
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

import app_paths

_EXTRACTION_ROOT = app_paths.src_dir()
if not app_paths.is_frozen() and str(_EXTRACTION_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXTRACTION_ROOT))

from excel_export import ColumnSpec, PAGE_BAND_COLORS, build_columns, export_results
from practice_consolidation import PracticeRecord, consolidate

# ============================================================
# Costanti
# ============================================================

# Riga 0 della tabella: fascia di raggruppamento per pagina canonica.
# QTableWidget non ha intestazioni a due livelli native, quindi la fascia e'
# una riga reale con celle unite via setSpan().
_BAND_ROW = 0
_FIRST_DATA_ROW = 1


# ============================================================
# Tab
# ============================================================


class DataTableTab(QWidget):
    """
    Tab spreadsheet: una riga per pratica, una colonna per campo canonico.

    I frame catturati vengono consolidati per NDG: le 9 schermate del router
    sono varianti di 4 pagine della stessa pratica, quindi una riga per frame
    mostrerebbe la stessa pratica nove volte, quasi sempre vuota.
    """

    def __init__(
        self,
        extraction_client: Any,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._client = extraction_client
        self._current_job_id: Optional[str] = None
        self._records: List[PracticeRecord] = []

        # Rinomina colonne: schema_key -> label utente (sovrascrive display_name)
        self._column_labels: Dict[str, str] = {}
        self._columns: List[ColumnSpec] = build_columns()
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
        self.rename_btn.setToolTip(
            "Clicca un'intestazione di colonna, poi questo pulsante per rinominarla"
        )
        self.rename_btn.clicked.connect(self._on_rename_column)
        top_row.addWidget(self.rename_btn)

        export_xlsx_btn = QPushButton("⬇️ Esporta Excel", self)
        export_xlsx_btn.clicked.connect(self._on_export_excel)
        top_row.addWidget(export_xlsx_btn)

        top_row.addStretch(1)
        layout.addLayout(top_row)

        self.table = QTableWidget(self)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

        layout.addWidget(self.table)

    # ------------------------------------------------------------------ Slots

    def _on_result_ready(self, job_id: str, _result: dict) -> None:
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
            self._clear_table()

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
        self._selected_col_idx = col_idx
        item = self.table.horizontalHeaderItem(col_idx)
        label_text = item.text() if item else "?"
        self.rename_btn.setEnabled(True)
        self.rename_btn.setText(f"✏️ Rinomina: {label_text}")

    def _on_rename_column(self) -> None:
        if self._selected_col_idx is None:
            return
        if not 0 <= self._selected_col_idx < len(self._columns):
            return

        column = self._columns[self._selected_col_idx]

        new_label, ok = QInputDialog.getText(
            self,
            "Rinomina colonna",
            "Nuovo nome per la colonna:",
            text=column.label,
        )
        if not ok or not new_label.strip():
            return

        new_label = new_label.strip()
        self._column_labels[column.schema_key] = new_label
        # L'ordine non dipende dalle label (build_columns ordina sui display_name
        # canonici), quindi rinominare non fa saltare le colonne.
        self._columns = build_columns(self._column_labels)
        self._refresh_headers()
        self.rename_btn.setText(f"✏️ Rinomina: {new_label}")

    # ------------------------------------------------------------------ Table population

    def _clear_table(self) -> None:
        self._records = []
        self.table.clearContents()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

    def _load_table(self, job_id: str) -> None:
        self._records = consolidate(self._client.get_results(job_id))
        if not self._records:
            self._clear_table()
            return

        self.table.clearSpans()
        self.table.setColumnCount(len(self._columns))
        self.table.setRowCount(_FIRST_DATA_ROW + len(self._records))

        self._refresh_headers()
        self._paint_band_row()

        for row_offset, record in enumerate(self._records):
            row = _FIRST_DATA_ROW + row_offset
            for col_idx, column in enumerate(self._columns):
                value = (record.fields.get(column.schema_key) or {}).get("value")
                self._set_cell(row, col_idx, "" if value is None else str(value))

    def _refresh_headers(self) -> None:
        self.table.setHorizontalHeaderLabels([c.label for c in self._columns])
        for col_idx, column in enumerate(self._columns):
            item = self.table.horizontalHeaderItem(col_idx)
            if item:
                item.setToolTip(f"{column.page_name} — {column.schema_key}")

    def _paint_band_row(self) -> None:
        """Riga 0: nome della pagina canonica su celle unite, una per gruppo."""
        start = 0
        for index in range(1, len(self._columns) + 1):
            is_last = index == len(self._columns)
            changes = (
                not is_last
                and self._columns[index].page_key != self._columns[index - 1].page_key
            )
            if not (is_last or changes):
                continue

            column = self._columns[start]
            item = QTableWidgetItem(column.page_name)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            font = QFont()
            font.setBold(True)
            item.setFont(font)
            item.setBackground(
                QBrush(QColor("#" + PAGE_BAND_COLORS.get(column.page_key, "555555")))
            )
            item.setForeground(QBrush(QColor("#FFFFFF")))
            self.table.setItem(_BAND_ROW, start, item)
            if index > start + 1:
                self.table.setSpan(_BAND_ROW, start, 1, index - start)
            start = index

    def _set_cell(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col, item)

    # ------------------------------------------------------------------ Export

    def _on_export_excel(self) -> None:
        job_id = self._current_job_id or self.job_combo.currentText().strip()
        if not job_id or not self._records:
            QMessageBox.warning(
                self, "Esporta Excel", "Nessun dato disponibile da esportare."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Salva Excel", f"dati_{job_id}.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return

        try:
            written = export_results(
                self._client.get_results(job_id), path, labels=self._column_labels
            )
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Errore", f"Errore durante la scrittura:\n{e}")
            return

        QMessageBox.information(
            self,
            "Esporta Excel",
            f"{written} pratiche salvate in:\n{path}",
        )

    # ------------------------------------------------------------------ Public API

    def set_job_id(self, job_id: Optional[str]) -> None:
        """Chiamato da MainWindow quando si passa a questa tab."""
        if not job_id:
            return
        if self.job_combo.findText(job_id) == -1:
            self.job_combo.addItem(job_id)
        self.job_combo.setCurrentText(job_id)
