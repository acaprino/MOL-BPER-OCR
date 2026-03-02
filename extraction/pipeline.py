"""Multi-pass extraction pipeline: anchor -> main -> conditional retry."""

import os
from typing import Dict, Any, List, Tuple

from PIL import Image
from langchain_core.language_models import BaseChatModel

from extraction.config import (
    CONTENT_CROP,
    HEADER_IN_CONTENT,
    FIELD_RETRY_MAP,
    ANCHOR_CONF_MIN,
    MAX_CALLS_PER_SCREEN,
    STOP_ON_ANCHOR_UNCERTAIN,
)
from extraction.fields import FIELD_KEYS
from extraction.prompts import PROMPT, ANCHOR_PROMPT
from extraction.schemas import ExtractionResponse, AnchorResponse
from extraction.normalization import (
    normalize_tipo,
    is_nullish,
    safe_field,
    safe_set_field,
    merge_field_sources,
)
from extraction.imaging import (
    normalize_image,
    crop_relative,
    img_to_png_bytes,
    save_debug_crop,
)
from extraction.vlm_client import call_vlm_with_retry

# ============================================================
# Startup assertions — catch naming drift early
# ============================================================

_invalid_retry = set(FIELD_RETRY_MAP) - set(FIELD_KEYS)
if _invalid_retry:
    raise ValueError(f"FIELD_RETRY_MAP keys not in FIELD_KEYS: {_invalid_retry}")
del _invalid_retry


# ============================================================
# Anchor extraction (NDG, Denominazione)
# ============================================================

def extract_anchors(
    anchor_model: BaseChatModel,
    anchor_model_name: str,
    content_img: Image.Image,
    screen_id: str,
) -> Dict[str, Any]:
    header_img = crop_relative(content_img, HEADER_IN_CONTENT)
    save_debug_crop(header_img, screen_id, "HEADER_IN_CONTENT")

    payload = img_to_png_bytes(header_img)
    out = call_vlm_with_retry(
        chat_model=anchor_model,
        image_bytes=payload,
        prompt=ANCHOR_PROMPT,
        screen_id=screen_id,
        attempt="ANCHOR_HEADER",
        model=anchor_model_name,
        schema=AnchorResponse,
    )

    fields = out.get("fields", {})
    ndg = safe_field(fields, "ndg")
    den = safe_field(fields, "denominazione")

    # Gate duro: alta confidenza o null
    if ndg.get("confidence", 0.0) < ANCHOR_CONF_MIN:
        safe_set_field(fields, "ndg", value=None, confidence=ndg.get("confidence", 0.0),
                       evidence_text=ndg.get("evidence_text"), section=ndg.get("section"))
    if den.get("confidence", 0.0) < ANCHOR_CONF_MIN:
        safe_set_field(fields, "denominazione", value=None, confidence=den.get("confidence", 0.0),
                       evidence_text=den.get("evidence_text"), section=den.get("section"))

    return {
        "ndg": ndg,
        "denominazione": den,
        "_meta": out["_meta"],
    }


# ============================================================
# Pipeline sub-functions (decomposed from extract_from_screen)
# ============================================================

def _prepare_content_image(path: str) -> Tuple[str, Image.Image]:
    """Load, normalize, and crop the content area. Returns (screen_id, content_img)."""
    img = Image.open(path).convert("RGB")
    img = normalize_image(img)
    screen_id = os.path.splitext(os.path.basename(path))[0]
    content_img = crop_relative(img, CONTENT_CROP)
    save_debug_crop(content_img, screen_id, "CONTENT")
    return screen_id, content_img


def _build_anchor_hint_prompt(anchors: Dict[str, Any]) -> str:
    """Append anchor hints to the base prompt for disambiguation."""
    hints: List[str] = []
    if anchors["ndg"]["value"]:
        hints.append(f"NDG atteso: {anchors['ndg']['value']}")
    if anchors["denominazione"]["value"]:
        hints.append(f"Denominazione attesa: {anchors['denominazione']['value']}")
    return PROMPT + ("\n\n" + "\n".join(hints) if hints else "")


def _merge_anchors(
    result: Dict[str, Any],
    anchors: Dict[str, Any],
    field_sources: Dict[str, str],
) -> None:
    """Overwrite main-pass anchors with gated anchor values (higher priority)."""
    for k in ("ndg", "denominazione"):
        if anchors[k]["value"] is not None:
            result["fields"][k] = anchors[k]
            field_sources[k] = "ANCHOR_HEADER"


def _postprocess_tipo(result: Dict[str, Any]) -> None:
    """Apply categorical mapping to the 'tipo' field."""
    tipo_field = (result.get("fields", {}) or {}).get("tipo")
    if isinstance(tipo_field, dict):
        tipo_field["value"] = normalize_tipo(tipo_field.get("value"))
        result["fields"]["tipo"] = tipo_field


def _retry_low_confidence_fields(
    main_model: BaseChatModel,
    main_model_name: str,
    content_img: Image.Image,
    screen_id: str,
    prompt_with_hint: str,
    result: Dict[str, Any],
    field_sources: Dict[str, str],
    attempts_meta: List[Dict[str, Any]],
    max_retry_calls: int = MAX_CALLS_PER_SCREEN - 2,
) -> None:
    """Retry fields that are nullish or have confidence < 0.55 using targeted crops."""
    retry_calls = 0
    for field_key, crop_box in FIELD_RETRY_MAP.items():
        if retry_calls >= max_retry_calls:
            break

        current = result["fields"].get(field_key) or {}
        cur_val = current.get("value")
        cur_conf = float(current.get("confidence", 0.0) or 0.0)

        should_retry = is_nullish(cur_val) or (cur_conf < 0.55)
        if not should_retry:
            continue

        crop_img = crop_relative(content_img, crop_box)
        save_debug_crop(crop_img, screen_id, f"RETRY_{field_key}")

        retry_out = call_vlm_with_retry(
            chat_model=main_model,
            image_bytes=img_to_png_bytes(crop_img),
            prompt=prompt_with_hint,
            screen_id=screen_id,
            attempt=f"RETRY_{field_key}",
            model=main_model_name,
            schema=ExtractionResponse,
        )
        attempts_meta.append(retry_out["_meta"])
        retry_calls += 1

        candidate = retry_out["fields"].get(field_key) or {}
        if field_key == "tipo":
            candidate["value"] = normalize_tipo(candidate.get("value"))

        result["fields"][field_key] = merge_field_sources(
            field_sources=field_sources,
            field_key=field_key,
            current=current,
            candidate=candidate,
            candidate_source=f"RETRY_{field_key}",
        )


def _aggregate_meta(
    attempts_meta: List[Dict[str, Any]],
    main_model_name: str,
    anchor_model_name: str,
) -> Dict[str, Any]:
    """Sum tokens/cost across all VLM calls for one screen."""
    return {
        "model_main": main_model_name,
        "model_anchor": anchor_model_name,
        "calls": len(attempts_meta),
        "prompt_tokens": sum(int(m.get("prompt_tokens", 0) or 0) for m in attempts_meta),
        "completion_tokens": sum(int(m.get("completion_tokens", 0) or 0) for m in attempts_meta),
        "total_tokens": sum(int(m.get("total_tokens", 0) or 0) for m in attempts_meta),
        "estimated_cost_usd": round(
            sum(float(m.get("estimated_cost_usd", 0.0) or 0.0) for m in attempts_meta), 6
        ),
        "latency_ms": sum(int(m.get("latency_ms", 0) or 0) for m in attempts_meta),
    }


# ============================================================
# Main extraction orchestrator
# ============================================================

def extract_from_screen(
    main_model: BaseChatModel,
    anchor_model: BaseChatModel,
    main_model_name: str,
    anchor_model_name: str,
    path: str,
) -> Dict[str, Any]:
    screen_id, content_img = _prepare_content_image(path)

    # 1) Anchor pass
    anchors = extract_anchors(anchor_model, anchor_model_name, content_img, screen_id)

    # Early exit if anchor confidence too low and STOP_ON_ANCHOR_UNCERTAIN is enabled
    if STOP_ON_ANCHOR_UNCERTAIN:
        if anchors["ndg"]["value"] is None and anchors["denominazione"]["value"] is None:
            return {
                "screen_id": screen_id,
                "fields": {},
                "soggetti": [],
                "_status": "ANCHOR_UNCERTAIN",
                "_attempts": [anchors["_meta"]],
                "_meta_agg": _aggregate_meta(
                    [anchors["_meta"]], main_model_name, anchor_model_name,
                ),
                "_field_sources": {},
            }

    # 2) Main pass
    prompt_with_hint = _build_anchor_hint_prompt(anchors)
    payload = img_to_png_bytes(content_img)

    main_out = call_vlm_with_retry(
        chat_model=main_model,
        image_bytes=payload,
        prompt=prompt_with_hint,
        screen_id=screen_id,
        attempt="CONTENT_MAIN",
        model=main_model_name,
        schema=ExtractionResponse,
    )

    attempts_meta: List[Dict[str, Any]] = [anchors["_meta"], main_out["_meta"]]
    field_sources: Dict[str, str] = {k: "CONTENT_MAIN" for k in FIELD_KEYS}
    result = main_out

    # 3) Merge anchors
    _merge_anchors(result, anchors, field_sources)

    # 4) Post-process tipo
    _postprocess_tipo(result)

    # 5) Retry low-confidence fields
    _retry_low_confidence_fields(
        main_model, main_model_name, content_img, screen_id, prompt_with_hint,
        result, field_sources, attempts_meta,
    )

    # 6) Aggregate meta
    result["_attempts"] = attempts_meta
    result["_meta_agg"] = _aggregate_meta(attempts_meta, main_model_name, anchor_model_name)
    result["_field_sources"] = field_sources

    # 7) Anchor gate status
    ndg_field = result["fields"].get("ndg") or {}
    den_field = result["fields"].get("denominazione") or {}
    if ndg_field.get("value") is None or den_field.get("value") is None:
        result["_status"] = "ANCHOR_UNCERTAIN"
    else:
        result["_status"] = "OK"

    return result
