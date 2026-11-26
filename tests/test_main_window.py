"""Tests for ui/main_window.py and ui/shell.py (navigation, status header, close dialog)."""

import os
import threading
import time
from typing import Any, Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("isolated_edge_backup")

pytest.importorskip("PyQt6.QtWidgets")

# Must be set before ui/__init__ pulls in extraction.config (read at import time).
os.environ.setdefault("LLM_API_KEY", "test-key")

from PIL import Image
from openpyxl import load_workbook
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtTest import QTest

import local_extraction_client as lec
from config import AgentConfig
import ui.capture_tab as capture_tab_module
from workers.capture import DefaultCaptureWorker
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


def test_reexport_keeps_qt_responsive_until_the_window_can_close(
    window: MainWindow, qapp: QtWidgets.QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _publish_a_practice(window, qapp)
    client = window.extraction_client
    window.capture_tab.job_id = job
    window.data_tab.set_job_id(job)
    client.export_workbook(job, str(tmp_path / "previous.xlsx"))
    assert client.unexported_jobs() == []
    path = tmp_path / "again.xlsx"
    chosen, finished = [], []
    entered, release = threading.Event(), threading.Event()
    fsync = os.fsync

    def hold_file(fd: int) -> None:
        entered.set()
        release.wait(3)
        fsync(fd)

    monkeypatch.setattr(os, "fsync", hold_file)
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName",
                        lambda *_: chosen.append(True) or (str(path), ""))
    monkeypatch.setattr(QtWidgets.QMessageBox, "information",
                        lambda *_: finished.append(threading.current_thread()))
    window.show()
    window.capture_tab.export_button.click()
    try:
        assert entered.wait(3)
        tick = threading.Event()
        QtCore.QTimer.singleShot(0, tick.set)
        qapp.processEvents()
        assert tick.is_set() and not path.exists()
        assert not window.data_tab.export_button.isEnabled()
        window.data_tab.export_button.click()
        assert chosen == [True]
        assert not window.close() and window.isVisible()
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while window.isVisible() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert not window.isVisible()
    assert finished == [threading.main_thread()]
    assert load_workbook(path).active["A3"].value == "123"


def test_gui_export_failure_can_be_retried_from_the_other_tab(
    window: MainWindow, qapp: QtWidgets.QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _publish_a_practice(window, qapp)
    window.capture_tab.job_id = job
    window.data_tab.set_job_id(job)
    destination = tmp_path / "export.xlsx"
    success, failure = [], []
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *_: (str(destination), ""))
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *_: success.append(threading.current_thread()))
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *_: failure.append(threading.current_thread()))

    def locked(src: str, dst: Path) -> None:
        raise PermissionError("workbook in use")

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", locked)
        window.data_tab.export_button.click()
        deadline = time.monotonic() + 5
        while not failure and time.monotonic() < deadline:
            QTest.qWait(10)
    assert failure == [threading.main_thread()] and not destination.exists()
    assert window.extraction_client.unexported_jobs() == [job]
    window.capture_tab.export_button.click()
    deadline = time.monotonic() + 5
    while not success and time.monotonic() < deadline:
        QTest.qWait(10)
    assert success == [threading.main_thread()]
    assert load_workbook(destination).active["A3"].value == "123"


def test_a_correction_arriving_during_gui_export_remains_unexported(
    window: MainWindow, qapp: QtWidgets.QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _publish_a_practice(window, qapp)
    window.data_tab.set_job_id(job)
    target = tmp_path / "before.xlsx"
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    fsync = os.fsync

    def hold_file(fd: int) -> None:
        entered.set()
        release.wait(3)
        fsync(fd)

    monkeypatch.setattr(os, "fsync", hold_file)
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *_: (str(target), ""))
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *_: finished.set())
    window.data_tab.export_button.click()
    try:
        assert entered.wait(3) and not finished.is_set()
        window.extraction_client.set_correction(job, "123", "tipo", "Mutuo")
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while not finished.is_set() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert finished.is_set()
    assert load_workbook(target).active["H3"].value == "BPI Mutui"
    assert window.extraction_client.unexported_jobs() == [job]


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
    navigation_changed = QtCore.pyqtSignal(str, dict)
    finished = QtCore.pyqtSignal()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(kwargs.get("parent"))
        self.started = False
        self.stopped = False

    def start_capture(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True
        self.finished.emit()

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


def test_close_warns_when_a_frame_finishes_during_the_unexported_check(
    blocking_window: tuple[MainWindow, BlockingPipeline], monkeypatch: pytest.MonkeyPatch
) -> None:
    win, pipeline = blocking_window
    client = win.extraction_client
    published = threading.Event()
    client.result_ready.connect(lambda *_: published.set(), QtCore.Qt.ConnectionType.DirectConnection)
    job = client.start_job()
    client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type="slow")
    assert pipeline.started.wait(3)
    unexported_jobs = client.unexported_jobs

    def finish_frame_during_check() -> list[str]:
        before_publication = unexported_jobs()
        pipeline.release.set()
        assert published.wait(3)
        return before_publication

    monkeypatch.setattr(client, "unexported_jobs", finish_frame_during_check)
    asked: list = []
    win._ask_leave_unexported = lambda labels, pending: asked.append((labels, pending)) or False
    event = QCloseEvent()
    win.closeEvent(event)
    assert not event.isAccepted() and asked == [([], 1)]


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


@pytest.fixture
def busy_capture(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> Iterator[threading.Event]:
    """A real capture thread held at the screen-capture boundary."""
    entered = threading.Event()
    release = threading.Event()

    def capture_frame(_worker: DefaultCaptureWorker) -> None:
        entered.set()
        release.wait(3)

    monkeypatch.setattr(DefaultCaptureWorker, "_capture_once", capture_frame)
    window.config.show_capture_border = False
    window.capture_tab.mode_combo.setCurrentIndex(window.capture_tab.mode_combo.findData("default"))
    window.header.toggle_button.click()
    worker = window.capture_tab.worker
    assert entered.wait(3)
    try:
        yield release
    finally:
        release.set()
        if window.capture_tab.worker is worker:
            window.capture_tab.stop_capture()
            worker.wait(3000)


def test_stop_keeps_the_window_interactive_until_capture_finishes(
    window: MainWindow, busy_capture: threading.Event, qapp: QtCore.QCoreApplication
) -> None:
    window.header.toggle_button.click()
    assert window.capture_tab.is_running()
    assert not window.header.toggle_button.isEnabled()
    assert "arresto" in window.header.state_label.text().lower()
    window.nav.set_current(1)
    assert window.stack.currentWidget() is window.data_tab

    busy_capture.set()
    assert window.capture_tab.worker.wait(3000)
    qapp.processEvents()
    assert window.header.toggle_button.isEnabled()
    assert window.header.toggle_button.text() == "Avvia"


def test_capture_that_stops_itself_enables_restart(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, qapp: QtCore.QCoreApplication
) -> None:
    monkeypatch.setattr(DefaultCaptureWorker, "_capture_once", DefaultCaptureWorker.stop)
    window.config.show_capture_border = False
    window.capture_tab.mode_combo.setCurrentIndex(window.capture_tab.mode_combo.findData("default"))
    window.header.toggle_button.click()
    assert window.capture_tab.worker.wait(3000)
    qapp.processEvents()
    assert window.header.toggle_button.text() == "Avvia"
    assert not window.capture_tab.is_running()
    assert window.capture_tab.settings_card.isEnabled()


def test_close_waits_asynchronously_for_capture_after_confirming_once(
    window: MainWindow, busy_capture: threading.Event, qapp: QtCore.QCoreApplication
) -> None:
    job = _publish_a_practice(window, qapp)
    asked: list = []
    window._ask_leave_unexported = lambda labels, pending: asked.append(labels) or True
    window.show()
    assert not window.close()
    assert window.isVisible()
    assert not window.close()
    busy_capture.set()
    assert window.capture_tab.worker.wait(3000)
    qapp.processEvents()
    assert not window.isVisible()
    assert asked == [[window.extraction_client.session_label(job)]]


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
    # OPENBLAS_NUM_THREADS: numpy allocates a buffer per thread, and a busy PC ran out of memory.
    env.update({"QT_QPA_PLATFORM": "offscreen", "LLM_API_KEY": "test-key", "OPENBLAS_NUM_THREADS": "1"})
    result = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(edge_agent_dir)!r}); import ui.main_window"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-600:]


def test_a_destroyed_window_stops_reacting_to_scheme_changes(qapp, tmp_path, monkeypatch) -> None:
    from PyQt6 import sip

    from ui import win_effects

    client = lec.LocalExtractionClient(pipeline=ScriptedPipeline())
    win = MainWindow(AgentConfig(config_path=tmp_path / "config.ini"), extraction_client=client)
    calls: list = []
    monkeypatch.setattr(win_effects, "apply_window_effects", lambda w, dark: calls.append(w) or True)
    sip.delete(win)
    qapp.processEvents()
    qapp.styleHints().colorSchemeChanged.emit(QtCore.Qt.ColorScheme.Dark)
    assert calls == []
    client.shutdown()


@pytest.fixture
def reopened_window(
    qapp: QtCore.QCoreApplication, tmp_path: Path,
) -> Iterator[tuple[MainWindow, list[str]]]:
    recovery_dir = tmp_path / "sessions"
    client = lec.LocalExtractionClient(pipeline=ScriptedPipeline(), recovery_dir=recovery_dir)
    jobs = []
    for _ in range(2):
        job = client.start_job()
        jobs.append(job)
        client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type="p1")
        deadline = time.monotonic() + 5
        while not client.get_results(job) and time.monotonic() < deadline:
            QTest.qWait(5)
        assert client.get_results(job)
    client.shutdown()
    restored = lec.LocalExtractionClient(pipeline=ScriptedPipeline(), recovery_dir=recovery_dir)
    win = MainWindow(AgentConfig(config_path=tmp_path / "config.ini"), extraction_client=restored)
    yield win, jobs
    win.hide()
    restored.shutdown()


def test_reopening_lists_every_session_before_another_capture(reopened_window: tuple[MainWindow, list[str]]) -> None:
    win, jobs = reopened_window
    assert not win.capture_tab.is_running()
    assert win.capture_tab.get_current_job_id() == jobs[-1]
    assert "1 elaborati su 1" in win.header.counters_label.text()
    win.nav.set_current(1)
    combo = win.data_tab.job_combo
    assert [combo.itemData(i) for i in range(combo.count())] == jobs
    for job in jobs:
        combo.setCurrentIndex(combo.findData(job))
        assert win.data_tab.table.item(1, 0).text() == "123"


def test_restart_allows_continuing_an_older_session_or_starting_a_new_one(
    reopened_window: tuple[MainWindow, list[str]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    win, jobs = reopened_window
    monkeypatch.setattr(capture_tab_module, "BPERCaptureWorker", FakeWorker)
    win.config.show_capture_border = False
    combo = win.capture_tab.session_combo
    combo.setCurrentIndex(combo.findData(jobs[0]))
    assert win.header.toggle_button.text() == "Riprendi"
    win.header.toggle_button.click()
    assert win.capture_tab.is_running() and win.capture_tab.get_current_job_id() == jobs[0]
    win.header.toggle_button.click()
    combo.setCurrentIndex(combo.findText("Nuova sessione"))
    win.header.toggle_button.click()
    assert win.capture_tab.is_running() and win.capture_tab.get_current_job_id() not in jobs
    win.header.toggle_button.click()


@pytest.mark.parametrize("fail_commit", [False, True])
def test_export_waits_for_a_confirmation_submitted_while_choosing_the_file(
    reopened_window: tuple[MainWindow, list[str]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    fail_commit: bool,
) -> None:
    win, jobs = reopened_window
    win.nav.set_current(1)
    job = jobs[-1]
    win.data_tab.set_job_id(job)
    win.capture_tab.job_id = job
    store = win.extraction_client._store
    put = store.put
    entered, release = threading.Event(), threading.Event()
    success, errors = [], []
    target = tmp_path / "with-edit.xlsx"

    def slow_commit(key: str, payload: bytes) -> None:
        if key.startswith("edits/"):
            entered.set()
            release.wait(3)
            if fail_commit:
                raise OSError("disk full")
        put(key, payload)

    def choose(*args: object) -> tuple[str, str]:
        # The native file dialog can move focus and commit the active editor.
        col = next(i for i, c in enumerate(win.data_tab._columns) if c.schema_key == "tipo")
        win.data_tab.table.item(1, col).setText("Mutuo")
        return str(target), ""

    monkeypatch.setattr(store, "put", slow_commit)
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", choose)
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *_: success.append(True))
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *_: errors.append(True))
    try:
        win.capture_tab._on_export_excel()
        assert entered.wait(3) and not success and not errors
        assert not win.data_tab.export_button.isEnabled() and not win.capture_tab.export_button.isEnabled()
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while not (success or errors) and time.monotonic() < deadline:
        QTest.qWait(10)
    if fail_commit:
        assert errors and not success and not target.exists()
        # The operator can still export the last confirmed values after a journal failure.
        monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *_: (str(target), ""))
        win.capture_tab.export_button.click()
        deadline = time.monotonic() + 5
        while not success and time.monotonic() < deadline:
            QTest.qWait(10)
    assert success == [True]
    assert load_workbook(target).active["H3"].value == ("BPI Mutui" if fail_commit else "Mutuo")


def test_capture_is_paused_with_a_visible_notice_when_a_checkpoint_fails(
    reopened_window: tuple[MainWindow, list[str]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    win, _ = reopened_window
    monkeypatch.setattr(capture_tab_module, "BPERCaptureWorker", FakeWorker)
    win.config.show_capture_border = False
    win.header.toggle_button.click()
    win.extraction_client.recovery_error.emit("Spazio esaurito")
    assert not win.capture_tab.is_running()
    assert not win.header.toggle_button.isEnabled()
    win.nav.set_current(1)
    assert not win.recovery_notice.isHidden() and "Spazio esaurito" in win.recovery_notice.text()
    win.extraction_client.history_warning.emit("Storico non disponibile")
    assert "Spazio esaurito" in win.recovery_notice.text()


def test_history_warning_leaves_capture_available(window: MainWindow) -> None:
    window.extraction_client.history_warning.emit("Storico non disponibile")
    assert not window.recovery_notice.isHidden()
    assert "Storico non disponibile" in window.recovery_notice.text()
    assert "Storico non disponibile" in window.capture_tab.log_text.toPlainText()
    assert window.header.toggle_button.isEnabled()


def test_recoverable_close_explains_what_will_be_available_after_restart() -> None:
    message = leave_message(["Sessione 1"], 2, recoverable=True)
    assert "Sessione 1" in message and "2 frame" in message
    assert "riapertura" in message
    assert "persi" not in message


def test_pending_only_session_is_selectable_while_its_replay_is_running(
    qapp: QtCore.QCoreApplication, tmp_path: Path,
) -> None:
    archive = tmp_path / "recovery"
    old_pipeline = BlockingPipeline()
    old_client = lec.LocalExtractionClient(pipeline=old_pipeline, recovery_dir=archive)
    try:
        job = old_client.start_job()
        old_client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type="slow")
        assert old_pipeline.started.wait(3)
    finally:
        old_client.shutdown()
        old_pipeline.release.set()
    pipeline = BlockingPipeline()
    client = lec.LocalExtractionClient(pipeline=pipeline, recovery_dir=archive)
    try:
        assert pipeline.started.wait(3)
        win = MainWindow(AgentConfig(config_path=tmp_path / "config.ini"), extraction_client=client)
        assert win.data_tab.job_combo.currentData() == job
        assert win.header.toggle_button.text() == "Riprendi"
        assert "0 elaborati su 1" in win.header.counters_label.text()
        pipeline.release.set()
        deadline = time.monotonic() + 5
        while "1 elaborati su 1" not in win.header.counters_label.text() and time.monotonic() < deadline:
            QTest.qWait(5)
        assert "1 elaborati su 1" in win.header.counters_label.text()
        assert not win.capture_tab.is_running()
    finally:
        pipeline.release.set()
        client.shutdown()


@pytest.mark.parametrize("save_succeeds", [True, False])
def test_close_waits_for_the_last_typed_draft_without_blocking_the_window(
    save_succeeds: bool, reopened_window: tuple[MainWindow, list[str]],
    qapp: QtWidgets.QApplication, monkeypatch: pytest.MonkeyPatch,
) -> None:
    win, jobs = reopened_window
    job = jobs[-1]
    client = win.extraction_client
    release = threading.Event()
    save = client.set_cell_draft

    def slow_save(*args: Any) -> None:
        release.wait(1)
        if not save_succeeds:
            raise OSError("Disco pieno")
        save(*args)

    monkeypatch.setattr(client, "set_cell_draft", slow_save)
    win._ask_leave_unexported = lambda labels, pending: True
    win.show()
    win.nav.set_current(1)
    qapp.processEvents()
    try:
        tab = win.data_tab
        col = next(i for i, c in enumerate(tab._columns) if c.schema_key == "tipo")
        tab.table.editItem(tab.table.item(1, col))
        editor = qapp.focusWidget()
        assert isinstance(editor, QtWidgets.QLineEdit)
        editor.selectAll()
        QTest.keyClicks(editor, "x")
        assert not win.close() and win.isVisible()
        QTest.qWait(20)
        assert win.isVisible() and client.get_cell_draft(job) is None
        release.set()
        deadline = time.monotonic() + 5
        while tab.has_pending_writes() and time.monotonic() < deadline:
            QTest.qWait(5)
        qapp.processEvents()
        assert not tab.has_pending_writes()
        if save_succeeds:
            assert not win.isVisible()
            assert client.get_cell_draft(job)["text"] == "x"
        else:
            assert win.isVisible() and "Disco pieno" in tab.edit_error.text()
            assert client.get_cell_draft(job) is None
    finally:
        release.set()
