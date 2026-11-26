"""Exercise visible queue state through the desktop and the real dispatcher."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PIL import Image
if TYPE_CHECKING:
    from PyQt6 import QtWidgets


class GatedReader:
    def __init__(self) -> None:
        self.release = threading.Event()

    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict:
        if screen_id == "Prima" and not self.release.wait(15):
            raise TimeoutError()
        if screen_id == "Errore":
            raise RuntimeError("sensitive provider detail")
        return {"fields": {"ndg": {"value": "111", "confidence": 1}}, "_status": "OK"}


def wait_for(app: QtWidgets.QApplication, condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 8
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert condition()


@pytest.mark.parametrize(("limit", "later_state"), [(1, "In coda"), (2, "In attesa delle precedenti")])
def test_queue_page_distinguishes_waiting_from_out_of_order_results(
    qapp: QtWidgets.QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    limit: int, later_state: str,
) -> None:
    from PyQt6 import QtWidgets
    from config import AgentConfig
    from local_extraction_client import LocalExtractionClient
    from ui.main_window import MainWindow

    monkeypatch.setenv("EDGE_AGENT_MAX_JOBS", str(limit))
    reader = GatedReader()
    client = LocalExtractionClient(pipeline=reader)
    window = MainWindow(AgentConfig(config_path=tmp_path / "agent.ini"), extraction_client=client)
    try:
        window.show()
        buttons = [b for b in window.findChildren(QtWidgets.QToolButton) if b.text() == "Coda"]
        assert buttons, "The processing queue must be accessible from the navigation rail"
        buttons[0].click()
        table = window.stack.currentWidget().findChild(QtWidgets.QTableView)
        model = table.model()

        def states() -> dict[str, str]:
            return {model.index(row, 2).data(): model.index(row, 3).data()
                    for row in range(model.rowCount())}

        for page in ("Prima", "Note"):
            client.ingest_frame("uno", Image.new("L", (5, 5)), page_type=page)
        wait_for(qapp, lambda: states() == {"Prima": "In lettura", "Note": later_state})
        reader.release.set()
        client.ingest_frame("due", Image.new("L", (5, 5)), page_type="Errore")
        wait_for(qapp, lambda: states() == {
            "Prima": "Elaborata", "Note": "Elaborata", "Errore": "Lettura fallita"})
        assert {model.index(row, 0).data() for row in range(3)} == {
            client.session_label("uno"), client.session_label("due")}
    finally:
        reader.release.set()
        window.hide()
        client.shutdown()
        window.deleteLater()


class HungReader:
    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict:
        if screen_id == "bloccata":
            Path(os.environ["HUNG_READER_STARTED"]).touch()
            threading.Event().wait(30)
        return {"screen_id": screen_id}


def test_queue_keeps_every_open_capture_beyond_the_recent_history_limit(
    qapp: QtWidgets.QApplication, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from local_extraction_client import LocalExtractionClient
    from work_queue import RECENT_LIMIT

    monkeypatch.setenv("EDGE_AGENT_MAX_JOBS", "1")
    reader = GatedReader()
    client = LocalExtractionClient(pipeline=reader)
    try:
        image = Image.new("L", (2, 2))
        for seq in range(RECENT_LIMIT + 5):
            client.ingest_frame("session", image, page_type="Prima" if seq == 0 else "Note")
        active = client.queue_snapshot()
        assert len(active.rows) == RECENT_LIMIT + 5
        reader.release.set()
        wait_for(qapp, lambda: client.frames_in_progress() == 0)
        history = client.queue_snapshot()
        assert len(history.rows) == RECENT_LIMIT
        assert history.rows[0].sequence == RECENT_LIMIT + 4
        assert all(row.state == "done" for row in history.rows)
    finally:
        reader.release.set()
        client.shutdown()


def startup_reader() -> HungReader:
    marker = Path(os.environ["READER_FIRST_START"])
    if not marker.exists():
        marker.touch()
        raise RuntimeError("model temporarily unavailable")
    return HungReader()


def test_next_capture_can_initialize_a_reader_after_startup_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from extraction_service import ExtractionService

    monkeypatch.setenv("READER_FIRST_START", str(tmp_path / "start"))
    service = ExtractionService(1, startup_reader)
    try:
        image = Image.new("L", (5, 5))
        with pytest.raises(RuntimeError, match="temporarily unavailable"):
            service.extract_from_image(image, "prima")
        assert service.extract_from_image(image, "successiva")["screen_id"] == "successiva"
    finally:
        service.close()


def test_queue_restores_page_names_for_pending_and_completed_captures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_edge_backup: Path,
    qapp: QtWidgets.QApplication,
) -> None:
    from local_extraction_client import LocalExtractionClient

    monkeypatch.setenv("EDGE_AGENT_MAX_JOBS", "1")
    reader = GatedReader()
    directory = tmp_path / "recovery"
    source = LocalExtractionClient(pipeline=reader, recovery_dir=directory)
    try:
        for page in ("Elenco", "Prima", "Note"):
            source.ingest_frame("uno", Image.new("L", (5, 5)), page_type=page)
        wait_for(qapp, lambda: source.capture_counts("uno") == (3, 1))
    finally:
        source.shutdown()
        reader.release.set()
    resumed_reader = GatedReader()
    resumed = LocalExtractionClient(pipeline=resumed_reader, recovery_dir=directory)
    try:
        def states() -> dict[str, str]:
            return {row.page: row.state for row in resumed.queue_snapshot().rows}

        wait_for(qapp, lambda: states() == {"Elenco": "done", "Prima": "reading", "Note": "queued"})
        resumed_reader.release.set()
        wait_for(qapp, lambda: all(state == "done" for state in states().values()))
    finally:
        resumed_reader.release.set()
        resumed.shutdown()


def test_unresponsive_reader_releases_its_slot_after_one_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from extraction_service import ExtractionService

    marker = tmp_path / "started"
    monkeypatch.setenv("HUNG_READER_STARTED", str(marker))
    service = ExtractionService(1, HungReader, timeout=2.0)
    retries = []
    image = Image.new("L", (5, 5))
    try:
        assert service.extract_from_image(image, "pronta")["screen_id"] == "pronta"
        with pytest.raises(TimeoutError):
            service.read(image, "bloccata", on_retry=lambda: retries.append(True))
        assert retries == [True] and marker.exists()
        assert service.extract_from_image(image, "successiva")["screen_id"] == "successiva"
    finally:
        service.close()
