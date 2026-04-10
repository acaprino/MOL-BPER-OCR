# Features

poc-data-extraction converts BPER banking screenshots into structured data through a combination of image processing, Vision LLM calls, and accuracy evaluation. It offers three ways to run extraction (CLI, desktop GUI, live screen capture), a multi-pass pipeline that retries weak results, a pluggable ML/LLM page detection system, and a built-in evaluation framework that scores results against ground truth.

## Multi-Pass Extraction Pipeline

The core of the project. Every screenshot passes through up to four VLM calls, each targeting a different region with a specialized prompt. See [Architecture](04-architecture.md) and [Workflows](05-workflows.md) for the full data flow.

### Anchor Pass

Extracts only the customer NDG (identifier) and Denominazione (name) from a cropped header strip. These two fields anchor the entire extraction -- if the model cannot read them with high confidence (default threshold: 0.95), the values are zeroed out.

- Entry point: `ExtractionPipeline.extract_anchors()` in `D:\Projects\poc-data-extraction\extraction\pipeline.py`
- Uses `AnchorResponse` schema from `D:\Projects\poc-data-extraction\extraction\schemas.py`
- Prompt defined as `ANCHOR_PROMPT` in `D:\Projects\poc-data-extraction\extraction\prompts.py`
- Crop region: header strip at relative coordinates `(0.00, 0.00, 1.00, 0.22)` within the content area, configured in `D:\Projects\poc-data-extraction\extraction\config.py`

### Main Pass

Sends the full content area (sidebar removed) to the VLM with the complete Italian extraction prompt. The prompt includes hints from the anchor pass ("NDG atteso: ...", "Denominazione attesa: ...") so the model can validate what it reads. Returns all 40+ fields, plus structured tables for subjects (soggetti), loans (fidi), and guarantees (garanzie).

- Entry point: the main-pass section of `ExtractionPipeline.extract_from_image()` in `D:\Projects\poc-data-extraction\extraction\pipeline.py`
- Uses `ExtractionResponse` schema (dynamically built from `FIELD_KEYS`) in `D:\Projects\poc-data-extraction\extraction\schemas.py`
- Full prompt in `PROMPT` at `D:\Projects\poc-data-extraction\extraction\prompts.py`
- Content crop: `(0.18, 0.12, 0.98, 0.98)` removes the BPER sidebar

### Retry Pass

After the main pass, the pipeline inspects every field. Any field that came back null or below 0.60 confidence triggers a retry for its area (HEADER, BODY, or FOOTER). Each area gets a tighter crop, enhanced contrast and sharpness, and an area-specific prompt. Retries run in parallel. Results merge via `pick_best()` -- the higher-confidence value wins.

- Entry point: `ExtractionPipeline._retry_areas()` in `D:\Projects\poc-data-extraction\extraction\pipeline.py`
- Area definitions and field-to-area mapping in `RETRY_AREAS` and `AREA_TO_FIELDS` at `D:\Projects\poc-data-extraction\extraction\config.py`
- Area-specific prompts (`RETRY_PROMPT_HEADER`, `RETRY_PROMPT_BODY`, `RETRY_PROMPT_FOOTER`) in `D:\Projects\poc-data-extraction\extraction\prompts.py`
- Budget: limited to `MAX_CALLS_PER_SCREEN - 2` retries (default: 2 retries after the anchor + main passes)

### Coherence Check

A post-processing step that uses tooltip fields to correct the main fields. If `tooltip_evidenze_b` has a value but `evidenze` is null or looks numeric, `evidenze` gets set to "B". If `tooltip_descrizione_bmb` has a value but `tipo` is null, `tipo` gets set to "BMB".

- Entry point: `ExtractionPipeline._coherence_check()` in `D:\Projects\poc-data-extraction\extraction\pipeline.py`

## Multi-Provider LLM Support

The extraction engine works with both OpenAI and Google Gemini models through a factory pattern. You switch providers via the `LLM_PROVIDER` environment variable. Each provider has different structured output handling. See [Configuration Guide](10-configuration-guide.md#switching-between-providers) for the exact `.env` recipes.

### LLM Factory

Creates thread-safe LangChain `ChatModel` instances. Uses lazy imports so only the installed provider's package gets loaded. Validates that the model name matches the provider (prevents using `gpt-4o` with Gemini or `gemini-2.0-flash` with OpenAI).

- Entry point: `create_chat_model()` in `D:\Projects\poc-data-extraction\extraction\llm_factory.py`
- Supported providers and models listed in `PROVIDER_MODELS` at `D:\Projects\poc-data-extraction\extraction\config.py`

### OpenAI Structured Output

Uses LangChain's `.with_structured_output(PydanticModel)` to get guaranteed schema-conformant JSON from OpenAI models. The prompt goes as a `SystemMessage`, and the screenshot goes as a base64-encoded `image_url` in a `HumanMessage`.

- Implementation: the OpenAI branch of `call_vlm()` in `D:\Projects\poc-data-extraction\extraction\vlm_client.py`

### Gemini Structured Output

Gemini 1.5 models use LangChain's `json_mode` with `response_schema`. Newer Gemini models (2.0+, 3.x) reject complex schemas, so the code falls back to free-form JSON: the Pydantic JSON schema gets injected into the prompt text, the model responds with `application/json` MIME type, and the response is manually parsed and validated with Pydantic.

- Implementation: `_call_vlm_gemini_freeform()` and the Gemini branch of `call_vlm()` in `D:\Projects\poc-data-extraction\extraction\vlm_client.py`
- Schema mode selection controlled by `_GEMINI_JSON_SCHEMA_MODELS` in the same file

### Retry with Backoff

Transient API errors (rate limits, timeouts) get exponential backoff retries up to 3 attempts. Parsing and validation errors (`ValueError`) are raised immediately -- they are not transient.

- Entry point: `call_vlm_with_retry()` in `D:\Projects\poc-data-extraction\extraction\vlm_client.py`
- Backoff formula: `min(8.0, 2^i * 0.8) + 0.05*i` seconds

## Image Processing

Screenshots go through normalization before any VLM call.

### Normalization

Resizes the image so its long side is 1800 pixels, applies a small contrast boost (1.05x), and runs an unsharp mask filter for edge enhancement. This produces cleaner input for the VLM without drastically altering the image.

- Entry point: `normalize_image()` in `D:\Projects\poc-data-extraction\extraction\imaging.py`

### Relative Cropping

All crop regions are defined as relative coordinates `(left, top, right, bottom)` in the range 0.0-1.0. This makes crops resolution-independent. The main content crop at `(0.18, 0.12, 0.98, 0.98)` removes the BPER navigation sidebar and top chrome.

- Entry point: `crop_relative()` in `D:\Projects\poc-data-extraction\extraction\imaging.py`
- Crop definitions: `CONTENT_CROP`, `HEADER_IN_CONTENT`, and `RETRY_AREAS` in `D:\Projects\poc-data-extraction\extraction\config.py`

### Debug Crop Saving

When `DEBUG_SAVE_CROPS=1`, every intermediate crop image gets saved to `mnt/data/debug_crops/` for visual inspection.

- Entry point: `save_debug_crop()` in `D:\Projects\poc-data-extraction\extraction\imaging.py`

## Field Definitions and Schemas

The project extracts 40+ fields across nine BPER screens. Fields are defined once and used everywhere.

### Field Keys

A single ordered list of all extractable field names. This list drives the dynamic Pydantic model creation, the evaluation logic, and the CSV export.

- Definition: `FIELD_KEYS` in `D:\Projects\poc-data-extraction\extraction\fields.py`
- Includes header fields (ndg, denominazione, tipo, stato, fase), table fields (n_fido, rapporto, etc.), flattened subject fields (ndg_1 through ruolo_4), demographic fields (professione_principale, retribuzione_annua_netta), and tooltip fields

### Dynamic Pydantic Schema

The `FieldsModel` is created at import time using Pydantic's `create_model()`, generating one `Optional[FieldResult]` attribute per entry in `FIELD_KEYS`. This means adding a new field requires only adding its name to the list -- no model class changes needed. See [Data Model](06-data-model.md#fieldsmodel) for the full entity shape.

- Definition: `FieldsModel` in `D:\Projects\poc-data-extraction\extraction\schemas.py`
- Each `FieldResult` carries: `value`, `confidence` (0.0-1.0), `evidence_text`, and `section`

### Canonical Field Metadata

Each schema key maps to a display name (for UI presentation) and a page key (which BPER screen it belongs to). Four canonical pages are defined: `risultato_ricerca`, `elenco_soggetti`, `gestione_fidi_e_garanzie`, and `note_da_richiesta`.

- Definitions: `D:\Projects\poc-data-extraction\extraction\field_definitions.py` and `D:\Projects\poc-data-extraction\extraction\page_definitions.py`
- Consumed by: `build_canonical_field_entries()` in `D:\Projects\poc-data-extraction\extraction\canonical_mapping.py`

### CSV-to-Schema Mapping

Maps Italian column headers from the ground truth CSV (e.g., "n FIDO", "Importo (E)", "Denom.") to internal schema keys (e.g., `n_fido`, `importo_euro`, `denominazione`). Handles variant spellings and trailing spaces.

- Definition: `CSV_TO_SCHEMA` in `D:\Projects\poc-data-extraction\extraction\fields.py`

## CLI Batch Processing

Process all screenshots in a directory, evaluate against ground truth, and get accuracy and cost reports. See [Workflows](05-workflows.md) for the step-by-step flow.

### Batch Runner

Creates LLM model instances once and shares them across all extraction workers. Supports parallel execution via `ThreadPoolExecutor` (configurable workers, default 12 in code). Accepts callbacks for per-screen completion and error handling.

- Entry point: `BatchRunner` class and `run_extraction_batch()` wrapper in `D:\Projects\poc-data-extraction\extraction\cli.py`
- Launched from: `main()` in `D:\Projects\poc-data-extraction\extraction\cli.py`, called by `D:\Projects\poc-data-extraction\main.py`

### Output Artifacts

The CLI saves two files: a JSON file (`poc_outputs_improved.json`) with the complete extraction results including per-field metadata, and a semicolon-delimited debug CSV (`poc_debug_improved.csv`) with per-field accuracy verdicts. Both land in the `INPUT_DIR` directory (default: `mnt/data/`).

- JSON save: `main()` in `D:\Projects\poc-data-extraction\extraction\cli.py`
- Debug CSV: `build_debug_report()` in `D:\Projects\poc-data-extraction\extraction\evaluation.py`

### Page Deduplication (experimental)

A deduplication function exists that would keep only the best result per canonical page across multiple screenshots. It scores outputs by filled-field count and confidence. Currently this feature is implemented but commented out in the batch runner.

- Implementation: `_deduplicate_same_page_outputs()` in `D:\Projects\poc-data-extraction\extraction\cli.py` (lines 92-152, disabled at lines 268-275)

## Accuracy Evaluation

Built-in evaluation compares extraction results against a ground truth CSV.

### Field Classification

Each extracted field is classified as one of five statuses: `OK` (matches ground truth), `OK_NULL` (both null), `WRONG` (values differ), `MISSING` (ground truth has a value but extraction returned null), or `HALLUCINATED` (extraction produced a value but ground truth is null). Numeric fields use normalized number comparison. Long text fields (20+ characters) use fuzzy matching with an 0.85 threshold.

- Entry point: `classify_field()` in `D:\Projects\poc-data-extraction\extraction\normalization.py`

### Dataset Mismatch Guard

Detects when the ground truth row does not belong to the same customer as the extraction result by comparing NDG and Denominazione. Mismatched screens are excluded from the filtered accuracy metric.

- Entry point: `dataset_mismatch_guard()` in `D:\Projects\poc-data-extraction\extraction\normalization.py`

### Dual Accuracy Metrics

Reports both RAW accuracy (all fields, all screens) and FILTERED accuracy (excludes dataset-mismatched screens). Per-field breakdown shows which fields the model handles well and which it struggles with.

- Entry point: `eval_outputs()` in `D:\Projects\poc-data-extraction\extraction\evaluation.py`

### Cost Tracking

Every VLM call records prompt tokens, completion tokens, latency, and estimated USD cost. These get aggregated per screen and reported in the console summary. Pricing tables for all supported models are maintained in `PRICING_PER_1M`.

- Cost estimation: `estimate_cost_usd()` in `D:\Projects\poc-data-extraction\extraction\vlm_client.py`
- Summary output: `print_cost_summary()` in `D:\Projects\poc-data-extraction\extraction\evaluation.py`
- Pricing tables: `PRICING_PER_1M` in `D:\Projects\poc-data-extraction\extraction\config.py`

## Tkinter Desktop GUI

A standalone desktop application for interactive batch extraction.

### Provider and Model Selection

Drop-down menus let you pick the LLM provider (OpenAI or Gemini) and model. The model list updates dynamically when you switch providers. You enter your API key directly in the UI.

- Entry point: `App` class in `D:\Projects\poc-data-extraction\gui_app.py`

### File Selection and Batch Extraction

A file browser dialog selects one or more screenshot images. Optionally load a ground truth CSV for accuracy comparison. Extraction runs in a background thread using the same `run_extraction_batch()` as the CLI.

- Implementation: `run_process()` in `D:\Projects\poc-data-extraction\gui_app.py`

### Results Display

A tabbed interface shows a cost summary, accuracy metrics (if ground truth was loaded), and a tree view of all extracted fields organized by screen. Each field shows its value and confidence score.

- Implementation: `display_results()` in `D:\Projects\poc-data-extraction\gui_app.py`

## Edge Agent (Live Screen Capture)

A PyQt6 desktop application that watches the operator's monitor and extracts data from BPER screens in real time. This is the most complex interface. See [Architecture](04-architecture.md) for component relationships and [Workflows](05-workflows.md) for the capture flow.

### Live Screenshot Capture

Captures the configured monitor at a configurable FPS using the `mss` library. Images are preprocessed with contrast stretching and unsharp masking. A red border overlay marks the captured monitor area.

- Entry point: `BPERCaptureWorker._capture_screenshot()` in `D:\Projects\poc-data-extraction\edge-agent\workers\capture\bper_capture_worker.py`
- Overlay: `CaptureBorderOverlay` in `D:\Projects\poc-data-extraction\edge-agent\ui\overlay.py`
- Preprocessing: `preprocess_for_ocr()` in `D:\Projects\poc-data-extraction\edge-agent\image_ops.py`

### Frame Deduplication

Every captured frame gets a perceptual hash (pHash). If the Hamming distance from the previous frame is below a threshold (default: 3), the frame is considered a duplicate and skipped. This avoids wasting LLM calls on static screens.

- Implementation: `BPERCaptureWorker._is_duplicate_frame()` in `D:\Projects\poc-data-extraction\edge-agent\workers\capture\bper_capture_worker.py`

### Page Detection

Three routing strategies, selectable via `config.ini`:

**ML Router** -- Uses Facebook's DINOv2 ViT-S/14 vision transformer to compute image embeddings and compares them against pre-computed prototype embeddings for each known BPER page via cosine similarity. The prototype embeddings are cached in JSON. Gracefully degrades to disabled mode if PyTorch is not installed.

- Implementation: `BPERPagePrototypeClassifier` in `D:\Projects\poc-data-extraction\edge-agent\page_classifier.py`
- Prototypes: `D:\Projects\poc-data-extraction\edge-agent\assets\templates\bper\bper_page_prototypes.json`
- Wrapper: `MLPageRouter` in `D:\Projects\poc-data-extraction\edge-agent\llm_router.py`

**LLM Router** -- Sends the screenshot (downscaled to 1280px) plus a header ROI crop to OpenAI Vision with a structured page-identification prompt. Returns page type, confidence, and optional reasoning. Validates results against known page names.

- Implementation: `LLMPageRouter` in `D:\Projects\poc-data-extraction\edge-agent\llm_router.py`
- Page definitions: `D:\Projects\poc-data-extraction\edge-agent\assets\templates\bper\prompts.json`

**Hybrid** -- Tries the LLM router first; falls back to ML if the LLM returns no match.

### Temporal Stability

A detected page must remain stable for 2 seconds before extraction fires. If the operator navigates away before 2 seconds, the detection resets. This prevents extracting transitional or partially loaded screens.

- Implementation: stability logic in `BPERCaptureWorker._capture_once()` at `D:\Projects\poc-data-extraction\edge-agent\workers\capture\bper_capture_worker.py`

### Operator Guidance

After each successful capture, the agent tells the operator which BPER page to open next. The page sequence is loaded from an Excel file if present, falling back to the `prompts.json` page definitions. The guidance message updates only when the next target changes, avoiding log spam.

- Implementation: `BPERCaptureWorker._next_pending_page()` and `_load_page_sequence()` in `D:\Projects\poc-data-extraction\edge-agent\workers\capture\bper_capture_worker.py`

### Local Extraction Bridge

Connects the capture worker to the extraction pipeline without network calls. When a stable page is detected, `LocalExtractionClient.ingest_frame()` runs the full multi-pass pipeline in the capture thread, stores the result, and emits a Qt signal to update the UI tabs.

- Entry point: `LocalExtractionClient` in `D:\Projects\poc-data-extraction\edge-agent\local_extraction_client.py`

### Four-Tab UI

The edge agent window has four tabs:

- **Cattura (Capture)**: start/stop controls, FPS configuration, mode selection (BPER vs. generic), force-capture button for manual page submission, real-time log. Entry point: `D:\Projects\poc-data-extraction\edge-agent\ui\capture_tab.py`
- **Risultati (Results)**: tree view of extracted pages with status indicators, field table, raw JSON viewer, CSV export. Entry point: `D:\Projects\poc-data-extraction\edge-agent\ui\extraction_results_tab.py`
- **Dati Estratti (Data Table)**: spreadsheet view of all extracted data, column renaming, CSV and Excel export via openpyxl. Entry point: `D:\Projects\poc-data-extraction\edge-agent\ui\data_table_tab.py`
- **Debug LLM** (visible with `--debug` flag): raw JSON of the last LLM router request/response for troubleshooting page detection. Entry point: `D:\Projects\poc-data-extraction\edge-agent\ui\debug_tab.py`

### Force Capture

Operators can manually trigger capture for a specific page by name, bypassing the router and stability checks. The page name is normalized against known asset and prompt definitions.

- Entry point: `BPERCaptureWorker.force_capture()` in `D:\Projects\poc-data-extraction\edge-agent\workers\capture\bper_capture_worker.py`

## Text Normalization

Extraction results go through several normalization steps before evaluation or display.

### Tipo Normalization

Maps variant spellings of the "Tipo" field to canonical values (e.g., "mutui spesa" and "mutuo spesa" both become "BPI Mutui").

- Implementation: `normalize_tipo()` in `D:\Projects\poc-data-extraction\extraction\normalization.py`

### Number and Text Normalization

`norm_number_str()` strips currency symbols, normalizes thousands separators and decimal commas, and formats to two decimal places. `norm_text()` collapses whitespace and lowercases for comparison.

- Implementation: both in `D:\Projects\poc-data-extraction\extraction\normalization.py`

### Field Merging

When retry results arrive, `pick_best()` chooses between the existing value and the candidate based on nullity and confidence. `merge_field_sources()` tracks which pipeline pass produced the winning value for each field.

- Implementation: `pick_best()` and `merge_field_sources()` in `D:\Projects\poc-data-extraction\extraction\normalization.py`

## Data Export

### JSON Export

Full structured output including fields, tables (soggetti, fidi, garanzie), canonical field entries, metadata aggregation, field sources, and status.

- CLI output: `poc_outputs_improved.json` written by `main()` in `D:\Projects\poc-data-extraction\extraction\cli.py`
- GUI output: `poc_outputs_gui.json` written by `run_process()` in `D:\Projects\poc-data-extraction\gui_app.py`

### CSV Export

Flat CSV with one row per field per screen. Includes canonical display names, page assignments, values, confidence, and evidence text. Uses semicolon delimiter and UTF-8 with BOM encoding.

- Entry point: `export_to_csv()` in `D:\Projects\poc-data-extraction\extraction\evaluation.py`
- Edge agent CSV: `LocalExtractionClient.export_csv()` in `D:\Projects\poc-data-extraction\edge-agent\local_extraction_client.py`

### Excel Export

Available in the edge agent's Data Table tab via openpyxl.

- Entry point: `DataTableTab` in `D:\Projects\poc-data-extraction\edge-agent\ui\data_table_tab.py`
