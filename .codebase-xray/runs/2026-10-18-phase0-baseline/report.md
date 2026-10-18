# Phase 0: plan correction, OCR cache, A0 reproduction and B0 retrained on the current bundle

- Date: 2026-10-18. HEAD: `0fd7c07aba56f46da6060132fba83e4b76756b2f`. All changes below are uncommitted; the unrelated untracked `uv.lock` was left untouched.
- Scope: the four Phase 0 actions the user approved after `../2026-10-18-phase0-reconciliation/report.md`: correct plan sections 1.1/1.2, restore the OCR cache, set up the OCR environment and rerun A0, retrain LiLT on the current bundle on Modal.
- Previous scoped state: `analysis-state-before.json` (the `2026-10-18-phase0-reconciliation` record).

## Files changed or added

| Path | Change |
|---|---|
| `docs/next-ver-plan.md` | Sections 1.1, 1.2, G1 baseline and the A5 note use the reconciled figures; after the user's approval of the follow-up, B0 (section 3.2) names the current-bundle run and the G4/G5 baseline column cites it, keeping the 2026-10-16 figures for comparison. SHA-256 `ec8941a7...` (before: `plan-before.md`, `a619655c...`; diff in `plan.diff`). |
| `data/training/ocr-cache/rapid_v6_small_1x.json` | New. The 113-screen cache restored byte for byte from git blob `803ef962...` (`d939ea5`), SHA-256 `e261c05b...` as in the bundle manifest. |
| `data/README.md`, `src/training/README.md` | Document the restored cache path, the manifest's stale path, rebuild reproducibility and the new run. |
| `.gitignore` | Adds `.venv-ocr/`. |
| `data/training/runs/lilt-v3.1-20261018-current-bundle/` | New run artifacts (same layout as the 2026-10-16 run); `cpu_model/model.safetensors` (1,134,412,212 bytes, SHA-256 `36849777...`) is gitignored like the previous weights. `validation_field_metrics.json` and `test_field_metrics.json` were written locally with the current evaluator. |

The sealed bundle `data/training/ground-truth-v3.1/` and the 2026-10-16 run were not modified.

## Findings rechecked against the working tree

| Finding | Evidence | Status |
|---|---|---|
| R19: plan section 1.2 attributes the 9 unavailable test `rapporto` to 6->8 on 9 screens of `52060489` | Reconciliation showed 6 are `51531667` stage B errors and 2 were already correct; `52060489` has 4 `GestioneFidi*` screens. Plan corrected; `check_plan_reconciled.py` 28/28 (negative control on the unedited plan 26/28). | Resolved in plan. |
| R20: OCR cache path in the manifest no longer exists | Restored to `data/training/ocr-cache/`; the sealed manifest keeps the old path, documented in both READMEs. | Resolved; manifest path left as history. |
| R21: the bundle is not byte-reproducible | Rebuild with the current code, workbook (`ba537eff...`) and restored cache: `roles.json`, `coverage.json`, `ground_truth.csv`, `alignment_report.csv` identical; `examples.json` identical in ids, labels, word texts and y coordinates, but 1,567 x coordinates differ: 1,565 by at most 1e-6 and 2 by 3 px (word `(?)/%` x1 1050 vs 1053, `fitted=True`, label `O`, on `51185037__GestioneFidi` word 275 and `52135039__GestioneFidi_Tooltip1` word 271). Content fingerprint `beca470c...` vs `469c26d1...` (`rebuild-compare.txt`, `rebuild-manifest.json`). Cause not investigated; the current `.venv` has numpy 2.2.6 and pillow 12.3.0, the original build environment is not recorded. | Open. The committed bundle is used unchanged. |
| R22: A0 reproduction | `ocr_local_rapid.py` (historic script, unchanged, from `d939ea5`) in `.venv-ocr` (Python 3.13.14, rapidocr 3.9.2, onnxruntime 1.30.0, opencv-python 5.0.0.93, numpy 2.5.4; `ocr-venv-freeze.txt`) on the 113 screenshots, each copied from `data/pratiche/` after matching `image_sha256`: **113/113 screens identical** to the cache in token texts, order, scores and boxes (max delta 0). Time per screen, first excluded: mean 6.79 s, max 13.35 s (historic 7.69 / 12.19). | Resolved: A0 is reproducible. Timing is not a G6 measurement (no pc4/vdi2 profile, no warm-up protocol, concurrent desktop load). |
| R23: B0 needed a model trained on the current bundle | New run below. | Resolved as a baseline; G4/G5 not met. |

## B0 baseline: both LiLT runs, current evaluator, current examples

`compare_lilt_runs.py` -> `lilt-compare.json`, `lilt-compare.txt`. Validation is the selection population; the test is a seen regression set and did not influence any choice here.

| Validation (146 fields, 2 practices) | 2026-10-16 | 2026-10-18 current bundle | Gate minimum |
|---|---:|---:|---:|
| Strict, including correct nulls (G4) | 115/146 | **124/146** | 129 (min), 135 (target) |
| Non-null correct | 102/133 | 115/133 | |
| Unique (practice, field, value) all correct | 39/61 | 49/61 | |
| Fidi non-null (G5), unique values | 13/25, 3/10 | **19/25**, 5/10 | 23 |
| Soggetti non-null (G5), unique values | 10/15, 10/15 | **15/15**, 15/15 | 14 |
| Per practice `51659595` / `52126316` | 55/72, 60/74 | **52/72**, 72/74 | |
| Hallucinated | 0 | 4 | |
| OCR available, non-null | 124/133 | 124/133 | 131 (G1) |

| Test, regression only (192 fields) | 2026-10-16 | 2026-10-18 |
|---|---:|---:|
| Strict | 127/192 | 144/192 |
| Non-null correct | 119/183 | 135/183 |
| Fidi non-null, unique values | 20/60, 4/14 | 25/60, 4/14 |
| Soggetti non-null | 10/21 | 19/21 |
| Per practice `51531667` / `52060489` | 56/107, 71/85 | 72/107, 72/85 |

Observations:
- The validation gain is concentrated in `52126316` (60 -> 72 of 74); `51659595` loses 3 fields net. New errors there: `fase` hallucinated as `APP` on 4 `Elenco*` screens while `stato` `APP` becomes missing (a stato/fase role swap), `51659595__GestioneFidi_Tooltip2` `rapporto` truncated to `034 0021 0017` and `importo_euro` read as `05585799 135.800` (column bleed), `denominazione` `TABACCHI LANDOGNA CORRADO` and `LANDOGNA CORRADO 3MB`.
- Per the plan's selection-power rule, the per-practice split shows how much one practice drives the aggregate: this is a baseline, not a winner.
- The two runs differ in training alignment **and** in checkpoint rule (old: validation word micro F1 only; new: validation whole-field accuracy, then non-note word F1, then micro F1), so the gain cannot be attributed to the alignment fix alone. Same seed (7), settings and packages (torch 2.12.0+cu130, transformers 5.15.0).
- Best epoch is 8, the bound enforced by `src/training/modal_train.py` (`1 <= epochs <= 8`); validation field accuracy was still rising (0.8425 at epochs 6-7, 0.8493 at 8). Whether more epochs help was not tested.
- On the current corpus G4 and G5 Fidi fail with B0; G5 Soggetti passes. Stage B remains the larger gap (validation: 124 OCR-available non-null values, 115 correct).

## Execution notes

- Modal: the first attempt failed before creating anything (`Could not connect to the Modal server.`) because the session exports `HTTPS_PROXY=http://127.0.0.1:18789`, which the Modal client cannot traverse; plain HTTPS to `api.modal.com` worked. The second attempt ran the same command with `HTTPS_PROXY`/`HTTP_PROXY` unset and the shell sandbox disabled for that command only (`modal-train.log`). App `ap-eqOubPrJTs5jDjHMHwdsaP`, remote directory `model_v3_1_5bd3c5a3b65e366a` on volume `bper-lilt-spike`, one L4, remote wall 382.3 s, training 329.5 s, no retries. Per `modal_train.py`, only OCR words, boxes, labels and manifests were sent; screenshots and the workbook stayed local.
- The first bundle rebuild raised `MemoryError` in `rgb.tobytes()` (`src/training/dataset.py:207`) with 6.0 GB of commit available; the identical retry succeeded. Known machine condition, not a code defect.

## Newly executed verification

- `check_plan_reconciled.py`: 28/28, exit 0 (`checks-plan.txt`), including the B0 figures cited in the G4/G5 rows and the A0 identity; negative control on the unedited plan 26/28.
- `compare_rebuild.py`, `compare_a0.py`, `compare_lilt_runs.py`: outputs above; each stops on id or word-count mismatch where relevant.
- `.venv\Scripts\python.exe -m pytest tests`, Python 3.11.15: exit code **0**, **439 passed, 3 warnings in 34.59s** (`pytest-full.txt`, fresh run). No source or test changed.
- Not executed: Phase 0 step 3 (runner, common field-value evaluation entry for B1, behavioural tests first) and step 4 (G8 practice plan); A1-A5, B1-B3; G6/G7 measurements; more than 8 epochs (needs a change to the bound in `src/training/modal_train.py` and a paid run).
- `source-manifest.json` records input and output hashes.
