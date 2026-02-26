# CLAUDE.md — poc-data-extraction

## Project Overview

AI-powered data extraction from Italian banking screenshots using OpenAI Vision API (GPT-4o).
Extracts 19 structured fields from UI screenshots via a multi-pass VLM pipeline, evaluates
accuracy against ground truth CSV, and reports per-field metrics and cost breakdowns.

**Tech stack:** Python 3.8+, OpenAI Vision API, Pillow, Pandas, Streamlit
**Entry points:** `main.py` (CLI batch), `app.py` (Streamlit web UI)

## Architecture

### Multi-Pass Extraction Pipeline

Each screenshot goes through three stages in `extract_from_screen()`:

1. **Anchor extraction** — `extract_anchors()` crops the header region and extracts only NDG + DENOMINAZIONE with high confidence (>= 0.95). Gates further processing.
2. **Main extraction** — Full content crop sent to VLM with anchor hints ("NDG atteso: {value}"). Extracts all 19 fields + soggetti array in one call.
3. **Conditional retry** — Only retries fields that are nullish or low confidence (< 0.55). Each field has a dedicated crop region in `FIELD_RETRY_MAP`. Best value selected via `pick_best()`.

### Dual Mode

- **CLI** (`python main.py`): Batch-processes all screens in `INPUT_DIR`, outputs JSON results + debug CSV, prints accuracy metrics and cost summary.
- **Streamlit** (`streamlit run app.py`): Web UI with file upload, per-screen results display, confidence tables, and JSON export.

## Running the Project

```bash
# CLI mode — processes all screenshots in INPUT_DIR
export OPENAI_API_KEY="sk-..."
python main.py

# Streamlit mode — launches web UI on localhost:8501
streamlit run app.py
```

**Required:** `OPENAI_API_KEY` must be set (or entered in Streamlit sidebar).

## Configuration (Environment Variables)

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | OpenAI API credential |
| `OPENAI_MODEL` | `gpt-4o` | Model for main extraction |
| `OPENAI_MODEL_ANCHOR` | same as `OPENAI_MODEL` | Model for anchor pass |
| `INPUT_DIR` | `mnt/data` | Data directory (screenshots + ground truth) |
| `SCREENSHOT_DIR` | same as `INPUT_DIR` | Screenshot location |
| `PARALLEL_WORKERS` | `4` | Thread pool size |
| `PARALLEL_ENABLED` | `1` | Enable parallel processing (`0` to disable) |
| `MAX_CALLS_PER_SCREEN` | `4` | Max VLM calls per screen |
| `ANCHOR_CONF_MIN` | `0.95` | Minimum confidence for anchor acceptance |
| `STOP_ON_ANCHOR_UNCERTAIN` | `0` | Stop processing if anchor confidence is low |
| `DEBUG_SAVE_CROPS` | `0` | Save intermediate crop images to disk |

## Code Conventions

### Type Annotations
All functions must have full type annotations on parameters and return types:
```python
def call_vlm(client: OpenAI, img: Image.Image, ...) -> Dict[str, Any]: ...
def normalize_image(img: Image.Image, long_side: int = 1800) -> Image.Image: ...
```

### Naming
- **Constants:** `UPPER_SNAKE_CASE` — `FIELD_KEYS`, `CONTENT_CROP`, `MODEL_MAIN`
- **Private helpers:** `_leading_underscore` — `_extract_date_ddmmyyyy()`, `_norm_company()`
- **Schemas:** `UPPER_SNAKE_CASE` — `RESPONSE_SCHEMA`, `ANCHOR_SCHEMA`

### Section Markers
Code sections are delimited with:
```python
# ============================================================
```

### Language Policy
- **English:** Code, variable names, function names, imports, commit messages, comments
- **Italian:** VLM prompts (extraction context requires Italian), field keys (banking domain terms like `professione_principale`), Streamlit UI strings, CSV column headers
- Do not translate Italian field keys — they must match the banking domain schema

## Architectural Constraints

These patterns are load-bearing. Do not remove or restructure without understanding downstream effects:

1. **Multi-pass pipeline** — The anchor → main → retry pattern is critical for accuracy. Anchors gate main extraction; retries use field-specific crops.
2. **Cost tracking** — Every VLM call must populate `_meta` with `estimated_cost_usd`, `prompt_tokens`, `completion_tokens`, `latency_ms`. Aggregated in `_meta_agg`.
3. **Environment-based config** — All configuration via `os.getenv()` with sensible defaults. No config files.
4. **Thread safety** — Each worker thread creates its own `OpenAI()` client. Never share clients across threads.
5. **Structured output** — VLM calls use `json_schema` response format with `additionalProperties: False`. All fields explicitly defined.
6. **Field source tracking** — `_field_sources` dict records which pass (ANCHOR_HEADER, CONTENT_MAIN, RETRY_{field}) produced each field's final value.
7. **Dataset mismatch guard** — `dataset_mismatch_guard()` detects when extracted NDG/DENOMINAZIONE differs from ground truth, preventing false negatives in evaluation.

## Key Files

| File | Purpose |
|---|---|
| `main.py` | Core extraction engine (1071 lines): pipeline, VLM calls, evaluation, cost tracking |
| `app.py` | Streamlit web UI (233 lines): upload, process, display results |
| `mnt/data/dati.csv` | Ground truth dataset (5 screens, maps field names to expected values) |
| `mnt/data/screen *.png` | Test banking screenshots (5 images) |
| `mnt/data/poc_outputs_improved.json` | Previous extraction results |
| `mnt/data/poc_debug_improved.csv` | Per-field debug report |
| `prompts_immagini.txt` | Image generation prompts (reference only, not used in pipeline) |

## Dependencies

No `requirements.txt` exists. Inferred from imports:

```
openai          # GPT-4V API client
pillow          # Image processing (PIL)
pandas          # CSV/data handling
streamlit       # Web UI
```

## Missing Infrastructure

The following are not yet implemented:
- `requirements.txt` or `pyproject.toml` — dependencies are not pinned
- Tests — no test suite exists
- CI/CD — no pipeline configured
- Docker — no containerization
- `.env.example` — no template for required environment variables
- README — no project documentation

## Testing & Validation

There is no automated test suite. To verify changes manually:

1. **Run extraction:** `python main.py` — should complete without errors
2. **Check accuracy:** Output includes per-field accuracy breakdown (RAW + FILTERED metrics). Compare against baseline.
3. **Check costs:** `print_cost_summary()` outputs per-screen token counts and USD costs. Verify no regressions.
4. **Streamlit smoke test:** `streamlit run app.py` — upload a screenshot, verify results display correctly.
5. **Ground truth eval:** `eval_outputs()` classifies each field as OK / WRONG / MISSING / HALLUCINATED / OK_NULL.
