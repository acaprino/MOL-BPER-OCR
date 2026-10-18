# Scoped review: correction of the next-version plan

- Date: 2026-10-18. HEAD: `d9462a46b75a5cb50e58ad6c6ebb30ddec85b807`.
- Scope: `docs/next-ver-plan.md` and this X-ray record only. No application, test, dependency, configuration, model or dataset changes.
- Final plan SHA-256: `0a03e224de948f090f70ebfa05894702e914274c28fa04b3f20330d696789084`.
- Before snapshot: `plan-before.md`, SHA-256 `14bdb6c07cd4ba7a4e159cdd8eadce86acf8d051aced91f2287481c31e767b8f`.
- Previous scoped state: `analysis-state-before.json`; previous report remains at `../2026-10-18-plan-resilience/report.md` and its test results are historical.
- The plan and X-ray were untracked at intake. The unrelated untracked `uv.lock` was left untouched. Existing signed codebase-map state and history were not changed.

## Documentation findings rechecked against the working tree

| Finding | Verified evidence and correction | Status |
|---|---|---|
| R1: selection consumes held-out test results | Plan sections 4, 5.1 and 6 now select and decide phases on train/validation only. Existing test practices are explicitly an exposed regression population. Fresh confirmation is required after one candidate is frozen. | Resolved in plan. |
| R2: 45-field coverage is unsupported | `coverage.json` and both saved field reports cover only 30 fields positively in validation/test. Section 1.3 and G8 explicitly require additional practice-separated validation and confirmation coverage, with at least two confirmation practices per field. | Resolved in plan; collecting new data remains required. |
| R3: G3 population omits subject occurrences | Current alignment CSV has 33 non-null subject NDG occurrences (train 21, val 5, test 7), 26 exact. Rapporto has 41 occurrences, 39 exact. G3 now uses those populations, with separate validation and frozen-regression criteria. | Resolved in plan. |
| R4: per-field diagnosis disagrees with saved report | Corrected missing/wrong counts for importo_euro, n_fido, scadenza and tipo_op; rapporto is 3/12, ruolo_1 0/2, ruolo_2 1/2. Rapporto word precision is 8/(8+37)=0.1778. Lexical overfitting and table-structure explanations are hypotheses. | Resolved in plan. |
| R5: 38-screen cache cannot pass build_dataset | `src/training/dataset.py:193-197` checks the complete workbook screen set and reviewed practices. The revised runner must create complete 113-screen caches and restrict selection reports to validation. | Resolved in plan; runner implementation pending. |
| R6: field dictionaries cannot enter role evaluator | `src/training/evaluation.py:173-182,227-276` consumes per-word roles and returns `overall.counts`, `by_field` and `by_split`. Section 5.2 requires a shared field-value evaluation entry point before B1/B3, preserving comparators, denominator and parser choices. | Resolved in plan; API extension pending. |
| R7: arithmetic and group definitions are ambiguous | G1 uses exact ceilings (131/133 validation; 181/183 historical). G2 separates <=6 mismatches from >=890 complete rows. G4 uses 129/146 and 135/146. G5 explicitly uses non-null micro accuracy: Fidi 23/25, Soggetti 14/15 validation, with nulls reported separately. | Resolved in plan. |
| R8: Pixel Guard result is overclaimed | Historical helper checks supplied text/coordinates, abstains and only covers 7px font. Section 1.2 records 89/99 checked values, 149 checked digits, 10 abstentions. A5 requires automatic localization, original/corrected evidence, coverage and regressions; re-OCR is separately timed. | Resolved in plan; automatic correction pending. |
| R9: integrated resource qualification is missing | G6 now measures the application with queues, resident models and results. ONNX and PyTorch thread limits share a declared CPU budget; actual PC/VDI checks precede adoption. Phase gates no longer certify G6 from OCR-only timing. | Resolved in plan; measurement pending. |
| R10: v3.2 path conflicts with validator | `src/training/model.py:28-29` accepts v3.1 only; dataset builder hardcodes v3.1 and unmodified OCR metadata. Sections 5.2 and 6 require guarded version/provenance support with regressions before creating a v3.2 bundle. | Resolved in plan; contract changes pending. |
| R11: license generalizations | Section 2 now cites primary sources, separates code/weight/component licenses, records LiLT MIT metadata, removes blanket CRAFT noncommercial/OmniParser AGPL assertions, and requires artifact-specific terms and notices. | Resolved in plan; package inventory remains a prerequisite. |
| R12: split totals and snapshot provenance | Coverage/current corpus yields 670 train, 146 val, 192 test rows. Saved run availability differs from current examples/alignment (details below). Section 1.1 and Phase 0 distinguish snapshots and require reconciliation before experiments. | Resolved in plan; source reconciliation pending. |

## Source snapshot discrepancy

Saved run non-null OCR availability is validation 121/133 and test 170/183.
Current `examples.json` availability aggregates are validation 124/133 and test
178/183. Expected values match; differences concern one validation and eight test
rapporto observations. Current `alignment_report.csv` strict expected/OCR-text
comparison yields rapporto 5/5 validation and 11/12 test, whereas saved run
availability is 4/5 and 3/12. These are different artifact snapshots; no saved
report or dataset was overwritten to make them agree. The plan now explicitly
requires a new reproducible baseline instead of treating these as one observation.

Saved validation/test G5 non-null baselines are Fidi 13/25 and 20/60, Soggetti
10/15 and 10/21. Subject nulls are 9 and 3, all correct, with zero hallucinations.
These aggregate checks did not train models, tune rules or inspect screenshots.

## Preserved resilience requirement and runtime interfaces

G7 and section 5.3 retain bounded queues/retention, terminal job outcomes, real
hang recovery, practice integrity, offline clean-cache startup, stop/restart,
export failures, and an eight-hour / 1,000-frame soak for each CPU profile. Runtime
gaps recorded in the previous report remain open. Ingest, capture ordering,
normalize_ndg, pick_best, consolidation and export interfaces were not changed.
No runtime guarantee is claimed by this documentation correction.

## Newly executed verification

- Ten document/data checks passed: split totals, saved validation baseline, saved test baseline, exact gate ceilings, G1-G8 presence, balanced code fences, valid JSON example, existing relative links, absence of conflict markers, and whitespace check.
- An independent read-only reviewer checked current plan consistency, historical counts, all-field coverage, test isolation, API/version contracts and G6/G7 criteria. It reported no remaining actionable errors. No reviewer changed files or ran training.
- `python -m pytest tests`, Python 3.13.14: exit code **2**; **183 items collected / 16 collection errors**; final summary **16 errors in 2.25s**. Missing packages are `PyQt6` and `langchain_core`. Fresh complete output is in `pytest.txt` in this directory. Dependencies and tests were left unchanged.
- No OCR/model benchmark, training, new candidate evaluation, fault injection, soak, app startup or packaged-app resource measurement was executed. G1-G8 candidate qualification is not claimed.
- `source-manifest.json` records source hashes; `plan.diff` records the before/after document change. This is a current scoped analysis, not a full codebase audit or a relabelled historical run.
