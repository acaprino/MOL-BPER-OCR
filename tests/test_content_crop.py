"""The calibrated content crop must not amputate uncalibrated framings."""

import io
from typing import Any, Dict, List, Optional, Tuple

import pytest
from PIL import Image

from conftest import install_fake_vlm
from extraction.config import CONTENT_CROP
from extraction.imaging import select_content_crop
from extraction.pipeline import ExtractionPipeline

CALIBRATED = (848, 679)             # the reference framing of data/dataset/pratiche/51350695 (846-850 wide, ADR 0001)
MEASURED_AMPUTATION = (1536, 1032)  # real capture: crop's left edge cut NDG/Denom/Tipo/Importo
LEGACY_5_4 = (1280, 1024)           # 5:4 full-screen grab: 0.09% from the calibrated aspect


# ------------------------------------------------- the family gate, pure


def test_the_calibrated_family_keeps_the_calibrated_crop():
    assert select_content_crop(CALIBRATED) == CONTENT_CROP
    assert select_content_crop((850, 680)) == CONTENT_CROP  # the references span 846-850


def test_a_divergent_aspect_is_not_cropped():
    assert select_content_crop(MEASURED_AMPUTATION) is None
    assert select_content_crop((1920, 1080)) is None


def test_a_matching_aspect_at_a_foreign_size_is_not_cropped():
    """Aspect alone is not identity: 1280/1024 sits 0.09% from 848/679.

    A full-screen 5:4 grab is not a reference window: its navigator share is
    nothing like the calibrated 18%, and an aspect-only gate would approve it
    and amputate the left columns exactly as in the measured 1536x1032 case.
    The references are 846-850 px wide and normalize_image() never upscales,
    so anything materially larger cannot be one of them.
    """
    assert select_content_crop(LEGACY_5_4) is None
    assert select_content_crop((424, 340)) is None  # nor can anything materially smaller


# ------------------------------------------------- plumbing


def _png_size(image_bytes: bytes) -> Tuple[int, int]:
    return Image.open(io.BytesIO(image_bytes)).size


@pytest.fixture
def call_sizes(monkeypatch) -> List[Tuple[str, Tuple[int, int]]]:
    """Record (attempt, image size) for every VLM call the pipeline makes."""
    calls: List[Tuple[str, Tuple[int, int]]] = []
    install_fake_vlm(
        monkeypatch,
        lambda kwargs: calls.append((kwargs["attempt"], _png_size(kwargs["image_bytes"]))),
    )
    return calls


def _pipeline() -> ExtractionPipeline:
    return ExtractionPipeline(None, None, "test-model", "test-model")


def _expected_crop_size(size: Tuple[int, int]) -> Tuple[int, int]:
    left, top, right, bottom = CONTENT_CROP
    return (round(size[0] * (right - left)), round(size[1] * (bottom - top)))


def _close(got: Tuple[int, int], expected: Tuple[int, int]) -> bool:
    return abs(got[0] - expected[0]) <= 1 and abs(got[1] - expected[1]) <= 1


# ------------------------------------------------- live path


def test_a_live_frame_is_never_cropped_even_at_the_calibrated_aspect(call_sizes):
    """On the live path, a matching aspect is always a false positive.

    No operator window is the reference rendered at 848px: every operator has a
    different resolution, and the navigator is laid out in CSS pixels, so a window
    that lands on the calibrated aspect by coincidence still has a narrower
    navigator share and the crop would amputate columns anyway. The crop decision
    belongs to the entry point, not to a heuristic on the image.
    """
    _pipeline().extract_from_image(Image.new("RGB", CALIBRATED, "white"), "screen x")

    assert dict(call_sizes)["CONTENT_MAIN"] == CALIBRATED


def test_the_anchor_pass_reads_the_whole_image_when_the_crop_was_skipped(call_sizes):
    """No fixed band contains the identifiers on an arbitrary window.

    Measured on a real 1296x1027 operator window: the top 22% band holds only
    browser chrome, logo and tab bar; at 35% the NDG bar appears half-cut at the
    bottom edge. Handing the anchor pass a band of an uncalibrated image is the
    content-crop amputation all over again, one level down, so on this path the
    anchor reads the full image.
    """
    _pipeline().extract_from_image(Image.new("RGB", MEASURED_AMPUTATION, "white"), "screen x")

    assert dict(call_sizes)["ANCHOR_HEADER"] == MEASURED_AMPUTATION


def test_the_live_result_states_that_no_crop_was_applied(call_sizes):
    result = _pipeline().extract_from_image(Image.new("RGB", CALIBRATED, "white"), "screen x")

    assert result["_content_crop"] == "full-frame"


# ------------------------------------------------- file path


def test_a_reference_shaped_file_still_gets_the_calibrated_crop(call_sizes, tmp_path):
    """extract_from_screen serves the reference-practice family: there the crop
    is calibrated, measured, and must keep applying or the CLI baseline moves."""
    path = tmp_path / "screen x.png"
    Image.new("RGB", CALIBRATED, "white").save(path)

    result = _pipeline().extract_from_screen(str(path))

    got = dict(call_sizes)["CONTENT_MAIN"]
    assert _close(got, _expected_crop_size(CALIBRATED)), got
    assert result["_content_crop"] == "calibrated"


def test_the_anchor_band_still_applies_on_the_calibrated_file_path(call_sizes, tmp_path):
    path = tmp_path / "screen x.png"
    Image.new("RGB", CALIBRATED, "white").save(path)

    _pipeline().extract_from_screen(str(path))

    crop_w, crop_h = _expected_crop_size(CALIBRATED)
    got = dict(call_sizes)["ANCHOR_HEADER"]
    assert _close(got, (crop_w, round(crop_h * 0.22))), got


@pytest.mark.parametrize("size", [MEASURED_AMPUTATION, LEGACY_5_4])
def test_an_out_of_family_file_is_not_amputated(call_sizes, tmp_path, size):
    """The gate must act on the file path too: the GUI accepts arbitrary uploads
    and the CLI scans whatever lands in INPUT_DIR, and both enter here."""
    path = tmp_path / "screen x.png"
    Image.new("RGB", size, "white").save(path)

    _pipeline().extract_from_screen(str(path))

    assert dict(call_sizes)["CONTENT_MAIN"] == size


# ------------------------------------------------- retry tables off calibration


def _row(conf: float) -> Dict[str, Any]:
    return {"ndg": "12345", "denominazione": None, "ruolo": None, "confidence": conf}


def _responder_with_body_retry(main_soggetti: List[Dict[str, Any]],
                               retry_soggetti: List[Dict[str, Any]]):
    def responder(kwargs) -> Optional[Dict[str, Any]]:
        if kwargs["attempt"] == "CONTENT_MAIN":
            return {"fields": {}, "soggetti": list(main_soggetti),
                    "fidi": [], "garanzie": [], "_meta": {}}
        if kwargs["attempt"] == "RETRY_BODY":
            return {"fields": {}, "soggetti": list(retry_soggetti),
                    "fidi": [], "garanzie": [], "_meta": {}}
        return None
    return responder


def test_a_longer_retry_table_does_not_replace_rows_off_calibration(monkeypatch):
    """Off calibration, the BODY retry band includes the navigator column.

    _merge_tables adopts the retry's tables wholesale whenever the retry returns
    MORE rows. On the live path the retry crop is a band of the raw window, so a
    spurious row read out of navigator text would replace genuinely read rows
    and the flatten step would emit fabricated ndg_N into the consolidated
    practice. Off calibration a longer retry table may only fill an empty one.
    """
    install_fake_vlm(monkeypatch, lambda kwargs: None,
                     responder=_responder_with_body_retry([_row(0.9)], [_row(0.2), _row(0.2)]))

    result = _pipeline().extract_from_image(
        Image.new("RGB", MEASURED_AMPUTATION, "white"), "screen x")

    assert len(result["soggetti"]) == 1, "la tabella letta e' stata sostituita da un retry fuori taratura"


def test_a_longer_retry_table_still_fills_an_empty_one_off_calibration(monkeypatch):
    install_fake_vlm(monkeypatch, lambda kwargs: None,
                     responder=_responder_with_body_retry([], [_row(0.8)]))

    result = _pipeline().extract_from_image(
        Image.new("RGB", MEASURED_AMPUTATION, "white"), "screen x")

    assert len(result["soggetti"]) == 1


def test_a_longer_retry_table_still_replaces_on_the_calibrated_path(monkeypatch, tmp_path):
    install_fake_vlm(monkeypatch, lambda kwargs: None,
                     responder=_responder_with_body_retry([_row(0.9)], [_row(0.8), _row(0.8)]))
    path = tmp_path / "screen x.png"
    Image.new("RGB", CALIBRATED, "white").save(path)

    result = _pipeline().extract_from_screen(str(path))

    assert len(result["soggetti"]) == 2
