"""VLM API calls (Chat Completions + Structured Outputs) with retry."""

import base64
import json
import time
from typing import Dict, Any, Optional

from openai import OpenAI

from extraction.config import PRICING_PER_1M


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p = PRICING_PER_1M.get(model)
    if not p:
        return 0.0
    return (prompt_tokens / 1_000_000) * p["input"] + (completion_tokens / 1_000_000) * p["output"]


def call_vlm(
    client: OpenAI,
    image_bytes: bytes,
    prompt: str,
    screen_id: str,
    attempt: str,
    model: str,
    schema: Dict[str, Any],
) -> Dict[str, Any]:
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Estrai i campi richiesti dallo screenshot."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                ],
            },
        ],
        response_format={"type": "json_schema", "json_schema": schema},
    )
    dt_ms = int((time.time() - t0) * 1000)

    if not resp.choices:
        raise ValueError(f"VLM returned empty choices for {screen_id}/{attempt}")
    out = json.loads(resp.choices[0].message.content)

    usage = getattr(resp, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
    completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
    total_tokens = getattr(usage, "total_tokens", 0) if usage else 0
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
    client: OpenAI,
    image_bytes: bytes,
    prompt: str,
    screen_id: str,
    attempt: str,
    model: str,
    schema: Dict[str, Any],
    max_retries: int = 3,
) -> Dict[str, Any]:
    """Retry wrapper for transient API errors (rate limits, timeouts)."""
    last_err: Optional[Exception] = None
    for i in range(max_retries):
        try:
            return call_vlm(
                client=client,
                image_bytes=image_bytes,
                prompt=prompt,
                screen_id=screen_id,
                attempt=attempt,
                model=model,
                schema=schema,
            )
        except Exception as e:
            last_err = e
            sleep_s = min(8.0, (2 ** i) * 0.8) + (0.05 * i)
            time.sleep(sleep_s)
    raise last_err  # type: ignore[misc]
