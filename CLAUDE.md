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

Read `docs/how-it-works.md` for the multi-pass extraction pipeline (anchor -> main -> conditional
retry), the three run modes, and the edge-agent capture flow.

The rules that follow from that machinery, the ones you must not break, stay inline below under
*Architectural Constraints*. Read them even when you skip the mechanics.

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
| `MAX_CALLS_PER_SCREEN` | `2 + len(AREA_TO_FIELDS)` (= `5`) | Max VLM calls per screen (1 anchor + 1 main + 1 retry per retry area). Lowering it starves the trailing areas of `AREA_TO_FIELDS` |
| `ANCHOR_CONF_MIN` | `0.95` | Anchor confidence gate; below it the anchor value is nulled and never reaches the merge or the main-pass hint |
| `STOP_ON_ANCHOR_UNCERTAIN` | `0` | Early exit when both anchor values are null |
| `LLM_THINKING_LEVEL` | *(unset)* | Thinking budget `low`/`medium`/`high`; applied only to models whose name contains `thinking` |
| `DEBUG_MODE` | `0` | Verbose `[DEBUG]` logging in `extraction/cli.py` (`config.py:108`) |
| `DEBUG_SAVE_CROPS` | `0` | Save intermediate crop images to `INPUT_DIR/debug_crops` |
| `PROMPTS_DIR` | *(unset)* | Override the prompt catalog directory (read in `prompt_store.py`, not `config.py`); default is `prompts/` at the repo root, or next to the exe when frozen. An explicit override fails closed: no fallback to the bundled copy |

### Secrets policy

- **Never commit API keys.** An OpenAI key was once committed at `edge-agent/config.ini` `[llm]
  api_key`; on 2026-07-21 it was scrubbed from the entire git history (`git filter-repo`,
  force-pushed). The line now ships blank; `AgentConfig` also treats any `REDACTED*` value as
  empty (a leftover placeholder once shadowed the env keys and silently broke the LLM router).
- Router key precedence (`AgentConfig.resolve_llm_settings()` in `edge-agent/config.py`,
  provider-aware): `config.ini [llm] api_key` first if non-blank; else for `gemini`
  `GEMINI_API_KEY` → `GOOGLE_API_KEY` → `LLM_API_KEY`, for `openai` `OPENAI_API_KEY` →
  `LLM_API_KEY`. Leave `api_key` empty in the INI to use env keys -- `build_exe.bat` refuses
  to package a config.ini with a non-blank `api_key`.
- `AgentConfig.save()` re-persists `llm_api_key` back into `config.ini`
  (`edge-agent/config.py:326-332`; currently uncalled). Do not wire it up with a real key loaded.
- Real keys belong in `.env` (gitignored; template in `.env.example`).

## Testing & Validation

A pytest suite lives in `tests/` (`python -m pytest tests`, 116 tests) covering the page registry,
the capture stability tracker, the daemon thread pool, the async local-extraction client, the prompt
catalog, frame normalization (`test_frame_normalize.py`), the worker's capture framing
(`test_bper_capture_framing.py`), page recognition from live-shaped frames
(`test_page_classifier.py`) and retry-area selection (`test_pipeline_retry.py`). The rest of the
extraction pipeline is still untested.

`test_page_classifier.py` needs torch and runs DINOv2 on CPU (~20s, and it rebuilds the prototype
cache the first time after any geometry change); it skips via
`pytest.importorskip` where torch is absent. It rebuilds the app-window-inside-a-monitor framing from
the reference templates rather than feeding the classifier its own prototypes back, so it fails if
the ROI, the resize or the scoring rule regress. Do not "simplify" it into classifying the templates
directly: that variant passes even with the geometry that recognized 1 page out of 9 in the field.

Dev dependencies for the suite install via `pip install -r requirements-dev.txt`. To
verify changes manually:

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
   `ingest_frame()` is called and that one screen's worth of capture yields **one** row in Dati
   Estratti, not one per frame; export the workbook and check the two-level header.

## Test-Suite Rules

1. **A test exists to fail.** Write the test before the fix, watch it fail for the expected reason,
   then make it pass. A test written after the code passes on the first run and proves nothing.
2. **Test behavior, not internals.** Assert on what the code produces, never on how it got there.
   A test that breaks on a rename, but not on a wrong answer, is a liability.
3. **Never weaken a test to make it pass.** If a test fails, the code is wrong until proven
   otherwise. Loosening an assertion, widening a tolerance, or deleting a case to get green is
   forbidden without an explicit decision recorded in the commit message.
4. **No mocks where the real thing fits.** Mock only genuine boundaries: network calls, the clock,
   the filesystem when it is the subject. Mocking the code under test is testing the mock.
5. **One behavior per test, named for that behavior.** If the name needs an "and", split it.
6. **A failing test is never left failing.** Fix it, or quarantine it with an explicit skip and a
   reason. Never commit a red suite silently.
7. **Run the suite before claiming done.** `python -m pytest tests`. Report the actual output,
   including failures. Never assert success from expectation.

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
   importing `extraction`. In the edge-agent this is why `edge_agent.main()` imports
   `ui.main_window` (which transitively imports `extraction`) only *after*
   `bootstrap.run_preflight()` has created/loaded the local `.env` -- do not hoist that import
   to module scope.
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
   call is commented out (`cli.py:271-276`, "TEMP TEST" pending page_key mapping validation).
9. **Screenshot discovery** -- the CLI scans `INPUT_DIR` directly for `.png/.jpg/.jpeg`
   (`cli.py:326-330`). `get_screenshot_paths()` in `extraction/config.py` currently has no caller.
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
    `extract_from_image()` (not `extract_from_screen()`), bypassing `normalize_image()`. Capture and
    extraction are decoupled: `ingest_frame()` queues and returns, extraction runs on
    `PARALLEL_WORKERS` daemon threads sharing one pipeline (same pattern as `BatchRunner`).
13. **Every relative crop assumes window framing** -- the classifier ROI, the pipeline's
    `CONTENT_CROP`/`HEADER_IN_CONTENT` and the `RETRY_AREAS` are all fractions calibrated on the
    848x679 window screenshots in `mnt/data`. `_grab_raw()` captures the whole monitor, so
    `frame_normalize.normalize_frame()` must run there, before dedup, routing and extraction: with a
    full-monitor frame the same fractions point at different content and page recognition drops to
    1 page out of 9. Do not move the normalization into a single consumer, and do not add a consumer
    that re-derives crops from a raw monitor grab.
    See `docs/adr/0001-normalizzazione-inquadratura-frame.md`.
14. **Prompts are data** -- every LLM prompt lives in `prompts/*.json` (one file per prompt) and is
    read once at import by the root-level `prompt_store.py`, then served from memory. Do not re-add
    prompt literals to Python: `extraction/prompts.py`, `vlm_client.py`, `pipeline.py` and the
    edge-agent `llm_router.py` all resolve theirs through the store. The store is stdlib-only and
    lives outside `extraction/` on purpose, so the edge-agent router can read a prompt without
    importing LangChain. Notes:
    - `CATALOG` declares, per prompt id, the `parts` the code looks up and the `{placeholder}`
      fields it formats. Both are validated at load, so a stray brace fails at startup instead of
      raising `KeyError` mid-capture; write `{{` for a literal brace. Adding a prompt or a
      placeholder means updating `CATALOG` and the JSON file together.
    - **Fail-fast is deliberate, and asymmetric with the page catalog.** A corrupt prompt is worse
      than a missing file: the pipeline would keep running and emit wrong fields that look right.
      `edge-agent/assets/templates/bper/prompts.json` does the opposite and degrades to an empty
      spec, because a missed page detection is visible to the operator. Keep that asymmetry.
    - Candidate directories are tried in order and the first that *loads* wins, so a damaged
      editable copy next to the exe falls back to the bundled one. `bootstrap._ensure_files()`
      re-seeds `prompts/` from the bundle only when it is missing or empty, never overwriting
      hand-edited files. `catalog_source()` reports which copy is live; it is logged by
      `LocalExtractionClient.__init__()` and by the CLI.
    - There is deliberately no reload: consumers bind their prompts to module constants at import,
      so a partial reload would update some and not others.
    - `llm_router.py` imports the store *lazily* (inside `_load_prompt_templates()`) so an unreadable
      catalog raises inside `_init_router()`'s handler, disabling only the router, instead of
      failing the `ui.main_window` import chain and taking the app down. This is **not** about the
      bootstrap order of constraint 3: `llm_router` is only reachable via `ui.main_window`, which is
      already imported after `run_preflight()`.
14. **Edge-agent shows business data only** -- the UI presents the 45 canonical fields, one row per
    consolidated practice. Confidence, status, cost, tokens, latency and field provenance go to
    `edge-agent.log` via `_log_extraction()`, never back into a tab. Notes:
    - **One row = one practice.** The router recognises 9 screens but they are variants of the 4
      canonical pages (`PAGE_SHEET_ORDER`) of a single practice: a scrolled table or an open tooltip
      carries 1-6 useful fields. `consolidate()` groups frames by normalized NDG (a frame whose NDG
      was not read attaches to the most recent practice; frames before the first readable NDG wait
      in a buffer) and merges fields with `pick_best()` -- do not write a second merge semantics.
    - **`normalize_ndg()` is not `norm_number_str()`.** The latter is a *quantity* normalizer: it
      turns `12.345` into `12.35` (splitting one practice across two rows) and `12345/A` into
      `12345.00` (merging two distinct practices). An NDG is an identifier.
      `dataset_mismatch_guard()` still uses `norm_number_str()` on NDGs and has the same flaw; it is
      ground-truth evaluation code and was left alone.
    - **In xlsx, neutralize formulas with `cell.data_type = "s"`, never `escape_csv_formula()`.**
      The apostrophe is the CSV convention and stays visible in a spreadsheet cell, and the function
      also prefixes `-` and `+`, which would corrupt every negative amount.
    - Column order pins `ndg` and `denominazione` first: the canonical sort orders display names by
      codepoint, which would put `Creazione` first and NDG sixth, so the frozen panes would anchor
      two arbitrary columns.

## Code Conventions

- **Commit authorship (hard rule):** commits are authored by the human developer only. NEVER
  credit Claude or any AI assistant in a commit -- no `Co-Authored-By:` trailer, no
  "Generated with" line, no AI mention anywhere in subject, body, or footer. This overrides
  any default tooling behavior that appends such trailers.
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
- `CONTENT_CROP = (0.18, 0.12, 0.98, 0.98)` -- full content area (main pass); applied only on the file path (`extract_from_screen()`) and only when the image aspect matches the 848x679 calibration within 5% (`select_content_crop()`, ADR 0009); the live path (`extract_from_image()`) never crops -- every operator window has a different resolution, so a matching aspect there is always a false positive
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
(`extraction/cli.py:320`) -- obtain it separately and place it at `mnt/data/dati.csv`. The
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
| `edge-agent/edge_agent.py` | PyQt6 entry point: loads `.env`, creates `AgentConfig`, launches `MainWindow`. `--debug` adds the Debug LLM tab (`ui/debug_tab.py`), but the router traffic only reaches it when `config.ini` also has `[debug] show_llm_tab = true`, which gates the `llm_debug` signal. Both are required. |
| `run_edge_agent.bat` | Windows launcher: bootstraps/self-heals `.venv` (Python 3.13, then 3.12), installs `requirements.txt`, starts the edge-agent. |
| `prompt_store.py` | Prompt catalog loader shared by `extraction/` and the edge-agent router. Stdlib-only and deliberately outside `extraction/`, so reading a prompt does not import LangChain. `CATALOG`, `get_text()`, `get_part()`, `catalog_source()`. |

### `extraction/` package (core engine)

Flat package, no sub-packages, one module per concern. Grouped by role:

- **Domain vocabulary** -- `fields.py` (`FIELD_KEYS`, 45 fields; `CSV_TO_SCHEMA`),
  `field_definitions.py` (field → display-name / page-key), `page_definitions.py` (canonical page
  names), `canonical_mapping.py` (`build_canonical_field_entries()` for client-facing output).
- **Configuration** -- `config.py`: env-var snapshot, crop constants, pricing,
  `AREA_TO_FIELDS`/`FIELD_RETRY_MAP`.
- **Pipeline** -- `pipeline.py` (`ExtractionPipeline`), `vlm_client.py` (the single VLM call path,
  `call_vlm_with_retry()`, `estimate_cost_usd()`), `llm_factory.py` (`create_chat_model()`),
  `schemas.py` (Pydantic models), `prompts.py` (constants resolved from `prompt_store`).
- **Support** -- `normalization.py` (`classify_field()`, `pick_best()`,
  `dataset_mismatch_guard()`), `imaging.py` (`normalize_image()`, `crop_relative()`,
  `save_debug_crop()`).
- **Batch & reporting** -- `cli.py` (`BatchRunner`, `run_extraction_batch()`, `main()`),
  `evaluation.py` (`eval_outputs()`, `print_cost_summary()`, `load_ground_truth()`).
- `__init__.py` re-exports the public API for backward compatibility.

### `edge-agent/` package (live capture)

Flat modules plus two sub-packages: `ui/` (one module per PyQt6 tab, plus `main_window.py` and the
`overlay.py` capture border) and `workers/capture/` (`BaseCaptureWorker` with one subclass per
capture mode). `assets/templates/bper/` holds the page catalog and the DINOv2 prototype cache.

The capture chain, in order: `bper_capture_worker.py` grabs → `frame_normalize.py` reframes →
`image_ops.py` preprocesses → `llm_router.py` / `page_classifier.py` identify the page →
`stability.py` gates it → `page_registry.py` names it → `local_extraction_client.py` queues it onto
`extraction_pool.py`. Results reach `ui/data_table_tab.py`, where `practice_consolidation.py` groups
frames by normalized NDG (merging with `pick_best()`) and `excel_export.py` writes the workbook
(two-level header, one row per practice).

Called out individually, because the filename alone does not tell you:

- `app_paths.py` -- every path in the app resolves through here, and it answers differently from
  source and from a PyInstaller bundle (`env_file()`, `templates_dir()`, `prompts_dir()`).
- `bootstrap.py` -- `run_preflight()` creates/loads the local `.env`; `_ensure_files()` re-seeds
  `prompts/` from the bundle only when missing or empty. Must run *before* `ui.main_window` is
  imported (Constraint 3).
- `frame_normalize.py` -- reframes a full-monitor grab onto the app window (Constraint 13).
- `page_classifier.py` -- `embedding_geometry()` is part of the prototype cache key, so changing
  ROI, resize, model or scoring rule rebuilds the prototypes instead of silently mismatching them.
- `config.py` -- `AgentConfig` reads `config.ini`, **not** env vars; `resolve_llm_settings()` is the
  provider-aware key/endpoint/model resolver.
- `local_extraction_client.py` -- `ingest_frame()` enqueues and returns immediately; extraction runs
  on the daemon pool, not on the capture thread.
- `default_capture_worker.py` -- generic mode, uploads raw frames to a remote API. **No such backend
  exists in this repo**; do not use it as a model for the BPER path (Constraint 11).

### Data files

| File | Purpose |
|---|---|
| `mnt/data/dati.csv` | Ground-truth dataset -- **expected here but absent from repo and git** (`/mnt` gitignored); required by the CLI |
| `mnt/data/screen *.png` | Test banking screenshots (9 BPER images, force-tracked in git) |
| `prompts/*.json` | LLM prompt catalog: one file per prompt, loaded at startup by `prompt_store.py` |
| `edge-agent/assets/templates/bper/prompts.json` | Page catalog (names, order, template, hints) for the router and `page_registry.py` -- not a prompt file |

### Documentation

| Path | Purpose |
|---|---|
| `docs/how-it-works.md` | The pipeline mechanics extracted from this file: multi-pass stages, three run modes, edge-agent capture flow. In English, like this file, because it is the same document split for size |
| `docs/` | Narrative codebase guide in Italian (start at `docs/INDEX.md`) |
| `docs/adr/` | Architecture Decision Records in Italian, one decision per file, numbered and immutable once accepted (start at `docs/adr/README.md`). A decision that changes behaviour gets an ADR *and* a test; the ADR explains why, the test keeps it true |
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
openpyxl>=3.1.2         # Excel export (edge-agent/excel_export.py)
```

**Edge-agent (PyQt6 live capture):**
```
PyQt6>=6.4.0            # Desktop UI framework
qt-material>=2.14       # PyQt6 Material theme (edge-agent/edge_agent.py)
mss>=9.0.0             # Fast screenshot capture
pyscreenshot>=3.1      # Screenshot fallback (Linux-only env marker)
imagehash>=4.3.0       # pHash for frame dedup
torch, torchvision     # DINOv2 ViT-S/14 ML page classifier (edge-agent/page_classifier.py)
openai>=1.51.0         # SDK for the page router in `llm` mode; endpoint and model come from
                       # config.ini [llm], so it also talks to non-OpenAI providers
requests>=2.31.0       # Remote upload in DefaultCaptureWorker (generic mode only)
```

**Build tooling** (in `requirements.txt`, imported by no module):
```
pyinstaller>=6.10,<7    # portable package build only (build_exe.bat); the dist layout depends on the major
```

## Missing Infrastructure

Not yet implemented:
- `pyproject.toml` -- dependencies are listed in `requirements.txt` but not version-pinned
- Tests -- unit suite in `tests/` covers the edge-agent pure logic (page registry, stability tracker, extraction pool, async client, frame normalization, capture framing), the prompt catalog, page recognition and retry-area selection; the rest of the extraction pipeline (anchor gate, merge order, coherence check, flatten) is still untested
- CI/CD -- no pipeline configured
- Docker -- no containerization
