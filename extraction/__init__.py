"""extraction — AI-powered data extraction from banking screenshots.

Public API re-exports for backward compatibility with app.py and main.py.
"""

__all__ = [
    # Config
    "INPUT_DIR", "GROUND_TRUTH_CSV", "PARALLEL_WORKERS", "PARALLEL_ENABLED",
    "MAX_CALLS_PER_SCREEN", "MODEL_MAIN", "MODEL_ANCHOR", "PRICING_PER_1M",
    "CONTENT_CROP", "HEADER_IN_CONTENT", "FIELD_RETRY_MAP", "ANCHOR_CONF_MIN",
    "DEBUG_SAVE_CROPS", "DEBUG_CROP_DIR", "STOP_ON_ANCHOR_UNCERTAIN",
    "get_screenshot_paths",
    # Fields
    "FIELD_KEYS", "CSV_TO_SCHEMA",
    # Prompts
    "PROMPT", "ANCHOR_PROMPT",
    # Schemas
    "RESPONSE_SCHEMA", "ANCHOR_SCHEMA",
    # Normalization
    "TIPO_MAPPING", "normalize_tipo", "is_nullish", "norm_text", "norm_number_str",
    "safe_field", "safe_set_field", "pick_best", "merge_field_sources",
    "classify_field", "get_pred_value_for_gt_key", "dataset_mismatch_guard",
    # Imaging
    "normalize_image", "crop_relative", "img_to_png_bytes",
    # VLM client
    "estimate_cost_usd", "call_vlm", "call_vlm_with_retry",
    # Pipeline
    "extract_anchors", "extract_from_screen",
    # Evaluation
    "infer_screenshots_from_gt", "load_ground_truth", "eval_outputs",
    "build_debug_report", "print_cost_summary",
    # CLI
    "main", "run_extraction_batch",
]

# Config
from extraction.config import (
    INPUT_DIR,
    GROUND_TRUTH_CSV,
    PARALLEL_WORKERS,
    PARALLEL_ENABLED,
    MAX_CALLS_PER_SCREEN,
    MODEL_MAIN,
    MODEL_ANCHOR,
    PRICING_PER_1M,
    CONTENT_CROP,
    HEADER_IN_CONTENT,
    FIELD_RETRY_MAP,
    ANCHOR_CONF_MIN,
    DEBUG_SAVE_CROPS,
    DEBUG_CROP_DIR,
    STOP_ON_ANCHOR_UNCERTAIN,
    get_screenshot_paths,
)

# Fields
from extraction.fields import FIELD_KEYS, CSV_TO_SCHEMA

# Prompts
from extraction.prompts import PROMPT, ANCHOR_PROMPT

# Schemas
from extraction.schemas import RESPONSE_SCHEMA, ANCHOR_SCHEMA

# Normalization
from extraction.normalization import (
    TIPO_MAPPING,
    normalize_tipo,
    is_nullish,
    norm_text,
    norm_number_str,
    safe_field,
    safe_set_field,
    pick_best,
    merge_field_sources,
    classify_field,
    get_pred_value_for_gt_key,
    dataset_mismatch_guard,
)

# Imaging
from extraction.imaging import normalize_image, crop_relative, img_to_png_bytes

# VLM client
from extraction.vlm_client import estimate_cost_usd, call_vlm, call_vlm_with_retry

# Pipeline
from extraction.pipeline import extract_anchors, extract_from_screen

# Evaluation
from extraction.evaluation import (
    infer_screenshots_from_gt,
    load_ground_truth,
    eval_outputs,
    build_debug_report,
    print_cost_summary,
)

# CLI
from extraction.cli import main, run_extraction_batch
