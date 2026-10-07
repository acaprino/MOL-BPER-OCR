"""Model adapters: the one place that knows how each model family is built and read.

A family differs in how it is told its reasoning depth and in how it returns
structured output. Those differences used to be substring checks scattered
across the factory and the VLM client ("thinking" in the name, "gemini-1.5" in
the name), and a thinking level set for a family that ignored it vanished
silently. Here each family is one adapter, and adapter_for() is the single
name-to-family rule: a name outside every family is refused, not guessed.
"""

import json
import re
import warnings
from typing import Any, Dict, List, Optional, Tuple, Type

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from prompt_store import get_text

# Prompt catalog entries resolved once at import (see prompt_store.py).
_USER_INSTRUCTION = get_text("extraction_user_instruction")
_JSON_SCHEMA_INSTRUCTION = get_text("extraction_json_schema_instruction")

THINKING_LEVELS = ("low", "medium", "high")

# Safety filters disabled by design: inputs are legitimate banking-UI OCR
# screenshots, and the default filters produce spurious refusals on them.
# Accepted risk: the only provider-side content filter is off.
_GEMINI_SAFETY_SETTINGS = {
    "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
    "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
    "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
}


def _image_part(base64_image: str) -> Dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}


def _read_structured(
    chat_model: BaseChatModel,
    messages: List[BaseMessage],
    schema: Type[BaseModel],
    screen_id: str,
    attempt: str,
    **structured_kwargs: Any,
) -> Tuple[BaseModel, Any]:
    """Provider-native structured output; a parsing error is permanent (ValueError)."""
    structured = chat_model.with_structured_output(schema, include_raw=True, **structured_kwargs)
    result = structured.invoke(messages)
    if result["parsing_error"]:
        raise ValueError(
            f"Structured output parsing failed for {screen_id}/{attempt}: {result['parsing_error']}"
        )
    return result["parsed"], result["raw"]


def _extract_json_str(text: str) -> str:
    """Extract the first complete JSON object from a string.

    Uses json.JSONDecoder.raw_decode so it stops at the correct closing brace
    and ignores any trailing characters the model may append after the JSON.
    """
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "")
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in model response: {text[:200]!r}")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text, start)
        return json.dumps(obj, ensure_ascii=False)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON decode error in model response: {e}\nText: {text[start:start+200]!r}")


# ============================================================
# Adapters
# ============================================================

class ModelAdapter:
    """How one model family is built and asked for a structured reply."""

    provider = ""
    family = ""
    supports_thinking = False

    def build(self, model: str, api_key: str, thinking_level: str) -> BaseChatModel:
        """Create the LangChain model; thinking_level is '' (model default) or a validated level."""
        if thinking_level and not self.supports_thinking:
            warnings.warn(
                f"LLM_THINKING_LEVEL={thinking_level} ignored: the {self.family} family "
                f"({model}) has no thinking level control.",
                UserWarning,
                stacklevel=3,
            )
            thinking_level = ""
        return self._build(model, api_key, thinking_level)

    def _build(self, model: str, api_key: str, thinking_level: str) -> BaseChatModel:
        raise NotImplementedError

    def invoke(
        self,
        chat_model: BaseChatModel,
        prompt: str,
        base64_image: str,
        schema: Type[BaseModel],
        screen_id: str,
        attempt: str,
    ) -> Tuple[BaseModel, Any]:
        """Ask for one structured reply; returns (parsed, raw message). Parse failures raise ValueError."""
        raise NotImplementedError


class OpenAIAdapter(ModelAdapter):
    """OpenAI chat models: native structured output, prompt as system message."""

    provider = "openai"
    family = "OpenAI"

    def _build(self, model: str, api_key: str, thinking_level: str) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, api_key=api_key)

    def invoke(self, chat_model, prompt, base64_image, schema, screen_id, attempt):
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=[{"type": "text", "text": _USER_INSTRUCTION}, _image_part(base64_image)]),
        ]
        return _read_structured(chat_model, messages, schema, screen_id, attempt)


class GeminiAdapter(ModelAdapter):
    """Gemini base: shared construction, free-form JSON read.

    From 2.0 on, passing the complex extraction schema as response_schema is
    rejected with INVALID_ARGUMENT, so the schema goes into the prompt, the
    reply is requested as JSON and validated with Pydantic here.
    """

    provider = "gemini"
    family = "Gemini"

    def _thinking_kwargs(self, thinking_level: str) -> Dict[str, Any]:
        return {}

    def _build(self, model: str, api_key: str, thinking_level: str) -> BaseChatModel:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            safety_settings=_GEMINI_SAFETY_SETTINGS,
            **self._thinking_kwargs(thinking_level),
        )

    def invoke(self, chat_model, prompt, base64_image, schema, screen_id, attempt):
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        full_prompt = f"{prompt}\n\n{_JSON_SCHEMA_INSTRUCTION.format(schema=schema_json)}"
        messages = [HumanMessage(content=[{"type": "text", "text": full_prompt}, _image_part(base64_image)])]

        raw_msg = chat_model.bind(generation_config={"response_mime_type": "application/json"}).invoke(messages)

        # The reply content may be a list of parts.
        content = raw_msg.content
        if isinstance(content, list):
            content = " ".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)

        json_str = _extract_json_str(content)
        try:
            parsed = schema.model_validate_json(json_str)
        except Exception as e:
            raise ValueError(
                f"Pydantic validation failed for {screen_id}/{attempt}: {e}\n"
                f"Raw JSON (first 300): {json_str[:300]}"
            )
        return parsed, raw_msg


class Gemini15Adapter(GeminiAdapter):
    """Gemini 1.5: small enough schemas are accepted in json_mode."""

    family = "Gemini 1.5"

    def invoke(self, chat_model, prompt, base64_image, schema, screen_id, attempt):
        messages = [
            HumanMessage(content=[{"type": "text", "text": f"{prompt}\n\n{_USER_INSTRUCTION}"}, _image_part(base64_image)]),
        ]
        return _read_structured(chat_model, messages, schema, screen_id, attempt, method="json_mode")


class Gemini3Adapter(GeminiAdapter):
    """Gemini 3.x: reasoning depth via thinking_level; left unset, the model default is 'high'."""

    family = "Gemini 3"
    supports_thinking = True

    def _thinking_kwargs(self, thinking_level: str) -> Dict[str, Any]:
        return {"thinking_level": thinking_level} if thinking_level else {}


# Name prefix -> family, first match wins: specific families before their parent.
_FAMILIES: Tuple[Tuple[str, ModelAdapter], ...] = (
    ("gpt-", OpenAIAdapter()),
    ("o1", OpenAIAdapter()),
    ("o3", OpenAIAdapter()),
    ("o4", OpenAIAdapter()),
    ("gemini-1.5", Gemini15Adapter()),
    ("gemini-3", Gemini3Adapter()),
    ("gemini-", GeminiAdapter()),
)


def adapter_for(model: str) -> ModelAdapter:
    """Return the adapter of the family the model name belongs to; refuse unknown names."""
    name = model.strip().lower()
    for prefix, adapter in _FAMILIES:
        if name.startswith(prefix):
            return adapter
    known = ", ".join(f"{prefix}*" for prefix, _ in _FAMILIES)
    raise ValueError(f"Model {model!r} belongs to no known family ({known}).")


def validate_thinking_level(level: Optional[str]) -> str:
    """Normalize LLM_THINKING_LEVEL: '' keeps the model default; a typo is refused, not ignored."""
    value = (level or "").strip().lower()
    if value and value not in THINKING_LEVELS:
        raise ValueError(
            f"LLM_THINKING_LEVEL={level!r} is not valid: use one of {', '.join(THINKING_LEVELS)} or leave it empty."
        )
    return value
