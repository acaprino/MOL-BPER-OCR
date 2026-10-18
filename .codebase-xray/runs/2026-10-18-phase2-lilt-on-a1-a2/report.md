# Stage B on the stage A candidates: LiLT trained on A1 and A2 OCR, three seeds

- Date: 2026-10-18. HEAD: `a043d29` (stage A completed on Modal). Uncommitted at intake and covered here: `data/README.md` (one bullet on the new runs), this directory, and the run metadata under `data/training/runs/lilt-v3.1-20261018-{A1-ocr,A2-ocr,A0-ocr-seed11,A0-ocr-seed23,A1-ocr-seed11,A1-ocr-seed23}/` (weights `*.safetensors` are gitignored). No source or test file changed. The unrelated untracked `uv.lock` was left untouched.
- Why: the user set the goal (m01063) as finding the best local offline engine and how to train it, ignoring Gemini; the reference is the current system, A0 OCR + LiLT B0 (`lilt-v3.1-20261018-current-bundle`, seed 7). Stage A (`../2026-10-18-phase1-modal-ocr/`) left A1 as the best OCR on quality without passing G1, so stage B was measured on A1 and A2 instead of waiting for a frozen A*.
- Protocol: unchanged `training.modal_train` (L4, at most 8 epochs, 2 train variants, patience 2, epoch chosen on validation whole-field accuracy). Each run is trained and decoded on the examples of its own OCR: A0 on `data/training/ground-truth-v3.1/`, A1/A2 on the derived datasets in `../2026-10-18-phase1-modal-ocr/medium/<config>/run/dataset/`. The reviewed values are identical across datasets (`compare_lilt_ocr.py` refuses otherwise). Validation (51659595, 52126316; 146 records) selects; test (51531667, 52060489; 192 records) is a seen regression set.
- Previous scoped state: `analysis-state-before.json`.

## Results

`compare_lilt_ocr.py` (`lilt-compare.txt`, `lilt-compare-seeds.txt`). Fidi = n_fido, importo_euro, scadenza, tipo_op, rapporto (non-null); Soggetti = ndg/denominazione/ruolo 1-4.

| Run | OCR | Seed | Best epoch | Val strict (G4 min 129, target 135) | Val Fidi (G5 23) | Val Soggetti (G5 14) | Val hallucinated | Test strict |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| B0 (current) | A0 | 7 | 8 | 124/146 | 19/25 | 15/15 | 4 | 144/192 |
| A0-s11 | A0 | 11 | 8 | 131/146 | 21/25 | 14/15 | 0 | 135/192 |
| A0-s23 | A0 | 23 | 5 | 128/146 | 20/25 | 14/15 | 0 | 152/192 |
| B1 | A1 | 7 | 8 | **134/146** | 22/25 | 12/15 | 0 | 146/192 |
| A1-s11 | A1 | 11 | 8 | 133/146 | 22/25 | 12/15 | 0 | 145/192 |
| A1-s23 | A1 | 23 | 8 | 133/146 | 22/25 | 13/15 | 2 | 147/192 |
| A2 | A2 | 7 | 8 | 123/146 | 12/25 | 12/15 | 0 | 128/192 |

Validation whole-field accuracy per epoch (x146), from each `result.json`: A0 s7 `13,13,58,87,116,123,123,124`; s11 `13,19,70,107,127,128,131,131`; s23 `13,21,85,119,128,128,128` (stopped by patience); A1 s7 `13,13,57,100,113,130,131,134`; s11 `13,22,78,121,126,133,133,133`; s23 `13,13,88,117,125,127,131,133`; A2 `13,13,33,57,95,105,120,123`.

## Findings

| Finding | Evidence | Status |
|---|---|---|
| R41: A1 + LiLT beats A0 + LiLT on validation under every seed | A1 133-134/146 against A0 124-131; the worst A1 seed is above the best A0 seed. A1 passes G4 minimum (129) on every seed and misses the target (135) by one or two; A0 passes the minimum on one seed of three. A1 is also steadier (spread 1 against 7). Fidi 22/25 on every A1 seed against 19-21 for A0. B0's 124 was the lowest of the three A0 seeds, so part of the earlier 124 -> 134 jump was seed noise: the like-for-like gain is +2 to +10, mean 133.3 against 127.7. | A1 is the stage A base for stage B on this evidence. G5 Fidi (23) still fails on every run. |
| R42: A1 loses Soggetti on validation | A1 12-13/15 against A0 14-15/15 (G5 needs 14). Two of A1's misses keep `Di` on the wrong side of a cell boundary (`denominazione_3` `ADERNO' GIOVANNA` -> `ADERNO' GIOVANNA Di`, `ruolo_3` `...Datore Di Pegno` -> `...Datore Pegno`), one is OCR (`LANDOGNAANTONINO`, R37). On test A1 reads Soggetti 21/21 on every seed, A0 19/21. | Open: the `Di` boundary is a decoding/ordering issue, not recognition. |
| R43: test FIDI fails on multi-row tables, and validation cannot see it | Test Fidi is 22-33/60 for every run. A1 s7: 25 of its 28 test FIDI misses are on 51531667, whose FIDI table has two rows (F1, F2); the role is predicted on both rows and the decoder joins them (`n_fido` `F1 F2 F1 F2`, `rapporto` with the other row's numbers, `scadenza` `361 mesi 30/04/2026`). The reviewed value is always one row: the topmost F word in reading order (F1; F2 on `GestioneFidi_down`). In the training split only 52102599 has a two-row table (its reviewed values are the F1 row); validation has none, so validation selects blind to this case. | Open; see R44. |
| R44: a one-row constraint on the FIDI fields never hurts and repairs most of R43 | `simulate_fidi_row.py` (`fidi-row-simulation.txt`) keeps, for n_fido, rapporto, descrizione, scadenza, importo_euro and tipo_op, only the words above the midpoint between the topmost predicted `n_fido` and the next word in its column. Validation: unchanged on five runs, +1 on A0 s23. Test strict: A1 146 -> 162, 145 -> 152, 147 -> 151; A0 144 -> 151, 135 -> 153, 152 -> 154. The rule follows from the training data (52102599) and from the schema (one scalar per field); its size was measured on the seen test set, which therefore stops being a clean estimate for this rule. What remains on 51531667 is the model not tagging the first row on the tooltip screens (`n_fido` F1 and `importo_euro` missing, `tipo_op` `Sostituzione` never tagged) and `034 0744` repeated inside `rapporto`. | Proposed decoder change, to land with a test and an ADR. |
| R45: the 8-epoch cap is binding | Six of seven runs pick the last allowed epoch, and the curves are still rising there (A1 s7 131 -> 134, A2 120 -> 123). A2's 123/146 is therefore an undertrained figure, not a ranking against A1. | Open: a longer bounded run is a `modal_train` change. |
| R46: a stalled download is not a failed run | The A1 s11 local client stopped writing `model.safetensors` at 360 MB for an hour after the remote run had finished (the A1 s23 client in parallel logged a `MemoryError` inside the SSL read and recovered). The process was killed and `redownload_model.py` fetched the eleven files of `model_v3_1_2c370ac09abcb310` from the volume as `modal_train.main()` does (`redownload-A1-seed11.log`, exit 0, 1134412212 bytes as for the other runs). Predictions and metrics had been written before the download and were not touched. | Resolved for this run. |

## Cost

Seven L4 training runs of 275-337 s of training each (about 6 minutes per app with start-up), roughly $0.5-1 each on the account `alfio-caprino`; app ids are in the `train-*.log` files.

## Newly executed verification

- `compare_lilt_ocr.py` over the seven runs: exit 0, `lilt-compare.json`/`.txt` (A0 s7, A1 s7, A2) and `lilt-compare-seeds.json`/`.txt` (three seeds of A0 and A1). It refuses runs whose reviewed values, prediction ids or word counts differ from their examples.
- `simulate_fidi_row.py` over the six seed runs: exit 0, `fidi-row-simulation.txt`. It wraps `training.evaluation.decode_fields()` without changing the source.
- No source changed, so the suite was not re-run here; the last full run is `../2026-10-18-phase1-modal-ocr/pytest-full.txt` (494 passed).
- `source-manifest.json` records the hashes of the datasets, the run results and predictions, and the scripts of this record.
