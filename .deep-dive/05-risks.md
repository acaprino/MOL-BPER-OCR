# Phase 5: Pattern & Risk Detection

Scope: `extraction/` package (15 files, ~2,442 LoC). Domain: multi-pass Vision-LLM
extraction from Italian banking screenshots. Every claim below is cited to `file:line`
and was verified against the current source. External consumers (`main.py`,
`gui_app.py`, `edge-agent/local_extraction_client.py`) are referenced only to size blast
radius; all findings live in `extraction/`.

Legend for the six CLAUDE.md-documented quirks: **[CONFIRMED]** verified as described,
**[REFINED]** true but the real behaviour is worse/different than documented,
**[REFUTED]** documentation is wrong.

---

## Anti-Patterns Found

### CRITICAL

**A1. Config-triggered crash: `ThreadPoolExecutor(max_workers=0)` when `MAX_CALLS_PER_SCREEN <= 2`** — `pipeline.py:262,284`
`allowed_retries = max(0, MAX_CALLS_PER_SCREEN - 2)`. When the env var is set to `1` or `2`,
`allowed_retries == 0`, so `areas_to_retry_list = sorted(areas_to_retry)[:0] == []`
(`pipeline.py:263`). The early `return` at `pipeline.py:259` is **not** reached, because
`areas_to_retry` (the set) is almost always non-empty (any nullish or `< 0.60`-confidence
field adds an area, `pipeline.py:255`). Execution then hits
`with ThreadPoolExecutor(max_workers=len(areas_to_retry_list))` == `max_workers=0`, which
raises `ValueError: max_workers must be greater than 0` at construction.
- **Failure scenario:** an operator sets `MAX_CALLS_PER_SCREEN=2` to "disable retries and
  save cost". Every screen with at least one weak field (i.e. essentially all of them)
  throws; the exception propagates through `extract_from_image` → `_worker` and is caught
  per-screen (`cli.py:246`/`261`), so the whole batch silently produces **zero** results
  (or, in the sequential no-callback path, re-raises and aborts, `cli.py:266`).
- **Documentation contradiction:** `docs/10-configuration-guide.md:180` explicitly states
  "Con `2` i retry sono disabilitati del tutto" (with `2`, retries are disabled entirely).
  The code does the opposite — it crashes. **This is a REFUTED doc claim with a live crash.**
- Fix: guard `if allowed_retries == 0 or not areas_to_retry_list: return`, or clamp
  `max_workers=max(1, len(areas_to_retry_list))`.

### HIGH

**A2. Anchor confidence gate is dead code — doubly broken [REFINED]** — `pipeline.py:86-102`, `normalization.py:78-79`
CLAUDE.md says the `ANCHOR_CONF_MIN` gate is "ineffective". It is actually broken by **two
independent mechanisms**, either of which alone kills it:
  1. `ndg`/`den` are bound to **copies** returned by `safe_field()` (`pipeline.py:87-88`);
     `safe_field` builds a fresh dict (`normalization.py:60-69`). The gate then calls
     `safe_set_field(fields, ...)` which mutates the *original* `fields` dict
     (`pipeline.py:92-96`), but the function returns the copies `ndg`/`den`
     (`pipeline.py:98-102`). The mutation is discarded.
  2. Even targeting the right object, `safe_set_field(..., value=None)` cannot null a
     non-null value: `if value is not None or f.get("value") is None`
     (`normalization.py:78`) is `False` when `value=None` and the field already holds a
     value.
- **Failure scenario:** a hallucinated NDG with `confidence=0.30` is meant to be zeroed but
  flows into the main-pass hint (`"NDG atteso: {value}"`, `pipeline.py:206`) and into the
  final `ndg` field, biasing the model toward a wrong anchor and defeating
  `dataset_mismatch_guard`.
- Note: `ANCHOR_CONF_MIN` also drives the (dead) `_is_confident_output` (`cli.py:87-88`),
  so tuning this env var currently affects **nothing** in any live path.

**A3. Retry area priority is alphabetical, starving HEADER** — `pipeline.py:263`
`areas_to_retry_list = sorted(areas_to_retry)[:allowed_retries]`. `sorted({"HEADER","BODY","FOOTER"})`
== `["BODY","FOOTER","HEADER"]`. With the default `MAX_CALLS_PER_SCREEN=4`,
`allowed_retries=2`, so when all three areas need a retry, HEADER is **truncated away**.
- **Failure scenario:** HEADER owns the highest-value fields (`ndg`, `denominazione`,
  `tipo`, `stato`, `fase`, `evidenze`, `filiale_relazione`, `ultima_validazione_scheda`,
  `config.py:70`). On a low-quality screen where all areas are weak, the two least critical
  areas (BODY, FOOTER) get the retry budget and the identity fields never do. Retry
  ordering is accidental (string sort), not importance-based.

**A4. Soggetti flatten unconditionally overwrites retry results with `None` [REFINED]** — `pipeline.py:159-166`
The flatten runs at step 7, **after** the BODY retry (step 4) that also targets
`ndg_1..ruolo_4` (`config.py:71-80`). For each `soggetti[:4]` row it writes
`result["fields"][f"ndg_{idx}"] = {"value": s.get("ndg"), ...}` with **no null check**.
- **Failure scenario (data loss):** the BODY retry successfully recovers `ndg_1 = "12345"`,
  but the main pass produced one `soggetti` row with `ndg=None`. The flatten overwrites the
  good retry value with `None`. CLAUDE.md documents the overwrite and the missing
  `_field_sources` update, but not that it can **destroy a value a retry just recovered**.
- Compounding: `_field_sources` still reports `CONTENT_MAIN`/`RETRY_BODY` for these keys
  (`pipeline.py:161-166` never touches `field_sources`), so the debug report
  (`evaluation.py:151`) attributes a soggetti-sourced value to the wrong pass.

### MEDIUM

**A5. Bare `except:` swallows everything** — `normalization.py:54`
`norm_number_str` wraps `float(s)` in `try/except:` with no exception type, catching
`KeyboardInterrupt` and `SystemExit` too. It also hides genuinely malformed numeric input
by silently returning the raw string, which then flows into `classify_field` numeric
comparison (`normalization.py:127-133`) and can mislabel OK/WRONG.

**A6. Inconsistent error handling between parallel and sequential batch paths** — `cli.py:246-251` vs `261-266`
Parallel path: on worker exception, if no `on_error` callback, it **prints and continues**
(`cli.py:250-251`). Sequential path: same condition **re-raises** (`cli.py:266`). Identical
inputs produce a partial result set in parallel mode and a hard abort in serial mode — a
correctness-affecting divergence driven only by `PARALLEL_ENABLED`.

**A7. Unreachable branch in `_merge_tables`** — `pipeline.py:240-241`
`elif len(old_data) == 0 and len(new_data) > 0:` can never fire: if `old==0` and `new>0`
then `len(new) > len(old)` already matched the first branch (`pipeline.py:236-237`). Dead
logic that misleads readers into thinking empty-table replacement is specially handled.

**A8. Confidence values never validated or clamped** — `schemas.py:11`, `pipeline.py:255`, `normalization.py:94-96`
`FieldResult.confidence: float = 0.0` has no bounds validator. The VLM can return `>1.0`,
`<0`, or `NaN`. `NaN` breaks every comparison (`< 0.60`, `pick_best`'s `c1 >= c2`) because
all `NaN` comparisons are `False`, silently flipping retry and winner-selection decisions.

---

## Red Flags

### Security

**S1. CSV / formula injection into exported spreadsheets** — `evaluation.py:172-177,234-239`
`build_debug_report` and `export_to_csv` write LLM-extracted `value`/`pred_value` fields
straight to CSV with `pd.DataFrame(...).to_csv(...)` and **no formula-escaping**. Values
originate from OCR of an untrusted screenshot, so a cell text like `=cmd|'/c calc'!A1`,
`+HYPERLINK(...)`, `-2+3`, or `@SUM(...)` is written verbatim. Opening the CSV/`utf-8-sig`
file in Excel (the intended Italian-banking workflow) executes it. CWE-1236.
- Blast radius extends downstream: the edge-agent writes the same untrusted values to
  `.xlsx` via `df.to_excel(..., engine="openpyxl")` (`edge-agent/ui/data_table_tab.py:381,394`)
  and to CSV (`edge-agent/local_extraction_client.py:112-137`). Mitigation belongs at the
  extraction sink so all consumers inherit it (prefix risky leading chars with `'`).

**S2. Prompt-injection surface via screenshot content** — `vlm_client.py:186-192`, `prompts.py`
The image is the untrusted input; its rendered text is interpreted by the VLM alongside the
system prompt. Structured output (`with_structured_output`, `vlm_client.py:193`) constrains
the *shape* of the response but not the *content* of field values — injected instruction
text inside a screenshot ("ignora le istruzioni…") can still steer the free-form `value`
strings that are later trusted by `_coherence_check`, evaluation, and exports. There is no
allow-list or post-hoc validation of extracted values. Low exploitability (no tool/code
execution off the value), but it feeds directly into S1.

**S3. API-key handling — acceptable, one note** — `llm_factory.py:30-44`
Keys are read from `api_key` arg → `LLM_API_KEY` → legacy `OPENAI_API_KEY`/`GEMINI_API_KEY`
(`llm_factory.py:30-40`) and never logged; `_debug_log` prints provider/model only
(`cli.py:198-205`), and `ValueError` messages omit the key (`llm_factory.py:41-44,50-53,59-63`).
No leak found in-scope. Residual: the key is embedded in shared `ChatModel` instances held
for the batch lifetime and passed across every worker thread — fine, but it means a memory
dump / exception with `repr(chat_model)` in some LangChain versions could surface it.

**S4. Gemini safety filters hard-disabled** — `llm_factory.py:64-71`
All four `HARM_CATEGORY_*` are set to `BLOCK_NONE`. Reasonable for OCR of banking UIs
(avoids false refusals), but it means any adversarial image content is passed through
unfiltered. Document the intent; it is a deliberate posture, not an accident.

### Reliability

**R1. Thread-safety is an unverified assumption, and fan-out is unbounded** — `cli.py:181-197`, `pipeline.py:284-285`
The shared-`ChatModel`-across-workers assumption (`cli.py:161`, `pipeline.py:50`) is stated
but not enforced anywhere in code. Worse, pools **nest**: the outer batch pool
(`cli.py:233`, up to `PARALLEL_WORKERS=4`, or `min(len(images), 12)` from the GUI,
`gui_app.py:244`) each spawns an inner retry pool of up to 3 (`pipeline.py:284`). Worst
case: 12 × 3 = 36 concurrent VLM calls plus anchor/main. No global concurrency ceiling,
so this reliably trips provider rate limits under load.

**R2. Transient vs permanent error classification is coarse** — `vlm_client.py:252-257`
`call_vlm_with_retry` re-raises `ValueError` immediately (parse/validation) and retries
**everything else** up to 3× with backoff. Consequences:
  - A `401 Unauthorized` / bad-key error is non-`ValueError`, so it is retried 3× with
    sleeps before finally raising — slow, pointless.
  - A `.model_dump()` on a `None` parsed result (if `parsing_error` were ever falsy with
    `parsed=None`) raises `AttributeError`, is treated as transient, retried, then surfaced
    as an opaque `AttributeError` (`vlm_client.py:205-207`).
  - A one-off malformed JSON from Gemini (`_extract_json_str`/`model_validate_json`,
    `vlm_client.py:91-98`) raises `ValueError` and is **not** retried — a recoverable blip
    becomes a hard screen failure.

**R3. Cost tracking silently under-counts [CONFIRMED]** — `vlm_client.py:21-26`, `config.py:36-49`
`estimate_cost_usd` returns `0.0` for any model absent from `PRICING_PER_1M`. Since
`LLM_MODEL` is free-form (`config.py:18`), a current-but-unlisted name
(e.g. `gpt-4o-2024-11-20`, `gemini-2.5-flash`) zeroes the cost report rather than warning.
Additionally, if `usage_metadata` is missing/renamed by a provider
(`vlm_client.py:102-104,209-211` default to `0`), tokens and therefore cost also read `0`.
Both silently violate the "every VLM call must populate `_meta.estimated_cost_usd`"
architectural constraint.

**R4. Non-transient exceptions in retry threads are swallowed to a warning** — `pipeline.py:287-292`
A failed area retry only prints `Warning: retry {area} … failed` and continues. Intended
(non-fatal), but combined with R3 there is no structured signal — a systematic retry
failure (e.g. every BODY retry 500s) is invisible unless someone reads stdout.

### Performance

**P1. Lossless PNG payloads on every call** — `imaging.py:31-34`, `pipeline.py:75,128,276`
Every VLM call encodes the crop as PNG (`img_to_png_bytes`) and base64s it
(`vlm_client.py:132`). PNG is lossless and large; a 1800px-long-side content crop can be
multiple MB, inflating input tokens and latency on the main pass and each retry. No JPEG/
downscale option for image payloads.

**P2. `extract_from_image` bypasses `normalize_image`, so caller image size is unbounded** — `pipeline.py:104-107`
`extract_from_screen` downscales to 1800px (`imaging.py:12-16`) but `extract_from_image`
(the edge-agent entry, `pipeline.py:104`) does not. A 4K frame's `CONTENT_CROP` is sent at
full resolution. This is by design (CLAUDE.md constraint 12: edge-agent pre-processes), but
nothing in `extraction/` enforces a max dimension, so a mis-wired caller can push oversized
images and hit provider image-size limits or extreme token bills.

**P3. `normalize_image` only ever shrinks** — `imaging.py:14-16`
`if scale < 1.0` — small screenshots are never upscaled before the contrast/unsharp pass,
so low-DPI captures get no resolution help even though OCR accuracy is the goal.

---

## Technical Debt Inventory

**D1. `_deduplicate_same_page_outputs` and its helper cluster are dead [CONFIRMED]** — `cli.py:36-152`, call commented at `cli.py:268-273`
The call is commented "TEMP TEST … until page_key mapping is validated". This orphans
`_deduplicate_same_page_outputs` (`cli.py:92-152`) plus its exclusive dependencies
`_extract_page_key` (`45-51`), `_output_score` (`54-74`), `_is_confident_output` (`77-89`),
and `_has_meaningful_value` (`36-42`) — roughly **115 lines** reachable only through the
commented call. `_output_score` returns a tuple compared with `>` (`cli.py:137`) — works,
but it is untested dead logic. Either wire it up behind a flag or delete it.

**D2. Dict-consistency-by-convention, no guards [CONFIRMED]** — `config.py:69-88`, `pipeline.py:296`
`FIELD_RETRY_MAP` is derived from `AREA_TO_FIELDS` (`config.py:85-88`) with **no validation**
against `FIELD_KEYS`. A typo in `AREA_TO_FIELDS` silently (a) adds a phantom key to
`FIELD_RETRY_MAP`, and (b) makes the retry loop `for f in AREA_TO_FIELDS[area_name]` create
a spurious `result["fields"][f]` entry (`pipeline.py:296-307`) that no schema, CSV mapping,
or evaluation ever reads. `creazione` + the 5 `tooltip_*` keys are absent from every area
and therefore **never retried** [CONFIRMED] (`config.py:69-82` vs `fields.py:12-53`) — a
silent coverage hole with no diagnostic.

**D3. Schema built at import time from a runtime list** — `schemas.py:46-49`
`FieldsModel = create_model("FieldsModel", **{k: (Optional[FieldResult], None) for k in FIELD_KEYS})`.
If any future `FIELD_KEYS` entry collided with a Pydantic-reserved name
(`model_config`, `schema`, `copy`, …) the import would fail globally. No guard; convention
only.

**D4. Duplicated screen-id / content-prep logic** — `pipeline.py:182-187` vs `193-200`
`extract_from_screen` inlines open→normalize→screen_id, while `_prepare_content_image`
(`pipeline.py:193-200`) does the same plus the crop and is **never called** — orphaned
helper drifting from the live path.

**D5. `get_screenshot_paths` has no live caller [CONFIRMED]** — `config.py:99-109`, `evaluation.py:19-21`
Only reached via the backward-compat alias `infer_screenshots_from_gt`
(`evaluation.py:19-21`), which itself is exported but unused by the CLI (the CLI scans
`INPUT_DIR` directly, `cli.py:322-327`). `import re` inside the function body
(`config.py:100`) is a further smell.

**D6. Stale docstrings referencing removed front-ends** — `cli.py:296`
`run_extraction_batch` docstring says "Shared by CLI (main) and Streamlit (app.py)". There
is no `app.py`/Streamlit consumer; the real second consumer is the Tkinter `gui_app.py`.
`streamlit` also lingers in `requirements.txt` (per CLAUDE.md) as an orphan.

**D7. `_prepare_content_image`, `extract_anchors`, `extract_from_screen` module wrappers** — `pipeline.py:347-365`
Backward-compat module-level wrappers instantiate a throwaway `ExtractionPipeline` per call
(`pipeline.py:353,364`). Fine for compat, but they recreate models implicitly if ever fed
raw models and are an easy footgun for callers expecting model reuse.

**D8. Hardcoded retry confidence threshold** — `pipeline.py:255`
The `< 0.60` retry gate is a literal, while the (dead) anchor gate is env-driven
(`ANCHOR_CONF_MIN`). Inconsistent configurability; the one threshold that actually fires is
the one you cannot tune.

---

## Failure Mode Analysis

| Condition | What happens | Where | Severity |
|---|---|---|---|
| `MAX_CALLS_PER_SCREEN` set to `1` or `2` | `ThreadPoolExecutor(max_workers=0)` → `ValueError` on every non-trivial screen; batch yields zero results (parallel) or aborts (serial). Contradicts docs that claim retries are cleanly disabled. | `pipeline.py:262,284` | **Critical** |
| Ground-truth CSV missing | `FileNotFoundError` raised up-front (CLI only). | `cli.py:315-316` | Expected/handled |
| Ground-truth CSV is `;`-separated (Italian Excel default) or non-UTF-8 | `pd.read_csv` uses default `,` sep and utf-8; a `;` file parses as one column → `_find_column` raises `ValueError: Cannot find screen column`; a cp1252 file can raise `UnicodeDecodeError` or mangle accents. No `sep`/`encoding` args. | `evaluation.py:35`, `_find_column:26-31` | High |
| Provider auth error (bad key) | Not a `ValueError` → retried 3× with backoff before raising; slow-fail. | `vlm_client.py:254-258` | Medium |
| Provider rate limit under batch load | Nested pools fan out to ~12–36 concurrent calls; 429s retried per call, but no global throttle → cascading slowdowns/failures. | `cli.py:233`, `gui_app.py:244`, `pipeline.py:284` | High |
| Malformed / truncated LLM JSON (Gemini free-form) | `_extract_json_str` or `model_validate_json` raises `ValueError` → **not** retried → hard screen failure. | `vlm_client.py:91-98,252-253` | Medium |
| OpenAI structured-output parse error / refusal | `result["parsing_error"]` set → `ValueError` → not retried → screen fails. | `vlm_client.py:199-203` | Medium |
| Model name absent from `PRICING_PER_1M` | Cost silently reported as `$0.00`; no warning. | `vlm_client.py:24-26` | Medium (financial) |
| Provider omits `usage_metadata` | Tokens and cost read `0`; `_meta_agg` under-reports. | `vlm_client.py:102-104,209-211` | Medium |
| VLM returns `confidence` = `NaN`/`>1`/`<0` | No validation; `NaN` makes retry gate and `pick_best` comparisons all-`False`, silently corrupting winner selection and retry triggering. | `schemas.py:11`, `pipeline.py:255`, `normalization.py:94-96` | Medium |
| Oversized image via `extract_from_image` | No downscale; full-res crop sent → provider image-size limit or token blow-up. | `pipeline.py:104-107` | Medium |
| Empty-valued `soggetti` row present | Flatten overwrites good main/retry `ndg_i/denominazione_i/ruolo_i` with `None`; `_field_sources` left stale. | `pipeline.py:159-166` | Medium (data loss) |
| All three retry areas weak, default cap | HEADER (identity fields) dropped by alphabetical truncation; never retried. | `pipeline.py:263` | Medium (accuracy) |
| Low-confidence anchor | Gate is dead code; bad anchor propagates into main-pass hint and final result. | `pipeline.py:86-102` | High (accuracy) |
| Untrusted value with leading `=`/`+`/`-`/`@` | Written verbatim to CSV/XLSX; executes as formula in Excel. | `evaluation.py:172-177,234-239` | High (security) |
| Retry worker raises non-transient error | Swallowed to a stdout `Warning`; main-pass values kept, no structured signal. | `pipeline.py:287-292` | Low/Medium |
| `STOP_ON_ANCHOR_UNCERTAIN=1`, both anchors null | Early return with a **different dict shape** (no `canonical_fields`, empty `fields`); downstream consumers survive only because they use `.get(... ) or []` (`evaluation.py:187`, `edge-agent/ui/data_table_tab.py:164`). | `pipeline.py:112-124` | Low |

---

### Summary of documented-quirk verification

| CLAUDE.md quirk | Verdict | Note |
|---|---|---|
| Anchor gate ineffective | **REFINED** | Dead by two independent bugs (copy + `safe_set_field` guard), not one. |
| `creazione` + 5 `tooltip_*` never retried | **CONFIRMED** | Absent from all `AREA_TO_FIELDS`; no diagnostic. |
| Soggetti flatten overwrites without `_field_sources` | **REFINED** | Also destroys values a retry just recovered (`None` overwrite). |
| `_deduplicate_same_page_outputs` call commented out | **CONFIRMED** | Orphans ~115 lines incl. 4 helper fns. |
| Unknown model → `$0.00` | **CONFIRMED** | Plus missing `usage_metadata` zeroes tokens too. |
| No guards for `AREA_TO_FIELDS`/`FIELD_RETRY_MAP` vs `FIELD_KEYS` | **CONFIRMED** | Typos create phantom keys silently. |
| `MAX_CALLS_PER_SCREEN=2` "disables retries" (`docs/10-configuration-guide.md:180`) | **REFUTED** | Actually crashes with `max_workers=0`. |

**Top 3 to fix first:** A1 (config crash + wrong docs), S1 (CSV/formula injection at the
export sink so all consumers inherit the fix), A2 (resurrect the anchor gate — currently
zero accuracy protection despite the env var). A3 (alphabetical retry starvation) and A4
(flatten data loss) are the highest-value accuracy bugs.
