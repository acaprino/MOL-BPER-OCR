"""Retry-area selection: which areas actually get a second read."""

from typing import Any, Dict, List, Optional

import pytest
from PIL import Image

import extraction.pipeline as pipeline_mod
from extraction.config import AREA_TO_FIELDS
from extraction.fields import FIELD_KEYS
from extraction.pipeline import ExtractionPipeline


from conftest import install_fake_vlm


@pytest.fixture
def recorded_attempts(monkeypatch) -> List[str]:
    """Capture the `attempt` label of every VLM call the pipeline makes."""
    attempts: List[str] = []
    install_fake_vlm(monkeypatch, lambda kwargs: attempts.append(kwargs["attempt"]))
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


def test_missing_creazione_is_recovered_by_header_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing creation date alone must trigger the header's second read."""
    calls: Dict[str, Dict[str, Any]] = {}

    def record_call(kwargs: Dict[str, Any]) -> None:
        calls[kwargs["attempt"]] = kwargs

    def respond(kwargs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if kwargs["attempt"] == "CONTENT_MAIN":
            fields = {
                key: {"value": "letto", "confidence": 0.98, "section": "Header"}
                for key in FIELD_KEYS
            }
            fields["creazione"] = {
                "value": None, "confidence": 0.0, "section": "Header"
            }
        elif kwargs["attempt"] == "RETRY_HEADER":
            fields = {
                "creazione": {
                    "value": "16/10/2026", "confidence": 0.98, "section": "Header"
                }
            }
        else:
            return None
        return {
            "fields": fields, "soggetti": [], "fidi": [], "garanzie": [], "_meta": {}
        }

    install_fake_vlm(monkeypatch, record_call, responder=respond)

    result = _pipeline().extract_from_image(
        Image.new("RGB", (400, 300), "white"), "Risultato ricerca"
    )

    assert "RETRY_HEADER" in calls
    assert "creazione" in calls["RETRY_HEADER"]["prompt"]
    assert result["fields"]["creazione"]["value"] == "16/10/2026"
    assert result["_field_sources"]["creazione"] == "RETRY_HEADER"
