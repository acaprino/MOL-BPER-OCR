"""extraction — AI-powered data extraction from banking screenshots.

Public API re-exports for backward compatibility with main.py and gui_app.py.
"""

import warnings
# Suppress Pydantic V1 / LangChain compatibility warnings (mostly relevant for Python 3.14+)
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", category=UserWarning, module="langchain_core")

__all__ = [
    # Config
    "INPUT_DIR", "GROUND_TRUTH_CSV", "PARALLEL_WORKERS", "PARALLEL_ENABLED",
    "MAX_CALLS_PER_SCREEN", "PRICING_PER_1M",
    "CONTENT_CROP", "HEADER_IN_CONTENT", "ANCHOR_CONF_MIN",
    "DEBUG_SAVE_CROPS", "DEBUG_CROP_DIR", "STOP_ON_ANCHOR_UNCERTAIN",
    "LLM_PROVIDER", "LLM_MODEL", "LLM_MODEL_ANCHOR", "LLM_THINKING_LEVEL",
    "PROVIDER_MODELS",
    # LLM factory
    "create_chat_model",
    # Fields
    "FIELD_KEYS", "CSV_TO_SCHEMA",
    # Prompts
    "PROMPT", "ANCHOR_PROMPT",
    # Schemas
    "FieldResult", "Soggetto", "ExtractionResponse", "AnchorResponse",
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
    "ExtractionPipeline", "extract_anchors", "extract_from_screen",
    # Evaluation
    "Evaluator",
    "load_ground_truth", "eval_outputs",
    "build_debug_report", "print_cost_summary", "export_to_csv",
    # CLI
    "BatchRunner", "main", "run_extraction_batch",
]

# Config
from extraction.config import (
    INPUT_DIR,
    GROUND_TRUTH_CSV,
    PARALLEL_WORKERS,
    PARALLEL_ENABLED,
    MAX_CALLS_PER_SCREEN,
    PRICING_PER_1M,
    CONTENT_CROP,
    HEADER_IN_CONTENT,
    ANCHOR_CONF_MIN,
    DEBUG_SAVE_CROPS,
    DEBUG_CROP_DIR,
    STOP_ON_ANCHOR_UNCERTAIN,
    LLM_PROVIDER,
    LLM_MODEL,
    LLM_MODEL_ANCHOR,
    LLM_THINKING_LEVEL,
    PROVIDER_MODELS,
)

# LLM factory
from extraction.llm_factory import create_chat_model

# Fields
from extraction.fields import FIELD_KEYS, CSV_TO_SCHEMA

# Prompts
from extraction.prompts import PROMPT, ANCHOR_PROMPT

# Schemas
from extraction.schemas import (
    FieldResult,
    Soggetto,
    ExtractionResponse,
    AnchorResponse,
    RESPONSE_SCHEMA,
    ANCHOR_SCHEMA,
)

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
from extraction.pipeline import ExtractionPipeline, extract_anchors, extract_from_screen

# Evaluation
from extraction.evaluation import (
    Evaluator,
    load_ground_truth,
    eval_outputs,
    build_debug_report,
    print_cost_summary,
    export_to_csv,
)

# CLI
from extraction.cli import BatchRunner, main, run_extraction_batch
