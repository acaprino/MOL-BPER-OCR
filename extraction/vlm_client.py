"""VLM API calls — LangChain structured output with retry."""

import base64
import time
from typing import Dict, Any, Optional, Type

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel

from extraction.config import PRICING_PER_1M


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Backward-compatible cost helper (used by evaluation and other modules)."""
    p = PRICING_PER_1M.get(model)
    if not p:
        return 0.0
    return (prompt_tokens / 1_000_000) * p["input"] + (completion_tokens / 1_000_000) * p["output"]


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

    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=[
            {"type": "text", "text": "Estrai i campi richiesti dallo screenshot."},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{base64_image}"},
            },
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

    parsed: BaseModel = result["parsed"]
    raw_msg = result["raw"]

    out = parsed.model_dump()

    # Token usage from LangChain's standardized usage_metadata
    usage = getattr(raw_msg, "usage_metadata", None) or {}
    prompt_tokens = usage.get("input_tokens", 0)
    completion_tokens = usage.get("output_tokens", 0)
    total_tokens = prompt_tokens + completion_tokens
    cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)

    out["_meta"] = {
        "model": model,
        "screen_id": screen_id,
        "attempt": attempt,
        "latency_ms": dt_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
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
        except ValueError:
            raise  # parsing/validation errors are not transient
        except Exception as e:
            last_err = e
            sleep_s = min(8.0, (2 ** i) * 0.8) + (0.05 * i)
            time.sleep(sleep_s)
    raise last_err  # type: ignore[misc]
