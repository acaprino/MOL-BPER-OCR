"""Multi-pass extraction pipeline: anchor -> main -> conditional retry."""
import re
from typing import Dict, Any, List, Tuple, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageEnhance
from langchain_core.language_models import BaseChatModel
from extraction.canonical_mapping import build_canonical_field_entries


from extraction.config import (
    HEADER_IN_CONTENT,
    ANCHOR_CONF_MIN,
    RETRY_CONF_MIN,
    MAX_CALLS_PER_SCREEN,
    MAX_IMAGE_LONG_SIDE,
    STOP_ON_ANCHOR_UNCERTAIN,
    RETRY_AREAS,
    AREA_TO_FIELDS,
)
from extraction.fields import FIELD_KEYS
from extraction.prompts import (
    PROMPT,
    ANCHOR_PROMPT,
    FIELD_RETRY_PROMPTS
)
from prompt_store import get_part
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
    clamp_long_side,
    crop_relative,
    select_content_crop,
    img_to_png_bytes,
    save_debug_crop,
    screen_id_from_path,
)
from extraction.vlm_client import call_vlm_with_retry

# Hint lines appended to the main-pass prompt with the anchor values already read.
ANCHOR_HINT_NDG = get_part("extraction_anchor_hints", "ndg")
ANCHOR_HINT_DENOMINAZIONE = get_part("extraction_anchor_hints", "denominazione")


# ============================================================
# ExtractionPipeline class
# ============================================================

class ExtractionPipeline:
    """Multi-pass extraction pipeline: anchor → main → conditional retry.

    Thread-safe: LangChain ChatModel instances are shared across workers.
    Create once per batch and reuse across calls to extract_from_screen().
    """

    def __init__(
        self,
        main_model: BaseChatModel,
        anchor_model: BaseChatModel,
        main_model_name: str,
        anchor_model_name: str,
    ) -> None:
        self._main_model = main_model
        self._anchor_model = anchor_model
        self._main_model_name = main_model_name
        self._anchor_model_name = anchor_model_name

    # --------------------------------------------------------
    # Public interface
    # --------------------------------------------------------

    def extract_anchors(
        self, content_img: Image.Image, screen_id: str, *, calibrated: bool = True
    ) -> Dict[str, Any]:
        """Pass 1: extract NDG + Denominazione.

        On the calibrated family the identifiers live in the top band of the
        content area, so the pass reads HEADER_IN_CONTENT only. Off calibration
        no fixed band contains them: measured on a real 1296x1027 operator
        window, the top 22% holds only browser chrome and tab bar, and at 35%
        the NDG bar appears half-cut. Banding an uncalibrated image is the
        content-crop amputation one level down, so there the pass reads the
        whole image and pays the larger payload instead.
        """
        header_img = crop_relative(content_img, HEADER_IN_CONTENT) if calibrated else content_img
        save_debug_crop(header_img, screen_id, "HEADER_IN_CONTENT" if calibrated else "HEADER_FULL")

        payload = img_to_png_bytes(header_img)
        out = call_vlm_with_retry(
            chat_model=self._anchor_model,
            image_bytes=payload,
            prompt=ANCHOR_PROMPT,
            screen_id=screen_id,
            attempt="ANCHOR_HEADER",
            model=self._anchor_model_name,
            schema=AnchorResponse,
        )

        fields = out.get("fields", {})
        ndg = safe_field(fields, "ndg")
        den = safe_field(fields, "denominazione")

        # Gate: zero-out low-confidence anchors on the returned copies.
        # (Must mutate ndg/den directly — they are the values returned below.)
        if ndg.get("confidence", 0.0) < ANCHOR_CONF_MIN:
            ndg["value"] = None
        if den.get("confidence", 0.0) < ANCHOR_CONF_MIN:
            den["value"] = None

        return {
            "ndg": ndg,
            "denominazione": den,
            "_meta": out["_meta"],
        }

    def extract_from_image(
        self, img: Image.Image, screen_id: str, *, allow_content_crop: bool = False
    ) -> Dict[str, Any]:
        """Full multi-pass extraction for a single PIL image.

        `allow_content_crop` defaults to False because this is the live entry
        point: every operator has a different window resolution, so no framing
        arriving here is ever the one CONTENT_CROP was calibrated on. Even an
        aspect that matches by coincidence is a false positive: the navigator is
        laid out in CSS pixels, and on any window not rendered at the reference's
        848px width its share of the width differs, so the calibrated fractions
        amputate columns regardless of aspect. Only extract_from_screen(), which
        serves the reference files on disk, opts in; even then the aspect guard
        still has to agree (ADR 0009).
        """
        # Bound oversized raw frames (edge-agent path skips normalize_image);
        # no-op for the already-normalized CLI path.
        img = clamp_long_side(img, MAX_IMAGE_LONG_SIDE)
        crop_box = select_content_crop(img.size) if allow_content_crop else None
        calibrated = crop_box is not None
        content_img = crop_relative(img, crop_box) if calibrated else img
        # Distinct debug names: a full frame saved as "CONTENT" is indistinguishable
        # from a genuine content crop when recalibrating fractions from disk.
        save_debug_crop(content_img, screen_id, "CONTENT" if calibrated else "CONTENT_FULL")

        # 1) Anchor pass
        anchors = self.extract_anchors(content_img, screen_id, calibrated=calibrated)

        if STOP_ON_ANCHOR_UNCERTAIN:
            if is_nullish(anchors["ndg"]["value"]) and is_nullish(anchors["denominazione"]["value"]):
                return {
                    "screen_id": screen_id,
                    "fields": {},
                    "soggetti": [],
                    "fidi": [],
                    "garanzie": [],
                    "_status": "ANCHOR_UNCERTAIN",
                    "_content_crop": "calibrated" if calibrated else "full-frame",
                    "_attempts": [anchors["_meta"]],
                    "_meta_agg": self._aggregate_meta([anchors["_meta"]]),
                    "_field_sources": {},
                }

        # 2) Main pass
        prompt_with_hint = self._build_anchor_hint_prompt(anchors)
        payload = img_to_png_bytes(content_img)

        main_out = call_vlm_with_retry(
            chat_model=self._main_model,
            image_bytes=payload,
            prompt=prompt_with_hint,
            screen_id=screen_id,
            attempt="CONTENT_MAIN",
            model=self._main_model_name,
            schema=ExtractionResponse,
        )

        attempts_meta: List[Dict[str, Any]] = [anchors["_meta"], main_out["_meta"]]
        field_sources: Dict[str, str] = {k: "CONTENT_MAIN" for k in FIELD_KEYS}
        table_sources: Dict[str, str] = {k: "CONTENT_MAIN" for k in ("soggetti", "fidi", "garanzie")}
        result = main_out

        # 3) Merge anchors & post-process
        self._merge_anchors(result, anchors, field_sources)
        self._postprocess_tipo(result)

        # 4) Retry areas
        self._retry_areas(content_img, screen_id, result, field_sources, attempts_meta,
                          calibrated=calibrated, table_sources=table_sources)

        # 5) Coherence check
        self._coherence_check(result)

        # 6) Aggregate meta
        result["_attempts"] = attempts_meta
        result["_meta_agg"] = self._aggregate_meta(attempts_meta)
        result["_field_sources"] = field_sources
        result["_content_crop"] = "calibrated" if calibrated else "full-frame"

        # 7) Flatten soggetti for flat evaluation (CSV compatibility)
        soggetti = result.get("soggetti", [])
        for i, s in enumerate(soggetti[:4]):
            idx = i + 1
            conf = s.get("confidence", 0.0)
            for key in ("ndg", "denominazione", "ruolo"):
                field_key = f"{key}_{idx}"
                candidate = {"value": s.get(key), "confidence": conf, "section": "soggetti_table"}
                result["fields"][field_key] = merge_field_sources(
                    field_sources=field_sources,
                    field_key=field_key,
                    current=result["fields"].get(field_key) or {},
                    candidate=candidate,
                    candidate_source=table_sources["soggetti"],
                )
        
        result["canonical_fields"] = build_canonical_field_entries(
            result.get("fields", {})
        )    

        # 8) Status
        ndg_field = result["fields"].get("ndg") or {}
        den_field = result["fields"].get("denominazione") or {}
        result["_status"] = (
            "OK" if not is_nullish(ndg_field.get("value")) and not is_nullish(den_field.get("value"))
            else "ANCHOR_UNCERTAIN"
        )

        return result

    def extract_from_screen(self, path: str) -> Dict[str, Any]:
        """Full multi-pass extraction for a single screenshot path."""
        img = Image.open(path).convert("RGB")
        img = normalize_image(img)
        screen_id = screen_id_from_path(path)
        return self.extract_from_image(img, screen_id, allow_content_crop=True)

    # --------------------------------------------------------
    # Private helpers
    # --------------------------------------------------------

    @staticmethod
    def _build_anchor_hint_prompt(anchors: Dict[str, Any]) -> str:
        hints: List[str] = []
        if not is_nullish(anchors["ndg"]["value"]):
            hints.append(ANCHOR_HINT_NDG.format(value=anchors["ndg"]["value"]))
        if not is_nullish(anchors["denominazione"]["value"]):
            hints.append(ANCHOR_HINT_DENOMINAZIONE.format(value=anchors["denominazione"]["value"]))
        return PROMPT + ("\n\n" + "\n".join(hints) if hints else "")

    @staticmethod
    def _merge_anchors(result: Dict[str, Any], anchors: Dict[str, Any], field_sources: Dict[str, str]) -> None:
        for k in ("ndg", "denominazione"):
            if not is_nullish(anchors[k]["value"]):
                result["fields"][k] = anchors[k]
                field_sources[k] = "ANCHOR_HEADER"

    @staticmethod
    def _postprocess_tipo(result: Dict[str, Any]) -> None:
        tipo_field = (result.get("fields", {}) or {}).get("tipo")
        if isinstance(tipo_field, dict):
            tipo_field["value"] = normalize_tipo(tipo_field.get("value"))
            result["fields"]["tipo"] = tipo_field

    @staticmethod
    def _merge_tables(result: Dict[str, Any], retry_out: Dict[str, Any], area_name: str,
                      *, calibrated: bool = True,
                      table_sources: Dict[str, str] | None = None) -> None:
        if area_name != "BODY":
            return
        for tbl in ["soggetti", "fidi", "garanzie"]:
            new_data = retry_out.get(tbl) or []
            old_data = result.get(tbl, [])

            # An empty subject table is also normal on pages without subjects.
            # Seed it only with confident, identified rows; discard weak or
            # anonymous rows independently so they cannot reach the flatten.
            if tbl == "soggetti" and not old_data:
                new_data = [
                    row for row in new_data
                    if row.get("confidence", 0.0) >= RETRY_CONF_MIN
                    and (not is_nullish(row.get("ndg"))
                         or not is_nullish(row.get("denominazione")))
                ]

            # Off calibration the BODY crop is a band of the raw window and
            # includes the navigator column, so a longer retry table may be
            # padded with rows read out of menu text. There it may only fill an
            # empty table, never replace one: a fabricated soggetti row flattens
            # into ndg_N and reaches the consolidated practice looking real.
            if not calibrated:
                if new_data and not old_data:
                    result[tbl] = new_data
                    if table_sources is not None:
                        table_sources[tbl] = f"RETRY_{area_name}"
                continue

            new_conf = sum(row.get("confidence", 0) for row in new_data) / max(1, len(new_data))
            old_conf = sum(row.get("confidence", 0) for row in old_data) / max(1, len(old_data))

            if len(new_data) > len(old_data) or (len(new_data) == len(old_data) and new_conf > old_conf):
                result[tbl] = new_data
                if table_sources is not None:
                    table_sources[tbl] = f"RETRY_{area_name}"

    def _retry_areas(
        self,
        content_img: Image.Image,
        screen_id: str,
        result: Dict[str, Any],
        field_sources: Dict[str, str],
        attempts_meta: List[Dict[str, Any]],
        *,
        calibrated: bool = True,
        table_sources: Dict[str, str] | None = None,
    ) -> None:
        areas_to_retry: Set[str] = set()
        for area, fields in AREA_TO_FIELDS.items():
            for f in fields:
                field_data = safe_field(result["fields"], f)
                if is_nullish(field_data.get("value")) or field_data.get("confidence", 0.0) < RETRY_CONF_MIN:
                    areas_to_retry.add(area)
                    break

        if not areas_to_retry:
            return

        allowed_retries = max(0, MAX_CALLS_PER_SCREEN - 2)  # 1 anchor + 1 main already done
        # Select in priority order (HEADER first), NOT alphabetically: HEADER
        # owns the identity/status fields that drive _status and the mismatch
        # guard, so it must be retried before the budget runs out instead of
        # being dropped by a sort. AREA_TO_FIELDS declaration order = priority.
        areas_to_retry_list = [a for a in AREA_TO_FIELDS if a in areas_to_retry][:allowed_retries]

        # No retry budget left (e.g. MAX_CALLS_PER_SCREEN <= 2): keep main-pass
        # results. Guarding here avoids ThreadPoolExecutor(max_workers=0), which
        # raises ValueError.
        if not areas_to_retry_list:
            return

        def _do_retry(area_name: str) -> Tuple[str, Dict[str, Any]]:
            crop_img = crop_relative(content_img, RETRY_AREAS[area_name])
            if area_name == "BODY":
                crop_img = ImageEnhance.Contrast(crop_img).enhance(1.3)
                crop_img = ImageEnhance.Sharpness(crop_img).enhance(2.5)
            elif area_name == "HEADER":
                crop_img = ImageEnhance.Contrast(crop_img).enhance(1.4)
                crop_img = ImageEnhance.Sharpness(crop_img).enhance(3.5)
            save_debug_crop(crop_img, screen_id, f"RETRY_{area_name}")
            return area_name, call_vlm_with_retry(
                chat_model=self._main_model,
                image_bytes=img_to_png_bytes(crop_img),
                prompt=FIELD_RETRY_PROMPTS.get(area_name, PROMPT),
                screen_id=screen_id,
                attempt=f"RETRY_{area_name}",
                model=self._main_model_name,
                schema=ExtractionResponse,
            )

        with ThreadPoolExecutor(max_workers=len(areas_to_retry_list)) as executor:
            future_to_area = {executor.submit(_do_retry, a): a for a in areas_to_retry_list}
            for future in as_completed(future_to_area):
                try:
                    area_name, retry_out = future.result()
                except Exception as e:
                    failed_area = future_to_area[future]
                    print(f"Warning: retry {failed_area} for {screen_id} failed (keeping main-pass results): {e}")
                    continue

                attempts_meta.append(retry_out["_meta"])

                for f in AREA_TO_FIELDS[area_name]:
                    candidate = retry_out["fields"].get(f) or {}
                    if f == "tipo":
                        candidate["value"] = normalize_tipo(candidate.get("value"))
                    current = result["fields"].get(f) or {}
                    result["fields"][f] = merge_field_sources(
                        field_sources=field_sources,
                        field_key=f,
                        current=current,
                        candidate=candidate,
                        candidate_source=f"RETRY_{area_name}",
                    )

                self._merge_tables(result, retry_out, area_name, calibrated=calibrated,
                                   table_sources=table_sources)

    @staticmethod
    def _coherence_check(result: Dict[str, Any]) -> None:
        flds = result.get("fields", {})
        if not flds:
            return

        t_evid_b = safe_field(flds, "tooltip_evidenze_b")
        if not is_nullish(t_evid_b.get("value")):
            curr_evid = safe_field(flds, "evidenze")
            val_evid = str(curr_evid.get("value") or "")
            if is_nullish(val_evid) or re.match(r"^\d+(\.\d+)?$", val_evid):
                safe_set_field(flds, "evidenze", value="B", confidence=t_evid_b.get("confidence"))

        t_tipo_bmb = safe_field(flds, "tooltip_descrizione_bmb")
        if not is_nullish(t_tipo_bmb.get("value")):
            curr_tipo = safe_field(flds, "tipo")
            if is_nullish(curr_tipo.get("value")):
                safe_set_field(flds, "tipo", value="BMB", confidence=t_tipo_bmb.get("confidence"))

    def _aggregate_meta(self, attempts_meta: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "model_main": self._main_model_name,
            "model_anchor": self._anchor_model_name,
            "calls": len(attempts_meta),
            "prompt_tokens": sum(int(m.get("prompt_tokens", 0) or 0) for m in attempts_meta),
            "completion_tokens": sum(int(m.get("completion_tokens", 0) or 0) for m in attempts_meta),
            "total_tokens": sum(int(m.get("total_tokens", 0) or 0) for m in attempts_meta),
            "estimated_cost_usd": round(sum(float(m.get("estimated_cost_usd", 0.0) or 0.0) for m in attempts_meta), 6),
            "latency_ms": sum(int(m.get("latency_ms", 0) or 0) for m in attempts_meta),
        }


# ============================================================
# Backward-compatible module-level wrappers
# ============================================================

def extract_anchors(
    anchor_model: BaseChatModel,
    anchor_model_name: str,
    content_img: Image.Image,
    screen_id: str,
) -> Dict[str, Any]:
    pipeline = ExtractionPipeline(anchor_model, anchor_model, anchor_model_name, anchor_model_name)
    return pipeline.extract_anchors(content_img, screen_id)


def extract_from_screen(
    main_model: BaseChatModel,
    anchor_model: BaseChatModel,
    main_model_name: str,
    anchor_model_name: str,
    path: str,
) -> Dict[str, Any]:
    pipeline = ExtractionPipeline(main_model, anchor_model, main_model_name, anchor_model_name)
    return pipeline.extract_from_screen(path)
