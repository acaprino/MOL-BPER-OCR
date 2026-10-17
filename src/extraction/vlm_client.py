"""VLM API calls — structured output per model family (model_adapters.py), with retry."""

import base64
import time
from typing import Dict, Any, Optional, Type

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from extraction.config import PRICING_PER_1M
from extraction.model_adapters import adapter_for


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost from token counts; returns 0.0 for models absent from PRICING_PER_1M."""
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
    """Ask the model for one structured reply and return it as a dict with ``_meta``.

    The model family decides how the request is shaped and the reply parsed;
    a reply that cannot be parsed raises ValueError.
    """
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    t0 = time.time()
    parsed, raw_msg = adapter_for(model).invoke(chat_model, prompt, base64_image, schema, screen_id, attempt)
    dt_ms = int((time.time() - t0) * 1000)

    out = parsed.model_dump()

    usage = getattr(raw_msg, "usage_metadata", None) or {}
    prompt_tokens = usage.get("input_tokens", 0)
    completion_tokens = usage.get("output_tokens", 0)

    out["_meta"] = {
        "model": model,
        "screen_id": screen_id,
        "attempt": attempt,
        "latency_ms": dt_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "estimated_cost_usd": estimate_cost_usd(model, prompt_tokens, completion_tokens),
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
