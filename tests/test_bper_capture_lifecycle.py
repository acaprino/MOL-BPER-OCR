"""Capture acknowledgement and manual commands across the real worker loop."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

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
        self.results: dict[tuple[str, int], dict] = {}
        self.reject = False
        self.submitted = threading.Event()

    def ingest_frame(self, **kwargs: Any) -> int:
        if self.reject:
            raise RuntimeError("queue closed")
        sequence = sum(frame["job_id"] == kwargs["job_id"] for frame in self.frames)
        self.frames.append(kwargs)
        self.submitted.set()
        return sequence

    def complete(self, sequence: int, status: str = "OK", job: str = "job", ndg: str | None = None) -> None:
        frames = [frame for frame in self.frames if frame["job_id"] == job]
        result = {
            "_capture_sequence": sequence, "_status": status,
            "_page_type": frames[sequence]["page_type"], "fields": {"ndg": {"value": ndg}},
        }
        self.results[job, sequence] = result
        self.result_ready.emit(job, result)

    def get_results(self, job: str) -> list[dict]:
        published = []
        while (job, len(published)) in self.results:
            published.append(self.results[job, len(published)])
        return published


class RecoverableCaptureClient(CaptureClient):
    def __init__(self) -> None:
        super().__init__()
        self.decisions: list[dict] = []

    def record_navigation_decision(self, job: str, ndg: str, page: str, action: str, sequence: int) -> None:
        self.decisions.append(dict(job=job, ndg=ndg, page=page, action=action, sequence=sequence))

    def navigation_decisions(self, job: str) -> list[dict]:
        return [item for item in self.decisions if item["job"] == job]

    def last_accepted_sequence(self, job: str) -> int:
        return sum(frame["job_id"] == job for frame in self.frames) - 1


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
def capture(app: QtCore.QCoreApplication, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> SimpleNamespace:
    config = SimpleNamespace(
        fps=100, monitor_index=1, window_title_contains="no-such-test-window",
        image_scale=None, unsharp_amount=0.8, unsharp_radius=1.2,
        unsharp_threshold=2, router_mode="ml", dedup_threshold=3,
        route_retry_seconds=1.0, show_llm_debug_tab=False,
    )
    client, camera, router = getattr(request, "param", CaptureClient)(), Camera(), Router()
    worker = BPERCaptureWorker(config, lambda: "job", api_client=client)
    worker._mss_ctx = camera
    worker.router = router
    worker.registry = PageRegistry([
        PageDef("Pagina A", 1, None, "a"), PageDef("Pagina B", 2, None, "b"),
    ], None)
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


@pytest.fixture
def guided(capture: SimpleNamespace) -> SimpleNamespace:
    capture.worker._load_registry()
    capture.names = {page.order: page.name for page in capture.worker.registry.pages}
    capture.events = []
    capture.worker.navigation_changed.connect(lambda job, state: capture.events.append((job, state)))
    capture.step = 0
    return capture


def visit(capture: SimpleNamespace, screen: int) -> None:
    capture.router.page = f"screen {screen}"
    capture.step += 1
    capture.camera.image.paste((capture.step, 20, 90), (30, 40, 180, 110))
    acquire(capture)


def finish(capture: SimpleNamespace, sequence: int, ndg: str | None = None) -> dict:
    capture.client.complete(sequence, ndg=ndg)
    capture.worker._capture_once()
    return capture.events[-1][1]


def test_guidance_follows_a_backwards_jump_to_the_current_content_tab(guided: SimpleNamespace) -> None:
    visit(guided, 9)
    state = finish(guided, 0, "100")
    assert state["next_page"] == guided.names[5]
    assert "scheda" in state["action"].lower()
    visit(guided, 5)
    state = finish(guided, 1, "100")
    assert state["current_page"] == guided.names[5]
    assert state["next_page"] == guided.names[6]
    assert "descrizione" in state["action"].lower()


def test_revisit_restores_only_that_practices_successful_pages(guided: SimpleNamespace) -> None:
    visit(guided, 1)
    finish(guided, 0, "001.000")
    visit(guided, 4)
    b = finish(guided, 1, "2000")
    assert b["captured"] == [guided.names[4]]
    visit(guided, 9)
    a = finish(guided, 2, "1000")
    assert a["practice_ndg"] == "1000"
    assert a["captured"] == [guided.names[1], guided.names[9]]
    assert guided.names[4] in a["missing"]


def test_late_results_attach_anonymous_views_using_capture_order(guided: SimpleNamespace) -> None:
    visit(guided, 1)
    finish(guided, 0, "100")
    visit(guided, 4)
    visit(guided, 9)
    early = finish(guided, 2)
    assert early["practice_ndg"] is None
    assert early["status"] == "pending"
    current = finish(guided, 1, "200")
    assert current["current_page"] == guided.names[9]
    assert current["practice_ndg"] == "200"
    assert current["identity_source"] == "preceding"
    assert current["captured"] == [guided.names[4], guided.names[9]]


def test_initial_anonymous_view_joins_the_first_identified_practice(guided: SimpleNamespace) -> None:
    visit(guided, 3)
    first = finish(guided, 0)
    assert first["practice_ndg"] is None
    assert first["captured"] == [guided.names[3]]
    visit(guided, 1)
    current = finish(guided, 1, "100")
    assert current["captured"] == [guided.names[1], guided.names[3]]


def test_a_new_visit_keeps_the_previous_checklist_explicitly_attributed(guided: SimpleNamespace) -> None:
    visit(guided, 1)
    finish(guided, 0, "100")
    visit(guided, 5)
    state = guided.events[-1][1]
    assert state["current_page"] == guided.names[5]
    assert state["status"] == "pending"
    assert state["practice_ndg"] is None and state["coverage_ndg"] == "100"
    assert state["captured"] == [guided.names[1]]
    assert state["next_page"] is None


def test_unknown_route_clears_the_current_page(guided: SimpleNamespace) -> None:
    visit(guided, 4)
    finish(guided, 0, "100")
    ticks = []
    guided.worker.tick.connect(ticks.append)
    guided.router.page = guided.worker.registry.catchall_name
    guided.camera.image.paste("pink", (45, 50, 100, 95))
    acquire(guided)
    state = guided.events[-1][1]
    assert state["status"] == "unrecognized" and state["current_page"] is None
    assert not any("Riconosciuta:" in line for line in ticks)
    assert len(guided.client.frames) == 1


def test_operator_can_update_the_last_identified_practice_from_an_unknown_screen(guided: SimpleNamespace) -> None:
    visit(guided, 5)
    finish(guided, 0, "100")
    visit(guided, 50)
    guided.worker.set_page_available("100", guided.names[8], False)
    guided.worker._capture_once()
    state = guided.events[-1][1]
    assert state["coverage_ndg"] == "100" and state["practice_ndg"] is None
    assert state["unavailable"] == [guided.names[8]]
    assert state["status"] == "unrecognized" and state["next_page"] is None


def test_changed_pixels_clear_current_identity_before_a_slow_route(
    guided: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    visit(guided, 5)
    finish(guided, 0, "100")
    before_answer = []

    def route(_image: Image.Image) -> RouterResult:
        before_answer.append(guided.events[-1][1])
        return RouterResult("screen 9", 0.95, {})

    monkeypatch.setattr(guided.router, "route", route)
    visit(guided, 9)
    state = before_answer[0]
    assert state["status"] == "recognizing" and state["current_page"] is None
    assert state["practice_ndg"] is None and state["coverage_ndg"] == "100"


def test_a_failed_manual_override_cannot_be_confirmed_by_the_older_capture(guided: SimpleNamespace) -> None:
    visit(guided, 1)
    guided.client.reject = True
    guided.worker.force_capture(guided.names[5])
    guided.worker._capture_once()
    assert guided.events[-1][1]["status"] == "error"
    state = finish(guided, 0, "100")
    assert state["status"] == "error" and state["current_page"] == guided.names[5]
    guided.client.reject = False
    acquire(guided)
    assert [f["page_type"] for f in guided.client.frames] == [guided.names[1], guided.names[5]]


def test_unavailable_tooltips_are_scoped_to_the_identified_practice(guided: SimpleNamespace) -> None:
    visit(guided, 5)
    state = finish(guided, 0, "100")
    tooltip = guided.names[8]
    assert tooltip in state["optional"] and tooltip not in state["missing"]
    guided.worker.set_page_available("100", tooltip, False)
    guided.worker._capture_once()
    state = guided.events[-1][1]
    assert state["unavailable"] == [tooltip] and tooltip not in state["optional"]
    visit(guided, 5)
    other = finish(guided, 1, "200")
    assert tooltip in other["optional"] and not other["unavailable"]
    visit(guided, 8)
    restored = finish(guided, 2, "100")
    assert tooltip in restored["captured"] and not restored["unavailable"]


def test_optional_view_can_be_restored_before_recapture(guided: SimpleNamespace) -> None:
    visit(guided, 5)
    finish(guided, 0, "100")
    page = guided.names[6]
    guided.worker.set_page_available("100", page, False)
    guided.worker._capture_once()
    assert guided.events[-1][1]["next_page"] != page
    guided.worker.set_page_available("100", page, True)
    guided.worker._capture_once()
    assert guided.events[-1][1]["next_page"] == page


def test_failed_capture_does_not_remove_a_required_view(guided: SimpleNamespace) -> None:
    visit(guided, 1)
    finish(guided, 0, "100")
    visit(guided, 5)
    guided.client.complete(1, status="ERROR")
    guided.worker._capture_once()
    assert guided.events[-1][1]["status"] == "error"
    visit(guided, 4)
    current = finish(guided, 2, "100")
    assert guided.names[5] in current["missing"]


def test_operator_can_reopen_a_wrongly_recognized_view_until_it_is_captured_again(guided: SimpleNamespace) -> None:
    visit(guided, 9)
    finish(guided, 0, "100")
    guided.worker.reopen_page("100", guided.names[9])
    guided.worker._capture_once()
    reopened = guided.events[-1][1]
    assert reopened["status"] == "review" and guided.names[9] in reopened["missing"]
    assert not reopened["captured"]
    visit(guided, 5)
    away = finish(guided, 1, "100")
    assert guided.names[9] in away["missing"]
    visit(guided, 9)
    back = finish(guided, 2, "100")
    assert guided.names[9] in back["captured"]


def test_new_job_ignores_late_completions_on_an_identical_frame(guided: SimpleNamespace) -> None:
    visit(guided, 1)
    guided.worker.job_id_getter = lambda: "new-job"
    guided.client.complete(0, job="job", ndg="100")
    acquire(guided)
    assert [frame["job_id"] for frame in guided.client.frames] == ["job", "new-job"]
    guided.client.complete(0, job="new-job", ndg="200")
    guided.worker._capture_once()
    job, state = guided.events[-1]
    assert job == "new-job" and state["practice_ndg"] == "200"
    assert state["captured"] == [guided.names[1]]


def test_old_inflight_result_cannot_close_a_view_reopened_by_the_operator(guided: SimpleNamespace) -> None:
    visit(guided, 9)
    finish(guided, 0, "100")
    visit(guided, 9)
    guided.worker.reopen_page("100", guided.names[9])
    guided.worker._capture_once()
    late = finish(guided, 1, "100")
    assert guided.names[9] in late["missing"]


@pytest.mark.parametrize("capture", [RecoverableCaptureClient], indirect=True)
def test_resumed_guidance_replays_decisions_at_their_capture_sequence(guided: SimpleNamespace) -> None:
    c = guided
    # These frames were completed before the new worker connected.
    with QtCore.QSignalBlocker(c.client):
        for screen in (9, 9, 5):
            sequence = c.client.ingest_frame(job_id="job", page_type=c.names[screen])
            c.client.complete(sequence, ndg="100")
    record = c.client.record_navigation_decision
    record("job", "100", c.names[9], "reopen", 0)
    record("job", "100", c.names[8], "skip", 0)
    record("job", "100", c.names[3], "skip", 0)
    record("job", "100", c.names[3], "restore", 0)
    record("job", "100", c.names[5], "reopen", 2)
    c.router.page = c.worker.registry.catchall_name
    c.worker._capture_once()
    state = c.events[-1][1]
    assert state["coverage_ndg"] == "100"
    assert state["current_page"] is None and state["practice_ndg"] is None
    assert state["captured"] == [c.names[9]]
    assert c.names[5] in state["missing"] and c.names[3] in state["optional"]
    assert state["unavailable"] == [c.names[8]]


@pytest.mark.parametrize("capture", [RecoverableCaptureClient], indirect=True)
def test_reopening_after_resume_covers_precrash_frames_still_in_flight(guided: SimpleNamespace) -> None:
    c = guided
    with QtCore.QSignalBlocker(c.client):
        for screen in (9, 4, 9):
            c.client.ingest_frame(job_id="job", page_type=c.names[screen])
        c.client.complete(0, ndg="100")
    c.router.page = c.worker.registry.catchall_name
    c.worker._capture_once()
    c.worker.reopen_page("100", c.names[9])
    c.worker._capture_once()
    assert c.client.navigation_decisions("job") == [
        dict(job="job", ndg="100", page=c.names[9], action="reopen", sequence=2)
    ]
    c.client.complete(2)
    c.client.complete(1, ndg="100")
    c.worker._capture_once()
    state = c.events[-1][1]
    assert state["captured"] == [c.names[4]] and c.names[9] in state["missing"]
    assert state["current_page"] is None and state["practice_ndg"] is None


@pytest.mark.parametrize("capture", [RecoverableCaptureClient], indirect=True)
def test_failed_navigation_write_leaves_the_optional_view_available(
    guided: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = guided
    visit(c, 5)
    finish(c, 0, "100")
    monkeypatch.setattr(c.client, "record_navigation_decision", Mock(side_effect=OSError("disk full")))
    errors = []
    c.worker.error.connect(errors.append)
    c.worker.set_page_available("100", c.names[6], False)
    c.worker._capture_once()
    assert errors and "disk full" in str(errors[-1])
    assert c.names[6] in c.events[-1][1]["optional"]


@pytest.fixture
def routing_models(guided: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    import llm_router
    import page_classifier

    sdk = Mock()
    local = Mock()
    local.classify_detailed.return_value = SimpleNamespace(
        label="screen 4", score=0.72, margin=0.01, rejected_by=None,
    )
    local.classify.return_value = ("screen 4", 0.72)
    monkeypatch.setattr(page_classifier, "BPERPagePrototypeClassifier", lambda **kwargs: local)
    monkeypatch.setattr(llm_router, "OpenAI", lambda **kwargs: sdk)
    guided.worker.config.llm_provider = "openai"
    guided.worker.config.llm_timeout = 1
    guided.worker.config.resolve_llm_settings = lambda: ("test-only", "unused", "test-model")
    guided.sdk = sdk
    return guided


def route_model_reply(capture: SimpleNamespace, mode: str, label: str, key_available: bool = True) -> None:
    capture.worker.config.router_mode = mode
    if not key_available:
        capture.worker.config.resolve_llm_settings = lambda: ("", "unused", "test-model")
    message = SimpleNamespace(content=json.dumps({"page_type": label, "confidence": 0.95}))
    capture.sdk.chat.completions.create.return_value.choices = [SimpleNamespace(message=message)]
    capture.worker._init_router()
    acquire(capture)


def test_local_first_defers_a_low_margin_to_the_configured_provider(routing_models: SimpleNamespace) -> None:
    c = routing_models
    route_model_reply(c, "local-first", c.names[1])
    assert [frame["page_type"] for frame in c.client.frames] == [c.names[1]]


def test_local_first_leaves_a_low_margin_unrecognized_when_provider_is_unavailable(routing_models: SimpleNamespace) -> None:
    c = routing_models
    route_model_reply(c, "local-first", c.names[1], key_available=False)
    assert not c.client.frames
    assert c.events[-1][1]["status"] == "unrecognized"


def test_hybrid_honors_an_explicit_provider_abstention(routing_models: SimpleNamespace) -> None:
    c = routing_models
    route_model_reply(c, "hybrid", c.worker.registry.catchall_name)
    assert not c.client.frames
    assert c.events[-1][1]["status"] == "unrecognized"


def test_failed_camera_read_clears_stale_guidance_until_next_good_frame(
    guided: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    visit(guided, 5)
    finish(guided, 0, "100")
    with monkeypatch.context() as camera:
        camera.setattr(guided.camera, "grab", Mock(side_effect=OSError("not available")))
        guided.worker._capture_once()
        state = guided.events[-1][1]
        assert state["status"] == "error" and state["current_page"] is None
    guided.worker._capture_once()
    assert guided.events[-1][1]["current_page"] == guided.names[5]
    assert len(guided.client.frames) == 1
