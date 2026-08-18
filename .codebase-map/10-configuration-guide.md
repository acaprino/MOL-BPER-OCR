# Configuration and Usage Guide

This project is configured almost entirely through environment variables, with one exception: the PyQt6 edge-agent reads its own settings from `edge-agent/config.ini`. There is no database to provision and no server to start. Day-to-day work is running one of three entry points (`main.py` CLI, `gui_app.py` Tkinter desktop, or the edge-agent) against a directory of screenshots and a ground-truth CSV. This guide walks through building a working configuration from scratch, the OpenAI-vs-Gemini split that drives most of the setup, copy-pasteable recipes for the knobs you will actually turn, the commands you run repeatedly (Windows/PowerShell-first: the dev machine is Windows 11 with Python 3.13), and the errors you will hit when something is wrong, each quoted from the actual source.

For the complete catalog of every environment variable and config key, see [Project Anatomy](09-project-anatomy.md). For first-time setup, see [Getting Started](07-getting-started.md). For dependency and provider details, see [Tech Stack](03-tech-stack.md).

## Configuration Walkthrough

The pipeline reads all of its configuration at import time. **`extraction/config.py`** runs its `os.getenv()` calls at module load, so values are frozen the moment `from extraction import *` executes in `main.py:8`. Setting an environment variable after the process starts has no effect. This matters for the order below.

**Step 1: Create the virtual environment.** On Windows, `run_edge_agent.bat` does this for you (it prefers Python 3.13, then 3.12, and installs `requirements.txt` on first run, `run_edge_agent.bat:50-54,67-69`). Manually:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

The torch/torchvision download is the slow part; it is only needed by the edge-agent's ML page router.

**Step 2: Create your `.env`.** Copy the template:

```powershell
Copy-Item .env.example .env
```

`main.py:7` calls `load_dotenv()` before importing the `extraction` package, so anything in `.env` is in the environment before `extraction/config.py` reads it. The edge-agent loads the same root `.env` explicitly (`edge-agent/edge_agent.py:9-13`). `.env` is gitignored (`.gitignore` covers `.env*`). Keep it that way.

**Step 3: Set the one required value.** `LLM_API_KEY` is the only variable you must provide; everything else has a working default. Without it, `create_chat_model()` raises at `extraction/llm_factory.py:41-44`:

```
API key required. Set LLM_API_KEY env var or pass api_key=.
```

Replace the `.env.example:5` placeholder (`LLM_API_KEY=your-api-key-here`) with a real key. The Tkinter GUI is the exception: `gui_app.py:24` shows an API-key field pre-filled from `LLM_API_KEY` (falling back to `OPENAI_API_KEY`), so you can run it without a `.env` and paste the key in.

**Step 4: Pick a provider and model (optional).** Defaults in `extraction/config.py:17-18` are `LLM_PROVIDER=openai` and `LLM_MODEL=gpt-4o`. With an OpenAI key you change nothing. To switch to Gemini, see Environment Profiles; provider and model must move together or the factory rejects them.

**Step 5: Put the data where the CLI looks for it.** The CLI reads screenshots and the ground-truth CSV from `INPUT_DIR`, default `mnt/data` (`extraction/config.py:8`); the ground-truth path is derived from it as `mnt/data/dati.csv` (`extraction/config.py:9`). **`dati.csv` is not in the repository** (`/mnt` is gitignored; only the 9 `screen *.png` files were force-added), and the CLI hard-fails without it (`extraction/cli.py:315-316`); see Troubleshooting. Obtain the file separately and place it in `mnt/data/` before running `python main.py`. The Tkinter GUI and the edge-agent do not need it.

**Step 6: Edge-agent in `llm` mode only: supply the router key.** Needed with the shipped configuration, which uses `router = llm`. In that case `[llm] api_key` in the shipped `config.ini` is deliberately **blank** and the key is picked up from the environment according to the provider; see the recipe below.

### Order dependencies that bite

- `INPUT_DIR` must be set **before** the process starts: `GROUND_TRUTH_CSV` and `DEBUG_CROP_DIR` are computed from it at import (`extraction/config.py:9,94`). Exporting it after launch does nothing.
- `LLM_PROVIDER` and `LLM_MODEL` must agree (OpenAI provider needs an OpenAI model and vice versa). The factory enforces this; see Troubleshooting.
- The edge-agent builds both extraction ChatModels at window construction (`edge-agent/ui/main_window.py:37` → `edge-agent/local_extraction_client.py:47-48`), so a missing `LLM_API_KEY` crashes the edge-agent at startup, not at first capture.

## Environment Profiles

There are no dev/staging/prod profiles: no per-environment config files and no profile selector. Configuration is one flat set of environment variables plus one INI file. What actually varies between setups are three orthogonal switches: **which LLM provider** runs the extraction, **which page-detection mode** the edge-agent uses, and **whether debug output is on**.

### OpenAI vs Gemini (the main split)

The provider is selected by `LLM_PROVIDER` and resolved in `create_chat_model()` (`extraction/llm_factory.py:46-77`). The two profiles differ in three variables.

**OpenAI profile (default).** Nothing beyond the key:

```bash
LLM_PROVIDER=openai
LLM_API_KEY=sk-your-openai-key
LLM_MODEL=gpt-4o
```

Valid OpenAI models per `PROVIDER_MODELS` (`extraction/config.py:22-23`): `gpt-4o`, `gpt-4o-mini`, `o1`, `o1-mini`.

**Gemini profile.** Switch provider, key, and model together:

```bash
LLM_PROVIDER=gemini
LLM_API_KEY=your-gemini-key
LLM_MODEL=gemini-1.5-flash
```

Valid Gemini models (`extraction/config.py:24-32`): `gemini-1.5-pro`, `gemini-1.5-flash`, `gemini-2.0-flash`, `gemini-2.0-flash-exp`, `gemini-2.0-flash-thinking-exp`, `gemini-3-flash-preview`, `gemini-3.1-flash-lite-preview`. The Gemini branch sets all four harm-category `safety_settings` to `BLOCK_NONE` (`extraction/llm_factory.py:64-71`). Structured output also takes a different path per model generation: `gemini-1.5*` uses json_mode with a response schema, while 2.0+/3.x fall back to free-form JSON plus manual Pydantic validation (`extraction/vlm_client.py:15-18,134-183`).

Two extra knobs:

- `LLM_MODEL_ANCHOR` (`extraction/config.py:19`) lets the cheap anchor pass use a different model from the main pass; defaults to `LLM_MODEL`.
- `LLM_THINKING_LEVEL` (`extraction/config.py:20`): `low`/`medium`/`high`; applied only when the model name contains `thinking` (`extraction/llm_factory.py:72-74`). A no-op for every other model.

> **External service:** both profiles call a paid third-party API (OpenAI or Google) over the network. You need a valid, funded key for whichever provider you choose. Nothing in this project mocks the LLM.

### Edge-agent page-detection mode

The edge-agent picks how it recognizes which BPER screen is on display via the `router` key in `[agent]` of **`edge-agent/config.ini`**, read into `AgentConfig.router_mode` (`edge-agent/config.py:160`):

- `ml`: DINOv2 prototype matching, local and free per frame (needs `torch`/`torchvision`). Code default (`edge-agent/config.py:25`).
- `llm`: OpenAI Vision (`gpt-4o-mini`) classifies each candidate frame. The value shipped in `edge-agent/config.ini:4`.
- `hybrid`: LLM first, ML fallback.

The `ml`/`hybrid` modes degrade gracefully: if torch fails to import, the classifier enters DISABLED mode and returns no classification instead of crashing (`edge-agent/page_classifier.py:50,158`).

### Debug profile

Three independent toggles, none tied to an "environment":

- `DEBUG_MODE=1`: prints `[DEBUG]` batch/pipeline logs (`extraction/cli.py:31-34`; default `0` at `extraction/config.py:92`). Not listed in `.env.example`.
- `DEBUG_SAVE_CROPS=1`: writes intermediate crop images to `mnt/data/debug_crops` (`extraction/config.py:93-94`).
- Edge-agent `--debug` flag: adds the "Debug LLM" tab showing raw router prompt/response (`edge-agent/edge_agent.py:51`). The `[debug] show_llm_tab=true` key in `config.ini:32` additionally gates the debug signal emission; both are needed to see router traffic.

## Configuration Recipes

Each recipe lists what to change, where, and what you should see. Only scenarios the code supports are included.

### Use Google Gemini instead of OpenAI

In `.env`:

```bash
LLM_PROVIDER=gemini
LLM_API_KEY=your-gemini-key
LLM_MODEL=gemini-1.5-flash
```

Result: `create_chat_model()` builds a `ChatGoogleGenerativeAI` (`extraction/llm_factory.py:56-75`). Requires `langchain-google-genai`, which is imported lazily only on this branch.

### Run a cheaper anchor pass than the main pass

In `.env`:

```bash
LLM_MODEL=gpt-4o
LLM_MODEL_ANCHOR=gpt-4o-mini
```

Result: the header anchor extraction uses the cheap model while the full-content main pass uses `gpt-4o`. Both names flow into `BatchRunner` (`extraction/cli.py:176-177`), which creates two separate shared ChatModel instances (`extraction/cli.py:181-191`).

### Point the pipeline at a different data folder

In `.env`:

```bash
INPUT_DIR=C:\data\bper_screens
```

Result: the CLI lists `*.png`/`*.jpg`/`*.jpeg` from that directory (`extraction/cli.py:322-327`), expects `dati.csv` inside it (`extraction/config.py:9`), and writes `poc_outputs_improved.json` / `poc_debug_improved.csv` there (`extraction/cli.py:337,345`). Set it before launching.

### Edit a prompt, or point at a different catalog

Prompts no longer live in code: they sit in `prompts/`, one JSON file per prompt, read and validated once at startup by `prompt_store.py`. To change what the model is asked, edit the JSON and restart; no Python change, no rebuild. In the portable package the copy next to the exe wins over the one inside the bundle.

To work against a separate catalog (prompt A/B, local experiments), in `.env`:

```
PROMPTS_DIR=C:\work\alternative_prompts
```

Result: that directory becomes the **only** candidate (`prompt_store.py:222`), with no fallback to the repo or bundled catalog: if it is incomplete or malformed, startup fails on purpose. The directory actually loaded is printed as `[PROMPTS] catalog loaded from ...` by the CLI and by `LocalExtractionClient`.

Two constraints when editing a JSON: braces are meaningful only in the prompts the code formats (`extraction_json_schema_instruction`, `extraction_anchor_hints`, `page_router_system`, `page_router_user`) and must be doubled (`{{`) when you want them literal; adding a new `{placeholder}` also means adding it to `CATALOG` in `prompt_store.py`.

### Enable debug logging and save crop images

In `.env`:

```bash
DEBUG_MODE=1
DEBUG_SAVE_CROPS=1
```

Result: console shows `[DEBUG]` lines for batch and per-screen progress, and every intermediate crop lands in `INPUT_DIR/debug_crops`. On completion the CLI prints `Saved debug crops to: ...` (`extraction/cli.py:351-352`).

### Tune parallelism

In `.env`:

```bash
PARALLEL_WORKERS=8
PARALLEL_ENABLED=1
```

Result: the batch runner uses an 8-thread `ThreadPoolExecutor` when there is more than one screen (`extraction/cli.py:229-233`). Defaults are `4` and `1` (`extraction/config.py:11-12`). Set `PARALLEL_ENABLED=0` to force sequential processing, useful when reading per-screen output or isolating a failure.

### Make anchor uncertainty stop a screen early

In `.env`:

```bash
STOP_ON_ANCHOR_UNCERTAIN=1
ANCHOR_CONF_MIN=0.95
```

Result: when the anchor pass cannot read NDG and DENOMINAZIONE, the pipeline returns early with `_status="ANCHOR_UNCERTAIN"` instead of spending main and retry calls (`extraction/pipeline.py:112-120`). Toggle at `extraction/config.py:55`, threshold at `:56`. Note: the early exit fires only when the model itself returns both anchors as null; `ANCHOR_CONF_MIN` does not currently null low-confidence values (the gate is ineffective; see [Workflows](05-workflows.md#multi-pass-extraction-pipeline)), so changing the threshold does not affect this behavior.

### Cap the cost per screen

In `.env`:

```bash
MAX_CALLS_PER_SCREEN=5
```

Result: limits total VLM calls per screenshot. One anchor and one main call are always spent; the retry pass gets `MAX_CALLS_PER_SCREEN - 2` retries, one per weak area (`extraction/pipeline.py:261`).

The default is **derived**, not written: `2 + len(AREA_TO_FIELDS)` = `5` (`extraction/config.py:102-103`). Lowering it does not trim cost evenly: it cuts the areas at the **tail** of `AREA_TO_FIELDS` declaration order, which is HEADER, BODY, FOOTER. At `4` only two areas can be retried and `FOOTER` never is; since `FOOTER` owns `note_della_richiesta`, a notes page loses exactly the field it is captured for. Rationale in [ADR 0004](../docs/adr/0004-budget-retry-derivato-dalle-aree.md).

### Switch the edge-agent to ML page detection

In `edge-agent/config.ini`, `[agent]` section:

```ini
router = ml
```

Result: DINOv2 prototype matching replaces the per-frame VLM call: no router API key or cost. This is the setting in force, both as the code default and in the shipped `config.ini` ([ADR 0005](../docs/adr/0005-router-ml-invece-di-router-llm.md)). Requires `torch`/`torchvision`; if unavailable the classifier reports DISABLED and never matches.

Matching runs on the application-area ROI `DEFAULT_CROP_ROI = (0.0, 0.20, 1.0, 0.98)` (`edge-agent/page_classifier.py:44`), squashed to 224x224, with a **centered** cosine and threshold `0.35` (`:51`). Three values not to touch lightly: they are the outcome of a measurement, and the previous configuration recognized 1 page out of 9 in the field ([ADR 0002](../docs/adr/0002-riconoscimento-pagina-roi-e-coseno-centrato.md)). Change any of them and the prototype cache invalidates itself, because `embedding_geometry()` is part of its key ([ADR 0003](../docs/adr/0003-chiave-cache-prototipi-con-geometria.md)): the next start rebuilds the 9 prototypes.

### Configure which monitor the edge-agent captures

In `edge-agent/config.ini`, `[agent]` section:

```ini
monitor_index = 2
```

Result: `mss` grabs monitor 2 (1-based). Read at `edge-agent/config.py:163-167` (values below 1 fall back to the default); out-of-range indices fall back to monitor 1 in the capture loop (`edge-agent/workers/capture/bper_capture_worker.py:554,569`). A red border overlay marks the captured monitor when `show_capture_border = true` (`config.ini:6`).

### Supply the edge-agent's router API key

Only needed with `router = llm` or `hybrid`. Resolution happens in `AgentConfig.resolve_llm_settings()` (`edge-agent/config.py`) and is **provider-aware**: explicit `config.ini [llm]` values are authoritative, provider defaults fill only blank entries.

Key precedence:

| provider | order |
|---|---|
| any | `config.ini [llm] api_key` when non-blank |
| `gemini` | then `GEMINI_API_KEY` → `GOOGLE_API_KEY` → `LLM_API_KEY` |
| `openai` | then `OPENAI_API_KEY` → `LLM_API_KEY` |

The shipped `config.ini` uses `provider = gemini`, `model = gemini-3.6-flash` and Google's OpenAI-compatible endpoint, with a **blank** `api_key`: the key comes from the environment. Leave it blank. The INI is tracked in git, so any key pasted there is one commit away from leaking, and `build_exe.bat` refuses to package a `config.ini` with a non-blank `api_key`.

> **Security note:** an OpenAI key was previously committed in `edge-agent/config.ini` and has been scrubbed from git history; the line now ships blank. `AgentConfig` additionally treats any value starting with `REDACTED` as empty: a leftover placeholder once shadowed the env keys and silently broke the router. Rotation of the exposed key is still to be confirmed. Never commit a real key to this file.

## Common Operations

There is no database, no migrations, no cache, and no long-running server; several "standard" operations simply do not apply. The commands below are verified against `main.py`, `gui_app.py`, `edge-agent/edge_agent.py`, `run_edge_agent.bat`, and `README.md`. Run them from the project root with the venv active (`.venv\Scripts\Activate.ps1`).

### Run the CLI batch extraction

```powershell
python main.py
```

What it does (`extraction/cli.py:314-352`): verifies `mnt/data/dati.csv` exists, lists every image in `INPUT_DIR`, runs the multi-pass extraction (parallel when more than one image), evaluates against ground truth, and writes results. Expected output, roughly in order:

- `Parallel enabled: workers=4, screens=9` (`extraction/cli.py:230-232`)
- `Done screen 1` … per completed screen (`extraction/cli.py:245`)
- RAW and FILTERED accuracy tables from `evaluator.eval()` (`extraction/cli.py:343`)
- A per-screen token/cost summary from `print_cost_summary()` (`extraction/cli.py:347`)
- `Saved outputs: mnt/data\poc_outputs_improved.json` and `Saved debug report: mnt/data\poc_debug_improved.csv` (`extraction/cli.py:349-350`)

### Launch the Tkinter desktop GUI

```powershell
python gui_app.py
```

Opens a native window with an API-key field, provider/model dropdowns, and file/CSV pickers. The ground-truth CSV is optional here (`gui_app.py:263`), so this is the way to extract ad-hoc screenshots without `dati.csv`. Outputs are written to the **current working directory**: `poc_outputs_gui.json`, `poc_results_gui.csv`, and (if a GT CSV was selected) `poc_debug_gui.csv` (`gui_app.py:250-256,273-274`).

### Launch the edge-agent (live capture)

```powershell
.\run_edge_agent.bat            # recommended on Windows: self-heals/creates .venv, then launches
# equivalents once a venv exists:
python edge-agent/edge_agent.py
python main.py --gui
```

`run_edge_agent.bat` probes the existing `.venv`, rebuilds it if its base interpreter is gone (`run_edge_agent.bat:23-29`), and forwards any arguments. Add `--debug` for the Debug LLM tab:

```powershell
.\run_edge_agent.bat --debug
```

In the app: pick the BPER mode in the Cattura tab, press "Avvia", and navigate the BPER application on the captured monitor. Detected pages are extracted locally and appear in the Risultati and Dati Estratti tabs; "Acquisisci ora" force-captures a manually selected page. Export CSV from the UI (`LocalExtractionClient.export_csv()`).

### Build a Windows executable (Tkinter app)

```powershell
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name "AI_Data_Extractor" --add-data "extraction;extraction" --collect-all langchain_google_genai --collect-all langchain_openai gui_app.py
```

Produces `dist/AI_Data_Extractor.exe` (`README.md:88-100`).

### Check results and logs

There is no log file. The CLI prints to stdout; the edge-agent logs into its Cattura tab's log pane. After a CLI run, inspect:

- `mnt/data/poc_outputs_improved.json`: full per-screen extraction results, including `_meta_agg` (calls, tokens, `estimated_cost_usd`) and `_field_sources`.
- `mnt/data/poc_debug_improved.csv`: per-(screen, field) classification; semicolon-separated, `utf-8-sig` (opens cleanly in Excel).

Operations that **do not exist** here: database migrations, seeding, automated tests (none: validation is the manual accuracy/cost comparison described in `CLAUDE.md`), cache clearing, server start/stop.

## Troubleshooting

Every symptom below is grounded in a real error string or behavior in the codebase.

### Ground-truth CSV not found

**Symptom:**

```
FileNotFoundError: Ground truth CSV not found: mnt/data\dati.csv
```

**Cause:** `python main.py` checks for `dati.csv` in `INPUT_DIR` before anything else (`extraction/cli.py:315-316`). The file is absent from the repository (`/mnt` is gitignored; only the PNGs are tracked), so this failure is guaranteed on a fresh clone.

**Fix:** obtain `dati.csv` and place it in `mnt/data/` (format in `README.md:221-241`: columns `Fotogramma`, `Denominazione da attribuire`, `Valore rilevato`). To extract without ground truth, use `python gui_app.py` instead: the CSV is optional there (`gui_app.py:263`). Where the canonical `dati.csv` lives is an open question; see [Open Questions](08-open-questions.md).

### Missing or invalid API key

**Symptom (CLI/Tkinter/edge-agent startup):**

```
ValueError: API key required. Set LLM_API_KEY env var or pass api_key=.
```

**Cause:** neither `LLM_API_KEY` nor a legacy `OPENAI_API_KEY`/`GEMINI_API_KEY` is set (`extraction/llm_factory.py:30-44`). Legacy variables work but emit a `DeprecationWarning`. In the edge-agent this surfaces as a startup crash because `LocalExtractionClient` builds both ChatModels in the `MainWindow` constructor (`edge-agent/ui/main_window.py:37`, `edge-agent/local_extraction_client.py:47-48`).

**Fix:** set `LLM_API_KEY` in the root `.env`, or paste the key into the Tkinter GUI's field (the GUI blocks with the dialog `Inserisci la API Key!` if left empty, `gui_app.py:214-215`).

### Provider / model mismatch

**Symptom:** one of (`extraction/llm_factory.py:49-53,59-63,77`):

```
ValueError: Model 'gemini-1.5-flash' looks like a Gemini model but provider is 'openai'. Set LLM_PROVIDER=gemini or choose an OpenAI model.
ValueError: Model 'gpt-4o' looks like an OpenAI model but provider is 'gemini'. Set LLM_MODEL to a Gemini model (e.g. 'gemini-1.5-flash').
ValueError: Unknown provider: 'azure'. Available: ['openai', 'gemini']
```

**Cause:** `LLM_PROVIDER` and `LLM_MODEL` disagree, or the provider is not `openai`/`gemini`.

**Fix:** change them together, picking from `PROVIDER_MODELS` (`extraction/config.py:22-33`).

### Prompt catalog fails to load

**Symptom:** at startup, before any model call (`prompt_store.py`):

```
prompt_store.PromptStoreError: no usable prompt catalog (set PROMPTS_DIR to point at a valid one):
  cannot read ...\prompts\extraction_main.json: Expecting ',' delimiter: line 8 column 5
prompt_store.PromptStoreError: prompt 'page_router_system': unknown placeholder(s) ['"page_type"']; ...
prompt_store.PromptStoreError: ... is missing prompt(s): extraction_anchor
```

**Cause:** a catalog JSON is malformed, missing, or contains an unexpected brace in a prompt the code formats. The failure is deliberate and immediate: a corrupt prompt would not stop the pipeline, it would make it emit wrong fields that look right.

**Fix:** correct the file named in the message (double literal braces, `{{`); declare any new `{placeholder}` in `CATALOG` inside `prompt_store.py`. From source, `git checkout prompts/` restores the catalog. In the portable package, delete the `prompts/` folder next to the exe: the loader uses the bundled copy and bootstrap re-seeds it on the next start.

### Model response could not be parsed

**Symptom:** one of (`extraction/vlm_client.py:39,44,95-98,199-203`):

```
ValueError: No JSON object found in model response: ...
ValueError: JSON decode error in model response: ...
ValueError: Pydantic validation failed for screen 1/CONTENT_MAIN: ...
ValueError: Structured output parsing failed for screen 1/CONTENT_MAIN: ...
```

**Cause:** the VLM returned output that does not match the Pydantic schema. These are deliberately **not retried**: `call_vlm_with_retry()` re-raises `ValueError` immediately (`extraction/vlm_client.py:252-253`). Transient API failures (rate limits, timeouts) are different: those retry up to 3 times with capped exponential backoff (`extraction/vlm_client.py:254-257`).

**Fix:** usually the chosen model is too weak for structured vision extraction. Switch to a stronger one (`gpt-4o`, `gemini-1.5-pro`). Note a retry-pass failure alone is non-fatal: the pipeline keeps main-pass results and prints `Warning: retry {AREA} for {screen} failed (keeping main-pass results)` (`extraction/pipeline.py:291`).

### CSV column not recognized

**Symptom:**

```
ValueError: Cannot find Screenshot column in CSV. Columns=[...]
```

**Cause:** `load_ground_truth()` could not find a required column under its known aliases (`extraction/evaluation.py:31`). Recognized: `Fotogramma`/`Screenshot`/`Screen`, `Denominazione da attribuire`/`Campo`/`Field`, `Valore rilevato`/`Valore`/`Value`.

**Fix:** rename the CSV headers to one of the recognized names.

### Edge-agent: screenshot capture fails

**Symptom:** in the Cattura log, one of (`edge-agent/workers/capture/bper_capture_worker.py:562,594-596`):

```
mss non disponibile: ...
Cattura fallita 5 volte consecutive. Ultimo errore: ...
```

**Cause:** the `mss` library failed to initialize, or 5 consecutive capture errors triggered the auto-stop (`_MAX_CONSECUTIVE_CAPTURE_ERRORS = 5`, `bper_capture_worker.py:98`), often a bad `monitor_index`.

**Fix:** confirm `mss` is installed (`pip install -r requirements.txt`); check `monitor_index` in `edge-agent/config.ini:5` (1-based; out-of-range indices fall back to monitor 1).

### Edge-agent: pages are never recognized (LLM router)

**Symptom:** capture runs, the border overlay shows, but no page is ever detected and no extraction fires. With `--debug`, the Debug LLM tab shows (`edge-agent/llm_router.py:148`):

```
LLM client non inizializzato (manca API key o import OpenAI fallito)
```

**Cause:** the router has no usable key for the configured provider. The router is resilient by design: it returns "no match" instead of raising, so the failure is silent in the normal UI.

**Fix:** leave the `api_key` line in `config.ini` blank and set the key in the root `.env` under the name the provider expects: with `provider = gemini` any of `GEMINI_API_KEY`, `GOOGLE_API_KEY` or `LLM_API_KEY`; with `provider = openai`, `OPENAI_API_KEY` or `LLM_API_KEY`. The env fallback fires only when the INI value is blank, and a value starting with `REDACTED` counts as blank. The startup log line `[BPER-LLM] Router LLM inizializzato (provider=..., model=..., pages=..., api_key=yes|no)` tells you whether a key was found, but not whether it is valid.

Before chasing the key, check you actually need the LLM router: the shipped configuration is `router = llm`, so the key really is needed.

### Edge-agent: ML page detection silently does nothing

**Symptom:** with `router = ml` or `hybrid`, pages are never recognized; the log shows `[BPER-ML] import_error: ...` (`bper_capture_worker.py:200-201`).

**Cause:** `torch`/`torchvision` failed to import, so `BPERPagePrototypeClassifier` runs in DISABLED mode and returns no classification (`edge-agent/page_classifier.py:50,158`). A related error, `FileNotFoundError: templates_dir non trovato: ...` (`edge-agent/page_classifier.py:143`), means `edge-agent/assets/templates/bper/` is missing.

**Fix:** install torch/torchvision (Python 3.13 or 3.12; 3.14 has no wheels, which is why the launcher avoids it, `run_edge_agent.bat:47-52`), or switch `router = llm`.

### Edge-agent: the same wrong page is recognized over and over

**Symptom:** the router recognizes a page on every frame, with a plausible score but always the same name, whatever is on screen. After the first capture the log loops:

```
[Router] Riconosciuta: «Note da Richiesta» (score=0.848)
ℹ️ «Note da Richiesta» già acquisita → apri nel sistema BPER: «Risultato ricerca»
```

and the screen it asks for is the one the operator already has open. The session stalls with one page out of nine acquired, and the exported CSV holds one page's fields under another page's name.

**Cause:** framing mismatch between the prototypes and the frame. The prototypes are *window* screenshots; if the classifier receives a whole monitor, the relative ROIs land on different content and the choice among the 9 pages becomes arbitrary. The defect is self-reinforcing: the mislabelled page enters `captured_page_types`, and from then on every frame hits the "already captured" early return.

**How to confirm:** compare the extracted values against the reference screenshots in `mnt/data`. If they match a **different** page from the one in the log, extraction is working and the problem is routing.

**Fix:** check that framing normalization is actually engaging. `_grab_raw()` brings the frame back to the application window (`edge-agent/frame_normalize.py`), first via the window title using `window_title_contains` in `config.ini`, then inferred from the desktop background. If the window title does not contain the configured substring **and** the desktop around the window is not uniform (other windows visible at the corners), both strategies give up and the frame passes through whole-monitor: align `window_title_contains` with the real window title. Full context in [ADR 0001](../docs/adr/0001-normalizzazione-inquadratura-frame.md).

### Launcher: no suitable Python / broken venv

**Symptom:** `run_edge_agent.bat` prints one of:

```
[edge-agent] ERROR: no suitable Python found (need 3.12 or 3.13).
[edge-agent] ERROR: dependency installation failed.
```

**Cause:** no `py -3.13`/`py -3.12`/`python` on PATH (`run_edge_agent.bat:50-58`), or `pip install -r requirements.txt` failed inside the fresh venv (`run_edge_agent.bat:69-74`).

**Fix:** install Python 3.13 from python.org, then delete `.venv` and rerun the launcher. A venv whose base interpreter was moved/uninstalled is detected and rebuilt automatically (`run_edge_agent.bat:23-29`).

### Per-screen extraction error in a batch

**Symptom:** `ERROR extracting screen 3: <message>` in the CLI output, or `Warning: File not found <path>` at batch start.

**Cause:** a single screenshot raised during extraction; the parallel runner catches it per-screen and continues (`extraction/cli.py:246-251`). The file-not-found warning means a listed path does not exist (`extraction/cli.py:215-217`).

**Fix:** read the underlying message (corrupt image, exhausted API retries). The batch completes and reports on the screens that succeeded. In the edge-agent the same situation yields a stored result with `_status: "ERROR"` (`edge-agent/local_extraction_client.py:87-92`).

### Port already in use

Cannot happen from this project: it opens **no** ports. The `http://localhost:8081` (`edge-agent/config.ini:10`) and MinIO `:9000` (`config.ini:13`) entries belong to the legacy remote path that the BPER-local flow never touches. Any port conflict is another process.

### Missing dependencies / version mismatches

`requirements.txt` uses loose bounds and there is no lockfile or `pyproject.toml`. If an import fails, reinstall into the venv. Watch for the lazy imports: `langchain-google-genai` only loads when `LLM_PROVIDER=gemini` (`extraction/llm_factory.py:57`), so a missing Gemini package surfaces only when you switch providers; `qt-material` is optional and its absence just drops the theme (`edge-agent/edge_agent.py:37-44`).

## Quick Reference

| Task | Command | Notes |
|---|---|---|
| Bootstrap on Windows | `.\run_edge_agent.bat` | Creates/heals `.venv`, installs deps, starts edge-agent |
| Install deps manually | `pip install -r requirements.txt` | torch only needed for `ml`/`hybrid` router |
| Create config | `Copy-Item .env.example .env` | Then set `LLM_API_KEY` |
| Run CLI batch | `python main.py` | Needs `mnt/data/dati.csv`; writes JSON + debug CSV |
| Run Tkinter GUI | `python gui_app.py` | GT CSV optional; key can be pasted in-app |
| Run edge-agent | `python edge-agent/edge_agent.py` | Same as `python main.py --gui` |
| Edge-agent + debug tab | `.\run_edge_agent.bat --debug` | Requires `show_llm_tab = true` in `config.ini:32` too |
| Use Gemini | `LLM_PROVIDER=gemini` + `LLM_MODEL=gemini-1.5-flash` | Provider and model must match |
| Cheaper anchor pass | `LLM_MODEL_ANCHOR=gpt-4o-mini` | Defaults to `LLM_MODEL` |
| Change data dir | `INPUT_DIR=...` | Before launch; `dati.csv` must live inside it |
| Edit a prompt | edit `prompts/<id>.json` | No rebuild; new `{placeholder}`s must be declared in `CATALOG` |
| Alternative prompt catalog | `PROMPTS_DIR=...` | Becomes the only candidate: no fallback, fails closed |
| Debug logs / crops | `DEBUG_MODE=1` / `DEBUG_SAVE_CROPS=1` | Crops go to `INPUT_DIR/debug_crops` |
| Sequential run | `PARALLEL_ENABLED=0` | Easier to read output / isolate failures |
| Cap cost per screen | `MAX_CALLS_PER_SCREEN=N` | Retries get `N - 2` calls |
| Edge-agent monitor / router | edit `monitor_index` / `router` in `edge-agent/config.ini` | 1-based; `ml` \| `llm` \| `hybrid` |
| Build .exe | `pyinstaller ... gui_app.py` | Full command in `README.md:91` |
