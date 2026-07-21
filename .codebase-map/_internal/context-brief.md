# Context Brief

## Project Profile
- **Project type / domain:** Proof-of-concept desktop/CLI tooling for AI-powered data extraction (Vision-LLM) in the Italian banking domain. Targets screenshots of the BPER credit-management application ("BStore Pratiche" / PEF pages). Signals: `README.md` line 5, `extraction/prompts.py` (Italian banking prompts), `edge-agent/assets/templates/bper/prompts.json` (BPER page definitions), field vocabulary (`ndg`, `fido`, `garanzie` in `extraction/fields.py`). Confidence: **high**.
- **Primary audience (USER-CONFIRMED 2026-07-21):** the developers and engineers who work on this project (Tri-tech solutions). The documentation produced by this pipeline is TECHNICAL documentation for them — calibrate depth, vocabulary, and detail to a professional software engineer maintaining/extending this codebase. (Supporting signals: evaluation harness, cost tracking, debug reports in `extraction/evaluation.py`; org name "Tri-tech solutions" in `edge-agent/edge_agent.py` line 35.)
- **Secondary audiences (context only, NOT the documentation target):** bank operators use the Italian-language PyQt6 edge-agent UI (`edge-agent/workers/capture/bper_capture_worker.py` lines 516-546), and a separate plain-language Italian docs layer already exists for non-technical stakeholders (`docs/`). Writers should NOT calibrate `.codebase-map/` documents to these audiences — the operator/stakeholder need is already served elsewhere. The 00-executive-summary still follows its plain-language format, but everything else is developer-facing.
- **Register (USER-CONFIRMED):** technical, precise, developer-oriented. Write in English (matching the codebase's code/comment language policy), preserving Italian domain terms verbatim (field keys like `professione_principale`, UI strings, prompt content) — do not translate them. Favor precision and depth over accessibility; file:line citations expected.
- **Scope:** Extract ~45 structured fields from 9 known BPER screen types via a multi-pass Vision-LLM pipeline; evaluate against a ground-truth CSV; report per-field accuracy and per-screen token/cost; capture screens live via a PyQt6 edge-agent that runs extraction locally.
- **Non-goals:** No remote backend/SaaS upload in the BPER path (removed, see `bper_capture_worker.py` line 710 comment "Rimossa logica di upload remoto"); no classic OCR (all extraction is VLM-based); no automated test suite, CI/CD, packaging metadata, or containerization (absent from repo).
- **Maturity:** prototype/POC in active development. Signals: repo name `poc-data-extraction`, no tests/CI, `# TEMP TEST` commented-out dedup logic in `extraction/cli.py` lines 268-273, active recent git history. Confidence: **high**.
- **Low-confidence items:** whether the POC is headed for productization (dataset-collection hooks for a "futura CNN" exist but are stubbed — `bper_capture_worker.py` `_maybe_upload_dataset()` returns immediately, lines 713-715); intended deployment model for the edge-agent (Windows launcher exists, `run_edge_agent.bat`, but no installer/packaging for it).

## Why / Context
- **Problem solved:** Manually re-keying data from the BPER credit-management application (practice header data, co-holders, credit lines, guarantees, employment/income data) is slow and error-prone. This POC reads screenshots of those pages with vision LLMs and produces structured, per-field JSON with confidence scores, then measures how accurate and how expensive that extraction is. Signals: `README.md` lines 5-23, ground-truth evaluation harness in `extraction/evaluation.py`, cost pricing table in `extraction/config.py` lines 36-49.
- **Who benefits:** Engineers assessing VLM extraction feasibility/accuracy/cost for the bank use case; operators who would otherwise transcribe screen data by hand (edge-agent guides them page-by-page through the BPER app and captures automatically).
- **Value proposition:** One shared extraction engine (`extraction/` package) exposed through three front-ends (CLI batch, Tkinter desktop, PyQt6 live capture), with built-in accuracy evaluation (OK/WRONG/MISSING/HALLUCINATED/OK_NULL per field) and per-call cost accounting, so model/prompt changes can be compared against a baseline.
- **Key decisions and history (from `git log`):**
  - Started as a monolithic `main.py`, decomposed into the `extraction/` package (commits `ce87bd3`, `699a8db`).
  - Migrated custom provider code to LangChain's unified ChatModel abstraction (`37560b9`), then simplified config to 4 unified env vars (`6ee9767`) and added `python-dotenv` (`368b7aa`).
  - Edge-agent was originally built against a remote backend (api_client, MinIO); deprecated remote components were removed (`ea04ef7`) and the BPER path was consolidated to local-only extraction via `LocalExtractionClient` (`e12af18`, and code comment at `bper_capture_worker.py:710`). Config remnants of the remote era remain (`[api]`, `[minio]` sections in `edge-agent/config.ini`).
  - Canonical field/page mapping layer and CSV delimiter work added recently (`e9f22a1`, `5709f66`, `3521ba9`), plus qt-material theming (`6e3634b`) and LLM-router hallucination guards (`c80f809`).
  - Docs layer and CLAUDE.md audits are the most recent work (`397f17a`, `f5b5a85`, `665149c`), then Windows launcher hardening (`40725a3`, `f74c21e`).
  - Branch names show explored directions: `feature/ollama-version` (local models), `feature/image-optimization`, `dev/optimization`, `bug-fix/improove_accuracy`.
- **UNCLEAR:** who the external client is (field/page "canonical" names suggest a client-facing contract — `extraction/canonical_mapping.py` docstring "backend/UI/export integration" — but no client is named in the repo); whether a remote ingestion backend will return (config.ini keeps `[api]`/`[minio]` sections that no BPER-path code uses).

## Project Identity
- **Name:** poc-data-extraction (window title "BPER Edge Agent" for the PyQt6 app, `edge-agent/ui/main_window.py` line 39; PyInstaller name "AI_Data_Extractor" in `README.md` line 91).
- **Purpose:** AI-powered extraction of structured fields from Italian BPER banking screenshots via a multi-pass (anchor → main → retry) Vision-LLM pipeline, with ground-truth evaluation and cost reporting.
- **Target users:** Internal engineers (accuracy/cost evaluation) and bank operators (live capture UI).
- **Project type:** Python POC — CLI batch tool + two desktop GUIs (Tkinter, PyQt6) sharing one library package. No web service, no published package.

## Tech Stack
- **Language:** Python. `CLAUDE.md`/`README.md` say 3.8+; compiled bytecode in `extraction/__pycache__/` is CPython 3.13; `run_edge_agent.bat` targets 3.13 then 3.12 (lines 50-52).
- **Frameworks:**
  - LangChain (`langchain-core`, `langchain-openai`, `langchain-google-genai`) — unified ChatModel + structured output (`extraction/llm_factory.py`, `extraction/vlm_client.py`).
  - PyQt6 + qt-material — edge-agent UI (`edge-agent/edge_agent.py` applies `dark_cyan.xml` theme).
  - Tkinter (stdlib) — desktop GUI (`gui_app.py`).
- **Databases:** none. Results are in-memory dicts persisted to JSON/CSV files.
- **Key dependencies (with purpose)** — all in root `requirements.txt` (loosely bounded, not pinned):
  - `Pillow>=10.0.0` — image normalize/crop/enhance (`extraction/imaging.py`, `edge-agent/image_ops.py`)
  - `pandas` — ground-truth CSV loading and report writing (`extraction/evaluation.py`)
  - `python-dotenv` — `.env` loading in all three entry points
  - `pydantic` (transitive via LangChain) — structured-output schemas (`extraction/schemas.py`)
  - `mss>=9.0.0` — fast screen capture (`bper_capture_worker.py` `_capture_screenshot()`)
  - `pyscreenshot>=3.1` (Linux-only marker) — fallback capture used by `DefaultCaptureWorker`
  - `imagehash>=4.3.0` — pHash frame dedup (`bper_capture_worker.py` `_is_duplicate_frame()`)
  - `torch`, `torchvision` — DINOv2 ViT-S/14 page classifier (`edge-agent/page_classifier.py`; degrades gracefully to disabled if torch import fails)
  - `openai>=1.51.0` — direct OpenAI SDK used only by `LLMPageRouter` (`edge-agent/llm_router.py`)
  - `openpyxl>=3.1.2` — optional page-sequence Excel loading (`bper_capture_worker.py` `_load_page_sequence()`)
  - `requests>=2.31.0` — remote frame upload in generic mode only (`default_capture_worker.py`)
  - `streamlit` — **orphaned**: listed in `requirements.txt` line 5 but no importer exists (the old `app.py` was removed in commit `ea04ef7`)
- **Build/dev tools:** none configured (no pyproject.toml, linter, formatter, or test framework). PyInstaller build recipe documented in `README.md` lines 78-100. Windows launcher `run_edge_agent.bat` self-heals a stale `.venv`.

## Directory Structure
```
poc-data-extraction/
├── main.py                     # Shim entry: .env load + CLI batch, or --gui → edge-agent
├── gui_app.py                  # Tkinter desktop GUI (upload, provider/model pick, results, export)
├── run_edge_agent.bat          # Windows launcher: venv bootstrap + edge-agent start
├── claude_.bat                 # Dev helper: launches Claude Code with agent-teams flag
├── requirements.txt            # Single dependency list for everything
├── .env.example                # Env var template (committed); .env is gitignored but present locally
├── CLAUDE.md / README.md       # AI-assistant guide / project README (Italian)
├── extraction/                 # Core engine package (no UI code)
│   ├── __init__.py             # Public API re-exports (__all__, backward-compat)
│   ├── config.py               # Env-var config, crop coords, pricing table, retry-area maps
│   ├── fields.py               # FIELD_KEYS (45 keys), CSV_TO_SCHEMA mapping
│   ├── field_definitions.py    # Canonical display-name + page_key per schema key
│   ├── page_definitions.py     # Canonical page keys/names, aliases, sheet order
│   ├── canonical_mapping.py    # build_canonical_field_entries() for client-facing output
│   ├── schemas.py              # Pydantic models (ExtractionResponse, AnchorResponse, ...)
│   ├── prompts.py              # Italian VLM prompts: main, anchor, 3 area-retry prompts
│   ├── normalization.py        # is_nullish, norm_*, pick_best, classify_field, mismatch guard
│   ├── imaging.py              # normalize_image, crop_relative, PNG encoding, debug crops
│   ├── vlm_client.py           # call_vlm / call_vlm_with_retry, cost estimation, Gemini paths
│   ├── llm_factory.py          # create_chat_model() — the single LLM provider factory
│   ├── pipeline.py             # ExtractionPipeline: anchor → main → retry orchestration
│   ├── evaluation.py           # GT loader, eval_outputs, debug report, CSV export, cost summary
│   └── cli.py                  # BatchRunner + run_extraction_batch + CLI main()
├── edge-agent/                 # PyQt6 live-capture app (imports extraction/ via sys.path)
│   ├── edge_agent.py           # Qt entry point (theme, AgentConfig, MainWindow)
│   ├── config.py               # AgentConfig: parses config.ini with defaults
│   ├── config.ini              # Committed INI (fps, router=llm, monitor, [llm] incl. api_key)
│   ├── local_extraction_client.py  # QObject bridge: ingest_frame() → ExtractionPipeline
│   ├── llm_router.py           # PageRouter base, MLPageRouter, LLMPageRouter (OpenAI Vision)
│   ├── page_classifier.py      # BPERPagePrototypeClassifier (DINOv2 ViT-S/14 prototypes)
│   ├── image_ops.py            # preprocess_for_ocr (scale/unsharp/autocontrast), png8/webp
│   ├── ui/
│   │   ├── main_window.py      # Tabs: Cattura, Risultati, Dati Estratti, (Debug LLM w/ --debug)
│   │   ├── capture_tab.py      # Start/stop, mode combo, FPS, force-capture, log, CSV export
│   │   ├── extraction_results_tab.py  # Pages tree + fields + raw JSON per result
│   │   ├── data_table_tab.py   # Spreadsheet view (rows=screens, cols=canonical fields)
│   │   ├── debug_tab.py        # LLM router prompt/response viewer
│   │   └── overlay.py          # Red border overlay on the captured monitor
│   ├── workers/capture/
│   │   ├── base_capture_worker.py     # QThread FPS loop; tick/error/llm_debug signals
│   │   ├── bper_capture_worker.py     # BPER flow: dedup, routing, stability, ingest_frame
│   │   └── default_capture_worker.py  # Generic flow: POST raw frames to remote API
│   └── assets/templates/bper/  # prompts.json (10 page defs), prototype embeddings JSON,
│                               #   9 template screenshots, transitions/ reference images
├── mnt/data/                   # Test data: screen 1..9.png (tracked); dati.csv EXPECTED here
│                               #   but absent from working tree (dir is gitignored via /mnt)
├── docs/                 # Italian narrative documentation layer (INDEX + docs 00-12)
├── .codebase-map/              # Auto-generated codebase map (this file lives in _internal/)
├── .claude/                    # Claude Code local settings only
└── prompts_immagini.txt        # Image-generation prompts (reference only, unused by code)
```

## Key Entry Points
- `main.py` — thin shim: suppresses pydantic warnings, loads `.env`, `from extraction import *`; `python main.py` runs `extraction.cli.main()`; `python main.py --gui` adds `edge-agent/` to `sys.path` and calls `edge_agent.main()`.
- `gui_app.py` — Tkinter `App`: API key + provider/model dropdowns (from `PROVIDER_MODELS`), image and optional GT-CSV selection, runs `run_extraction_batch()` in a background thread, writes `poc_outputs_gui.json` / `poc_results_gui.csv` / `poc_debug_gui.csv`.
- `edge-agent/edge_agent.py` — Qt app: loads root `.env`, applies qt-material theme, reads `edge-agent/config.ini` into `AgentConfig`, shows `MainWindow` (with Debug LLM tab only if `--debug` passed).
- `run_edge_agent.bat` — Windows bootstrap: probes/rebuilds `.venv` (prefers Python 3.13), installs `requirements.txt`, launches the edge-agent forwarding args.

## Core Entities / Data Model
Pydantic models in `extraction/schemas.py` (used with LangChain `.with_structured_output()`):
- **FieldResult** — `value: Optional[str]`, `confidence: float`, `evidence_text: Optional[str]`, `section: Optional[str]`. The atom of every extracted field.
- **FieldsModel** — dynamically created via `create_model()` with one `Optional[FieldResult]` per key in `FIELD_KEYS` (single source of truth, `schemas.py` lines 46-49).
- **Soggetto** — `ndg`, `denominazione`, `ruolo` + confidence/evidence (co-holders table).
- **Fido** — `n_fido`, `rapporto`, `descrizione`, `scadenza`, `importo_euro`, `tipo_op` + confidence/evidence (credit lines).
- **Garanzia** — `n_gar`, `descrizione`, `fido`, `ndg`, `denominazione`, `importo_percentuale`, `tipo_op` + confidence/evidence (guarantees).
- **ExtractionResponse** — `fields: FieldsModel`, `soggetti: List[Soggetto]`, `fidi: List[Fido]`, `garanzie: List[Garanzia]`. Main-pass and retry-pass schema.
- **AnchorResponse** — `fields.{ndg, denominazione}` only. Anchor-pass schema.
- **FIELD_KEYS** (`extraction/fields.py`) — 45 keys: header identifiers (`ndg`, `denominazione`), practice metadata (`tipo`, `stato`, `fase`, `creazione`, `evidenze`), credit data (`filiale_relazione`, `n_fido`, `rapporto`, `descrizione`, `scadenza`, `importo_euro`, `tipo_op`), notes + 5 tooltip fields, flattened soggetti (`ndg_1..4`, `denominazione_1..4`, `ruolo_1..4`), and 13 "scheda privati" fields (`professione_principale`, `retribuzione_annua_netta`, `score_cgs`, `rating_ufficiale`, etc.). Italian keys are load-bearing domain terms — do not translate.
- **Runtime result dict** (per screen, built in `pipeline.py` `extract_from_image()`): `screen_id`, `fields` (key → FieldResult dict), `soggetti`/`fidi`/`garanzie` lists, `canonical_fields` (sorted client-facing entries with display_name/page_key/page_name from `canonical_mapping.py`), `_attempts` (per-call meta), `_meta_agg` (calls, tokens, `estimated_cost_usd`, latency), `_field_sources` (which pass produced each field: ANCHOR_HEADER / CONTENT_MAIN / RETRY_{HEADER|BODY|FOOTER}), `_status` ("OK" | "ANCHOR_UNCERTAIN"; LocalExtractionClient adds "ERROR" and `_page_type`/`_page_no`/`_page_confidence`).
- **Canonical mapping layer** — `field_definitions.py` maps each schema key to a display name and one of 4 canonical page keys (`risultato_ricerca`, `elenco_soggetti`, `gestione_fidi_e_garanzie`, `note_da_richiesta`; `page_definitions.py`). Used by CSV export, Tkinter results tree, and the edge-agent DataTableTab.
- **Ground-truth CSV** (`mnt/data/dati.csv`, currently absent — see Open Questions): long format with columns `Fotogramma` / `Denominazione da attribuire` / `Valore rilevato`; loader accepts alternates (`Screenshot`/`Screen`, `Campo`/`Field`, `Valore`/`Value`) via `_find_column()` in `evaluation.py`. `CSV_TO_SCHEMA` in `fields.py` maps GT labels to schema keys.

## Identified Workflows

### 1. CLI batch extraction + evaluation
- **Trigger:** `python main.py` (requires `mnt/data/dati.csv` — `cli.main()` raises `FileNotFoundError` without it, `extraction/cli.py` line 315).
- **Steps:** load GT → collect all `.png/.jpg/.jpeg` in `INPUT_DIR` → `BatchRunner` creates two shared LangChain ChatModels (main + anchor) once → `ThreadPoolExecutor` (if `PARALLEL_ENABLED`, `PARALLEL_WORKERS`) runs `ExtractionPipeline.extract_from_screen()` per image → save `mnt/data/poc_outputs_improved.json` → `Evaluator.eval()` prints RAW + FILTERED accuracy and per-field breakdown → `build_debug_report()` writes `poc_debug_improved.csv` (semicolon-separated, utf-8-sig) → `print_cost_summary()` prints per-screen calls/tokens/USD.
- **Key files:** `extraction/cli.py`, `extraction/pipeline.py`, `extraction/evaluation.py`.

### 2. Multi-pass extraction (per image — the core algorithm)
- **Trigger:** `extract_from_screen(path)` (CLI/Tkinter; normalizes image first) or `extract_from_image(img, screen_id)` (edge-agent; image already preprocessed, `normalize_image()` intentionally bypassed).
- **Steps** (`extraction/pipeline.py`):
  1. Crop `CONTENT_CROP (0.18, 0.12, 0.98, 0.98)`; anchor pass on `HEADER_IN_CONTENT (0, 0, 1, 0.22)` extracts only NDG + DENOMINAZIONE with `AnchorResponse`; confidence gate `ANCHOR_CONF_MIN=0.95` nulls weak anchors; optional early exit if both null and `STOP_ON_ANCHOR_UNCERTAIN=1`.
  2. Main pass: full content crop + prompt with anchor hints ("NDG atteso: ...") → all fields + soggetti/fidi/garanzie in one `ExtractionResponse` call.
  3. Merge anchors back; `normalize_tipo()` post-processing.
  4. Conditional retry: any area (HEADER/BODY/FOOTER, `AREA_TO_FIELDS` in `config.py`) containing a nullish or `<0.60`-confidence field is retried with a dedicated crop (`RETRY_AREAS`), extra contrast/sharpness enhancement, and an area-specific Italian prompt (`FIELD_RETRY_PROMPTS`); retries run in a nested ThreadPoolExecutor and are capped at `MAX_CALLS_PER_SCREEN - 2`; per-field winner chosen by `pick_best()` (non-null beats null; ties → higher confidence); table lists merged by row-count-then-confidence in `_merge_tables()`.
  5. Coherence check: repairs `evidenze`→"B" and `tipo`→"BMB" from their tooltip fields (`_coherence_check()`).
  6. Aggregate `_meta_agg`, flatten first 4 soggetti to `ndg_1..4`/`denominazione_1..4`/`ruolo_1..4`, build `canonical_fields`, set `_status`.
- **Key files:** `extraction/pipeline.py`, `extraction/config.py`, `extraction/prompts.py`, `extraction/vlm_client.py`, `extraction/normalization.py`.

### 3. Edge-agent live capture (BPER mode)
- **Trigger:** `python edge-agent/edge_agent.py` (or `python main.py --gui` or `run_edge_agent.bat`) → "Avvia" in CaptureTab.
- **Steps:** `CaptureTab._on_start_capture()` gets a UUID job from `LocalExtractionClient.start_job()` → starts `BPERCaptureWorker` (QThread at configured FPS, 10 in config.ini) → each tick: mss screenshot of `monitor_index` → `preprocess_for_ocr()` (adaptive upscale, unsharp, autocontrast) → pHash dedup (Hamming ≤ `dedup_threshold`/3, with `route_retry_seconds` throttling on duplicates) → page routing (`router=llm` in config.ini: `LLMPageRouter` sends downscaled full image + header ROI to OpenAI `gpt-4o-mini` with page hints from `assets/templates/bper/prompts.json`; validates returned page name against known pages; skips catch-all "Altro / Non riconosciuto") → 2-second stability requirement (`STABILITY_SECONDS`) → `_upload_page()` detects `hasattr(api_client, "ingest_frame")` and calls `LocalExtractionClient.ingest_frame()` synchronously in the capture thread → `ExtractionPipeline.extract_from_image()` → result stored under job_id, `result_ready(job_id, result)` Qt signal → Risultati tree / Dati Estratti spreadsheet / capture counter update. Operator guidance messages announce each acquired page and the next one to open. "Acquisisci ora" force-captures a manually selected page (`force_capture()`). CSV export via `LocalExtractionClient.export_csv()` (flat, one row per screen).
- **Key files:** `edge-agent/workers/capture/bper_capture_worker.py`, `edge-agent/local_extraction_client.py`, `edge-agent/llm_router.py`, `edge-agent/ui/capture_tab.py`, `edge-agent/ui/main_window.py`.

### 4. Tkinter desktop extraction
- **Trigger:** `python gui_app.py` → select images (+ optional GT CSV) → "AVVIA ESTRAZIONE DATI".
- **Steps:** background thread calls `run_extraction_batch()` with GUI-chosen api_key/provider/model (`max_workers=min(len(images), 12)`) → writes `poc_outputs_gui.json` + `poc_results_gui.csv` → if GT CSV selected, runs `eval_outputs()` + `build_debug_report()` (`poc_debug_gui.csv`) → results tree grouped by canonical page names, summary pane with accuracy and cost totals.
- **Key files:** `gui_app.py`, `extraction/cli.py`, `extraction/evaluation.py`.

### 5. Generic capture mode (legacy remote path)
- **Trigger:** CaptureTab mode combo "Generico".
- **Steps:** `DefaultCaptureWorker` grabs full-screen via `pyscreenshot` and POSTs every frame to `{api.base_url}/jobs/{job_id}/frames` (`config.ini` `base_url=http://localhost:8081`). No page recognition, no local extraction. No such backend exists in this repo.
- **Key files:** `edge-agent/workers/capture/default_capture_worker.py`.

## Architecture Notes
- **Hub-and-spokes:** `extraction/` is a UI-free core; three front-ends import it. Edge-agent reaches it by inserting the project root into `sys.path` (`local_extraction_client.py` lines 17-19); `main.py --gui` does the reverse for `edge-agent/`.
- **Single LLM factory:** all chat-model creation goes through `create_chat_model()` (`extraction/llm_factory.py`) — provider from `LLM_PROVIDER`, cross-provider model-name sanity checks, Gemini safety settings, thinking-level only for models with "thinking" in the name. Exception: `LLMPageRouter` (page routing only) uses the raw `openai` SDK directly with its own key/model from `config.ini`.
- **Structured output strategy** (`extraction/vlm_client.py`): OpenAI → `.with_structured_output(schema, include_raw=True)`; Gemini 1.5 → json_mode with response_schema; Gemini 2.0+/3.x → free-form JSON with the schema injected into the prompt + manual Pydantic validation (complex schemas trigger INVALID_ARGUMENT otherwise, `_GEMINI_JSON_SCHEMA_MODELS` gate). `call_vlm_with_retry()` retries transient errors with capped exponential backoff but re-raises `ValueError` (parse failures) immediately.
- **Cost tracking:** every call populates `_meta` (model, tokens, latency, `estimated_cost_usd` from `PRICING_PER_1M` in `config.py`); pipeline aggregates into `_meta_agg`.
- **Thread model:** LangChain ChatModels created once per batch and shared across `ThreadPoolExecutor` workers (`BatchRunner.__init__`, comment "thread-safe — shared across all workers"); pipeline retries use a nested executor; edge-agent extraction runs synchronously inside the capture QThread; Qt signals bridge back to the UI thread.
- **Graceful degradation:** ML page classifier disables itself (returns `(None, 0.0)`) if torch import fails (`page_classifier.py` docstring, lines 9-19); LLM router returns null results if no API key/client; qt-material theme optional.
- **Field-source provenance:** `_field_sources` records which pass won each field — surfaced in the debug report (`source_attempt` column).
- **Dedup of same-page outputs** (`_deduplicate_same_page_outputs()` in `cli.py`) exists but is currently disabled: the call is commented out with `# TEMP TEST: keep all outputs until page_key mapping is validated` (lines 268-273).
- **Doc/code drift observed:** CLAUDE.md claims startup `if/raise` guards validating `FIELD_RETRY_MAP` vs `FIELD_KEYS` and `_FIELD_COMPARATORS`; neither guard nor `_FIELD_COMPARATORS` exists in current code (grep of `extraction/`). CLAUDE.md also omits `ui/data_table_tab.py` (a third "Dati Estratti" tab wired in `main_window.py` lines 68-75). `run_extraction_batch()` docstring still says "Shared by CLI (main) and Streamlit (app.py)" though `app.py` was deleted. `bper_capture_worker.py` line 42 comment says "MobileNetV3" but the classifier is DINOv2 ViT-S/14 (`page_classifier.py`).

## External Integrations
- **OpenAI API** — main extraction (via `langchain-openai`, key `LLM_API_KEY`/`OPENAI_API_KEY`) and page routing (via `openai` SDK, key from `config.ini [llm]` or env). Models: `gpt-4o` default main, `gpt-4o-mini` router.
- **Google Gemini API** — alternative extraction provider (via `langchain-google-genai`, `LLM_PROVIDER=gemini`); models listed in `PROVIDER_MODELS` incl. `gemini-1.5-*`, `gemini-2.0-*`, `gemini-3-flash-preview`.
- **DINOv2 ViT-S/14** (torch) — local ML page classification via prototype cosine similarity; prototype cache `edge-agent/assets/templates/bper/bper_page_prototypes.json`.
- **Remote frame-ingest API** (`POST /jobs/{job_id}/frames`, `http://localhost:8081`) — generic capture mode only; no backend implemented in this repo.
- **MinIO** — configured in `config.ini [minio]` but no code path uses it in the BPER-local flow (dataset upload is stubbed out); legacy remnant.

## Configuration Files
- `.env.example` (committed) — env-var template with Italian comments; `.env` (gitignored, present locally) — actual secrets.
- `edge-agent/config.ini` (**committed, tracked in git**) — `[agent]` fps=10, `window_title_contains=BPER` (declared but not enforced by capture code), `router=llm`, `monitor_index=1`, `show_capture_border=true`, `route_retry_seconds=1.0`; `[api] base_url=http://localhost:8081` (unused in BPER mode); `[minio]` defaults (unused); `[llm]` provider/model/timeout **and a hardcoded `api_key=sk-proj-...` OpenAI key committed to the repo** (`config.ini` line 23) — a security/redaction concern for any documentation; `[dataset]` enabled=true but the consuming code is a no-op stub; `[debug] show_llm_tab=true` (gates `llm_debug` signal emission; the Debug LLM tab itself additionally requires the `--debug` CLI flag, `edge_agent.py` line 51).
- `edge-agent/assets/templates/bper/prompts.json` (committed) — 10 page definitions (name, hints, fields), including catch-all "Altro / Non riconosciuto"; source of truth for LLM routing and the force-capture combo.
- `edge-agent/assets/templates/bper/bper_page_prototypes.json` (committed) — cached DINOv2 prototype embeddings.
- `.gitignore` — ignores `/mnt` (the 9 screenshots are tracked anyway), `.env*`, `build/`, `dist/`, `src/`, `__pycache__/`, `.venv/`, `temp_uploads/`, `test_no_gt/`.
- `.claude/settings.local.json` — Claude Code local permissions only.
- No pyproject.toml, setup.cfg, tox/pytest/lint config, Dockerfile, or CI workflows exist.

## Environment Variables
All read via `os.getenv()` with defaults (grep across repo; definitions in `extraction/config.py` and `extraction/llm_factory.py`):

| Variable | Default | Required | Purpose / where read |
|---|---|---|---|
| `LLM_PROVIDER` | `openai` | no | Provider selector, `config.py:17` |
| `LLM_API_KEY` | — | **yes** (or GUI-entered / legacy var) | API credential, `llm_factory.py:30` |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` | — | no | Deprecated fallbacks with DeprecationWarning, `llm_factory.py:10-40`; also router key fallback, `bper_capture_worker.py:122` |
| `LLM_MODEL` | `gpt-4o` | no | Main-pass model, `config.py:18` |
| `LLM_MODEL_ANCHOR` | = `LLM_MODEL` | no | Anchor-pass model, `config.py:19` |
| `LLM_THINKING_LEVEL` | unset | no | low/medium/high; only applied when model name contains "thinking", `llm_factory.py:72-74` |
| `INPUT_DIR` | `mnt/data` | no | Data dir (screenshots + `dati.csv` + outputs), `config.py:8` |
| `PARALLEL_WORKERS` | `4` | no | Batch thread pool size, `config.py:11` |
| `PARALLEL_ENABLED` | `1` | no | Toggle parallel batch, `config.py:12` |
| `MAX_CALLS_PER_SCREEN` | `4` | no | VLM call cap per screen (1 anchor + 1 main + retries), `config.py:54` |
| `ANCHOR_CONF_MIN` | `0.95` | no | Anchor acceptance gate, `config.py:56` |
| `STOP_ON_ANCHOR_UNCERTAIN` | `0` | no | Early-exit toggle, `config.py:55` |
| `DEBUG_MODE` | `0` | no | Verbose `[DEBUG]` logging in `cli.py`; **not listed in `.env.example` or CLAUDE.md's table**, `config.py:92` |
| `DEBUG_SAVE_CROPS` | `0` | no | Save intermediate crops to `INPUT_DIR/debug_crops`, `config.py:93` |

Note: CLAUDE.md documents `SCREENSHOT_DIR` as inert/historical; it does not appear anywhere in code (grep confirms).

## Scripts and Commands
- `python main.py` — CLI batch extraction + evaluation (needs `mnt/data/dati.csv` and `LLM_API_KEY`).
- `python main.py --gui` — launches the PyQt6 edge-agent.
- `python gui_app.py` — Tkinter desktop app.
- `python edge-agent/edge_agent.py [--debug]` — edge-agent directly; `--debug` adds the Debug LLM tab.
- `run_edge_agent.bat [--debug]` — Windows: venv bootstrap (Python 3.13 preferred) + launch.
- `pip install -r requirements.txt` — full install (torch is the heavy item).
- PyInstaller one-liner for `gui_app.py` documented in `README.md` lines 88-92.
- No Makefile, no script registry, no test command.

## Startup and Ports
- **CLI boot:** `main.py` → warnings filter → `load_dotenv()` → `extraction` package import (env vars are read at module import time in `config.py`, so env must be set before import) → `cli.main()`.
- **Edge-agent boot:** `edge_agent.py` → `load_dotenv(root/.env)` → QApplication + qt-material theme → `AgentConfig(edge-agent/config.ini)` → `MainWindow` (constructs `LocalExtractionClient`, which builds both ChatModels immediately — fails fast if no API key) → Qt event loop.
- **Config precedence for the edge-agent LLM router key:** `config.ini [llm] api_key` → `OPENAI_API_KEY` → `LLM_API_KEY` (`bper_capture_worker.py:122`). Extraction itself uses env vars only.
- **Ports:** none opened by this project. Outbound only: OpenAI/Gemini HTTPS; generic mode expects a local API at `:8081`, and MinIO config points at `:9000` (both unused in the default BPER flow).
- **Health checks:** none.

## Environment Profiles
- None. No dev/staging/prod distinction and no profile selection mechanism. Behavior varies only via env vars, `edge-agent/config.ini`, and GUI inputs. `.env` vs `.env.example` is the only local-vs-template split.

## Common Error Patterns
- `"API key required. Set LLM_API_KEY env var or pass api_key=."` — `llm_factory.py:42` (missing credential; raised at model construction, i.e., at BatchRunner/LocalExtractionClient init).
- `"Model '...' looks like a Gemini model but provider is 'openai'"` (and inverse) — `llm_factory.py:50-63` (provider/model mismatch).
- `FileNotFoundError: Ground truth CSV not found: mnt/data/dati.csv` — `cli.py:316` (CLI without GT file; currently guaranteed on a fresh clone since dati.csv is not tracked).
- `"Structured output parsing failed for {screen}/{attempt}: ..."` / `"Pydantic validation failed ..."` / `"No JSON object found in model response"` — `vlm_client.py` (model returned unparseable output; not retried).
- `"Warning: retry {AREA} for {screen} failed (keeping main-pass results)"` — `pipeline.py:291` (retry-pass failure is non-fatal).
- `"Cattura fallita N volte consecutive"` — `bper_capture_worker.py:594` (5 consecutive screenshot failures auto-stop the worker); `"mss non disponibile"` — `bper_capture_worker.py:562`.
- `"LLM client non inizializzato (manca API key o import OpenAI fallito)"` — `llm_router.py:148` (router silently returns no-match; visible only in the Debug LLM tab).
- Router hallucination guard: unknown `page_type` values from the LLM are rejected against `prompts.json` page names (`llm_router.py:225-230`).
- Dataset mismatch: evaluation marks whole screens `DATASET_MISMATCH` when extracted NDG/DENOMINAZIONE disagree with GT (`normalization.py dataset_mismatch_guard()`), and FILTERED metrics exclude them.

## Development Setup
1. Python 3.12/3.13 recommended (3.8+ claimed; torch wheel availability drives the launcher's preference — `run_edge_agent.bat:47-52`).
2. `python -m venv .venv && pip install -r requirements.txt` (or just run `run_edge_agent.bat` on Windows).
3. `cp .env.example .env`, set `LLM_API_KEY` (and `LLM_PROVIDER`/`LLM_MODEL` for Gemini).
4. Obtain/create `mnt/data/dati.csv` (not in the repo) to run the CLI; the Tkinter GUI and edge-agent work without it.
5. Verify: `python main.py` completes with accuracy + cost report; `python gui_app.py` smoke test; `python edge-agent/edge_agent.py` capture smoke test (Risultati tab populates).
6. No automated tests exist — validation is manual, comparing accuracy/cost output against a baseline (per `CLAUDE.md` Testing & Validation).

## Open Questions
- **UNCLEAR: `mnt/data/dati.csv` is referenced everywhere (CLI hard-requires it, README documents its format) but is absent from both the working tree and git** (`/mnt` is gitignored; only the 9 PNGs were force-added). Where does the canonical ground truth live, and can it be shared?
- **UNCLEAR: a live-looking OpenAI API key is committed in `edge-agent/config.ini` line 23.** Is it revoked? Documentation must not reproduce it, and writers should flag secret hygiene.
- **UNCLEAR: client identity and the "canonical" contract's consumer.** `canonical_mapping.py` sorts entries into a 4-page "sheet order" for "backend/UI/export integration", but no external consumer exists in-repo.
- **UNCLEAR: fate of the remote/generic path.** `DefaultCaptureWorker` posts to a nonexistent `localhost:8081` API; `[minio]` and `[dataset]` config survive with the dataset upload stubbed to a no-op (`bper_capture_worker.py:713-715`). Legacy to delete, or planned revival?
- **UNCLEAR: page-sequence Excel/CSV.** `_load_page_sequence()` looks for `Guida pagine ITA .xlsx` and `Nomenclatura.csv` in `edge-agent/assets/templates/bper/`; neither exists, so ordering falls back to `prompts.json`. Are those files distributed separately?
- **UNCLEAR: output-dedup activation.** `_deduplicate_same_page_outputs()` is fully implemented but disabled pending "page_key mapping validation" (`cli.py:268`). What validates it?
- **UNCLEAR: model list freshness and cost accuracy.** `PROVIDER_MODELS`/`PRICING_PER_1M` include preview names (`gemini-3-flash-preview`, `gemini-3.1-flash-lite-preview`) with hardcoded prices; unknown models silently cost $0.00 (`estimate_cost_usd()` returns 0.0 on missing pricing, `vlm_client.py:21-26`) — cost reports can under-count.
- **UNCLEAR: `window_title_contains` setting** is loaded and editable in the UI but no capture code filters by window title (capture is whole-monitor via mss).
- **Doc drift to reconcile when writing:** CLAUDE.md's claims about startup if/raise guards and `_FIELD_COMPARATORS` (not in code), the missing `data_table_tab.py` in its module table, the stale Streamlit reference in `run_extraction_batch()`'s docstring, README's "18 campi" framing vs the 45 `FIELD_KEYS`, and the "MobileNetV3" comment vs the actual DINOv2 classifier.
