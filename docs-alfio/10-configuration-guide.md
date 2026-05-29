# Configuration and Usage Guide

This guide walks through configuring poc-data-extraction from a fresh clone to a working extraction run, covers the day-to-day commands you will actually type, and documents the error messages you will encounter when something breaks. The project has two independent configuration systems -- environment variables (`.env`) for the core extraction pipeline, and an INI file (`edge-agent/config.ini`) for the desktop capture agent -- and understanding which one controls what saves real debugging time.

## Configuration Walkthrough

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

The `requirements.txt` at the project root (`D:\Projects\poc-data-extraction\requirements.txt`) covers both the extraction pipeline and the edge-agent. Two heavy dependencies deserve attention:

- **torch / torchvision** -- required only for the ML page classifier in the edge-agent. If you skip them, the classifier degrades to `DISABLED` mode and the agent still runs (it falls back to the LLM router). Install takes significant disk space.
- **PyQt6 / qt-material** -- required only for the edge-agent GUI (`main.py --gui` or `edge-agent/edge_agent.py`). Not needed for CLI batch mode.

If you only need CLI batch extraction, a minimal install works:

```bash
pip install langchain-core langchain-openai langchain-google-genai pillow pandas python-dotenv
```

### Step 2: Create the .env File

```bash
cp .env.example .env
```

The template lives at `D:\Projects\poc-data-extraction\.env.example`. One value is mandatory -- everything else has working defaults.

**You must set:**

| Variable | What to put here |
|----------|-----------------|
| `LLM_API_KEY` | Your OpenAI or Google Gemini API key |

**You can leave as defaults:**

| Variable | Default | Why it is fine |
|----------|---------|---------------|
| `LLM_PROVIDER` | `openai` | Works if your key is an OpenAI key |
| `LLM_MODEL` | `gpt-4o` | Best accuracy for extraction |
| `INPUT_DIR` | `mnt/data` | Standard data directory location |
| `PARALLEL_WORKERS` | `4` (in .env.example) | Good for most machines |
| `MAX_CALLS_PER_SCREEN` | `4` | Balances accuracy vs. cost |
| `ANCHOR_CONF_MIN` | `0.95` | High bar for anchor acceptance is intentional |

**Important default discrepancy:** The code in `extraction/config.py` (line 11) defaults `PARALLEL_WORKERS` to `12` when the env var is unset. The `.env.example` template sets it to `4`. If you create `.env` from the template, you get 4 workers. If you skip creating `.env` entirely, you get 12. Set it explicitly to avoid surprises.

### Step 3: Prepare Test Data

The CLI batch mode expects screenshots and a ground truth CSV in `INPUT_DIR` (default: `mnt/data/`). This directory is gitignored (`/mnt` in `.gitignore`), so it will not be present after cloning.

```bash
mkdir -p mnt/data
```

Place your BPER banking screenshots (`.png` or `.jpg`) in `mnt/data/`. For accuracy evaluation, also provide `mnt/data/dati.csv` -- a CSV with three columns:

```
Fotogramma,Denominazione da attribuire,Valore rilevato
screen 1,NDG,31943680
screen 1,DENOMINAZIONE,"TICCHI SERENA"
screen 1,Tipo,BPI Mutui
```

The CSV loader in `extraction/evaluation.py` (function `_find_column()`, line 26) auto-detects alternative column names: `Screenshot`/`Screen`/`screen` for the screen column, `Valore`/`Value` for values, `Campo`/`Field` for keys.

### Step 4: Configure the Edge Agent (Optional)

The edge-agent has its own configuration file at `D:\Projects\poc-data-extraction\edge-agent\config.ini`. This is a standard INI file with six sections. The most important settings to review:

```ini
[agent]
router = llm          # ml | llm | hybrid
monitor_index = 1     # which monitor to capture (1-based)

[llm]
provider = openai
model = gpt-4o-mini
api_key = <your-key>  # or leave blank and rely on .env LLM_API_KEY
```

**Security note:** The committed `config.ini` contains an API key on line 23. Replace it with your own key or clear it and rely on the `.env` file instead. The edge-agent loads `.env` from the project root at startup (`edge-agent/edge_agent.py`, lines 9-12), and the `LLMPageRouter` falls back to `OPENAI_API_KEY` and `LLM_API_KEY` environment variables (`bper_capture_worker.py`, line 122).

### Configuration Load Order

Values resolve in this priority (first one wins):

1. `.env` file -- loaded by `python-dotenv` at the top of `main.py` (line 7) and `edge-agent/edge_agent.py` (line 11)
2. `extraction/config.py` -- reads `os.getenv()` at import time with hardcoded defaults
3. `edge-agent/config.ini` -- read by `AgentConfig.__init__()` in `edge-agent/config.py` (line 109)

The extraction pipeline only reads environment variables. The edge-agent reads both `.env` (for `LLM_API_KEY`) and `config.ini` (for agent-specific settings like FPS, router mode, monitor index).

## Environment Profiles

This project has no formal environment profiles (no `NODE_ENV`, no staging/production split). All configuration flows through a single `.env` file and the edge-agent's `config.ini`.

### Switching Between Providers

Toggle between OpenAI and Gemini by changing two variables in `.env`:

**OpenAI (default):**
```
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o
```

**Google Gemini:**
```
LLM_PROVIDER=gemini
LLM_API_KEY=AI...
LLM_MODEL=gemini-2.0-flash
```

The factory in `extraction/llm_factory.py` validates provider-model combinations and raises `ValueError` if they mismatch (e.g., a `gpt-` model with `gemini` provider, or vice versa).

### Debug Mode vs. Normal Mode

Enable debug output by setting two variables in `.env`:

```
DEBUG_MODE=1
DEBUG_SAVE_CROPS=1
```

`DEBUG_MODE` (read in `extraction/config.py`, line 88) enables verbose `[DEBUG]` log lines from `BatchRunner` in `extraction/cli.py`. `DEBUG_SAVE_CROPS` (line 89) writes every intermediate crop image to `{INPUT_DIR}/debug_crops/` via `save_debug_crop()` in `extraction/imaging.py` (line 37).

For the edge-agent, debug output is controlled in `config.ini`:

```ini
[debug]
show_llm_tab = true
```

This shows the LLM debug tab in the edge-agent UI, exposing raw prompt/response pairs from the page router. You can also launch with `--debug` flag: `python edge-agent/edge_agent.py --debug`.

## Configuration Recipes

### Use a cheaper model for faster iteration

In `.env`:
```
LLM_MODEL=gpt-4o-mini
```

Or for Gemini:
```
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
```

Supported models are listed in `extraction/config.py` lines 22-32 (`PROVIDER_MODELS` dict):
- OpenAI: `gpt-4o`, `gpt-4o-mini`, `o1`, `o1-mini`
- Gemini: `gemini-1.5-pro`, `gemini-1.5-flash`, `gemini-2.0-flash`, `gemini-2.0-flash-exp`, `gemini-2.0-flash-thinking-exp`, `gemini-3-flash-preview`

### Use a different model for the anchor pass

The anchor pass extracts only NDG and DENOMINAZIONE from the header strip. You can assign a faster/cheaper model to it while keeping the main extraction on a stronger model:

```
LLM_MODEL=gpt-4o
LLM_MODEL_ANCHOR=gpt-4o-mini
```

If `LLM_MODEL_ANCHOR` is unset, it defaults to whatever `LLM_MODEL` is (`extraction/config.py`, line 19).

### Point to a different screenshot directory

```
INPUT_DIR=path/to/my/screenshots
```

The ground truth CSV is expected at `{INPUT_DIR}/dati.csv` (`extraction/config.py`, line 9). Output files also land in `INPUT_DIR`:
- `poc_outputs_improved.json` -- extraction results
- `poc_debug_improved.csv` -- per-field debug report

### Disable parallel processing

```
PARALLEL_ENABLED=0
```

This forces sequential extraction, one screenshot at a time. Useful for debugging or when hitting API rate limits. Defined in `extraction/config.py`, line 12.

### Reduce VLM calls per screenshot

```
MAX_CALLS_PER_SCREEN=2
```

The pipeline always uses 2 calls minimum (1 anchor + 1 main). Retry passes consume additional calls. Setting this to `2` disables all retries. The default of `4` allows up to 2 retry areas. Defined in `extraction/config.py`, line 50.

### Enable Gemini thinking mode

For Gemini 3+ "thinking" models:

```
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash-thinking-exp
LLM_THINKING_LEVEL=low
```

Valid values: `low`, `medium`, `high`. The thinking level is only applied when the model name contains "thinking" (`extraction/llm_factory.py`, line 73). Note: `extraction/config.py` line 20 also stores a `medium` default, but that constant is never consumed -- `llm_factory.py` reads the env var directly with an empty default. If you do not set the variable in `.env`, thinking mode stays off.

### Switch the edge-agent page router

In `edge-agent/config.ini`, section `[agent]`:

```ini
# ML-only (requires torch):
router = ml

# LLM-only (requires API key, no torch needed):
router = llm

# Try LLM first, fall back to ML:
router = hybrid
```

The ML router uses DINOv2 prototype matching (`edge-agent/page_classifier.py`). The LLM router uses OpenAI Vision (`edge-agent/llm_router.py`). Hybrid tries LLM first and falls back to ML on failure.

### Change the captured monitor

In `edge-agent/config.ini`:

```ini
[agent]
monitor_index = 2
```

Uses 1-based indexing (mss convention). If the index is out of range, it falls back to monitor 1 (`bper_capture_worker.py`, lines 569-571).

### Stop processing on uncertain anchors

```
STOP_ON_ANCHOR_UNCERTAIN=1
```

When enabled, if both NDG and DENOMINAZIONE come back null from the anchor pass, the pipeline stops immediately and returns status `ANCHOR_UNCERTAIN` instead of proceeding to the main pass. This saves API costs on unreadable screenshots. Defined in `extraction/config.py`, line 51; checked in `extraction/pipeline.py`, line 112.

## Common Operations

### Run CLI batch extraction

```bash
python main.py
```

Processes all `.png`/`.jpg`/`.jpeg` files in `INPUT_DIR`, runs the multi-pass pipeline on each, evaluates against ground truth, and prints accuracy metrics and cost summary. Outputs:
- `mnt/data/poc_outputs_improved.json` -- full extraction results
- `mnt/data/poc_debug_improved.csv` -- per-field debug comparison

Expected console output includes:
```
Parallel enabled: workers=4, screens=9
Done screen 1
Done screen 2
...
OVERALL (RAW):      35/40 = 87.50%
OVERALL (FILTERED): 33/38 = 86.84%

COST SUMMARY (per screen):
  screen 1    calls= 3  tokens=12500  cost=$0.0350  status=OK
  ...
TOTAL: calls=27  tokens=112000  cost=$0.3150
```

### Launch the edge-agent GUI

```bash
python main.py --gui
```

Or directly:

```bash
cd edge-agent
python edge_agent.py
```

The `--debug` flag enables the LLM debug tab:

```bash
python edge-agent/edge_agent.py --debug
```

### Launch the Tkinter desktop GUI

```bash
python gui_app.py
```

This standalone GUI (`D:\Projects\poc-data-extraction\gui_app.py`) provides file selection, provider/model dropdown, and a results viewer. It reads `LLM_API_KEY` from the environment but also has an API key input field in the UI (line 24).

### Build a Windows executable

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name "AI_Data_Extractor" --add-data "extraction;extraction" --collect-all langchain_google_genai --collect-all langchain_openai gui_app.py
```

Output lands in `dist/AI_Data_Extractor.exe`. This packages the Tkinter GUI only, not the edge-agent.

### View debug crops

Set `DEBUG_SAVE_CROPS=1` in `.env`, then run extraction. Crop images are saved to `{INPUT_DIR}/debug_crops/` with filenames like `screen 1__CONTENT.png`, `screen 1__HEADER_IN_CONTENT.png`, `screen 1__RETRY_HEADER.png`. This helps verify that the pipeline's crop coordinates are landing on the right regions.

### Export results from the edge-agent

In the edge-agent UI:
1. **Risultati tab** -- click CSV export to save per-field results
2. **Dati tab** -- spreadsheet view with CSV and Excel export (Excel via `openpyxl`)

The `LocalExtractionClient.export_csv()` method (`edge-agent/local_extraction_client.py`, line 112) generates flat CSV with `{field}_value` and `{field}_conf` columns.

## Troubleshooting

### "API key required. Set LLM_API_KEY env var or pass api_key="

**Symptom:** `ValueError: API key required. Set LLM_API_KEY env var or pass api_key=.`

**Cause:** No API key was found. The factory in `extraction/llm_factory.py` (line 42) checks `LLM_API_KEY`, then falls back to legacy vars `OPENAI_API_KEY` / `GEMINI_API_KEY` (lines 30-38). All were empty.

**Fix:** Set `LLM_API_KEY` in your `.env` file. Verify the file is in the project root and that `python-dotenv` is installed (`pip install python-dotenv`). If using the Tkinter GUI, you can also paste the key directly into the API Key field.

### "Unknown provider" or model-provider mismatch

**Symptom:** `ValueError: Unknown provider: 'xyz'. Available: ['openai', 'gemini']`
or: `ValueError: Model 'gemini-2.0-flash' looks like a Gemini model but provider is 'openai'.`

**Cause:** `LLM_PROVIDER` does not match the model name, or is set to something other than `openai` or `gemini`. Validation is in `extraction/llm_factory.py`, lines 49-53 and 59-62.

**Fix:** Ensure `LLM_PROVIDER` and `LLM_MODEL` are consistent:
```
# OpenAI models: gpt-4o, gpt-4o-mini, o1, o1-mini
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o

# Gemini models: gemini-1.5-flash, gemini-2.0-flash, etc.
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
```

### "Ground truth CSV not found"

**Symptom:** `FileNotFoundError: Ground truth CSV not found: mnt/data/dati.csv`

**Cause:** The CLI entry point (`extraction/cli.py`, line 316) requires `dati.csv` to exist at `{INPUT_DIR}/dati.csv`. The `mnt/` directory is gitignored and not present after a fresh clone.

**Fix:** Either create the directory and provide the CSV:
```bash
mkdir -p mnt/data
# copy your dati.csv and screenshot files here
```

Or change `INPUT_DIR` in `.env` to point to wherever your data lives:
```
INPUT_DIR=path/to/my/data
```

### "Cannot find column in CSV"

**Symptom:** `ValueError: Cannot find screen column in CSV. Columns=['Col1', 'Col2', ...]`

**Cause:** The ground truth CSV does not contain any of the expected column names. The loader in `extraction/evaluation.py` (function `_find_column()`, line 26) looks for specific candidates:
- Screen column: `Screenshot`, `Fotogramma`, `Screen`, `screen`
- Value column: `Valore rilevato`, `Valore rilevato ` (with trailing space), `Valore`, `Value`
- Key column: `Denominazione da attribuire`, `Denominazione`, `Campo`, `Field`

**Fix:** Rename your CSV columns to match one of the expected names. The most common format is:
```csv
Fotogramma,Denominazione da attribuire,Valore rilevato
```

### "No images found in INPUT_DIR"

**Symptom:** Console prints `No images found in mnt/data` and exits without processing.

**Cause:** No `.png`, `.jpg`, or `.jpeg` files exist in the configured `INPUT_DIR`. The file discovery is in `extraction/cli.py`, lines 322-327.

**Fix:** Place screenshot files in the `INPUT_DIR` directory. Verify the path: `ls mnt/data/*.png`

### "No JSON object found in model response"

**Symptom:** `ValueError: No JSON object found in model response: '...'`

**Cause:** The Gemini model returned free-form text instead of JSON. This happens with the Gemini freeform path in `extraction/vlm_client.py` (line 39) when newer Gemini models (2.0+) produce responses without a valid JSON object. This is a `ValueError`, so the retry logic does not retry it -- it fails immediately (line 252-253).

**Fix:** Try a different Gemini model. `gemini-1.5-flash` and `gemini-1.5-pro` use the schema-based JSON mode which is more reliable. For 2.0+ models, the code falls back to freeform JSON parsing which is inherently less stable.

### "Pydantic validation failed" or "Structured output parsing failed"

**Symptom:** `ValueError: Pydantic validation failed for screen 1/CONTENT_MAIN: ...` or `ValueError: Structured output parsing failed for screen 1/CONTENT_MAIN: ...`

**Cause:** The LLM returned JSON that does not match the expected Pydantic schema. OpenAI structured output parsing failure is caught at `extraction/vlm_client.py`, lines 199-202. Gemini freeform validation failure is at lines 95-98.

**Fix:** These errors are non-retriable by design. They typically indicate the model struggled with the image. Options: try a more capable model (`gpt-4o` instead of `gpt-4o-mini`), or check that the screenshot is a valid BPER banking screen.

### "mss non disponibile"

**Symptom:** Edge-agent stops with `RuntimeError: mss non disponibile: ...`

**Cause:** The `mss` screenshot library failed to initialize. This error is raised in `edge-agent/workers/capture/bper_capture_worker.py`, line 562. Common on environments without a display server.

**Fix:** Ensure you are running on a machine with a display. On Windows, this should work out of the box. On Linux, ensure X11 or Wayland is running. Install `mss` if missing: `pip install mss>=9.0.0`.

### "Cattura fallita N volte consecutive"

**Symptom:** Edge-agent auto-stops with `RuntimeError: Cattura fallita 5 volte consecutive. Ultimo errore: ...`

**Cause:** Five consecutive screenshot captures failed. The counter is in `bper_capture_worker.py`, lines 589-598. This usually means the configured monitor index does not exist.

**Fix:** Check `monitor_index` in `edge-agent/config.ini`. Set it to `1` for the primary monitor. If you have multiple monitors, use `2`, `3`, etc. The index is 1-based per `mss` convention.

### ML classifier disabled / torch import failure

**Symptom:** Edge-agent log shows `[BPER-ML] import_error: ...` or `[BPER] Router disabilitato.`

**Cause:** `torch` or `torchvision` failed to import. The `page_classifier.py` is designed to degrade gracefully -- it sets itself to `DISABLED` mode and `classify()` returns `(None, 0.0)`. See `edge-agent/page_classifier.py`, lines 137-165.

**Fix:** If you need ML page classification, install PyTorch: `pip install torch torchvision`. If you do not need it, switch to the LLM router in `config.ini`:
```ini
[agent]
router = llm
```

### "LLM client non inizializzato (manca API key o import OpenAI fallito)"

**Symptom:** Edge-agent LLM debug tab shows this error. Page routing returns no matches.

**Cause:** The `LLMPageRouter` in `edge-agent/llm_router.py` (line 148) could not create an OpenAI client. Either the `openai` package is not installed, or no API key was provided.

**Fix:** Ensure `openai` is installed (`pip install openai>=1.51.0`). Set the API key in either `edge-agent/config.ini` under `[llm] api_key = ...` or in `.env` as `LLM_API_KEY=...` or `OPENAI_API_KEY=...`.

### Rate limits and transient API errors

**Symptom:** Extraction is slow with intermittent failures, then eventually succeeds or fails after retries.

**Cause:** The retry logic in `extraction/vlm_client.py` (function `call_vlm_with_retry`, lines 240-258) handles transient errors with exponential backoff: `min(8.0, 2^i * 0.8) + 0.05*i` seconds, up to 3 retries. `ValueError` exceptions (parsing failures) are not retried.

**Fix:** Reduce `PARALLEL_WORKERS` to lower concurrent API calls. If using a free-tier API key, set `PARALLEL_WORKERS=1` and `PARALLEL_ENABLED=0`.

### Deprecation warning: "OPENAI_API_KEY is deprecated. Use LLM_API_KEY instead."

**Symptom:** `DeprecationWarning: OPENAI_API_KEY is deprecated. Use LLM_API_KEY instead.`

**Cause:** You have `OPENAI_API_KEY` or `GEMINI_API_KEY` set in your environment but not `LLM_API_KEY`. The factory in `extraction/llm_factory.py` (lines 36-40) still accepts the legacy names but warns about them.

**Fix:** Rename the variable in your `.env`:
```
# Before:
OPENAI_API_KEY=sk-...

# After:
LLM_API_KEY=sk-...
```

## Quick Reference

| Task | Command | Notes |
|------|---------|-------|
| Install dependencies | `pip install -r requirements.txt` | Full install including edge-agent |
| Create config | `cp .env.example .env` | Then set `LLM_API_KEY` |
| Run CLI batch extraction | `python main.py` | Needs screenshots in `INPUT_DIR` + `dati.csv` |
| Launch edge-agent | `python main.py --gui` | PyQt6 live capture + extraction |
| Launch edge-agent (direct) | `python edge-agent/edge_agent.py` | Same as above, skips main.py shim |
| Launch edge-agent (debug) | `python edge-agent/edge_agent.py --debug` | Shows LLM debug tab |
| Launch Tkinter GUI | `python gui_app.py` | Standalone desktop app |
| Switch to Gemini | Set `LLM_PROVIDER=gemini` and `LLM_MODEL=gemini-2.0-flash` in `.env` | Also change `LLM_API_KEY` to Gemini key |
| Enable debug crops | Set `DEBUG_SAVE_CROPS=1` in `.env` | Crops saved to `{INPUT_DIR}/debug_crops/` |
| Disable parallelism | Set `PARALLEL_ENABLED=0` in `.env` | Sequential processing |
| Build Windows .exe | `pyinstaller --noconfirm --onefile --windowed --name "AI_Data_Extractor" --add-data "extraction;extraction" --collect-all langchain_google_genai --collect-all langchain_openai gui_app.py` | Packages Tkinter GUI only |
| Change edge-agent router | Set `router = ml` or `llm` or `hybrid` in `edge-agent/config.ini` | ML requires torch |
| Change capture monitor | Set `monitor_index = N` in `edge-agent/config.ini` | 1-based index |

---

Cross-references: [Project Anatomy](09-project-anatomy.md) for the full catalog of environment variables, config files, and their locations. [Getting Started](07-getting-started.md) for initial setup and first run. [Tech Stack](03-tech-stack.md) for dependency details and version constraints.
