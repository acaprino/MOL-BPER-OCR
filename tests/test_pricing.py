"""Every model the project ships as its default must have a price.

estimate_cost_usd() returns 0.0 for a model absent from PRICING_PER_1M, so a
default switched to an unpriced model makes every cost report read $0.00 with
no error. The 2026-09-29 baseline on gemini-3.8-flash reported $0.0000 for
247k tokens that actually cost $0.34.
"""

from pathlib import Path

import pytest
from dotenv import dotenv_values

from extraction.vlm_client import estimate_cost_usd

REPO_ROOT = Path(__file__).resolve().parent.parent
SHIPPED_ENV_FILES = ["edge-agent/defaults/env.template", ".env.example"]


@pytest.mark.parametrize("env_file", SHIPPED_ENV_FILES)
def test_shipped_default_model_has_a_price(env_file: str) -> None:
    model = dotenv_values(REPO_ROOT / env_file)["LLM_MODEL"]

    assert estimate_cost_usd(model, 1_000_000, 1_000_000) > 0, model
