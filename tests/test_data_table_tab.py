"""Tests for ui/data_table_tab.py (session picker, search, empty state, rename, export)."""

import os
import time
from typing import Any, Iterator

import pytest

pytest.importorskip("PyQt6.QtWidgets")

# Must be set before ui/__init__ pulls in extraction.config (read at import time).
os.environ.setdefault("LLM_API_KEY", "test-key")

from PIL import Image
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtTest import QTest

import local_extraction_client as lec
import theme
from excel_export import build_columns
from ui.data_table_tab import CORRECTED_ROLE, DataTableTab

PRACTICES = {
    "p1": {"ndg": "111", "denominazione": "Alfa Costruzioni S.r.l.", "tipo": "BPI Mutui"},
    "p2": {"ndg": "222", "denominazione": "Beta Servizi S.p.A.", "tipo": "Fido a revoca"},
    "p3": {"tipo": "Senza NDG"},                      # a session that never reads the NDG
    "p4": {"ndg": "111", "tipo": "Altro tipo"},       # a later frame of the first practice
    "p5": {"ndg": "012.345/A", "denominazione": "Delta Edilizia S.r.l."},  # NDG with separators
}


class ScriptedPipeline:
    """The extraction boundary: one invented practice per page type."""

    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict[str, Any]:
        fields = {k: {"value": v, "confidence": 1.0} for k, v in PRACTICES[screen_id].items()}
        return {"screen_id": screen_id, "fields": fields, "_status": "OK"}


@pytest.fixture
def client() -> Iterator[lec.LocalExtractionClient]:
    instance = lec.LocalExtractionClient(pipeline=ScriptedPipeline())
    yield instance
    instance.shutdown()


@pytest.fixture
def tab(qapp, client) -> DataTableTab:
    return DataTableTab(extraction_client=client)


def _publish(client: lec.LocalExtractionClient, qapp, *pages: str) -> str:
    job = client.start_job()
    for page in pages:
        client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type=page)
    deadline = time.time() + 5
    while len(client.get_results(job)) < len(pages) and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    assert len(client.get_results(job)) == len(pages), "the fake pipeline never answered"
    return job


def test_empty_state_is_shown_until_a_practice_exists(tab: DataTableTab, client, qapp) -> None:
    assert tab.stack.currentWidget() is tab.empty_state
    job = _publish(client, qapp, "p1")
    tab.set_job_id(job)
    assert tab.stack.currentWidget() is tab.table


def test_session_picker_shows_labels_and_keeps_job_ids_as_data(tab: DataTableTab, client, qapp) -> None:
    job = _publish(client, qapp, "p1")
    tab.set_job_id(job)
    assert tab.job_combo.itemText(0) == client.session_label(job)
    assert tab.job_combo.itemData(0) == job


def test_search_hides_rows_that_do_not_match_ndg_or_denominazione(tab: DataTableTab, client, qapp) -> None:
    tab.set_job_id(_publish(client, qapp, "p1", "p2"))
    first, second = 1, 2  # row 0 is the page band
    tab.search_box.setText("BETA")
    assert (tab.table.isRowHidden(first), tab.table.isRowHidden(second), tab.table.isRowHidden(0)) == (True, False, False)
    tab.search_box.setText("111")
    assert (tab.table.isRowHidden(first), tab.table.isRowHidden(second)) == (False, True)
    tab.search_box.setText("")
    assert (tab.table.isRowHidden(first), tab.table.isRowHidden(second)) == (False, False)


def test_renaming_a_column_updates_the_shared_labels_for_every_export(tab: DataTableTab, client, qapp) -> None:
    tab.set_job_id(_publish(client, qapp, "p1"))
    tab._apply_column_label("tipo", "Tipo pratica")
    assert client.get_column_labels() == {"tipo": "Tipo pratica"}
    column = [c.schema_key for c in tab._columns].index("tipo")
    assert tab.table.horizontalHeaderItem(column).text() == "Tipo pratica"


def test_export_goes_through_the_clients_single_export_path(tab: DataTableTab, client, qapp, tmp_path, monkeypatch) -> None:
    job = _publish(client, qapp, "p1")
    tab.set_job_id(job)
    target = tmp_path / "out.xlsx"
    # The two dialogs are the genuine boundary: the real export path runs.
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", staticmethod(lambda *a, **k: None))
    assert client.unexported_jobs() == [job]
    tab._on_export_excel()
    assert target.is_file() and client.unexported_jobs() == []


# ============================================================
# Correcting values
# ============================================================


def _locate(tab: DataTableTab, ndg: str, key: str) -> tuple[int, int]:
    """(row, column) of a practice's field in the table."""
    row = 1 + [r.ndg for r in tab._records].index(ndg)
    return row, [c.schema_key for c in tab._columns].index(key)


def _edit(tab: DataTableTab, qapp, ndg: str, key: str, text: str) -> None:
    """Type `text` in a cell the way a committed edit does, then let the reload run."""
    row, col = _locate(tab, ndg, key)
    tab.table.item(row, col).setText(text)
    qapp.processEvents()


def test_editing_a_cell_stores_a_correction_and_marks_it(tab: DataTableTab, client, qapp) -> None:
    job = _publish(client, qapp, "p1", "p2")
    tab.set_job_id(job)
    _edit(tab, qapp, "111", "tipo", "Mutuo")
    assert client.get_corrections(job) == {"111": {"tipo": "Mutuo"}}
    item = tab.table.item(*_locate(tab, "111", "tipo"))
    assert item.text() == "Mutuo" and item.data(CORRECTED_ROLE) is True
    assert item.toolTip() == "Valore originale: BPI Mutui"
    other = tab.table.item(*_locate(tab, "222", "tipo"))
    assert other.data(CORRECTED_ROLE) is None


def test_ndg_band_row_and_rows_without_ndg_are_not_editable(tab: DataTableTab, client, qapp) -> None:
    tab.set_job_id(_publish(client, qapp, "p1"))
    editable = QtCore.Qt.ItemFlag.ItemIsEditable
    assert not tab.table.item(*_locate(tab, "111", "ndg")).flags() & editable
    assert not tab.table.item(0, 0).flags() & editable
    assert tab.table.item(*_locate(tab, "111", "tipo")).flags() & editable
    tab.set_job_id(_publish(client, qapp, "p3"))
    anonymous = tab.table.item(1, [c.schema_key for c in tab._columns].index("tipo"))
    assert not anonymous.flags() & editable


def test_typing_the_extracted_value_does_not_create_a_correction(tab: DataTableTab, client, qapp) -> None:
    job = _publish(client, qapp, "p1")
    tab.set_job_id(job)
    _edit(tab, qapp, "111", "tipo", "BPI Mutui")
    assert client.get_corrections(job) == {}
    assert tab.table.item(*_locate(tab, "111", "tipo")).data(CORRECTED_ROLE) is None


def test_typing_the_original_back_removes_the_correction(tab: DataTableTab, client, qapp) -> None:
    job = _publish(client, qapp, "p1")
    tab.set_job_id(job)
    _edit(tab, qapp, "111", "tipo", "Mutuo")
    _edit(tab, qapp, "111", "tipo", "BPI Mutui")
    assert client.get_corrections(job) == {}


def test_clearing_the_text_stores_an_empty_correction(tab: DataTableTab, client, qapp) -> None:
    job = _publish(client, qapp, "p1")
    tab.set_job_id(job)
    _edit(tab, qapp, "111", "tipo", "")
    assert client.get_corrections(job) == {"111": {"tipo": None}}
    item = tab.table.item(*_locate(tab, "111", "tipo"))
    assert item.text() == "" and item.data(CORRECTED_ROLE) is True


def test_correction_survives_a_new_result_for_the_same_practice(tab: DataTableTab, client, qapp) -> None:
    job = _publish(client, qapp, "p1")
    tab.set_job_id(job)
    _edit(tab, qapp, "111", "tipo", "Mutuo")
    client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type="p4")
    deadline = time.time() + 5
    while len(client.get_results(job)) < 2 and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    item = tab.table.item(*_locate(tab, "111", "tipo"))
    assert item.text() == "Mutuo" and item.data(CORRECTED_ROLE) is True


def test_restore_original_removes_the_correction(tab: DataTableTab, client, qapp) -> None:
    job = _publish(client, qapp, "p1")
    tab.set_job_id(job)
    _edit(tab, qapp, "111", "tipo", "Mutuo")
    row, col = _locate(tab, "111", "tipo")
    tab._restore_original(row, col)
    qapp.processEvents()
    assert client.get_corrections(job) == {}
    assert tab.table.item(row, col).text() == "BPI Mutui"


def test_result_arriving_while_an_editor_is_open_keeps_the_editor(tab: DataTableTab, client, qapp) -> None:
    job = _publish(client, qapp, "p1")
    tab.set_job_id(job)
    tab.show()
    qapp.processEvents()
    row, col = _locate(tab, "111", "tipo")
    tab.table.editItem(tab.table.item(row, col))
    editor = tab.table.viewport().findChild(QtWidgets.QLineEdit)
    assert editor is not None
    editor.setText("Mutu")

    client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type="p4")
    deadline = time.time() + 5
    while len(client.get_results(job)) < 2 and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    assert tab.table.state() == QtWidgets.QAbstractItemView.State.EditingState
    assert editor.text() == "Mutu"

    QTest.keyClicks(editor, "o")
    QTest.keyClick(editor, QtCore.Qt.Key.Key_Return)
    qapp.processEvents()
    assert client.get_corrections(job) == {"111": {"tipo": "Mutuo"}}
    assert tab.table.item(row, col).text() == "Mutuo"


def test_editing_a_frozen_column_stores_a_correction_and_defers_reloads(tab: DataTableTab, client, qapp) -> None:
    job = _publish(client, qapp, "p1")
    tab.set_job_id(job)
    tab.show()
    qapp.processEvents()
    row, col = _locate(tab, "111", "denominazione")
    tab.table.frozen_view.edit(tab.table.model().index(row, col))
    editor = tab.table.frozen_view.viewport().findChild(QtWidgets.QLineEdit)
    assert editor is not None and tab.table.is_editing()
    editor.setText("Alfa Costruzioni 2")

    client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type="p4")  # a result arrives meanwhile
    deadline = time.time() + 5
    while len(client.get_results(job)) < 2 and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    assert tab.table.is_editing() and editor.text() == "Alfa Costruzioni 2"

    QTest.keyClick(editor, QtCore.Qt.Key.Key_Return)
    qapp.processEvents()
    assert client.get_corrections(job) == {"111": {"denominazione": "Alfa Costruzioni 2"}}
    assert tab.table.item(row, col).text() == "Alfa Costruzioni 2"


def test_corrected_cells_follow_a_theme_change(tab: DataTableTab, client, qapp) -> None:
    from PyQt6.QtCore import Qt

    theme.apply_theme(qapp, Qt.ColorScheme.Light)
    job = _publish(client, qapp, "p1")
    tab.set_job_id(job)
    _edit(tab, qapp, "111", "tipo", "Mutuo")
    row, col = _locate(tab, "111", "tipo")
    assert tab.table.item(row, col).background().color().name() == theme.LIGHT.corrected_bg.lower()
    theme.apply_theme(qapp, Qt.ColorScheme.Dark)
    qapp.processEvents()
    try:
        assert tab.table.item(row, col).background().color().name() == theme.DARK.corrected_bg.lower()
    finally:
        theme.apply_theme(qapp)


# ============================================================
# Second code review
# ============================================================


class BrokenPipeline:
    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict[str, Any]:
        raise RuntimeError("VLM down")


def test_search_finds_the_ndg_as_it_is_shown(tab: DataTableTab, client, qapp) -> None:
    tab.set_job_id(_publish(client, qapp, "p5", "p2"))
    for needle in ("012.345/A", "345/A", "12345a"):
        tab.search_box.setText(needle)
        assert not tab.table.isRowHidden(1), needle
    tab.search_box.setText("zzz")
    assert tab.table.isRowHidden(1)


def test_the_context_menu_survives_a_reload_while_it_is_open(tab: DataTableTab, client, qapp, monkeypatch) -> None:
    job = _publish(client, qapp, "p1")
    tab.set_job_id(job)
    _edit(tab, qapp, "111", "tipo", "Mutuo")
    item = tab.table.item(*_locate(tab, "111", "tipo"))

    def exec_while_a_frame_lands(menu, *args, **kwargs):
        tab._load_table(job)  # a frame finished: every item is replaced and the old ones deleted
        return menu.actions()[0]

    monkeypatch.setattr(QtWidgets.QMenu, "exec", exec_while_a_frame_lands)
    tab._show_cell_menu(item, QtCore.QPoint(0, 0))
    qapp.processEvents()
    assert client.get_corrections(job) == {}


def test_a_session_of_errors_only_shows_the_empty_state(qapp) -> None:
    client = lec.LocalExtractionClient(pipeline=BrokenPipeline())
    tab = DataTableTab(extraction_client=client)
    job = client.start_job()
    client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type="p1")
    deadline = time.time() + 5
    while not client.get_results(job) and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    tab.set_job_id(job)
    assert tab.stack.currentWidget() is tab.empty_state
    client.shutdown()


def test_clearing_a_column_name_restores_the_canonical_one(tab: DataTableTab, client, qapp, monkeypatch) -> None:
    tab.set_job_id(_publish(client, qapp, "p1"))
    tab._apply_column_label("tipo", "Tipo pratica")
    col = [c.schema_key for c in tab._columns].index("tipo")
    canonical = next(c.label for c in build_columns() if c.schema_key == "tipo")
    monkeypatch.setattr(QtWidgets.QInputDialog, "getText", staticmethod(lambda *a, **k: ("", True)))
    tab._on_header_double_clicked(col)
    assert client.get_column_labels() == {}
    assert tab.table.horizontalHeaderItem(col).text() == canonical
