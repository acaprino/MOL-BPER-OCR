# Phase 0, step 2: reconciliation of the lilt-v3.1-20261016 run with the current v3.1 bundle

- Date: 2026-10-18. HEAD: `0fd7c07aba56f46da6060132fba83e4b76756b2f` (plan and X-ray committed). Uncommitted at intake: only the unrelated `uv.lock`, left untouched.
- Scope: read-only reconciliation required by `docs/next-ver-plan.md` Phase 0 step 2. No source, test, configuration, model, dataset or saved-run file was changed; outputs live only in this directory.
- Previous scoped state: `analysis-state-before.json` (the `2026-10-18-plan-selection-power` record).

## Provenance: what differs between the run and the current bundle

The run's training manifest (`result.json` -> `manifest.dataset_manifest`) was compared key by key with `data/training/ground-truth-v3.1/manifest.json`.

| Item | Run (2026-10-16T16:33Z) | Current bundle (files dated 2026-10-16 21:46) |
|---|---|---|
| `dataset_content_sha256` | `11b88186...` | `469c26d1...` |
| Workbook | `mnt/riscontro-2026-10-07/...xlsx`, `483e1ab4...` | `data/revisione/revisione/...xlsx`, `ba537eff...` |
| `alignment.py`, `dataset.py`, `model.py`, `schema.py` hashes | older | current (`evaluation.py` identical) |
| Supervision | 844 supervised, 55 ocr mismatch, 17 partial | 863, 31, 22 |
| Training role words | `IGNORE` 2957, `rapporto` 76, `scadenza` 29, `sogg_ruolo` 63 | 1066, 92, 33, 73 |
| OCR cache | `rapid_v6_small_1x.json`, `e261c05b...`, 1x, not rewritten | identical reference |

So the saved model was trained on an older alignment of the same OCR, before the credit-table alignment fix (commit `d939ea5`). The current bundle was rebuilt about three hours after the run.

**OCR cache location.** Both manifests point to `.tritech/codebase-xray/baselines/2026-10-07-riscontro-12-pratiche/prove/ocr-locale-rapidocr/rapid_v6_small_1x.json`, deleted from the working tree by `d9462a4`. The 113-screen cache survives only in git history (blob `803ef962...` at `d939ea5`; its SHA-256 is `e261c05b...`, verified). `data/spike-ocr/scripts/ocr_probe_out/rapid_v6_small_1x.json` has the same name but is a different file (9 screens). Any rebuild of the bundle or of A0 must first restore that blob to a stable path.

## Re-evaluation of the saved predictions on the current examples

`reconcile_lilt_run.py` feeds the saved `validation_predictions.json` and `test_predictions.json` (content equal to the predictions embedded in `result.json`) to the current `evaluate_predictions()` over the current `examples.json`. Preconditions checked: same example ids per split, and same word count on all 38 held-out screens.

| Split | Records | Expected / predicted / status changed | Strict accuracy | OCR availability, non-null: saved -> current |
|---|---:|---|---|---|
| validation | 146 | 0 / 0 / 0 | 115/146 unchanged | 121/133 -> **124/133** |
| test | 192 | 0 / 0 / 0 | 127/192 unchanged | 170/183 -> **178/183** |

Identical predicted values on all 338 records show the decoded words are the same, so the only change is the availability oracle, which depends on the alignment labels. The strict baselines of the plan (115/146, 127/192) therefore hold on the current corpus; the availability figures of section 1.1 are the outdated part.

### The section 1.2 diagnosis of the 13 unavailable test values is wrong

With the same OCR, the current oracle leaves 5 non-null test values unavailable: `52060489__GestioneFidi` `rapporto` (OCR `05666385`, the only 6->8 on a rapporto), `52060489__Soggetti` `ndg_1` and `ndg_2` (6->8), and the two `note_della_richiesta`. The other 8 saved "unavailable" values become available:

- 6 are `rapporto` `034 0744 0017 05502254` on `51531667__GestioneFidi_Tooltip1..6`, a different practice from the one section 1.2 names. OCR reads them exactly; LiLT still gets all 6 wrong by merging the second credit line, e.g. `034 0744 0017 05502254 020 0744 0000 020 04479993`. This is a stage B row-assignment error.
- 2 are `52060489__GestioneFidi_Tooltip1` and `_Tooltip3`, which LiLT already predicted **correctly** while the old oracle called them unavailable.

`52060489` has 4 `GestioneFidi*` screens, not 9, and RapidOCR reads `05666365` correctly on 3 of them. Section 1.2's "9 of 13 are the same rapporto on 9 GestioneFidi screens of 52060489, read 6 as 8" is not supported by the run's own records: the 9 saved unavailable rapporti came from the old alignment, and only 1 is an OCR 6->8.

Consequences for the plan (not applied; pending the user's decision):
- On the current corpus the test OCR gap is 5/183, of which 3 are 6->8. The stage B gap (178 available vs 119 correct non-null) is larger than section 1.2 states.
- Validation still misses G1 (124/133 against 131/133), for reasons other than 6->8: a detector miss on `scadenza` `301 mesi` (two tooltip screens, no OCR token), `Nuova Fnanza`, `21 - STELFRANCO`, a leading `-LANDOGNA`, `180,000`, `tipo` `BMB` excluded by alignment, two notes. Detector variants (A2, A3) and the latin recognizer (A4) remain relevant; A5's expected gain is smaller than motivated.
- B0 as it stands is LiLT trained on the older alignment. A B0 retrained on the current bundle is a different baseline and needs a GPU run (Modal, ADR 0022); it was not executed.

## Newly executed verification

- `reconcile_lilt_run.py` (`reconcile.txt`, `reconciliation_summary.json`, `*_record_diff.json`, `*_field_metrics_current_examples.json`): exit 0; it stops with an error if ids or word counts differ.
- Manifest diff, OCR blob hash and raw OCR token inspection on `52060489` and `51659595` screens: commands recorded in this session, results above.
- Local `*_predictions.json` equal the predictions embedded in `result.json`; their byte sizes differ from `download_manifest.json` (re-serialised during the recorded recovery), so byte identity with the remote files is not verified.
- `.venv\Scripts\python.exe -m pytest tests`, Python 3.11.15: exit code **0**, **439 passed, 3 warnings in 48.63s** (`pytest-full.txt`, fresh run). No code changed; it is not evidence for any gate.
- Not executed: OCR re-run (rapidocr and onnxruntime are not installed in `.venv`), bundle rebuild, retraining, any candidate A1-A5 or B1-B3.
- `source-manifest.json` records input and output hashes.
