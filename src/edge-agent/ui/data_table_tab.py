"""Tab con vista a spreadsheet delle pratiche estratte."""

from __future__ import annotations

import sys
from typing import Any, List, Optional

from PyQt6 import QtCore, QtGui
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QHeaderView,
    QStackedLayout,
)

import app_paths
import theme

_EXTRACTION_ROOT = app_paths.src_dir()
if not app_paths.is_frozen() and str(_EXTRACTION_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXTRACTION_ROOT))

from excel_export import ColumnSpec, PAGE_BAND_COLORS, build_columns
from practice_consolidation import PracticeRecord, consolidate

from . import icons
from .widgets import default_export_name

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

    Le etichette di colonna rinominate vivono nel client, così valgono per ogni
    export (anche quello della tab Cattura).
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
        self._columns: List[ColumnSpec] = build_columns(self._client.get_column_labels())

        self._init_ui()

        try:
            self._client.result_ready.connect(self._on_result_ready)
        except Exception:
            pass

    # ------------------------------------------------------------------ UI setup

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        tokens = theme.current_tokens()

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        session_label = QLabel("Sessione", self)
        session_label.setProperty("muted", True)
        self.job_combo = QComboBox(self)
        self.job_combo.setMinimumWidth(210)
        self.job_combo.currentIndexChanged.connect(self._on_job_index_changed)

        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText("Cerca per NDG o denominazione")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMinimumWidth(300)
        self.search_box.setToolTip("Filtra le pratiche (Ctrl+F)")
        self.search_box.addAction(
            icons.icon("search", tokens.text_muted, 16), QLineEdit.ActionPosition.LeadingPosition
        )
        self.search_box.textChanged.connect(self._apply_filter)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+F"), self, activated=self._focus_search)

        refresh_btn = QPushButton(self)
        refresh_btn.setIcon(icons.icon("refresh-cw", tokens.text, 18))
        refresh_btn.setToolTip("Ricarica l'elenco delle sessioni e la tabella")
        refresh_btn.setAccessibleName("Ricarica")
        refresh_btn.clicked.connect(self._refresh)

        self.export_button = QPushButton("Esporta Excel", self)
        self.export_button.setProperty("primary", True)
        self.export_button.setIcon(icons.icon("download", tokens.on_primary, 18))
        self.export_button.setShortcut(QtGui.QKeySequence("Ctrl+E"))
        self.export_button.setToolTip("Esporta in Excel le pratiche della sessione (Ctrl+E)")
        self.export_button.clicked.connect(self._on_export_excel)

        toolbar.addWidget(session_label)
        toolbar.addWidget(self.job_combo)
        toolbar.addWidget(self.search_box)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self.export_button)
        layout.addLayout(toolbar)

        self.table = QTableWidget(self)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setToolTip("Doppio click su un'intestazione per rinominare la colonna")
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().sectionDoubleClicked.connect(self._on_header_double_clicked)

        # Stato vuoto: dice cosa fare invece di mostrare una griglia senza righe.
        self.empty_state = QWidget(self)
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.addStretch(1)
        title = QLabel("Nessuna pratica ancora", self.empty_state)
        title.setObjectName("cardTitle")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("Avvia la cattura dalla scheda Cattura: le pratiche compaiono qui.", self.empty_state)
        hint.setProperty("muted", True)
        hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(title)
        empty_layout.addWidget(hint)
        empty_layout.addStretch(2)

        self.stack = QStackedLayout()
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.table)
        self.stack.setCurrentWidget(self.empty_state)
        layout.addLayout(self.stack, stretch=1)

    # ------------------------------------------------------------------ Slots

    def _focus_search(self) -> None:
        self.search_box.setFocus()
        self.search_box.selectAll()

    def _ensure_job_item(self, job_id: str) -> None:
        if self.job_combo.findData(job_id) == -1:
            self.job_combo.addItem(self._client.session_label(job_id), job_id)

    def _select_job(self, job_id: str) -> None:
        self._ensure_job_item(job_id)
        self.job_combo.setCurrentIndex(self.job_combo.findData(job_id))

    def _on_result_ready(self, job_id: str, _result: dict) -> None:
        self._ensure_job_item(job_id)
        if self._current_job_id is None:
            self._select_job(job_id)
        if job_id == self._current_job_id:
            self._load_table(job_id)

    def _on_job_index_changed(self, index: int) -> None:
        job_id = self.job_combo.itemData(index) if index >= 0 else None
        self._current_job_id = job_id or None
        if self._current_job_id:
            self._load_table(self._current_job_id)
        else:
            self._clear_table()

    def _refresh(self) -> None:
        try:
            for job_id in self._client.get_all_job_ids():
                self._ensure_job_item(job_id)
        except Exception:
            pass
        if self._current_job_id:
            self._load_table(self._current_job_id)

    def _on_header_double_clicked(self, col_idx: int) -> None:
        if not 0 <= col_idx < len(self._columns):
            return

        column = self._columns[col_idx]

        new_label, ok = QInputDialog.getText(
            self,
            "Rinomina colonna",
            "Nuovo nome per la colonna:",
            text=column.label,
        )
        if not ok or not new_label.strip():
            return
        self._apply_column_label(column.schema_key, new_label)

    def _apply_column_label(self, schema_key: str, label: str) -> None:
        self._client.set_column_label(schema_key, label)
        # L'ordine non dipende dalle label (build_columns ordina sui display_name
        # canonici), quindi rinominare non fa saltare le colonne.
        self._columns = build_columns(self._client.get_column_labels())
        self._refresh_headers()

    def _apply_filter(self, *_args: object) -> None:
        needle = self.search_box.text().strip().casefold()
        for offset, record in enumerate(self._records):
            haystack = f"{record.ndg or ''} {record.denominazione or ''}".casefold()
            self.table.setRowHidden(_FIRST_DATA_ROW + offset, bool(needle) and needle not in haystack)

    # ------------------------------------------------------------------ Table population

    def _clear_table(self) -> None:
        self._records = []
        self.table.clearContents()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.stack.setCurrentWidget(self.empty_state)

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

        self.stack.setCurrentWidget(self.table)
        self._apply_filter()

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
        job_id = self._current_job_id
        if not job_id or not self._records:
            QMessageBox.warning(
                self,
                "Niente da esportare",
                "Non c'è ancora niente da esportare. Avvia la cattura e attendi almeno un'estrazione.",
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Salva Excel", default_export_name(), "Excel (*.xlsx)"
        )
        if not path:
            return

        try:
            # Unico percorso di export: etichette rinominate incluse.
            written = self._client.export_workbook(job_id, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Salvataggio non riuscito", f"Non riesco a salvare il file:\n{e}")
            return

        QMessageBox.information(
            self,
            "Esportazione completata",
            f"{written} pratiche salvate in:\n{path}",
        )

    # ------------------------------------------------------------------ Public API

    def set_job_id(self, job_id: Optional[str]) -> None:
        """Chiamato da MainWindow quando si passa a questa tab."""
        if not job_id:
            return
        self._select_job(job_id)
