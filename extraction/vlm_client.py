"""VLM API calls — LangChain structured output with retry."""

import base64
import json
import re
import time
from typing import Dict, Any, Optional, Type

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel

from extraction.config import PRICING_PER_1M
from prompt_store import get_text

# Gemini models that support response_schema in json_mode (small schemas only).
# Newer models (2.0+, 3.x) reject response_schema for complex schemas —
# we fall back to free-form JSON + manual Pydantic validation.
_GEMINI_JSON_SCHEMA_MODELS = ("gemini-1.5",)

# Prompt catalog entries resolved once at import (see prompt_store.py).
_USER_INSTRUCTION = get_text("extraction_user_instruction")
_JSON_SCHEMA_INSTRUCTION = get_text("extraction_json_schema_instruction")


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost from token counts; returns 0.0 for models absent from PRICING_PER_1M."""
    p = PRICING_PER_1M.get(model)
    if not p:
        return 0.0
    return (prompt_tokens / 1_000_000) * p["input"] + (completion_tokens / 1_000_000) * p["output"]


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


def _call_vlm_gemini_freeform(
    chat_model: BaseChatModel,
    base64_image: str,
    prompt: str,
    screen_id: str,
    attempt: str,
    model: str,
    schema: Type[BaseModel],
) -> Dict[str, Any]:
    """Gemini path: response_mime_type=json without response_schema, parse manually.

    Used for newer Gemini models (2.0+, 3.x) where passing a complex
    response_schema causes INVALID_ARGUMENT.
    The JSON schema is injected into the prompt so the model knows the exact
    structure to produce.
    """
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    full_prompt = f"{prompt}\n\n{_JSON_SCHEMA_INSTRUCTION.format(schema=schema_json)}"
    messages = [
        HumanMessage(content=[
            {"type": "text", "text": full_prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
        ]),
    ]

    llm_json = chat_model.bind(
        generation_config={"response_mime_type": "application/json"}
    )

    t0 = time.time()
    raw_msg = llm_json.invoke(messages)
    dt_ms = int((time.time() - t0) * 1000)

    # Extract text from response (may be a list of content parts)
    content = raw_msg.content
    if isinstance(content, list):
        content = " ".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in content
        )

    json_str = _extract_json_str(content)
    try:
        parsed = schema.model_validate_json(json_str)
    except Exception as e:
        raise ValueError(
            f"Pydantic validation failed for {screen_id}/{attempt}: {e}\n"
            f"Raw JSON (first 300): {json_str[:300]}"
        )

    out = parsed.model_dump()

    usage = getattr(raw_msg, "usage_metadata", None) or {}
    prompt_tokens = usage.get("input_tokens", 0)
    completion_tokens = usage.get("output_tokens", 0)
    cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)

    out["_meta"] = {
        "model": model,
        "screen_id": screen_id,
        "attempt": attempt,
        "latency_ms": dt_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "estimated_cost_usd": cost_usd,
    }
    out["screen_id"] = screen_id
    out["attempt"] = attempt
    return out


def call_vlm(
    chat_model: BaseChatModel,
    image_bytes: bytes,
    prompt: str,
    screen_id: str,
    attempt: str,
    model: str,
    schema: Type[BaseModel],
) -> Dict[str, Any]:
    """Invoke LangChain ChatModel with structured output and return a dict."""
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    if "gemini" in model.lower():
        # For gemini-1.5 models: json_mode with response_schema works fine.
        # For gemini-2.0+/3.x: response_schema causes INVALID_ARGUMENT with
        # complex schemas (7k+ char) — use free-form JSON + manual validation.
        use_schema_mode = any(tag in model for tag in _GEMINI_JSON_SCHEMA_MODELS)

        if use_schema_mode:
            messages = [
                HumanMessage(content=[
                    {"type": "text", "text": f"{prompt}\n\n{_USER_INSTRUCTION}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                ]),
            ]
            structured = chat_model.with_structured_output(schema, include_raw=True, method="json_mode")
            t0 = time.time()
            result = structured.invoke(messages)
            dt_ms = int((time.time() - t0) * 1000)

            if result["parsing_error"]:
                raise ValueError(
                    f"Structured output parsing failed for {screen_id}/{attempt}: "
                    f"{result['parsing_error']}"
                )

            parsed: BaseModel = result["parsed"]
            raw_msg = result["raw"]
            out = parsed.model_dump()

            usage = getattr(raw_msg, "usage_metadata", None) or {}
            prompt_tokens = usage.get("input_tokens", 0)
            completion_tokens = usage.get("output_tokens", 0)
            cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)

            out["_meta"] = {
                "model": model,
                "screen_id": screen_id,
                "attempt": attempt,
                "latency_ms": dt_ms,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "estimated_cost_usd": cost_usd,
            }
            out["screen_id"] = screen_id
            out["attempt"] = attempt
            return out
        else:
            return _call_vlm_gemini_freeform(
                chat_model, base64_image, prompt, screen_id, attempt, model, schema
            )

    # ── OpenAI (and other non-Gemini providers) ──────────────────────────────
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=[
            {"type": "text", "text": _USER_INSTRUCTION},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
        ]),
    ]
    structured = chat_model.with_structured_output(schema, include_raw=True)

    t0 = time.time()
    result = structured.invoke(messages)
    dt_ms = int((time.time() - t0) * 1000)

    if result["parsing_error"]:
        raise ValueError(
            f"Structured output parsing failed for {screen_id}/{attempt}: "
            f"{result['parsing_error']}"
        )

    parsed = result["parsed"]
    raw_msg = result["raw"]
    out = parsed.model_dump()

    usage = getattr(raw_msg, "usage_metadata", None) or {}
    prompt_tokens = usage.get("input_tokens", 0)
    completion_tokens = usage.get("output_tokens", 0)
    cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)

    out["_meta"] = {
        "model": model,
        "screen_id": screen_id,
        "attempt": attempt,
        "latency_ms": dt_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "estimated_cost_usd": cost_usd,
    }
    out["screen_id"] = screen_id
    out["attempt"] = attempt
    return out


def call_vlm_with_retry(
    chat_model: BaseChatModel,
    image_bytes: bytes,
    prompt: str,
    screen_id: str,
    attempt: str,
    model: str,
    schema: Type[BaseModel],
    max_retries: int = 3,
) -> Dict[str, Any]:
    """Retry wrapper for transient API errors (rate limits, timeouts)."""
    last_err: Optional[Exception] = None
    for i in range(max_retries):
        try:
            return call_vlm(
                chat_model=chat_model,
                image_bytes=image_bytes,
                prompt=prompt,
                screen_id=screen_id,
                attempt=attempt,
                model=model,
                schema=schema,
            )
        except (ValueError, KeyError, IndexError):
            # Parse failures and malformed prompt templates (a stray brace makes
            # str.format raise KeyError/IndexError) are permanent: retrying them
            # only burns the backoff.
            raise
        except Exception as e:
            last_err = e
            sleep_s = min(8.0, (2 ** i) * 0.8) + (0.05 * i)
            time.sleep(sleep_s)
    raise last_err  # type: ignore[misc]
