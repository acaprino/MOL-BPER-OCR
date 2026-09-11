"""Capture acknowledgement and manual commands across the real worker loop."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image, ImageDraw
from PyQt6 import QtCore

from llm_router import RouterResult
from page_registry import PageDef, PageRegistry
from workers.capture.bper_capture_worker import BPERCaptureWorker


class CaptureClient(QtCore.QObject):
    result_ready = QtCore.pyqtSignal(str, dict)

    def __init__(self) -> None:
        super().__init__()
        self.frames: list[dict[str, Any]] = []
        self.reject = False
        self.submitted = threading.Event()

    def ingest_frame(self, **kwargs: Any) -> int:
        if self.reject:
            raise RuntimeError("queue closed")
        sequence = len(self.frames)
        self.frames.append(kwargs)
        self.submitted.set()
        return sequence

    def complete(self, sequence: int, status: str = "OK", job: str = "job") -> None:
        self.result_ready.emit(job, {"_capture_sequence": sequence, "_status": status})


class Camera:
    def __init__(self) -> None:
        self.image = Image.new("RGB", (400, 300), "white")
        self.image.paste((20, 40, 80), (0, 0, 400, 30))
        self.monitors = [{}, {"left": 0, "top": 0, "width": 400, "height": 300}]
        self.grab_threads: list[int] = []
        self.close_threads: list[int] = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = False

    def grab(self, _monitor: dict[str, int]) -> SimpleNamespace:
        self.grab_threads.append(threading.get_ident())
        self.entered.set()
        if self.block:
            assert self.release.wait(5), "camera was not released"
        return SimpleNamespace(size=self.image.size, rgb=self.image.tobytes())

    def close(self) -> None:
        self.close_threads.append(threading.get_ident())


class Router:
    def __init__(self) -> None:
        self.page = "Pagina A"
        self.fields: dict[str, Any] = {}
        self.calls = 0

    def route(self, _img: Image.Image) -> RouterResult:
        self.calls += 1
        return RouterResult(self.page, 0.99, self.fields)


@pytest.fixture
def app() -> QtCore.QCoreApplication:
    return QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])


@pytest.fixture
def capture(app: QtCore.QCoreApplication, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    config = SimpleNamespace(
        fps=100, monitor_index=1, window_title_contains="no-such-test-window",
        image_scale=None, unsharp_amount=0.8, unsharp_radius=1.2,
        unsharp_threshold=2, router_mode="ml", dedup_threshold=3,
        route_retry_seconds=1.0, show_llm_debug_tab=False,
    )
    client, camera, router = CaptureClient(), Camera(), Router()
    worker = BPERCaptureWorker(config, lambda: "job", api_client=client)
    worker._mss_ctx = camera
    worker.router = router
    worker.registry = PageRegistry([
        PageDef("Pagina A", 1, None, "a"), PageDef("Pagina B", 2, None, "b"),
    ], None)
    worker._acquirable_names = ["Pagina A", "Pagina B"]
    worker._router_ready = True
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr("workers.capture.bper_capture_worker.time.time", lambda: clock.now)
    return SimpleNamespace(worker=worker, client=client, camera=camera, router=router, clock=clock)


def acquire(capture: SimpleNamespace) -> None:
    capture.worker._capture_once()
    capture.clock.now += 3
    capture.worker._capture_once()


def test_queued_page_is_not_reported_as_completed(capture: SimpleNamespace) -> None:
    acquire(capture)
    assert len(capture.client.frames) == 1
    assert "Pagina A" not in capture.worker.captured_page_types


def test_stationary_page_is_not_rerouted_after_completion(capture: SimpleNamespace) -> None:
    acquire(capture)
    capture.client.complete(0)
    for _ in range(4):
        capture.clock.now += 3
        capture.worker._capture_once()
    assert len(capture.client.frames) == 1
    assert capture.router.calls == 1
    assert "Pagina A" in capture.worker.captured_page_types


def test_failed_extraction_rearms_the_stationary_page(capture: SimpleNamespace) -> None:
    acquire(capture)
    capture.client.complete(0, "ERROR")
    capture.worker._capture_once()
    assert len(capture.client.frames) == 1
    capture.clock.now += 3
    capture.worker._capture_once()
    assert len(capture.client.frames) == 2


def test_rejected_enqueue_does_not_consume_the_page(capture: SimpleNamespace) -> None:
    capture.client.reject = True
    acquire(capture)
    assert not capture.worker.captured_page_types
    capture.client.reject = False
    acquire(capture)
    assert len(capture.client.frames) == 1


def test_small_identity_change_on_the_same_page_can_be_acquired(capture: SimpleNamespace) -> None:
    acquire(capture)
    capture.client.complete(0)
    capture.worker._capture_once()
    # A tiny change can stay below the global pHash threshold.
    ImageDraw.Draw(capture.camera.image).text((80, 45), "NDG 222", fill="black")
    acquire(capture)
    assert len(capture.client.frames) == 2


def test_returning_to_a_page_is_a_new_visit(capture: SimpleNamespace) -> None:
    acquire(capture)
    capture.client.complete(0)
    capture.router.page = "Pagina B"
    original = capture.camera.image.copy()
    capture.camera.image.paste("gray", (30, 80, 300, 180))
    acquire(capture)
    capture.client.complete(1)
    capture.router.page = "Pagina A"
    capture.camera.image = original
    acquire(capture)
    assert [f["page_type"] for f in capture.client.frames] == ["Pagina A", "Pagina B", "Pagina A"]


def test_old_failure_does_not_release_the_current_pending_visit(capture: SimpleNamespace) -> None:
    acquire(capture)
    capture.router.page = "Pagina B"
    capture.camera.image.paste("gray", (30, 80, 300, 180))
    acquire(capture)
    capture.client.complete(0, "ERROR")
    acquire(capture)
    assert [f["page_type"] for f in capture.client.frames] == ["Pagina A", "Pagina B"]


def test_uncertain_anchor_does_not_trigger_endless_recapture(capture: SimpleNamespace) -> None:
    acquire(capture)
    capture.client.complete(0, "ANCHOR_UNCERTAIN")
    acquire(capture)
    assert len(capture.client.frames) == 1
    assert "Pagina A" in capture.worker.captured_page_types


def test_manual_request_waits_for_the_capture_thread(capture: SimpleNamespace) -> None:
    capture.camera.block = True
    capture.worker.start()
    try:
        assert capture.camera.entered.wait(2)
        capture.worker.force_capture("Pagina B")
        assert not capture.client.frames
        capture.camera.release.set()
        assert capture.client.submitted.wait(2)
    finally:
        capture.worker.stop()
        capture.camera.release.set()
        assert capture.worker.wait(3000)
    assert capture.client.frames[0]["page_type"] == "Pagina B"
    assert len(set(capture.camera.grab_threads)) == 1
    assert threading.get_ident() not in capture.camera.grab_threads
    assert capture.camera.close_threads == [capture.camera.grab_threads[0]]


def test_stop_discards_queued_manual_requests(capture: SimpleNamespace) -> None:
    capture.worker.force_capture("Pagina A")
    capture.worker.stop()
    capture.worker.run()
    assert not capture.camera.grab_threads
    assert not capture.client.frames


def test_manual_request_during_pending_extraction_is_coalesced(capture: SimpleNamespace) -> None:
    acquire(capture)
    capture.worker.force_capture("Pagina A")
    capture.worker._capture_once()
    assert len(capture.client.frames) == 1


def test_manual_request_after_success_can_capture_again(capture: SimpleNamespace) -> None:
    acquire(capture)
    capture.client.complete(0)
    capture.worker._capture_once()
    capture.worker.force_capture("Pagina A")
    capture.worker._capture_once()
    assert len(capture.client.frames) == 2


def test_first_manual_capture_retries_the_operator_page_after_error(capture: SimpleNamespace) -> None:
    capture.worker.force_capture("Pagina B")
    capture.worker._capture_once()
    capture.client.complete(0, "ERROR")
    capture.worker._capture_once()
    assert len(capture.client.frames) == 1
    capture.clock.now += 3
    capture.worker._capture_once()
    assert [frame["page_type"] for frame in capture.client.frames] == ["Pagina B", "Pagina B"]


def test_manual_retry_does_not_reuse_automatic_route_metadata(capture: SimpleNamespace) -> None:
    capture.router.fields = {"ndg": "111"}
    acquire(capture)
    capture.client.complete(0)
    capture.worker._capture_once()
    capture.worker.force_capture("Pagina B")
    capture.worker._capture_once()
    capture.client.complete(1, "ERROR")
    acquire(capture)
    assert len(capture.client.frames) == 3
    retry = capture.client.frames[-1]
    assert (retry["page_type"], retry["confidence"], retry["fields_json"]) == ("Pagina B", 0.0, "{}")
