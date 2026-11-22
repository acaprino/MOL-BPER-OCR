"""Tests for ui/frozen_table.py (a table whose first columns stay put while scrolling sideways)."""

import os

import pytest

pytest.importorskip("PyQt6.QtWidgets")

# Must be set before ui/__init__ pulls in extraction.config (read at import time).
os.environ.setdefault("LLM_API_KEY", "test-key")

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QTableWidgetItem

from ui.frozen_table import FrozenColumnsTable

ROWS, COLUMNS = 40, 8


@pytest.fixture
def table(qapp) -> FrozenColumnsTable:
    widget = FrozenColumnsTable(frozen_count=2)
    widget.setColumnCount(COLUMNS)
    widget.setRowCount(ROWS)
    for row in range(ROWS):
        for col in range(COLUMNS):
            widget.setItem(row, col, QTableWidgetItem(f"r{row}c{col}"))
    widget.sync_frozen_columns()
    widget.resize(360, 220)
    widget.show()
    qapp.processEvents()
    return widget


def test_frozen_view_shows_only_the_first_columns(table: FrozenColumnsTable) -> None:
    shown = [col for col in range(COLUMNS) if not table.frozen_view.isColumnHidden(col)]
    assert shown == [0, 1]


def test_vertical_scroll_stays_in_sync_both_ways(table: FrozenColumnsTable, qapp) -> None:
    table.verticalScrollBar().setValue(120)
    qapp.processEvents()
    assert table.frozen_view.verticalScrollBar().value() == table.verticalScrollBar().value() > 0
    table.frozen_view.verticalScrollBar().setValue(60)
    qapp.processEvents()
    assert table.verticalScrollBar().value() == table.frozen_view.verticalScrollBar().value() == 60


def test_selecting_a_row_selects_it_in_both_views(table: FrozenColumnsTable) -> None:
    table.selectRow(3)
    assert table.frozen_view.selectionModel().isRowSelected(3)


def test_horizontal_scroll_does_not_move_the_frozen_columns(table: FrozenColumnsTable, qapp) -> None:
    before = table.frozen_view.geometry()
    table.horizontalScrollBar().setValue(table.horizontalScrollBar().maximum())
    qapp.processEvents()
    assert table.horizontalScrollBar().value() > 0
    assert table.frozen_view.geometry() == before


def test_hiding_a_row_hides_it_in_both_views(table: FrozenColumnsTable) -> None:
    table.setRowHidden(4, True)
    assert table.frozen_view.isRowHidden(4)
    table.setRowHidden(4, False)
    assert not table.frozen_view.isRowHidden(4)


def test_is_editing_covers_the_frozen_view(table: FrozenColumnsTable) -> None:
    assert not table.is_editing()
    table.frozen_view.edit(table.model().index(2, 1))
    assert table.is_editing()


def test_keyboard_edit_of_a_frozen_cell_opens_the_editor_in_the_frozen_view(table: FrozenColumnsTable, qapp) -> None:
    table.setCurrentCell(2, 1)
    table.setFocus()
    qapp.processEvents()
    QTest.keyClick(table, QtCore.Qt.Key.Key_F2)
    assert table.frozen_view.state() == QtWidgets.QAbstractItemView.State.EditingState
    assert table.frozen_view.viewport().findChild(QtWidgets.QLineEdit) is not None


def test_arrow_keys_never_park_the_current_cell_under_the_frozen_columns(table: FrozenColumnsTable, qapp) -> None:
    table.horizontalScrollBar().setValue(table.horizontalScrollBar().maximum())
    qapp.processEvents()
    table.setCurrentCell(2, 1)
    table.setFocus()
    qapp.processEvents()
    QTest.keyClick(table, QtCore.Qt.Key.Key_Right)
    qapp.processEvents()
    index = table.currentIndex()
    assert index.column() == 2
    assert table.visualRect(index).left() >= table._frozen_width()


def test_moving_left_never_parks_the_current_cell_under_the_frozen_columns(table: FrozenColumnsTable, qapp) -> None:
    frozen = table._frozen_width()
    # scroll so that column 3 starts 30 px behind the frozen view
    unscrolled_left = sum(table.columnWidth(col) for col in range(3))
    table.horizontalScrollBar().setValue(unscrolled_left - frozen + 30)
    qapp.processEvents()
    table.setCurrentCell(2, 4)
    table.setFocus()
    qapp.processEvents()
    QTest.keyClick(table, QtCore.Qt.Key.Key_Left)
    qapp.processEvents()
    index = table.currentIndex()
    assert index.column() == 3
    assert table.visualRect(index).left() >= frozen
