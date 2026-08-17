# Getting Started

This is a Python proof-of-concept that extracts structured fields from Italian BPER banking screenshots with a multi-pass Vision-LLM pipeline. Before you touch the code, internalize three facts. First, all business logic lives in one UI-free package, `extraction/`; the CLI (`main.py`), the Tkinter GUI (`gui_app.py`), and the PyQt6 edge-agent (`edge-agent/`) are thin front-ends over it. Second, there is no test suite, no CI, and no Docker; you verify changes by running the pipeline and comparing the accuracy and cost numbers it prints. Third, every run calls a paid LLM API; there is no offline or mock mode, so you need a funded OpenAI (or Gemini) key from minute one.

Two things will block you on day one if you don't know them: the ground-truth file `mnt/data/dati.csv` is **not in the repository** (the CLI refuses to start without it, `extraction/cli.py:315-316`), and the git history was **rewritten on 2026-07-21** to scrub a leaked API key; if you cloned before that date, re-clone before doing anything else. Both are covered in [Gotchas](#gotchas) and in [Open Questions](08-open-questions.md).

Read this alongside [Architecture](04-architecture.md), [Tech Stack](03-tech-stack.md), and [Workflows](05-workflows.md).

## Prerequisites

- **Python 3.13** (3.12 acceptable). The docs claim 3.8+ (`README.md` line 3), but the Windows launcher deliberately probes `py -3.13`, then `py -3.12`, and avoids newer interpreters that lack torch wheels (`run_edge_agent.bat:44-58`). 3.13 is the known-good runtime on the dev machine.
- **A funded LLM API key.** OpenAI by default; Gemini as the alternative provider. Without a key, model construction raises `ValueError: API key required` (`extraction/llm_factory.py:41-44`); this fires at startup for both the CLI batch runner and the edge-agent's `LocalExtractionClient`.
- **`mnt/data/dati.csv`**: required only for the CLI evaluation path. It is absent from both the working tree and git (`.gitignore:9` ignores `/mnt`; only the 9 PNGs were force-added). Ask the team for the canonical file; see [Open Questions](08-open-questions.md#business-logic).
- **A torch/torchvision-capable machine** for the edge-agent's ML page router. The shipped config uses `router = ml`, so it is needed: the classifier disables itself gracefully if torch fails to import (`edge-agent/page_classifier.py:9-19`), but in that state no page is ever recognized. Only switching to `router = llm` makes torch unnecessary.
- **(Optional) A monitor showing the BPER application** for live capture. The edge-agent grabs a whole monitor by index (`monitor_index = 1` in `edge-agent/config.ini`), not a window.

Platform note: development happens on Windows 11. The extraction pipeline itself is platform-neutral; the only platform-conditional dependency is `pyscreenshot`, marked Linux-only in `requirements.txt:10`. Commands below are PowerShell-first with bash equivalents where the syntax differs.

## Setup

### 0. If you cloned before 2026-07-21: re-clone

The entire git history was rewritten with `git filter-repo` and force-pushed to scrub a leaked OpenAI key from `edge-agent/config.ini`. All commit hashes changed. A stale clone will fail to push cleanly, and worse, pushing from one would **reintroduce the leaked key into history**. Do not merge or push from an old clone; start fresh:

```powershell
git clone <origin-url> poc-data-extraction
cd poc-data-extraction
```

### 1. Fast path (Windows): the launcher does everything

```powershell
.\run_edge_agent.bat
```

This creates `.venv` with Python 3.13 (or 3.12), installs `requirements.txt` (torch is large; first run takes several minutes), and launches the edge-agent. It also self-heals a broken venv whose base interpreter was moved or uninstalled (`run_edge_agent.bat:19-29`). Any arguments are forwarded to the app, e.g. `.\run_edge_agent.bat --debug`.

### 2. Manual path (all platforms)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

One `requirements.txt` covers everything: extraction core and edge-agent. Note that `streamlit` (`requirements.txt:5`) is orphaned: the old Streamlit `app.py` was deleted, nothing imports it.

### 3. Create your `.env`

```powershell
copy .env.example .env
```

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```
LLM_API_KEY=<your key>
```

All three entry points auto-load `.env` via `python-dotenv` (`main.py:7`, `edge-agent/edge_agent.py:9-13`, `edge-agent/local_extraction_client.py:21-25`), so you never need to export variables in your shell for a normal run. The template defaults to `LLM_PROVIDER=openai` and `LLM_MODEL=gpt-4o`.

For Gemini instead:

```
LLM_PROVIDER=gemini
LLM_API_KEY=<your Gemini key>
LLM_MODEL=gemini-1.5-flash
```

The factory rejects mismatched pairs: a `gemini-*` model with `LLM_PROVIDER=openai` (or `gpt-*` with `gemini`) raises `ValueError` (`extraction/llm_factory.py:49-63`).

### 4. Supply the ground-truth CSV (CLI only)

Place `dati.csv` in `mnt/data/` using the long format documented in `README.md` lines 221-241:

```
Fotogramma,Denominazione da attribuire,Valore rilevato
screen 1,NDG,31943680
screen 1,DENOMINAZIONE,"TICCHI SERENA, CABRAS LUCA"
screen 1,Tipo,BPI Mutui
```

The loader tolerates alternate column names (`Screenshot`/`Screen`, `Campo`/`Field`, `Valore`/`Value`; `_find_column()` in `extraction/evaluation.py`). The Tkinter GUI and the edge-agent work **without** this file; only `python main.py` hard-requires it.

### 5. Run

```powershell
python main.py                            # CLI batch over every image in mnt/data/
python gui_app.py                         # Tkinter desktop GUI (pick files manually)
python main.py --gui                      # edge-agent (PyQt6) live capture
python edge-agent/edge_agent.py           # edge-agent, launched directly
python edge-agent/edge_agent.py --debug   # edge-agent + Debug LLM router tab
```

`main.py --gui` just inserts `edge-agent/` into `sys.path` and calls `edge_agent.main()` (`main.py:15-20`). The `--debug` flag gates the Debug LLM tab (`edge-agent/edge_agent.py:51`), which additionally requires `show_llm_tab = true` in `edge-agent/config.ini` `[debug]`.

## Key Files to Read First

Ordered by learning value: from the data contract outward to orchestration and UI.

1. **`extraction/fields.py`**: `FIELD_KEYS` (45 keys, lines 12-54) is the single source of truth for everything the system extracts. The Pydantic schema, CSV mapping, metrics, and retry map all key off this list; read it first and the domain vocabulary (`ndg`, `fido`, `professione_principale`) stops being noise.
2. **`extraction/schemas.py`**: The LLM output contract: `FieldResult` (value/confidence/evidence/section), `Soggetto`, `Fido`, `Garanzia`, `ExtractionResponse`, `AnchorResponse`. `FieldsModel` is generated dynamically from `FIELD_KEYS`, which is why `fields.py` comes first.
3. **`extraction/pipeline.py`**: `ExtractionPipeline`, the heart of the system: anchor pass → main pass → conditional area retries → coherence check → soggetti flattening. If you read only one file, read this one; note the two entry points `extract_from_screen()` (CLI/Tkinter) and `extract_from_image()` (edge-agent, normalization intentionally bypassed).
4. **`extraction/config.py`**: Every tunable knob: env-var config, crop coordinates (`CONTENT_CROP`, `HEADER_IN_CONTENT`, `RETRY_AREAS`), the field-to-retry-area map (`AREA_TO_FIELDS`), and the pricing table (`PRICING_PER_1M`). Env vars are read **at import time** (module-level `os.getenv`), which matters; see Gotchas.
5. **`extraction/cli.py`**: `BatchRunner` and `run_extraction_batch()`, the shared batch engine used by both the CLI and the Tkinter GUI. Shows the thread model: ChatModels created once, shared across the `ThreadPoolExecutor`. `main()` at line 314 is the CLI flow end to end.
6. **`extraction/vlm_client.py`**: The low-level LLM calls and the provider-specific structured-output strategies (OpenAI `.with_structured_output()`, Gemini 1.5 json_mode, Gemini 2.0+/3.x free-form JSON + manual validation, gated by `_GEMINI_JSON_SCHEMA_MODELS` at line 18). Also where `_meta` cost tracking is populated.
7. **`extraction/evaluation.py`**: `load_ground_truth()`, `eval_outputs()`, and the OK / WRONG / MISSING / HALLUCINATED / OK_NULL classification; explains the RAW vs FILTERED metric split driven by `dataset_mismatch_guard()`.
8. **`edge-agent/local_extraction_client.py`**: Short and load-bearing: the QObject bridge between the PyQt6 UI and `ExtractionPipeline`, the `ingest_frame()` seam, and the `result_ready` signal that crosses back to the UI thread.
9. **`edge-agent/workers/capture/bper_capture_worker.py`**: The capture loop: mss screenshot, `preprocess_for_ocr()`, pHash dedup, page routing, 2-second stability gate, then the synchronous `ingest_frame()` call (line 696). The largest file in `edge-agent/`; read it last, once the pipeline is clear.

## Where Things Live

| To do this… | Look here |
|---|---|
| Add or rename an extracted field | `extraction/fields.py` (`FIELD_KEYS`, `CSV_TO_SCHEMA`), then `extraction/field_definitions.py` (`CANONICAL_FIELD_DEFINITIONS`, `FIELD_LABEL_ALIASES`) and `extraction/config.py` (`AREA_TO_FIELDS`) |
| Change what the VLM is asked to extract | `prompts/*.json` (`extraction_main`, `extraction_anchor`, `extraction_retry_*`) - Italian by design, loaded by `prompt_store.py`; adding a `{placeholder}` means updating `CATALOG` too |
| Adjust crop regions | `extraction/config.py` (`CONTENT_CROP`, `HEADER_IN_CONTENT`, `RETRY_AREAS`) |
| Add a model or fix pricing | `extraction/config.py` (`PROVIDER_MODELS`, `PRICING_PER_1M`) |
| Change provider/key selection | `extraction/llm_factory.py` (`create_chat_model()`) - the single LLM factory |
| Tune the multi-pass logic (gates, retry caps) | `extraction/pipeline.py` + env vars `ANCHOR_CONF_MIN`, `MAX_CALLS_PER_SCREEN`, `STOP_ON_ANCHOR_UNCERTAIN` |
| Change accuracy scoring or GT loading | `extraction/normalization.py` (`classify_field`, `pick_best`, `dataset_mismatch_guard`) and `extraction/evaluation.py` |
| Change the batch flow | `extraction/cli.py` - do not re-implement its threading elsewhere; both CLI and Tkinter use `run_extraction_batch()` |
| Edit the Tkinter desktop UI | `gui_app.py` (single file) |
| Edit the edge-agent UI | `edge-agent/ui/` (`main_window.py`, `capture_tab.py`, `extraction_results_tab.py`, `data_table_tab.py`, `debug_tab.py`, `overlay.py`) |
| Change live-capture behavior (FPS, dedup, stability, monitor) | `edge-agent/workers/capture/bper_capture_worker.py` + `edge-agent/config.ini` |
| Change page detection | `edge-agent/llm_router.py`, `edge-agent/page_classifier.py`; mode via `router =` in `edge-agent/config.ini`; page definitions in `edge-agent/assets/templates/bper/prompts.json` |
| Configure the edge-agent | `edge-agent/config.ini` - **not** env vars (only the router API key falls back to env) |

## Common Tasks

### Run a full extraction and evaluate it (CLI)

```powershell
python main.py
```

Processes every `.png`/`.jpg`/`.jpeg` in `INPUT_DIR` (`extraction/cli.py:322-327`), then:

- writes `mnt/data/poc_outputs_improved.json` (full per-screen results, `extraction/cli.py:337`);
- prints RAW and FILTERED accuracy with a per-field breakdown;
- writes `mnt/data/poc_debug_improved.csv`: semicolon-separated, `utf-8-sig` (Excel-friendly, `extraction/evaluation.py:172-176`);
- prints per-screen calls/tokens/USD via `print_cost_summary()`.

There is no committed baseline, so "did my change help?" means comparing these numbers against a run you saved yourself before changing anything. Save the previous JSON and the printed summary first.

### Extract a few images without ground truth (Tkinter)

```powershell
python gui_app.py
```

The API key field pre-fills from `LLM_API_KEY` (or legacy `OPENAI_API_KEY`, `gui_app.py:24`); pick provider/model from the dropdowns, select images, optionally a GT CSV, and run. Outputs land in the current directory: `poc_outputs_gui.json`, `poc_results_gui.csv`, and (if a GT CSV was given) `poc_debug_gui.csv` (`gui_app.py:250-273`).

### Smoke-test live capture (edge-agent)

```powershell
.\run_edge_agent.bat --debug
```

In the *Cattura* tab, choose BPER mode and press *Avvia*. Each frame is grabbed whole-monitor, normalized back to the app window (`frame_normalize.normalize_frame()`), preprocessed, deduped by pHash, routed to a page type (ML router by default, `router = ml` in `edge-agent/config.ini`), held to a 2-second stability window, then extracted locally via `ingest_frame()`. Verify results appear in the *Risultati* tree and the *Dati Estratti* spreadsheet. Use *Acquisisci ora* to force-capture a manually selected page. The Debug LLM tab (with `--debug`) shows the router's raw prompt/response: the first place to look when pages are not recognized.

### Add a new field

`FIELD_KEYS` fans out widely; a new field touches four or five files:

1. Add the key to `FIELD_KEYS` in `extraction/fields.py`; the Pydantic `FieldsModel` regenerates automatically from it.
2. Map the ground-truth CSV label in `CSV_TO_SCHEMA` (`extraction/fields.py`).
3. Add `display_name` + `page_key` in `CANONICAL_FIELD_DEFINITIONS` and the alias in `FIELD_LABEL_ALIASES` (`extraction/field_definitions.py`) so canonical export and the UI page grouping pick it up.
4. Assign it to a retry area in `AREA_TO_FIELDS` (`extraction/config.py:69-82`) if it should be re-attempted when null/low-confidence.
5. Describe it in the Italian prompt (`prompts/extraction_main.json`) so the model knows to look for it.

### Debug a wrong extraction

```powershell
$env:DEBUG_MODE = "1"
$env:DEBUG_SAVE_CROPS = "1"
python main.py
```

`DEBUG_MODE` turns on verbose batch logging (`extraction/config.py:92`; note it is missing from `.env.example`), and `DEBUG_SAVE_CROPS` dumps every intermediate crop to `mnt/data/debug_crops/` (`extraction/config.py:93-94`). Seeing exactly which crop went to the model is the fastest way to diagnose a bad field. Cross-check `_field_sources` in the output JSON to learn which pass (ANCHOR_HEADER / CONTENT_MAIN / RETRY_*) produced the final value.

### "Deploy": build the Windows executable

The only packaging path is a PyInstaller build of the Tkinter app (`README.md:78-100`):

```powershell
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name "AI_Data_Extractor" --add-data "extraction;extraction" --collect-all langchain_google_genai --collect-all langchain_openai gui_app.py
```

Output: `dist/AI_Data_Extractor.exe`. The `--collect-all` flags are load-bearing: LangChain's provider packages use dynamic imports PyInstaller misses otherwise. There is no packaged distribution for the edge-agent; `run_edge_agent.bat` is its only launcher.

## Gotchas

- **The CLI dies immediately without `mnt/data/dati.csv`.** Guaranteed on a fresh clone: `/mnt` is gitignored (`.gitignore:9`) and only the 9 screenshots were force-added, so `python main.py` raises `FileNotFoundError: Ground truth CSV not found: mnt/data/dati.csv` (`extraction/cli.py:315-316`). Get the file from the team before attempting a CLI run; the two GUIs work without it.

- **The git history was rewritten on 2026-07-21; stale clones are dangerous.** An OpenAI key had been committed in `edge-agent/config.ini`; it was scrubbed from the full history with `git filter-repo` and force-pushed. Every commit hash changed. If your clone predates the rewrite, re-clone (or hard-reset to the new origin); a push or merge from a stale clone would put the leaked key back into history.

- **Never put a real key in `edge-agent/config.ini`.** The `[llm] api_key` line is in a tracked file and now ships **blank**. The router's key lookup prefers the INI value over env and is provider-aware (`AgentConfig.resolve_llm_settings()`): for `gemini` it falls back to `GEMINI_API_KEY` → `GOOGLE_API_KEY` → `LLM_API_KEY`, for `openai` to `OPENAI_API_KEY` → `LLM_API_KEY`. The safe pattern is: leave the INI line blank and set the key in `.env`. Any value starting with `REDACTED` counts as blank, because a leftover placeholder once shadowed the env keys and silently broke the router. Extra trap: `AgentConfig.save()` writes `llm_api_key` back into `config.ini` (`edge-agent/config.py:326-332`); currently nothing calls `save()`, but wiring it to a UI button would re-persist secrets into a tracked file.

- **Every run spends money, and unknown models report $0.00.** Per screen: 1 anchor call + 1 main call + up to `MAX_CALLS_PER_SCREEN - 2` area retries, one per weak area (`extraction/pipeline.py:261`), in parallel across screens. `MAX_CALLS_PER_SCREEN` defaults to `2 + len(AREA_TO_FIELDS)` (= 5), so the worst case is 5 calls. `estimate_cost_usd()` returns `0.0` for any model missing from `PRICING_PER_1M` (`extraction/vlm_client.py:21-26`); since `LLM_MODEL` is free-form, a typo'd or dated model name (e.g. `gpt-4o-2024-11-20`) silently zeroes the cost report rather than failing.

- **Env vars are read at import time.** `extraction/config.py` evaluates every `os.getenv()` at module import. The entry points load `.env` before importing `extraction`, so normal runs are fine, but in a REPL or notebook, set env vars *before* `import extraction`, or your changes are ignored.

- **The edge-agent is INI-configured, not env-configured.** FPS, router mode, monitor index, dedup threshold: all from `edge-agent/config.ini`. Editing `.env` changes only the extraction LLM and the router-key fallback.

- **Capture is whole-monitor, but the frame is cropped back to the window.** `_grab_raw()` grabs the monitor via `mss`, then `frame_normalize.normalize_frame()` brings the framing back to the application window: first by looking for the title containing `window_title_contains` (`config.ini`), then by inferring the rectangle from the desktop background, otherwise leaving the frame alone. This is not cosmetic: every downstream crop (the classifier ROI, the pipeline's `CONTENT_CROP`) is a fraction calibrated on window screenshots and lands elsewhere on a full monitor. Without the crop, page recognition drops from 9 correct out of 9 to 1 out of 9 ([ADR 0001](../docs/adr/0001-normalizzazione-inquadratura-frame.md)).

- **`CLAUDE.md` and `README.md` drift from the code; trust the code.** Known drift: CLAUDE.md describes startup `if/raise` guards and a `_FIELD_COMPARATORS` dict that do not exist in `extraction/`; README says "18 campi" but `FIELD_KEYS` has 45; the `run_extraction_batch()` docstring still says "Shared by CLI (main) and Streamlit (app.py)" (`extraction/cli.py:296`) though `app.py` is long gone; the comment at `edge-agent/workers/capture/bper_capture_worker.py:42` says "MobileNetV3" but the classifier is DINOv2 ViT-S/14 (`edge-agent/page_classifier.py:203`); `SCREENSHOT_DIR` in CLAUDE.md's table is read nowhere.

- **The ML page router downloads weights from the internet on first use.** `torch.hub.load('facebookresearch/dinov2', 'dinov2_vits14')` (`edge-agent/page_classifier.py:203`) fetches from GitHub on the first `router = ml`/`hybrid` run. On a locked-down network the classifier will fail and silently disable itself; page routing then never matches, which looks like "capture runs but nothing is ever acquired".

- **Extraction blocks the capture thread.** `ingest_frame()` runs the full multi-call VLM pipeline synchronously inside the capture QThread (`edge-agent/local_extraction_client.py:77-86`, called from `bper_capture_worker.py:696`). While a page is being extracted, the FPS loop is stalled. Intentional, but surprising if you expect background processing.

- **Italian is intentional.** VLM prompts, field keys (`professione_principale`), PyQt6/Tkinter UI strings, and CSV headers are Italian domain terms; do not translate them. Code, identifiers, comments, and commit messages stay English (language policy in `CLAUDE.md`).
