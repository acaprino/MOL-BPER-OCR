# Architecture Review — `extraction/` package

> Saved by team lead from the architecture-reviewer's report (subagent could not write files directly).

- **Dimension**: architecture (coupling, abstractions, failure flows, pattern consistency, quality scoring)
- **Scope**: 15 files, ~2,442 lines at HEAD (see `.team-review/00-scope.md`); external consumers read for coupling context only (`main.py`, `gui_app.py`, `edge-agent/local_extraction_client.py`)
- **Method**: defect-taxonomy frameworks (review-frameworks.md, logic-types.md, memory-resources.md), failure-flow methodology, interconnect-map anchor verification. Every map claim cited below was re-verified in source; two greps confirmed the single-factory constraint and env-read discipline.
- **Date**: 2026-07-21

---

## Findings

### CRITICAL

**ARCH-01 — Retry stage crashes on documented config values (`ThreadPoolExecutor(max_workers=0)`)**
`extraction/pipeline.py:259-263, 284` — `allowed_retries = max(0, MAX_CALLS_PER_SCREEN - 2)`; with `MAX_CALLS_PER_SCREEN` set to `1` or `2` (permitted by `extraction/config.py:54`), `areas_to_retry` is almost always non-empty (any nullish or `< 0.60`-confidence field adds an area, `pipeline.py:255`), so the early return at `pipeline.py:259` is not reached, the slice at `:263` is empty, and `ThreadPoolExecutor(max_workers=0)` raises `ValueError` at `:284`. Verified independently: the guard order is `if not areas_to_retry: return` **before** the truncation, so an empty *list* with a non-empty *set* falls through.
Failure flow: the exception propagates out of `extract_from_image` into `BatchRunner`; in the CLI's parallel no-callback path it is printed per screen (`cli.py:246-251`) and the run "completes" with zero outputs — `eval_outputs` then prints `0/0 = 0.00%` (`evaluation.py:106-110`), so a config tweak intended to save cost silently produces an empty, plausible-looking report. `docs/10-configuration-guide.md:180` claims 2 "disables retries" — refuted by code.
Fix: return when `areas_to_retry_list` is empty (`if not areas_to_retry_list: return` after `:263`), and fix the doc.
Map anchors: `## Invariants` I3 (verified, violated); shared with logic-integrity — reported here because it is a failure-flow defect in the orchestration layer.
Confidence: 95

### HIGH

**ARCH-02 — Nested thread-pool fan-out with no global ceiling; thread-safety is comment-only; no explicit call timeouts**
Outer batch pool: `extraction/cli.py:229-234` (`max_workers` = `PARALLEL_WORKERS` default 4; the Tkinter GUI passes `min(len(paths), 12)`, `gui_app.py:244`). Each worker runs `extract_from_screen` → `_retry_areas`, which opens an inner pool sized to the retry list (`pipeline.py:284`, ≤2 with the default budget, 3 if `MAX_CALLS_PER_SCREEN >= 5`). Worst case from the GUI: 24 concurrent VLM calls with defaults (36 with a raised budget), each of which may issue up to 3 HTTP attempts with sleeps up to ~8s (`vlm_client.py:241, 256-257`). No global semaphore, no bulkhead, no explicit request timeout configured on the ChatModels (`llm_factory.py:54, 75` — SDK defaults only). The shared-ChatModel thread-safety assumption is asserted in docstrings only (`cli.py:161, 181`, `pipeline.py:50`, `llm_factory.py:26`) with no runtime guard.
Consequence: under provider rate limiting the pools fill with sleeping retry threads (taxonomy 13.3 thread-pool exhaustion / missing bulkhead), and the retry-with-backoff design *amplifies* load exactly when the provider is throttling.
Fix direction: module-level `BoundedSemaphore` around `call_vlm` (single choke point already exists), or cap outer × inner from one config value; set explicit timeouts in `create_chat_model`.
Map anchors: `## Reviewer Hints` architecture bullet 1 (verified); `## Assumptions` unverified — "No global concurrency ceiling", "ChatModel thread-safety documented but not enforced".
Confidence: 90

**ARCH-03 — Untyped tri-shape result contract at the highest-traffic boundary; the error shape is minted by a consumer, not the engine**
The pipeline's return value is a string-keyed dict with three shape variants: normal (`pipeline.py:104-180`), early-exit (`pipeline.py:112-124` — no `canonical_fields`, no top-level `_meta`, no `attempt`), and error — fabricated *outside the package* by `edge-agent/local_extraction_client.py:89-94` (no `_meta_agg`, no table keys). No Pydantic model or TypedDict describes any of them, even though the package uses Pydantic everywhere else (`schemas.py`). Every consumer independently re-derives defensive access: `evaluation.py:92, 138-139, 186, 202, 250-253`, `gui_app.py:309-333`, `local_extraction_client.py:121, 135-139`. The engine reads its own `out["_meta"]` unguarded (`pipeline.py:101, 140, 294`), so the per-call `_meta` key is load-bearing yet also untyped.
Architectural problem: the contract is defined by the union of one producer and three consumers; the package does not own its error envelope, so any new consumer (or key) must rediscover all three shapes from call sites. One `.get`-less access on the early-exit or error shape is a latent crash (e.g. `out["_meta_agg"]` on an edge-agent error result).
Fix direction: a `TypedDict`/dataclass for the result (shape already documented in `.deep-dive/02-interfaces.md`), and move the error envelope into the pipeline (an `extract_safe` wrapper or `make_error_result()` factory) so the edge-agent stops inventing shape #3.
Map anchors: `## Contracts` → Structural (verified, all three shapes); `## Integration Hot-Spots` 1; `## Reviewer Hints` architecture bullet 3.
Confidence: 90

**ARCH-04 — Shared-runner model fallback ignores the provider override: GUI provider switching crashes at batch start**
`BatchRunner.__init__` falls back per-model to env config: `self._anchor_model_name = model_anchor or LLM_MODEL_ANCHOR` (`cli.py:177`), where `LLM_MODEL_ANCHOR` defaults to `LLM_MODEL` = `"gpt-4o"` (`config.py:18-19`). The Tkinter GUI passes `provider_name` and `model_main` but **never** `model_anchor` (`gui_app.py:238-247`). Result, verified against `llm_factory.py:49-53, 59-63`:
- Default env (no `LLM_MODEL` exported), user picks **gemini** + any Gemini model in the GUI → anchor model is `create_chat_model("gemini", model="gpt-4o")` → `ValueError: Model 'gpt-4o' looks like an OpenAI model but provider is 'gemini'` in `BatchRunner.__init__` → GUI shows a generic "ERRORE GENERALE" (`gui_app.py:281-283`).
- Converse env (`LLM_MODEL=gemini-1.5-flash` per the CLAUDE.md Gemini setup), user picks **openai** in the GUI → same crash from the other guard (`llm_factory.py:49-53`).
So cross-provider selection — the GUI's headline feature ("Multi-LLM Support", `gui_app.py:20`) — is broken in both directions unless the user also exports a matching `LLM_MODEL_ANCHOR`. Even same-provider, the anchor silently uses the env-default model rather than the one the user picked (picking `gpt-4o-mini` still runs anchors on `gpt-4o` — cost surprise).
Fix: default the anchor to the *effective main* model (`model_anchor or model_main or LLM_MODEL_ANCHOR`), or have the GUI pass `model_anchor=self.model_choice.get()`.
Map anchors: `## Integration Hot-Spots` 2 and 10 (the map notes the override parameters but not this interaction); interface-contract gap in the shared runner both front-ends depend on.
Confidence: 90

### MEDIUM

**ARCH-05 — Parallel vs serial error semantics diverge in the shared runner, and the parallel path feeds a silent-metrics chain**
Same input, different failure behavior selected only by `PARALLEL_ENABLED`/`parallel`: parallel no-callback path prints and continues (`cli.py:246-251`); serial no-callback path re-raises and aborts, discarding completed work (`cli.py:261-266`). The no-callback mode is exactly the CLI path (`main()` passes no callbacks, `cli.py:334`). Downstream, a screen that errored in parallel mode is simply absent from `outputs`, and `eval_outputs` silently skips missing predictions (`evaluation.py:79-81`) — accuracy percentages remain plausible while coverage shrinks (anti-pattern "mixed error handling"; silent-wrong-output flow). Pick one policy (collect-and-continue) for both paths and report a failure count in the batch summary.
Map anchors: `## Reviewer Hints` architecture bullet 2 (verified); interacts with logic-integrity's "silent denominator drift".
Confidence: 95

**ARCH-06 — Eager monolithic facade forces the full dependency graph (and all import-time side effects) on every consumer**
`extraction/__init__.py:47-126` imports every module — including `cli.py`, which pulls `evaluation.py` and therefore **pandas** — at package-import time. Python imports the package `__init__` before any submodule, so even the edge-agent's targeted imports (`from extraction.llm_factory import create_chat_model`, `local_extraction_client.py:27-29`) execute the whole chain. Consequences: (a) the live-capture agent cannot start if pandas (used only for CSV evaluation it never runs) is broken or missing; (b) any import-time failure anywhere — including a future `FIELD_KEYS` entry colliding with a Pydantic-reserved name in the dynamically built `FieldsModel` (`schemas.py:46-49`) — takes down all three front-ends at once; (c) import cost paid by everyone. The layered DAG underneath is clean (verified: no cycles), so the coupling is introduced purely by the facade.
Fix direction: lazy facade (PEP 562 module `__getattr__`) or at minimum stop importing `cli`/`evaluation` eagerly and let `main.py` import them directly.
Map anchors: `## Reviewer Hints` architecture bullet 7 (facade discipline — extended: the sync requirement is real, but the eager-import coupling is the larger cost); `## Contracts` implicit "Facade sync".
Confidence: 90

**ARCH-07 — Import-time env configuration; `from`-import snapshots make constants untunable and untestable after import**
All env reads happen at module import (`config.py:8-56`; grep-verified no `os.getenv` elsewhere in the package except `llm_factory.py`, see ARCH-14). Consumers bind constants by value at their own import (`pipeline.py:11-19`, `cli.py:9-21`), so patching `extraction.config.MAX_CALLS_PER_SCREEN` at runtime (tests, notebooks, GUI) has no effect on the pipeline's already-bound copy. Combined with ARCH-06, `.env` must be populated before the *first* `import extraction` anywhere in the process; `gui_app.py:1-14` never calls `load_dotenv` (documented, still a per-entry-point trap — three loaders and one non-loader). Derived values freeze too (`GROUND_TRUTH_CSV`, `DEBUG_CROP_DIR`, `FIELD_RETRY_MAP`, `config.py:9, 85-88, 94`).
Fix direction: a `get_config()` accessor or dataclass read once but passed explicitly to `ExtractionPipeline`/`BatchRunner` (both already take constructor args — the pattern is half-adopted).
Map anchors: `## Reviewer Hints` architecture bullet 4; `## Contracts` implicit "Import-order contract"; `## Invariants` I10 (all verified).
Confidence: 95

**ARCH-08 — Provider dispatch re-derived downstream from model-name substrings (leaky, stringly-typed abstraction)**
`create_chat_model` is the sanctioned provider decision point, yet `vlm_client.py:134` re-infers the provider with `"gemini" in model.lower()` and picks schema mode via a `"gemini-1.5"` substring (`vlm_client.py:18, 138`) — two additional, name-string-based sources of truth for the same fact. The `BaseChatModel` abstraction leaks: correctness of the call path depends on the *name label* passed alongside the instance (`pipeline.py:63-64`), and a mismatched pair silently misroutes (wrong message format/JSON mode) and misprices (`estimate_cost_usd` keyed on the same string, `vlm_client.py:23`). A future OpenAI-compatible proxy named `my-gemini-gw` would take the Gemini branch.
Fix direction: have the factory return provider identity with the model (small wrapper/dataclass `{model, provider, name}`), or dispatch on `isinstance(chat_model, ChatGoogleGenerativeAI)` at the seam.
Map anchors: `## Contracts` implicit "Gemini routing by model-name substring" and "Model-name/model-instance pairing" (both verified).
Confidence: 90

**ARCH-09 — `safe_set_field`'s overloaded `None` sentinel makes intentional nulling impossible; asymmetric copy/mutate helper contract**
`normalization.py:71-85`: `value=None` means both "no update" and "set null" — the guard `if value is not None or f.get("value") is None` (`:78`) makes clearing a non-null value unexpressible. Meanwhile `safe_field` (`:60-69`) returns a fresh copy, so read-then-write code that mutates the returned dict silently writes nothing back. These two ambiguities *jointly* produced the dead anchor gate (`pipeline.py:87-102`: gate mutates the original via `safe_set_field` — which refuses the null — then returns the pre-gate copies). This is an API-design defect, not just a call-site bug: the same helper pair is used in `_coherence_check` (`pipeline.py:311-328`), which works only because it never needs to null anything.
Fix direction: an explicit `UNSET` sentinel (or dedicated `clear_field()`), and a docstring on `safe_field` stating copy semantics.
Map anchors: `## Contracts` implicit "`safe_field` returns a fresh copy" and I5 (functional consequence belongs to logic-integrity; the abstraction defect is reported here).
Confidence: 95

**ARCH-10 — Cost-telemetry chain has three silent-zero/under-count paths, breaching architectural constraint #2**
(1) Unknown model name → `estimate_cost_usd` returns `0.0` with no warning (`vlm_client.py:23-25`), while `LLM_MODEL` is free-form (`config.py:18`) — e.g. `gpt-4o-2024-11-20` zeroes the report. (2) Missing/renamed `usage_metadata` → tokens default to 0 in all three call paths (`vlm_client.py:102-104, 162-164, 209-211`). (3) Failed area retries append nothing to `attempts_meta` (`pipeline.py:287-292`), and each logical call may be up to 3 HTTP attempts (`vlm_client.py:241`), so `_meta_agg.calls` under-counts real API usage in both directions of the ledger (`pipeline.py:330-340`). CLAUDE.md documents (1); (2) and (3) extend it. A one-line warning on pricing miss and a `failed_calls` counter in `_meta_agg` would close most of the gap.
Map anchors: `## Integration Hot-Spots` 8; `## Invariants` I2 caveat and I7 (all verified).
Confidence: 90

**ARCH-11 — `_meta` finalization triplicated across the three VLM paths**
The usage-extraction + `_meta` dict + `screen_id`/`attempt` stamping block is duplicated near-verbatim three times: `vlm_client.py:100-119` (Gemini free-form), `:160-179` (Gemini schema-mode), `:205-226` (OpenAI). A `_meta`-shape change must touch three sites plus the aggregator key list (`pipeline.py:335-339`) plus consumers (`evaluation.py:250-253`) — the exact single-source-of-truth failure the module otherwise centralizes well. Extract one `_finalize(parsed, raw_msg, t0, model, screen_id, attempt)` helper.
Map anchors: `## Contracts` "Per-call `_meta`" (verified — the three sites are currently in sync).
Confidence: 95

**ARCH-12 — Raw entry point has no input-size enforcement; the seam's contract lives in a consumer comment**
`extract_from_image` (`pipeline.py:104`) deliberately skips `normalize_image` for the edge-agent (CLAUDE.md constraint 12), but nothing in `extraction/` asserts or clamps incoming dimensions — the pre-normalization contract exists only as a comment in the consumer (`local_extraction_client.py:84-86`). A mis-wired caller sends full-resolution 4K crops → provider image limits / token blow-up, and lossless PNG encoding (`imaging.py:31-34`) amplifies it. A cheap width/height clamp at the seam would make the dual-entry design safe without re-processing.
Map anchors: `## Reviewer Hints` architecture bullet 5; `## Contracts` implicit "Entry-point selection" (verified).
Confidence: 85

**ARCH-13 — Result-presentation branching (`canonical_fields` else `fields` fallback) duplicated across consumers; third CSV export re-implemented**
The "prefer `canonical_fields`, fall back to iterating `FIELD_KEYS` over raw `fields`" logic is implemented independently in `evaluation.export_to_csv` (`evaluation.py:186-217`) and `gui_app.display_results` (`gui_app.py:333-368`); the edge-agent additionally hand-rolls a third CSV writer with a different scheme (union-of-keys columns, `local_extraction_client.py:112-143`) that will not inherit fixes to the package writers (relevant to the CSV-injection fix security will demand — three sinks, not one). This duplication is a direct consequence of ARCH-03. A single `iter_field_entries(result)` helper in the package would collapse the branching.
Map anchors: `## Integration Hot-Spots` 7; `## Change Impact Radius` CSV-writers row (verified).
Confidence: 85

### LOW

**ARCH-14 — `LLM_THINKING_LEVEL` read twice with different lifetimes** — `config.py:20` defines and exports it (read at import); `llm_factory.py:72` re-reads `os.getenv("LLM_THINKING_LEVEL")` at call time instead of importing the constant — two values that can diverge mid-process. Grep-verified these are the only env reads outside `config.py` besides the API-key lookups. Confidence: 95

**ARCH-15 — Name shadowing between module-level wrappers and methods; throwaway pipelines** — `extract_from_screen` exists as a 1-arg method (`pipeline.py:182`) and a 5-arg module function (`pipeline.py:357-365`) under the same name; the facade exports the module one (`__init__.py:38, 112`). The wrappers build a throwaway `ExtractionPipeline` per call, contradicting the class docstring's "create once and reuse" (`pipeline.py:50-51`). Confidence: 90

**ARCH-16 — Facade export asymmetry and stale references** — `Soggetto` exported but `Fido`/`Garanzia`/`AnchorFields`/`FieldsModel` not (`__init__.py:27` vs `schemas.py:22-49`). Facade docstring cites `app.py` (`__init__.py:3`); `run_extraction_batch` docstring cites "Streamlit (app.py)" (`cli.py:296`); the real second consumer is Tkinter `gui_app.py`. Confidence: 95

**ARCH-17 — `screen_id` derivation duplicated across layers (join-key coupling)** — basename-sans-extension implemented in `cli.py:225`, again at `cli.py:237, 254`, and in `pipeline.py:186`. It is the ground-truth join key (`evaluation.py:79-81` silently skips non-matches), so divergence between copies silently zeroes the evaluation. One `screen_id_from_path()` helper would pin it. Map anchor: `## Contracts` implicit "screen_id ↔ ground truth join key" (verified). Confidence: 90

**ARCH-18 — Hardcoded live threshold vs env-driven dead threshold** — the retry gate that actually fires is a literal `0.60` (`pipeline.py:255`); the anchor gate that is dead code is env-tunable (`ANCHOR_CONF_MIN`, `config.py:56`). The one knob operators can turn does nothing (logic-integrity I5); the one that matters is unreachable from config. Confidence: 95

---

## Failure Flow Summary (architecture-relevant)

| Kill/failure point | Behavior | Assessment |
|---|---|---|
| Worker exception, parallel CLI | print-and-continue → screen absent → eval silently skips → plausible metrics on shrunken denominator (`cli.py:246-251`, `evaluation.py:79-81`) | Silent partial output (ARCH-05) |
| Worker exception, serial CLI | batch aborts, completed screens' work discarded (`main()` writes outputs only after `run()` returns, `cli.py:334-340`) | Wasted work; divergent policy (ARCH-05) |
| `MAX_CALLS_PER_SCREEN <= 2` | every non-trivial screen crashes; batch yields zero results | CRITICAL (ARCH-01) |
| Provider rate-limit under GUI load | up to 24 concurrent calls each retrying 3× with sleeps; pools saturate with sleeping threads | HIGH (ARCH-02) |
| Retry-area worker failure | stdout warning only; no meta record; cost ledger under-counts | MEDIUM (ARCH-10) |
| Edge-agent extraction failure | consumer-minted error dict, shape #3; package unaware of its own error envelope | HIGH (ARCH-03) |
| Batch process killed mid-run | no partial persistence (outputs in memory until end); rerun redoes all screens; no resume/cache layer | Acceptable for a 9-screen POC; flagged for scale |

## Pattern Consistency

Strong baseline, verified: consistent full type annotations, `UPPER_SNAKE_CASE` constants / `_private` helpers, section markers, Italian-prompt/English-identifier policy, single LLM factory (grep-confirmed: `ChatOpenAI`/`ChatGoogleGenerativeAI` appear only in `llm_factory.py`; `create_chat_model` has exactly the two sanctioned call sites — `cli.py:182-191`, `local_extraction_client.py:47-48`), clean acyclic layering (leaves → primitives → engines → orchestration → facade). Deviations: `_meta` triplication (ARCH-11), dual env read (ARCH-14), presentation-logic duplication (ARCH-13), export asymmetry (ARCH-16), hardcoded-vs-env threshold inversion (ARCH-18).

## Positive Observations

- `extract_from_image` is a readable, well-sequenced 8-step orchestration; ordering constraints at least documented even where unenforced.
- `run_extraction_batch`/`BatchRunner` genuinely is shared by both front-ends — no duplicated threading logic found (constraint 8 holds).
- `call_vlm_with_retry`'s ValueError-vs-transient split is a real design decision at the right seam (its coarseness is logic-integrity's finding).
- Provider/model family mismatch is validated at construction (`llm_factory.py:49-53, 59-63`) — which is exactly why ARCH-04 fails fast instead of mid-batch.

## Code Quality Score

Per review-frameworks scoring (start 10, CRITICAL −2, HIGH −1, MEDIUM −0.5, LOW noted), per category over this dimension's findings:

| Category | Score | Deductions applied |
|---|---|---|
| Reliability / failure flows | 5.0/10 | ARCH-01 (−2), ARCH-02 (−1), ARCH-04 (−1), ARCH-05 (−0.5), ARCH-10 (−0.5) |
| Architecture / coupling & abstractions | 6.5/10 | ARCH-03 (−1), ARCH-06 (−0.5), ARCH-07 (−0.5), ARCH-08 (−0.5), ARCH-09 (−0.5), ARCH-12 (−0.5) |
| Pattern consistency | 8.0/10 | ARCH-11 (−0.5), ARCH-13 (−0.5), ARCH-14/16/18 (−1 aggregate, LOWs partially noted-only) |
| Maintainability | 6.5/10 | untyped core contract (ARCH-03 spillover), import-time config (ARCH-07), duplication (ARCH-11/13), name shadowing (ARCH-15) |

**Overall: 6.0/10.** Justification (required below 7): one verified config-triggered crash on a documented setting (ARCH-01), a broken headline GUI flow at the shared-runner interface (ARCH-04), unbounded nested concurrency against a rate-limited external dependency (ARCH-02), and an untyped three-shape contract at the system's highest-traffic boundary partly defined outside the package (ARCH-03). The underlying structure (layering, single factory, shared runner, naming discipline) is solid for a POC and lifts the score; deductions concentrate in failure paths and contracts, not the decomposition itself.

## Cross-Reviewer Notes

- **logic-integrity**: ARCH-01 is your I3 — independently re-verified, including the guard-order detail (`pipeline.py:259` fires only when the *set* is empty). ARCH-09 is the API-design root of your I5 (dead anchor gate); the accuracy impact (low-confidence anchors feeding the main-pass hint, `pipeline.py:205-208`) is yours. Also confirmed while reading: `_merge_tables` third branch unreachable (`pipeline.py:240-241` — `old==0 ∧ new>0` implies `new>old`, matched at `:236`), and the soggetti flatten (`pipeline.py:159-166`) runs after the retry merge with no null check and no `_field_sources` update — it can overwrite a BODY-retry-recovered `ndg_1` with `None`.
- **security**: the CSV-injection fix should land at the package sinks (`evaluation.py:172-177, 234-239`) **and** the edge-agent's independent writer (`local_extraction_client.py:131-143`) — per ARCH-13 there are three sinks, not one. GUI also writes results JSON/CSV to cwd (`gui_app.py:250-256`) in addition to the `INPUT_DIR` writes.
- **hygiene**: confirmed unused imports in `cli.py:25-27` (`eval_outputs`, `build_debug_report`, `print_cost_summary` — `main()` uses the `Evaluator` methods); `_prepare_content_image` orphan (`pipeline.py:193-200`); `get_screenshot_paths` no live caller + function-body `import re` (`config.py:99-100`); `FIELD_RETRY_MAP` built and exported but never consumed (`config.py:85-88` — pipeline iterates `AREA_TO_FIELDS` directly); dead ~115-line dedup cluster behind the commented call (`cli.py:36-152, 268-273`); stale `app.py`/Streamlit references (`__init__.py:3`, `cli.py:296`).
- **UI/concurrency (route to whoever owns it, else lead)**: `gui_app.py` calls Tkinter widget methods from a worker thread — `self.log` → `log_area.insert` from batch callbacks and `messagebox.showinfo/showerror` all run on the `threading.Thread` started at `gui_app.py:225`; only `display_results` is marshalled via `self.after` (`gui_app.py:278`). Tkinter is not thread-safe; outside `extraction/` scope but sits on the shared-runner callback contract (`cli.py:162-163`).
