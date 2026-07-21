# CLAUDE.md -- poc-data-extraction

AI-powered extraction of structured fields from Italian BPER banking screenshots.
A multi-pass Vision-LLM pipeline reads each screenshot, evaluates the result against a
ground-truth CSV, and reports per-field accuracy plus token/cost breakdowns. The same
extraction engine is exposed through three front-ends: a CLI batch runner, a Tkinter
desktop GUI, and a PyQt6 edge-agent that captures the screen live.

- **Language/runtime:** Python 3.12/3.13 (practical target: `run_edge_agent.bat` probes
  `py -3.13` then `py -3.12` and errors otherwise; no packaging metadata pins a version)
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
   DENOMINAZIONE. A confidence gate (`>= 0.95`, `ANCHOR_CONF_MIN`) is *intended* to zero out
   low-confidence anchors, but is currently **ineffective**: the returned `ndg`/`den` dicts are
   copied via `safe_field()` *before* the gate runs (`pipeline.py:87-96`), and `safe_set_field()`
   cannot null an existing non-null value (`normalization.py:78-79`), so low-confidence anchors
   flow downstream unfiltered. With `STOP_ON_ANCHOR_UNCERTAIN=1` the pipeline exits early when
   both anchor *values* are null.
2. **Main pass** -- the full content crop is sent to the VLM together with anchor hints
   (`"NDG atteso: {value}"`). Extracts all scalar fields plus the soggetti / fidi / garanzie arrays
   in one call.
3. **Conditional retry** -- an area (HEADER / BODY / FOOTER) is retried when any of its fields is
   nullish or below confidence `0.60` (hardcoded). Each area gets a dedicated crop, a
   contrast/sharpness boost, and an area-specific Italian prompt. At most
   `max(0, MAX_CALLS_PER_SCREEN - 2)` areas are retried (anchor + main already count,
   `pipeline.py:262`). The per-field winner is chosen by `pick_best()`: non-null beats null; on
   equal nullness the current value wins unless the candidate has strictly higher confidence.
   **Retry coverage gap:** `creazione` and the 5 `tooltip_*` fields belong to *no* retry area
   (`AREA_TO_FIELDS`, `extraction/config.py:69-82`), so they can never be retried. A failed area
   retry is non-fatal (main-pass values are kept, warning printed).

Post-processing order is load-bearing (`pipeline.py:144-178`): anchors are merged back and `tipo`
normalized *before* retries; the coherence check (repairs `evidenze` / `tipo` from their tooltips)
runs *after* retries; then `soggetti[:4]` are flattened to `ndg_1..4` / `denominazione_1..4` /
`ruolo_1..4` for CSV-style evaluation. This flatten runs after the retry merge and
**unconditionally overwrites** those 12 fields from the soggetti rows (even with `None` values),
without updating `_field_sources` (`pipeline.py:161-166`).

Two entry methods exist by design:
- `extract_from_screen(path)` -- used by CLI and the Tkinter GUI; normalizes the image internally.
- `extract_from_image(img, screen_id)` -- used by `LocalExtractionClient`; the image is already
  preprocessed by the edge-agent, so `normalize_image()` is intentionally bypassed.

### Three run modes

- **CLI** (`python main.py`): batch-processes every `.png/.jpg/.jpeg` in `INPUT_DIR`, writes JSON
  results, prints accuracy metrics and a cost summary. Hard-requires `mnt/data/dati.csv`
  (`FileNotFoundError` at `extraction/cli.py:315-316`); the CSV is **not** in the repo -- see
  Data & Evaluation.
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
  ├── Dedup check via pHash (Hamming distance <= config dedup_threshold, default 3)
  ├── Detects page type via router (LLM or ML)
  ├── Stability check (STABILITY_SECONDS = 2.0 steady-state)
  └── _upload_page() → LocalExtractionClient.ingest_frame()
                           └── ExtractionPipeline.extract_from_image()
                                   ├── Anchor pass (header crop → NDG + DENOMINAZIONE)
                                   ├── Main pass (full content → all fields)
                                   └── Retry pass (low-confidence fields only)
                               → stores result → emits result_ready(job_id, result)
                                                     ├── ExtractionResultsTab (Risultati)
                                                     └── DataTableTab (Dati Estratti)
```

- **Detection hook:** `BPERCaptureWorker._upload_page()` detects `LocalExtractionClient` via
  `hasattr(api_client, "ingest_frame")` and calls it directly (synchronously, in the capture QThread).
- **Page routing modes** (set in `edge-agent/config.ini` `router=`; the code default is `ml`,
  `config.ini` currently ships `router=llm`):
  - `ml` -- `MLPageRouter` wraps `BPERPagePrototypeClassifier` (DINOv2 ViT-S/14, 384-dim, prototype
    matching via cosine similarity). Degrades gracefully to disabled if torch is unavailable.
  - `llm` -- `LLMPageRouter` uses OpenAI Vision (`gpt-4o-mini` per config.ini); reads page
    definitions from `assets/templates/bper/prompts.json`.
  - `hybrid` -- tries LLM first, falls back to ML.

## Running the Project

OpenAI (default):

```bash
export LLM_API_KEY="sk-..."
python main.py                        # CLI batch mode (requires mnt/data/dati.csv)
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

`LLM_API_KEY` must be set (or entered in the Tkinter GUI, which pre-fills from
`LLM_API_KEY`/`OPENAI_API_KEY`). Note: `gui_app.py` does **not** call `load_dotenv()` -- env vars
must already be exported when launching it directly (`main.py`, `edge_agent.py`, and
`local_extraction_client.py` do load `.env`). The edge-agent's capture/router settings come from
`edge-agent/config.ini`; its extraction engine still reads the env vars below.

## Configuration (Environment Variables)

All defaults verified against `extraction/config.py`.

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | Provider: `openai` or `gemini` |
| `LLM_API_KEY` | *(required)* | API credential (OpenAI or Gemini key) |
| `LLM_MODEL` | `gpt-4o` | Model for the main pass |
| `LLM_MODEL_ANCHOR` | same as `LLM_MODEL` | Model for the anchor pass |
| `INPUT_DIR` | `mnt/data` | Data directory (screenshots + ground truth) |
| `PARALLEL_WORKERS` | `4` | Thread pool size |
| `PARALLEL_ENABLED` | `1` | Enable parallel processing (`0` to disable) |
| `MAX_CALLS_PER_SCREEN` | `4` | Max VLM calls per screen (1 anchor + 1 main + retries) |
| `ANCHOR_CONF_MIN` | `0.95` | Anchor confidence gate (currently ineffective -- see pipeline notes) |
| `STOP_ON_ANCHOR_UNCERTAIN` | `0` | Early exit when both anchor values are null |
| `LLM_THINKING_LEVEL` | *(unset)* | Thinking budget `low`/`medium`/`high`; applied only to models whose name contains `thinking` |
| `DEBUG_MODE` | `0` | Verbose `[DEBUG]` logging in `extraction/cli.py` (`config.py:92`) |
| `DEBUG_SAVE_CROPS` | `0` | Save intermediate crop images to `INPUT_DIR/debug_crops` |

### Secrets policy

- **Never commit API keys.** An OpenAI key was once committed at `edge-agent/config.ini` `[llm]
  api_key`; on 2026-07-21 it was scrubbed from the entire git history (`git filter-repo`,
  force-pushed) and the line now holds the placeholder `REDACTED_OPENAI_API_KEY`.
- Router key precedence: `config.ini [llm] api_key` → `OPENAI_API_KEY` → `LLM_API_KEY`
  (`bper_capture_worker.py:122`). The env fallback only triggers when the INI value is blank --
  leave `api_key` empty in the INI to use env keys.
- `AgentConfig.save()` re-persists `llm_api_key` back into `config.ini`
  (`edge-agent/config.py:326-332`; currently uncalled). Do not wire it up with a real key loaded.
- Real keys belong in `.env` (gitignored; template in `.env.example`).

## Testing & Validation

There is no automated test suite. To verify changes manually:

1. **Run extraction:** `python main.py` -- should complete without errors (needs `LLM_API_KEY`
   and a local `mnt/data/dati.csv`).
2. **Check accuracy:** output includes a per-field accuracy breakdown (RAW + FILTERED). Compare
   against a baseline.
3. **Check costs:** `print_cost_summary()` reports per-screen token counts and USD costs. Watch for
   regressions.
4. **Tkinter GUI smoke test:** `python gui_app.py` -- upload a screenshot, verify results display.
5. **Ground-truth eval:** `eval_outputs()` classifies each field as OK / WRONG / MISSING /
   HALLUCINATED / OK_NULL.
6. **Edge-agent smoke test:** `python edge-agent/edge_agent.py` -- start capture in BPER mode, verify
   `ingest_frame()` is called and results appear in the Risultati and Dati Estratti tabs.

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

1. **Multi-pass pipeline** -- the anchor → main → retry pattern is critical for accuracy. Retries
   use area-specific crops and are capped at `MAX_CALLS_PER_SCREEN - 2`. Post-processing order is
   sequenced (merge → tipo-normalize → retry → coherence → flatten → canonical → status). See
   `extraction/pipeline.py`.
2. **Cost tracking** -- every VLM call must populate `_meta` with `estimated_cost_usd`,
   `prompt_tokens`, `completion_tokens`, `latency_ms`, aggregated in `_meta_agg`. Models absent
   from `PRICING_PER_1M` silently cost `$0.00` (`estimate_cost_usd()` returns 0.0), so cost
   reports can under-count. See `extraction/vlm_client.py`.
3. **Environment-based config** -- all configuration via `os.getenv()` with sensible defaults,
   read at *import time* in `extraction/config.py`. Env (or `.env`) must be populated before
   importing `extraction`.
4. **Thread safety** -- LangChain ChatModel instances are treated as thread-safe and shared across
   all workers. Created once in `BatchRunner.__init__()` before the thread pool. See
   `extraction/cli.py`.
5. **Structured output** -- VLM calls use LangChain's `.with_structured_output(PydanticModel)` for
   OpenAI and Gemini 1.5; newer Gemini models fall back to free-form JSON plus manual Pydantic
   validation (`extraction/vlm_client.py`). Pydantic models live in `extraction/schemas.py`.
   `call_vlm_with_retry()` retries only transient errors; `ValueError` (parse failures) is re-raised
   immediately.
6. **Field source tracking** -- the `_field_sources` dict records which pass (ANCHOR_HEADER,
   CONTENT_MAIN, RETRY_{area}) produced each field's final value. Caveat: the soggetti flatten does
   *not* update it for `ndg_1..ruolo_4`.
7. **Dataset mismatch guard** -- `dataset_mismatch_guard()` detects when extracted NDG/DENOMINAZIONE
   differs from ground truth, preventing false negatives in evaluation. See
   `extraction/normalization.py`.
8. **Shared batch runner** -- `run_extraction_batch()` in `extraction/cli.py` (a wrapper over
   `BatchRunner`) is used by both `main()` and the Tkinter GUI (`gui_app.py`). It accepts optional
   `model_main`/`model_anchor` overrides (the GUI provider/model dropdown). Callbacks
   (`on_complete`, `on_error`) run on the calling thread, not on worker threads. Do not
   re-implement batch/threading logic elsewhere. `_deduplicate_same_page_outputs()` exists but its
   call is commented out (`cli.py:268-273`, "TEMP TEST" pending page_key mapping validation).
9. **Screenshot discovery** -- the CLI scans `INPUT_DIR` directly for `.png/.jpg/.jpeg`
   (`cli.py:322-327`). `get_screenshot_paths()` in `extraction/config.py` currently has no caller.
   Do not reintroduce the old mutable global `SCREENSHOTS` list.
10. **No startup guards** -- contrary to what this file used to claim, there are **no** `if/raise`
    guards validating `FIELD_RETRY_MAP`/`AREA_TO_FIELDS` against `FIELD_KEYS` (and no
    `_FIELD_COMPARATORS` exists anywhere). Dict consistency is by convention only: a key missing
    from `AREA_TO_FIELDS` is silently never retried. When adding a field, update `FIELD_KEYS`,
    `AREA_TO_FIELDS`, `CSV_TO_SCHEMA`, `field_definitions.py`, and the prompts.
11. **Edge-agent is local-only** -- `LocalExtractionClient` is the only client the edge-agent uses;
    there is no remote API backend. Do not reintroduce remote upload logic into the BPER path.
12. **Edge-agent preprocessing** -- `BPERCaptureWorker` preprocesses via
    `image_ops.preprocess_for_ocr()` before calling `ingest_frame()`, so `LocalExtractionClient` calls
    `extract_from_image()` (not `extract_from_screen()`), bypassing `normalize_image()`.

## Code Conventions

- **Type annotations:** every function has full annotations on parameters and return type, e.g.
  `def normalize_image(img: Image.Image, long_side: int = 1800) -> Image.Image: ...`
- **Naming:** constants `UPPER_SNAKE_CASE` (`FIELD_KEYS`, `CONTENT_CROP`); private helpers
  `_leading_underscore` (`_find_column()`, `_aggregate_meta()`); Pydantic models `PascalCase`
  (`ExtractionResponse`, `AnchorResponse`) with legacy `UPPER_SNAKE_CASE` aliases
  (`RESPONSE_SCHEMA`, `ANCHOR_SCHEMA` in `schemas.py`) kept for backward compat.
- **Section markers:** code sections are delimited with `# ============================================================`.
- **Language policy:**
  - *English* for code, identifiers, imports, commit messages, comments.
  - *Italian* for VLM prompts (the extraction context requires it), field keys (banking domain terms
    like `professione_principale`), PyQt6/Tkinter UI strings, and CSV column headers.
  - Do not translate Italian field keys -- they must match the banking domain schema.

## BPER Domain

The extractor targets **9 BPER banking screens** (`mnt/data/screen 1.png` ... `screen 9.png`), each a
different page of the BPER credit-management application.

**Extracted fields** -- 45 entries in `FIELD_KEYS` (`extraction/fields.py`):

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
- Per-area retry crops in `RETRY_AREAS`; field-to-area mapping in `AREA_TO_FIELDS` (from which
  `FIELD_RETRY_MAP` is derived)

## Data & Evaluation

**Ground-truth CSV** (`mnt/data/dati.csv`) uses three columns: `Fotogramma` (screen ID),
`Denominazione da attribuire` (field name), `Valore rilevato` (expected value). `load_ground_truth()`
in `extraction/evaluation.py` auto-detects alternative column names (`Screenshot`/`Screen`,
`Campo`/`Field`, `Valore`/`Value`) via `_find_column()`.

**The CSV is NOT in the repo:** `/mnt` is gitignored (only the 9 PNGs are force-tracked), and no
copy exists in the working tree. `python main.py` raises `FileNotFoundError` without it
(`extraction/cli.py:315-316`) -- obtain it separately and place it at `mnt/data/dati.csv`. The
Tkinter GUI and the edge-agent work without it (evaluation is optional there).

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
| `gui_app.py` | Tkinter GUI: upload screenshots, pick provider/model, process, display, export CSV/JSON. Imports `run_extraction_batch` from `extraction`. Does not load `.env`. |
| `edge-agent/edge_agent.py` | PyQt6 entry point: loads `.env`, creates `AgentConfig`, launches `MainWindow`. `--debug` adds the Debug LLM tab. |
| `run_edge_agent.bat` | Windows launcher: bootstraps/self-heals `.venv` (Python 3.13, then 3.12), installs `requirements.txt`, starts the edge-agent. |

### `extraction/` package (core engine)

| Module | Purpose |
|---|---|
| `__init__.py` | Public API re-exports for backward compatibility |
| `config.py` | Env-var config, crop constants, pricing, `AREA_TO_FIELDS`/`FIELD_RETRY_MAP` |
| `fields.py` | `FIELD_KEYS` (45 fields), `CSV_TO_SCHEMA` mapping |
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
| `cli.py` | `BatchRunner`, `run_extraction_batch()` (shared by CLI and Tkinter GUI), `main()` CLI entry |

### `edge-agent/` package (live capture)

| Module | Purpose |
|---|---|
| `local_extraction_client.py` | `LocalExtractionClient(QObject)`: bridge to `ExtractionPipeline`; `start_job()`, `ingest_frame()`, `export_csv()`, `result_ready` signal |
| `config.py` | `AgentConfig`: loads `config.ini` (FPS, router mode, preprocessing params, monitor index) |
| `llm_router.py` | `LLMPageRouter` (OpenAI Vision), `MLPageRouter` (DINOv2 ViT-S/14), `PageRouter` base |
| `image_ops.py` | `preprocess_for_ocr()`, `to_png8()`, `to_webp_lossless()` -- capture preprocessing |
| `page_classifier.py` | `BPERPagePrototypeClassifier` -- DINOv2 ViT-S/14 (384-dim) prototype matching |
| `ui/main_window.py` | `MainWindow`: creates `LocalExtractionClient` and the Cattura / Risultati / Dati Estratti tabs (+ Debug LLM with `--debug`) |
| `ui/capture_tab.py` | `CaptureTab`: start/stop, FPS/filter, force-capture, log |
| `ui/extraction_results_tab.py` | `ExtractionResultsTab`: pages tree, fields table, raw JSON, CSV export |
| `ui/data_table_tab.py` | `DataTableTab`: spreadsheet view (rows = captured screens, cols = canonical fields), CSV/Excel export |
| `ui/debug_tab.py` | `DebugTab`: LLM router prompt/response viewer (tab shown with `--debug`; `show_llm_tab=true` in config.ini gates the `llm_debug` signal) |
| `ui/overlay.py` | `CaptureBorderOverlay`: red border on the captured monitor |
| `workers/capture/base_capture_worker.py` | `BaseCaptureWorker(QThread)`: FPS run loop, `tick`/`error`/`llm_debug` signals |
| `workers/capture/bper_capture_worker.py` | `BPERCaptureWorker`: pHash dedup, page routing, stability, calls `ingest_frame()` |
| `workers/capture/default_capture_worker.py` | `DefaultCaptureWorker`: generic mode, uploads raw frames to a remote API (no local extraction; no such backend exists in this repo) |

### Data files

| File | Purpose |
|---|---|
| `mnt/data/dati.csv` | Ground-truth dataset -- **expected here but absent from repo and git** (`/mnt` gitignored); required by the CLI |
| `mnt/data/screen *.png` | Test banking screenshots (9 BPER images, force-tracked in git) |
| `prompts_immagini.txt` | Image-generation prompts (reference only, not used by the pipeline) |

### Documentation

| Path | Purpose |
|---|---|
| `docs/` | Narrative codebase guide in Italian (start at `docs/INDEX.md`) |
| `.codebase-map/` | Generated technical map (start at `.codebase-map/INDEX.md`); `_internal/context-brief.md` and `_internal/interconnect.md` hold code-verified facts with file:line citations |

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
python-dotenv           # .env loading (main.py, edge_agent.py, local_extraction_client.py -- NOT gui_app.py)
openpyxl>=3.1.2         # Excel read (edge-agent/workers/capture/bper_capture_worker.py)
```

**Edge-agent (PyQt6 live capture):**
```
PyQt6>=6.4.0            # Desktop UI framework
qt-material>=2.14       # PyQt6 Material theme (edge-agent/edge_agent.py)
mss>=9.0.0             # Fast screenshot capture
pyscreenshot>=3.1      # Screenshot fallback (Linux-only env marker)
imagehash>=4.3.0       # pHash for frame dedup
torch, torchvision     # DINOv2 ViT-S/14 ML page classifier (edge-agent/page_classifier.py)
openai>=1.51.0         # LLM page router (gpt-4o-mini)
requests>=2.31.0       # Remote upload in DefaultCaptureWorker (generic mode only)
```

**Present in `requirements.txt` but unused / orphaned** (no importer in current code -- removal
candidate): `streamlit`.

## Missing Infrastructure

Not yet implemented:
- `pyproject.toml` -- dependencies are listed in `requirements.txt` but not version-pinned
- Tests -- no test suite exists
- CI/CD -- no pipeline configured
- Docker -- no containerization
