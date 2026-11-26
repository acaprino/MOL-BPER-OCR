"""The BPER worker must hand a window-framed image to routing and extraction."""

from typing import Any, Dict
from types import SimpleNamespace

from PIL import Image
from PyQt6.QtCore import QCoreApplication

from workers.capture.bper_capture_worker import BPERCaptureWorker

MONITOR: Dict[str, int] = {"left": 0, "top": 0, "width": 1200, "height": 900}
DESKTOP = (32, 34, 38)
WINDOW_SIZE = (600, 480)
WINDOW_AT = (200, 150)


class _FakeConfig:
    fps = 3
    monitor_index = 1
    # A title no window on the test machine can match, so the worker has to fall
    # back to detecting the app rectangle from the frame itself.
    window_title_contains = "zzz-no-such-window-zzz"
    image_scale = None
    unsharp_amount = 0.8
    unsharp_radius = 1.2
    unsharp_threshold = 2
    router_mode = "ml"
    dedup_threshold = 3
    route_retry_seconds = 1.0


class _FakeShot:
    def __init__(self, img: Image.Image) -> None:
        self.size = img.size
        self.rgb = img.convert("RGB").tobytes()


class _FakeMss:
    """Minimal stand-in for an mss context: monitors list plus grab()."""

    def __init__(self, img: Image.Image) -> None:
        self._img = img
        self.monitors = [MONITOR, MONITOR]

    def grab(self, _mon: Dict[str, int]) -> _FakeShot:
        return _FakeShot(self._img)

    def close(self) -> None:
        pass


def _monitor_with_window() -> Image.Image:
    frame = Image.new("RGB", (MONITOR["width"], MONITOR["height"]), DESKTOP)
    frame.paste(Image.new("RGB", WINDOW_SIZE, "white"), WINDOW_AT)
    return frame


def _worker(frame: Image.Image) -> Any:
    QCoreApplication.instance() or QCoreApplication([])
    worker = BPERCaptureWorker(_FakeConfig(), lambda: "job")
    worker._mss_ctx = _FakeMss(frame)
    return worker


def test_grab_raw_crops_the_monitor_down_to_the_app_window():
    """Routing and extraction are both calibrated on window-sized screenshots.

    A full-monitor frame puts every relative crop (the classifier ROI, the
    pipeline's CONTENT_CROP) over different content, so the framing has to be
    normalized at the point of capture rather than in each consumer.
    """
    grabbed = _worker(_monitor_with_window())._grab_raw()

    assert grabbed.size == WINDOW_SIZE


def _maximized_app() -> Image.Image:
    filled = Image.new("RGB", (MONITOR["width"], MONITOR["height"]), "white")
    filled.paste(Image.new("RGB", (MONITOR["width"], 60), (10, 40, 90)), (0, 0))
    return filled


def test_grab_raw_keeps_the_full_frame_when_no_window_can_be_located():
    grabbed = _worker(_maximized_app())._grab_raw()

    assert grabbed.size == (MONITOR["width"], MONITOR["height"])


def _ticks_from(worker: Any, frames: int) -> list:
    captured: list = []
    worker.tick.connect(captured.append)
    for _ in range(frames):
        worker._grab_raw()
    return captured


def test_grab_raw_announces_which_framing_strategy_ran():
    """The operator must be able to read the framing decision, not infer it.

    A frame that was never cropped is out of distribution for the classifier,
    and the only symptom is a plausible-looking but wrong page at a mediocre
    score. That is unreadable from the capture feed unless the decision is
    stated.
    """
    ticks = _ticks_from(_worker(_monitor_with_window()), 1)

    assert any("content-rect" in t for t in ticks), ticks


def test_the_framing_announcement_is_not_repeated_every_frame():
    # At 3 FPS a per-frame line would bury the feed.
    ticks = _ticks_from(_worker(_monitor_with_window()), 4)

    assert len([t for t in ticks if "content-rect" in t]) == 1


def test_grab_raw_warns_when_the_frame_is_passed_through_uncropped():
    ticks = _ticks_from(_worker(_maximized_app()), 1)

    assert any("unchanged" in t for t in ticks), ticks


# ------------------------------------------------- confirmation on unchanged frames

class _Page:
    def __init__(self, name: str) -> None:
        self.name = name
        self.order = 1
        self.slug = "risultato_ricerca"


class _Registry:
    def resolve(self, label):
        return _Page(label) if label else None


def _routing_worker(frame: Image.Image, monkeypatch) -> Any:
    """A worker whose router answers once and counts how often it is asked."""
    worker = _worker(frame)
    worker.registry = _Registry()
    worker._acquirable_names = ["Risultato ricerca"]
    worker.routes = 0

    def fake_detect(_img):
        worker.routes += 1
        return "Risultato ricerca", 0.95, {}

    monkeypatch.setattr(worker, "_detect_page", fake_detect)
    worker.queued = []
    def enqueue(**frame: Any) -> int:
        worker.queued.append(frame["page_type"])
        return len(worker.queued) - 1
    worker.api_client = SimpleNamespace(ingest_frame=enqueue)
    return worker


def test_an_unchanged_screen_is_acquired_without_a_second_route(monkeypatch):
    """The router costs one VLM call per answer.

    Requiring two concordant answers means requiring the operator to hold a
    screen still for two routing round-trips. An identical frame already proves
    the page has not changed, so it must be able to close the stability gate.
    """
    worker = _routing_worker(_monitor_with_window(), monkeypatch)
    clock = {"t": 1000.0}
    monkeypatch.setattr("workers.capture.bper_capture_worker.time.time", lambda: clock["t"])

    worker._capture_once()          # routes once, adopts the candidate
    clock["t"] += 3.0
    worker._capture_once()          # same frame: confirmation, no new route

    assert worker.queued == ["Risultato ricerca"]
    assert worker.routes == 1, f"il router è stato interrogato {worker.routes} volte"


# ---------------------------------------------------- local-first routing

class _FakeClassification:
    def __init__(self, label, score, margin, rejected_by=None):
        self.label, self.score, self.margin = label, score, margin
        self.runner_up, self.rejected_by = "altro", rejected_by


class _FakeClassifier:
    """Records how often it is asked, and answers whatever it was handed."""

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def classify_detailed(self, _img):
        self.calls += 1
        return self.result

    def classify(self, img):
        r = self.classify_detailed(img)
        return r.label, r.score


class _FakeRouter:
    def __init__(self):
        self.calls = 0

    def route(self, _img):
        self.calls += 1
        class R:
            page_type, confidence, fields, reason = "Risultato ricerca", 0.9, {}, None
        return R()


def _hybrid_worker(monkeypatch, classification):
    worker = _worker(_monitor_with_window())
    worker.classifier = _FakeClassifier(classification)
    worker.router = _FakeRouter()
    worker.registry = _Registry()
    worker.config.router_mode = "local-first"
    worker.local_margin_min = 0.10
    return worker


def test_a_confident_local_answer_does_not_call_the_router(monkeypatch):
    """The whole point of the local classifier is removing the network call.

    If the router is asked anyway, the local path costs CPU and buys nothing: the
    4-5s per routed frame stay, and so does the dependency on a key and a
    connection.
    """
    worker = _hybrid_worker(monkeypatch, _FakeClassification("Elenco Soggetti", 0.8, 0.30))

    label, _score, _fields = worker._detect_page(_monitor_with_window())

    assert label == "Elenco Soggetti"
    assert worker.router.calls == 0, "il router e' stato interrogato senza bisogno"


def test_a_low_margin_answer_defers_to_the_router(monkeypatch):
    """Accuracy alone cannot gate a hybrid decision; the margin can.

    Measured on held-out frames: correct answers carried margins an order of
    magnitude above wrong ones, so a margin floor sends the doubtful cases to the
    model that reads text instead of comparing pixels.
    """
    worker = _hybrid_worker(monkeypatch, _FakeClassification("Elenco Soggetti", 0.8, 0.02))

    label, _score, _fields = worker._detect_page(_monitor_with_window())

    assert worker.router.calls == 1
    assert label == "Risultato ricerca", "avrebbe dovuto prevalere la risposta del router"


def test_a_frame_rejected_locally_does_not_call_the_router(monkeypatch):
    """A frame that lost to a reject prototype was actively recognised as a
    non-page. Paying a VLM call to confirm it is waste: reject classes exist
    precisely to answer this case without the network."""
    worker = _hybrid_worker(
        monkeypatch, _FakeClassification(None, 0.5, 0.40, rejected_by="SCARTO-fuori-processo"))

    label, _score, _fields = worker._detect_page(_monitor_with_window())

    assert label is None
    assert worker.router.calls == 0
