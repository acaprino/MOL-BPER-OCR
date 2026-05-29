# Tech Stack

This is a Python-only project built around LangChain for multi-LLM integration, Pillow for image processing, and Pydantic for structured output validation. It talks to cloud Vision-Language Models (OpenAI GPT-4o, Google Gemini) to extract structured data from banking screenshots, with no local database -- everything lives in memory or flat files. The desktop UIs use two different toolkits: Tkinter for the standalone GUI and PyQt6 for the edge-agent.

## Languages

| Language | Version | Where Configured |
|----------|---------|-----------------|
| Python | 3.8+ required; 3.13 observed in compiled `.pyc` files | No `pyproject.toml` or `setup.py` exists. The `.pyc` bytecodes in `__pycache__/` (e.g., `extraction/__pycache__/fields.cpython-313.pyc`) confirm the dev environment runs 3.13. |

There is no explicit Python version pin anywhere in the repository. The code uses `from __future__ import annotations` in some edge-agent modules (`edge-agent/edge_agent.py`, `edge-agent/local_extraction_client.py`, `edge-agent/llm_router.py`, `edge-agent/page_classifier.py`) for forward-compatible type hints, and Python 3.10+ union syntax (`float | None`) appears in `edge-agent/config.py` line 39 -- so 3.10 is the practical floor despite the docs claiming 3.8+.

## Frameworks

### LangChain (langchain-core, langchain-openai, langchain-google-genai)

The central abstraction for all LLM communication. `extraction/llm_factory.py` uses a factory function `create_chat_model()` that lazy-imports either `langchain_openai.ChatOpenAI` or `langchain_google_genai.ChatGoogleGenerativeAI` depending on the configured provider. The pipeline calls LangChain's `.with_structured_output()` on the resulting model to get Pydantic-validated JSON directly from the LLM response (`extraction/vlm_client.py` lines 147, 193). No version pins are specified in `requirements.txt`.

### PyQt6 (>= 6.4.0)

Drives the edge-agent desktop application. The entry point is `edge-agent/edge_agent.py`, which creates a `QApplication`, applies a Material Design theme via `qt-material`, and launches a `MainWindow` with four tabs (Cattura, Risultati, Dati, Debug). Worker threads subclass `QThread` and communicate with the UI via `pyqtSignal`. Configured in `requirements.txt` line 8.

### Tkinter (standard library)

Provides the standalone desktop GUI in `gui_app.py`. This is a simpler interface: file picker, provider/model selection, batch extraction trigger, and results treeview. No external dependency required -- it ships with Python.

### qt-material (>= 2.14)

Theming library for the PyQt6 app. Applied in `edge-agent/edge_agent.py` lines 38-43 with the `dark_cyan.xml` theme. Falls back gracefully if not installed (`except ImportError: pass`).

## Key Dependencies

### LLM Integration

| Dependency | Role | Configured In |
|-----------|------|---------------|
| `langchain-core` | Base abstractions (`BaseChatModel`, `HumanMessage`, `SystemMessage`) | `requirements.txt` line 1; used throughout `extraction/vlm_client.py`, `extraction/llm_factory.py` |
| `langchain-openai` | `ChatOpenAI` wrapper for OpenAI API | `requirements.txt` line 2; lazy-imported in `extraction/llm_factory.py` line 47 |
| `langchain-google-genai` | `ChatGoogleGenerativeAI` wrapper for Gemini API | `requirements.txt` line 3; lazy-imported in `extraction/llm_factory.py` line 57 |
| `openai` (>= 1.51.0) | Used directly (not through LangChain) by the edge-agent's `LLMPageRouter` for page classification via Vision API | `requirements.txt` line 19; `edge-agent/llm_router.py` line 23 |
| `pydantic` | Transitive via LangChain. All extraction schemas (`FieldResult`, `ExtractionResponse`, `AnchorResponse`) are Pydantic `BaseModel` subclasses. `FieldsModel` is dynamically generated via `create_model()`. | `extraction/schemas.py` |

### Image Processing

| Dependency | Role | Configured In |
|-----------|------|---------------|
| `Pillow` (>= 10.0.0) | Core image operations: resize, crop, contrast enhancement, unsharp mask, format conversion | `requirements.txt` lines 4, 12 (listed twice); `extraction/imaging.py`, `edge-agent/image_ops.py` |
| `imagehash` (>= 4.3.0) | Perceptual hashing (pHash) for frame deduplication in the capture worker. Hamming distance <= threshold means "same frame" | `requirements.txt` line 13; `edge-agent/workers/capture/bper_capture_worker.py` line 8 |

### Machine Learning (Page Classification)

| Dependency | Role | Configured In |
|-----------|------|---------------|
| `torch` | PyTorch runtime for DINOv2 ViT-S/14 feature extraction. Loaded via `torch.hub.load('facebookresearch/dinov2', 'dinov2_vits14')` | `requirements.txt` line 17; `edge-agent/page_classifier.py` line 203 |
| `torchvision` | Provides `transforms` (Resize, CenterCrop, Normalize) for image preprocessing before DINOv2 | `requirements.txt` line 18; `edge-agent/page_classifier.py` line 162 |

Both are optional. If `torch` fails to import (missing DLL, incompatible environment), the classifier enters DISABLED mode and `classify()` returns `(None, 0.0)`. The application continues to work with LLM-only routing. See `edge-agent/page_classifier.py` lines 153-170.

### Data Handling

| Dependency | Role | Configured In |
|-----------|------|---------------|
| `pandas` | CSV reading for ground truth (`pd.read_csv`), DataFrame construction for debug reports and exports (`pd.DataFrame.to_csv`) | `requirements.txt` line 5; `extraction/evaluation.py` |
| `openpyxl` (>= 3.1.2) | Excel export from the DataTableTab in the edge-agent UI | `requirements.txt` line 20 |

### Utilities

| Dependency | Role | Configured In |
|-----------|------|---------------|
| `python-dotenv` | Loads `.env` file at startup. Called in `main.py` line 7, `edge-agent/edge_agent.py` line 11, and `edge-agent/local_extraction_client.py` line 23 | `requirements.txt` line 7 |
| `mss` (>= 9.0.0) | Fast cross-platform monitor screenshot capture for the edge-agent | `requirements.txt` line 10; used by `BaseCaptureWorker` |
| `pyscreenshot` (>= 3.1) | Linux-only fallback screenshot library. Conditional install: `sys_platform == 'linux'` | `requirements.txt` line 11 |
| `requests` (>= 2.31.0) | HTTP calls in `DefaultCaptureWorker` (the generic, non-BPER capture mode) | `requirements.txt` line 14 |

### Dormant / Stubbed Dependencies

| Dependency | Status | Notes |
|-----------|--------|-------|
| `boto3` (>= 1.35.0) | Listed in `requirements.txt` line 15. `edge-agent/config.ini` has a `[minio]` section. The dataset upload path (`_maybe_upload_dataset`) is a no-op in current code. | Likely planned for S3/MinIO frame storage. |
| `keyboard` (== 0.13.5) | Pinned exactly in `requirements.txt` line 16. No active usage found in any source file. | Probably a leftover from a removed hotkey feature. |
| `streamlit` | Listed in `requirements.txt` line 6. Referenced in `CLAUDE.md` as `app.py`. No `app.py` exists in the repo. | Was likely a Streamlit web UI that was removed or never committed to this branch. |

## Infrastructure

There is no database. All state lives in Python dicts during a run.

| Component | Role | Status |
|-----------|------|--------|
| Ground truth CSV (`mnt/data/dati.csv`) | Stores expected field values per screenshot for accuracy evaluation | Gitignored (`/mnt` in `.gitignore` line 9). Must be provided externally. |
| Output JSON (`mnt/data/poc_outputs_improved.json`) | Batch extraction results | Written by `extraction/cli.py` line 339 |
| Debug CSV (`mnt/data/poc_debug_improved.csv`) | Per-field accuracy breakdown | Written by `extraction/cli.py` line 346 |
| MinIO / S3 | Object storage for captured frames | Configured in `edge-agent/config.ini` lines 12-16 (endpoint `localhost:9000`). Upload code is stubbed -- not active. |
| OpenAI API | Cloud LLM for extraction + page routing | Accessed via LangChain (`langchain-openai`) and directly (`openai` SDK) |
| Google Gemini API | Alternative cloud LLM for extraction | Accessed via LangChain (`langchain-google-genai`) |
| DINOv2 (Facebook Research) | Pre-trained vision model downloaded on first run via `torch.hub` | `edge-agent/page_classifier.py` line 203. Cached locally by PyTorch Hub. |

## Dev Tools

| Tool | Purpose | Configuration |
|------|---------|--------------|
| PyInstaller | Packaging `gui_app.py` as a standalone `.exe` | Documented in `README.md`. No `.spec` file is committed (`.gitignore` excludes `*.spec`). |

Notably absent:

- **No linter or formatter configuration.** No `ruff.toml`, `.flake8`, `pyproject.toml [tool.black]`, or similar.
- **No test framework.** No `pytest.ini`, `tests/` directory, or test files anywhere in the repo.
- **No CI/CD pipeline.** No `.github/workflows/`, `Jenkinsfile`, or equivalent.
- **No type checking config.** No `mypy.ini` or `py.typed` markers, despite heavy use of type annotations.

## Dependency Management

Dependencies are managed through a single `requirements.txt` at the project root (`D:\Projects\poc-data-extraction\requirements.txt`). There is no `pyproject.toml`, `setup.py`, `setup.cfg`, or `Pipfile`.

**Pinning strategy:** Most dependencies use minimal or no version constraints. Only a few specify minimums (e.g., `PyQt6>=6.4.0`, `openai>=1.51.0`). One dependency is hard-pinned: `keyboard==0.13.5`. The LangChain packages (`langchain-core`, `langchain-openai`, `langchain-google-genai`) and `pillow` (at the top of the file) have no version constraint at all, while `Pillow>=10.0.0` appears again lower in the file as a duplicate with a floor.

**No lockfile exists.** There is no `requirements.lock`, `pip-compile` output, or `poetry.lock`. Builds are not reproducible across environments without manual intervention.

**Virtual environment:** A `.venv/` directory is present (gitignored). Standard `pip install -r requirements.txt` is the documented setup path.

**Edge-agent dependencies are combined** into the same `requirements.txt` as the extraction core. There is no separation between the CLI tool's needs (LangChain, pandas) and the desktop agent's needs (PyQt6, torch, mss). Installing everything is required regardless of which interface you plan to use.

## See Also

- [Architecture](04-architecture.md) -- how these packages wire together at runtime and which modules talk to which APIs
- [Project Anatomy](09-project-anatomy.md) -- the complete catalog of configuration files and environment variables these dependencies consume
- [Getting Started](07-getting-started.md) -- installation walkthrough and the minimal subset you need for CLI-only work
- [Open Questions](08-open-questions.md) -- unresolved issues around `boto3`, `keyboard`, and `streamlit` dependencies with no active callers
