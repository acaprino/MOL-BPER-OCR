# Phase 1: stage A comparison (A0-A4) and stop/go outcome

- Date: 2026-10-18. HEAD: `29a275fa23e43a87b27d08ec0e3e0ae72dcebdf3`; stop/go section and R31, R32, R35 corrected on top of `83a9c186de215e16a9faf4638c7e79bb79128046`. Uncommitted at intake: the `CLAUDE.md` pointer fix (`.tritech/codebase-xray` paths removed by `d9462a4`) and this directory; the unrelated untracked `uv.lock` was left untouched.
- Scope: `docs/next-ver-plan.md` Phase 1 steps 1-3. Runner: `src/training/ocr_runner.py` (commit `29a275f`) in `.venv-ocr` (`requirements-ocr.txt`), profile `pc4` (4 intra-op, 1 inter-op threads). Selection metrics on train and validation only; no historical test row enters any figure below.
- Machine: Intel64 Family 6 Model 170, 22 logical CPUs, Windows 11 desktop with other applications running. Timings rank configurations on one machine; they are not G6 measurements.
- Previous scoped state: `analysis-state-before.json` (the `2026-10-18-phase0-ocr-runner` record).

## Results

| Config | Det / Rec | Status | Train OCR non-null | Val OCR non-null (G1 needs 131) | Train+val subject NDG | Train+val rapporto | 6->8 train+val | s/screen mean, p95, max | Peak MB |
|---|---|---|---:|---:|---:|---:|---:|---|---:|
| A0 | v6 small / v6 small | complete, 113/113 | 562/613 | **124/133** | 21/26 | 28/29 | 11 | 6.14, 8.76, 11.19 | 585 |
| A1 | v6 small / v6 medium | stopped after 18 screens | - | - | - | - | - | **154.2** mean on 18 screens (A0 on the same: 7.03) | - |
| A2 | v6 medium / v6 medium | not run | - | - | - | - | - | - | - |
| A3 | v6 tiny / v6 medium | cost sample, 2 screens | - | - | - | - | - | **81.7, 83.6** (A0: 5.10, 5.14; A1: 96.7, 98.3) | - |
| A4 | v6 small / v5 latin mobile | complete, 113/113 | 553/613 | 120/133 | 21/26 | **18/29** | 19 | 5.46, 7.55, 9.23 | 498 |

Model SHA-256 prefixes (all equal to the RapidOCR 3.9.2 catalog): det small `090f04ab`, det tiny `f42c0fbd`, rec small `6f327246`, rec medium `eef44482`, rec latin v5 `b20bd37c`, cls `e47acedf`. Full figures: `stage-a-compare.json` / `.txt` (`compare_stage_a.py`), per-run `manifest.json` and `ocr_selection.json`.

## Findings

| Finding | Evidence | Status |
|---|---|---|
| R31: the v6 medium recognizer costs about 1 s per text box on this CPU | A1 differs from A0 only in the recognizer and took 17-26x longer per screen on the same 18 screens (92.6-208.0 s, mean 154.2 s). The cost tracks the number of boxes: 0.86-1.30 s per box on every screen over 50 minutes, and 1.07-1.16 s per box in A3 an hour later in the other chain (`timing-per-box.txt`). Paging or a passing load would make it erratic, so the cost is probably intrinsic, but it was measured on an uncontrolled machine with low commit memory, and the medium model file is only 3.6x the small one (76.6 against 21.2 MB), so a configuration cause is not excluded. Stopped by hand to free the CPU, not by the memory stop. A1's texts on the 8 train screens it read differ from A0 mostly on UI glyphs (filter icons read `7`); field-level quality was not measured (no complete cache). | Cost probable, not controlled. Quality unknown. |
| R32: A3 shares that cost | Two screens before the memory stop: 81.7 and 83.6 s, 16x A0 on the same screens, same per-box cost as A1. Quality not measured. | Cost probable (n=2). Quality unknown. |
| R33: A2 unmeasured | Not started: the first chain was stopped while it was about to start A2, the second chain was stopped by the memory reaper. A2 uses the same medium recognizer as A1 and A3 plus a larger detector; its cost is expected to be at least theirs, but this is an inference, not a measurement. | Open; a 3-screen cost sample needs about 10 minutes when memory allows. |
| R34: the latin recognizer reads identifiers worse | A4 versus A0 on train+val: 39 values lost (rapporto 11, scadenza 7, tipo_op 6, tipo 4, ndg_4 2, others 9), 26 gained (denominazione 11, scadenza 4, filiale_relazione 2, ndg_1 2, others 7). Losses are digit confusions, e.g. `05508922` -> `05508822` (9->8), `05669132` -> `05869132` (6->8). Rapporto train+val 18/29 against 28/29: G3 fails. Faster and lighter than A0. | A4 rejected on G1 and G3. |
| R35: A0, A4 and A5 cannot pass validation G1; A1-A3 are unmeasured | Best measured value is A0 at 124/133 (131 needed). A5 cannot close the gap: validation holds one 6->8 case, `importo_euro` `160.000` read `180,000`, whose punctuation is also wrong, so even a perfect 6->8 correction leaves it unavailable. The other 8 gaps are a detector miss (`301 mesi`, two tooltip screens of `51659595`), recognizer errors (`Nuova Fnanza`, `21 - STELFRANCO`), a leading `-` before `LANDOGNA CORRADO`, `tipo` `BMB` excluded by alignment, and two whole-note blocks. The detector miss and the recognizer errors are the kind a medium detector (A2) or recognizer (A1-A3) could fix, and none of those three was scored. | Stop/go open, see below. |
| R36: A0 alone already exceeds the G6 budget on this desktop | Mean 6.14 s and max 11.19 s per screen for OCR only, against G6 limits of 6 s mean and 10 s max for the whole process (pc4). Not a G6 measurement (uncontrolled load, not the target hardware), but it leaves no time for stage B. | Open: latency needs its own work (smaller input, faster detector or recognizer). |

Historical context, not used for selection: the 2026-10-07 baseline also tried A0 at scale 2x on 23 screens (`d939ea5:.tritech/codebase-xray/baselines/2026-10-07-riscontro-12-pratiche/prove/ocr-locale-rapidocr/punteggio_2x_sub23.txt`): subject NDG 19/21 (17 at 1x), scadenze with a 6 3/8 (5), rapporti 8/10 (9), 8.06 s per screen (7.20). Mixed, and slower. Those screens mixed splits.

## Stop/go

Plan Phase 1 step 3: "Congelare A* soltanto se supera G1/G3 di validazione e lascia un budget realistico per Stadio B entro G6 ... Se nessuna configurazione è idonea, interrompere la promozione e documentare l'esito."

What is settled: A0 fails G1 (124/133) and A4 fails G1 and G3. Both are complete runs, recounted independently (12/12), and A0 reproduces the bundle cache exactly; the memory stop came after both had finished and does not alter what the OCR read. A5 on A0 cannot change validation G1.

What is not settled: A1, A2 and A3 were never scored. A1 was stopped by hand on cost, the A3 and A2 cost samples were cut by the memory stop before A2 started, and their cost comes from an uncontrolled machine. The stop/go rule judges G1/G3 first; a configuration that passes them but is too slow would turn the next step into making it faster (the cost is linear in the number of boxes, so reading only the content area would cut it), not into giving up stage A. **No A* is frozen and none is excluded on quality: the stop/go stays open** until A1 and A2 are scored on the validation screens on an idle machine.

Correction: commit `83a9c18` recorded "No configuration qualifies ... promotion stops here" and treated A1-A3 as excluded. That overstated the evidence, which covers A0, A4 and A5 only; this section replaces it.

## Execution notes

- The first chain (`run_stage_a.sh A0 A1 A2 A3 A4`, `stage-a.log`) was stopped after A1's cost was clear. TaskStop ended only the outer shell: the inner script kept running and started A2 when the A1 process was killed. All its processes were then stopped by PID and the empty `A2-pc4` directory (manifest only, no screen) was removed.
- The second chain (A4 complete, then 3-screen samples of A3 and A2, `stage-a-2.log`) was stopped by Claude Code's memory-pressure reaper during the A3 sample, after A4 and its report had finished. Commit charge afterwards: 2.1 GB free of 43.5 GB, 5.0 GB of RAM free. Per the harness, it was not restarted.
- The full suite of the previous record ran from about 11:39:54Z to 11:40:35Z, during A1; A1 is excluded on a cost 22x above A0, far beyond that interference.
- Derived `dataset/examples.json` files (3.5 MB each) are gitignored: they are rebuilt from `cache.json` by `python -m training.ocr_runner report`, and `dataset/manifest.json` keeps their content fingerprint.

## Newly executed verification

- `timing_per_box.py`: PASS, exit 0 (`timing-per-box.txt`): A1 and A3 cost per text box within 0.8-1.4 s on every screen. Negative control: doubling one A1 timing in a copy makes it FAIL, exit 1.
- `check_stage_a.py`: 12/12, exit 0 (`check-stage-a.txt`): recounts train/val OCR availability, subject NDG and rapporto from each derived alignment report, independently of `ocr_selection_metrics()`, and checks no historical test row is included.
- A0 through the runner reproduces the bundle cache: 12/12 in `../2026-10-18-phase0-ocr-runner/check-a0-runner.txt`.
- Test suite: not re-run for this record. No source or test file changed since `29a275f`, where `.venv\Scripts\python.exe -m pytest tests` gave 479 passed (`../2026-10-18-phase0-ocr-runner/pytest-full.txt`); this record changes only `CLAUDE.md`, `.gitignore` and X-ray files, and commit memory was critically low.
- `source-manifest.json` records hashes.
