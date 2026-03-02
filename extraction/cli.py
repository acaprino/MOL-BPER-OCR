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
    DEBUG_SAVE_CROPS,
    DEBUG_CROP_DIR,
    LLM_PROVIDER,
    get_model_main,
    get_model_anchor,
    get_screenshot_paths,
)
from extraction.pipeline import extract_from_screen
from extraction.evaluation import (
    load_ground_truth,
    eval_outputs,
    build_debug_report,
    print_cost_summary,
)


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
    """Run extraction on a batch of screenshot paths.

    Shared by CLI (main) and Streamlit (app.py). Callbacks (on_complete,
    on_error) are invoked from the calling thread, not from worker threads.
    """
    effective_provider = provider_name or LLM_PROVIDER
    main_model_name = model_main or get_model_main(effective_provider)
    anchor_model_name = model_anchor or get_model_anchor(effective_provider)

    # LangChain ChatModels are thread-safe — shared across all workers
    main_model = create_chat_model(effective_provider, model=main_model_name, api_key=api_key)
    anchor_model = create_chat_model(effective_provider, model=anchor_model_name, api_key=api_key)

    existing_paths = [p for p in paths if os.path.exists(p)]
    missing_paths = [p for p in paths if not os.path.exists(p)]
    for p in missing_paths:
        print(f"Warning: File not found {p}")

    outputs: Dict[str, Dict[str, Any]] = {}

    def _worker(path: str) -> Tuple[str, Dict[str, Any]]:
        screen_id = os.path.splitext(os.path.basename(path))[0]
        return screen_id, extract_from_screen(
            main_model, anchor_model, main_model_name, anchor_model_name, path,
        )

    if parallel and max_workers > 1 and len(existing_paths) > 1:
        print(f"Parallel enabled: workers={max_workers}, screens={len(existing_paths)}")
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(_worker, p): p for p in existing_paths}
            for fut in as_completed(futs):
                p = futs[fut]
                screen_id = os.path.splitext(os.path.basename(p))[0]
                try:
                    sid, out = fut.result()
                    outputs[sid] = out
                    if on_complete:
                        on_complete(sid, out)
                    else:
                        print(f"Done {sid}")
                except Exception as e:
                    if on_error:
                        on_error(screen_id, e)
                    else:
                        print(f"ERROR extracting {screen_id}: {e}")
    else:
        for p in existing_paths:
            screen_id = os.path.splitext(os.path.basename(p))[0]
            print(f"Extracting {screen_id} ...")
            if on_error:
                try:
                    outputs[screen_id] = extract_from_screen(
                        main_model, anchor_model, main_model_name, anchor_model_name, p,
                    )
                    if on_complete:
                        on_complete(screen_id, outputs[screen_id])
                except Exception as e:
                    on_error(screen_id, e)
            else:
                outputs[screen_id] = extract_from_screen(
                    main_model, anchor_model, main_model_name, anchor_model_name, p,
                )
                if on_complete:
                    on_complete(screen_id, outputs[screen_id])

    return outputs


def main() -> None:
    if not os.path.exists(GROUND_TRUTH_CSV):
        raise FileNotFoundError(f"Ground truth CSV not found: {GROUND_TRUTH_CSV}")

    gt = load_ground_truth(GROUND_TRUTH_CSV)
    screenshot_paths = get_screenshot_paths(gt)

    outputs = run_extraction_batch(
        screenshot_paths,
        parallel=PARALLEL_ENABLED,
        max_workers=PARALLEL_WORKERS,
    )

    # Save outputs
    outputs_path = os.path.join(INPUT_DIR, "poc_outputs_improved.json")
    with open(outputs_path, "w", encoding="utf-8") as f:
        json.dump(outputs, f, ensure_ascii=False, indent=2)

    # Evaluate & report
    eval_outputs(outputs, gt)

    debug_csv_path = os.path.join(INPUT_DIR, "poc_debug_improved.csv")
    build_debug_report(outputs, gt, debug_csv_path)
    print_cost_summary(outputs)

    print(f"Saved outputs: {outputs_path}")
    print(f"Saved debug report: {debug_csv_path}")
    if DEBUG_SAVE_CROPS:
        print(f"Saved debug crops to: {DEBUG_CROP_DIR}")
