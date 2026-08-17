# Tech Stack

This is a Python-only proof-of-concept that treats the vision LLM as a swappable component. Every extraction call goes through **LangChain**, so one factory function (`create_chat_model()` in **`extraction/llm_factory.py`**) picks OpenAI or Google Gemini at runtime from a single environment variable, and the rest of the stack is arranged around that seam: Pillow for image cropping and enhancement, Pandas for ground-truth comparison, Tkinter and PyQt6 for the two desktop front-ends, and an optional PyTorch/DINOv2 classifier for on-device page recognition. There is no web server, no database, and no build system; the project runs as scripts from a single flat `requirements.txt`.

## Languages

| Language | Version | Where configured |
|----------|---------|------------------|
| Python | 3.8+ claimed (`CLAUDE.md`, `README.md`); 3.12/3.13 in practice | No `pyproject.toml` exists, so nothing declares a version formally. `run_edge_agent.bat` lines 50-52 probe for Python 3.13, then 3.12 (torch wheel availability drives the preference), and the committed bytecode in `extraction/__pycache__/` is CPython 3.13. Treat 3.12+ as the real target. |

Python is the only implementation language. The codebase deliberately mixes two *natural* languages, though: code, identifiers, comments, and commit messages are English, while VLM prompts (**`prompts/*.json`**), field keys (`professione_principale`, `filiale_relazione`, ...), GUI strings, and CSV headers are Italian, because the extraction target is the Italian BPER banking UI and the field keys are load-bearing domain terms that must match the ground-truth CSV (`extraction/fields.py`, `CSV_TO_SCHEMA`). Do not translate them.

## Frameworks

| Framework | Role | Version constraint |
|-----------|------|--------------------|
| LangChain | The LLM abstraction layer and the project's load-bearing dependency. `create_chat_model()` (`extraction/llm_factory.py:16`) returns a `BaseChatModel`; `call_vlm()` (`extraction/vlm_client.py:122`) drives Pydantic structured output through `.with_structured_output()`. Both providers, all three passes, all front-ends go through it. | `langchain-core`, `langchain-openai`, `langchain-google-genai` - all unpinned (`requirements.txt:1-3`) |
| PyQt6 | Desktop UI for the edge-agent (live screen capture). Entry `edge-agent/edge_agent.py`; window and tabs in `edge-agent/ui/`; capture workers are `QThread` subclasses, and results cross back to the UI thread via Qt signals. | `PyQt6>=6.4.0` (`requirements.txt:7`) |
| qt-material | Material theme (`dark_cyan.xml`) applied at edge-agent startup (`edge-agent/edge_agent.py`). Optional: startup degrades to the default style if the import fails. | `qt-material>=2.14` (`requirements.txt:8`) |
| Tkinter | The standalone desktop GUI `gui_app.py` (image picker, provider/model dropdowns, results view, CSV/JSON export). Standard library, so no `requirements.txt` entry. | stdlib |
| PyTorch / torchvision | Backs the optional ML page classifier `BPERPagePrototypeClassifier` (`edge-agent/page_classifier.py`): DINOv2 ViT-S/14 embeddings (384-dim) matched against cached prototypes by cosine similarity. If the torch import fails, the classifier self-disables and `classify()` returns `(None, 0.0)` instead of crashing (`edge-agent/page_classifier.py:9-19`). | `torch`, `torchvision` - unpinned (`requirements.txt:14-15`) |

## Key Dependencies

Grouped by purpose. Everything lives in the single root **`requirements.txt`** (17 lines); transitive dependencies are omitted except where they matter.

### LLM access
- **`langchain-core` / `langchain-openai` / `langchain-google-genai`** (`requirements.txt:1-3`): covered under Frameworks. The provider packages are lazily imported inside `create_chat_model()`, so only the selected provider's package must actually work at runtime (`extraction/llm_factory.py:47,57`).
- **`openai`** (`requirements.txt:16`, `>=1.51.0`): the *raw* OpenAI SDK, used only by the edge-agent's `LLMPageRouter` for page classification (`edge-agent/llm_router.py:200-209`), with `response_format=json_object`, `temperature=0.0`, and a config-driven timeout. The extraction pipeline itself never touches this SDK; it is the one sanctioned exception to the single-factory rule.
- **`pydantic`** (transitive via LangChain): defines the structured-output schemas in `extraction/schemas.py` (`FieldResult`, `ExtractionResponse`, `AnchorResponse`) and validates the Gemini free-form JSON path manually (`extraction/vlm_client.py:93`).

### Imaging and capture
- **`Pillow`** (`requirements.txt:11`, `>=10.0.0`): all crop/resize/enhance work: `normalize_image()`, `crop_relative()`, `img_to_png_bytes()` in `extraction/imaging.py` for the pipeline; `preprocess_for_ocr()` (adaptive upscale, unsharp mask, autocontrast) in `edge-agent/image_ops.py` for capture.
- **`mss`** (`requirements.txt:9`, `>=9.0.0`): fast monitor grab in the edge-agent capture loop (`edge-agent/workers/capture/bper_capture_worker.py:557-574`).
- **`imagehash`** (`requirements.txt:12`, `>=4.3.0`): perceptual hashing (pHash) for frame dedup; frames within Hamming distance `dedup_threshold` (default 3) skip routing (`bper_capture_worker.py:601-624`).
- **`pyscreenshot`** (`requirements.txt:10`, `>=3.1`, **Linux-only environment marker** `sys_platform == 'linux'`): fallback grabber used only by `DefaultCaptureWorker` (generic mode). On Windows it is not installed at all, which is fine because the BPER path uses `mss`.

### Data and evaluation
- **`pandas`** (`requirements.txt:4`): loads the ground-truth CSV with column-name auto-detection (`load_ground_truth()`, `extraction/evaluation.py:33`) and writes the debug/results CSVs (`;`-separated, `utf-8-sig`).
- **`openpyxl`** (`requirements.txt:17`, `>=3.1.2`): reads the optional page-sequence workbook `Guida pagine ITA .xlsx` (`bper_capture_worker.py:273-291`; the file is absent from the repo, with a graceful fallback to `prompts.json`) and backs the Excel export in `edge-agent/ui/data_table_tab.py`.

### Configuration and bootstrap
- **`python-dotenv`** (`requirements.txt:6`): loads `.env` before the `extraction` package is imported, which matters because `extraction/config.py` reads every env var at import time. Loaded in `main.py:7`, `edge-agent/edge_agent.py:9-13`, and `edge-agent/local_extraction_client.py:22-25`, but **not** in `gui_app.py`, which assumes env vars are already exported (see [Open Questions](08-open-questions.md)).
- **`requests`** (`requirements.txt:13`, `>=2.31.0`): HTTP frame upload used only by the legacy generic capture mode (`edge-agent/workers/capture/default_capture_worker.py:62-66`), which POSTs to a backend that does not exist in this repo.

### Orphaned
- **`streamlit`** (`requirements.txt:5`): nothing imports it. It is a leftover from the removed Streamlit web UI (`app.py`, deleted in commit `ea04ef7`). Removal candidate; `CLAUDE.md` flags it too.

## Infrastructure

There is no database, message queue, or cache. Results live in in-memory dicts (in the edge-agent, a `threading.Lock`-guarded `_results` dict inside `LocalExtractionClient`) and are persisted only as files: `mnt/data/poc_outputs_improved.json` and `poc_debug_improved.csv` from the CLI, `poc_outputs_gui.json` / `poc_results_gui.csv` / `poc_debug_gui.csv` from the Tkinter GUI, and operator-exported CSV/XLSX from the edge-agent.

Live external services (all outbound HTTPS):
- **OpenAI API**: main extraction via LangChain (`gpt-4o` default) and page routing via the raw SDK (`gpt-4o-mini`).
- **Google Gemini API**: alternative extraction provider (`LLM_PROVIDER=gemini`).
- **torch.hub**: DINOv2 weights are downloaded once on the first ML-router run.

Dead infrastructure referenced in config but unused in the BPER local-only flow, remnants of the removed remote backend era (commit `ea04ef7`):
- A frame-ingest API at `http://localhost:8081` (`edge-agent/config.ini:10`, `[api]`), reachable only from the legacy generic mode.
- MinIO at `http://localhost:9000` (`config.ini` `[minio]`); the only would-be consumer, `_maybe_upload_dataset()`, is a no-op stub (`bper_capture_worker.py:713-715`).

## Dev Tools

| Tool | Role | Status |
|------|------|--------|
| PyInstaller | Packages `gui_app.py` into a Windows `.exe` (`AI_Data_Extractor`), with `--collect-all` flags for LangChain's dynamic imports. | Recipe documented in `README.md` lines 78-100 only; not in `requirements.txt` |
| `run_edge_agent.bat` | Windows launcher: probes/rebuilds a stale `.venv` (preferring Python 3.13), installs `requirements.txt`, launches the edge-agent forwarding args. | Committed, working |
| Linter / formatter | None. No `ruff`, `flake8`, `black`, or `pyproject.toml` config anywhere. | Absent |
| Test runner | None. There is no test suite; validation is manual (run `python main.py`, compare accuracy and cost against a baseline, smoke-test the GUIs - `CLAUDE.md` "Testing & Validation"). | Absent |
| CI/CD | None. No `.github/workflows` or pipeline config. | Absent |
| Docker | None. No `Dockerfile`. | Absent |

The gaps are consistent with POC maturity and are acknowledged in `CLAUDE.md` "Missing Infrastructure".

## Dependency Management

pip with a **single flat `requirements.txt`** at the repo root: extraction-core and edge-agent dependencies combined, no per-component split, no dev-dependency group, no lockfile, no `pyproject.toml`.

Two constraint styles coexist:
- **Unpinned:** the LangChain trio, `pandas`, `streamlit`, `python-dotenv`, `torch`, `torchvision`. The unpinned LangChain packages are the highest-risk item: the structured-output behavior that `extraction/vlm_client.py` branches on per provider/model family (`_GEMINI_JSON_SCHEMA_MODELS`, `vlm_client.py:18,134-138`) is sensitive to LangChain version drift.
- **Lower-bound (`>=`):** `PyQt6`, `qt-material`, `mss`, `pyscreenshot`, `Pillow`, `imagehash`, `requests`, `openai`, `openpyxl`.

Nothing is exactly pinned, so a fresh `pip install -r requirements.txt` is not reproducible across days: different LangChain or torch versions can land silently. Two more things worth flagging: `pyscreenshot` carries a platform marker (Linux only), so cross-platform installs differ by design; and `streamlit` is a pure orphan inflating an already heavy install (torch is the bulk of it).

---

See also: [Architecture](04-architecture.md) for how these pieces fit together, [Features](02-features.md) for what they deliver, and [Workflows](05-workflows.md) for the end-to-end paths through them.
