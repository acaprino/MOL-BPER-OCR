# Scoped review: selection power of the next-version plan

- Date: 2026-10-18. HEAD: `d9462a46b75a5cb50e58ad6c6ebb30ddec85b807`.
- Scope: `docs/next-ver-plan.md` and this X-ray record only. No application, test, dependency, configuration, model or dataset changes.
- Final plan SHA-256: `a619655c487cf765d6add426bc106d33e5c9a17b6f126f91e9c55724ecb39d3c`.
- Before snapshot: `plan-before.md`, SHA-256 `0a03e224de948f090f70ebfa05894702e914274c28fa04b3f20330d696789084`, identical to the final plan recorded by `../2026-10-18-plan-corrections/report.md` (no change in between).
- Previous scoped state: `analysis-state-before.json` (the `2026-10-18-venv-dependencies` record). Earlier reports and their test results remain history.
- Intake: an external review of the corrected plan, pasted by the user. Each claim was rechecked against `data/training/ground-truth-v3.1/alignment_report.csv` and `src/training/evaluation.py` before any edit. The plan and X-ray are still untracked; the unrelated untracked `uv.lock` was left untouched.

## Review claims confirmed without plan changes

- `evaluate_predictions()` (`src/training/evaluation.py:227-244`) decodes fields only from per-word roles via `decode_fields()` (line 235). Section 5.2 already requires a field-value entry point before B1/B3.
- Current alignment CSV OCR availability on non-null values is validation 124/133 and test 178/183, against the saved run's 121/133 and 170/183. Already recorded as a snapshot discrepancy by the previous report.
- G6 and G7 are adoption gates, not ranking criteria; a green suite does not verify them.

## Findings rechecked against the working tree

| Finding | Verified evidence and correction | Status |
|---|---|---|
| R13: validation G3 cannot rank OCR engines | Validation subject NDG 5/5 and rapporto 5/5 are already saturated. Pretrained OCR engines are not fitted on train practices, so train is legitimate selection data for OCR-only metrics. G3 row and Phase 1 step 1-2 now rank A0-A4 on G1, G3 and per-practice 6→8 counts over train plus validation (10 practices); validation G1/G3 stay non-regression gates. Caveat recorded: B0 is LiLT trained on A0 output of train, so the admission does not extend to G4/G5 measured with B0. Section 5.1 train use updated. | Resolved in plan. |
| R14: the 6→8 signal is absent from selection | Partly incorrect in the review. Digit-only comparison gives train 10 observations in 4 practices, 8 distinct values (5 subject NDG, 1 rapporto, `scadenza` `361 mesi` read `381 mesi` on two screens each of 52068422 and 52135039); the review's six counted only NDG and rapporto. Validation has 1 case, not 0: `52126316__GestioneFidi_Tooltip1` `importo_euro` `160.000` read `180,000` (`ignored_ocr_mismatch`). Test has 3. Section 1.2 records the current distribution. | Resolved in plan. |
| R15: A5 cannot be certified on its development data | The review's proposed ban ("no A5 promotion if validation has no case") would not trigger, since one case exists, and one case certifies nothing. Validation can still measure regressions: correctly read Fidi values and subject NDGs contain 15 digits `6` and 12 digits `8` (screen repetitions counted). Section 3.1 now requires per-practice train reporting, leave-one-practice-out when A5 has tunable thresholds, validation counts of wrong corrections and abstentions, promotion only with zero wrong corrections, and G8 confirmation practices containing subject NDGs and rapporti with digit `6`, chosen on reviewed truth rather than OCR errors. | Resolved in plan; A5 implementation pending. |
| R16: G5 micro accuracy over repeated screens | Validation Fidi has 25 non-null observations but 10 unique values (51659595: 5 values on 2 screens; 52126316: 5 values on 3). One wrong value gives 22/25 (fail) in 52126316 and 23/25 (pass) in 51659595. Section 4 now reports per-unique-value and per-practice counts next to per-screen counts for G4 and G5. | Resolved in plan. |
| R17: G4/G5 differences within sampling noise decide the choice | 129/146 vs 135/146 is six fields over repeated observations of two practices. Section 4 now states that, when two candidates both pass a gate, a difference that hinges on one repeated value does not decide; ties go to the simpler or cheaper candidate. | Resolved in plan. |
| R18: the figure motivating A1-A5 comes from the historical snapshot | Section 1.2 counts 9 unavailable `rapporto` in the saved test report; the current CSV has 1 (11/12). Section 1.2 now says so and defers the defect's weight on the current corpus to Phase 0. | Resolved in plan; Phase 0 remeasurement pending. |

Not verified: whether the validation `importo_euro` tooltip uses the 7-pixel font that `pixel_six_eight.py` checks. No screenshot was inspected.

## Newly executed verification

- `python -I check_selection_power.py <alignment_report.csv> plan-before.md docs/next-ver-plan.md`: **23/23 checks passed**, exit 0 (`checks.txt`). It recomputes every figure added to the plan from the CSV, plus document checks (no em dash added, balanced code fences, no conflict markers, no trailing whitespace on new lines, Phase 1 validation-only phrase removed). Negative control: passing `plan-before.md` as the edited plan yields 22/23, with the phrase check failing as expected.
- `.venv\Scripts\python.exe -m pytest tests`, Python 3.11.15: exit code **0**, **439 passed, 3 warnings in 63.85s** (`pytest-full.txt`). The change is documentation-only; the run records the suite state, it is not evidence for any gate.
- The fast lane was not re-executed; its last result belongs to `../2026-10-18-venv-dependencies/`.
- No OCR/model benchmark, A5 prototype, training, screenshot inspection, fault injection, soak or packaged-app measurement was executed. G1-G8 candidate qualification is not claimed.
- Pre-existing em dashes in the plan's title, date and headings were left unchanged (count unchanged); the added text contains none.
- `source-manifest.json` records source hashes; `plan.diff` records the before/after document change.
