"""Tests for the stop latch in BaseCaptureWorker (run() called synchronously)."""

from typing import List, Optional

from PyQt6.QtCore import QCoreApplication

from workers.capture.base_capture_worker import BaseCaptureWorker


class _FakeConfig:
    fps: int = 50


class _ProbeWorker(BaseCaptureWorker):
    """Worker that records calls and stops itself after the first tick."""

    def __init__(self) -> None:
        super().__init__(_FakeConfig(), lambda: "job")
        self.calls: List[str] = []

    def _capture_once(self) -> None:
        self.calls.append("tick")
        self.stop()


def _app() -> QCoreApplication:
    return QCoreApplication.instance() or QCoreApplication([])


def test_stop_before_run_skips_the_loop() -> None:
    _app()
    worker = _ProbeWorker()
    worker.stop()          # arrives while the subclass would still be initializing
    worker.run()           # called synchronously: must return without looping
    assert worker.calls == []


def test_run_without_prior_stop_executes_loop() -> None:
    _app()
    worker = _ProbeWorker()
    worker.run()
    assert worker.calls == ["tick"]
