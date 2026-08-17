"""The BPER worker must hand a window-framed image to routing and extraction."""

from typing import Any, Dict

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


def test_grab_raw_keeps_the_full_frame_when_no_window_can_be_located():
    filled = Image.new("RGB", (MONITOR["width"], MONITOR["height"]), "white")
    filled.paste(Image.new("RGB", (MONITOR["width"], 60), (10, 40, 90)), (0, 0))

    grabbed = _worker(filled)._grab_raw()

    assert grabbed.size == (MONITOR["width"], MONITOR["height"])
