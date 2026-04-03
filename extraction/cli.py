"""CLI entry point and shared batch extraction runner."""

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Tuple, Callable

from extraction.llm_factory import create_chat_model
from extraction.config import (
    INPUT_DIR,
    GROUND_TRUTH_CSV,
    PARALLEL_ENABLED,
    PARALLEL_WORKERS,
    ANCHOR_CONF_MIN,
    DEBUG_MODE,
    DEBUG_SAVE_CROPS,
    DEBUG_CROP_DIR,
    LLM_PROVIDER,
    LLM_MODEL,
    LLM_MODEL_ANCHOR,
)
from extraction.pipeline import ExtractionPipeline
from extraction.evaluation import (
    load_ground_truth,
    eval_outputs,
    build_debug_report,
    print_cost_summary,
    Evaluator,
)

def _debug_log(message: str) -> None:
    """Print debug logs only when DEBUG_MODE=1."""
    if DEBUG_MODE:
        print(f"[DEBUG] {message}")

def _has_meaningful_value(value: Any) -> bool:
    """Return True when a field value is materially present."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def _extract_page_key(output: Dict[str, Any]) -> Optional[str]:
    """Return the canonical page key, if available."""
    for entry in output.get("canonical_fields") or []:
        page_key = entry.get("page_key")
        if page_key:
            return str(page_key)
    return None


def _output_score(output: Dict[str, Any]) -> Tuple[int, float]:
    """Score an extraction result by filled fields and confidence sum."""
    entries = output.get("canonical_fields") or []
    if not entries:
        entries = [
            {
                "value": field_data.get("value"),
                "confidence": field_data.get("confidence"),
            }
            for field_data in (output.get("fields", {}) or {}).values()
            if isinstance(field_data, dict)
        ]

    filled_fields = 0
    confidence_sum = 0.0
    for entry in entries:
        if _has_meaningful_value(entry.get("value")):
            filled_fields += 1
            confidence_sum += float(entry.get("confidence", 0.0) or 0.0)

    return filled_fields, confidence_sum


def _is_confident_output(output: Dict[str, Any]) -> bool:
    """Return True when the result is safe enough to keep as primary."""
    fields = output.get("fields", {}) or {}
    ndg = fields.get("ndg") or {}
    denominazione = fields.get("denominazione") or {}

    return (
        output.get("_status") == "OK"
        and _has_meaningful_value(ndg.get("value"))
        and _has_meaningful_value(denominazione.get("value"))
        and float(ndg.get("confidence", 0.0) or 0.0) >= ANCHOR_CONF_MIN
        and float(denominazione.get("confidence", 0.0) or 0.0) >= ANCHOR_CONF_MIN
    )


def _deduplicate_same_page_outputs(
    outputs: Dict[str, Dict[str, Any]],
    screen_order: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Keep one result per canonical page, using later screenshots only as fallback."""
    deduped: Dict[str, Dict[str, Any]] = {}
    chosen_screen_by_page: Dict[str, str] = {}

    for screen_id in screen_order:
        output = outputs.get(screen_id)
        if output is None:
            continue

        page_key = _extract_page_key(output)
        if not page_key:
            deduped[screen_id] = output
            continue

        current_screen_id = chosen_screen_by_page.get(page_key)
        if current_screen_id is None:
            chosen_screen_by_page[page_key] = screen_id
            deduped[screen_id] = output
            continue

        current_output = deduped[current_screen_id]
        current_confident = _is_confident_output(current_output)
        candidate_confident = _is_confident_output(output)

        if current_confident:
            _debug_log(
                f"Dedup keep-safe-first page_key={page_key}: "
                f"{current_screen_id} kept, {screen_id} discarded"
            )
            continue

        if not current_confident and candidate_confident:
            deduped.pop(current_screen_id, None)
            chosen_screen_by_page[page_key] = screen_id
            deduped[screen_id] = output
            _debug_log(
                f"Dedup fallback page_key={page_key}: "
                f"{current_screen_id} replaced by {screen_id}"
            )
            continue

        if _output_score(output) > _output_score(current_output):
            deduped.pop(current_screen_id, None)
            chosen_screen_by_page[page_key] = screen_id
            deduped[screen_id] = output
            _debug_log(
                f"Dedup better-score page_key={page_key}: "
                f"{current_screen_id} replaced by {screen_id}"
            )
            continue

        _debug_log(
            f"Dedup keep-existing page_key={page_key}: "
            f"{current_screen_id} kept, {screen_id} discarded"
        )

    return deduped

# ============================================================
# BatchRunner class
# ============================================================

class BatchRunner:
    """Creates models once and runs extraction over a batch of screenshots.

    Thread-safe: the internal ExtractionPipeline is shared across all workers.
    Callbacks (on_complete, on_error) are invoked from the calling thread.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        provider_name: Optional[str] = None,
        model_main: Optional[str] = None,
        model_anchor: Optional[str] = None,
        parallel: bool = True,
        max_workers: int = 4,
    ) -> None:
        effective_provider = provider_name or LLM_PROVIDER
        self._main_model_name = model_main or LLM_MODEL
        self._anchor_model_name = model_anchor or LLM_MODEL_ANCHOR
        self._parallel = parallel
        self._max_workers = max_workers

        # LangChain ChatModels are thread-safe — shared across all workers
        main_model = create_chat_model(
            effective_provider,
            model=self._main_model_name,
            api_key=api_key,
        )
        anchor_model = create_chat_model(
            effective_provider,
            model=self._anchor_model_name,
            api_key=api_key,
        )
        self._pipeline = ExtractionPipeline(
            main_model,
            anchor_model,
            self._main_model_name,
            self._anchor_model_name,
        )
        _debug_log(
            "BatchRunner init: "
            f"provider={effective_provider}, "
            f"model_main={self._main_model_name}, "
            f"model_anchor={self._anchor_model_name}, "
            f"parallel={self._parallel}, "
            f"max_workers={self._max_workers}"
        )

    def run(
        self,
        paths: List[str],
        on_complete: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_error: Optional[Callable[[str, Exception], None]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Extract from all paths, returns {screen_id: result}."""
        existing_paths = [p for p in paths if os.path.exists(p)]
        for p in paths:
            if not os.path.exists(p):
                print(f"Warning: File not found {p}")

        outputs: Dict[str, Dict[str, Any]] = {}
        _debug_log(
            f"Batch start: requested_paths={len(paths)}, existing_paths={len(existing_paths)}"
        )

        def _worker(path: str) -> Tuple[str, Dict[str, Any]]:
            screen_id = os.path.splitext(os.path.basename(path))[0]
            _debug_log(f"Extracting screen_id={screen_id} path={path}")
            return screen_id, self._pipeline.extract_from_screen(path)

        if self._parallel and self._max_workers > 1 and len(existing_paths) > 1:
            print(
                f"Parallel enabled: workers={self._max_workers}, screens={len(existing_paths)}"
            )
            with ThreadPoolExecutor(max_workers=self._max_workers) as ex:
                futs = {ex.submit(_worker, p): p for p in existing_paths}
                for fut in as_completed(futs):
                    p = futs[fut]
                    screen_id = os.path.splitext(os.path.basename(p))[0]
                    try:
                        sid, out = fut.result()
                        outputs[sid] = out
                        _debug_log(f"Completed screen_id={sid}")
                        if on_complete:
                            on_complete(sid, out)
                        else:
                            print(f"Done {sid}")
                    except Exception as e:
                        _debug_log(f"Error screen_id={screen_id}: {e}")
                        if on_error:
                            on_error(screen_id, e)
                        else:
                            print(f"ERROR extracting {screen_id}: {e}")
        else:
            for p in existing_paths:
                screen_id = os.path.splitext(os.path.basename(p))[0]
                print(f"Extracting {screen_id} ...")
                try:
                    outputs[screen_id] = self._pipeline.extract_from_screen(p)
                    _debug_log(f"Completed screen_id={screen_id}")
                    if on_complete:
                        on_complete(screen_id, outputs[screen_id])
                except Exception as e:
                    _debug_log(f"Error screen_id={screen_id}: {e}")
                    if on_error:
                        on_error(screen_id, e)
                    else:
                        raise

        # TEMP TEST: keep all outputs until page_key mapping is validated
        # screen_order = [
        #     os.path.splitext(os.path.basename(path))[0]
        #     for path in existing_paths
        # ]
        # outputs = _deduplicate_same_page_outputs(outputs, screen_order)

        _debug_log(f"Batch completed: outputs={len(outputs)}")
        return outputs

# ============================================================
# Backward-compatible module-level wrapper
# ============================================================

def run_extraction_batch(
    paths: List[str],
    *,
    api_key: Optional[str] = None,
    provider_name: Optional[str] = None,
    model_main: Optional[str] = None,
    model_anchor: Optional[str] = None,
    parallel: bool = True,
    max_workers: int = 4,
    on_complete: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    on_error: Optional[Callable[[str, Exception], None]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Backward-compatible wrapper — delegates to BatchRunner.

    Shared by CLI (main) and Streamlit (app.py). Callbacks (on_complete,
    on_error) are invoked from the calling thread, not from worker threads.
    """
    runner = BatchRunner(
        api_key=api_key,
        provider_name=provider_name,
        model_main=model_main,
        model_anchor=model_anchor,
        parallel=parallel,
        max_workers=max_workers,
    )
    return runner.run(paths, on_complete=on_complete, on_error=on_error)


# ============================================================
# CLI entry point
# ============================================================

def main() -> None:
    if not os.path.exists(GROUND_TRUTH_CSV):
        raise FileNotFoundError(f"Ground truth CSV not found: {GROUND_TRUTH_CSV}")

    gt = load_ground_truth(GROUND_TRUTH_CSV)
    evaluator = Evaluator(gt)

    # Process all images in INPUT_DIR (supports 9+ images, not just those in GT)
    all_files = os.listdir(INPUT_DIR)
    screenshot_paths = [
        os.path.join(INPUT_DIR, f) for f in all_files
        if f.lower().endswith(('.png', '.jpg', '.jpeg'))
    ]
    screenshot_paths.sort()

    if not screenshot_paths:
        print(f"No images found in {INPUT_DIR}")
        return

    runner = BatchRunner(parallel=PARALLEL_ENABLED, max_workers=PARALLEL_WORKERS)
    outputs = runner.run(screenshot_paths)

    # Save outputs
    outputs_path = os.path.join(INPUT_DIR, "poc_outputs_improved.json")
    os.makedirs(os.path.dirname(outputs_path), exist_ok=True)
    with open(outputs_path, "w", encoding="utf-8") as f:
        json.dump(outputs, f, ensure_ascii=False, indent=2)

    # Evaluate & report
    evaluator.eval(outputs)

    debug_csv_path = os.path.join(INPUT_DIR, "poc_debug_improved.csv")
    evaluator.build_debug_report(outputs, debug_csv_path)
    evaluator.print_cost_summary(outputs)

    print(f"Saved outputs: {outputs_path}")
    print(f"Saved debug report: {debug_csv_path}")
    if DEBUG_SAVE_CROPS:
        print(f"Saved debug crops to: {DEBUG_CROP_DIR}")
