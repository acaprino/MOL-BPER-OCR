# Project Anatomy

This document is the practical map for configuring, running, and navigating `poc-data-extraction`. It covers every directory, configuration file, environment variable, runnable command, and startup behavior -- the things you need on day one to stop guessing and start working. For high-level design, see [Architecture](04-architecture.md); for step-by-step setup, see [Getting Started](07-getting-started.md).

## Directory Tree

```
poc-data-extraction/
  main.py                              # CLI entry point; --gui flag launches edge-agent
  gui_app.py                           # Standalone Tkinter desktop GUI for manual extraction
  requirements.txt                     # All Python dependencies (extraction + edge-agent combined)
  .env.example                         # Environment variable template (committed)
  .env                                 # Actual env vars with API keys (gitignored)
  .gitignore                           # Excludes .env, __pycache__, /mnt, build/, dist/, .venv/
  CLAUDE.md                            # Comprehensive project documentation (276 lines)
  README.md                            # Italian-language README with usage guide
  prompts_immagini.txt                 # Reference-only image generation prompts (unused by pipeline)
  extraction/                          # Core Python package: all extraction business logic
    __init__.py                        # Public API re-exports (46 symbols in __all__)
    config.py                          # Env-var config, crop coordinates, pricing tables, helpers
    fields.py                          # FIELD_KEYS list (40+ fields), CSV_TO_SCHEMA mapping
    field_definitions.py               # Canonical field definitions (display_name, page_key)
    page_definitions.py                # Canonical page names, aliases, sheet ordering
    canonical_mapping.py               # Converts extracted fields to canonical backend entries
    schemas.py                         # Pydantic models: ExtractionResponse, AnchorResponse, etc.
    prompts.py                         # Italian VLM prompts (PROMPT, ANCHOR_PROMPT, retry prompts)
    normalization.py                   # Text normalization, field classification, pick_best
    imaging.py                         # normalize_image, crop_relative, img_to_png_bytes
    vlm_client.py                      # call_vlm, call_vlm_with_retry, estimate_cost_usd
    llm_factory.py                     # create_chat_model -- ChatModel factory (OpenAI/Gemini)
    pipeline.py                        # ExtractionPipeline: anchor -> main -> retry multi-pass
    evaluation.py                      # Evaluator, eval_outputs, debug_report, cost_summary
    cli.py                             # BatchRunner, run_extraction_batch, main() CLI entry
  edge-agent/                          # PyQt6 desktop agent for live screen capture
    __init__.py                        # Empty package marker
    edge_agent.py                      # App entry point: loads .env, AgentConfig, MainWindow
    config.py                          # AgentConfig class: loads config.ini
    config.ini                         # INI config with 6 sections (agent, api, minio, llm, dataset, debug)
    local_extraction_client.py         # LocalExtractionClient: bridges capture to extraction pipeline
    llm_router.py                      # PageRouter, MLPageRouter, LLMPageRouter
    page_classifier.py                 # BPERPagePrototypeClassifier (DINOv2 + cosine similarity)
    image_ops.py                       # preprocess_for_ocr, to_png8, to_webp_lossless
    ui/                                # PyQt6 UI components
      main_window.py                   # MainWindow: 4 tabs (Cattura/Risultati/Dati/Debug)
      capture_tab.py                   # CaptureTab: start/stop, FPS, force capture, log
      extraction_results_tab.py        # Pages tree, fields table, raw JSON, CSV export
      data_table_tab.py                # Spreadsheet view, column rename, CSV/Excel export
      debug_tab.py                     # Raw LLM router JSON debug output
      overlay.py                       # CaptureBorderOverlay: red border on captured monitor
    workers/capture/                   # Screenshot capture workers (QThread-based)
      base_capture_worker.py           # BaseCaptureWorker(QThread): FPS loop, signals
      bper_capture_worker.py           # BPERCaptureWorker: dedup, routing, stability
      default_capture_worker.py        # DefaultCaptureWorker: generic remote upload mode
    assets/templates/bper/             # BPER-specific detection assets
      prompts.json                     # LLM router page definitions (5 pages)
      bper_page_prototypes.json        # Cached DINOv2 prototype embeddings
      screen 1-9.png                   # Prototype images for ML page matching
      transitions/                     # ~25 transition state screenshots for detection training
  mnt/data/                            # Test data directory (gitignored via /mnt)
    screen 1-9.png                     # 9 BPER banking screenshots for testing
    dati.csv                           # Ground truth dataset
  .idea/                               # PyCharm project config (not gitignored, but not essential)
  .claude/                             # Claude AI assistant settings
  .venv/                               # Python virtual environment (gitignored)
```

## Configuration Files

### Application Configuration

**`extraction/config.py`** -- The central configuration module for the extraction pipeline. Reads all environment variables at import time via `os.getenv()` and exposes them as module-level constants. Contains crop coordinates (`CONTENT_CROP`, `HEADER_IN_CONTENT`, `RETRY_AREAS`), LLM pricing tables (`PRICING_PER_1M`), field-to-retry-area mapping (`FIELD_RETRY_MAP`, `AREA_TO_FIELDS`), and the `get_screenshot_paths()` helper. Committed. Works out of the box with defaults; see the Environment Variables section below for tuning.

**`edge-agent/config.ini`** -- INI-format configuration for the edge-agent desktop application. Six sections: `[agent]` (FPS, router mode, monitor index, preprocessing parameters), `[api]` (base URL), `[minio]` (endpoint, credentials, bucket), `[llm]` (provider, model, timeout, API key), `[dataset]` (collection settings for future CNN), and `[debug]` (LLM debug tab toggle). Loaded by `AgentConfig` in `edge-agent/config.py`. Committed to the repository. **Warning:** line 23 of this file contains a plaintext OpenAI API key. This is a credential leak in the git history.

**`.env.example`** -- Template for the `.env` file. Lists every environment variable the extraction pipeline recognizes, with commented explanations in Italian. Copy this to `.env` and fill in `LLM_API_KEY` before running. Committed.

**`.env`** -- The actual environment file loaded by `python-dotenv` at startup. Contains real API keys. Gitignored -- never committed.

### Dependency and Build Configuration

**`requirements.txt`** -- All Python dependencies for both the extraction pipeline and edge-agent, combined in a single file. Minimally pinned (most packages unpinned, a few with `>=` lower bounds). Includes `torch` and `torchvision` for ML page classification, `PyQt6` for the edge-agent GUI, and `streamlit` (though the Streamlit entry point `app.py` does not exist on this branch). Committed.

### Detection Assets

**`edge-agent/assets/templates/bper/prompts.json`** -- Defines 5 BPER page types (Risultato ricerca, Elenco Soggetti, Gestione Fidi e Garanzie, Note da Richiesta, Altro / Non riconosciuto) with Italian-language `hints` used by the LLM page router. Committed.

**`edge-agent/assets/templates/bper/bper_page_prototypes.json`** -- Pre-computed DINOv2 ViT-S/14 embeddings (384 dimensions) for each prototype page. Used by `BPERPagePrototypeClassifier` in ML page routing mode. Committed.

### Editor and IDE

**`.idea/`** -- PyCharm project configuration. The `.iml` file references Python 3.13 and excludes `.venv/`, `mnt/`, and `edge-agent/` from indexing. Committed but not essential for development.

**`.claude/settings.local.json`** -- Claude AI assistant permission rules. Not relevant to application operation.

### Git Configuration

**`.gitignore`** -- Excludes `build/`, `dist/`, `*.spec` (PyInstaller artifacts), `/mnt` (test data), `.env` and `.env.local` (secrets), `temp_uploads/`, `test_no_gt/`, `__pycache__/`, `*.pyc`, and `.venv/`. Committed.

## Environment Variables

Every environment variable is read in `extraction/config.py` at module import time via `os.getenv()`, except for `LLM_API_KEY` and the legacy key variables which are read in `extraction/llm_factory.py` and `edge-agent/workers/capture/bper_capture_worker.py`. The `.env` file is loaded by `python-dotenv` at the top of `main.py` (line 7), `edge-agent/edge_agent.py` (line 11), and `edge-agent/local_extraction_client.py` (line 23).

To set up a local environment, copy the template and edit:

```bash
cp .env.example .env
# Edit .env -- at minimum, set LLM_API_KEY
```

### Required Variables

| Variable | Purpose | Read in | Default |
|----------|---------|---------|---------|
| `LLM_API_KEY` | API credential for OpenAI or Google Gemini, depending on `LLM_PROVIDER` | `extraction/llm_factory.py` (line 30) | None -- **must be set** |

### Optional Variables -- LLM Configuration

| Variable | Purpose | Read in | Default |
|----------|---------|---------|---------|
| `LLM_PROVIDER` | LLM provider selection: `openai` or `gemini` | `extraction/config.py` (line 17) | `openai` |
| `LLM_MODEL` | Model name for the main extraction pass | `extraction/config.py` (line 18) | `gpt-4o` |
| `LLM_MODEL_ANCHOR` | Model name for the anchor pass (NDG + denominazione) | `extraction/config.py` (line 19) | Same as `LLM_MODEL` |
| `LLM_THINKING_LEVEL` | Gemini 2.0+/3.x thinking budget: `low`, `medium`, or `high`. Only applies when model name contains "thinking". | `extraction/config.py` (line 20, unused constant), `extraction/llm_factory.py` (line 72, the live check) | Effectively unset. The `medium` default in `config.py` is dead code; `llm_factory.py` reads the env var with an empty default. |

### Optional Variables -- Execution

| Variable | Purpose | Read in | Default |
|----------|---------|---------|---------|
| `INPUT_DIR` | Directory containing screenshots and ground truth CSV | `extraction/config.py` (line 8) | `mnt/data` |
| `PARALLEL_WORKERS` | Thread pool size for batch extraction | `extraction/config.py` (line 11) | `12` in code; `.env.example` says `4` |
| `PARALLEL_ENABLED` | Enable parallel processing (`1`) or serial (`0`) | `extraction/config.py` (line 12) | `1` |
| `MAX_CALLS_PER_SCREEN` | Maximum VLM API calls per screenshot (anchor + main + retries) | `extraction/config.py` (line 50) | `4` |
| `ANCHOR_CONF_MIN` | Minimum confidence threshold for accepting anchor NDG/denominazione | `extraction/config.py` (line 52) | `0.95` |
| `STOP_ON_ANCHOR_UNCERTAIN` | Stop processing a screen if both anchors are null (`1` to enable) | `extraction/config.py` (line 51) | `0` (disabled) |

### Optional Variables -- Debug

| Variable | Purpose | Read in | Default |
|----------|---------|---------|---------|
| `DEBUG_MODE` | Enable verbose debug logging in CLI batch runs | `extraction/config.py` (line 88) | `0` (disabled) |
| `DEBUG_SAVE_CROPS` | Save intermediate crop images to disk for inspection | `extraction/config.py` (line 89) | `0` (disabled) |

### Legacy / Deprecated Variables

| Variable | Purpose | Read in | Default |
|----------|---------|---------|---------|
| `OPENAI_API_KEY` | Legacy OpenAI key; used as fallback when `LLM_API_KEY` is unset | `extraction/llm_factory.py` (line 34), `gui_app.py` (line 24), `edge-agent/workers/capture/bper_capture_worker.py` (line 122) | None |
| `GEMINI_API_KEY` | Legacy Gemini key; used as fallback when `LLM_API_KEY` is unset | `extraction/llm_factory.py` (line 34) | None |
| `SCREENSHOT_DIR` | Documented in `.env.example` (line 17) and `CLAUDE.md` (line 113) but **never read by any Python code**. Has no effect. | Nowhere | N/A |

### Known Default Discrepancies

Two variables have defaults that differ between code and documentation:

- **`PARALLEL_WORKERS`**: Code default is `12` (`extraction/config.py` line 11). The `.env.example` template and `CLAUDE.md` both say `4`. If you rely on the default without setting the variable, you get 12 workers.
- **`LLM_THINKING_LEVEL`**: `extraction/config.py` line 20 stores a `medium` default into a module-level constant, but that constant is not actually consumed anywhere. The gate that matters is in `extraction/llm_factory.py` line 72, which re-reads `os.getenv("LLM_THINKING_LEVEL", "")` with an empty default and only applies it when both the value is in `{low, medium, high}` and the model name contains `thinking` (line 73). So in practice, if you leave the env var unset (as `.env.example` and `CLAUDE.md` suggest), thinking mode stays off regardless of what `config.py` says. The docs and code disagree on the surface but behave identically at runtime.

## Scripts and Executables

This project has no Makefile, no npm scripts, and no formal build system. All commands are invoked directly with Python.

### Development Commands

| Command | What it does | When to use it |
|---------|-------------|----------------|
| `pip install -r requirements.txt` | Install all dependencies (extraction + edge-agent + ML) | First-time setup or after pulling new deps |
| `cp .env.example .env` | Create local env file from template | First-time setup |

### Running the Application

| Command | What it does | When to use it |
|---------|-------------|----------------|
| `python main.py` | CLI batch extraction: processes all `.png`/`.jpg` in `INPUT_DIR`, evaluates against ground truth, saves JSON + debug CSV | Batch processing of saved screenshots |
| `python main.py --gui` | Launch the edge-agent PyQt6 desktop application for live screen capture | Real-time extraction from a running BPER application |
| `python gui_app.py` | Launch the Tkinter desktop GUI for manual file selection and extraction | One-off extraction without ground truth evaluation |
| `python edge-agent/edge_agent.py` | Launch edge-agent directly (without going through `main.py`) | Alternative to `--gui` flag, useful for development |
| `python edge-agent/edge_agent.py --debug` | Launch edge-agent with the LLM debug tab visible | Inspecting LLM router prompt/response JSON |

### Build and Packaging

| Command | What it does | When to use it |
|---------|-------------|----------------|
| `pip install pyinstaller` | Install PyInstaller for `.exe` packaging | Before building a standalone executable |
| `pyinstaller --noconfirm --onefile --windowed --name "AI_Data_Extractor" --add-data "extraction;extraction" --collect-all langchain_google_genai --collect-all langchain_openai gui_app.py` | Build a standalone Windows `.exe` from `gui_app.py` | Distributing the Tkinter GUI as a single file |

The resulting `.exe` lands in `dist/AI_Data_Extractor.exe`. This is documented in `README.md` (line 91).

### Output Files

CLI batch extraction (`python main.py`) generates these files in the `INPUT_DIR` directory:

| File | Contents |
|------|----------|
| `poc_outputs_improved.json` | Full extraction results for all screenshots |
| `poc_debug_improved.csv` | Per-field accuracy breakdown against ground truth |

The Tkinter GUI (`gui_app.py`) writes to the current working directory:

| File | Contents |
|------|----------|
| `poc_outputs_gui.json` | Extraction results JSON |
| `poc_results_gui.csv` | Extracted data in CSV format |
| `poc_debug_gui.csv` | Debug report (only when ground truth CSV is provided) |

When `DEBUG_SAVE_CROPS=1`, intermediate crop images are saved to `{INPUT_DIR}/debug_crops/`.

## Startup and Boot Sequence

### CLI Batch Mode (`python main.py`)

1. `main.py` (line 7): `python-dotenv` loads `.env` from the project root.
2. `main.py` (line 8): `from extraction import *` triggers `extraction/__init__.py`, which imports `extraction/config.py`. All environment variables are read into module-level constants at this point.
3. `extraction/cli.py::main()` (line 315): Checks that `mnt/data/dati.csv` (or whatever `GROUND_TRUTH_CSV` resolves to) exists; raises `FileNotFoundError` if missing.
4. Loads ground truth via `load_ground_truth()` from `extraction/evaluation.py`.
5. Discovers all `.png`/`.jpg`/`.jpeg` files in `INPUT_DIR`.
6. Creates a `BatchRunner` (line 333), which internally calls `create_chat_model()` twice (once for the main model, once for the anchor model) and constructs an `ExtractionPipeline`.
7. Runs extraction in parallel via `ThreadPoolExecutor` (or serial if `PARALLEL_ENABLED=0`).
8. Saves JSON to `poc_outputs_improved.json`, evaluates accuracy, saves debug CSV, prints cost summary.

### Edge-Agent Mode (`python main.py --gui`)

1. `main.py` (line 7): `python-dotenv` loads `.env`.
2. `main.py` (line 16): Inserts `edge-agent/` directory into `sys.path`.
3. `edge-agent/edge_agent.py::main()` (line 24): Creates `QApplication`.
4. Applies `qt-material` dark_cyan theme (line 38-43); gracefully degrades if the package is missing.
5. Loads `edge-agent/config.ini` into `AgentConfig` (line 48).
6. Creates `MainWindow`, which creates `LocalExtractionClient` (line 37 in `edge-agent/ui/main_window.py`). The client calls `create_chat_model()` twice and builds an `ExtractionPipeline`.
7. `MainWindow` creates four tabs: CaptureTab, ExtractionResultsTab, DataTableTab, and optionally DebugTab (if `--debug` flag is present).
8. Enters the Qt event loop (`app.exec()`).

### Tkinter GUI Mode (`python gui_app.py`)

1. Imports `extraction` package (line 6), which triggers `.env` loading and config parsing.
2. Creates a `tk.Tk()` window with two tabs (Configurazione & Log, Risultati).
3. Pre-populates the API key field from `LLM_API_KEY` or `OPENAI_API_KEY` environment variables (line 24).
4. Waits for user interaction -- no extraction runs until the user selects files and clicks the start button.

### Configuration Load Order

Configuration is loaded in this order, where later values do not override earlier ones (each source fills in its own scope):

1. `python-dotenv` reads `.env` and sets OS-level environment variables.
2. `extraction/config.py` reads those environment variables via `os.getenv()` at import time.
3. For edge-agent only: `AgentConfig` reads `edge-agent/config.ini` for agent-specific settings (FPS, router mode, monitor index, etc.). The INI file has its own `[llm]` section with provider/model/api_key, which is used for the page router -- separate from the extraction pipeline's env-var configuration.

### How to Verify the App Is Running

- **CLI**: The console prints `Parallel enabled: workers=N, screens=N` and then `Done screen 1`, `Done screen 2`, etc. as each screen completes. A full run ends with accuracy metrics and cost summary.
- **Edge-agent**: The MainWindow appears with the "Cattura" tab. Clicking "Avvia" starts the capture worker. A red border overlay appears on the captured monitor. The log area shows FPS tick messages and page detection results.
- **Tkinter GUI**: The window opens with the "Configurazione & Log" tab. The API key field should show masked characters if `LLM_API_KEY` is set in the environment.

## Ports, URLs, and Service Endpoints

This project operates primarily as a local application that calls external LLM APIs. It does not expose any HTTP servers in normal operation.

### External API Endpoints

| Service | URL | Used by |
|---------|-----|---------|
| OpenAI API | `https://api.openai.com/v1` | `extraction/llm_factory.py` (via `langchain-openai`), `edge-agent/config.ini` (line 20) |
| Google Gemini API | `https://generativelanguage.googleapis.com` | `extraction/llm_factory.py` (via `langchain-google-genai`) |

### Internal References (edge-agent config.ini)

| Port | URL | Purpose | Status |
|------|-----|---------|--------|
| 8081 | `http://localhost:8081` | API base URL in `edge-agent/config.ini` `[api]` section (line 10) | **Unused in local-only mode**. The `DefaultCaptureWorker` references this for remote upload, but `BPERCaptureWorker` with `LocalExtractionClient` bypasses it entirely. |
| 9000 | `http://localhost:9000` | MinIO/S3 endpoint in `edge-agent/config.ini` `[minio]` section (line 13) | **Unused**. `_maybe_upload_dataset()` in the capture worker is a no-op. The MinIO integration is stubbed out. |

### DINOv2 Model Download

On first run of the ML page classifier, `torch.hub.load('facebookresearch/dinov2', 'dinov2_vits14')` downloads the DINOv2 ViT-S/14 model from GitHub/PyTorch Hub. This requires internet access the first time; subsequent runs use the cached model in `~/.cache/torch/hub/`.
