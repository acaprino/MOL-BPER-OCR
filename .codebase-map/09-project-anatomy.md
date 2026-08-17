# Project Anatomy

This is the operator's map of `poc-data-extraction`: where things live, what each configuration file controls, every environment variable the code actually reads, the commands you can run, and the order in which each front-end wires itself together at boot. Everything here was verified against the source; where `CLAUDE.md`, `README.md`, or `.env.example` disagree with the code, this document follows the code and says so.

Three facts shape how you read the rest of this page:

- There is **no build manifest**: no `pyproject.toml`, no `Makefile`, no `setup.py`. Every command is a plain `python …` invocation, plus one Windows launcher batch file.
- There is **no Docker, no CI, and no test suite** (see [Tech Stack](03-tech-stack.md)). Validation is manual.
- Two independent configuration systems coexist: the extraction pipeline is configured **entirely through environment variables** (`extraction/config.py`), while the edge-agent is configured **through an INI file** (`edge-agent/config.ini`). The only overlap is API-key fallback, covered below.

## Directory Tree

The repository splits into two Python packages: **`extraction/`** (the UI-free core engine) and **`edge-agent/`** (the PyQt6 live-capture app), plus entry-point scripts at the root. The edge-agent is not installed as a package; it reaches `extraction/` by inserting the project root into `sys.path` (`edge-agent/local_extraction_client.py:17-19`), and `main.py --gui` does the reverse (`main.py:16-19`).

```
poc-data-extraction/
  main.py                      # Entry shim: loads .env, `from extraction import *`; default = CLI batch, --gui = edge-agent
  gui_app.py                   # Entry: Tkinter desktop GUI (API-key field, provider/model dropdowns, batch + export)
  run_edge_agent.bat           # Windows launcher: self-healing .venv bootstrap (prefers Python 3.13) + edge-agent start
  claude_.bat                  # Dev helper (untracked): launches Claude Code with the agent-teams flag
  requirements.txt             # Single dependency list for everything (loosely bounded, not pinned)
  prompt_store.py              # Prompt catalog loader: stdlib-only, outside extraction/ so reading a prompt skips LangChain
  prompts/                     # LLM prompt catalog: one JSON per prompt, read and validated once at startup
  .env.example                 # Committed env-var template (Italian comments); copy to .env
  .env                         # Local secrets (gitignored, present locally)
  .gitignore                   # Ignores .env*, /mnt, .venv/, build/, dist/, *.spec, src/, temp_uploads/, test_no_gt/
  CLAUDE.md                    # AI-assistant project guide (has some drift vs. code - noted inline below)
  README.md                    # Italian README, incl. the PyInstaller build recipe

  extraction/                  # Core engine package - pipeline, evaluation, no UI code
    __init__.py                # Public API re-exports (the `from extraction import *` surface)
    config.py                  # ALL env-var reads for the pipeline + crop coords, pricing table, retry-area maps
    fields.py                  # FIELD_KEYS (45 keys), CSV_TO_SCHEMA ground-truth mapping
    field_definitions.py       # Canonical display-name + page_key per schema key
    page_definitions.py        # Canonical page keys/names and sheet order (4 pages)
    canonical_mapping.py       # build_canonical_field_entries() - client-facing output shape
    schemas.py                 # Pydantic models: ExtractionResponse, AnchorResponse, FieldResult, …
    prompts.py                 # VLM prompt constants (main, anchor, 3 area-retry) read from prompts/*.json
    normalization.py           # Text normalization, classify_field(), pick_best(), dataset_mismatch_guard()
    imaging.py                 # normalize_image(), crop_relative(), PNG encoding, debug-crop saving
    vlm_client.py              # call_vlm() / call_vlm_with_retry(), cost estimation, Gemini schema paths
    llm_factory.py             # create_chat_model() - the single LLM provider factory (reads LLM_API_KEY)
    pipeline.py                # ExtractionPipeline: anchor → main → retry orchestration
    evaluation.py              # Ground-truth loader, eval_outputs(), debug report, cost summary
    cli.py                     # main() CLI entry + BatchRunner + run_extraction_batch() (shared with Tkinter GUI)

  edge-agent/                  # PyQt6 live-capture app (flat-name imports; needs edge-agent/ on sys.path)
    edge_agent.py              # Qt entry point: .env load, qt-material theme, AgentConfig, MainWindow
    config.py                  # AgentConfig: parses config.ini with per-key fallback defaults
    config.ini                 # Committed INI - the edge-agent's entire configuration (see below)
    local_extraction_client.py # QObject bridge: ingest_frame() → ExtractionPipeline, result_ready signal
    llm_router.py              # PageRouter base + LLMPageRouter (OpenAI Vision) + MLPageRouter
    page_classifier.py         # BPERPagePrototypeClassifier - DINOv2 ViT-S/14 prototype matching
    image_ops.py               # preprocess_for_ocr() (scale/unsharp/autocontrast), png8/webp encoders
    ui/
      main_window.py           # Tabs: Cattura, Risultati, Dati Estratti (+ Debug LLM with --debug)
      capture_tab.py           # Start/stop, mode combo, FPS, force-capture, log, CSV export
      extraction_results_tab.py# Pages tree + fields table + raw JSON per result
      data_table_tab.py        # Spreadsheet view: rows = screens, columns = canonical fields
      debug_tab.py             # LLM router prompt/response viewer
      overlay.py               # Red border overlay on the captured monitor
    workers/capture/
      base_capture_worker.py   # QThread FPS loop; tick / error / llm_debug signals
      bper_capture_worker.py   # BPER flow: pHash dedup, page routing, stability, ingest_frame()
      default_capture_worker.py# Generic flow: POSTs raw frames to a remote API (no backend in repo)
    assets/templates/bper/
      prompts.json             # 10 BPER page definitions - source of truth for LLM routing + UI combo
      bper_page_prototypes.json# Cached DINOv2 prototype embeddings for the ML router
      screen 1..9.png          # Template screenshots (prototype sources)
      transitions/             # Reference screenshots of intermediate BPER pages (not read by code)

  mnt/data/                    # Data directory (default INPUT_DIR); /mnt is gitignored, PNGs force-added
    screen 1..9.png            # The 9 test screenshots (tracked)
    dati.csv                   # Ground-truth CSV - EXPECTED here but NOT in the repo (see Open Questions)
    poc_outputs_improved.json  # CLI output (generated at runtime)
    poc_debug_improved.csv     # CLI debug report (generated at runtime)
    debug_crops/               # Intermediate crops, only when DEBUG_SAVE_CROPS=1

  docs/                  # Italian plain-language documentation layer (INDEX + docs 00-12)
  .codebase-map/               # This documentation set
  .claude/                     # Claude Code local settings (settings.local.json only)
  .idea/                       # PyCharm project files
  .venv/                       # Local virtualenv (gitignored; created by run_edge_agent.bat)
```

## Configuration Files

### Application config

- **`.env.example`** (committed): the template for pipeline environment variables, with Italian comments. Copy it to `.env` and set `LLM_API_KEY`; everything else has a working default. It documents 10 of the 12 live variables: `DEBUG_MODE` and the legacy key fallbacks are missing from it (see the table below). **`.env`** itself is gitignored (`.gitignore:12-14`) and loaded automatically by `main.py:7`, `edge-agent/edge_agent.py:9-13`, and `edge-agent/local_extraction_client.py:21-25`; but **not** by `gui_app.py`, which has no `load_dotenv` call and relies on variables already being exported in your shell (or the API key typed into its UI).

- **`edge-agent/config.ini`** (committed, tracked): the edge-agent's entire configuration, parsed by `AgentConfig` (`edge-agent/config.py:109-269`). Missing keys fall back to per-key defaults, so the file works out of the box except for the LLM router key. Sections:
  - `[agent]`: the live section. `fps = 10` (capture rate), `router = llm` (page-routing mode: `ml` | `llm` | `hybrid`), `monitor_index = 1` (mss monitor numbering, 1..N), `show_capture_border = true` (red overlay), `route_retry_seconds = 1.0` (routing throttle on duplicate frames), `window_title_contains = BPER` (loaded and editable in the UI, but no capture code filters by window title: capture is whole-monitor). The section also accepts preprocessing keys not present in the committed file (`image_scale`, `unsharp_amount`, `unsharp_radius`, `unsharp_threshold`, `upload_format`, `dedup_threshold`, `required_pages_only`, `required_pages_csv`: defaults at `edge-agent/config.py:39-49`).
  - `[llm]`: the OpenAI-Vision page router: `provider`, `base_url = https://api.openai.com/v1`, `model = gpt-4o-mini`, `timeout = 60`, and `api_key`. **Needs manual setup**: the committed value at `edge-agent/config.ini:23` is the placeholder `REDACTED_OPENAI_API_KEY`: a real key was exposed here, has been scrubbed from git history, and must now be supplied locally after rotation. Prefer leaving the INI value empty and using the env fallback instead: the router resolves its key as `config.ini [llm] api_key` → `OPENAI_API_KEY` → `LLM_API_KEY` (`edge-agent/workers/capture/bper_capture_worker.py:122,147`). Be aware that `AgentConfig.save()` would write whatever key is in memory back into the tracked file (`edge-agent/config.py:326-332`); it currently has no caller, but keep it that way or move the key out of the INI entirely.
  - `[api]`: `base_url = http://localhost:8081`. Used **only** by the legacy "Generico" capture mode (`edge-agent/workers/capture/default_capture_worker.py:62-66`); no such backend exists in this repo. Inert in the default BPER flow.
  - `[minio]`: endpoint/credentials/bucket defaults pointing at `http://localhost:9000`. Remnant of the removed remote backend; no active code path uses it.
  - `[dataset]`: `enabled = true` plus thresholds, but the consuming code is a no-op stub (`edge-agent/workers/capture/bper_capture_worker.py:713-715`). Inert.
  - `[debug]`: `show_llm_tab = true` gates emission of the `llm_debug` signal; the Debug LLM tab itself additionally requires the `--debug` CLI flag (`edge-agent/edge_agent.py:51`). You need both to see router traffic.

- **`edge-agent/assets/templates/bper/prompts.json`** (committed): 10 BPER page definitions (name, visual hints, expected fields), including the catch-all "Altro / Non riconosciuto". This file is read independently by three consumers: the LLM router (`edge-agent/llm_router.py:96-103`), the capture worker's page sequence (`edge-agent/workers/capture/bper_capture_worker.py:255-306`), and the force-capture combo in the UI (`edge-agent/ui/capture_tab.py:156-170`). Edit it and all three change together, but there is no schema validation, so a typo degrades routing silently.

- **`edge-agent/assets/templates/bper/bper_page_prototypes.json`** (committed): cached DINOv2 prototype embeddings for the ML router, loaded and revalidated by `edge-agent/page_classifier.py:104-107`. Regenerated from the template screenshots when stale; works out of the box.

### Build / tooling

- **`requirements.txt`**: the only dependency manifest, shared by all three front-ends. Loosely bounded versions, no lock file. `streamlit` is listed but orphaned (its importer, the old `app.py`, was deleted). `torch`/`torchvision` are the heavy installs and only matter for the ML page router, which degrades gracefully to disabled if they are missing (`edge-agent/page_classifier.py:9-19`).
- **`run_edge_agent.bat`**: see Scripts below; doubles as the de-facto environment-setup tool on Windows.
- No linter, formatter, pytest, tox, pre-commit, Dockerfile, or CI workflow exists anywhere in the repo.

### Editor / IDE

- **`.claude/settings.local.json`** (committed): Claude Code local permission settings only.
- **`.idea/`**: PyCharm project metadata; `.idea/.gitignore` excludes the volatile parts.

### Committed vs. gitignored

Committed: `.env.example`, `edge-agent/config.ini`, both asset JSONs, `requirements.txt`, the 9 screenshots under `mnt/data/` (force-added past the `/mnt` ignore rule). Gitignored (`.gitignore`): `.env` and variants, `/mnt` (so runtime outputs and `dati.csv` never land in git), `.venv/`, `__pycache__/`, `build/`, `dist/`, `*.spec`, `src/`, `temp_uploads/`, `test_no_gt/`.

## Environment Variables

All pipeline variables are read via `os.getenv()` **at module import time** in `extraction/config.py`: they are snapshotted into module constants when `extraction` is first imported. Consequences: (a) set them before any `import extraction`, which is why every entry point except `gui_app.py` calls `load_dotenv()` first; (b) malformed numeric values (`PARALLEL_WORKERS`, `MAX_CALLS_PER_SCREEN`, `ANCHOR_CONF_MIN`) raise `ValueError` at import, not at use (`extraction/config.py:11,54,56`).

| Variable | Default | Required | Purpose | Read at |
|---|---|---|---|---|
| `LLM_API_KEY` | - | **yes** (unless typed into the Tkinter GUI or a legacy var is set) | API credential for OpenAI or Gemini | `extraction/llm_factory.py:30`; GUI prefill `gui_app.py:24` |
| `OPENAI_API_KEY` | - | no | Legacy fallback for `LLM_API_KEY` (emits `DeprecationWarning`); also 2nd choice for the edge-agent router key | `extraction/llm_factory.py:32-40`; `edge-agent/workers/capture/bper_capture_worker.py:122,147` |
| `GEMINI_API_KEY` | - | no | Legacy fallback when `LLM_PROVIDER=gemini` (emits `DeprecationWarning`) | `extraction/llm_factory.py:10-13,32-40` |
| `LLM_PROVIDER` | `openai` | no | Provider selector: `openai` or `gemini` | `extraction/config.py:17` |
| `LLM_MODEL` | `gpt-4o` | no | Model for the main extraction pass | `extraction/config.py:18` |
| `LLM_MODEL_ANCHOR` | = `LLM_MODEL` | no | Model for the anchor pass | `extraction/config.py:19` |
| `LLM_THINKING_LEVEL` | unset | no | `low`/`medium`/`high`; applied only when the model name contains `thinking` | `extraction/config.py:20`, `extraction/llm_factory.py:72-74` |
| `INPUT_DIR` | `mnt/data` | no | Data directory: screenshots, `dati.csv`, and CLI outputs | `extraction/config.py:8` |
| `PARALLEL_ENABLED` | `1` | no | `0` disables the batch thread pool | `extraction/config.py:12` |
| `PARALLEL_WORKERS` | `4` | no | Batch thread-pool size | `extraction/config.py:11` |
| `MAX_CALLS_PER_SCREEN` | `4` | no | Hard cap on VLM calls per screenshot (1 anchor + 1 main + retries) | `extraction/config.py:54` |
| `ANCHOR_CONF_MIN` | `0.95` | no | Anchor-pass confidence gate - intended null-out, currently ineffective in the pipeline (see [Workflows](05-workflows.md#multi-pass-extraction-pipeline)) | `extraction/config.py:56` |
| `STOP_ON_ANCHOR_UNCERTAIN` | `0` | no | `1` = abort a screen early when both anchors are null | `extraction/config.py:55` |
| `DEBUG_MODE` | `0` | no | Verbose `[DEBUG]` logging in the batch runner. **Undocumented** in `.env.example` and `CLAUDE.md` - code is the only source | `extraction/config.py:92` |
| `DEBUG_SAVE_CROPS` | `0` | no | Save intermediate crop images to `INPUT_DIR/debug_crops` | `extraction/config.py:93-94` |
| `PROMPTS_DIR` | *(unset)* | no | Alternative prompt-catalog directory. The one pipeline variable read **outside** `config.py`; when set it is the only candidate, with no fallback to the bundled copy | `prompt_store.py:222` |

Two non-variables worth knowing: `SCREENSHOT_DIR` appears in `CLAUDE.md`'s table but nowhere in code (grep confirms: it is inert), and the edge-agent itself takes **no** dedicated env vars; it is configured by `config.ini`, falling back to `OPENAI_API_KEY`/`LLM_API_KEY` only for the router key.

Local setup: `copy .env.example .env` (or `cp` on POSIX), set `LLM_API_KEY`, and (for Gemini) set `LLM_PROVIDER=gemini` plus a Gemini model in `LLM_MODEL` (cross-provider model names are rejected at startup, `extraction/llm_factory.py:49-63`).

## Scripts and Executables

There is no script registry; these are all the runnable things in the repo.

### Development / run

- `python main.py`: CLI batch extraction + evaluation. Hard-requires `mnt/data/dati.csv` (`extraction/cli.py:315-316` raises `FileNotFoundError`: guaranteed on a fresh clone, since the file is not tracked) and a valid `LLM_API_KEY`. Processes every `.png`/`.jpg`/`.jpeg` in `INPUT_DIR` (sorted lexically), then writes `mnt/data/poc_outputs_improved.json` and `mnt/data/poc_debug_improved.csv` and prints RAW/FILTERED accuracy plus the per-screen cost table (`extraction/cli.py:333-352`).
- `python main.py --gui`: same shim, but inserts `edge-agent/` into `sys.path` and launches the edge-agent instead (`main.py:15-20`).
- `python gui_app.py`: Tkinter desktop GUI. Runs `run_extraction_batch()` on a background thread; writes `poc_outputs_gui.json`, `poc_results_gui.csv`, and (if a ground-truth CSV was selected) `poc_debug_gui.csv` into the **current working directory** (`gui_app.py:250-273`), not `INPUT_DIR`. Remember: this entry point does not load `.env`.
- `python edge-agent/edge_agent.py [--debug]`: the PyQt6 edge-agent directly. `--debug` adds the "Debug LLM" tab (`edge-agent/edge_agent.py:51`).
- `run_edge_agent.bat [--debug]`: Windows launcher. Probes `.venv\Scripts\python.exe` and rebuilds the venv if its base interpreter has vanished; on first run creates the venv (preferring `py -3.13`, then `py -3.12`, then `python`: deliberately not bare `py -3`, which could pick a torch-less 3.14) and installs `requirements.txt`, then launches the edge-agent forwarding all arguments (`run_edge_agent.bat:19-75`).

### Setup / build

- `python -m venv .venv` + `pip install -r requirements.txt`: manual environment setup (the batch file automates exactly this). torch makes the first install slow.
- PyInstaller packaging of the Tkinter GUI (documented at `README.md:91`):

  ```bash
  pip install pyinstaller
  pyinstaller --noconfirm --onefile --windowed --name "AI_Data_Extractor" --add-data "extraction;extraction" --collect-all langchain_google_genai --collect-all langchain_openai gui_app.py
  ```

  Output lands in `dist/AI_Data_Extractor.exe`; `build/`, `dist/`, and `*.spec` are gitignored.

### Utilities

- `claude_.bat`: developer convenience wrapper for Claude Code; not part of the application.

There are no test, lint, migration, or deployment commands: none of that infrastructure exists.

## Startup and Boot Sequence

### CLI (`python main.py`)

1. **`main.py`** suppresses pydantic/langchain `UserWarning`s (`main.py:3-5`), then loads `.env` (`main.py:7`).
2. `from extraction import *`: this import is the configuration moment: `extraction/config.py` snapshots all env vars into constants right now.
3. `extraction.cli.main()` (`extraction/cli.py:314`): verifies `GROUND_TRUTH_CSV` exists → loads ground truth → collects screenshots from `INPUT_DIR` → `BatchRunner` constructs the two shared LangChain ChatModels (main + anchor) **once, before the pool** (`extraction/cli.py:182-191`): a missing/invalid API key fails here with `ValueError: API key required…` (`extraction/llm_factory.py:41-44`) → `ThreadPoolExecutor` (if `PARALLEL_ENABLED`) runs `ExtractionPipeline.extract_from_screen()` per image → outputs saved, evaluation and cost summary printed.
4. **Verify it worked:** the run ends with `Saved outputs: …` / `Saved debug report: …` lines plus the accuracy and cost tables on stdout.

### Tkinter GUI (`python gui_app.py`)

1. Module import pulls in `extraction` immediately (`gui_app.py:6-14`), **without** `load_dotenv`, so export your env vars first or rely on the in-app API-key field (prefilled from `LLM_API_KEY`, then `OPENAI_API_KEY`, `gui_app.py:24`).
2. The window opens with provider/model dropdowns fed by `PROVIDER_MODELS` (`extraction/config.py:22-33`). Extraction starts only on button press; model construction (and therefore key validation) happens inside `run_extraction_batch()` at that point.
3. **Verify:** results tree populates, summary pane shows accuracy/cost, output files appear in the working directory.

### Edge-agent (`python edge-agent/edge_agent.py`, `run_edge_agent.bat`, or `python main.py --gui`)

1. **`edge-agent/edge_agent.py`** loads the project-root `.env` (`edge-agent/edge_agent.py:9-13`), creates the `QApplication`, and applies the qt-material `dark_cyan.xml` theme (optional: skipped if `qt_material` is missing).
2. `AgentConfig` parses `edge-agent/config.ini` (`edge-agent/edge_agent.py:47-48`).
3. `MainWindow` is constructed (`edge-agent/edge_agent.py:52`) and immediately builds `LocalExtractionClient` (`edge-agent/ui/main_window.py:37`), which constructs **both** ChatModels in its `__init__` (`edge-agent/local_extraction_client.py:47-48`). This is the fail-fast point: no `LLM_API_KEY` (or legacy var) means the window never opens.
4. Tabs are added: **Cattura**, **Risultati**, **Dati Estratti**, and (only with `--debug`) **Debug LLM** (`edge-agent/ui/main_window.py:73-77`). The Qt event loop starts.
5. Extraction begins when the operator clicks "Avvia": `start_job()` issues a UUID, `BPERCaptureWorker` starts its QThread loop, and each stable, routed page flows through `ingest_frame()` → `ExtractionPipeline.extract_from_image()` synchronously in the capture thread. The page router resolves its own OpenAI key separately: `config.ini [llm] api_key` → `OPENAI_API_KEY` → `LLM_API_KEY` (`edge-agent/workers/capture/bper_capture_worker.py:122`). With no router key, routing silently returns no matches: visible only in the Debug LLM tab.
6. **Verify:** the red capture border appears on the configured monitor, the Cattura log announces detected pages, and rows appear in Risultati / Dati Estratti as `result_ready` fires.

### Service dependencies at startup

Only the LLM providers (OpenAI and/or Google Gemini over HTTPS). No database, no cache, no message broker. The torch/DINOv2 stack is optional: the ML page classifier disables itself if torch is not importable (`edge-agent/page_classifier.py:9-19`).

## Ports, URLs, and Service Endpoints

This project **opens no listening ports** and exposes no health-check or admin endpoints. All network traffic is outbound:

| Endpoint | Used by | Status |
|---|---|---|
| `https://api.openai.com/v1` (and the Gemini API when `LLM_PROVIDER=gemini`) | Extraction passes (`extraction/vlm_client.py`) and the LLM page router (`edge-agent/llm_router.py:200-209`; base URL from `edge-agent/config.ini:20`) | Active |
| `http://localhost:8081` - `POST {base_url}/jobs/{job_id}/frames` | "Generico" capture mode only (`edge-agent/workers/capture/default_capture_worker.py:62-66`; URL from `edge-agent/config.ini:10`) | Dead - no backend exists in this repo |
| `http://localhost:9000` (MinIO) | Nothing - `[minio]` config is a remnant of the removed remote backend | Dead |

To confirm the app is healthy you read its outputs, not a port: CLI prints its report to stdout, the GUIs surface results in their result tabs, and `DEBUG_MODE=1` / `DEBUG_SAVE_CROPS=1` / `--debug` are the diagnostic levers (see [Getting Started](07-getting-started.md) for a first-run walkthrough and [Architecture](04-architecture.md) for how the pieces connect). Configuration recipes for common scenarios are in the [Configuration Guide](10-configuration-guide.md).
