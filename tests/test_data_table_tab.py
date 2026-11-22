"""Tests for ui/data_table_tab.py (session picker, search, empty state, rename, export)."""

import os
import time
from typing import Any, Iterator

import pytest

pytest.importorskip("PyQt6.QtWidgets")

# Must be set before ui/__init__ pulls in extraction.config (read at import time).
os.environ.setdefault("LLM_API_KEY", "test-key")

from PIL import Image
from PyQt6 import QtWidgets

import local_extraction_client as lec
from ui.data_table_tab import DataTableTab

PRACTICES = {
    "p1": {"ndg": "111", "denominazione": "Alfa Costruzioni S.r.l.", "tipo": "BPI Mutui"},
    "p2": {"ndg": "222", "denominazione": "Beta Servizi S.p.A.", "tipo": "Fido a revoca"},
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
