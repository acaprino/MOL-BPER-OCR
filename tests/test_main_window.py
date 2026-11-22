"""Tests for ui/main_window.py and ui/shell.py (navigation, status header, close dialog)."""

import os
import threading
import time
from typing import Any, Iterator

import pytest

pytest.importorskip("PyQt6.QtWidgets")

# Must be set before ui/__init__ pulls in extraction.config (read at import time).
os.environ.setdefault("LLM_API_KEY", "test-key")

from PIL import Image
from PyQt6 import QtCore
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtTest import QTest

import local_extraction_client as lec
from config import AgentConfig
import ui.capture_tab as capture_tab_module
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


def test_window_effects_are_applied_once_when_the_window_is_first_shown(window: MainWindow, monkeypatch) -> None:
    from ui import win_effects

    applied: list = []
    monkeypatch.setattr(win_effects, "apply_window_effects", lambda win, dark: applied.append((win, dark)) or True)
    window.show()
    window.hide()
    window.show()
    assert len(applied) == 1 and applied[0][0] is window
    window.hide()


# ============================================================
# Final-review fixes: frames in flight, the real capture flow, F9
# ============================================================


class BlockingPipeline:
    """Answers at once, except the page 'slow', which waits until released."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict[str, Any]:
        if screen_id == "slow":
            self.started.set()
            self.release.wait(timeout=5.0)
        fields = {"ndg": {"value": "123", "confidence": 1.0}, "tipo": {"value": "BPI Mutui", "confidence": 1.0}}
        return {"screen_id": screen_id, "fields": fields, "_status": "OK"}


class FakeWorker(QtCore.QObject):
    """The capture boundary (it would grab the real screen): same surface as the real worker."""

    tick = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(Exception)
    llm_debug = QtCore.pyqtSignal(str)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(kwargs.get("parent"))
        self.started = False
        self.stopped = False

    def start_capture(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def wait(self, _ms: int) -> bool:
        return True


@pytest.fixture
def blocking_window(qapp, tmp_path) -> Iterator[tuple[MainWindow, BlockingPipeline]]:
    pipeline = BlockingPipeline()
    client = lec.LocalExtractionClient(pipeline=pipeline)
    win = MainWindow(AgentConfig(config_path=tmp_path / "config.ini"), extraction_client=client)
    yield win, pipeline
    pipeline.release.set()
    client.shutdown()


def test_leave_message_without_unexported_data_still_warns_about_frames_in_flight() -> None:
    message = leave_message([], 3)
    assert "3 frame ancora in elaborazione" in message
    assert "dati non ancora esportati" not in message


def test_close_with_frames_in_flight_asks_even_when_nothing_is_modified(blocking_window) -> None:
    win, pipeline = blocking_window
    client = win.extraction_client
    job = client.start_job()
    client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type="slow")
    assert pipeline.started.wait(5.0)
    assert client.unexported_jobs() == []
    asked: list = []
    win._ask_leave_unexported = lambda labels, pending: asked.append((labels, pending)) or False
    event = QCloseEvent()
    win.closeEvent(event)
    assert not event.isAccepted() and asked == [([], 1)]


def test_close_dialog_counts_a_running_frame_next_to_unexported_data(blocking_window, qapp) -> None:
    win, pipeline = blocking_window
    client = win.extraction_client
    first = _publish_a_practice(win, qapp)
    second = client.start_job()
    client.ingest_frame(second, Image.new("RGB", (10, 10)), page_type="slow")
    assert pipeline.started.wait(5.0)
    asked: list = []
    win._ask_leave_unexported = lambda labels, pending: asked.append((labels, pending)) or False
    win.closeEvent(QCloseEvent())
    assert asked == [([client.session_label(first)], 1)]


def test_header_button_runs_the_real_start_and_stop_flow(window: MainWindow, monkeypatch) -> None:
    monkeypatch.setattr(capture_tab_module, "BPERCaptureWorker", FakeWorker)
    window.config.show_capture_border = False  # no overlay window in the test
    window.header.toggle_button.click()
    worker = window.capture_tab.worker
    assert window.capture_tab.is_running() and worker.started
    assert window.header.toggle_button.text() == "Ferma"
    window.header.toggle_button.click()
    assert not window.capture_tab.is_running() and worker.stopped
    assert window.header.toggle_button.text() == "Avvia"


def test_f9_starts_the_capture(window: MainWindow, monkeypatch, qapp) -> None:
    monkeypatch.setattr(capture_tab_module, "BPERCaptureWorker", FakeWorker)
    window.config.show_capture_border = False
    window.show()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window, 2000)
    qapp.processEvents()
    QTest.keyClick(window, QtCore.Qt.Key.Key_F9)
    assert window.capture_tab.is_running()
    window.capture_tab.stop_capture()
    window.hide()


def _same_colour(a: str, b: str, tolerance: int = 3) -> bool:
    """#RRGGBB equality that forgives the rounding of anti-aliased, premultiplied pixels."""
    return all(abs(int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) <= tolerance for i in (1, 3, 5))


def _solid_color(icon) -> str:
    """Colour of the first strongly opaque pixel of a 16 px icon."""
    image = icon.pixmap(16, 16).toImage()
    for y in range(image.height()):
        for x in range(image.width()):
            colour = image.pixelColor(x, y)
            if colour.alpha() > 200:
                return colour.name()
    raise AssertionError("the icon rendered nothing")


def test_header_icons_follow_a_theme_change(qapp) -> None:
    import theme
    from PyQt6.QtCore import Qt

    theme.apply_theme(qapp, Qt.ColorScheme.Light)
    header = StatusHeader()
    light = _solid_color(header.toggle_button.icon())
    theme.apply_theme(qapp, Qt.ColorScheme.Dark)
    dark = _solid_color(header.toggle_button.icon())
    theme.apply_theme(qapp)
    assert _same_colour(light, theme.LIGHT.on_primary) and _same_colour(dark, theme.DARK.on_primary)


def test_main_window_imports_the_way_the_app_does_not_the_way_the_tests_do(tmp_path) -> None:
    """conftest.py puts src/ on sys.path, which hid an import that only works after another module set it."""
    import subprocess
    import sys
    from pathlib import Path

    edge_agent_dir = Path(__file__).resolve().parent.parent / "src" / "edge-agent"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update({"QT_QPA_PLATFORM": "offscreen", "LLM_API_KEY": "test-key"})
    result = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(edge_agent_dir)!r}); import ui.main_window"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-600:]
