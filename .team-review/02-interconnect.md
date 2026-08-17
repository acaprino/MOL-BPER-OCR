# Interconnect Map — `extraction/` package

Scope: 15 Python files, ~2,442 lines (see `.team-review/00-scope.md`). Every claim below was
verified against current source and is cited `file:line`. External consumers included:
`main.py`, `gui_app.py`, `edge-agent/local_extraction_client.py`.

---

## Call Graph

### Entry flows (three front-ends, one engine)

```
main.py:7-8  load_dotenv() → from extraction import *          gui_app.py:6-14 (NO load_dotenv)
main.py:23   main() ──────────────┐                            gui_app.py:225 threading.Thread(run_process)
                                  │                            gui_app.py:238-247 run_extraction_batch(
cli.py:314 main()                 │                                api_key, provider, model_main,
  ├─ cli.py:315-316  FileNotFoundError if GROUND_TRUTH_CSV missing  max_workers=min(len(paths),12))
  ├─ cli.py:318      load_ground_truth()          ← evaluation.py:33
  ├─ cli.py:322-327  scan INPUT_DIR for .png/.jpg/.jpeg
  ├─ cli.py:333      BatchRunner(parallel=PARALLEL_ENABLED, max_workers=PARALLEL_WORKERS)
  ├─ cli.py:334      runner.run(paths)
  ├─ cli.py:343      evaluator.eval()             → evaluation.py:74 eval_outputs()
  ├─ cli.py:346      evaluator.build_debug_report() → evaluation.py:125
  └─ cli.py:347      evaluator.print_cost_summary() → evaluation.py:244

run_extraction_batch (cli.py:282-307)  — thin wrapper → BatchRunner (both CLI + Tkinter GUI)

BatchRunner.__init__ (cli.py:165-205)
  ├─ cli.py:182-191  create_chat_model() ×2 (main + anchor)   ← llm_factory.py:16
  └─ cli.py:192-197  ExtractionPipeline(main, anchor, names)  ← pipeline.py:47

BatchRunner.run (cli.py:207-276)
  ├─ cli.py:214-217  existence filter (warning per missing path)
  ├─ parallel: cli.py:229-251  ThreadPoolExecutor(max_workers) → _worker → extract_from_screen
  │            on exception: on_error OR print-and-continue (cli.py:246-251)
  ├─ serial:   cli.py:252-266  loop; on exception: on_error OR re-raise (cli.py:266)
  └─ cli.py:268-273  _deduplicate_same_page_outputs call COMMENTED OUT ("TEMP TEST")

Edge-agent path (no BatchRunner):
edge-agent/local_extraction_client.py:21-25  load_dotenv(.env)
  :27-29  imports create_chat_model, ExtractionPipeline, LLM_PROVIDER/LLM_MODEL/LLM_MODEL_ANCHOR
  :47-54  builds 2 models + one ExtractionPipeline in __init__
  :65-106 ingest_frame(job_id, img, ...) — synchronous in capture QThread
     ├─ :86  pipeline.extract_from_image(img, screen_id)   ← bypasses normalize_image BY DESIGN
     ├─ :89-94  on ANY exception → substitute error dict {"screen_id","fields":{},"_status":"ERROR","_error"}
     └─ :106 result_ready.emit(job_id, dict(result))  → Qt signal crosses thread boundary
```

### Pipeline internals (per screen)

```
ExtractionPipeline.extract_from_screen (pipeline.py:182-187)
  ├─ Image.open(path).convert("RGB")          pipeline.py:184
  ├─ normalize_image()                        imaging.py:12-19 (shrink-only to 1800px + contrast + unsharp)
  ├─ screen_id = basename sans extension      pipeline.py:186
  └─ extract_from_image(img, screen_id)       pipeline.py:187

ExtractionPipeline.extract_from_image (pipeline.py:104-180)   [fixed order — load-bearing]
  0. crop_relative(img, CONTENT_CROP)                          pipeline.py:106  ← config.py:59
  1. extract_anchors(content_img)                              pipeline.py:110
       ├─ crop_relative(HEADER_IN_CONTENT)                     pipeline.py:72   ← config.py:60
       ├─ call_vlm_with_retry(schema=AnchorResponse)           pipeline.py:76-84
       ├─ safe_field copies of ndg/den                         pipeline.py:87-88 ← normalization.py:60-69
       └─ ANCHOR_CONF_MIN gate (DEAD — see Invariants I5)      pipeline.py:91-96
  1b. STOP_ON_ANCHOR_UNCERTAIN early exit (divergent shape)    pipeline.py:112-124
  2. _build_anchor_hint_prompt ("NDG atteso: {v}")             pipeline.py:127, 202-209
     call_vlm_with_retry(schema=ExtractionResponse)            pipeline.py:130-138
  3. _merge_anchors (non-null anchors overwrite fields)        pipeline.py:145, 211-216
     _postprocess_tipo (normalize_tipo)                        pipeline.py:146, 218-223
  4. _retry_areas                                              pipeline.py:149, 243-309
       ├─ weak-area detection (nullish OR conf < 0.60)         pipeline.py:251-257
       ├─ allowed = max(0, MAX_CALLS_PER_SCREEN - 2)           pipeline.py:262
       ├─ sorted(areas)[:allowed]  (ALPHABETICAL)              pipeline.py:263
       ├─ inner ThreadPoolExecutor(max_workers=len(list))      pipeline.py:284
       ├─ per-area crop + contrast/sharpness boost             pipeline.py:266-272
       ├─ call_vlm_with_retry(FIELD_RETRY_PROMPTS[area])       pipeline.py:274-282 ← prompts.py:74-78
       ├─ failed retry → print warning, continue               pipeline.py:287-292
       ├─ merge_field_sources per field                        pipeline.py:296-307 ← normalization.py:98-108
       └─ _merge_tables (BODY only)                            pipeline.py:309, 225-241
  5. _coherence_check (tooltip → evidenze/tipo repair)         pipeline.py:152, 311-328
  6. _attempts / _meta_agg / _field_sources                    pipeline.py:155-157, 330-340
  7. soggetti[:4] flatten → ndg_1..ruolo_4 (unconditional)     pipeline.py:159-166
     build_canonical_field_entries                             pipeline.py:168-170 ← canonical_mapping.py:20-42
  8. _status = OK | ANCHOR_UNCERTAIN                           pipeline.py:172-178

call_vlm_with_retry (vlm_client.py:229-258)
  ├─ ValueError → re-raise immediately (parse/validation)      vlm_client.py:252-253
  ├─ any other Exception → up to 3 attempts, exp backoff       vlm_client.py:254-257
  └─ call_vlm (vlm_client.py:122-226)
       ├─ "gemini" in model.lower() → branch                   vlm_client.py:134
       │    ├─ gemini-1.5* → json_mode + response_schema       vlm_client.py:138-179
       │    └─ else → _call_vlm_gemini_freeform (schema JSON injected into prompt,
       │             raw_decode + model_validate_json)         vlm_client.py:47-119, 181-183
       └─ OpenAI/other → with_structured_output(include_raw)   vlm_client.py:185-226
       All paths: estimate_cost_usd()                          vlm_client.py:21-26 ← config.py:36-49
```

### Evaluation / export flows

```
eval_outputs (evaluation.py:74-120)
  ├─ per GT screen: outputs.get(scr) — missing pred silently skipped   evaluation.py:79-81
  ├─ dataset_mismatch_guard(kv, pred)                                  evaluation.py:84 ← normalization.py:174-189
  ├─ CSV_TO_SCHEMA lookup — unknown CSV key silently skipped           evaluation.py:88-90 ← fields.py:56-100
  └─ classify_field → RAW + FILTERED accumulators                      evaluation.py:93-104 ← normalization.py:113-148

build_debug_report (evaluation.py:125-177) → pd.to_csv(sep=";", utf-8-sig)  evaluation.py:172-177
export_to_csv     (evaluation.py:182-239) → prefers canonical_fields; same sink  evaluation.py:186, 234-239
print_cost_summary(evaluation.py:244-258) → reads _meta_agg via .get with defaults

gui_app.py:256 export_to_csv → cwd; gui_app.py:266 eval_outputs; gui_app.py:274 build_debug_report
edge-agent local_extraction_client.py:112-143 export_csv (own csv.writer, union of field keys)
```

### Module dependency layers (import edges verified)

- Leaves: `config.py`, `field_definitions.py`, `page_definitions.py`, `prompts.py`, `llm_factory.py`
- Primitives: `fields.py` (→ field/page defs, `fields.py:3-7`), `schemas.py` (→ fields, `schemas.py:4`),
  `normalization.py` (→ fields, `normalization.py:5`), `imaging.py` (→ config, `imaging.py:9`),
  `vlm_client.py` (→ config, `vlm_client.py:13`), `canonical_mapping.py` (→ fields + page defs, `canonical_mapping.py:5-6`)
- Engines: `pipeline.py` (→ 8 modules, `pipeline.py:8-40`), `evaluation.py` (→ config/fields/normalization, `evaluation.py:6-14`)
- Orchestration: `cli.py` (→ llm_factory/config/pipeline/evaluation, `cli.py:8-29`)
- Facade: `__init__.py` re-exports everything (`__init__.py:11-45` + `47-126`)

---

## Contracts

### Formal (Pydantic — `schemas.py`)

| Model | Location | Fields | Notes |
|---|---|---|---|
| `FieldResult` | `schemas.py:9-13` | `value: Optional[str]`, `confidence: float = 0.0`, `evidence_text`, `section` | **No bounds validator on `confidence`** — accepts NaN, negatives, >1 |
| `Soggetto` | `schemas.py:15-20` | ndg/denominazione/ruolo + confidence/evidence_text | row-level confidence, not per-cell |
| `Fido` | `schemas.py:22-30` | 6 columns + confidence/evidence_text | |
| `Garanzia` | `schemas.py:32-41` | 7 columns + confidence/evidence_text | |
| `FieldsModel` | `schemas.py:46-49` | **dynamically built**: one `Optional[FieldResult]` per key in `FIELD_KEYS` | import-time `create_model`; a `FIELD_KEYS` entry colliding with a Pydantic-reserved name breaks import globally |
| `ExtractionResponse` | `schemas.py:54-58` | fields + soggetti/fidi/garanzie lists | main + retry schema |
| `AnchorFields`/`AnchorResponse` | `schemas.py:60-65` | only ndg + denominazione | anchor-pass schema |
| Legacy aliases | `schemas.py:70-71` | `RESPONSE_SCHEMA`, `ANCHOR_SCHEMA` | kept for callers |

### Structural (untyped dict shapes keyed by string — no model exists)

**Result dict has THREE shape variants** consumers must tolerate:

1. **Normal** (`pipeline.py:104-180`): `model_dump()` of `ExtractionResponse` mutated in place with
   `screen_id`, `attempt` (`vlm_client.py:224-225`), `_meta` (main-pass only, `vlm_client.py:214-223`),
   `_attempts` (list of per-call metas, `pipeline.py:155`), `_meta_agg` (`pipeline.py:330-340`:
   model_main, model_anchor, calls, prompt_tokens, completion_tokens, total_tokens,
   estimated_cost_usd, latency_ms), `_field_sources` (`pipeline.py:141,157`), `canonical_fields`
   (`pipeline.py:168-170`), `_status` (`pipeline.py:175-178`).
2. **Early-exit** (`STOP_ON_ANCHOR_UNCERTAIN`, `pipeline.py:114-124`): `{screen_id, fields:{},
   soggetti:[], fidi:[], garanzie:[], _status:"ANCHOR_UNCERTAIN", _attempts, _meta_agg,
   _field_sources:{}}` — **no `canonical_fields`, no top-level `_meta`, no `attempt`**.
3. **Error** (edge-agent only, `local_extraction_client.py:89-94`): `{screen_id, fields:{},
   _status:"ERROR", _error}` — **no `_meta_agg`, no tables at all**; plus `_page_type`/`_page_no`/
   `_page_confidence` stamped on every edge-agent result (`local_extraction_client.py:96-98`).

Consumers survive variants only via defensive `.get(..., default)`: `evaluation.py:92, 138-139,
186, 202, 250-253`; `local_extraction_client.py:121, 135-139`.

**Per-call `_meta`** (all three VLM paths, `vlm_client.py:107-116, 167-176, 214-223`):
`{model, screen_id, attempt, latency_ms, prompt_tokens, completion_tokens, total_tokens,
estimated_cost_usd}`. The pipeline reads `out["_meta"]` **unguarded** (`pipeline.py:101, 140, 294`) —
every `call_vlm` return must carry it.

**Canonical entry** (`canonical_mapping.py:29-40`): `{schema_key, display_name, page_key,
page_name, value, confidence, evidence_text, section}`, sorted by `PAGE_SHEET_ORDER` index then
display name (`canonical_mapping.py:8-18` ← `page_definitions.py:23-28`).

**Ground-truth dict** (`load_ground_truth`, `evaluation.py:58-69`): `{screen_id: {csv_key: value}}`;
blank/nan keys skipped, nan values → `""`. CSV columns auto-detected from candidate lists
(`evaluation.py:38-52`); missing column → `ValueError` (`evaluation.py:26-31`). Read with pandas
defaults — comma separator, utf-8 (`evaluation.py:35`) — while **both CSV writers emit `sep=";"`
utf-8-sig** (`evaluation.py:172-177, 234-239`): the tool cannot re-read its own output format.

**`eval_outputs` return** (`evaluation.py:116-120`): `{acc_raw, acc_filt, per_field_filt:
{schema_key: [correct, total]}}` — consumed by `gui_app.py:266-269`.

**Edge-agent duck-typed interface** (`local_extraction_client.py:39, 61-110`): `start_job()`,
`ingest_frame(job_id, img, page_no, page_type, confidence, fields_json)`, `requeue_job()`,
`export_csv()` — detected upstream by `hasattr(api_client, "ingest_frame")` (out-of-scope caller).

### Implicit (conventions with no enforcement)

- **Import-order contract**: every env var is read at import time (`config.py:8-56`); `.env` must be
  loaded *before* `import extraction`. `main.py:7` and `local_extraction_client.py:21-25` comply;
  **`gui_app.py:1-14` never calls `load_dotenv`** — it depends on pre-exported env.
- **ChatModel thread-safety**: asserted in comments/docstrings only (`cli.py:181`, `pipeline.py:50`,
  `llm_factory.py:26`); one pipeline instance is shared by up to 12 outer workers (`gui_app.py:244`)
  each spawning up to 3 inner retry workers (`pipeline.py:284`).
- **screen_id ↔ ground truth join key**: screen_id is the filename basename sans extension
  (`cli.py:225, 237`; `pipeline.py:186`) and must literally equal the CSV `Fotogramma` value —
  `eval_outputs` joins on it and silently skips non-matches (`evaluation.py:79-81`). The edge-agent
  fabricates human-readable ids (`"{page} — pag. {n}"`, `local_extraction_client.py:80-81`) that can
  never match a GT row (evaluation is not used on that path).
- **Entry-point selection**: callers must pick `extract_from_screen` (normalizes) vs
  `extract_from_image` (assumes pre-normalized) — `local_extraction_client.py:84-86` documents the
  intent; nothing enforces input size on the raw-image path (`pipeline.py:104-107`).
- **`pick_best` returns an input by identity**: `merge_field_sources` decides source attribution via
  `chosen is candidate` (`normalization.py:105-107`); `pick_best` must never return a copy
  (currently true — `normalization.py:87-96` returns `f1` or `f2` directly).
- **`safe_field` returns a fresh copy** (`normalization.py:60-69`) — mutating its return value does
  NOT write back to the fields dict. The anchor gate violates this contract (see I5).
- **Gemini routing by model-name substring**: `"gemini" in model.lower()` (`vlm_client.py:134`) and
  schema-mode by `"gemini-1.5"` prefix (`vlm_client.py:18, 138`) — provider branch is inferred from
  the *name string*, not from the actual chat model object.
- **Model-name/model-instance pairing**: cost attribution uses the name string passed alongside the
  instance (`pipeline.py:63-64`, `vlm_client.py:105, 165, 212`); a mismatch silently misprices.
- **Facade sync**: a new public symbol must be added to both `__all__` (`__init__.py:11-45`) and an
  import block (`__init__.py:47-126`); `main.py:8` star-imports the facade.
- **Field-config lockstep** (convention only, zero guards): a new field must touch `FIELD_KEYS`
  (`fields.py:12-54`), `CSV_TO_SCHEMA` (`fields.py:56-100`), `AREA_TO_FIELDS` (`config.py:69-82`),
  `CANONICAL_FIELD_DEFINITIONS`/`FIELD_LABEL_ALIASES` (`field_definitions.py:5, 229-235`), and the
  prompts (`prompts.py`). Omission from `AREA_TO_FIELDS` silently disables retry.

---

## Invariants

- **I1 — Post-processing order is load-bearing** (`pipeline.py:144-178`): merge-anchors →
  tipo-normalize → retry → coherence → meta-aggregate → soggetti-flatten → canonical → status.
  Coherence (`pipeline.py:311-328`) must see post-retry fields; the flatten (`pipeline.py:159-166`)
  runs after everything and **unconditionally overwrites** the 12 `ndg_/denominazione_/ruolo_1..4`
  keys from `soggetti[:4]` rows — even with `None` — without touching `_field_sources`.
- **I2 — Call budget**: VLM calls per screen ≤ `MAX_CALLS_PER_SCREEN` = anchor + main + at most
  `max(0, MAX_CALLS_PER_SCREEN - 2)` area retries (`pipeline.py:262-263`). Caveat: each logical call
  may issue up to 3 HTTP attempts (`vlm_client.py:237, 241`), so the *request* count can be 3× the
  nominal budget.
- **I3 — Budget floor (VIOLATED)**: the pipeline implicitly requires `MAX_CALLS_PER_SCREEN >= 3`
  whenever any area is weak: with a value of 1 or 2, `areas_to_retry` is non-empty but the slice is
  empty, and `ThreadPoolExecutor(max_workers=0)` raises `ValueError` at `pipeline.py:284`
  (`pipeline.py:259-263`). Config permits 1/2 (`config.py:54`); `docs/10-configuration-guide.md:180`
  claims 2 "disables retries" — refuted.
- **I4 — Winner selection**: non-null beats null; equal nullness → higher confidence wins, tie keeps
  current (`normalization.py:87-96`). Corollary: a retry can never null-out a non-null main value.
  The soggetti flatten (I1) bypasses `pick_best` entirely and CAN null it.
- **I5 — Anchor confidence gate is dead** (env `ANCHOR_CONF_MIN` affects nothing live): the gate
  mutates the original `fields` dict via `safe_set_field` (`pipeline.py:91-96`) but the function
  returns the pre-gate *copies* from `safe_field` (`pipeline.py:87-88, 98-102`); independently,
  `safe_set_field(value=None)` cannot null a non-null value (`normalization.py:78-79`). The only
  other `ANCHOR_CONF_MIN` consumer is `_is_confident_output` (`cli.py:87-88`), itself reachable only
  from the commented-out dedup call (`cli.py:268-273`).
- **I6 — `_field_sources` accuracy**: holds for all keys via `merge_field_sources`
  (`pipeline.py:301-307`, `normalization.py:98-108`) **except** the 12 flattened soggetti keys
  (`pipeline.py:159-166` never updates it) — the debug report's `source_attempt` column
  (`evaluation.py:151, 164`) is wrong for those keys whenever soggetti rows exist.
- **I7 — Meta aggregation**: `_meta_agg` totals are the sum over `_attempts` (`pipeline.py:330-340`).
  Failed area retries append nothing (`pipeline.py:287-292`), so a screen's `calls` count excludes
  failed retry calls that still consumed API quota.
- **I8 — `_status` domain**: pipeline produces only `"OK" | "ANCHOR_UNCERTAIN"`
  (`pipeline.py:112-124, 175-178`); the edge-agent adds `"ERROR"` (`local_extraction_client.py:92`).
  `_status = OK` requires both `ndg` and `denominazione` non-null *after* all merging.
- **I9 — Confidence domain assumed [0,1], never validated** (`schemas.py:11`): the retry gate
  `< 0.60` (`pipeline.py:255`), `pick_best` (`normalization.py:94-96`), and the dead anchor gate all
  compare it raw; NaN makes every comparison False.
- **I10 — Derived config coherence at import**: `GROUND_TRUTH_CSV = INPUT_DIR/dati.csv`
  (`config.py:8-9`), `DEBUG_CROP_DIR = INPUT_DIR/debug_crops` (`config.py:94`), `FIELD_RETRY_MAP`
  inverted from `AREA_TO_FIELDS` (`config.py:85-88`) — all frozen at first import.
- **I11 — Area-key alignment**: every `AREA_TO_FIELDS` key must exist in `RETRY_AREAS` (crop lookup
  `RETRY_AREAS[area_name]`, `pipeline.py:266`) and in `FIELD_RETRY_PROMPTS` (soft — falls back to
  `PROMPT`, `pipeline.py:277`). Currently aligned on HEADER/BODY/FOOTER (`config.py:63-82`,
  `prompts.py:74-78`); no guard.
- **I12 — Retry selection order is alphabetical, not priority-based**: `sorted({"HEADER","BODY",
  "FOOTER"})` = `["BODY","FOOTER","HEADER"]`, truncated to `allowed_retries` (`pipeline.py:263`) —
  with the default budget of 2, HEADER (identity fields, `config.py:70`) is dropped whenever all
  three areas are weak.

---

## Domain Rules

- **45 Italian banking field keys** (`fields.py:12-54`) are the schema's single source of truth;
  keys are Italian domain terms and must not be translated (they must match `CSV_TO_SCHEMA` headers,
  `fields.py:56-100`, and `FIELD_LABEL_ALIASES`, `field_definitions.py:229-235`).
- **9 BPER screens map to 4 canonical pages** (`page_definitions.py:5-10`): risultato_ricerca,
  elenco_soggetti, gestione_fidi_e_garanzie, note_da_richiesta; sheet order fixed at
  `page_definitions.py:23-28`.
- **Crop geometry** (`config.py:58-67`): content excludes the left nav (x < 0.18) and top bar
  (y < 0.12); anchors live in the top 22% of content; retry crops overlap deliberately (BODY
  0.25–0.75 vs FOOTER 0.65–1.00).
- **Tipo canonicalization**: "mutui spesa"/"mutuo spesa"/"bpi mutui" → "BPI Mutui"
  (`TIPO_MAPPING`, `normalization.py:10-23`); applied after the main pass (`pipeline.py:146`) and to
  each BODY/HEADER retry candidate for `tipo` (`pipeline.py:298-299`).
- **Coherence repairs** (`pipeline.py:311-328`): a non-null `tooltip_evidenze_b` forces
  `evidenze = "B"` when the current value is nullish *or purely numeric* (`pipeline.py:317-322`); a
  non-null `tooltip_descrizione_bmb` forces `tipo = "BMB"` only when tipo is nullish
  (`pipeline.py:324-328`). Note: the tooltips themselves belong to no retry area
  (`config.py:69-82`), so these repair inputs are main-pass-only.
- **Numeric vs text comparison**: a field is numeric if its key *contains* "importo_euro", "ndg", or
  "n_fido" (`normalization.py:127-128`) — substring semantics deliberately capture `ndg_1..4`.
  Numeric equality uses `norm_number_str` (strips €/spaces, resolves Italian `1.234,56` →
  `1234.56`, `normalization.py:40-55`); text equality uses whitespace-collapsed lowercase
  (`normalization.py:34-38`) with fuzzy fallback ratio ≥ 0.85 for texts > 20 chars
  (`normalization.py:142-146`).
- **Nullish vocabulary**: `"", "n/d", "nd", "---", "null", "none", "nan"` (`normalization.py:28-32`)
  — used by retry gating, pick_best, classification, and the mismatch guard.
- **Classification statuses**: OK / WRONG / MISSING / HALLUCINATED / OK_NULL
  (`normalization.py:113-148`); `build_debug_report` overrides all of a screen's rows to
  `DATASET_MISMATCH` when the guard fires (`evaluation.py:148-149`).
- **Dataset mismatch guard** (`normalization.py:174-189`): compares GT `NDG`/`Denom.` against
  extracted fields, falling back to `soggetti` rows (`normalization.py:162-172`); any confident
  mismatch removes the screen from FILTERED metrics (`evaluation.py:84, 99-104`).
- **Anchor prompt ↔ gate coupling**: the prompt instructs confidence ≥ 0.95 only when clearly
  readable (`prompts.py:36`) matching `ANCHOR_CONF_MIN` default 0.95 (`config.py:56`) — the gate
  that would consume this is dead (I5).
- **Only the first 4 soggetti** are flattened to scalar fields (`pipeline.py:161`); further rows
  survive only inside the `soggetti` table.
- **Retry coverage rule**: `creazione` and the five `tooltip_*` fields belong to no area
  (`config.py:69-82` vs `fields.py:18, 28-32`) — 6 of 45 fields can never be retried, silently.
- **Language policy**: prompts and UI strings Italian (`prompts.py:3-71`), identifiers English;
  the VLM must answer JSON-only (enforced structurally by Pydantic binding, `vlm_client.py:147, 193`,
  or prompt-injected schema for newer Gemini, `vlm_client.py:63-67`).

---

## Assumptions

### Verified (enforced by code or confirmed by reading)

- `FieldsModel` always mirrors `FIELD_KEYS` — derived at import (`schemas.py:46-49`).
- Provider/model family mismatch is rejected at construction (`llm_factory.py:49-53, 59-63`);
  unknown provider raises (`llm_factory.py:77`); missing key raises (`llm_factory.py:41-44`).
- Ground-truth CSV column presence is validated (`evaluation.py:26-31`).
- Batch paths are existence-filtered with a warning (`cli.py:214-217`).
- Callbacks fire on the calling thread: both the `as_completed` loop and the serial loop run in the
  thread that called `run()` (`cli.py:235-251, 253-266`), matching the documented contract
  (`cli.py:162-163, 296-297`).
- `pick_best` returns one of its inputs by identity (`normalization.py:87-96`) — the
  `chosen is candidate` check in `merge_field_sources` is currently sound.
- ValueError is never retried; everything else is retried ≤ 3× (`vlm_client.py:252-257`).

### Documented but not enforced

- **ChatModel instances are thread-safe and shareable** (`cli.py:181`, `pipeline.py:50`,
  `llm_factory.py:26`) — stated in comments; no runtime guard, no serialization.
- **Edge-agent pre-normalizes frames** before `extract_from_image` (`local_extraction_client.py:84-86`
  comment; CLAUDE.md constraint 12) — nothing in `extraction/` checks image dimensions.
- **`gui_app.py` requires pre-exported env vars** (CLAUDE.md; verified absent `load_dotenv`,
  `gui_app.py:1-14`).
- **`_deduplicate_same_page_outputs` is parked "until page_key mapping is validated"**
  (`cli.py:268-273` comment) — its ~115-line helper cluster (`cli.py:36-152`) is live-looking but
  unreachable.
- **Anchor gate documented as "ineffective"** (CLAUDE.md) — confirmed dead by two independent
  mechanisms (I5), which is stronger than documented.

### Unverified (implicit, no statement and no check)

- `confidence ∈ [0,1]` and non-NaN (`schemas.py:11`; consumers at `pipeline.py:255`,
  `normalization.py:94-96`, `cli.py:72, 87-88`).
- `MAX_CALLS_PER_SCREEN >= 3` (crash otherwise — I3).
- Provider responses always carry `usage_metadata` (`vlm_client.py:102-104, 162-164, 209-211`
  default tokens to 0 → cost silently 0).
- `LLM_MODEL` appears in `PRICING_PER_1M` (`vlm_client.py:23-25` returns $0.00 for unknown names;
  `LLM_MODEL` is free-form, `config.py:18`).
- `AREA_TO_FIELDS` values ⊆ `FIELD_KEYS` — a typo creates a phantom `result["fields"]` entry that
  no schema/eval/export reads (`pipeline.py:296-307`, `config.py:69-82`).
- `AREA_TO_FIELDS` keys ⊆ `RETRY_AREAS` keys — otherwise `KeyError` at `pipeline.py:266`.
- Screenshot filenames match GT `Fotogramma` ids exactly (`evaluation.py:79-81` silently skips).
- Model-name substring routing ("gemini" in name → Gemini API path, `vlm_client.py:134`) never
  misfires for a differently-named deployment.
- The GT CSV is comma-separated UTF-8 (`evaluation.py:35` uses pandas defaults; Italian Excel
  exports default to `;` — would collapse to one column and raise "Cannot find screen column").
- Tkinter calls from the worker thread are safe: `run_process` runs in a plain `threading.Thread`
  (`gui_app.py:225`) and calls `messagebox.showinfo`/`showerror` and `self.log` directly from it
  (`gui_app.py:279, 283`); only `display_results` is marshalled via `self.after` (`gui_app.py:278`).
- No global concurrency ceiling exists across nested pools (up to 12 × 3 concurrent VLM calls,
  `gui_app.py:244` × `pipeline.py:284`).

---

## Integration Hot-Spots

1. **The result dict (string-keyed, 3 shape variants)** — produced at `pipeline.py:104-180`,
   `pipeline.py:112-124`, `local_extraction_client.py:89-94`; consumed by `evaluation.py`
   (`:92, 138-151, 186-232, 250-257`), `gui_app.py:250-278`, `local_extraction_client.py:112-143`,
   and edge-agent UI tabs (out of scope). The highest-traffic untyped boundary in the system.
2. **`run_extraction_batch` / `BatchRunner`** (`cli.py:158-307`) — shared by `main()` (`cli.py:333`)
   and the Tkinter GUI (`gui_app.py:238-247`); GUI passes `max_workers=min(len(paths), 12)` vs CLI
   default 4; parallel/serial error semantics diverge (`cli.py:246-251` vs `:261-266`).
3. **`ExtractionPipeline.extract_from_image`** — the edge-agent boundary
   (`local_extraction_client.py:86`); synchronous in the capture QThread; unbounded input image
   size; result crosses threads via Qt signal (`local_extraction_client.py:106`).
4. **Import-time env configuration** (`config.py:8-56`) — coupling between `.env` loading order and
   every constant; three loaders (`main.py:7`, `edge-agent`, `local_extraction_client.py:21-25`) and
   one non-loader (`gui_app.py`).
5. **LangChain structured-output seam** (`vlm_client.py:122-226`) — three provider paths with
   different failure modes; `include_raw=True` parsing-error handling (`vlm_client.py:152-156,
   199-203`); Gemini free-form path injects the JSON schema into the prompt (`vlm_client.py:63-67`).
   Provider/library API drift lands here first.
6. **Ground-truth CSV boundary** (`evaluation.py:33-69`) — column auto-detection, pandas default
   separator/encoding, and the screen_id join key; the CLI hard-requires the file
   (`cli.py:315-316`) and it is absent from the repo.
7. **CSV/Excel export sinks** (`evaluation.py:172-177, 234-239`; `local_extraction_client.py:131-143`)
   — untrusted OCR-derived values written verbatim into files intended to be opened in Excel.
8. **Cost telemetry chain** — `PRICING_PER_1M` (`config.py:36-49`) → `estimate_cost_usd`
   (`vlm_client.py:21-26`) → per-call `_meta` → `_aggregate_meta` (`pipeline.py:330-340`) →
   `print_cost_summary` (`evaluation.py:244-258`). Two silent-zero paths (unknown model, missing
   usage_metadata).
9. **The `__init__.py` facade** (`__init__.py:11-126`) — `main.py:8` star-imports it; `gui_app.py:6-14`
   imports 7 symbols; any rename or missed re-export breaks external consumers at import time.
10. **`create_chat_model`** (`llm_factory.py:16-77`) — the single model-construction chokepoint with
    two call sites (`cli.py:182-191`, `local_extraction_client.py:47-48`); key resolution order
    `api_key` arg → `LLM_API_KEY` → legacy per-provider var (`llm_factory.py:30-40`).

---

## Change Impact Radius

| If you touch… | Also check… |
|---|---|
| `FIELD_KEYS` (`fields.py:12-54`) | `FieldsModel` auto-adapts (`schemas.py:46-49`); `AREA_TO_FIELDS` (`config.py:69-82` — omission = silently never retried); `CSV_TO_SCHEMA` (`fields.py:56-100` — omission = never evaluated); `CANONICAL_FIELD_DEFINITIONS` + `FIELD_LABEL_ALIASES` (`field_definitions.py:5, 229-235` — omission = raw key shown, no page grouping); prompts (`prompts.py`); Pydantic reserved-name collision (import-time failure) |
| `AREA_TO_FIELDS` / `RETRY_AREAS` (`config.py:63-82`) | key alignment (`pipeline.py:266` KeyError); `FIELD_RETRY_PROMPTS` (`prompts.py:74-78`, soft fallback `pipeline.py:277`); `_merge_tables` special-cases `"BODY"` only (`pipeline.py:227`); derived `FIELD_RETRY_MAP` (`config.py:85-88`) |
| Result-dict keys/shape (`pipeline.py:104-180`) | `evaluation.py:92, 138-151, 186-232, 250-257`; `gui_app.py:250-278`; `local_extraction_client.py:96-143`; edge-agent UI tabs; the two alternate shapes (`pipeline.py:112-124`, `local_extraction_client.py:89-94`) must stay `.get`-compatible |
| `_meta` shape (`vlm_client.py:107-116, 167-176, 214-223`) | `_aggregate_meta` key names (`pipeline.py:330-340`); `print_cost_summary` (`evaluation.py:250-253`); debug-report columns (`evaluation.py:165-168`); unguarded `out["_meta"]` reads (`pipeline.py:101, 140, 294`) |
| `pick_best` / `safe_set_field` / `safe_field` (`normalization.py:60-108`) | retry merge (`pipeline.py:296-307`); anchor gate (`pipeline.py:87-96` — currently dead, easy to half-fix); coherence check (`pipeline.py:311-328`); identity-based source attribution (`normalization.py:105-107`) |
| `classify_field` / normalizers (`normalization.py:28-148`) | accuracy metrics semantics (`evaluation.py:93-104`); mismatch guard (`normalization.py:185-188` uses the same normalizers); numeric-field substring list (`normalization.py:127`) |
| `config.py` env constants | read-at-import — takes effect only before first `import extraction`; `INPUT_DIR` cascades to `GROUND_TRUTH_CSV` and `DEBUG_CROP_DIR` (`config.py:8-9, 94`); `MAX_CALLS_PER_SCREEN` floor (I3) |
| `create_chat_model` (`llm_factory.py:16-77`) | both construction sites (`cli.py:182-191`, `local_extraction_client.py:47-48`); provider-name validation; `PROVIDER_MODELS` GUI dropdown (`config.py:22-33`, `gui_app.py:72-87`); pricing table coverage (`config.py:36-49`) |
| `__init__.py` exports | `main.py:8` star import; `gui_app.py:6-14`; `__all__` vs import-block sync (`__init__.py:11-45` vs `47-126`) |
| CSV writers (`evaluation.py:172-177, 234-239`) | downstream Excel workflow (`sep=";"`, utf-8-sig); `gui_app.py:256, 274` writes to cwd; edge-agent has its own writer (`local_extraction_client.py:131-143`) that would NOT inherit changes |
| Prompts (`prompts.py`) | anchor prompt's confidence-0.95 instruction is coupled to `ANCHOR_CONF_MIN` (`prompts.py:36`, `config.py:56`); retry prompts keyed by area name; Gemini free-form path re-wraps the prompt (`vlm_client.py:64-68`) |

---

## Reviewer Hints

### security

- **CSV/formula injection at the export sinks** — `evaluation.py:172-177` and `:234-239` write
  OCR-derived `value`/`pred_value`/`evidence_text` verbatim via `pd.DataFrame(...).to_csv(...)`;
  no escaping of leading `=`, `+`, `-`, `@` (CWE-1236). Same class of sink re-implemented in
  `local_extraction_client.py:131-143`. The intended workflow is opening these in Italian Excel.
- **Prompt-injection surface = the screenshot itself** — rendered text is interpreted alongside the
  system prompt (`vlm_client.py:186-192`); structured output constrains shape, not content
  (`vlm_client.py:147, 193`); the Gemini free-form path concatenates prompt + schema + image with no
  separation (`vlm_client.py:63-74`). Injected values flow untouched into `_coherence_check`
  (`pipeline.py:311-328`), evaluation, and the exports above.
- **API-key flow** — resolution order `llm_factory.py:30-40`; deprecation warning names only the
  var (`llm_factory.py:36-40`); error strings omit the key (`llm_factory.py:41-44, 50-53, 59-63`);
  `_debug_log` prints provider/model only (`cli.py:198-205`). GUI holds the key in a Tkinter
  `StringVar` pre-filled from env (`gui_app.py:24`) and passes it per-batch (`gui_app.py:240`).
- **Gemini safety filters hard-disabled** — all four `HARM_CATEGORY_* = BLOCK_NONE`
  (`llm_factory.py:64-71`); deliberate posture for banking-UI OCR, undocumented in code.
- **Banking PII at rest** — full extraction results (values + evidence text) are JSON-dumped to
  `INPUT_DIR` (`cli.py:337-340`) and cwd (`gui_app.py:250-254`); `DEBUG_SAVE_CROPS=1` writes raw
  screenshot crops to `INPUT_DIR/debug_crops` (`imaging.py:37-42`, `config.py:93-94`).

### architecture

- **Nested unbounded fan-out** — outer batch pool (`cli.py:229-234`; up to 12 from
  `gui_app.py:244`) × inner retry pool (`pipeline.py:284`; up to 3) with no global throttle; shared
  ChatModel thread-safety is comment-only (`cli.py:181`, `pipeline.py:50`).
- **Parallel vs serial error-semantics divergence** — same input, partial results
  (`cli.py:246-251`) vs hard abort (`cli.py:261-266`), selected by `PARALLEL_ENABLED`.
- **Untyped tri-shape result contract** — `pipeline.py:104-180` vs `:112-124` vs
  `local_extraction_client.py:89-94`; every consumer defends independently with `.get`. Check any
  new consumer/producer keeps all three shapes survivable.
- **Import-time config coupling** — `config.py:8-56`; the `gui_app.py` no-`load_dotenv` gap; any
  new entry point must load env before `import extraction`.
- **Dual pipeline entries by design** — `extract_from_screen` (normalizing, `pipeline.py:182-187`)
  vs `extract_from_image` (raw, `pipeline.py:104`); no size enforcement on the raw path; verify new
  callers pick correctly.
- **Two model-construction sites** both routed through `create_chat_model` (`cli.py:182-191`,
  `local_extraction_client.py:47-48`) — the single-factory constraint holds today; watch for a third.
- **Facade discipline** — `__all__` and import blocks must move together (`__init__.py:11-45`,
  `47-126`); `main.py` star-imports.

### logic-integrity

- **I5: dead anchor gate (two independent kill mechanisms)** — copies from `safe_field`
  (`pipeline.py:87-88`) discarded at `:98-102`; `safe_set_field` can't null non-null
  (`normalization.py:78-79`). `ANCHOR_CONF_MIN` tunes nothing live; low-confidence anchors feed the
  main-pass hint (`pipeline.py:205-208`) and bias it.
- **I3: `MAX_CALLS_PER_SCREEN ∈ {1,2}` crashes** — empty slice + `ThreadPoolExecutor(max_workers=0)`
  (`pipeline.py:259-263, 284`); parallel batch then yields zero results silently
  (`cli.py:246-251`); docs claim clean disable (`docs/10-configuration-guide.md:180`).
- **I12: alphabetical retry truncation starves HEADER** — `sorted(...)[:allowed]`
  (`pipeline.py:263`); HEADER owns ndg/denominazione/tipo/stato/fase/evidenze (`config.py:70`).
- **I1/I4 collision: soggetti flatten destroys retry wins** — BODY retry targets `ndg_1..ruolo_4`
  (`config.py:71-80`) and merges via `pick_best` (`pipeline.py:296-307`), then step 7 overwrites the
  same keys from `soggetti` rows with no null check and no `_field_sources` update
  (`pipeline.py:159-166`) — retry-recovered values can be replaced by `None`, and the debug report
  mis-attributes the source (`evaluation.py:151`).
- **Retry coverage hole feeds the coherence check** — `creazione` + 5 `tooltip_*` in no area
  (`config.py:69-82` vs `fields.py:18, 28-32`), yet `_coherence_check` repairs `evidenze`/`tipo`
  *from those tooltips* (`pipeline.py:317-328`): the repair inputs are main-pass-only, unretryable.
- **NaN/out-of-range confidence flips decisions silently** — no validator (`schemas.py:11`);
  all-False comparisons at `pipeline.py:255` and `normalization.py:94-96`.
- **Identity-dependent source tracking** — `chosen is candidate` (`normalization.py:105-107`);
  any future `pick_best` change that copies/merges dicts breaks `_field_sources` without failing.
- **`_merge_tables` dead branch** — `elif len(old)==0 and len(new)>0` unreachable after
  `len(new)>len(old)` (`pipeline.py:236-241`); BODY-only guard at `:227`.
- **Silent denominator drift in metrics** — screens without predictions skipped
  (`evaluation.py:79-81`); CSV keys missing from `CSV_TO_SCHEMA` skipped (`evaluation.py:88-90`);
  accuracy percentages can look stable while coverage shrinks.
- **Coarse transient/permanent error split** — only `ValueError` is permanent
  (`vlm_client.py:252-253`): auth errors retried 3× with sleeps; a one-off malformed Gemini JSON
  (`vlm_client.py:91-98`) is permanent and kills the screen.
- **Failed retries invisible** — swallowed to stdout warning, no meta record (`pipeline.py:287-292`;
  interacts with I7 call-count under-reporting).
- **GT/pred CSV dialect asymmetry** — reader uses pandas defaults (`evaluation.py:35`), writers emit
  `sep=";"` (`evaluation.py:172-177, 234-239`); Italian `;`-separated GT input fails column
  detection (`evaluation.py:26-31`).

### hygiene

- **~115-line dead dedup cluster** — `_has_meaningful_value`, `_extract_page_key`, `_output_score`,
  `_is_confident_output`, `_deduplicate_same_page_outputs` (`cli.py:36-152`) reachable only from the
  commented call (`cli.py:268-273`).
- **Orphan helpers** — `_prepare_content_image` never called (`pipeline.py:193-200`);
  `get_screenshot_paths` (`config.py:99-109`, with function-body `import re` at `:100`) reached only
  via the equally-unused alias `infer_screenshots_from_gt` (`evaluation.py:19-21`).
- **`FIELD_RETRY_MAP` built and exported but consumed nowhere** — `config.py:85-88`,
  `__init__.py:15, 57`; pipeline iterates `AREA_TO_FIELDS` directly (`pipeline.py:252, 296`).
- **Unused imports (linter-verifiable)** — `cli.py:25-27` `eval_outputs`, `build_debug_report`,
  `print_cost_summary` (main uses the `Evaluator` methods instead, `cli.py:343-347`);
  `normalization.py:5` `FIELD_KEYS`, `_SOGGETTI_KEY_MAP`; `evaluation.py:2-4, 9-10` `os`, `json`,
  `Tuple`, `norm_text`, `norm_number_str`; `schemas.py:2` `Union`, `Dict`, `Any`.
  `_GARANZIE_KEY_MAP` (`fields.py:108-116`) has zero importers repo-wide.
- **Stale docstrings** — `run_extraction_batch` says "Shared by CLI (main) and Streamlit (app.py)"
  (`cli.py:296`); the facade docstring cites `app.py` (`__init__.py:3`); the real second consumer is
  Tkinter `gui_app.py`. `streamlit` lingers in `requirements.txt` with no importer.
- **Bare `except:`** — `normalization.py:54` (catches KeyboardInterrupt/SystemExit; silently returns
  raw string into numeric comparison).
- **Hardcoded vs env-tunable threshold inconsistency** — live retry gate `0.60` is a literal
  (`pipeline.py:255`); the dead anchor gate is env-driven (`config.py:56`).
- **Duplicated warnings-filter boilerplate** — `__init__.py:7-9` and `main.py:3-5`.
- **Naming/style baseline for consistency checks** — full-width section markers, `UPPER_SNAKE_CASE`
  constants, `_leading_underscore` privates, full type annotations (see `.deep-dive/01-structure.md`
  Naming Conventions; verified representative samples `imaging.py:12`, `normalization.py:71`,
  `fields.py:102-116`).
