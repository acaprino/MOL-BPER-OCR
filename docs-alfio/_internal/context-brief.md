# Context Brief

## Project Identity
- Name: poc-data-extraction
- Purpose: AI-powered structured data extraction from Italian BPER banking screenshots using multi-LLM Vision APIs (OpenAI GPT-4o, Google Gemini) via LangChain. Extracts 40+ fields from 9 banking UI screens through a multi-pass VLM pipeline, evaluates accuracy against ground truth CSV, and reports per-field metrics and cost breakdowns.
- Target users/audience: Banking operations personnel working with BPER credit management application; developers building document-to-data pipelines on banking UIs.
- Project type: Multi-interface application (CLI batch tool, Tkinter desktop GUI, PyQt6 edge-agent with live screen capture). Proof of concept.

## Tech Stack
- Language(s): Python 3.8+ (Python 3.13 observed in compiled .pyc files)
- Framework(s):
  - LangChain (langchain-core, langchain-openai, langchain-google-genai) for LLM integration
  - PyQt6 + qt-material for edge-agent desktop UI
  - Tkinter for gui_app.py desktop UI
  - Streamlit (listed in requirements, referenced in CLAUDE.md, but app.py file does not exist in repo)
- Database(s): None. In-memory dicts. Ground truth stored in CSV (mnt/data/dati.csv).
- Key dependencies (with purpose):
  - langchain-core / langchain-openai / langchain-google-genai -- LLM abstraction, structured output via Pydantic
  - pillow (Pillow>=10.0.0) -- image processing (crop, resize, enhance, filter)
  - pandas -- CSV/data handling for ground truth and exports
  - python-dotenv -- loads .env at startup
  - PyQt6>=6.4.0 -- edge-agent desktop UI framework
  - qt-material>=2.14 -- Material Design theme for PyQt6
  - mss>=9.0.0 -- fast cross-platform screenshot capture
  - imagehash>=4.3.0 -- perceptual hash (pHash) for frame dedup
  - torch / torchvision -- DINOv2 ViT-S/14 for ML page classification
  - openai>=1.51.0 -- OpenAI SDK for LLM page routing in edge-agent
  - openpyxl>=3.1.2 -- Excel export from DataTableTab
  - boto3>=1.35.0 -- MinIO/S3 (listed in requirements, dataset upload stubs present but disabled)
  - keyboard==0.13.5 -- listed in requirements (no active usage found in current code)
  - requests>=2.31.0 -- HTTP calls in DefaultCaptureWorker
  - pyscreenshot>=3.1 -- Linux-only screenshot fallback in DefaultCaptureWorker
- Build/dev tools:
  - PyInstaller (documented for .exe packaging of gui_app.py)
  - No linter/formatter config files present
  - No test framework configured
  - No CI/CD pipeline

## Directory Structure

```
poc-data-extraction/
+-- main.py                          # CLI entry point + --gui flag for edge-agent
+-- gui_app.py                       # Standalone Tkinter desktop GUI
+-- requirements.txt                 # All dependencies (extraction + edge-agent combined)
+-- .env.example                     # Environment variable template
+-- .env                             # Gitignored actual env vars
+-- .gitignore                       # Ignores .env, __pycache__, /mnt, build/, dist/
+-- CLAUDE.md                        # Comprehensive project documentation (276 lines)
+-- README.md                        # Italian-language README with usage guide
+-- prompts_immagini.txt             # Reference only: image generation prompts (not used)
+-- extraction/                      # Core Python package: all extraction business logic
|   +-- __init__.py                  # Public API re-exports (46 symbols in __all__)
|   +-- config.py                    # Env-var config, crop coords, pricing tables, helpers
|   +-- fields.py                    # FIELD_KEYS list (40+ fields), CSV_TO_SCHEMA mapping
|   +-- field_definitions.py         # Canonical field definitions (display_name, page_key)
|   +-- page_definitions.py          # Canonical page names, aliases, sheet ordering
|   +-- canonical_mapping.py         # Converts extracted fields to canonical backend entries
|   +-- schemas.py                   # Pydantic models: ExtractionResponse, AnchorResponse, etc
|   +-- prompts.py                   # Italian VLM prompts (PROMPT, ANCHOR_PROMPT, retry prompts)
|   +-- normalization.py             # Text normalization, field classification, pick_best
|   +-- imaging.py                   # normalize_image, crop_relative, img_to_png_bytes
|   +-- vlm_client.py               # call_vlm, call_vlm_with_retry, estimate_cost_usd
|   +-- llm_factory.py              # create_chat_model -- ChatModel factory (OpenAI/Gemini)
|   +-- pipeline.py                  # ExtractionPipeline: anchor -> main -> retry multi-pass
|   +-- evaluation.py                # Evaluator, eval_outputs, debug_report, cost_summary
|   +-- cli.py                       # BatchRunner, run_extraction_batch, main() CLI entry
+-- edge-agent/                      # PyQt6 desktop agent for live screen capture
|   +-- __init__.py                  # Empty package marker
|   +-- edge_agent.py                # App entry point: loads .env, AgentConfig, MainWindow
|   +-- config.py                    # AgentConfig class: loads config.ini
|   +-- config.ini                   # INI config: agent, api, minio, llm, dataset, debug
|   +-- local_extraction_client.py   # LocalExtractionClient: bridges capture to pipeline
|   +-- llm_router.py               # PageRouter, MLPageRouter, LLMPageRouter
|   +-- page_classifier.py          # BPERPagePrototypeClassifier (DINOv2 + cosine sim)
|   +-- image_ops.py                # preprocess_for_ocr, to_png8, to_webp_lossless
|   +-- ui/
|   |   +-- main_window.py          # MainWindow: 4 tabs (Cattura/Risultati/Dati/Debug)
|   |   +-- capture_tab.py          # CaptureTab: start/stop, FPS, force capture, log
|   |   +-- extraction_results_tab.py  # Pages tree, fields table, raw JSON, CSV export
|   |   +-- data_table_tab.py       # Spreadsheet view, column rename, CSV/Excel export
|   |   +-- debug_tab.py            # Raw LLM router JSON debug output
|   |   +-- overlay.py              # CaptureBorderOverlay: red border on captured monitor
|   +-- workers/capture/
|   |   +-- base_capture_worker.py   # BaseCaptureWorker(QThread): FPS loop, signals
|   |   +-- bper_capture_worker.py   # BPERCaptureWorker: dedup, routing, stability
|   |   +-- default_capture_worker.py  # DefaultCaptureWorker: generic remote upload
|   +-- assets/templates/bper/
|       +-- prompts.json             # LLM router page definitions (5 pages)
|       +-- bper_page_prototypes.json  # Cached DINOv2 embeddings
|       +-- screen 1-9.png          # Prototype images for ML page matching
|       +-- transitions/             # Transition state screenshots (~25 files)
+-- mnt/data/                        # Test data directory (gitignored via /mnt)
|   +-- screen 1-9.png              # 9 BPER banking screenshots for testing
+-- .codebase-map/                   # Documentation output directory
```

## Key Entry Points
- main.py (D:\Projects\poc-data-extraction\main.py) -- Thin shim: loads .env, imports extraction package. Without flags: calls main() for CLI batch. With --gui: launches edge-agent MainWindow.
- gui_app.py (D:\Projects\poc-data-extraction\gui_app.py) -- Standalone Tkinter desktop app: API key input, provider/model selection, file selection, batch extraction, results display in tabbed UI.
- edge-agent/edge_agent.py (D:\Projects\poc-data-extraction\edge-agent\edge_agent.py) -- PyQt6 desktop entry: loads .env, creates AgentConfig from config.ini, applies qt-material theme, creates MainWindow.
- extraction/cli.py::main() (D:\Projects\poc-data-extraction\extraction\cli.py) -- CLI batch: loads ground truth CSV, discovers screenshot PNGs in INPUT_DIR, runs BatchRunner, saves JSON outputs + debug CSV, prints accuracy and cost.
- extraction/cli.py::run_extraction_batch() -- Shared batch runner used by CLI and gui_app.py. Creates BatchRunner, delegates to ExtractionPipeline.

## Core Entities / Data Model

### FieldResult (extraction/schemas.py)
- value: Optional[str] -- extracted text value
- confidence: float -- 0.0-1.0 confidence score
- evidence_text: Optional[str] -- supporting text from image
- section: Optional[str] -- UI section where field was found

### Soggetto (extraction/schemas.py)
- ndg, denominazione, ruolo: Optional[str] -- subject identifiers
- confidence: float, evidence_text: Optional[str]

### Fido (extraction/schemas.py)
- n_fido, rapporto, descrizione, scadenza, importo_euro, tipo_op: Optional[str]
- confidence: float, evidence_text: Optional[str]

### Garanzia (extraction/schemas.py)
- n_gar, descrizione, fido, ndg, denominazione, importo_percentuale, tipo_op: Optional[str]
- confidence: float, evidence_text: Optional[str]

### ExtractionResponse (extraction/schemas.py)
- fields: FieldsModel -- dynamically created Pydantic model with Optional[FieldResult] per FIELD_KEYS entry (40+ fields)
- soggetti: List[Soggetto], fidi: List[Fido], garanzie: List[Garanzia]

### AnchorResponse (extraction/schemas.py)
- fields: AnchorFields -- contains only ndg and denominazione FieldResult

### RouterResult (edge-agent/llm_router.py)
- page_type: Optional[str], confidence: float, fields: Dict[str, Any]
- reason: Optional[str], expected: Optional[str]

### AgentConfig (edge-agent/config.py)
- Loaded from config.ini. Sections: agent (fps, router, monitor_index, preprocessing), api, minio, llm (provider, model, api_key), dataset, debug.

### Canonical Field Metadata (extraction/field_definitions.py)
- Each of 40+ schema keys maps to {display_name: str, page_key: str} linking fields to canonical BPER pages.

### Canonical Pages (extraction/page_definitions.py)
- Four canonical pages: risultato_ricerca, elenco_soggetti, gestione_fidi_e_garanzie, note_da_richiesta
- PAGE_SHEET_ORDER defines ordering for exports

## Identified Workflows

### Workflow 1: CLI Batch Extraction
- Trigger: python main.py
- Steps:
  1. main.py loads .env via python-dotenv, imports extraction.*
  2. cli.main() loads ground truth from mnt/data/dati.csv via load_ground_truth()
  3. Discovers all .png/.jpg files in INPUT_DIR
  4. Creates BatchRunner with two LangChain ChatModels (main + anchor)
  5. Runs extraction in parallel via ThreadPoolExecutor (configurable workers)
  6. Each screen: 3-pass pipeline in ExtractionPipeline.extract_from_screen()
  7. Results saved to mnt/data/poc_outputs_improved.json
  8. Evaluator.eval() computes accuracy (RAW + FILTERED metrics)
  9. Debug CSV report saved to mnt/data/poc_debug_improved.csv
  10. Cost summary printed
- Outcome: JSON outputs, debug CSV, console accuracy/cost report
- Key files: main.py, extraction/cli.py, extraction/pipeline.py, extraction/vlm_client.py, extraction/evaluation.py

### Workflow 2: Edge Agent Live Capture
- Trigger: python main.py --gui or python edge-agent/edge_agent.py
- Steps:
  1. Loads .env, creates AgentConfig from config.ini, launches PyQt6 MainWindow
  2. MainWindow creates LocalExtractionClient (bridges to ExtractionPipeline)
  3. User clicks Avvia on CaptureTab, selects BPER mode
  4. BPERCaptureWorker starts as QThread at configured FPS
  5. Each tick: captures monitor screenshot via mss, preprocesses via preprocess_for_ocr()
  6. Dedup check via pHash (Hamming distance <= threshold)
  7. Page detection via router (LLM or ML or hybrid, per config.ini)
  8. Stability check: same page for 2+ seconds
  9. On stable: LocalExtractionClient.ingest_frame() -> ExtractionPipeline.extract_from_image()
  10. Result emitted via Qt signal result_ready -> ExtractionResultsTab + DataTableTab
  11. Worker guides operator to next uncaptured page
- Outcome: Real-time extraction results; CSV/Excel export available
- Key files: edge-agent/edge_agent.py, edge-agent/config.py, edge-agent/local_extraction_client.py, edge-agent/workers/capture/bper_capture_worker.py, edge-agent/llm_router.py, edge-agent/page_classifier.py, edge-agent/ui/*.py

### Workflow 3: Multi-Pass Extraction Pipeline (core)
- Trigger: Called by BatchRunner or LocalExtractionClient
- Steps:
  1. Image normalized (resize 1800px long side, contrast, unsharp mask) -- extraction/imaging.py
  2. Content cropped via CONTENT_CROP (0.18, 0.12, 0.98, 0.98) -- removes sidebar
  3. ANCHOR PASS: Header strip (0.00, 0.00, 1.00, 0.22) sent to VLM with ANCHOR_PROMPT. Extracts NDG + denominazione. Confidence gated at 0.95.
  4. MAIN PASS: Full content with PROMPT + anchor hints. Returns all fields via Pydantic structured output.
  5. Anchors merged. Tipo normalized. 
  6. RETRY PASS: For areas with nullish/low-confidence fields, crop + enhance + resend with area prompt. Parallel retries. Results via pick_best(). Max MAX_CALLS_PER_SCREEN - 2 retries.
  7. Coherence check: tooltip-based corrections
  8. Soggetti flattened for CSV. Canonical entries built. Metadata aggregated.
- Outcome: Dict with fields, soggetti, fidi, garanzie, canonical_fields, _meta_agg, _field_sources, _status
- Key files: extraction/pipeline.py, extraction/vlm_client.py, extraction/imaging.py, extraction/prompts.py, extraction/schemas.py, extraction/normalization.py, extraction/config.py

### Workflow 4: Tkinter Desktop GUI
- Trigger: python gui_app.py
- Steps: Tkinter App with provider/model selection, file browser, background extraction via run_extraction_batch(), results in tabs
- Key files: gui_app.py, extraction/cli.py

### Workflow 5: Accuracy Evaluation
- Trigger: After batch extraction in CLI
- Steps: load_ground_truth() -> eval_outputs() with classify_field() (OK/WRONG/MISSING/HALLUCINATED/OK_NULL) -> dataset_mismatch_guard() -> RAW + FILTERED accuracy -> per-field breakdown -> debug CSV
- Key files: extraction/evaluation.py, extraction/normalization.py, extraction/fields.py

## Architecture Notes

### Layers
1. Configuration: extraction/config.py (env vars), edge-agent/config.py (INI file)
2. Data model: extraction/schemas.py (Pydantic), extraction/fields.py, field_definitions.py, page_definitions.py, canonical_mapping.py
3. Image processing: extraction/imaging.py (normalization, cropping), edge-agent/image_ops.py (OCR preprocessing)
4. LLM integration: extraction/llm_factory.py (model creation), extraction/vlm_client.py (API calls + retry)
5. Pipeline orchestration: extraction/pipeline.py (multi-pass), extraction/cli.py (batch runner)
6. Evaluation: extraction/evaluation.py, extraction/normalization.py
7. UI: gui_app.py (Tkinter), edge-agent/ui/* (PyQt6)
8. Capture: edge-agent/workers/capture/* (screenshot), edge-agent/llm_router.py + page_classifier.py (detection)

### Key Patterns
- Factory pattern: create_chat_model() creates provider-specific LangChain ChatModel via lazy imports
- Strategy pattern: PageRouter base with MLPageRouter and LLMPageRouter implementations
- Observer pattern: Qt signals (result_ready, tick, error, llm_debug) connect worker threads to UI
- Thread safety: LangChain ChatModel instances created once, shared across ThreadPoolExecutor. LocalExtractionClient uses threading.Lock.
- Multi-pass pipeline: anchor -> main -> retry. Each pass uses different crops and prompts.
- Structured output: LangChain .with_structured_output(PydanticModel) for OpenAI; manual JSON + Pydantic for newer Gemini.
- Graceful degradation: ML classifier operates in DISABLED mode if torch unavailable.

### Component Communication
- CLI: run_extraction_batch() -> BatchRunner -> ExtractionPipeline -> call_vlm_with_retry() -> LangChain ChatModel -> LLM API
- Edge-agent: BPERCaptureWorker (QThread) -> LocalExtractionClient.ingest_frame() -> ExtractionPipeline.extract_from_image() -> Qt signal result_ready -> UI tabs
- Detection: BPERCaptureWorker._detect_page() -> PageRouter.route() -> LLM API or ML classifier

## External Integrations
- OpenAI API: Via langchain-openai (ChatOpenAI) for extraction; via openai SDK directly for LLM page routing
- Google Gemini API: Via langchain-google-genai (ChatGoogleGenerativeAI) when LLM_PROVIDER=gemini
- DINOv2 (Facebook Research): torch.hub.load for ML page classification (dinov2_vits14, embedding dim 384)
- MinIO/S3: boto3 in requirements; config.ini has minio section; upload stubbed out (_maybe_upload_dataset is no-op)

## Configuration Files

| File | Purpose | Committed |
|------|---------|-----------|
| .env.example | Template for environment variables | Yes |
| .env | Actual environment variables (API keys) | No (gitignored) |
| .gitignore | Git exclusions | Yes |
| requirements.txt | Python dependencies (minimally pinned) | Yes |
| edge-agent/config.ini | Edge-agent INI config (6 sections: agent, api, minio, llm, dataset, debug) | Yes |
| edge-agent/assets/templates/bper/prompts.json | LLM page router: 5 BPER page definitions with hints | Yes |
| edge-agent/assets/templates/bper/bper_page_prototypes.json | Cached DINOv2 prototype embeddings | Yes |
| CLAUDE.md | Comprehensive project documentation | Yes |
| README.md | Italian-language project README | Yes |

## Environment Variables

| Variable | Purpose | Required | Default | Source |
|----------|---------|----------|---------|--------|
| LLM_PROVIDER | Provider selection | Optional | openai | extraction/config.py |
| LLM_API_KEY | API credential (OpenAI or Gemini) | Required | None | extraction/llm_factory.py |
| LLM_MODEL | Model for main extraction | Optional | gpt-4o | extraction/config.py |
| LLM_MODEL_ANCHOR | Model for anchor pass | Optional | same as LLM_MODEL | extraction/config.py |
| LLM_THINKING_LEVEL | Gemini 3+ thinking budget | Optional | medium (code) | extraction/config.py |
| INPUT_DIR | Data directory | Optional | mnt/data | extraction/config.py |
| SCREENSHOT_DIR | Screenshot location | Optional | same as INPUT_DIR | .env.example |
| PARALLEL_WORKERS | Thread pool size | Optional | 12 (code) / 4 (docs) | extraction/config.py |
| PARALLEL_ENABLED | Enable parallel | Optional | 1 | extraction/config.py |
| MAX_CALLS_PER_SCREEN | Max VLM calls/screen | Optional | 4 | extraction/config.py |
| ANCHOR_CONF_MIN | Min anchor confidence | Optional | 0.95 | extraction/config.py |
| STOP_ON_ANCHOR_UNCERTAIN | Stop if anchor low | Optional | 0 | extraction/config.py |
| DEBUG_SAVE_CROPS | Save crop images | Optional | 0 | extraction/config.py |
| DEBUG_MODE | Debug logging in CLI | Optional | 0 | extraction/config.py |
| OPENAI_API_KEY | Legacy OpenAI key | Optional (deprecated) | None | extraction/llm_factory.py |
| GEMINI_API_KEY | Legacy Gemini key | Optional (deprecated) | None | extraction/llm_factory.py |

Note: PARALLEL_WORKERS default is 12 in code (config.py:11) but docs/.env.example say 4.
Note: LLM_THINKING_LEVEL default is medium in code (config.py:20) but CLAUDE.md says unset.

## Scripts and Commands

| Command | Purpose |
|---------|---------|
| python main.py | CLI batch extraction (all images in INPUT_DIR) |
| python main.py --gui | Launch edge-agent PyQt6 GUI |
| python gui_app.py | Launch Tkinter desktop GUI |
| python edge-agent/edge_agent.py | Launch edge-agent directly |
| python edge-agent/edge_agent.py --debug | Edge-agent with LLM debug tab |
| pip install -r requirements.txt | Install all dependencies |

## Startup and Ports
- CLI: main.py -> extraction.cli.main(). Boot: .env -> config.py env vars -> GT CSV -> BatchRunner (LLM models) -> extraction -> evaluation
- Edge-agent: edge_agent.py::main(). Boot: .env -> QApplication -> qt-material -> config.ini -> AgentConfig -> MainWindow (LocalExtractionClient + LLM models) -> Qt loop
- Tkinter: gui_app.py. Boot: import extraction -> Tk window -> user-driven
- Ports: config.ini references localhost:8081 (api) and localhost:9000 (MinIO), unused in local-only mode
- Config load order: (1) python-dotenv .env, (2) extraction/config.py os.getenv() at import, (3) edge-agent config.ini

## Environment Profiles
- No formal dev/staging/prod profiles
- LLM_PROVIDER switches openai/gemini providers
- config.ini [agent] router= switches ml/llm/hybrid detection modes
- DEBUG_MODE + DEBUG_SAVE_CROPS enable debug outputs
- config.ini [debug] show_llm_tab=true enables debug tab

## Common Error Patterns

### Extraction (extraction/vlm_client.py)
- ValueError: No JSON object found -- Gemini free-form fails to produce JSON
- ValueError: Pydantic validation failed -- Model JSON schema mismatch
- ValueError: Structured output parsing failed -- LangChain parsing failure
- ValueError: API key required -- Missing API key (llm_factory.py)
- ValueError: Unknown provider / Model-provider mismatch -- Config errors (llm_factory.py)

### Pipeline (extraction/pipeline.py)
- Warning: retry area failed, keeping main-pass results -- Non-fatal retry failure
- Status ANCHOR_UNCERTAIN -- Both anchors null + STOP_ON_ANCHOR_UNCERTAIN=1

### Edge-agent (bper_capture_worker.py)
- RuntimeError: mss non disponibile -- Screenshot library failure
- RuntimeError: Cattura fallita N volte consecutive -- Auto-stop after 5 errors
- torch import failure -- ML classifier gracefully degrades to DISABLED

### Evaluation (extraction/evaluation.py)
- ValueError: Cannot find column in CSV -- GT CSV column detection failure
- FileNotFoundError: Ground truth CSV not found

### Retry behavior (extraction/vlm_client.py)
- Transient errors: exponential backoff min(8.0, 2^i * 0.8) + 0.05*i seconds, max 3 retries
- ValueError (parsing): immediately re-raised, no retry

## Development Setup
1. pip install -r requirements.txt
2. cp .env.example .env -- set LLM_API_KEY
3. python main.py -- CLI batch
4. python main.py --gui -- edge-agent
5. python gui_app.py -- Tkinter GUI
6. For ML classifier: torch + torchvision required (DINOv2 auto-downloaded on first run)
7. For .exe: pip install pyinstaller, see README for command

## Open Questions
- Missing app.py: CLAUDE.md references app.py as a Streamlit web UI entry point, but no app.py file exists in the repository. Was it removed or never committed to this branch?
- PARALLEL_WORKERS default discrepancy: Code default is 12 (config.py line 11) but documentation and .env.example say 4.
- LLM_THINKING_LEVEL default discrepancy: Code defaults to medium (config.py line 20) but CLAUDE.md says unset and .env.example comments it out.
- Ground truth CSV file: mnt/data/dati.csv is referenced by code but the mnt/ directory is gitignored. No dati.csv is present in the checked-out working tree.
- boto3/keyboard dependencies: Listed in requirements.txt but no active usage found in current code. _maybe_upload_dataset is a no-op. Were these for a removed feature?
- edge-agent/config.ini contains an API key on line 23. This file is committed to git. This appears to be a credential leak.
- Test suite: No tests exist. CLAUDE.md explicitly notes no test suite exists.
- CI/CD: No pipeline configured. No Dockerfile.
- Deduplication logic in cli.py: _deduplicate_same_page_outputs() is implemented but commented out (lines 268-275). Current behavior keeps all outputs.
- Domain knowledge needed: Understanding of BPER banking application UI layout is needed to validate crop coordinates, field definitions, and page classifications.
