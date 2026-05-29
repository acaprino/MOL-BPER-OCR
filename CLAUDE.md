# CLAUDE.md -- poc-data-extraction

AI-powered extraction of structured fields from Italian BPER banking screenshots.
A multi-pass Vision-LLM pipeline reads each screenshot, evaluates the result against a
ground-truth CSV, and reports per-field accuracy plus token/cost breakdowns. The same
extraction engine is exposed through three front-ends: a CLI batch runner, a Tkinter
desktop GUI, and a PyQt6 edge-agent that captures the screen live.

- **Language/runtime:** Python 3.8+
- **LLM access:** LangChain. `create_chat_model()` in `extraction/llm_factory.py` is the single
  factory that selects the provider from the `LLM_PROVIDER` env var (OpenAI GPT-4o or Google Gemini).
- **Core libs:** LangChain (`langchain-openai` / `langchain-google-genai`), Pillow, Pandas
- **UI:** Tkinter (stdlib) for `gui_app.py`; PyQt6 + qt-material for the edge-agent
- **Entry points:** `main.py` (CLI batch; `--gui` launches the edge-agent), `gui_app.py`
  (Tkinter GUI), `edge-agent/edge_agent.py` (PyQt6 edge-agent)

## How It Works

### Multi-pass extraction pipeline

Each screenshot is processed in three stages by `ExtractionPipeline` in `extraction/pipeline.py`
(`extract_from_screen()` / `extract_from_image()`):

1. **Anchor pass** -- `extract_anchors()` crops the header region and extracts only NDG +
   DENOMINAZIONE. A confidence gate (`>= 0.95`, `ANCHOR_CONF_MIN`) zeroes out low-confidence
   anchors. With `STOP_ON_ANCHOR_UNCERTAIN=1` the pipeline exits early when both are null.
2. **Main pass** -- the full content crop is sent to the VLM together with anchor hints
   (`"NDG atteso: {value}"`). Extracts all scalar fields plus the soggetti / fidi / garanzie arrays
   in one call.
3. **Conditional retry** -- only fields that are nullish or below confidence `0.60` trigger a retry.
   Retries are grouped by area (HEADER / BODY / FOOTER), each with a dedicated crop and prompt, and
   are capped by `MAX_CALLS_PER_SCREEN`. The best value per field is chosen by `pick_best()`
   (non-null beats null; on a tie, higher confidence wins).

After merging, two post-processing steps run: anchors are merged back in, `tipo` is normalized, and
a coherence check repairs `evidenze` / `tipo` from their tooltips. Soggetti are flattened to
`ndg_1..4` / `denominazione_1..4` / `ruolo_1..4` for CSV-style evaluation.

Two entry methods exist by design:
- `extract_from_screen(path)` -- used by CLI and the Tkinter GUI; normalizes the image internally.
- `extract_from_image(img, screen_id)` -- used by `LocalExtractionClient`; the image is already
  preprocessed by the edge-agent, so `normalize_image()` is intentionally bypassed.

### Three run modes

- **CLI** (`python main.py`): batch-processes every screen in `INPUT_DIR`, writes JSON results,
  prints accuracy metrics and a cost summary.
- **Tkinter GUI** (`python gui_app.py`): desktop window for uploading screenshots, picking
  provider/model, viewing per-screen results, and exporting CSV/JSON. Imports
  `run_extraction_batch()` from the `extraction` package.
- **Edge-agent** (`python edge-agent/edge_agent.py`, or `python main.py --gui`): PyQt6 app that
  captures BPER screens in real time, detects the page type, and runs extraction locally via
  `LocalExtractionClient`.

CLI and the Tkinter GUI share `run_extraction_batch()` in `extraction/cli.py` -- do not duplicate the
`ThreadPoolExecutor` logic.

### Edge-agent capture flow

The edge-agent captures live screenshots and extracts locally, with no remote backend.

```
BPERCaptureWorker (QThread)
  ├── Captures screenshot via mss
  ├── Preprocesses (scale, unsharp, autocontrast) via image_ops.preprocess_for_ocr()
  ├── Dedup check via pHash (Hamming distance <= DEDUP_HASH_THRESHOLD)
  ├── Detects page type via router (LLM or ML)
  ├── Stability check (2 seconds steady-state)
  └── _upload_page() → LocalExtractionClient.ingest_frame()
                           └── ExtractionPipeline.extract_from_image()
                                   ├── Anchor pass (header crop → NDG + DENOMINAZIONE)
                                   ├── Main pass (full content → all fields)
                                   └── Retry pass (low-confidence fields only)
                               → stores result → emits result_ready(job_id, result)
                                                     └── ExtractionResultsTab updates UI
```

- **Detection hook:** `BPERCaptureWorker._upload_page()` detects `LocalExtractionClient` via
  `hasattr(api_client, "ingest_frame")` and calls it directly (synchronously, in the capture QThread).
- **Page routing modes** (set in `edge-agent/config.ini` `router=`):
  - `ml` -- `MLPageRouter` wraps `BPERPagePrototypeClassifier` (DINOv2 ViT-S/14, 384-dim, prototype
    matching via cosine similarity). Degrades gracefully to disabled if torch is unavailable.
  - `llm` -- `LLMPageRouter` uses OpenAI Vision; reads page definitions from
    `assets/templates/bper/prompts.json`.
  - `hybrid` -- tries LLM first, falls back to ML.

## Running the Project

OpenAI (default):

```bash
export LLM_API_KEY="sk-..."
python main.py                        # CLI batch mode
python gui_app.py                     # Tkinter desktop GUI
python edge-agent/edge_agent.py       # Edge-agent UI (or: python main.py --gui)
```

Google Gemini:

```bash
export LLM_PROVIDER=gemini
export LLM_API_KEY="AI..."
export LLM_MODEL=gemini-1.5-flash
python main.py
```

`LLM_API_KEY` must be set (or entered in the Tkinter GUI, which falls back to `OPENAI_API_KEY`).
The edge-agent is configured via `edge-agent/config.ini`, not env vars.

## Configuration (Environment Variables)

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | Provider: `openai` or `gemini` |
| `LLM_API_KEY` | *(required)* | API credential (OpenAI or Gemini key) |
| `LLM_MODEL` | `gpt-4o` | Model for the main pass |
| `LLM_MODEL_ANCHOR` | same as `LLM_MODEL` | Model for the anchor pass |
| `INPUT_DIR` | `mnt/data` | Data directory (screenshots + ground truth) |
| `SCREENSHOT_DIR` | *(unused)* | Declared historically but not read anywhere in code (inert) |
| `PARALLEL_WORKERS` | `4` | Thread pool size |
| `PARALLEL_ENABLED` | `1` | Enable parallel processing (`0` to disable) |
| `MAX_CALLS_PER_SCREEN` | `4` | Max VLM calls per screen |
| `ANCHOR_CONF_MIN` | `0.95` | Minimum confidence for anchor acceptance |
| `STOP_ON_ANCHOR_UNCERTAIN` | `0` | Stop processing if anchor confidence is low |
| `LLM_THINKING_LEVEL` | *(unset)* | Thinking budget `low`/`medium`/`high`; applied only to models whose name contains `thinking` |
| `DEBUG_SAVE_CROPS` | `0` | Save intermediate crop images to disk |

## Testing & Validation

There is no automated test suite. To verify changes manually:

1. **Run extraction:** `python main.py` -- should complete without errors.
2. **Check accuracy:** output includes a per-field accuracy breakdown (RAW + FILTERED). Compare
   against a baseline.
3. **Check costs:** `print_cost_summary()` reports per-screen token counts and USD costs. Watch for
   regressions.
4. **Tkinter GUI smoke test:** `python gui_app.py` -- upload a screenshot, verify results display.
5. **Ground-truth eval:** `eval_outputs()` classifies each field as OK / WRONG / MISSING /
   HALLUCINATED / OK_NULL.
6. **Edge-agent smoke test:** `python edge-agent/edge_agent.py` -- start capture in BPER mode, verify
   `ingest_frame()` is called and results appear in the Risultati tab.

## Working Principles

### 1. Think Before Coding
State assumptions explicitly. Ask when uncertain.
Present tradeoffs; don't pick silently.
- Read related code before editing; understand the call sites
- Isolate the root cause; don't patch symptoms
- Surface unknowns instead of guessing

### 2. Simplicity First
Minimum code that solves the problem.
No speculative features or abstractions.
- One responsibility per function or module
- Delete code when it stops paying rent
- Prefer composition over premature inheritance

### 3. Surgical Changes
Touch only what the task requires.
Match existing style. Clean up only your own orphans.
- No drive-by refactors outside the task scope
- Preserve public APIs unless the task requires a change
- Keep diffs small and reviewable

### 4. Goal-Driven Execution
Define success criteria, then loop until verified.
Transform "do X" into "X passes test Y".
- Write tests against behavior, not internals (evergreen tests)
- Verify with real evidence: run the code, read the output
- Stop when the criteria are met; don't gold-plate

### 5. Centralize Shared Logic
Route external calls (HTTP clients, broker APIs, LLM/embedding providers, payment gateways, DB access) and cross-cutting concerns (config, auth, logging) through a single utility, client, or facade module. Apply DRY and Single Source of Truth: one change, one place. Before adding a new call site, check whether an existing client/wrapper already exists and extend it instead of duplicating.

## Architectural Constraints

These patterns are load-bearing. Do not remove or restructure them without understanding the
downstream effects.

1. **Multi-pass pipeline** -- the anchor → main → retry pattern is critical for accuracy. Anchors gate
   the main pass (optional early exit via `STOP_ON_ANCHOR_UNCERTAIN`); retries use field-specific
   crops and are capped by `MAX_CALLS_PER_SCREEN`. See `extraction/pipeline.py`.
2. **Cost tracking** -- every VLM call must populate `_meta` with `estimated_cost_usd`,
   `prompt_tokens`, `completion_tokens`, `latency_ms`, aggregated in `_meta_agg`. See
   `extraction/vlm_client.py`.
3. **Environment-based config** -- all configuration via `os.getenv()` with sensible defaults. See
   `extraction/config.py`.
4. **Thread safety** -- LangChain ChatModel instances are thread-safe and shared across all workers.
   Created once in `run_extraction_batch()` before the thread pool. See `extraction/cli.py`.
5. **Structured output** -- VLM calls use LangChain's `.with_structured_output(PydanticModel)`, which
   handles per-provider schema translation. Pydantic models live in `extraction/schemas.py`.
   `call_vlm_with_retry()` retries only transient errors; `ValueError` (parse failures) is re-raised
   immediately.
6. **Field source tracking** -- the `_field_sources` dict records which pass (ANCHOR_HEADER,
   CONTENT_MAIN, RETRY_{area}) produced each field's final value.
7. **Dataset mismatch guard** -- `dataset_mismatch_guard()` detects when extracted NDG/DENOMINAZIONE
   differs from ground truth, preventing false negatives in evaluation. See
   `extraction/normalization.py`.
8. **Shared batch runner** -- `run_extraction_batch()` in `extraction/cli.py` is used by both `main()`
   and the Tkinter GUI (`gui_app.py`). It accepts optional `model_main`/`model_anchor` overrides
   (the GUI provider/model dropdown). Callbacks (`on_complete`, `on_error`) run on the calling thread,
   not on worker threads. Do not re-implement batch/threading logic elsewhere.
9. **Screenshot path resolution** -- use `get_screenshot_paths()` in `extraction/config.py`; do not
   reintroduce the old mutable global `SCREENSHOTS` list.
10. **Startup assertions** -- `if/raise` guards at module load catch naming drift between dicts.
    `FIELD_RETRY_MAP` keys are validated against `FIELD_KEYS` in `extraction/pipeline.py`;
    `_FIELD_COMPARATORS` keys against `FIELD_KEYS` in `extraction/normalization.py`. These run under
    `python -O` (unlike `assert`).
11. **Edge-agent is local-only** -- `LocalExtractionClient` is the only client the edge-agent uses;
    there is no remote API backend. Do not reintroduce remote upload logic into the BPER path.
12. **Edge-agent preprocessing** -- `BPERCaptureWorker` preprocesses via
    `image_ops.preprocess_for_ocr()` before calling `ingest_frame()`, so `LocalExtractionClient` calls
    `extract_from_image()` (not `extract_from_screen()`), bypassing `normalize_image()`.

## Code Conventions

- **Type annotations:** every function has full annotations on parameters and return type, e.g.
  `def normalize_image(img: Image.Image, long_side: int = 1800) -> Image.Image: ...`
- **Naming:** constants `UPPER_SNAKE_CASE` (`FIELD_KEYS`, `CONTENT_CROP`); private helpers
  `_leading_underscore` (`_extract_date_ddmmyyyy()`); Pydantic/schema names `UPPER_SNAKE_CASE`
  (`RESPONSE_SCHEMA`, `ANCHOR_SCHEMA`).
- **Section markers:** code sections are delimited with `# ============================================================`.
- **Language policy:**
  - *English* for code, identifiers, imports, commit messages, comments.
  - *Italian* for VLM prompts (the extraction context requires it), field keys (banking domain terms
    like `professione_principale`), PyQt6/Tkinter UI strings, and CSV column headers.
  - Do not translate Italian field keys -- they must match the banking domain schema.

## BPER Domain

The extractor targets **9 BPER banking screens** (`mnt/data/screen 1.png` ... `screen 9.png`), each a
different page of the BPER credit-management application.

**Extracted fields** (`extraction/fields.py → FIELD_KEYS`):

| Group | Fields |
|---|---|
| Header identifiers | `ndg`, `denominazione` |
| Practice metadata | `tipo`, `stato`, `fase`, `creazione`, `evidenze` |
| Credit data | `filiale_relazione`, `n_fido`, `rapporto`, `descrizione`, `scadenza`, `importo_euro`, `tipo_op` |
| Notes & tooltips | `note_della_richiesta`, `tooltip_descrizione_bmb`, `tooltip_evidenze_b`, `tooltip_descrizione_m_consap`, `tooltip_descrizione_consap_dr_bis`, `tooltip_descrizione_ipoteca` |
| Soggetti (screens 2-3) | `ndg_1/2/3/4`, `denominazione_1/2/3/4`, `ruolo_1/2/3/4` |
| Privati scheda (screens 4-5) | `dal`, `datore_di_lavoro_anagrafica`, `di_cui_percepiscono_reddito`, `importo_totale_annuo_nucleo`, `note_scheda_privati`, `nr_altri_componenti_nucleo`, `numero_mensilita`, `professione_principale`, `rating_ufficiale`, `retribuzione_annua_netta`, `score_cgs`, `tipo_contratto`, `ultima_validazione_scheda` |

**Crop regions** (relative coords, `extraction/config.py`):
- `CONTENT_CROP = (0.18, 0.12, 0.98, 0.98)` -- full content area (main pass)
- `HEADER_IN_CONTENT = (0.00, 0.00, 1.00, 0.22)` -- header strip (anchor pass)
- Per-area retry crops in `RETRY_AREAS`; field-to-area mapping in `AREA_TO_FIELDS` / `FIELD_RETRY_MAP`

## Data & Evaluation

**Ground-truth CSV** (`mnt/data/dati.csv`) uses three columns: `Fotogramma` (screen ID),
`Denominazione da attribuire` (field name), `Valore rilevato` (expected value). `load_ground_truth()`
in `extraction/evaluation.py` auto-detects alternative column names (`Screenshot`/`Screen`,
`Campo`/`Field`, `Valore`/`Value`) via `_find_column()`.

**Field classification** -- `classify_field()` labels each extracted field as one of:
- **OK** -- matches ground truth
- **WRONG** -- does not match
- **MISSING** -- ground truth has a value, extraction returned null
- **HALLUCINATED** -- ground truth is null, extraction produced a value
- **OK_NULL** -- both null (correct)

Metrics are reported in two variants: **RAW** (all screens) and **FILTERED** (excludes screens where
`dataset_mismatch_guard()` detected an NDG/DENOMINAZIONE mismatch).

## Project Structure

### Entry points

| File | Purpose |
|---|---|
| `main.py` | Shim: loads `.env` via `python-dotenv`, then `from extraction import *`. `python main.py` runs the CLI; `python main.py --gui` launches the edge-agent. |
| `gui_app.py` | Tkinter GUI: upload screenshots, pick provider/model, process, display, export CSV/JSON. Imports `run_extraction_batch` from `extraction`. |
| `edge-agent/edge_agent.py` | PyQt6 entry point: loads `.env`, creates `AgentConfig`, launches `MainWindow`. |

### `extraction/` package (core engine)

| Module | Purpose |
|---|---|
| `__init__.py` | Public API re-exports for backward compatibility |
| `config.py` | Env-var config, crop constants, pricing, `get_screenshot_paths()` |
| `fields.py` | `FIELD_KEYS` (all fields), `CSV_TO_SCHEMA` mapping |
| `field_definitions.py` | Canonical field → display-name / page-key resolution |
| `page_definitions.py` | Canonical page names and label resolution |
| `canonical_mapping.py` | `build_canonical_field_entries()` for client-facing output |
| `schemas.py` | Pydantic models: `ExtractionResponse`, `AnchorResponse`, `FieldResult`, `Soggetto` |
| `prompts.py` | `PROMPT`, `ANCHOR_PROMPT`, area retry prompts (Italian) |
| `normalization.py` | Text normalization, `classify_field()`, `pick_best()`, `dataset_mismatch_guard()` |
| `imaging.py` | `normalize_image()`, `crop_relative()`, `img_to_png_bytes()`, `save_debug_crop()` |
| `vlm_client.py` | `call_vlm()`, `call_vlm_with_retry()`, `estimate_cost_usd()` -- LangChain structured output |
| `llm_factory.py` | `create_chat_model()` -- LangChain ChatModel factory |
| `pipeline.py` | `ExtractionPipeline`: `extract_from_image()`, `extract_from_screen()` |
| `evaluation.py` | `eval_outputs()`, `build_debug_report()`, `print_cost_summary()`, `load_ground_truth()` |
| `cli.py` | `main()` CLI entry, `run_extraction_batch()` shared by CLI and the Tkinter GUI |

### `edge-agent/` package (live capture)

| Module | Purpose |
|---|---|
| `local_extraction_client.py` | `LocalExtractionClient(QObject)`: bridge to `ExtractionPipeline`; `start_job()`, `ingest_frame()`, `export_csv()`, `result_ready` signal |
| `config.py` | `AgentConfig`: loads `config.ini` (FPS, router mode, preprocessing params, monitor index) |
| `llm_router.py` | `LLMPageRouter` (OpenAI Vision), `MLPageRouter` (DINOv2 ViT-S/14), `PageRouter` base |
| `image_ops.py` | `preprocess_for_ocr()`, `to_png8()`, `to_webp_lossless()` -- capture preprocessing |
| `page_classifier.py` | `BPERPagePrototypeClassifier` -- DINOv2 ViT-S/14 (384-dim) prototype matching |
| `ui/main_window.py` | `MainWindow`: creates `LocalExtractionClient`, `CaptureTab`, `ExtractionResultsTab` |
| `ui/capture_tab.py` | `CaptureTab`: start/stop, FPS/filter, force-capture, log |
| `ui/extraction_results_tab.py` | `ExtractionResultsTab`: pages tree, fields table, raw JSON, CSV export |
| `ui/debug_tab.py` | `DebugTab`: LLM router prompt/response (enable via `show_llm_tab=true`) |
| `ui/overlay.py` | `CaptureBorderOverlay`: red border on the captured monitor |
| `workers/capture/base_capture_worker.py` | `BaseCaptureWorker(QThread)`: FPS run loop, `tick`/`error`/`llm_debug` signals |
| `workers/capture/bper_capture_worker.py` | `BPERCaptureWorker`: pHash dedup, page routing, stability, calls `ingest_frame()` |
| `workers/capture/default_capture_worker.py` | `DefaultCaptureWorker`: generic mode, uploads raw frames to a remote API (no local extraction) |

### Data files

| File | Purpose |
|---|---|
| `mnt/data/dati.csv` | Ground-truth dataset (9 screens; field name → expected value) |
| `mnt/data/screen *.png` | Test banking screenshots (9 BPER images) |
| `prompts_immagini.txt` | Image-generation prompts (reference only, not used by the pipeline) |

### Documentation

| Path | Purpose |
|---|---|
| `docs-alfio/` | Narrative codebase guide in Italian (start at `docs-alfio/INDEX.md`); doc 12 explains the internals in plain language |
| `.codebase-map/` | Auto-generated codebase map |

## Dependencies

All dependencies live in a single root `requirements.txt`; there is **no** `edge-agent/requirements.txt`.
Versions are loosely bounded, not strictly pinned.

**Extraction pipeline:**
```
langchain-core          # LangChain core abstractions (BaseChatModel, messages)
langchain-openai        # LangChain OpenAI ChatModel
langchain-google-genai  # LangChain Gemini ChatModel (required if LLM_PROVIDER=gemini)
Pillow>=10.0.0          # Image processing (PIL)
pandas                  # CSV/data handling
python-dotenv           # Auto-loads .env at startup (main.py, gui_app.py, edge_agent.py)
openpyxl>=3.1.2         # Excel read (edge-agent/workers/capture/bper_capture_worker.py)
```

**Edge-agent (PyQt6 live capture):**
```
PyQt6>=6.4.0            # Desktop UI framework
qt-material>=2.14       # PyQt6 Material theme (edge-agent/edge_agent.py)
mss>=9.0.0             # Fast screenshot capture
pyscreenshot>=3.1      # Screenshot fallback (Linux only)
imagehash>=4.3.0       # pHash for frame dedup
torch, torchvision     # DINOv2 ViT-S/14 ML page classifier (edge-agent/page_classifier.py)
openai>=1.51.0         # LLM page router (gpt-4o-mini)
requests>=2.31.0       # Remote upload in DefaultCaptureWorker (generic mode only)
```

**Present in `requirements.txt` but unused / orphaned** (no importer in current code -- removal
candidates): `streamlit`.

## Missing Infrastructure

Not yet implemented:
- `pyproject.toml` -- dependencies are listed in `requirements.txt` but not version-pinned
- Tests -- no test suite exists
- CI/CD -- no pipeline configured
- Docker -- no containerization
