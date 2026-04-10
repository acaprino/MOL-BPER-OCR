# Getting Started

This is a proof-of-concept Python application that extracts structured data from Italian BPER banking screenshots using vision language models (GPT-4o, Gemini) through LangChain. Before you touch anything, understand that the project has three separate interfaces -- a CLI batch tool, a Tkinter desktop GUI, and a PyQt6 edge-agent with live screen capture -- all sharing the same `extraction/` core package. There are no tests, no CI, no Docker, and no linter configuration. The codebase is functional but intentionally rough around the edges as a POC.

## Prerequisites

**Required:**
- Python 3.8 or higher (the team has been running 3.13 based on compiled .pyc artifacts)
- An OpenAI API key (for the default `gpt-4o` provider) *or* a Google Gemini API key
- Git (the repo uses `develop` as the working branch, `master` as main)

**Required for edge-agent ML page classification:**
- PyTorch and torchvision (DINOv2 model downloads automatically on first run from Facebook Research's torch hub)

**Optional:**
- PyInstaller (only if you need to build a standalone `.exe` of the Tkinter GUI)

**Platform notes:**
- The `mss` library handles cross-platform screenshot capture. On Linux, `pyscreenshot>=3.1` is pulled in as a fallback (see the platform marker in `requirements.txt` line 11: `pyscreenshot>=3.1; sys_platform == 'linux'`).
- The edge-agent overlay (`edge-agent/ui/overlay.py`) uses PyQt6 window flags that behave differently across Windows and Linux. Development has been on Windows.

## Setup

**1. Clone and switch to the working branch:**

```bash
git clone <repo-url> poc-data-extraction
cd poc-data-extraction
git checkout develop
```

**2. Create a virtual environment and install dependencies:**

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

The single `requirements.txt` covers both the extraction pipeline and the edge-agent. Dependencies like `torch` and `torchvision` are large (~2 GB). If you only need the CLI batch tool, you can skip them -- the ML page classifier in the edge-agent gracefully degrades to `DISABLED` mode when torch is unavailable (`edge-agent/page_classifier.py`).

**3. Configure environment variables:**

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```
LLM_API_KEY=sk-your-openai-key-here
```

For Gemini, also change:

```
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
```

Every other variable has a sensible default. See `.env.example` for the full list.

**4. Add test data:**

The `mnt/data/` directory is gitignored. You need the 9 BPER banking screenshots (`screen 1.png` through `screen 9.png`) and the ground truth CSV (`dati.csv`) placed in `mnt/data/`. Ask the team for these files -- they contain real banking UI screenshots.

```bash
mkdir -p mnt/data
# Copy screen 1.png ... screen 9.png and dati.csv into mnt/data/
```

**5. Run the CLI batch extraction:**

```bash
python main.py
```

This loads the ground truth CSV, processes all PNGs in `mnt/data/`, and prints accuracy metrics and a cost summary to the console. Outputs are saved to `mnt/data/poc_outputs_improved.json` and `mnt/data/poc_debug_improved.csv`.

**6. Launch the edge-agent (PyQt6 GUI):**

```bash
python main.py --gui
```

Or directly:

```bash
cd edge-agent
python edge_agent.py
```

**7. Launch the Tkinter desktop GUI:**

```bash
python gui_app.py
```

This one lets you enter your API key in the UI, pick files manually, and select provider/model from a dropdown.

## Key Files to Read First

Read these in order. Each builds on the previous one.

1. **`extraction/config.py`** -- All environment variable handling, crop coordinates, pricing tables, and the `FIELD_RETRY_MAP`. This is where you learn what knobs exist and what the defaults actually are (note: `PARALLEL_WORKERS` defaults to `12` in code despite docs saying `4`).

2. **`extraction/fields.py`** -- The `FIELD_KEYS` list defines every field the system extracts (40+ fields). `CSV_TO_SCHEMA` maps Italian ground truth column names to schema keys. This is the data contract between the VLM output and the evaluation system.

3. **`extraction/schemas.py`** -- Pydantic models (`ExtractionResponse`, `AnchorResponse`, `FieldResult`, `Soggetto`, `Fido`, `Garanzia`) that define the structured output the VLM must produce. `FieldsModel` is dynamically generated from `FIELD_KEYS` at import time.

4. **`extraction/pipeline.py`** -- The `ExtractionPipeline` class orchestrates the three-pass extraction (anchor, main, retry). This is the core algorithm. Understanding `extract_from_image()` is essential before changing anything.

5. **`extraction/vlm_client.py`** -- How LLM calls actually happen: LangChain structured output for OpenAI, free-form JSON with manual Pydantic parsing for newer Gemini models. Retry logic with exponential backoff lives here.

6. **`extraction/prompts.py`** -- The Italian-language prompts (`PROMPT`, `ANCHOR_PROMPT`) sent to the VLM. These are highly tuned to the BPER banking UI layout and directly affect extraction accuracy.

7. **`extraction/evaluation.py`** -- Ground truth loading, per-field accuracy classification (OK/WRONG/MISSING/HALLUCINATED/OK_NULL), and the RAW vs FILTERED metrics split. Read this to understand how results are measured.

8. **`extraction/cli.py`** -- The `BatchRunner` class and `main()` function. Shows how models are created once and shared across a `ThreadPoolExecutor`. Also contains the commented-out `_deduplicate_same_page_outputs()` function.

9. **`edge-agent/edge_agent.py`** and **`edge-agent/config.ini`** -- The PyQt6 entry point and its INI-based configuration. The edge-agent has its own config system separate from `.env` variables.

10. **`CLAUDE.md`** -- The project's own internal documentation. Comprehensive at 276 lines, covering architecture, conventions, and constraints. Some references are outdated (e.g., `app.py` Streamlit entry point no longer exists).

## Where Things Live

**To understand the extraction logic:**
Look in `extraction/pipeline.py` for the multi-pass orchestration. The three passes (anchor, main, retry) are methods on `ExtractionPipeline`. Crop coordinates are in `extraction/config.py` (`CONTENT_CROP`, `HEADER_IN_CONTENT`, `RETRY_AREAS`).

**To add or modify an extracted field:**
Start in `extraction/fields.py` -- add the key to `FIELD_KEYS` and add the ground truth mapping to `CSV_TO_SCHEMA`. Then add field metadata in `extraction/field_definitions.py` (display name and page assignment). The Pydantic schema in `extraction/schemas.py` auto-generates from `FIELD_KEYS`, so no change needed there.

**To change how LLM calls are made:**
`extraction/vlm_client.py` handles all VLM communication. `extraction/llm_factory.py` is the factory that creates LangChain `ChatModel` instances. Provider-specific behavior (OpenAI structured output vs Gemini freeform JSON) is in `vlm_client.py`.

**To modify the VLM prompts:**
`extraction/prompts.py` contains `PROMPT` (main pass), `ANCHOR_PROMPT` (header-only pass), and `FIELD_RETRY_PROMPTS` (per-area retry prompts). These are in Italian and tuned to BPER UI terminology.

**To change image preprocessing:**
`extraction/imaging.py` handles normalization (resize, contrast, unsharp mask) and cropping for the extraction pipeline. `edge-agent/image_ops.py` handles preprocessing for the live capture path (separate logic).

**To work on the edge-agent UI:**
Tab implementations are in `edge-agent/ui/` -- `capture_tab.py` (start/stop capture), `extraction_results_tab.py` (results display), `data_table_tab.py` (spreadsheet export), `debug_tab.py` (LLM router debug). The main window assembles them in `edge-agent/ui/main_window.py`.

**To change page detection in the edge-agent:**
`edge-agent/llm_router.py` has `LLMPageRouter` (OpenAI Vision) and `MLPageRouter` (DINOv2 cosine similarity). The router mode is set in `edge-agent/config.ini` under `[agent] router=`. Page prototypes and LLM definitions are in `edge-agent/assets/templates/bper/`.

**To change how accuracy is evaluated:**
`extraction/evaluation.py` for the evaluation framework. `extraction/normalization.py` for the `classify_field()` function and text normalization logic used for comparison.

## Common Tasks

### Run CLI batch extraction and see accuracy

```bash
python main.py
```

This requires `mnt/data/dati.csv` (ground truth) and screenshot PNGs in `mnt/data/`. It prints per-field accuracy (RAW and FILTERED metrics) and a cost summary to stdout. Outputs go to `mnt/data/poc_outputs_improved.json`.

To enable debug output:

```bash
DEBUG_MODE=1 python main.py
```

To save intermediate crop images:

```bash
DEBUG_SAVE_CROPS=1 python main.py
```

Crops are saved to `mnt/data/debug_crops/`.

### Switch LLM providers

Edit `.env`:

```bash
# For Gemini
LLM_PROVIDER=gemini
LLM_API_KEY=AI...
LLM_MODEL=gemini-2.0-flash
```

Or use environment variables directly:

```bash
LLM_PROVIDER=gemini LLM_API_KEY=AI... LLM_MODEL=gemini-2.0-flash python main.py
```

The `gui_app.py` Tkinter interface also lets you pick provider and model from a dropdown at runtime.

### Build a standalone Windows executable

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name "AI_Data_Extractor" --add-data "extraction;extraction" --collect-all langchain_google_genai --collect-all langchain_openai gui_app.py
```

The `.exe` appears in `dist/AI_Data_Extractor.exe`. This packages only the Tkinter GUI, not the edge-agent.

### Test a single screenshot manually

There is no single-image CLI command. The fastest path is to place one image in `mnt/data/`, ensure the ground truth CSV has matching rows, and run `python main.py`. Or use `gui_app.py` to select individual files through the file browser.

### Export edge-agent results to CSV/Excel

In the edge-agent GUI, the Data Table tab (`edge-agent/ui/data_table_tab.py`) provides CSV and Excel export buttons. The `LocalExtractionClient.export_csv()` method (`edge-agent/local_extraction_client.py`) handles the export logic. Excel export uses `openpyxl`.

## Gotchas

**PARALLEL_WORKERS default mismatch.** The code in `extraction/config.py` line 11 defaults to `12`, but `.env.example` and `CLAUDE.md` both say `4`. If you run without `.env`, you get 12 parallel workers, which may overwhelm rate limits on a free-tier API key.

**LLM_THINKING_LEVEL looks inconsistent but is functionally unset.** `extraction/config.py` line 20 stores a `medium` default into a module-level constant, but that constant is not consumed anywhere. The live check in `extraction/llm_factory.py` line 72 re-reads the env var with an empty default, so leaving it unset (as `.env.example` and `CLAUDE.md` both do) keeps thinking mode off. This only affects Gemini models whose name contains "thinking".

**The `mnt/` directory is gitignored.** You will not get test data from the repo. The ground truth CSV (`mnt/data/dati.csv`) and all 9 screenshot PNGs must be obtained separately. Without these, `python main.py` raises `FileNotFoundError`.

**API key in committed config file.** The file `edge-agent/config.ini` line 23 contains what appears to be a real OpenAI API key in the `[llm]` section. This key is committed to version control. Verify with the team whether it needs rotation.

**Missing Streamlit app.** `CLAUDE.md` references `app.py` as a Streamlit web UI entry point, and `streamlit` is in `requirements.txt`, but no `app.py` exists in the repository. The Streamlit interface was either removed or never committed to this branch.

**edge-agent has its own config system.** The extraction pipeline uses `.env` environment variables (`extraction/config.py`). The edge-agent uses `edge-agent/config.ini` parsed by `edge-agent/config.py`. These are separate systems -- changing `.env` does not affect the edge-agent's LLM router settings, and vice versa. The edge-agent does load `.env` for the extraction pipeline's `LLM_API_KEY`, but router LLM settings come from `config.ini`.

**Deduplication is disabled.** `_deduplicate_same_page_outputs()` in `extraction/cli.py` (lines 268-275) is implemented but commented out. The batch runner currently keeps all outputs, even if multiple screenshots map to the same canonical page.

**Config loads at import time.** `extraction/config.py` reads environment variables at module import, which happens when `main.py` does `from extraction import *`. If you set env vars after import, they will not take effect. The `.env` file must be loaded before the extraction package is imported -- `main.py` handles this correctly with `load_dotenv()` before the import.

**Italian field names are load-bearing.** Field keys like `professione_principale`, `retribuzione_annua_netta`, and `denominazione` are not translatable -- they must match the BPER banking domain schema. The VLM prompts are also in Italian. Do not translate them.

**torch is a heavy optional dependency.** The `requirements.txt` includes `torch` and `torchvision` for the edge-agent's ML page classifier. These are ~2 GB downloads. If you only need the CLI extraction, you can skip them. The ML classifier degrades gracefully to `DISABLED` mode (`edge-agent/page_classifier.py`), and the edge-agent can use `router = llm` in `config.ini` instead.

## See Also

- [Tech Stack](03-tech-stack.md) -- detailed breakdown of each dependency, version constraints, and what is optional
- [Project Anatomy](09-project-anatomy.md) -- the complete environment variable table and configuration file catalog
- [Configuration Guide](10-configuration-guide.md) -- recipes for switching providers, enabling debug crops, and troubleshooting common errors
- [Workflows](05-workflows.md) -- step-by-step flows for the CLI batch, edge-agent capture, and multi-pass pipeline
- [Open Questions](08-open-questions.md) -- discrepancies and unresolved decisions that will affect your first change
