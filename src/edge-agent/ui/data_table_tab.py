"""Tab con vista a spreadsheet delle pratiche estratte."""

from __future__ import annotations

import sys
from collections import deque
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, List, Optional

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
    QInputDialog,
    QHeaderView,
    QStackedLayout,
    QAbstractItemView,
    QAbstractItemDelegate,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QMenu,
)

import app_paths
import theme

_EXTRACTION_ROOT = app_paths.src_dir()
if not app_paths.is_frozen() and str(_EXTRACTION_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXTRACTION_ROOT))

from excel_export import ColumnSpec, PAGE_BAND_COLORS, build_columns
from local_extraction_client import clean_correction
from practice_consolidation import PracticeRecord, is_correctable

from . import icons
from .frozen_table import FrozenColumnsTable
from .workbook_export import WorkbookExport

# ============================================================
# Costanti
# ============================================================

# True on the cells whose value the operator corrected.
CORRECTED_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1

# Riga 0 della tabella: fascia di raggruppamento per pagina canonica.
# QTableWidget non ha intestazioni a due livelli native, quindi la fascia e'
# una riga reale con celle unite via setSpan().
_BAND_ROW = 0
_FIRST_DATA_ROW = 1


@dataclass(frozen=True)
class _EditWrite:
    action: str
    job: Optional[str]
    persist: Callable[[], None]
    editor_id: int = 0
    text: str = ""


class _WriteResult(QtCore.QObject):
    finished = QtCore.pyqtSignal(object, str)


class _WriteTask(QtCore.QRunnable):
    def __init__(self, request: _EditWrite) -> None:
        super().__init__()
        self.request = request
        self.result = _WriteResult()

    def run(self) -> None:
        try:
            self.request.persist()
        except Exception as exc:
            self.result.finished.emit(self.request, str(exc) or type(exc).__name__)
        else:
            self.result.finished.emit(self.request, "")


class _DraftDelegate(QStyledItemDelegate):
    """Keep unconfirmed editor text separate from the cell used for display and export."""

    def __init__(self, tab: DataTableTab, view: QAbstractItemView) -> None:
        super().__init__(view)
        self.tab = tab
        self.editor: Optional[QLineEdit] = None
        self.closeEditor.connect(self._on_close)

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QtCore.QModelIndex,
    ) -> Optional[QLineEdit]:
        target = self.tab._edit_target(index.row(), index.column())
        if not target or self.tab.has_pending_writes():
            return None
        job, ndg, key, _original = target
        draft = self.tab._client.get_cell_draft(job)
        if draft and (draft["ndg"], draft["key"]) != (ndg, key):
            # The existing draft has its own resume/discard controls.
            return None
        editor = QLineEdit(parent)
        editor.setProperty("cellTarget", target)
        editor.setToolTip("Invio o Tab per confermare, Esc per scartare. La bozza viene salvata mentre scrivi.")
        editor.textEdited.connect(lambda text: self._save_draft(editor, text))
        self.editor = editor
        return editor

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if (isinstance(watched, QLineEdit) and isinstance(event, QtGui.QKeyEvent)
                and event.type() == QtCore.QEvent.Type.KeyPress
                and event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter)):
            # Qt normally posts Return's commit to the next event-loop turn.
            # Queue the intent now so switching session or closing cannot erase it.
            self.commitData.emit(watched)
            self.closeEditor.emit(watched, QAbstractItemDelegate.EndEditHint.SubmitModelCache)
            return True
        if isinstance(watched, QLineEdit) and isinstance(event, QtGui.QFocusEvent):
            if event.type() == QtCore.QEvent.Type.FocusOut:
                # Searching, switching session or closing the window keeps an
                # unfinished draft. Only the editor's commit keys confirm it.
                if event.reason() != QtCore.Qt.FocusReason.PopupFocusReason:
                    self.closeEditor.emit(watched, QAbstractItemDelegate.EndEditHint.NoHint)
                return False
        return super().eventFilter(watched, event)

    def setEditorData(self, editor: QLineEdit, index: QtCore.QModelIndex) -> None:
        if editor.property("initialised"):
            return
        job, _ndg, _key, _original = editor.property("cellTarget")
        draft = self.tab._client.get_cell_draft(job)
        if draft:
            editor.setText(draft["text"])
            editor.setCursorPosition(len(editor.text()))
        else:
            editor.setText(str(index.data(QtCore.Qt.ItemDataRole.EditRole) or ""))
            editor.selectAll()
        editor.setProperty("initialised", True)
        editor.setProperty("savedText", editor.text())
        self.tab.draft_bar.hide()

    def _save_draft(self, editor: QLineEdit, text: str) -> None:
        job, ndg, key, _original = editor.property("cellTarget")
        save = partial(self.tab._client.set_cell_draft, job, ndg, key, text)
        self.tab._queue_write(_EditWrite("draft", job, save, id(editor), text))

    def setModelData(self, editor: QLineEdit, model: QtCore.QAbstractItemModel, index: QtCore.QModelIndex) -> None:
        # The normal Qt delegate skips itemChanged when text equals the cell.
        # Confirming even that text must atomically retire the matching draft.
        if not editor.isReadOnly():
            self.tab._commit_text(*editor.property("cellTarget"), editor.text())

    def _on_close(self, editor: QLineEdit, hint: QAbstractItemDelegate.EndEditHint) -> None:
        if editor is self.editor:
            self.editor = None
        if hint == QAbstractItemDelegate.EndEditHint.RevertModelCache:
            job, _ndg, _key, _original = editor.property("cellTarget")
            self.tab._discard_draft(job)


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

    writes_pending_changed = QtCore.pyqtSignal(bool)

    def __init__(
        self,
        extraction_client: Any,
        parent: Optional[QWidget] = None,
        workbook_export: Optional[WorkbookExport] = None,
    ) -> None:
        super().__init__(parent)

        self._client = extraction_client
        self._export = workbook_export or WorkbookExport(extraction_client, self)
        self._current_job_id: Optional[str] = None
        self._records: tuple[PracticeRecord, ...] = ()
        self._columns: List[ColumnSpec] = build_columns(self._client.get_column_labels())
        self._loading = False         # filling the table is not an edit
        self._reload_pending = False
        self._active_write: Optional[_WriteTask] = None
        self._queued_writes: deque[_EditWrite] = deque()
        self.last_write_failed = False
        self._result_timer = QtCore.QTimer(self)
        self._result_timer.setSingleShot(True)
        self._result_timer.timeout.connect(self._flush_results)

        self._init_ui()
        self._export.bind_button(self.export_button)
        self.writes_pending_changed.connect(self._update_export_after_edit)
        # Corrected cells use theme colours: redraw them when the theme changes.
        theme.notifier().changed.connect(self._reload_current)

        self._client.practices_updated.connect(self._on_practices_updated)
        if self._client.recovered_jobs:
            with QtCore.QSignalBlocker(self.job_combo):
                for job_id in self._client.recovered_jobs:
                    self._ensure_job_item(job_id)
                self.job_combo.setCurrentIndex(self.job_combo.count() - 1)
            self._on_job_index_changed(self.job_combo.currentIndex())

    # ------------------------------------------------------------------ UI setup

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
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
        search_action = self.search_box.addAction(
            icons.icon("search", theme.current_tokens().text_muted, 16), QLineEdit.ActionPosition.LeadingPosition
        )
        icons.bind_icon(search_action, "search", "text_muted", 16)
        self.search_box.textChanged.connect(self._apply_filter)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+F"), self, activated=self._focus_search)

        refresh_btn = QPushButton(self)
        icons.bind_icon(refresh_btn, "refresh-cw", "text", 18)
        refresh_btn.setToolTip("Ricarica l'elenco delle sessioni e la tabella")
        refresh_btn.setAccessibleName("Ricarica")
        refresh_btn.clicked.connect(self._refresh)

        self.export_button = QPushButton("Esporta Excel", self)
        self.export_button.setProperty("primary", True)
        icons.bind_icon(self.export_button, "download", "on_primary", 18)
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

        self.save_status = QLabel(self)
        self.save_status.setProperty("muted", True)
        self.save_status.hide()
        layout.addWidget(self.save_status)
        self.edit_error = QLabel(self)
        self.edit_error.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.edit_error.setWordWrap(True)
        self.edit_error.hide()
        layout.addWidget(self.edit_error)

        self.draft_bar = QWidget(self)
        draft_layout = QHBoxLayout(self.draft_bar)
        draft_layout.setContentsMargins(0, 0, 0, 0)
        self.draft_label = QLabel(self.draft_bar)
        self.draft_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.draft_label.setWordWrap(True)
        draft_layout.addWidget(self.draft_label, stretch=1)
        self.resume_draft_button = QPushButton("Riprendi modifica", self.draft_bar)
        self.resume_draft_button.clicked.connect(self._resume_draft)
        draft_layout.addWidget(self.resume_draft_button)
        discard = QPushButton("Scarta bozza", self.draft_bar)
        discard.clicked.connect(lambda: self._discard_draft(self._current_job_id))
        draft_layout.addWidget(discard)
        self.draft_bar.hide()
        layout.addWidget(self.draft_bar)

        # NDG and denominazione stay in view while the other 43 columns scroll.
        self.table = FrozenColumnsTable(frozen_count=2, parent=self)
        # Double click, F2 or typing corrects a cell; the NDG, the page band and rows
        # without an NDG are not editable (per-cell flag, see _set_cell).
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setToolTip("Doppio click su un'intestazione per rinominare la colonna")
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._on_item_changed)
        # The two views (scrolling and frozen) behave the same way.
        frozen = self.table.frozen_view
        for view in (self.table, frozen):
            if self._client.has_recovery:
                view.setItemDelegate(_DraftDelegate(self, view))
            view.horizontalHeader().sectionDoubleClicked.connect(self._on_header_double_clicked)
            view.itemDelegate().closeEditor.connect(self._on_editor_closed)
            view.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        frozen.customContextMenuRequested.connect(self._on_frozen_context_menu)

        # Empty state: says what to do instead of showing a grid with no rows.
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

    def _on_practices_updated(self, job_id: str) -> None:
        # Adding the first combo item also selects it. Defer that first render
        # just like subsequent results so one burst only needs one snapshot.
        if self._current_job_id is None:
            with QtCore.QSignalBlocker(self.job_combo):
                self._select_job(job_id)
            self._current_job_id = job_id
        else:
            self._ensure_job_item(job_id)
        if job_id == self._current_job_id:
            self._reload_pending = True
            if self.isVisible() and not self._result_timer.isActive():
                self._result_timer.start(0)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if self._reload_pending:
            self._result_timer.start(0)

    def _flush_results(self) -> None:
        if self.isVisible() and self._reload_pending and self._current_job_id:
            self._load_table(self._current_job_id, results_only=True)

    def _on_job_index_changed(self, index: int) -> None:
        job_id = self.job_combo.itemData(index) if index >= 0 else None
        if job_id != self._current_job_id:
            self.leave_draft_open()
            if not self.has_pending_writes():
                self.save_status.hide()
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
        if not ok:
            return
        # An empty name restores the canonical one.
        self._apply_column_label(column.schema_key, new_label)

    def _apply_column_label(self, schema_key: str, label: str) -> None:
        if self._client.has_recovery:
            self._queue_write(_EditWrite("rename", None, partial(self._client.set_column_label, schema_key, label)))
            return
        try:
            self._client.set_column_label(schema_key, label)
        except OSError as exc:
            self._show_edit_error(exc)
            return
        # L'ordine non dipende dalle label (build_columns ordina sui display_name
        # canonici), quindi rinominare non fa saltare le colonne.
        self._columns = build_columns(self._client.get_column_labels())
        self._refresh_headers()

    def _apply_filter(self, *_args: object) -> None:
        needle = self.search_box.text().strip().casefold()
        for offset, record in enumerate(self._records):
            self._filter_row(_FIRST_DATA_ROW + offset, record, needle)

    def _filter_row(self, row: int, record: PracticeRecord, needle: str) -> None:
        # Search the displayed identifiers and the normalized NDG.
        shown_ndg = record.fields["ndg"]["value"] or ""
        searchable = f"{shown_ndg} {record.denominazione or ''} {record.ndg or ''} {record.practice_number or ''}".casefold()
        self.table.setRowHidden(row, bool(needle) and needle not in searchable)

    # ------------------------------------------------------------------ Table population

    def _clear_table(self) -> None:
        self._records = ()
        self._refresh_draft()
        self.table.clearContents()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.table.sync_frozen_columns()
        self.stack.setCurrentWidget(self.empty_state)

    def _load_table(self, job_id: str, *, results_only: bool = False) -> None:
        # A new result must not pull the open editor away: reload as soon as the
        # operator is done (see _on_editor_closed).
        if self.table.is_editing():
            self._reload_pending = True
            return
        self._reload_pending = False

        previous = self._records if results_only else ()
        self._records = self._client.get_practices(job_id)
        if not self._records:
            self._clear_table()
            return

        self._loading = True
        try:
            first_load = self.table.columnCount() == 0
            self.table.setColumnCount(len(self._columns))
            self.table.setRowCount(_FIRST_DATA_ROW + len(self._records))

            if first_load:
                self.table.clearSpans()
                self._refresh_headers()
                self._paint_band_row()

            needle = self.search_box.text().strip().casefold()
            for row_offset, record in enumerate(self._records):
                if row_offset < len(previous):
                    old = previous[row_offset]
                    if old is record or (old.edit_key == record.edit_key and old.fields == record.fields):
                        continue
                row = _FIRST_DATA_ROW + row_offset
                for col_idx, column in enumerate(self._columns):
                    self._set_cell(row, col_idx, record, column)
                self._filter_row(row, record, needle)
            if first_load:
                self.table.sync_frozen_columns()
        finally:
            self._loading = False

        self.stack.setCurrentWidget(self.table)
        self._refresh_draft()

    def _reload_current(self) -> None:
        if self._current_job_id:
            self._load_table(self._current_job_id)

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

    def _set_cell(self, row: int, col: int, record: PracticeRecord, column: ColumnSpec) -> None:
        field = record.fields.get(column.schema_key) or {}
        value = field.get("value")
        item = QTableWidgetItem("" if value is None else str(value))
        if is_correctable(record, column.schema_key):
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)
        else:
            item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        if field.get("corrected"):
            # Marked with background, icon and tooltip: never colour alone.
            tokens = theme.current_tokens()
            original = field.get("original_value")
            shown = "(vuoto)" if original is None or str(original).strip() == "" else str(original)
            item.setData(CORRECTED_ROLE, True)
            item.setBackground(QBrush(QColor(tokens.corrected_bg)))
            item.setForeground(QBrush(QColor(tokens.text)))
            item.setIcon(icons.icon("pencil", tokens.corrected_icon, 14))
            item.setToolTip(f"Valore originale: {shown}")
        if column.schema_key == "ndg" and record.practice_number:
            item.setToolTip(f"Numero pratica {record.practice_number}")
        self.table.setItem(row, col, item)

    # ------------------------------------------------------------------ Correzioni

    def _show_edit_error(self, exc: OSError | str) -> None:
        self.edit_error.setText(f"Modifica non salvata. {exc}")
        self.edit_error.show()

    def has_pending_writes(self) -> bool:
        return self._active_write is not None

    def _queue_write(self, request: _EditWrite) -> None:
        if self.has_pending_writes():
            # Text supersedes earlier unsent text for this editor only. Confirm
            # and discard are ordered barriers and must never be coalesced.
            if request.action == "draft" and self._queued_writes:
                last = self._queued_writes[-1]
                if last.action == "draft" and last.editor_id == request.editor_id:
                    self._queued_writes.pop()
            self._queued_writes.append(request)
            return
        self.last_write_failed = False
        self.edit_error.hide()
        self.save_status.setText("Salvataggio…")
        self.save_status.show()
        self.draft_bar.hide()
        self._start_write(request)
        self.writes_pending_changed.emit(True)

    def _start_write(self, request: _EditWrite) -> None:
        task = _WriteTask(request)
        task.result.finished.connect(self._on_write_finished, QtCore.Qt.ConnectionType.QueuedConnection)
        self._active_write = task
        QtCore.QThreadPool.globalInstance().start(task)

    @QtCore.pyqtSlot(object, str)
    def _on_write_finished(self, request: _EditWrite, error: str) -> None:
        for view in (self.table, self.table.frozen_view):
            delegate = view.itemDelegate()
            editor = delegate.editor if isinstance(delegate, _DraftDelegate) else None
            if editor is not None and id(editor) == request.editor_id:
                if error:
                    editor.setText(editor.property("savedText"))
                    editor.setReadOnly(True)
                else:
                    editor.setProperty("savedText", request.text)
        if error:
            self.last_write_failed = True
            self._queued_writes.clear()
            self.save_status.hide()
            self._show_edit_error(error)
        elif request.action == "rename":
            self._columns = build_columns(self._client.get_column_labels())
            self._refresh_headers()
        elif request.action == "confirm" and request.job == self._current_job_id:
            self._reload_current()
        if self._queued_writes:
            self._start_write(self._queued_writes.popleft())
            return
        self._active_write = None
        if not error:
            labels = {"draft": "Bozza salvata.", "discard": "Bozza scartata."}
            self.save_status.setText(labels.get(request.action, "Modifica salvata."))
            self.save_status.setVisible(request.job is None or request.job == self._current_job_id)
        self._refresh_draft()
        self.writes_pending_changed.emit(False)

    def _refresh_draft(self) -> None:
        job_id = self._current_job_id
        draft = self._client.get_cell_draft(job_id) if job_id and self._client.has_recovery else None
        if not draft or self.table.is_editing() or self.has_pending_writes():
            self.draft_bar.hide()
            return
        column = next((c for c in self._columns if c.schema_key == draft["key"]), None)
        label = column.label if column else draft["key"]
        target = draft["ndg"]
        identity = f"pratica {target[4:]}" if target.startswith("pef:") else f"NDG {target}"
        self.draft_label.setText(
            f"Bozza per {label} · {identity}. Conferma la modifica per includerla nell’esportazione."
        )
        self.resume_draft_button.setEnabled(
            column is not None and any(record.edit_key == draft["ndg"] for record in self._records)
        )
        self.draft_bar.show()

    def _resume_draft(self) -> None:
        if not self._current_job_id:
            return
        draft = self._client.get_cell_draft(self._current_job_id)
        if draft:
            col = next(i for i, c in enumerate(self._columns) if c.schema_key == draft["key"])
            for row, record in enumerate(self._records, _FIRST_DATA_ROW):
                if record.edit_key == draft["ndg"]:
                    if self.table.isRowHidden(row):
                        self.search_box.clear()
                    item = self.table.item(row, col)
                    self.table.setCurrentItem(item)
                    self.table.scrollToItem(item)
                    self.table.editItem(item)
                    break

    def _discard_draft(self, job_id: Optional[str]) -> None:
        if job_id:
            self._queue_write(_EditWrite("discard", job_id, partial(self._client.clear_cell_draft, job_id)))

    def _edit_target(self, row: int, col: int) -> Optional[tuple[str, str, str, Optional[str]]]:
        index = row - _FIRST_DATA_ROW
        job_id = self._current_job_id
        if not job_id or not 0 <= index < len(self._records) or not 0 <= col < len(self._columns):
            return None
        record, key = self._records[index], self._columns[col].schema_key
        if not record.ndg or not is_correctable(record, key):
            return None
        field = record.fields[key]
        original = field["original_value"] if field.get("corrected") else field["value"]
        return job_id, record.edit_key, key, None if original is None else str(original)

    def _commit_text(self, job_id: str, ndg: str, key: str, original: Optional[str], text: str) -> None:
        typed = clean_correction(text)
        if typed == clean_correction(original):
            save = partial(self._client.clear_correction, job_id, ndg, key)
        else:
            save = partial(self._client.set_correction, job_id, ndg, key, typed)
        if self._client.has_recovery:
            self._queue_write(_EditWrite("confirm", job_id, save))
            return
        try:
            save()
        except OSError as exc:
            self._show_edit_error(exc)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        target = self._edit_target(item.row(), item.column())
        if target:
            self._commit_text(*target, item.text())
        # Also for a cell that is not correctable: redraw from the real state.
        QtCore.QTimer.singleShot(0, self._reload_current)

    def _on_editor_closed(self, *_args: object) -> None:
        if self._reload_pending:
            QtCore.QTimer.singleShot(0, self._reload_current)
        else:
            QtCore.QTimer.singleShot(0, self._refresh_draft)

    def _restore_original(self, row: int, col: int) -> None:
        index = row - _FIRST_DATA_ROW
        job_id = self._current_job_id
        if not job_id or not 0 <= index < len(self._records) or not 0 <= col < len(self._columns):
            return
        clear = partial(self._client.clear_correction, job_id, self._records[index].edit_key, self._columns[col].schema_key)
        if self._client.has_recovery:
            self._queue_write(_EditWrite("confirm", job_id, clear))
            return
        try:
            clear()
        except OSError as exc:
            self._show_edit_error(exc)
        self._reload_current()

    def _on_context_menu(self, pos: QtCore.QPoint) -> None:
        self._show_cell_menu(self.table.itemAt(pos), self.table.viewport().mapToGlobal(pos))

    def _on_frozen_context_menu(self, pos: QtCore.QPoint) -> None:
        index = self.table.frozen_view.indexAt(pos)
        item = self.table.item(index.row(), index.column()) if index.isValid() else None
        self._show_cell_menu(item, self.table.frozen_view.viewport().mapToGlobal(pos))

    def _show_cell_menu(self, item: Optional[QTableWidgetItem], global_pos: QtCore.QPoint) -> None:
        if item is None:
            return
        # exec() runs a nested event loop: a frame can land meanwhile and the reload deletes
        # every item, so only plain values read now may be used afterwards.
        row, col = item.row(), item.column()
        menu = QMenu(self)
        restore = menu.addAction("Ripristina originale")
        restore.setEnabled(bool(item.data(CORRECTED_ROLE)))
        if menu.exec(global_pos) is restore:
            self._restore_original(row, col)

    # ------------------------------------------------------------------ Export

    def _on_export_excel(self) -> None:
        self._export.start(self, self._current_job_id)

    @QtCore.pyqtSlot(bool)
    def _update_export_after_edit(self, pending: bool) -> None:
        self._export.set_edits_pending(pending, self.last_write_failed)

    # ------------------------------------------------------------------ Public API

    def leave_draft_open(self) -> None:
        """Close the editor without treating a session change or exit as confirmation."""
        for view in (self.table, self.table.frozen_view):
            delegate = view.itemDelegate()
            if isinstance(delegate, _DraftDelegate) and delegate.editor is not None:
                delegate.closeEditor.emit(delegate.editor, QAbstractItemDelegate.EndEditHint.NoHint)

    def set_job_id(self, job_id: Optional[str]) -> None:
        """Chiamato da MainWindow quando si passa a questa tab."""
        if not job_id:
            return
        self._select_job(job_id)
        if self._reload_pending:
            self._load_table(job_id, results_only=True)
