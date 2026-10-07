"""Tests for extraction/llm_factory.create_chat_model: one adapter per model family.

What each family can be told (reasoning depth, output strategy) is decided by
the family the model name belongs to, in one place. A requested thinking level
must reach the families that support it and must never vanish silently on the
ones that do not. Building a model makes no network call.
"""

import pytest

from extraction.llm_factory import create_chat_model


def test_thinking_level_reaches_gemini_3_models() -> None:
    model = create_chat_model("gemini", model="gemini-3.8-flash", api_key="test-key", thinking_level="low")

    assert model.thinking_level == "low"


def test_unset_thinking_level_leaves_the_model_default() -> None:
    model = create_chat_model("gemini", model="gemini-3.8-flash", api_key="test-key", thinking_level="")

    assert model.thinking_level is None


def test_thinking_level_on_a_family_without_it_warns() -> None:
    with pytest.warns(UserWarning, match="LLM_THINKING_LEVEL"):
        create_chat_model("gemini", model="gemini-2.0-flash", api_key="test-key", thinking_level="low")


def test_invalid_thinking_level_is_refused() -> None:
    with pytest.raises(ValueError, match="LLM_THINKING_LEVEL"):
        create_chat_model("gemini", model="gemini-3.8-flash", api_key="test-key", thinking_level="lwo")


def test_model_outside_every_family_is_refused() -> None:
    with pytest.raises(ValueError, match="claude-sonnet"):
        create_chat_model("gemini", model="claude-sonnet", api_key="test-key")


def test_model_of_another_provider_is_refused() -> None:
    with pytest.raises(ValueError, match="gemini-3.8-flash"):
        create_chat_model("openai", model="gemini-3.8-flash", api_key="test-key")
