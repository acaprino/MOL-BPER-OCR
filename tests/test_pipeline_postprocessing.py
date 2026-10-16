"""Pipeline results across anchor, retry, coherence and subject flattening."""

from copy import deepcopy
from typing import Any

import pytest
from PIL import Image

from conftest import install_fake_vlm
import extraction.pipeline as pipeline_mod
from extraction.pipeline import ExtractionPipeline


def _field(value: Any, confidence: float = 0.9) -> dict[str, Any]:
    return {"value": value, "confidence": confidence, "section": "main"}


def _reply(
    fields: dict[str, Any] | None = None,
    soggetti: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {"fields": fields or {}, "soggetti": soggetti or [],
            "fidi": [], "garanzie": [], "_meta": {}}


def _subject(
    ndg: str | None = "12345",
    denominazione: str | None = "ROSSI MARIO",
    ruolo: str | None = "Intestatario",
    confidence: float = 0.8,
) -> dict[str, Any]:
    return {"ndg": ndg, "denominazione": denominazione,
            "ruolo": ruolo, "confidence": confidence}


def _run(
    monkeypatch: pytest.MonkeyPatch,
    replies: dict[str, dict[str, Any]],
    *,
    calibrated: bool = False,
    stop_on_uncertain: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    def respond(kwargs: dict[str, Any]) -> dict[str, Any] | None:
        return deepcopy(replies.get(kwargs["attempt"]))

    install_fake_vlm(monkeypatch, calls.append, responder=respond)
    monkeypatch.setattr(pipeline_mod, "ANCHOR_CONF_MIN", 0.95)
    monkeypatch.setattr(pipeline_mod, "RETRY_CONF_MIN", 0.60)
    monkeypatch.setattr(pipeline_mod, "MAX_CALLS_PER_SCREEN", 5)
    monkeypatch.setattr(pipeline_mod, "STOP_ON_ANCHOR_UNCERTAIN", stop_on_uncertain)
    pipeline = ExtractionPipeline(None, None, "test-model", "test-model")
    image = Image.new("RGB", (848, 679) if calibrated else (320, 240), "white")
    result = pipeline.extract_from_image(image, "screen test", allow_content_crop=calibrated)
    return result, calls


@pytest.mark.parametrize("key", ["ndg", "denominazione"])
def test_an_anchor_below_threshold_is_returned_as_null(
    monkeypatch: pytest.MonkeyPatch, key: str,
) -> None:
    install_fake_vlm(
        monkeypatch, lambda kwargs: None,
        responder=lambda kwargs: _reply({key: _field("UNTRUSTED", 0.94)}),
    )
    monkeypatch.setattr(pipeline_mod, "ANCHOR_CONF_MIN", 0.95)
    pipeline = ExtractionPipeline(None, None, "test-model", "test-model")

    anchors = pipeline.extract_anchors(Image.new("RGB", (320, 240)), "screen test")

    assert anchors[key]["value"] is None


def test_an_uncertain_anchor_does_not_enter_the_main_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, calls = _run(monkeypatch, {
        "ANCHOR_HEADER": _reply({"ndg": _field("999887766", 0.94)}),
    })

    main_call = next(call for call in calls if call["attempt"] == "CONTENT_MAIN")
    assert "999887766" not in main_call["prompt"]


def test_an_uncertain_anchor_does_not_replace_the_main_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _ = _run(monkeypatch, {
        "ANCHOR_HEADER": _reply({"ndg": _field("999887766", 0.94)}),
        "CONTENT_MAIN": _reply({"ndg": _field("12345", 0.8)}),
    })

    assert result["fields"]["ndg"]["value"] == "12345"
    assert result["_field_sources"]["ndg"] == "CONTENT_MAIN"


def test_uncertain_anchors_can_stop_before_the_main_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, calls = _run(monkeypatch, {
        "ANCHOR_HEADER": _reply({"ndg": _field("12345", 0.94),
                                 "denominazione": _field(None, 1.0)}),
    }, stop_on_uncertain=True)

    assert result["_status"] == "ANCHOR_UNCERTAIN"
    assert [call["attempt"] for call in calls] == ["ANCHOR_HEADER"]
    assert result["_meta_agg"]["calls"] == 1
    assert result["fields"] == {}


@pytest.mark.parametrize("key,value", [("ndg", "12345"), ("denominazione", "ROSSI MARIO")])
def test_an_anchor_at_threshold_takes_priority_over_the_main_value(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str,
) -> None:
    result, calls = _run(monkeypatch, {
        "ANCHOR_HEADER": _reply({key: _field(value, 0.95)}),
        "CONTENT_MAIN": _reply({key: _field("OTHER", 0.99)}),
    })

    assert result["fields"][key]["value"] == value
    assert result["_field_sources"][key] == "ANCHOR_HEADER"
    main_call = next(call for call in calls if call["attempt"] == "CONTENT_MAIN")
    assert value in main_call["prompt"]


@pytest.mark.parametrize("attempt", ["CONTENT_MAIN", "RETRY_HEADER"])
def test_tipo_is_normalized_from_each_header_read(
    monkeypatch: pytest.MonkeyPatch, attempt: str,
) -> None:
    result, _ = _run(monkeypatch, {attempt: _reply({"tipo": _field("Mutui Spesa")})})

    assert result["fields"]["tipo"]["value"] == "BPI Mutui"
    assert result["_field_sources"]["tipo"] == attempt


@pytest.mark.parametrize("value", [None, "12", "12.0"])
def test_evidenze_is_repaired_from_its_tooltip(
    monkeypatch: pytest.MonkeyPatch, value: str | None,
) -> None:
    result, _ = _run(monkeypatch, {
        "CONTENT_MAIN": _reply({"evidenze": _field(value),
                                 "tooltip_evidenze_b": _field("Evidenza letta", 0.83)}),
    })

    assert result["fields"]["evidenze"]["value"] == "B"
    assert result["fields"]["evidenze"]["confidence"] == 0.83


def test_non_numeric_evidenze_is_preserved_despite_its_tooltip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _ = _run(monkeypatch, {
        "CONTENT_MAIN": _reply({"evidenze": _field("A"),
                                 "tooltip_evidenze_b": _field("Evidenza letta", 0.99)}),
    })

    assert result["fields"]["evidenze"]["value"] == "A"


def test_missing_tipo_is_repaired_from_the_bmb_tooltip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _ = _run(monkeypatch, {
        "CONTENT_MAIN": _reply({"tooltip_descrizione_bmb": _field("Descrizione BMB", 0.87)}),
    })

    assert result["fields"]["tipo"]["value"] == "BMB"
    assert result["fields"]["tipo"]["confidence"] == 0.87


def test_a_tipo_read_by_retry_survives_the_bmb_tooltip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _ = _run(monkeypatch, {
        "CONTENT_MAIN": _reply({"tooltip_descrizione_bmb": _field("Descrizione BMB")}),
        "RETRY_HEADER": _reply({"tipo": _field("Mutui Spesa")}),
    })

    assert result["fields"]["tipo"]["value"] == "BPI Mutui"


@pytest.mark.parametrize("key,value", [
    ("ndg", "12345"), ("denominazione", "ROSSI MARIO"), ("ruolo", "Intestatario"),
])
@pytest.mark.parametrize("table_value,confidence", [(None, 0.99), ("OTHER", 0.7), ("TIED", 0.98)])
def test_flatten_preserves_the_better_scalar_value(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str,
    table_value: str | None, confidence: float,
) -> None:
    row = _subject(confidence=confidence)
    row[key] = table_value
    result, _ = _run(monkeypatch, {
        "CONTENT_MAIN": _reply({f"{key}_1": _field(value, 0.98)}, [row]),
    })

    assert result["fields"][f"{key}_1"]["value"] == value
    assert result["fields"][f"{key}_1"]["confidence"] == 0.98
    assert result["_field_sources"][f"{key}_1"] == "CONTENT_MAIN"


def test_flatten_adopts_a_better_main_table_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _ = _run(monkeypatch, {
        "CONTENT_MAIN": _reply({"ndg_1": _field("OTHER", 0.7)}, [_subject()]),
    })

    assert result["fields"]["ndg_1"]["value"] == "12345"
    assert result["fields"]["ndg_1"]["section"] == "soggetti_table"
    assert result["_field_sources"]["ndg_1"] == "CONTENT_MAIN"


@pytest.mark.parametrize("calibrated", [False, True])
def test_flatten_reports_the_retry_source_for_an_adopted_table(
    monkeypatch: pytest.MonkeyPatch, calibrated: bool,
) -> None:
    result, _ = _run(monkeypatch, {"RETRY_BODY": _reply(soggetti=[_subject()])},
                     calibrated=calibrated)

    for key in ("ndg_1", "denominazione_1", "ruolo_1"):
        assert result["_field_sources"][key] == "RETRY_BODY"
    assert result["fields"]["ndg_1"]["value"] == "12345"


def test_off_calibration_a_retry_fills_an_empty_subject_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _subject()
    result, _ = _run(monkeypatch, {"RETRY_BODY": _reply(soggetti=[row])})

    assert result["soggetti"] == [row]


def test_off_calibration_a_retry_cannot_replace_a_populated_subject_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_row = _subject(confidence=0.7)
    result, _ = _run(monkeypatch, {
        "CONTENT_MAIN": _reply(soggetti=[main_row]),
        "RETRY_BODY": _reply(soggetti=[_subject("999", confidence=0.99), _subject("888")]),
    })

    assert result["soggetti"] == [main_row]
    assert result["fields"]["ndg_1"]["value"] == "12345"
    assert result["_field_sources"]["ndg_1"] == "CONTENT_MAIN"


def test_calibrated_replacement_updates_the_flattened_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _ = _run(monkeypatch, {
        "CONTENT_MAIN": _reply(soggetti=[_subject("111", confidence=0.7)]),
        "RETRY_BODY": _reply(soggetti=[_subject("222"), _subject("333")]),
    }, calibrated=True)

    assert result["fields"]["ndg_1"]["value"] == "222"
    assert result["_field_sources"]["ndg_1"] == "RETRY_BODY"


def test_a_rejected_retry_preserves_the_main_table_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _ = _run(monkeypatch, {
        "CONTENT_MAIN": _reply(soggetti=[_subject("111", confidence=0.9)]),
        "RETRY_BODY": _reply(soggetti=[_subject("222", confidence=0.8)]),
    }, calibrated=True)

    assert result["fields"]["ndg_1"]["value"] == "111"
    assert result["_field_sources"]["ndg_1"] == "CONTENT_MAIN"
