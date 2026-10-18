# Scoped fix: restore the empty `.venv` and re-run the full suite

- Date: 2026-10-18. HEAD: `d9462a46b75a5cb50e58ad6c6ebb30ddec85b807` (unchanged).
- Scope: local environment repair (`.venv` is gitignored) plus this X-ray record. **No source, test,
  configuration, documentation, model or dataset file was changed.**
- Motivation: the previous two scoped reports (`../2026-10-18-plan-resilience/report.md`,
  `../2026-10-18-plan-corrections/report.md`) ended with the suite interrupted by **16 collection
  errors** caused by missing `PyQt6` and `langchain_core`. Per AGENTS.md test-suite rule 6 a failing
  suite must not be left failing, and per rule 7 the suite must be re-run before claiming done.

## Root cause

`.venv` existed but was **completely empty** (`site-packages` contained only `__pycache__`), built by
`uv` from base interpreter `cpython-3.11.15` (`.venv/pyvenv.cfg`). The stray untracked `uv.lock`
indicates a `uv` sync ran against `pyproject.toml`, which declares **no dependencies** (pytest config
only), so nothing was installed. The 16 collection errors were environmental, not code regressions:
`src/extraction/__init__.py` eagerly imports `llm_factory` (`langchain_core`) and four edge-agent
test modules import `PyQt6` directly.

## Repair

- Installed the project's declared dependencies into the existing `.venv`:
  `uv pip install --python .venv\Scripts\python.exe -r requirements.txt -r requirements-dev.txt`
  (exit 0; second run idempotent, "Checked 22 packages").
- Notable resolved versions: `torch 2.14.1`, `transformers 5.20.1`, `tokenizers 0.23.3`,
  `PyQt6` and `langchain-core` present (import checks all `True`).
- `rapidocr` and `onnxruntime` are **not** in `requirements.txt`; they remain absent from `.venv`
  (relevant only to the `docs/next-ver-plan.md` benchmark phase, which will need them added
  explicitly before Phase 1 runs).
- Interpreter note: `.venv` runs Python **3.11.15**, while `run_edge_agent.bat` prefers 3.13 then
  3.12. The bat self-heals only a *broken* venv, and this one works (full suite green), so it was
  kept. If the packaged runtime must match the documented target, rebuild with
  `py -3.13 -m venv .venv` and reinstall; no test currently requires 3.12+.
- The untracked `uv.lock` was left untouched (unrelated artifact, as recorded previously).

## Newly executed verification (fresh, on this working tree)

| Check | Command | Result |
|---|---|---|
| Full suite (incl. 18 DINOv2 `slow` cases) | `.venv\Scripts\python.exe -m pytest tests` | **439 passed, 3 warnings in 56.88s** (exit 0) — log: `pytest-full.txt` |
| Fast lane | `.venv\Scripts\python.exe tools\check.py` | **421 passed, 18 deselected in 43.28s** (exit 0) — log: `pytest-fast.txt` |
| Collection count | `pytest tests --collect-only -q` | **439 tests collected, 0 errors** — log: `collect-count.txt` |

The 3 warnings are the known `xFormers is not available` notices from DINOv2 (torch hub cache),
harmless on CPU. Previous run: 183 collected / 16 collection errors (exit 2).

## Findings rechecked against the working tree

- Previous finding "suite interrupted by 16 collection errors (PyQt6, langchain_core)": **resolved**
  by the environment repair above; no test was weakened, skipped or changed to achieve green
  (AGENTS.md test-suite rule 3 respected — the suite now runs, it was never edited).
- `docs/next-ver-plan.md` SHA-256 re-verified unchanged:
  `0a03e224de948f090f70ebfa05894702e914274c28fa04b3f20330d696789084` (matches the corrections run).
- Untracked working-tree state unchanged except this X-ray run folder: `docs/next-ver-plan.md`,
  `.codebase-xray/`, `uv.lock` (untouched).
- All documentation findings R1–R12 and the resilience gates G6/G7 from the previous two reports
  remain **open as plan requirements**; this run makes no runtime, benchmark or training claim.
  A suite that collects and passes is not evidence for G1–G8.

## Not executed here

No OCR/model benchmark, training, fault injection, soak, app startup or packaged-app measurement was
run. G1–G8 qualification remains pending per `docs/next-ver-plan.md`.
