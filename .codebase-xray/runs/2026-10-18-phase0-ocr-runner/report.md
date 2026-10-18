# Phase 0, steps 3 and 4: OCR runner and G8 collection plan

- Date: 2026-10-18. HEAD: `a70ac085980fa505455dedb76a46617fc9a8df5b`. Changes below are uncommitted at the time of this record; the unrelated untracked `uv.lock` was left untouched. The Phase 1 runs started with this runner live in `../2026-10-18-phase1-ocr/` and are not part of this record.
- Scope: the rest of Phase 0 step 3 (reproducible runner for complete OCR caches) and step 4 (G8 plan) of `docs/next-ver-plan.md`, chosen in plan order after the user asked me to decide on my own.
- Previous scoped state: `analysis-state-before.json` (the `2026-10-18-phase0-field-evaluation` record).

## Changes

| Path | Change |
|---|---|
| `src/training/ocr_runner.py` | New. `run_ocr(config, profile, screens, out_dir, engine_factory=None)`: configurations `A0`..`A4` (plan section 3.1), profiles `pc4` (4/1 threads) and `vdi2` (2/1); refuses a screenshot whose bytes differ from the reviewed `image_sha256`; one JSON per screen written atomically as soon as it is read; a failing screen is recorded and does not stop the others; `cache.json` (the format `build_dataset()` reads) exists only when every screen has a result, and the manifest binds its SHA-256; a directory refuses another configuration, profile, screen set or engine build (model hashes, versions); a warm-up read is excluded from the stored results; manifest records engine load, warm-up, per-session peak working set and mean/median/p95/max seconds. `_rapidocr_engine()` resolves the model files RapidOCR loads, checks them against the catalog SHA-256 and records them. `ocr_selection_metrics(examples)`: OCR non-null availability, subject NDG and `rapporto` availability, 6-read-as-8 counts per split and per practice, on train and validation only. `report(run_dir, workbook, screenshots)`: refuses a partial or edited run, builds the derived dataset, writes `ocr_selection.json`. CLI `python -m training.ocr_runner run|report`. |
| `tests/test_training_ocr_runner.py` | New, 22 tests; the RapidOCR engine is faked at its boundary (absent from the test environment). |
| `requirements-ocr.txt` | New: exact pins of the `.venv-ocr` environment (rapidocr 3.9.2, onnxruntime 1.30.0, openpyxl 3.1.5 and resolved dependencies, Python 3.13.14). |
| `docs/next-ver-plan.md` | Section 5.2: the runner exists. New section 5.4: G8 collection plan. Phase 0 step 4 points to 5.4. SHA-256 `d0423bcd...`; `plan.diff` against the plan of `a70ac08`. |
| `src/training/README.md`, `CLAUDE.md` | Runner usage (Italian guide) and module/dependency description (`docs.diff`). |

## Test-first record

The first 20 tests failed against a stub with 20 `NotImplementedError`; two `report()` guard tests added next failed the same way (22). After the implementation: 22 passed.

## Findings rechecked against the working tree

| Finding | Evidence | Status |
|---|---|---|
| R27: no reproducible runner for complete OCR caches (plan section 7 item 1) | `src/training/ocr_runner.py` and its tests. | Resolved. |
| R28: the runner must reproduce A0 | `check_a0_runner.py` on `../2026-10-18-phase1-ocr/A0-pc4`: **12/12** (`check-a0-runner.txt`). 113/113 screens identical to `data/training/ocr-cache/rapid_v6_small_1x.json` in texts, scores and boxes; derived `alignment_report.csv` byte-identical to the bundle's; selection metrics equal the hand-derived counts (OCR non-null train 562/613, val 124/133; subject NDG 16/21 and 5/5; rapporto 23/24 and 5/5; 6->8 train 10, val 1, per practice as in plan section 1.2); historical test practices absent. Model SHA-256: det `090f04ab...`, rec `6f327246...` (both equal to the RapidOCR catalog), cls `e47acedf...`. The run's `cache.json` hash differs from the bundle cache only through the stored seconds. | Verified. |
| R29: G8 has no collection plan (Phase 0 step 4) | Plan section 5.4: inventory, minimum need (3 new practices per uncovered field: 1 extended validation, 2 confirmation), deterministic assignment rule on reviewed-truth presence only, isolation as `audit_splits()`, sealing, request to the screenshot provider. `check_g8_inventory.py` **9/9** (`check-g8-inventory.txt`); negative control on the plan before this run 7/9. | Plan written; collecting and reviewing the practices is pending and outside this repository. |
| R30: lotto 2026-08-21 exposure | No lotto practice id appears in training, review, prompts, sources, docs or earlier X-ray files; `tests/fixtures/frames/no-tooltip/manifest.json` cites `51788077`, `51800301`, `52032077` (page-classifier fixtures, commit `7b70bf7`). Recorded in section 5.4: usable for field metrics, not as a blind page-classifier test. | Recorded. |

## Measurements and caveats

- A0 through the runner, `pc4`: 113 screens, mean 6.14 s, median 5.88 s, p95 8.76 s, max 11.19 s per screen (PNG decoding included, warm-up and the 0.93 s engine load excluded); peak working set 612,909,056 bytes for the OCR process alone. Intel64 Family 6 Model 170, 22 logical CPUs, Windows 11 desktop with other applications running: these are comparison figures, not G6 measurements.
- The full suite of this record ran from about 11:39:54Z to 11:40:35Z while A1 was reading screens, so a few A1 timings carry that extra load; the Phase 1 record must say so.
- RapidOCR downloads its model files on first use into `.venv-ocr/Lib/site-packages/rapidocr/models` and the runner verifies them against the catalog SHA-256. The plan forbids implicit downloads in the distributed runtime: a packaged engine must ship the files.
- A5 correction metadata (`scale`, `words_rewritten` hardcoded in `src/training/dataset.py:248`) is deferred to A5.

## Newly executed verification

- `check_a0_runner.py`: 12/12, exit 0. `check_g8_inventory.py`: 9/9, exit 0; negative control 7/9.
- `.venv\Scripts\python.exe -m pytest tests`, Python 3.11.15: exit code **0**, **479 passed, 3 warnings in 41.02s** (`pytest-full.txt`, fresh run after all edits; 457 before plus 22 new).
- `source-manifest.json` records hashes.
