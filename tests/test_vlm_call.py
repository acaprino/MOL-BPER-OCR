"""Tests for extraction/vlm_client.call_vlm: how each model family is asked and read.

The provider SDK is the network boundary, so it is the only thing faked: the
fake returns one canned reply and records how it was asked. Everything between
the pipeline and that boundary (message layout, output strategy, parsing,
_meta) is the real code.
"""

from typing import Any, Dict, List, Optional

import pytest
from langchain_core.messages import AIMessage, SystemMessage

from extraction.schemas import ExtractionResponse
from extraction.vlm_client import call_vlm

NDG_REPLY = '{"fields": {"ndg": {"value": "26871394", "confidence": 0.97}}}'


class FakeProviderModel:
    """Stands in for the provider SDK: one canned reply, records how it was asked."""

    def __init__(self, reply_text: str, input_tokens: int = 1000, output_tokens: int = 500) -> None:
        self.reply = AIMessage(
            content=reply_text,
            usage_metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        )
        self.bound: Dict[str, Any] = {}
        self.structured_method: Optional[str] = "not used"
        self.messages: List[Any] = []

    def bind(self, **kwargs: Any) -> "FakeProviderModel":
        self.bound = kwargs
        return self

    def invoke(self, messages: List[Any]) -> AIMessage:
        self.messages = messages
        return self.reply

    def with_structured_output(self, schema: Any, include_raw: bool = False, method: Optional[str] = None) -> Any:
        self.structured_method = method
        fake = self

        class _Structured:
            def invoke(self, messages: List[Any]) -> Dict[str, Any]:
                fake.messages = messages
                return {
                    "parsed": schema.model_validate_json(fake.reply.content),
                    "raw": fake.reply,
                    "parsing_error": None,
                }

        return _Structured()


def _call(fake: FakeProviderModel, model: str) -> Dict[str, Any]:
    return call_vlm(
        chat_model=fake,
        image_bytes=b"\x89PNG fake",
        prompt="Leggi la schermata.",
        screen_id="screen 1",
        attempt="CONTENT_MAIN",
        model=model,
        schema=ExtractionResponse,
    )


def test_gemini_3_reply_is_read_from_fenced_free_form_json() -> None:
    fake = FakeProviderModel("```json\n" + NDG_REPLY + "\n```\nfine risposta")

    out = _call(fake, "gemini-3.8-flash")

    assert out["fields"]["ndg"]["value"] == "26871394"


def test_gemini_3_request_asks_for_a_json_reply() -> None:
    fake = FakeProviderModel(NDG_REPLY)

    _call(fake, "gemini-3.8-flash")

    assert fake.bound["generation_config"]["response_mime_type"] == "application/json"


def test_gemini_1_5_uses_json_mode_structured_output() -> None:
    fake = FakeProviderModel(NDG_REPLY)

    out = _call(fake, "gemini-1.5-flash")

    assert fake.structured_method == "json_mode"
    assert out["fields"]["ndg"]["value"] == "26871394"


def test_openai_sends_the_prompt_as_system_message() -> None:
    fake = FakeProviderModel(NDG_REPLY)

    _call(fake, "gpt-4o")

    assert isinstance(fake.messages[0], SystemMessage)
    assert fake.messages[0].content == "Leggi la schermata."


def test_call_meta_carries_tokens_and_cost() -> None:
    fake = FakeProviderModel(NDG_REPLY, input_tokens=1000, output_tokens=500)

    meta = _call(fake, "gemini-3.8-flash")["_meta"]

    assert (meta["prompt_tokens"], meta["completion_tokens"]) == (1000, 500)
    assert meta["estimated_cost_usd"] == pytest.approx(1000 / 1e6 * 0.75 + 500 / 1e6 * 3.75)


def test_unparseable_reply_raises_value_error() -> None:
    fake = FakeProviderModel("non ho trovato dati")

    with pytest.raises(ValueError):
        _call(fake, "gemini-3.8-flash")
