"""A retry may seed subjects only from sufficiently confident identified rows."""

from copy import deepcopy
from typing import Any

import pytest
from PIL import Image

from conftest import install_fake_vlm
import extraction.pipeline as pipeline_mod
from extraction.pipeline import ExtractionPipeline


def _row(
    confidence: float = 0.8,
    ndg: str | None = "12345",
    denominazione: str | None = "ROSSI MARIO",
) -> dict[str, Any]:
    return {"ndg": ndg, "denominazione": denominazione,
            "ruolo": "Intestatario", "confidence": confidence}


def _extract(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[dict[str, Any]],
    *,
    calibrated: bool,
) -> dict[str, Any]:
    def respond(kwargs: dict[str, Any]) -> dict[str, Any] | None:
        if kwargs["attempt"] != "RETRY_BODY":
            return None
        return {"fields": {}, "soggetti": deepcopy(rows),
                "fidi": [], "garanzie": [], "_meta": {}}

    install_fake_vlm(monkeypatch, lambda kwargs: None, responder=respond)
    monkeypatch.setattr(pipeline_mod, "MAX_CALLS_PER_SCREEN", 5)
    monkeypatch.setattr(pipeline_mod, "RETRY_CONF_MIN", 0.60)
    pipeline = ExtractionPipeline(None, None, "test-model", "test-model")
    image = Image.new("RGB", (848, 679) if calibrated else (320, 240), "white")
    return pipeline.extract_from_image(image, "screen test", allow_content_crop=calibrated)


@pytest.mark.parametrize("calibrated", [False, True])
def test_a_low_confidence_retry_cannot_seed_the_subject_table(
    monkeypatch: pytest.MonkeyPatch, calibrated: bool,
) -> None:
    result = _extract(monkeypatch, [_row(0.59)], calibrated=calibrated)

    assert result["soggetti"] == []
    assert not result["fields"].get("ndg_1", {}).get("value")


@pytest.mark.parametrize("calibrated", [False, True])
@pytest.mark.parametrize("missing", [None, "", "n/d", "---"])
def test_a_retry_row_without_identifiers_cannot_seed_the_subject_table(
    monkeypatch: pytest.MonkeyPatch, calibrated: bool, missing: str | None,
) -> None:
    result = _extract(monkeypatch, [_row(0.99, missing, missing)], calibrated=calibrated)

    assert result["soggetti"] == []
    assert not result["fields"].get("ruolo_1", {}).get("value")


@pytest.mark.parametrize("calibrated", [False, True])
@pytest.mark.parametrize("ndg,denominazione", [("12345", None), (None, "ROSSI MARIO")])
def test_an_identified_retry_row_at_the_threshold_can_seed_the_subject_table(
    monkeypatch: pytest.MonkeyPatch, calibrated: bool,
    ndg: str | None, denominazione: str | None,
) -> None:
    row = _row(0.60, ndg, denominazione)
    result = _extract(monkeypatch, [row], calibrated=calibrated)

    assert result["soggetti"] == [row]
    key = "ndg_1" if ndg is not None else "denominazione_1"
    assert result["fields"][key]["value"] == (ndg or denominazione)
    assert result["_field_sources"][key] == "RETRY_BODY"


@pytest.mark.parametrize("calibrated", [False, True])
def test_a_mixed_retry_seeds_only_the_valid_subject_rows(
    monkeypatch: pytest.MonkeyPatch, calibrated: bool,
) -> None:
    valid = _row(0.8)
    result = _extract(monkeypatch, [
        _row(0.99, None, None), valid, _row(0.2, "99999", "OTHER"),
    ], calibrated=calibrated)

    assert result["soggetti"] == [valid]
    assert result["fields"]["ndg_1"]["value"] == "12345"
    assert not result["fields"].get("ndg_2", {}).get("value")
