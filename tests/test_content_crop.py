"""The calibrated content crop must not amputate uncalibrated framings."""

import io
from typing import Any, Dict, List, Tuple

import pytest
from PIL import Image

import extraction.pipeline as pipeline_mod
from extraction.config import CONTENT_CROP
from extraction.imaging import select_content_crop
from extraction.pipeline import ExtractionPipeline

CALIBRATED = (848, 679)          # the mnt/data reference framing
NORMALIZED = (1800, 1441)        # the same framing after the CLI's normalize_image
MEASURED_AMPUTATION = (1536, 1032)  # real capture: crop's left edge cut NDG/Denom/Tipo/Importo


def test_the_calibrated_framing_keeps_the_calibrated_crop():
    assert select_content_crop(CALIBRATED) == CONTENT_CROP
    assert select_content_crop(NORMALIZED) == CONTENT_CROP


def test_a_divergent_framing_is_not_cropped():
    """Fractions calibrated on 848x679 amputate content on other framings.

    Measured on a real 1536x1032 capture: the crop's left edge lands at x=276,
    leaving the Denom., Tipo and Importo columns outside the image, and NDG
    32084406 was read as '06'. Skipping the crop costs image tokens; applying
    it on the wrong framing silently destroys fields. The two failure modes are
    not symmetric, so the gate stays tight.
    """
    assert select_content_crop(MEASURED_AMPUTATION) is None
    assert select_content_crop((1920, 1080)) is None


def _png_size(image_bytes: bytes) -> Tuple[int, int]:
    return Image.open(io.BytesIO(image_bytes)).size


@pytest.fixture
def call_sizes(monkeypatch) -> List[Tuple[str, Tuple[int, int]]]:
    """Record (attempt, image size) for every VLM call the pipeline makes."""
    calls: List[Tuple[str, Tuple[int, int]]] = []

    def fake_call(**kwargs: Any) -> Dict[str, Any]:
        calls.append((kwargs["attempt"], _png_size(kwargs["image_bytes"])))
        return {"fields": {}, "soggetti": [], "fidi": [], "garanzie": [], "_meta": {}}

    monkeypatch.setattr(pipeline_mod, "call_vlm_with_retry", fake_call)
    return calls


def test_the_main_pass_receives_the_full_image_on_a_divergent_framing(call_sizes):
    pipeline = ExtractionPipeline(None, None, "test-model", "test-model")

    pipeline.extract_from_image(Image.new("RGB", MEASURED_AMPUTATION, "white"), "screen x")

    sizes = dict(call_sizes)
    assert sizes["CONTENT_MAIN"] == MEASURED_AMPUTATION


def test_a_live_frame_is_never_cropped_even_at_the_calibrated_aspect(call_sizes):
    """On the live path, a matching aspect is always a false positive.

    No operator window is the reference rendered at 848px: every operator has a
    different resolution, and the navigator is laid out in CSS pixels, so a window
    that lands on the calibrated aspect by coincidence still has a narrower
    navigator share and the crop would amputate columns anyway. The crop decision
    belongs to the entry point, not to a heuristic on the image.
    """
    pipeline = ExtractionPipeline(None, None, "test-model", "test-model")

    pipeline.extract_from_image(Image.new("RGB", CALIBRATED, "white"), "screen x")

    assert dict(call_sizes)["CONTENT_MAIN"] == CALIBRATED


def test_the_file_path_still_gets_the_crop_on_a_reference_shaped_file(call_sizes, tmp_path):
    """extract_from_screen serves the mnt/data reference family: there the crop
    is calibrated, measured, and must keep applying or the CLI baseline moves."""
    path = tmp_path / "screen x.png"
    Image.new("RGB", CALIBRATED, "white").save(path)
    pipeline = ExtractionPipeline(None, None, "test-model", "test-model")

    pipeline.extract_from_screen(str(path))

    left, top, right, bottom = CONTENT_CROP
    expected = (round(CALIBRATED[0] * (right - left)), round(CALIBRATED[1] * (bottom - top)))
    got = dict(call_sizes)["CONTENT_MAIN"]
    assert abs(got[0] - expected[0]) <= 1 and abs(got[1] - expected[1]) <= 1, (got, expected)
