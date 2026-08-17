"""Page classifier: recognition from a live-shaped frame, and cache validity."""

import json
from pathlib import Path

import pytest
from PIL import Image

from frame_normalize import normalize_frame
from image_ops import preprocess_for_ocr

TEMPLATES = Path(__file__).resolve().parent.parent / "edge-agent" / "assets" / "templates" / "bper"
SCREENS = [f"screen {n}" for n in range(1, 10)]

MONITOR = {"left": 0, "top": 0, "width": 1920, "height": 1080}
DESKTOP = (32, 34, 38)


def _live_frame(template: Path, scale: float = 1.0) -> Image.Image:
    """What the capture loop really sees: the app window inside a full monitor.

    The reference templates are window screenshots; `mss` grabs the whole
    screen. This rebuilds that framing so the test exercises the live path
    instead of feeding the classifier its own prototype back.
    """
    win = Image.open(template).convert("RGB")
    if scale != 1.0:
        win = win.resize(
            (int(win.width * scale), int(win.height * scale)), Image.Resampling.LANCZOS
        )
    frame = Image.new("RGB", (MONITOR["width"], MONITOR["height"]), DESKTOP)
    frame.paste(win, ((MONITOR["width"] - win.width) // 2, (MONITOR["height"] - win.height) // 2))
    return frame


def _as_worker_sees_it(frame: Image.Image) -> Image.Image:
    """The worker's own order: normalize the framing, then preprocess for OCR."""
    normalized = normalize_frame(frame, MONITOR, window_rect_provider=lambda: None)
    return preprocess_for_ocr(
        normalized,
        scale=None,
        unsharp_amount=0.8,
        unsharp_radius=1.2,
        unsharp_threshold=2,
        contrast_stretch=True,
    )


@pytest.fixture(scope="module")
def classifier():
    pytest.importorskip("torch", reason="DINOv2 page classifier needs torch")
    from page_classifier import (
        BPERPagePrototypeClassifier,
        DEFAULT_CROP_ROI,
        DEFAULT_SIMILARITY_THRESHOLD,
    )

    return BPERPagePrototypeClassifier(
        templates_dir=TEMPLATES,
        crop_roi=DEFAULT_CROP_ROI,
        similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD,
        device="cpu",
    )


@pytest.mark.parametrize("screen", SCREENS)
def test_recognizes_each_page_from_a_full_monitor_frame(classifier, screen):
    label, score = classifier.classify(_as_worker_sees_it(_live_frame(TEMPLATES / f"{screen}.png")))

    assert label == screen, f"got {label!r} at score {score:.3f}"


@pytest.mark.parametrize("scale", [0.8, 1.4])
def test_recognition_survives_a_differently_sized_window(classifier, scale):
    # The operator's browser will not be 848x679. Recognition must not depend on
    # the window matching the template's pixel size.
    misread = [
        screen
        for screen in SCREENS
        if classifier.classify(
            _as_worker_sees_it(_live_frame(TEMPLATES / f"{screen}.png", scale=scale))
        )[0]
        != screen
    ]

    assert misread == []


def test_rejects_a_frame_that_is_not_a_bper_page(classifier):
    # A blank desktop must not be labelled as a page: a false positive burns the
    # page slot for the whole job and the operator cannot capture it again.
    label, _ = classifier.classify(Image.new("RGB", (1920, 1080), DESKTOP))

    assert label is None


def test_cache_is_stale_when_the_embedding_geometry_changed(tmp_path):
    """The prototype cache must key on geometry, not only on the image files.

    Prototypes and queries have to be embedded the same way. A cache keyed only
    on file contents keeps serving vectors built with a previous ROI or resize
    while queries use the new one, and every score becomes meaningless.
    """
    from page_classifier import BPERPagePrototypeClassifier, cache_is_valid, embedding_geometry

    templates = tmp_path / "bper"
    templates.mkdir()
    Image.new("RGB", (64, 48), "white").save(templates / "page a.png")
    Image.new("RGB", (64, 48), "black").save(templates / "page b.png")

    cache = templates / "bper_page_prototypes.json"
    dataset_hash = BPERPagePrototypeClassifier._compute_dataset_hash(
        {"page a": [templates / "page a.png"], "page b": [templates / "page b.png"]}
    )
    cache.write_text(
        json.dumps(
            {
                "dataset_hash": dataset_hash,
                "geometry": embedding_geometry() + " stale",
                "prototypes": {},
            }
        ),
        encoding="utf-8",
    )

    assert cache_is_valid(templates, cache) is False
