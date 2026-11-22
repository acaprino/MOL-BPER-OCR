"""A table whose first columns stay visible while the rest scrolls sideways.

The standard "frozen column" technique: a second view over the same model sits on top
of the left edge of the first one and shows only the first columns. Selection, vertical
scroll, widths and hidden rows are kept in step; what is per view in Qt (spans, hidden
rows) is repeated by hand.
"""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import QAbstractItemView, QTableView, QTableWidget


class FrozenColumnsTable(QTableWidget):
    """QTableWidget whose first `frozen_count` columns do not scroll horizontally."""

    def __init__(self, frozen_count: int = 2, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.frozen_count = frozen_count

        self.frozen_view = QTableView(self)
        self.frozen_view.setObjectName("frozenColumns")
        self.frozen_view.setModel(self.model())
        self.frozen_view.setSelectionModel(self.selectionModel())
        self.frozen_view.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.frozen_view.verticalHeader().hide()
        self.frozen_view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.frozen_view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.frozen_view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.frozen_view.setAlternatingRowColors(True)
        self.viewport().stackUnder(self.frozen_view)

        # Smooth scrolling: with per-item steps the two views would drift apart.
        for view in (self, self.frozen_view):
            view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        self.horizontalHeader().sectionResized.connect(self._on_section_resized)
        self.verticalHeader().sectionResized.connect(self._on_row_resized)
        self.verticalScrollBar().valueChanged.connect(self.frozen_view.verticalScrollBar().setValue)
        self.frozen_view.verticalScrollBar().valueChanged.connect(self.verticalScrollBar().setValue)
        self.frozen_view.show()

    # ------------------------------------------------------------------ Keeping the views in step

    def sync_frozen_columns(self) -> None:
        """Call after the columns or the rows were (re)built."""
        for col in range(self.columnCount()):
            self.frozen_view.setColumnHidden(col, col >= self.frozen_count)
            if col < self.frozen_count:
                self.frozen_view.setColumnWidth(col, self.columnWidth(col))
        # Spans belong to a view: the page band spans the frozen columns here too.
        self.frozen_view.clearSpans()
        if self.rowCount() and self.columnCount() >= self.frozen_count > 1:
            self.frozen_view.setSpan(0, 0, 1, self.frozen_count)
        self.frozen_view.setEditTriggers(self.editTriggers())
        self._update_geometry()

    def _on_section_resized(self, index: int, _old: int, new: int) -> None:
        if index < self.frozen_count:
            self.frozen_view.setColumnWidth(index, new)
            self._update_geometry()

    def _on_row_resized(self, index: int, _old: int, new: int) -> None:
        self.frozen_view.setRowHeight(index, new)

    def _frozen_width(self) -> int:
        return sum(self.columnWidth(col) for col in range(min(self.frozen_count, self.columnCount())))

    def _update_geometry(self) -> None:
        frame = self.frameWidth()
        self.frozen_view.setGeometry(
            self.verticalHeader().width() + frame,
            frame,
            self._frozen_width(),
            self.viewport().height() + self.horizontalHeader().height(),
        )

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._update_geometry()

    # ------------------------------------------------------------------ Per-view state

    def setRowHidden(self, row: int, hide: bool) -> None:  # noqa: N802 - Qt name
        super().setRowHidden(row, hide)
        self.frozen_view.setRowHidden(row, hide)

    def is_editing(self) -> bool:
        """True while a cell editor is open in either view."""
        editing = QAbstractItemView.State.EditingState
        return self.state() == editing or self.frozen_view.state() == editing

    # ------------------------------------------------------------------ Keyboard navigation

    def moveCursor(self, cursor_action, modifiers):  # type: ignore[override]
        current = super().moveCursor(cursor_action, modifiers)
        # Moving left must not park the cursor under the frozen columns.
        if cursor_action == QAbstractItemView.CursorAction.MoveLeft and current.column() >= self.frozen_count:
            left = self.visualRect(current).topLeft().x()
            if left < self._frozen_width():
                bar = self.horizontalScrollBar()
                bar.setValue(bar.value() + left - self._frozen_width())
        return current

    def scrollTo(self, index, hint=QAbstractItemView.ScrollHint.EnsureVisible) -> None:  # type: ignore[override]
        # A frozen cell is always visible: do not scroll sideways for it.
        if index.column() >= self.frozen_count:
            super().scrollTo(index, hint)

    def edit(self, index, trigger=None, event=None):  # type: ignore[override]
        """Open the editor in the view that is on top for that cell.

        A frozen cell is covered by the frozen view: an editor opened here (F2, a
        keystroke) would sit under it, invisible, and still take what the operator
        types. The key that started a typed edit is not forwarded.
        """
        if index.isValid() and index.column() < self.frozen_count and self._wants_edit(index, trigger, event):
            self.frozen_view.edit(index)
            return self.frozen_view.state() == QAbstractItemView.State.EditingState
        if trigger is None:
            return super().edit(index)
        return super().edit(index, trigger, event)

    def _wants_edit(self, index, trigger, event) -> bool:
        """Would this view start an editor for that trigger? (Qt also calls edit() just to ask.)"""
        triggers = QAbstractItemView.EditTrigger
        if not index.flags() & QtCore.Qt.ItemFlag.ItemIsEditable:
            return False
        if trigger is None or trigger == triggers.AllEditTriggers:
            return True
        if trigger == triggers.EditKeyPressed:
            return bool(self.editTriggers() & triggers.EditKeyPressed)
        if trigger == triggers.AnyKeyPressed:
            return bool(self.editTriggers() & triggers.AnyKeyPressed) and event is not None and bool(event.text().strip())
        return False
