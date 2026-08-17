# Logic-Integrity Review — `extraction/` package

> Saved by team lead from the logic-integrity-reviewer's report (subagent file writes are blocked by the harness).

- **Dimension**: logic-integrity (contracts, invariants, assumptions, domain rules, ordering, idempotency, state)
- **Target**: 15 files at HEAD (see `.team-review/00-scope.md`); no diff range
- **Driver**: `.team-review/02-interconnect.md` (anchors at lines 470-505; Invariants, Domain Rules, Assumptions, Contracts read in full)
- **Method**: every map anchor re-verified directly against source; verdicts are CONFIRMED / REFINED / REFUTED. 12 of 17 findings are map-anchored (~71%).

## Verdict summary for assigned anchors

| Map anchor | Verdict | Finding |
|---|---|---|
| I3 budget-floor crash | CONFIRMED + REFINED (fires on virtually every screen) | F1 |
| I12 alphabetical retry truncation | REFINED (HEADER is never retried in practice) | F2 |
| I5 dead anchor gate | CONFIRMED (two kill mechanisms, plus a third: the gated dict is discarded entirely) | F3 |
| I1/I4 soggetti flatten vs retry | CONFIRMED + REFINED (also drops `evidence_text`, creates mixed-provenance rows) | F5 |
| Retry coverage hole feeds coherence | CONFIRMED | F6 |
| NaN/out-of-range confidence | CONFIRMED + REFINED (NaN candidate always WINS `pick_best`) | F8 |
| Silent metric denominator drift | CONFIRMED + REFINED (crashed screens inflate accuracy) | F9 |
| Coarse transient/permanent error split | CONFIRMED | F10 |
| Failed retries invisible | CONFIRMED (plus internal HTTP retries never metered) | F11 |
| GT/pred CSV dialect asymmetry | CONFIRMED | F12 |
| `_merge_tables` dead branch | CONFIRMED | F14 |
| Identity-dependent source tracking | CONFIRMED sound today, fragile | F15 |

New violations in the same invariant classes: F4 (nullish-vocabulary bypass at four sites), F7 (coherence check breaks I6 too), F13 (`norm_number_str` Italian-format holes), F16 (mismatch guard compares the wrong entity), F17 (`canonical_fields` cardinality depends on retry path).

---

## CRITICAL

### F1 — `MAX_CALLS_PER_SCREEN <= 2` crashes on effectively every screen; docs claim it cleanly disables retries

- **Map anchor**: I3 (also I2, I10). **Verdict**: CONFIRMED, REFINED.
- **Location**: `extraction/pipeline.py:259-263`, `extraction/pipeline.py:284`; config at `extraction/config.py:54`; doc claim in `docs/10-configuration-guide.md` ("Con `2` i retry sono disabilitati del tutto").
- **Verified mechanics**: the early `return` at `pipeline.py:259-260` triggers only when `areas_to_retry` is empty. With `MAX_CALLS_PER_SCREEN=1|2`, `allowed_retries = max(0, MCS - 2) = 0` (`pipeline.py:262`), so `areas_to_retry_list = sorted(...)[:0] = []` (`pipeline.py:263`), and `ThreadPoolExecutor(max_workers=0)` at `pipeline.py:284` raises `ValueError: max_workers must be greater than 0`.
- **Refinement (why "every screen", not "bad screens")**: the weak-area detection (`pipeline.py:251-257`) iterates all of `AREA_TO_FIELDS` and treats any nullish-or-low-confidence field as weakness. `AREA_TO_FIELDS` mixes fields from different BPER pages into the same areas (`config.py:69-82`): `ultima_validazione_scheda` (screens 4-5 only) sits in HEADER, the soggetti/privati fields in BODY, the two note fields in FOOTER. On any given screen most of these are legitimately absent, hence nullish, hence every area is "weak" on essentially every screen. `areas_to_retry` is never empty in practice and the guard at `:259` never saves you.
- **Impact**: an operator following the docs to cap cost gets, in parallel mode, a batch that silently yields zero results (exceptions swallowed per screen at `cli.py:246-251`) or, in serial mode without callbacks, a hard abort (`cli.py:266`). Negative env values behave identically.
- **Suggested direction**: `if allowed_retries == 0 or not areas_to_retry_list: return` before the pool; validate `MAX_CALLS_PER_SCREEN >= 2` at config load; fix the doc sentence.
- **Confidence**: 95

## HIGH

### F2 — Retry area selection is page-type-blind: HEADER is never retried under the default budget, and the retry budget is spent unconditionally on every screen

- **Map anchor**: I12 (also I2). **Verdict**: REFINED (stronger than mapped).
- **Location**: `extraction/pipeline.py:251-263`; `extraction/config.py:69-82`; HEADER enhancement/prompt at `pipeline.py:270-272`, `extraction/prompts.py:41-48`.
- **Verified mechanics**: `sorted({"HEADER","BODY","FOOTER"})` yields `["BODY","FOOTER","HEADER"]`, truncated to `allowed_retries` (2 under default `MAX_CALLS_PER_SCREEN=4`). Per F1's refinement, all three areas are weak on virtually every screen, so the retry list is `["BODY","FOOTER"]` essentially always.
- **Consequences**: (1) HEADER, the only area whose fields (`ndg`, `denominazione`, `tipo`, `stato`, `fase`, `evidenze`, `config.py:70`) exist on every screen and drive `_status` and the mismatch guard, never receives its retry; `RETRY_PROMPT_HEADER` and the HEADER contrast/sharpness boost (`pipeline.py:270-272`) are dead code under the default config (with `MAX_CALLS_PER_SCREEN=3`, only BODY is ever retried). (2) The "conditional" retry is unconditional in practice: 2 extra VLM calls are burned on every screen, frequently re-reading areas that are legitimately empty for that page type, because the nullish gate cannot distinguish "absent on this page" from "extraction failed".
- **Suggested direction**: order areas by importance (HEADER first) instead of `sorted()`, and/or scope weakness detection to fields plausible for the detected page.
- **Confidence**: 85 (the "always weak" claim is inferential over the 9-screen field distribution, but each area demonstrably contains fields absent from most screens)

### F3 — Anchor confidence gate is dead code by three independent mechanisms; `ANCHOR_CONF_MIN` tunes nothing live

- **Map anchor**: I5. **Verdict**: CONFIRMED, with one addition.
- **Location**: `extraction/pipeline.py:86-102`; `extraction/normalization.py:60-69`, `:78-79`; the only other consumer at `cli.py:87-88` is reachable only from the commented-out dedup call (`cli.py:268-273`).
- **Verified mechanics**, each alone sufficient: (1) `ndg`/`den` are fresh copies from `safe_field()` (`pipeline.py:87-88`); the gate mutates `fields` (`:92-96`) but the function returns the pre-gate copies (`:98-102`). (2) `safe_set_field(..., value=None)` cannot null a non-null value: `if value is not None or f.get("value") is None` (`normalization.py:78`) is False exactly in the targeted case. (3) Not in the map: the mutated `fields` dict (and the whole anchor `out`) is discarded after `:98-102`; nothing ever reads it again, so even a corrected `safe_set_field` would fix nothing.
- **Impact**: a low-confidence hallucinated NDG flows into the main-pass hint (`"NDG atteso: ..."`, `pipeline.py:205-208`), biasing the model, then unconditionally overwrites the main-pass field via `_merge_anchors` (`:212-216`, see F4). The prompt's `confidence >= 0.95` instruction (`prompts.py:36`) coupled to `ANCHOR_CONF_MIN` (`config.py:56`) is decorative.
- **Suggested direction**: gate on the copies before returning (`if ndg["confidence"] < ANCHOR_CONF_MIN: ndg["value"] = None`), repairing all three mechanisms at once.
- **Confidence**: 98

### F4 — Nullish-vocabulary rule bypassed at four anchor-path sites: a "n/d"-style anchor value poisons the hint, overwrites good main-pass values, and yields `_status="OK"`

- **Map anchor**: NEW; violates Domain Rules "Nullish vocabulary" (`normalization.py:28-32`) and I4; interacts with I8.
- **Location**: `extraction/pipeline.py:113` (early exit), `:205-208` (hint), `:212-216` (`_merge_anchors`), `:173-178` (`_status`).
- **Verified mechanics**: the pipeline defines nullness via `is_nullish()` everywhere (retry gating `pipeline.py:255`, `pick_best` `normalization.py:90-93`, classification, mismatch guard), but the anchor path uses raw `is None`/truthiness: (1) `STOP_ON_ANCHOR_UNCERTAIN` fires only on literal `None`; `"n/d"`/`""` bypasses it. (2) `if anchors["ndg"]["value"]:` is True for `"n/d"`, so the main prompt gets `NDG atteso: n/d`, actively steering the model toward a placeholder. (3) `_merge_anchors` overwrites `result["fields"][k]` whenever the anchor value `is not None`, with no `pick_best` and no confidence check: an anchor `"N/D"` at any confidence (gate dead per F3) replaces a correct main-pass `"12345"`. This is the only merge point that bypasses I4 winner selection, and the dead gate was its only safety net. (4) `_status = "OK"` requires only `is not None`, so a screen whose ndg is the literal string `"n/d"` reports OK.
- **Impact**: the `is_nullish` vocabulary exists precisely because VLMs emit placeholder strings instead of JSON null; when that happens on the anchor pass the pipeline amplifies the error and labels the result OK. Downstream, the mismatch guard compares `"n/d"` against GT and the screen classifies WRONG/MISSING across the board.
- **Suggested direction**: use `is_nullish()` at all four sites; route `_merge_anchors` through `pick_best`/`merge_field_sources`.
- **Confidence**: 85

### F5 — Soggetti flatten (step 7) bypasses I4 and destroys retry-recovered values; also drops `evidence_text` and creates mixed-provenance rows

- **Map anchor**: I1/I4 collision, I6. **Verdict**: CONFIRMED, REFINED.
- **Location**: `extraction/pipeline.py:159-166`; BODY retry targets the same 12 keys (`config.py:71-80`) and merges via `pick_best` (`pipeline.py:296-307`); debug-report consumer at `evaluation.py:151`.
- **Verified mechanics**: after retry (step 4) and coherence (step 5) merged `ndg_1..ruolo_4` under I4 rules, step 7 overwrites those 12 fields from `soggetti[:4]` rows with no null check, no `pick_best`, and no `_field_sources` update. Refinements: (1) **Retry destruction**: a BODY retry that recovered `ndg_1="12345"` is overwritten with `None` if the merged soggetti table's row 1 has `ndg=None`. (2) **Mixed provenance**: the overwrite covers only `len(soggetti[:4])` rows; with 2 table rows, `ndg_1/ndg_2` come from the table while `ndg_3/ndg_4` keep field-pass/retry values; with an empty table nothing is overwritten. Which source wins per row is an accident of table length. (3) **Contract narrowing**: the written payloads are `{"value", "confidence", "section"}` with no `evidence_text` key (`pipeline.py:164-166`), silently dropping evidence for these fields in `canonical_fields`, exports, and the debug report; row-level confidence is copied onto all three cells. (4) **I6 confirmed**: `_field_sources` still says `CONTENT_MAIN`/`RETRY_BODY`; `source_attempt` (`evaluation.py:151`) is wrong whenever soggetti rows exist.
- **Suggested direction**: merge each flattened cell through `pick_best` (recording a `SOGGETTI_TABLE` source), or flatten before the retry pass so retries can repair the result.
- **Confidence**: 95

## MEDIUM

### F6 — Retry coverage hole: `creazione` + 5 `tooltip_*` fields can never be retried, and the coherence check depends on exactly those unretryable inputs

- **Map anchor**: coverage-hole anchor; Domain Rules "Coherence repairs". **Verdict**: CONFIRMED.
- **Location**: `extraction/config.py:69-82` vs `extraction/fields.py:18, 28-32`; weak-detection loop `pipeline.py:251-257`; coherence `pipeline.py:311-328`.
- **Verified mechanics**: the weak-area loop iterates only `AREA_TO_FIELDS`, so the 6 unmapped fields neither trigger nor receive retries. `_coherence_check` repairs `evidenze` (from `tooltip_evidenze_b`, `pipeline.py:317-322`, including replacing purely-numeric values with "B") and `tipo` (from `tooltip_descrizione_bmb`, `:324-328`); both repairs hinge on main-pass-only data, so a missed tooltip means the repair silently never fires, with no second chance and no diagnostic (nothing validates `AREA_TO_FIELDS` against `FIELD_KEYS`).
- **Confidence**: 95

### F7 — Coherence check breaks I6 too: repaired `evidenze`/`tipo` keep their pre-repair source label

- **Map anchor**: NEW, same class as I6.
- **Location**: `extraction/pipeline.py:311-328` (mutates fields at step 5) vs `:157` (`_field_sources` attached at step 6); consumer `evaluation.py:151`.
- **Verified mechanics**: `_coherence_check` rewrites `evidenze` to `"B"` and `tipo` to `"BMB"` via `safe_set_field` but receives no `field_sources` and never updates it; no `COHERENCE` source value exists. A repaired `evidenze` shows `source_attempt=CONTENT_MAIN` (or `RETRY_HEADER`) in the debug report, so pass-quality tuning based on that report attributes coherence-synthesized values to the VLM passes. Together with F5, two of the eight post-processing steps violate I6.
- **Confidence**: 92

### F8 — Confidence never validated; NaN makes a candidate unconditionally WIN `pick_best`, and >1.0 makes a wrong value unbeatable

- **Map anchor**: I9. **Verdict**: CONFIRMED, REFINED (failure direction is candidate-favoring, not neutral).
- **Location**: `extraction/schemas.py:11` (no bounds validator; Pydantic v2 accepts NaN/inf for `float` by default); consumers `pipeline.py:255`, `normalization.py:94-96`, `pipeline.py:233-234`; `normalization.py:65` (`or 0.0` does not catch NaN, which is truthy).
- **Verified mechanics**: `pick_best` ends with `return f1 if c1 >= c2 else f2` (`normalization.py:96`). With `c2 = NaN`, `c1 >= NaN` is False, so **f2 (the NaN candidate) wins** any equal-nullness contest, and `merge_field_sources` stamps the candidate source; with `c1 = NaN` the candidate also wins. A single NaN emitted during a retry silently replaces a healthy main-pass value. Separately, `confidence > 1.0` on a wrong value makes it unbeatable in later merges, and NaN at `pipeline.py:255` suppresses the retry that might have fixed the field. `_merge_tables`' averaged-confidence comparisons go all-False with NaN.
- **Suggested direction**: a `field_validator` clamping to [0,1] and mapping NaN to 0.0 on `FieldResult`, `Soggetto`, `Fido`, `Garanzia` closes every path at the schema boundary.
- **Confidence**: 85

### F9 — Metric denominators silently shrink: crashed screens inflate accuracy while graceful failures reduce it

- **Map anchor**: denominator-drift anchor. **Verdict**: CONFIRMED, REFINED (asymmetry between failure modes).
- **Location**: `extraction/evaluation.py:79-81` (`if not pred: continue`), `:88-90` (unknown CSV key skipped); producer behavior `cli.py:246-251`.
- **Verified mechanics**: in parallel mode a screen whose extraction raised is absent from `outputs`; `eval_outputs` then skips that GT screen entirely, removing all its fields from both RAW and FILTERED denominators; a run where 5 of 9 screens crashed reports accuracy over the 4 survivors with no coverage indicator. Contrast: an `ANCHOR_UNCERTAIN` early-exit result (`pipeline.py:114-124`) is a truthy dict, IS evaluated, and scores MISSING on every field. The harder failure (exception) improves the reported number; the softer failure (graceful uncertainty) tanks it, biasing metrics toward crash-heavy configurations. Same pattern for GT rows whose header is not in `CSV_TO_SCHEMA`. Nothing in the return contract (`evaluation.py:116-120`) exposes coverage.
- **Suggested direction**: count and print skipped screens / skipped CSV keys; consider scoring absent predictions as MISSING.
- **Confidence**: 90

### F10 — Transient/permanent error classification is inverted for the most common real failures

- **Map anchor**: transient/permanent anchor. **Verdict**: CONFIRMED.
- **Location**: `extraction/vlm_client.py:252-257`; ValueError producers at `:39`, `:44`, `:95-98`, `:153-156`, `:199-203`.
- **Verified mechanics**: only `ValueError` is permanent; everything else retries 3x with backoff. (1) Auth/permission/invalid-request errors are retried 3x with sleeps; the loop also sleeps after the final failed attempt (`:256-257` execute on the last iteration) before `raise last_err`, adding ~3.3s of dead time to an already-failed call. (2) A one-off truncated/malformed JSON from the Gemini free-form path, or an OpenAI `parsing_error`, raises `ValueError` and is never re-attempted, though re-rolling the generation is precisely the fix for stochastic output corruption. On anchor/main this kills the whole screen; in a retry thread it is swallowed to a warning (F11).
- **Suggested direction**: classify by error semantics (retry parse failures with a bounded budget; fail fast on 401/403-class errors); skip the sleep after the last attempt.
- **Confidence**: 90

### F11 — Failed retries and internal HTTP re-attempts are invisible to cost/call telemetry (I7); `_meta_agg` under-reports systematically

- **Map anchor**: failed-retries anchor, I7, I2 caveat. **Verdict**: CONFIRMED.
- **Location**: `extraction/pipeline.py:287-292` (warning only, no meta record); `vlm_client.py:241-257` (only the final successful attempt returns `_meta`); aggregation `pipeline.py:330-340`; consumer `evaluation.py:244-258`.
- **Verified mechanics**: a failed area retry appends nothing to `attempts_meta`, so `_meta_agg["calls"]`/tokens/cost exclude it even though the provider billed up to 3 HTTP attempts. Even successful logical calls under-report: if attempt 1 fails transiently and attempt 2 succeeds, only attempt 2's usage is recorded; attempt 1's tokens (a full image payload) vanish. The "every VLM call must populate `_meta`" constraint holds per successful return, but the aggregate silently means "successful logical calls only". There is also no structured signal for systematic retry failure; stdout warnings are the only trace.
- **Suggested direction**: append a failure stub to `attempts_meta`; accumulate usage inside `call_vlm_with_retry` across attempts.
- **Confidence**: 90

### F12 — CSV dialect asymmetry: the evaluator cannot read Italian-Excel ground truth nor its own outputs

- **Map anchor**: dialect-asymmetry anchor; Assumptions "GT CSV is comma-separated UTF-8". **Verdict**: CONFIRMED.
- **Location**: reader `extraction/evaluation.py:35` (pandas defaults, no `sep`/`encoding` args); writers `:172-177` and `:234-239` (`sep=";"`, `utf-8-sig`).
- **Verified mechanics**: the GT file comes from an Italian workflow where Excel saves CSV with `;` and often cp1252. A `;`-separated file parses as one column and `_find_column` raises `ValueError: Cannot find screen column` (`evaluation.py:26-31`); cp1252 accents either raise `UnicodeDecodeError` or corrupt the `Fotogramma` join key (then silent row skips per F9). Both writers emit `;`, so a round-trip (export, correct in Excel, reuse as GT) is structurally impossible.
- **Suggested direction**: `pd.read_csv(csv_path, sep=None, engine="python", encoding="utf-8-sig")` or explicit `sep=";"` symmetric with the writers.
- **Confidence**: 95

## LOW

### F13 — `norm_number_str` misparses Italian thousands-dot-only amounts and strips the sign

- **Map anchor**: NEW; against Domain Rules "Numeric vs text comparison". **Location**: `extraction/normalization.py:40-55`; consumers `:127-133`, `:185`.
- **Verified mechanics**: dot-stripping runs only when both "," and "." are present (`:46-47`). `36.177` (Italian thousands, no decimals) parses as `float("36.177")` and normalizes to `"36.18"`, while a prediction `36177` normalizes to `"36177.00"`: two equal values classify WRONG, and in `dataset_mismatch_guard` a grouping-dot NDG on one side can raise a false DATASET_MISMATCH, dropping the screen from FILTERED metrics. Separately, `re.sub(r"[^\d.]", "", s)` (`:50`) deletes a leading minus, so `-1.500,00` and `1.500,00` compare equal. The bare `except:` at `:54` also catches `KeyboardInterrupt`/`SystemExit` (hygiene overlap).
- **Confidence**: 80

### F14 — `_merge_tables`: dead third branch, and "more rows wins" invites wholesale replacement by hallucinated tables

- **Map anchor**: dead-branch anchor. **Verdict**: CONFIRMED plus a domain-rule note. **Location**: `extraction/pipeline.py:225-241`.
- **Verified mechanics**: `elif len(old_data) == 0 and len(new_data) > 0` (`:240-241`) is unreachable (`old==0 and new>0` implies `new>old`, matched at `:236-237`). Beyond that: the primary heuristic replaces the entire table whenever the retry returns MORE rows, with no confidence condition on that branch. A BODY retry that hallucinates an extra soggetti row wholesale-replaces a correct table, and step 7 (F5) then propagates the hallucinated rows into `ndg_1..ruolo_4`. Row-count is treated as quality, which for LLM outputs it is not.
- **Confidence**: 95 (dead branch), 70 (replacement materiality)

### F15 — Source attribution depends on `pick_best` returning inputs by identity; sound today, no failure signal if that ever changes

- **Map anchor**: identity-tracking anchor. **Verdict**: CONFIRMED (sound today). **Location**: `extraction/normalization.py:87-96`, `:105-107`; call sites `pipeline.py:297-300` (`... or {}` creates fresh distinct objects, keeping identity comparison meaningful).
- **Verified mechanics**: any future edit making `pick_best` return a copy or merged dict silently makes `chosen is candidate` always False: `_field_sources` freezes on `CONTENT_MAIN` and retry attribution vanishes, with no assertion or test to catch it. At minimum, an inline comment on `pick_best` should state the identity contract.
- **Confidence**: 95

### F16 — `dataset_mismatch_guard` may compare a co-obligor's NDG against the practice NDG via the soggetti fallback

- **Map anchor**: NEW; refines Domain Rules "Dataset mismatch guard". **Location**: `extraction/normalization.py:162-172`, `:174-189`.
- **Verified mechanics**: when `fields.ndg` is nullish but soggetti rows exist, the guard compares GT's practice-header NDG against the FIRST non-null soggetti row's NDG. Nothing guarantees row ordering or that row 1 is the intestatario; a co-obligor first row produces a false mismatch, silently removing the screen from FILTERED metrics (`evaluation.py:99-104`), or conversely masks a genuine mismatch. Interacts with F14: a retry-replaced table can change which row is first.
- **Confidence**: 60 (depends on an undocumented row-ordering guarantee)

### F17 — `canonical_fields` cardinality depends on which areas were retried: retried-but-empty fields appear as entries, untouched null fields do not

- **Map anchor**: NEW; refines Contracts "Canonical entry" and I1. **Location**: `extraction/pipeline.py:297-301`; `extraction/canonical_mapping.py:24-26`.
- **Verified mechanics**: `FieldsModel.model_dump()` emits `None` for absent fields and `build_canonical_field_entries` skips non-dict payloads; but the retry merge writes back a dict (possibly `{}`, when both current and candidate are empty) for every field of a retried area. After a BODY retry, all 29 BODY fields become dict payloads and produce canonical entries with value None, while null fields of non-retried areas produce none. Export row counts (`evaluation.py:186-200`) and any consumer treating entry presence as "field exists on this page" observe a shape that varies with the retry path, not the data.
- **Confidence**: 85

## Cross-Reviewer Notes

- **architecture**: F2's root cause is structural: the pipeline has no page-type concept while `AREA_TO_FIELDS` unions fields across pages; a real fix needs a page-aware field map (per-page keys already exist in `field_definitions.py`), not more pipeline patches. Also, the retry merge loop (`pipeline.py:286-309`) runs on the calling thread (the inner pool only executes the VLM calls), so there is no merge race; worth stating so nobody adds locking there unnecessarily.
- **security**: F4 widens the prompt-injection surface already mapped: screenshot-rendered text extracted by the anchor pass is re-injected verbatim into the main-pass prompt (`"NDG atteso: {value}"`, `pipeline.py:205-208`) with no sanitization or length cap; an adversarial screenshot can plant instruction text in the anchor value and have it delivered as part of the trusted prompt.
- **hygiene**: bare `except:` at `normalization.py:54` (F13), dead `_merge_tables` branch (`pipeline.py:240-241`), the HEADER-retry prompt/enhancement being dead under default config (F2), and the doc sentence in `docs/10-configuration-guide.md` ("Con `2` i retry sono disabilitati del tutto") which F1 refutes; correct it in the same change that fixes the crash.
- **api-contract**: per F17, `canonical_fields` is not a stable projection of the page; downstream consumers (edge-agent `DataTableTab`, `export_to_csv`) should key off `FIELD_KEYS`/page maps, not entry presence. Also note the flatten payloads' missing `evidence_text` key (F5.3) as a shape variance inside `fields` itself.
