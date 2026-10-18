# Phase 1 completed on Modal: A1-A3 scored, stop/go measured

- Date: 2026-10-18. HEAD: `1e63322` (record of `2026-10-18-phase1-ocr`, stop/go left open). Uncommitted at intake and covered here: `src/training/ocr_runner.py` (`merge_runs()`), `src/training/modal_ocr.py` (new), `tests/test_training_ocr_runner.py` (15 new tests), `src/training/README.md`, `CLAUDE.md`, `.gitignore` (derived `examples.json` ignored at any depth) and this directory. The unrelated untracked `uv.lock` was left untouched.
- Scope: `docs/next-ver-plan.md` Phase 1 steps 1-3 for the configurations the previous record never scored (A1, A2, A3), plus an A0 control. Selection figures cover train and validation only; no historical test row enters them.
- Why Modal: the user asked (m00926) to run the trials on Modal after pointing out that the local stop/go rested on runs cut by memory pressure. Containers: CPU only, 4 cores, 4 GiB, Python 3.13, the exact `requirements-ocr.txt` pins and the model files of the local `.venv-ocr` (same SHA-256 prefixes: det small `090f04ab`, rec small `6f327246`, cls `e47acedf`; the medium and tiny files are checked against the RapidOCR catalog digest inside `run_ocr()`).
- Previous scoped state: `analysis-state-before.json`.

## How the runs were made

- `src/training/modal_ocr.py` sends each group of 8 screens to `read_shard()`, which runs the ordinary `run_ocr()` on them (profile `pc4`, 4 intra-op threads). A0 ran as one shard. The local entrypoint stores each shard's `manifest.json` and `cache.json` unchanged (`<config>/shards/<n>/`), then `merge_runs()` builds `<config>/run/` only from complete shards with the same configuration and engine build that cover every reviewed screen exactly once. `ocr_runner report` then built the derived dataset and `ocr_selection.json` locally, as for a local run.
- First attempt (`attempt1-name-collision/`): refused before any reading by the image integrity check, `Screenshot 51185037__Elenco differs from the reviewed image: /tmp/.../images/Elenco.png`. Staged images were named by file name, which repeats across practices. Fixed by naming them `<screen id><suffix>`; nothing from that attempt was used.
- A0 control: one container, 113 screens. Its cache has the same texts in the same order as the bundle cache `data/training/ocr-cache/rapid_v6_small_1x.json` on 113/113 screens, scores and boxes within 1e-4 on 111/113 (`compare-A0-modal-vs-bundle.txt`), and its selection metrics equal the local A0 run exactly. The container port reproduces the local engine.
- Compute: about 6,400 container-seconds of reading on 4-CPU containers (1.8 h), excluding image build and start-up; app ids `ap-NN4aWWnWcti1FhoOqA6jIU` (A0 control) and the detached medium app recorded in `medium.log`.

## Results (train and validation only)

| Config | Det / Rec | Train OCR | Val OCR (G1 needs 131) | Train+val subject NDG | Train+val rapporto | 6->8 train+val | G3 val |
|---|---|---:|---:|---:|---:|---:|---|
| A0 | v6 small / v6 small | 562/613 | 124/133 | 21/26 | 28/29 | 11 | pass |
| A1 | v6 small / v6 medium | 575/613 | **126/133** | **26/26** | **29/29** | **0** | pass |
| A2 | v6 medium / v6 medium | **582/613** | 124/133 | 26/26 | 29/29 | 0 | pass |
| A3 | v6 tiny / v6 medium | 569/613 | 121/133 | 26/26 | 28/29 | 0 | pass |
| A4 | v6 small / v5 latin mobile | 553/613 | 120/133 | 21/26 | 18/29 | 19 | fail |

A0 and A4 are the local runs of `../2026-10-18-phase1-ocr/`; A1-A3 are the merged Modal runs. Full comparison with every value gained and lost against A0: `stage-a-compare-modal.json` / `.txt` (`compare_runs.py`).

## Findings

| Finding | Evidence | Status |
|---|---|---|
| R37: the v6 medium recognizer fixes the identifiers | A1, A2 and A3 read no value as 6->8 on train+val (A0: 11, A4: 19), every subject NDG (26/26 against 21/26) and every rapporto in A1 and A2 (29/29). A1 against A0: +27/-12 values. Gains: digits (`38237200` -> `36237200`, `381 mesi` -> `361 mesi`, `05865788` -> `05665788`), spaces inside names (`DE MARCHIALESSANDRO` -> `DE MARCHI ALESSANDRO`, five screens), leading `-` removed from denominations, `Nuova Finanza`, `21 - CASTELFRANCO`. Losses: dropped spaces (`LANDOGNAANTONINO`, `CIMINNISIPAMELA`), `KOLA AL..` for `KOLA AL...` (three screens), `tipo` read empty three times. A3's tiny detector loses `tipo` (`BPI Mutui`) on eleven screens. | A1 is the best measured stage A configuration on quality. |
| R38: no choice or combination of A0-A4 passes validation G1 | Best is A1 at 126/133. Across all five configurations, 130/133 validation values are read exactly by at least one of them; three never are: `tipo` `BMB` on `51659595__Elenco_dx` (alignment unresolved in every run) and the two long `note_della_richiesta` of `51659595` and `52126316` (`check-stage-a-full.txt`). G1 allows two misses. A1's other four misses: `301 mesi` twice (the detector misses it; A2 and A3 read it), `LANDOGNAANTONINO`, `160,000` for `160.000`. | Stop/go measured, see below. |
| R39: the note oracle drops punctuation at the edge of a line | `_include_punctuation()` (`src/training/alignment.py:642`) keeps a punctuation-only word only between the matched words of its line, so a leading bullet `-` and a trailing `€` never enter the aligned `ocr_text`, although the engine read them (A1 raw lines: `- Numero proposta DESK: N.D.`, `IMPORTO RICHIESTO : 160.000,00 €`). Notes with inner punctuation still align exactly (2-3 of 16 notes per configuration). The two validation notes also hold real recognition errors in every configuration (`CÓNDIZIONI`, `INDETERMÍNATO` and one garbled line in `52126316`; `Ázienda` in `51659595`, plus the missing line `Effettuato check up assicurativo ...` in A0, A1 and A3), so a corrected oracle alone would not make them available. | Open: the oracle under-counts notes; it does not change the validation outcome. |
| R40: Modal timings do not rank cost and are not G6 measurements | Shard means are bimodal on the same configuration: A1 5.3-8.2 s per screen on 12 shards and 39.6-44.7 s on 3; A2 5.6-9.4 against 53.6-76.5; A3 4.8-8.9 against 41.6-57.0. Warm-up times split the same way, so the host differs, not the screens. The same-host cost panel (`medium/cost-panel/`, three screens read by A0, A4, A1, A3, A2 in that order) put A2 below A1 (7.9-12.9 s against 16.2-36.0 s), although A2 does A1's work with a larger detector: the host slowed or sped up during the panel. CPU model is not exposed in gVisor (`host.json`: `unknown`). | Open: G6 for the medium recognizer needs the target hardware. |
| R31 corrected: the local A1 cost was inflated by the machine | A1 read at 154 s per screen locally (22x A0), against 5.3-8.2 s on the fast Modal hosts, about 3-4x the A0 control (1.86 s) on other hosts of the same kind. The previous record called the local cost "probably intrinsic" because it was stable per text box; that stability did not rule out a persistent machine-wide slowdown, which is what the Modal runs indicate. | Supersedes R31-R32 of `../2026-10-18-phase1-ocr/report.md`. |
| R36 updated | The A0 control on one Modal container read at 1.86 s mean, 2.57 s p95 and 2.77 s max per screen, against 6.14, 8.76 and 11.19 s on the loaded desktop. "A0 alone exceeds G6" is not established; G6 stays to be measured on the target hardware. Peak RSS under gVisor (1346 MB) is not comparable with the Windows working set (585 MB). | Open. |

## Stop/go

Plan Phase 1 step 3 freezes A* only if it passes validation G1/G3 with a G6 budget for stage B. All five configurations are now scored: none passes validation G1, and by R38 no choice or combination of them can, because three of the 133 values are read exactly by none and G1 tolerates two. **Promotion stops, this time on measurement.** No A* is frozen.

What the measurement changes for the plan, to be decided by the user: A1 reads every identifier exactly, which the plan's stage B gates (G4/G5) depend on, and comes within two values of the G1 count once the three values no engine reads are set aside. Whether G1 keeps counting the two long notes and the unresolved `BMB` cell, whether the note oracle of R39 is fixed first, and whether A1 continues as a provisional base for stage B are amendments of `docs/next-ver-plan.md`, not outcomes of this record.

## Newly executed verification

- `.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider`: **494 passed**, 3 warnings, exit 0 (`pytest-full.txt`); 14 of the 15 new `merge_runs()` tests were run against a `NotImplementedError` stub first and failed on it; the 15th (`test_shards_read_on_different_hosts_record_each_host`) was outside that `-k merge` selection and was not watched failing.
- `check_stage_a_full.py`: 11/11, exit 0 (`check-stage-a-full.txt`): recounts validation OCR, train+val NDG, rapporto and 6->8 for A0-A4 directly from each `dataset/alignment_report.csv`, and the 130/133 ceiling. Negative control: quoting a ceiling of 131 makes it FAIL, exit 1.
- `compare_caches.py`: the Modal A0 cache matches the bundle cache on 113/113 screens (exit 0); A4 against the bundle fails on 0/113 (exit 1), the negative control.
- `compare_runs.py` reproduces the local A0 and A4 rows of `../2026-10-18-phase1-ocr/stage-a-compare.txt` exactly.
- `src/training/modal_ocr.py` has no unit test: it is the Modal boundary, exercised end to end by the runs above; the merge logic it relies on is tested in `tests/test_training_ocr_runner.py`.
- `source-manifest.json` records the hashes of the covered sources and of the four Modal caches.
