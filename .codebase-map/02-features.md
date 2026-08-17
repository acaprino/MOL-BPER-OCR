# Features

The project does one core thing (turn a BPER banking screenshot into structured, scored data) and wraps it in three front-ends plus a layer of live-capture intelligence. Features are grouped here by what they do for you, not by directory. Each one names its entry point in the code. For end-to-end traces see [Workflows](05-workflows.md); for the data shapes see [Data Model](06-data-model.md); for plain definitions of the Italian banking terms (`ndg`, `fido`, `soggetti`, …) see the [Glossary](11-glossary.md).

## Extraction Engine

Everything else exists to feed this engine or report on its output. It lives entirely in the UI-free **`extraction/`** package.

### Multi-pass screenshot reading

You hand the engine an image and get back one record holding every field it could read. It works in three passes rather than one, because a single prompt covering 45 fields on a dense banking screen reads less reliably than several focused ones. Orchestration is `ExtractionPipeline.extract_from_image()` / `extract_from_screen()` in **`extraction/pipeline.py`**:

- **Anchor pass** (`extract_anchors()`) crops the header strip (`HEADER_IN_CONTENT` in `extraction/config.py`) and extracts only `ndg` and `denominazione` against the minimal `AnchorResponse` schema. Values below `ANCHOR_CONF_MIN` (0.95) are *intended* to be nulled, but the gate is currently ineffective (see the callout below); with `STOP_ON_ANCHOR_UNCERTAIN=1` the pipeline exits early when the model returns both anchors as null.
- **Main pass** sends the full content crop (`CONTENT_CROP`) with anchor hints ("NDG atteso: …") and extracts all scalar fields plus the `soggetti` / `fidi` / `garanzie` tables in one call.
- **Retry pass** finds areas (HEADER / BODY / FOOTER, mapped in `AREA_TO_FIELDS`) containing nullish or sub-0.60-confidence fields and re-reads each with a dedicated crop from `RETRY_AREAS`, extra contrast/sharpness, and an area-specific prompt. Retries run in a nested thread pool, capped at `MAX_CALLS_PER_SCREEN - 2`. Per field, `pick_best()` in **`extraction/normalization.py`** decides the winner (non-null beats null; ties go to higher confidence); table lists merge by row count then confidence in `_merge_tables()`.

> ⚠ **Known inconsistency**: the anchor confidence gate does not actually filter anything. The `ndg`/`denominazione` dicts that feed the hint prompt, the early exit, and the merge are copied *before* the gate runs, and `safe_set_field(..., None)` cannot overwrite a non-null value (`extraction/pipeline.py:87-96` vs `extraction/normalization.py:78-79`). `CLAUDE.md`'s "zeroes out low-confidence anchors" describes intent, not behavior. Full analysis in [Workflows](05-workflows.md#multi-pass-extraction-pipeline); tracked in [Open Questions](08-open-questions.md#architecture).

The two entry methods differ by design: `extract_from_screen(path)` (CLI, Tkinter GUI) normalizes the image first; `extract_from_image(img, screen_id)` (edge-agent) skips `normalize_image()` because the frame was already preprocessed upstream.

Prompts live in **`prompts/*.json`** (one file per prompt) and are loaded once at startup by `prompt_store.py`, which sits at the repo root, outside `extraction/`, so reading a prompt does not pull in LangChain; `extraction/prompts.py` only exposes the historical constants (`PROMPT`, `ANCHOR_PROMPT`, `FIELD_RETRY_PROMPTS`) read from the catalog. They are written in Italian on purpose: the screens, labels, and banking terms are Italian, and the field keys (`professione_principale`, `filiale_relazione`, …) are load-bearing domain vocabulary that must not be translated.

### Provider-agnostic LLM backend

One environment variable (`LLM_PROVIDER`) switches between OpenAI (default, `gpt-4o`) and Google Gemini; nothing else changes. The single factory is `create_chat_model()` in **`extraction/llm_factory.py`**: it lazily imports the right provider package, applies Gemini safety settings, honors `LLM_THINKING_LEVEL` only for models with "thinking" in the name, and rejects provider/model mismatches with a clear error. Calls go through `call_vlm()` / `call_vlm_with_retry()` in **`extraction/vlm_client.py`**; retries cover only transient errors, while parse failures (`ValueError`) re-raise immediately. The one deliberate exception to the factory: `LLMPageRouter` in the edge-agent uses the raw `openai` SDK for page routing only. See [Architecture](04-architecture.md) for why this seam matters.

### Structured, schema-validated output

The model is never asked for free text. Every call binds to a Pydantic schema via LangChain's `.with_structured_output()`, so a response either parses into the expected shape or fails loudly. Schemas are in **`extraction/schemas.py`**: `FieldResult` (value + confidence + evidence + section), `Soggetto`, `Fido`, `Garanzia`, and the top-level `ExtractionResponse` / `AnchorResponse`. The per-field model is generated dynamically with `create_model()` from `FIELD_KEYS` in **`extraction/fields.py`**, so the schema and the field list cannot drift apart. Provider quirks are handled in `vlm_client.py`: Gemini 1.5 uses json_mode, Gemini 2.0+/3.x gets the schema injected into the prompt with manual Pydantic validation.

### Confidence and per-field provenance

Every field records which pass produced its final value (`ANCHOR_HEADER`, `CONTENT_MAIN`, or `RETRY_{HEADER|BODY|FOOTER}`) in the `_field_sources` map built in `extraction/pipeline.py`, surfaced as the `source_attempt` column of the debug report. One exception: the soggetti flatten overwrites the twelve `ndg_1..4`/`denominazione_1..4`/`ruolo_1..4` keys without updating their source, so provenance for those keys can be stale (see [Data Model](06-data-model.md#result-dict)). This is how you tell not just *what* was extracted but *how*, and it is what the retry logic keys off.

### Domain coherence and normalization rules

After merging, hard-coded banking rules repair the output (`_coherence_check()` in `extraction/pipeline.py`): a present `tooltip_evidenze_b` forces `evidenze` to "B", a present `tooltip_descrizione_bmb` forces `tipo` to "BMB", and `normalize_tipo()` collapses type synonyms. Comparison-time normalization (numeric equality, date parsing, fuzzy matching for long free text) lives in **`extraction/normalization.py`** so trivial formatting differences do not count as errors.

### Canonical field and page mapping

A client-facing naming layer maps each schema key to a display name and one of four canonical page keys (`risultato_ricerca`, `elenco_soggetti`, `gestione_fidi_e_garanzie`, `note_da_richiesta`). The pieces are **`extraction/field_definitions.py`**, **`extraction/page_definitions.py`**, and `build_canonical_field_entries()` in **`extraction/canonical_mapping.py`**; each result dict carries the sorted `canonical_fields` list. Consumers today: CSV export, the Tkinter results tree, and the edge-agent's Dati Estratti table (`edge-agent/ui/data_table_tab.py`). This layer is recent (commits `e9f22a1`, `5709f66`) and its external consumer is not named in-repo; see [Open Questions](08-open-questions.md).

## Accuracy and Cost Evaluation

Reading the screens is half the point; the project exists to measure how well it reads and what that costs.

### Ground-truth scoring

Each extracted field is compared to the expected value from `mnt/data/dati.csv` (long format: `Fotogramma` / `Denominazione da attribuire` / `Valore rilevato`; the loader in **`extraction/evaluation.py`** tolerates alternate column names via `_find_column()`). `classify_field()` in `extraction/normalization.py` labels each field **OK**, **WRONG**, **MISSING** (expected a value, got null), **HALLUCINATED** (expected null, got a value), or **OK_NULL**. Caveat: `dati.csv` is currently absent from the working tree and git (`/mnt` is gitignored; only the 9 PNGs are tracked), and `cli.main()` hard-requires it: a fresh clone cannot run the CLI evaluation until the file is obtained. Tracked in [Open Questions](08-open-questions.md).

### RAW and FILTERED metrics

Accuracy is reported twice. **RAW** counts every screen; **FILTERED** drops screens where `dataset_mismatch_guard()` (`extraction/normalization.py`) detects that the extracted `ndg`/`denominazione` disagree with ground truth: if the engine read the wrong customer, scoring its other fields would be noise.

### Token and cost accounting

Every VLM call populates a `_meta` block (model, prompt/completion tokens, latency, `estimated_cost_usd` from `PRICING_PER_1M` in `extraction/config.py`), aggregated per screen into `_meta_agg` and printed by `print_cost_summary()` in `extraction/evaluation.py`. Caveat: models missing from the pricing table silently cost $0.00 (`estimate_cost_usd()` in `vlm_client.py`), so reports can under-count for preview model names.

### Debug report export

`build_debug_report()` in `extraction/evaluation.py` writes a per-screen, per-field CSV (semicolon-separated, `poc_debug_improved.csv`) with the extracted value, expected value, classification, and winning pass, the artifact you read when accuracy regresses.

## Front-Ends

Three front-ends, one engine. None re-implements extraction; the CLI and Tkinter GUI even share the same batch runner, `run_extraction_batch()` in **`extraction/cli.py`**; do not duplicate its thread-pool logic elsewhere.

### CLI batch runner

`python main.py` processes every image in `INPUT_DIR`, writes `mnt/data/poc_outputs_improved.json`, prints RAW + FILTERED accuracy and the cost summary, and writes the debug CSV. **`main.py`** is a thin shim (loads `.env`, imports `extraction`); the real work is `BatchRunner` in `extraction/cli.py`, which creates the two shared LangChain ChatModels once (they are thread-safe) and fans out over a `ThreadPoolExecutor` (`PARALLEL_WORKERS`). This is the most mature path: it is what the project's manual validation instructions target. A same-page output dedup step exists but is currently disabled (`_deduplicate_same_page_outputs()`, commented out at `extraction/cli.py:268-273` pending page_key validation).

### Tkinter desktop GUI

`python gui_app.py` opens a windowed app (**`gui_app.py`**, stdlib Tkinter): enter an API key, pick provider/model from `PROVIDER_MODELS` dropdowns, select screenshots and an optional ground-truth CSV, and run in a background thread. It calls the same `run_extraction_batch()`, writes `poc_outputs_gui.json` / `poc_results_gui.csv`, and (if a GT CSV was chosen) runs the same evaluation to produce `poc_debug_gui.csv`. Results display grouped by canonical page names with accuracy and cost totals.

### PyQt6 edge-agent

`python edge-agent/edge_agent.py` (or `python main.py --gui`, or `run_edge_agent.bat` on Windows) launches the live-capture app (**`edge-agent/edge_agent.py`**, PyQt6 + qt-material). Its window (**`edge-agent/ui/main_window.py`**) has tabs for capture control (`ui/capture_tab.py`), per-page results with raw JSON (`ui/extraction_results_tab.py`), a spreadsheet view of canonical fields (`ui/data_table_tab.py`), and an LLM-router debug view (`ui/debug_tab.py`, requires both `show_llm_tab=true` in `config.ini` and the `--debug` flag). Extraction is entirely local: `LocalExtractionClient` (**`edge-agent/local_extraction_client.py`**) bridges `ingest_frame()` straight into `ExtractionPipeline.extract_from_image()` and emits results over the `result_ready` Qt signal. There is no remote backend in this path.

## Live Capture (Edge-Agent)

These features turn the batch engine into a real-time tool. They are configured via **`edge-agent/config.ini`**, not env vars.

### Monitor capture and preprocessing

`BPERCaptureWorker` (**`edge-agent/workers/capture/bper_capture_worker.py`**, a QThread) grabs the configured monitor via `mss` at the configured FPS, then preprocesses each frame (adaptive upscale, unsharp mask, autocontrast) via `preprocess_for_ocr()` in **`edge-agent/image_ops.py`**. Because preprocessing happens here, extraction uses `extract_from_image()` and intentionally bypasses the engine's `normalize_image()`.

### Page detection and routing

Before extracting, the agent decides which BPER page is on screen, using the strategy set by `router=` in `config.ini` (implemented in **`edge-agent/llm_router.py`**):

- **`llm`** (current setting): `LLMPageRouter` sends a downscaled frame plus header ROI to OpenAI `gpt-4o-mini` with page hints from **`edge-agent/assets/templates/bper/prompts.json`** (10 page definitions including the "Altro / Non riconosciuto" catch-all). A hallucination guard rejects any page name not in the definitions.
- **`ml`**: `MLPageRouter` wraps `BPERPagePrototypeClassifier` (**`edge-agent/page_classifier.py`**): DINOv2 ViT-S/14 embeddings (384-dim) matched by cosine similarity against cached prototypes in `assets/templates/bper/bper_page_prototypes.json`. If torch fails to import, the classifier disables itself gracefully instead of crashing.
- **`hybrid`**: LLM first, ML fallback.

### Frame deduplication and stability gating

Consecutive frames are compared by perceptual hash (`imagehash` pHash, Hamming distance ≤ `dedup_threshold`); near-duplicates are skipped and re-routing is throttled by `route_retry_seconds`. A recognized page must then hold steady for 2 seconds (`STABILITY_SECONDS`) before capture, so the agent never extracts mid-scroll. Both live in `bper_capture_worker.py`.

### Operator guidance and manual override

The worker announces each acquired page and which page to open next (Italian UI strings), following an ordering that falls back to `prompts.json` when the optional page-sequence Excel/CSV is absent. "Acquisisci ora" in the capture tab force-captures a manually selected page (`force_capture()`). A red border (`CaptureBorderOverlay`, **`edge-agent/ui/overlay.py`**) marks the monitored screen.

### Live results and CSV export

Each result lands under its job ID and fires `result_ready(job_id, result)`, updating the Risultati tree, the Dati Estratti table, and the capture counter. `LocalExtractionClient.export_csv()` writes a flat CSV, one row per screen.

### Generic capture mode (legacy)

Selecting "Generico" in the capture tab runs `DefaultCaptureWorker` (**`edge-agent/workers/capture/default_capture_worker.py`**), which POSTs raw frames to `{api.base_url}/jobs/{job_id}/frames` (`http://localhost:8081` in `config.ini`). No such backend exists in this repo; this is a remnant of the pre-local-only architecture, kept but unusable as-is.

## Maturity Notes

The extraction engine and CLI evaluation path are the most exercised parts of the codebase; the edge-agent is feature-rich but carries legacy remnants (`[api]` / `[minio]` config sections no BPER-path code reads; a dataset-upload hook stubbed to a no-op at `bper_capture_worker.py:713-715`). The output-dedup step in the CLI is implemented but disabled pending validation. There is no automated test suite anywhere; validation is manual comparison of accuracy and cost output against a baseline.

One security note for anyone touching `edge-agent/config.ini`: an OpenAI API key was previously committed in its `[llm]` section, since scrubbed from git history (2026-07-21); the field now holds a redaction placeholder, and the original key must be treated as compromised and rotated. Supply the real key locally (config.ini is tracked, so prefer the `OPENAI_API_KEY` / `LLM_API_KEY` env fallbacks read at `bper_capture_worker.py:122`) and never re-commit one.
