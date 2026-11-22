"""Tests for ui/main_window.py and ui/shell.py (navigation, status header, close dialog)."""

import os
import time
from typing import Any, Iterator

import pytest

pytest.importorskip("PyQt6.QtWidgets")

# Must be set before ui/__init__ pulls in extraction.config (read at import time).
os.environ.setdefault("LLM_API_KEY", "test-key")

from PIL import Image
from PyQt6.QtGui import QCloseEvent

import local_extraction_client as lec
from config import AgentConfig
from ui.main_window import MainWindow, leave_message
from ui.shell import StatusHeader


class ScriptedPipeline:
    """The extraction boundary: one practice with a type, whatever the page."""

    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict[str, Any]:
        fields = {"ndg": {"value": "123", "confidence": 1.0}, "tipo": {"value": "BPI Mutui", "confidence": 1.0}}
        return {"screen_id": screen_id, "fields": fields, "_status": "OK"}


@pytest.fixture
def window(qapp, tmp_path) -> Iterator[MainWindow]:
    client = lec.LocalExtractionClient(pipeline=ScriptedPipeline())
    win = MainWindow(AgentConfig(config_path=tmp_path / "config.ini"), extraction_client=client)
    yield win
    client.shutdown()


def _publish_a_practice(win: MainWindow, qapp) -> str:
    client = win.extraction_client
    job = client.start_job()
    client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type="p1")
    deadline = time.time() + 5
    while not client.get_results(job) and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert client.get_results(job), "the fake pipeline never answered"
    return job


def test_status_header_labels_follow_state(qapp) -> None:
    header = StatusHeader()
    assert header.toggle_button.text() == "Avvia"
    header.set_running(True)
    assert header.toggle_button.text() == "Ferma"
    assert "in corso" in header.state_label.text()
    header.set_counters(12, 12, 3)
    assert header.counters_label.text() == "12 elaborati su 12 · 3 pratiche"


def test_leave_message_mentions_frames_still_processing_and_every_session() -> None:
    message = leave_message(["Sessione 1 · 10:42", "Sessione 2 · 11:05"], 2)
    assert "2 frame ancora in elaborazione" in message
    assert "Sessione 1 · 10:42" in message and "Sessione 2 · 11:05" in message
    assert "ancora in elaborazione" not in leave_message(["Sessione 1 · 10:42"], 0)


def test_close_without_unexported_data_accepts_without_asking(window: MainWindow) -> None:
    asked: list = []
    window._ask_leave_unexported = lambda labels, pending: asked.append(labels) or True
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted() and asked == []


def test_close_with_unexported_data_and_back_keeps_the_window_open(window: MainWindow, qapp) -> None:
    job = _publish_a_practice(window, qapp)
    asked: list = []
    stopped: list = []
    window._ask_leave_unexported = lambda labels, pending: asked.append((labels, pending)) or False
    window.capture_tab.stop_capture = lambda: stopped.append(1)
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert asked == [([window.extraction_client.session_label(job)], 0)]
    assert stopped == []
    window.extraction_client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type="p1")  # still accepts work


def test_exit_without_exporting_stops_capture_and_shuts_the_client_down(window: MainWindow, qapp) -> None:
    job = _publish_a_practice(window, qapp)
    stopped: list = []
    window._ask_leave_unexported = lambda labels, pending: True
    window.capture_tab.stop_capture = lambda: stopped.append(1)
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted() and stopped == [1]
    with pytest.raises(RuntimeError):
        window.extraction_client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type="p1")


def test_header_button_toggles_capture(window: MainWindow) -> None:
    calls: list = []
    window.capture_tab.start_capture = lambda: calls.append("start")
    window.capture_tab.stop_capture = lambda: calls.append("stop")
    window.capture_tab.is_running = lambda: False
    window.header.toggle_button.click()
    window.capture_tab.is_running = lambda: True
    window.header.toggle_button.click()
    assert calls == ["start", "stop"]


def test_capture_signals_drive_the_header(window: MainWindow) -> None:
    window.capture_tab.running_changed.emit(True)
    assert window.header.toggle_button.text() == "Ferma"
    window.capture_tab.counters_changed.emit(3, 2)
    assert window.header.counters_label.text() == "2 elaborati su 3 · 0 pratiche"


def test_nav_rail_switches_the_visible_page(window: MainWindow) -> None:
    window.nav.set_current(1)
    assert window.stack.currentWidget() is window.data_tab
    window.nav.set_current(0)
    assert window.stack.currentWidget() is window.capture_tab
