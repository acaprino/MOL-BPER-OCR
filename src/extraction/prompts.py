"""Prompt definitions for VLM extraction passes.

The texts themselves live in `prompts/*.json`; this module resolves them once at
import time (see `prompt_store` at the repo root) and keeps the historical
constant names the pipeline call sites use.
"""

from typing import Dict

from prompt_store import get_text

PROMPT = get_text("extraction_main")

ANCHOR_PROMPT = get_text("extraction_anchor")

RETRY_PROMPT_HEADER = get_text("extraction_retry_header")

RETRY_PROMPT_BODY = get_text("extraction_retry_body")

RETRY_PROMPT_FOOTER = get_text("extraction_retry_footer")

# Area mapping for retry prompts
FIELD_RETRY_PROMPTS: Dict[str, str] = {
    "HEADER": RETRY_PROMPT_HEADER,
    "BODY": RETRY_PROMPT_BODY,
    "FOOTER": RETRY_PROMPT_FOOTER,
}
