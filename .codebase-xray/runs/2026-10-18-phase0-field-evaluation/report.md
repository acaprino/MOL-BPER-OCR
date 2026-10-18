# Phase 0, step 3 (first part): field-value evaluation entry

- Date: 2026-10-18. HEAD: `5b429754bb549b1bf0e875b86a9280a2010a955d`. Changes below are uncommitted at the time of this record; the unrelated untracked `uv.lock` was left untouched.
- Scope: the common evaluation entry required by `docs/next-ver-plan.md` section 5.2 before any B1/B3 benchmark. Chosen by me as the next step after the user asked me to decide on my own; it is the step the plan puts first among the remaining Phase 0 work.
- Previous scoped state: `analysis-state-before.json` (the `2026-10-18-phase0-baseline` record).

## Change

`src/training/evaluation.py` (before: `evaluation-before.py`, SHA-256 `b65eec62...`; full diff with tests and docs in `code.diff`):

- `evaluate_field_values(examples, predictions)`: per screen `{"fields": {field: text or None}, "abstained": [field, ...]}`. Same `classify_value()` comparator, same records and summaries as the role path, OCR availability from the reviewed labels and alignment only. Absent and abstained fields score as absent values. Rejects unknown screens, missing `fields`, unexpected keys, fields outside the 45 `FIELD_KEYS` (read through `training.schema.vocabulary()`), non-string values, empty strings, and fields both predicted and abstained. Word metrics are `None`.
- Shared helpers `_oracle()`, `_record()`, `_field_report()`; `evaluate_predictions()` now builds its records and summaries through them.
- Both entry points add `complete` (false when a screen has no outcome) and an `abstained` count per summary and per field (always 0 on the role path); records carry `abstained`.
- Docs: `docs/next-ver-plan.md` section 5.2, `src/training/README.md`, the `evaluation.py` line of `CLAUDE.md`.

The sealed bundle manifest still records `evaluation.py` as `b65eec62...`: it describes the code at build time; `validate_reviewed_dataset()` does not check code hashes.

## Test-first record

18 new tests in `tests/test_training_evaluation.py` were written before the implementation. With the function stubbed (`raise NotImplementedError`) they failed for the expected reasons: 16 `NotImplementedError`, 2 `KeyError: 'complete'` on the role path; the 36 existing tests passed. After the implementation: 54 passed.

## Findings rechecked against the working tree

| Finding | Evidence | Status |
|---|---|---|
| R24: no field-value evaluation entry (plan section 5.2; earlier R6) | `evaluate_field_values()` added with schema checks and abstentions. | Resolved. |
| R25: the refactor could change role-path results | `check_field_evaluation.py` on the current B0 predictions: the role-path report equals the field metrics written before the change once the two new keys are removed, on validation and test. | Verified, no change. |
| R26: the field path must score like the role path | Same script: fields decoded from the B0 roles, fed to `evaluate_field_values()`, give identical records and `by_field` summaries (validation 124/146, test 144/192). Negative control `--perturb` (one value rewritten) fails as expected: 123/146 and 143/192, exit 1. | Verified. |

## Newly executed verification

- `check_field_evaluation.py .`: PASS, exit 0 (`check-field-evaluation.txt`); `--perturb`: FAIL, exit 1 (`check-field-evaluation-negative.txt`).
- `.venv\Scripts\python.exe -m pytest tests`, Python 3.11.15: exit code **0**, **457 passed, 3 warnings in 38.65s** (`pytest-full.txt`, fresh run; 439 before plus 18 new).
- Not done yet in step 3: the reproducible runner for complete OCR caches with manifests and resumable partial outputs; A5 correction metadata (`scale`, `words_rewritten` in `src/training/dataset.py`) is deferred to A5.
- Execution note: a negative-control attempt that staged a copy of the repository with `ln -s` produced a 2.3 GB deep copy of `data/` in the scratchpad (Git Bash copies instead of linking); it was deleted and the repository `data/` was verified intact (`examples.json` hash unchanged).
- `source-manifest.json` records hashes.
