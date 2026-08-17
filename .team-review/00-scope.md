# Review Scope

- **Target**: `extraction/` (directory, full-module review — no diff range)
- **Invoked as**: /agent-teams:team-review extraction/
- **Flags**: reviewers=auto, deep=false (deep-dive lite), skip_interconnect=false, fast=false, rigorous=false
- **Base branch**: develop (current), working tree clean
- **Date**: 2026-07-21

## Files in scope (15 Python files, 2,442 lines)

| File | Lines | Role |
|---|---|---|
| `extraction/pipeline.py` | 365 | `ExtractionPipeline`: anchor → main → retry multi-pass orchestration |
| `extraction/cli.py` | 352 | `BatchRunner`, `run_extraction_batch()` (shared CLI + Tkinter GUI), `main()` |
| `extraction/evaluation.py` | 282 | `eval_outputs()`, `load_ground_truth()`, `print_cost_summary()` |
| `extraction/field_definitions.py` | 262 | Canonical field → display-name / page-key resolution |
| `extraction/vlm_client.py` | 258 | `call_vlm()`, `call_vlm_with_retry()`, `estimate_cost_usd()` |
| `extraction/normalization.py` | 189 | Normalization, `classify_field()`, `pick_best()`, `dataset_mismatch_guard()` |
| `extraction/fields.py` | 138 | `FIELD_KEYS` (45 fields), `CSV_TO_SCHEMA` |
| `extraction/__init__.py` | 126 | Public API re-exports |
| `extraction/config.py` | 109 | Import-time env config, crop constants, pricing, `AREA_TO_FIELDS` |
| `extraction/prompts.py` | 78 | Italian VLM prompts |
| `extraction/llm_factory.py` | 77 | `create_chat_model()` provider factory |
| `extraction/schemas.py` | 71 | Pydantic models |
| `extraction/page_definitions.py` | 51 | Canonical page names |
| `extraction/imaging.py` | 42 | `normalize_image()`, `crop_relative()` |
| `extraction/canonical_mapping.py` | 42 | `build_canonical_field_entries()` |

## Context notes

- Language: Python 3.12/3.13. Domain: Vision-LLM extraction from Italian banking screenshots (LangChain, OpenAI/Gemini).
- Known documented quirks (CLAUDE.md): ineffective anchor confidence gate, retry coverage gap for `creazione`/`tooltip_*`, soggetti flatten overwrites without `_field_sources` update, `_deduplicate_same_page_outputs()` call commented out, no startup guards on field-map consistency, silent $0.00 pricing for unknown models.
- Consumers outside scope (call sites to respect): `main.py`, `gui_app.py`, `edge-agent/local_extraction_client.py`.
