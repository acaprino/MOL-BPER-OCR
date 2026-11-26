"""Tests for ui/capture_tab.py (settings card, actions, collapsible log, export)."""

import os
import threading
from typing import Any, Iterator

import pytest

pytest.importorskip("PyQt6.QtWidgets")

# Must be set before ui/__init__ pulls in extraction.config (read at import time).
os.environ.setdefault("LLM_API_KEY", "test-key")

import time

from PIL import Image
from PyQt6 import QtCore, QtTest, QtWidgets

import ui.capture_tab as capture_tab_module

import local_extraction_client as lec
from config import AgentConfig
from ui.capture_tab import CaptureTab


class ScriptedPipeline:
    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict[str, Any]:
        fields = {"ndg": {"value": "123", "confidence": 1.0}, "tipo": {"value": "BPI Mutui", "confidence": 1.0}}
        return {"screen_id": screen_id, "fields": fields, "_status": "OK"}


@pytest.fixture
def tab(qapp, tmp_path) -> Iterator[CaptureTab]:
    client = lec.LocalExtractionClient(pipeline=ScriptedPipeline())
    widget = CaptureTab(config=AgentConfig(config_path=tmp_path / "config.ini"), api_client=client)
    yield widget
    client.shutdown()


def test_log_panel_is_collapsed_by_default_and_summarises_the_last_line(tab: CaptureTab) -> None:
    assert not tab.log_panel.is_expanded()
    tab._log("Avvio cattura in modalità BPER.")
    assert "Avvio cattura in modalità BPER." in tab.log_panel.summary_label.text()
    tab.log_panel.set_expanded(True)
    assert tab.log_panel.is_expanded() and not tab.log_text.isHidden()


def test_error_lines_are_counted_in_the_panel_summary(tab: CaptureTab) -> None:
    tab._log("[ERROR] qualcosa non va")
    assert tab.log_error_count() == 1
    assert "1 errore" in tab.log_panel.summary_label.text()
    tab._log("[ERROR] ancora")
    assert "2 errori" in tab.log_panel.summary_label.text()


def test_a_worker_error_shows_a_plain_message_and_keeps_the_technical_line_in_the_log(tab: CaptureTab) -> None:
    tab._on_worker_error(RuntimeError("mss failed"))
    assert "Errore durante la cattura" in tab.log_panel.summary_label.text()
    assert "RuntimeError: mss failed" in tab.log_text.toPlainText()
    assert tab.log_error_count() == 1


def test_settings_are_locked_while_capturing(tab: CaptureTab) -> None:
    tab.running_changed.emit(True)
    assert not tab.settings_card.isEnabled()
    tab.running_changed.emit(False)
    assert tab.settings_card.isEnabled()


def test_export_marks_the_session_as_exported(tab: CaptureTab, qapp, tmp_path, monkeypatch) -> None:
    client = tab.api_client
    job = client.start_job()
    client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type="p1")
    deadline = time.time() + 5
    while not client.get_results(job) and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    tab.job_id = job
    target = tmp_path / "out.xlsx"
    finished = threading.Event()
    # The two dialogs are the genuine boundary: the real export path runs.
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", staticmethod(lambda *a, **k: finished.set()))
    assert client.unexported_jobs() == [job]
    tab._on_export_excel()
    deadline = time.monotonic() + 5
    while not finished.is_set() and time.monotonic() < deadline:
        QtTest.QTest.qWait(10)
    assert finished.is_set()
    assert target.is_file()
    assert client.unexported_jobs() == []


# ============================================================
# Second code review
# ============================================================


class FakeWorker(QtCore.QObject):
    """The capture boundary (it would grab the real screen): same surface as the real worker."""

    tick = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(Exception)
    llm_debug = QtCore.pyqtSignal(str)
    navigation_changed = QtCore.pyqtSignal(str, dict)
    finished = QtCore.pyqtSignal()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(kwargs.get("parent"))
        self.manual_pages: list[str] = []

    def start_capture(self) -> None:
        pass

    def force_capture(self, page: str) -> None:
        self.manual_pages.append(page)

    def stop(self) -> None:
        self.finished.emit()

    def wait(self, _ms: int) -> bool:
        return True


class BrokenPipeline:
    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict[str, Any]:
        raise RuntimeError("VLM down")


def test_manual_shot_on_the_captured_monitor_gives_time_to_expose_pef(
    tab: CaptureTab, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(capture_tab_module, "BPERCaptureWorker", FakeWorker)
    tab.config.show_capture_border = False
    tab.show()
    tab.start_capture()
    selected = tab.force_page_combo.currentText()
    pages = tab.worker.manual_pages
    tab.force_capture_button.click()
    assert tab.isMinimized() and not pages
    QtTest.QTest.qWait(3350)
    assert pages == [selected]
    tab.stop_capture()
    tab.close()


def test_activity_log_keeps_recent_messages_after_a_long_capture(tab: CaptureTab) -> None:
    for sequence in range(1_050):
        tab._on_worker_tick(f"Fotogramma {sequence}.")
    visible = tab.log_text.toPlainText()
    assert "Fotogramma 0." not in visible
    assert "Fotogramma 1049." in visible


def test_repeated_identical_worker_errors_count_once(tab: CaptureTab) -> None:
    for _ in range(5):
        tab._on_worker_error(RuntimeError("mss failed"))
    assert tab.log_error_count() == 1
    assert "1 errore" in tab.log_panel.summary_label.text()


def test_a_new_capture_starts_with_a_clean_error_count(tab: CaptureTab, monkeypatch) -> None:
    monkeypatch.setattr(capture_tab_module, "BPERCaptureWorker", FakeWorker)
    tab.config.show_capture_border = False
    tab._on_worker_error(RuntimeError("mss failed"))
    assert tab.log_error_count() == 1
    tab.start_capture()
    assert tab.log_error_count() == 0
    tab.stop_capture()


def test_export_of_an_errors_only_session_warns_and_writes_nothing(qapp, tmp_path, monkeypatch) -> None:
    client = lec.LocalExtractionClient(pipeline=BrokenPipeline())
    widget = CaptureTab(config=AgentConfig(config_path=tmp_path / "config.ini"), api_client=client)
    job = client.start_job()
    client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type="p1")
    deadline = time.time() + 5
    while not client.get_results(job) and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    widget.job_id = job
    warned: list = []

    def no_file_dialog(*args, **kwargs):
        raise AssertionError("nothing to export: the file dialog must not open")

    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a)))
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", staticmethod(no_file_dialog))
    widget._on_export_excel()
    assert len(warned) == 1
    client.shutdown()
