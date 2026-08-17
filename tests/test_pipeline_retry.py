"""Retry-area selection: which areas actually get a second read."""

from typing import Any, Dict, List

import pytest
from PIL import Image

import extraction.pipeline as pipeline_mod
from extraction.config import AREA_TO_FIELDS
from extraction.fields import FIELD_KEYS
from extraction.pipeline import ExtractionPipeline


def _empty_retry_response() -> Dict[str, Any]:
    """A retry that reads nothing: keeps the merge a no-op."""
    return {"fields": {}, "soggetti": [], "fidi": [], "garanzie": [], "_meta": {}}


@pytest.fixture
def recorded_attempts(monkeypatch) -> List[str]:
    """Capture the `attempt` label of every VLM call the pipeline makes."""
    attempts: List[str] = []

    def fake_call(**kwargs: Any) -> Dict[str, Any]:
        attempts.append(kwargs["attempt"])
        return _empty_retry_response()

    monkeypatch.setattr(pipeline_mod, "call_vlm_with_retry", fake_call)
    return attempts


def _pipeline() -> ExtractionPipeline:
    # The models are never touched: every VLM call is intercepted.
    return ExtractionPipeline(None, None, "test-model", "test-model")


def _result_with_only_header_partially_read() -> Dict[str, Any]:
    """Main-pass output for a page like 'Note da Richiesta'.

    The header identifiers were read, everything else came back null: BODY and
    FOOTER fields are absent from that page, and the note itself was missed.
    """
    fields: Dict[str, Any] = {
        k: {"value": None, "confidence": 0.0, "section": None} for k in FIELD_KEYS
    }
    for key in ("ndg", "denominazione", "stato", "fase", "creazione", "evidenze"):
        fields[key] = {"value": "letto", "confidence": 0.98, "section": "Header"}
    return {"fields": fields, "soggetti": [], "fidi": [], "garanzie": []}


def test_footer_is_retried_when_header_and_body_are_also_weak(recorded_attempts):
    """FOOTER owns note_della_richiesta; it must not lose its retry to the budget.

    On a notes page HEADER and BODY are always weak (their fields do not exist
    there), so a budget that only covers two areas starves the one area that
    holds the page's payload.
    """
    result = _result_with_only_header_partially_read()

    _pipeline()._retry_areas(
        Image.new("RGB", (400, 300), "white"),
        "Note da Richiesta",
        result,
        {k: "CONTENT_MAIN" for k in FIELD_KEYS},
        [],
    )

    assert "RETRY_FOOTER" in recorded_attempts


def test_every_declared_retry_area_gets_a_read_when_all_are_weak(recorded_attempts):
    """No area declared in AREA_TO_FIELDS may be structurally unreachable."""
    result = _result_with_only_header_partially_read()

    _pipeline()._retry_areas(
        Image.new("RGB", (400, 300), "white"),
        "Note da Richiesta",
        result,
        {k: "CONTENT_MAIN" for k in FIELD_KEYS},
        [],
    )

    assert sorted(recorded_attempts) == sorted(
        f"RETRY_{area}" for area in AREA_TO_FIELDS
    )
