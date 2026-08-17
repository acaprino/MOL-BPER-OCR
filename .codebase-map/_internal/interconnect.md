# Interconnect Map

> Produced by `semantic-interconnect-mapper` on 2026-07-21. Session: `.codebase-map/`. Context source: `.codebase-map/_internal/context-brief.md` (codebase-explorer).

## Target scope

- Files analyzed: 32 project Python files (15 in `extraction/`, 15 in `edge-agent/`, plus `main.py`, `gui_app.py`), 3 config/data surfaces (`edge-agent/config.ini`, `.env.example`, `edge-agent/assets/templates/bper/prompts.json`).
- Top-level entry points:
  - CLI batch: `main.py:23` → `extraction.cli.main()` (`extraction/cli.py:314`)
  - Edge-agent GUI: `main.py:15-20` (`--gui`) and `edge-agent/edge_agent.py:24` (`main()`)
  - Tkinter GUI: `gui_app.py:401-403` (`App().mainloop()`)
- Deep-dive mode: n/a (context-brief source, `/map-codebase` invocation).

## Call Graph (expanded, 2-3 hops)

### `extraction/` package — public surface (`extraction/__init__.py:11-45` defines `__all__`)

| Exported symbol | Declared at | External callers | External callees |
|-----------------|-------------|------------------|------------------|
| `ExtractionPipeline` | `extraction/pipeline.py:47` | `extraction/cli.py:192` (BatchRunner), `edge-agent/local_extraction_client.py:49` | `call_vlm_with_retry` → LangChain ChatModel `.invoke()` (OpenAI/Gemini HTTPS) |
| `ExtractionPipeline.extract_from_screen()` | `extraction/pipeline.py:182` | `extraction/cli.py:227,257` | `PIL.Image.open` (FS read), `normalize_image` (`extraction/imaging.py:12`), `extract_from_image` |
| `ExtractionPipeline.extract_from_image()` | `extraction/pipeline.py:104` | `edge-agent/local_extraction_client.py:86` | `crop_relative`, `call_vlm_with_retry` (`extraction/pipeline.py:76,130,274`), `build_canonical_field_entries` (`extraction/pipeline.py:168`), nested `ThreadPoolExecutor` (`extraction/pipeline.py:284`) |
| `BatchRunner` / `run_extraction_batch` | `extraction/cli.py:158` / `extraction/cli.py:282` | `gui_app.py:238` (`run_extraction_batch`), `extraction/cli.py:333` (`main()`) | `create_chat_model` (`extraction/cli.py:182-191`), `ThreadPoolExecutor` (`extraction/cli.py:233`) |
| `main` (CLI) | `extraction/cli.py:314` | `main.py:23` | `load_ground_truth`, `Evaluator`, FS writes (`extraction/cli.py:337-346`) |
| `create_chat_model` | `extraction/llm_factory.py:16` | `extraction/cli.py:182,187`, `edge-agent/local_extraction_client.py:47-48` | `langchain_openai.ChatOpenAI` (`extraction/llm_factory.py:54`), `langchain_google_genai.ChatGoogleGenerativeAI` (`extraction/llm_factory.py:75`) |
| `call_vlm` / `call_vlm_with_retry` | `extraction/vlm_client.py:122` / `:229` | `extraction/pipeline.py:76,130,274` (only callers) | `chat_model.with_structured_output(...).invoke()` (`extraction/vlm_client.py:147-149,193-196`), Gemini free-form path (`extraction/vlm_client.py:76-81`) |
| `estimate_cost_usd` | `extraction/vlm_client.py:21` | internal to `vlm_client` (`:105,165,212`); re-exported `extraction/__init__.py:36` | `PRICING_PER_1M` (`extraction/config.py:36-49`) |
| `load_ground_truth` | `extraction/evaluation.py:33` | `extraction/cli.py:318`, `gui_app.py:265` | `pandas.read_csv` (FS read) |
| `eval_outputs` | `extraction/evaluation.py:74` | `gui_app.py:266`, `Evaluator.eval` (`extraction/evaluation.py:271-273`) | `dataset_mismatch_guard`, `classify_field` |
| `build_debug_report` (module fn) | `extraction/evaluation.py:125` | `gui_app.py:274`, `Evaluator.build_debug_report` (`extraction/evaluation.py:275-277`) | `pandas.DataFrame.to_csv` (FS write, `;` sep, utf-8-sig, `extraction/evaluation.py:172-177`) |
| `export_to_csv` | `extraction/evaluation.py:182` | `gui_app.py:256` (only caller) | `pandas.DataFrame.to_csv` (`extraction/evaluation.py:234-239`) |
| `print_cost_summary` | `extraction/evaluation.py:244` | `extraction/cli.py:347` (via `Evaluator`) | stdout only |
| `classify_field` | `extraction/normalization.py:113` | `extraction/evaluation.py:93,147` | `SequenceMatcher` (stdlib) |
| `dataset_mismatch_guard` | `extraction/normalization.py:174` | `extraction/evaluation.py:84,137` | none |
| `pick_best` / `merge_field_sources` | `extraction/normalization.py:87` / `:98` | `extraction/pipeline.py:301-307` (`merge_field_sources`) | none |
| `build_canonical_field_entries` | `extraction/canonical_mapping.py:20` | `extraction/pipeline.py:168` | `get_canonical_field_metadata` (`extraction/fields.py:128`), `PAGE_SHEET_ORDER` (`extraction/page_definitions.py:23`) |
| `FIELD_KEYS` | `extraction/fields.py:12-54` (45 keys) | `extraction/schemas.py:48` (FieldsModel), `extraction/pipeline.py:141`, `extraction/evaluation.py:151,203`, `gui_app.py:357` | none |
| `CSV_TO_SCHEMA` | `extraction/fields.py:56-100` | `extraction/normalization.py:152`, `extraction/evaluation.py:88` | none |
| `CANONICAL_FIELD_DEFINITIONS` | `extraction/field_definitions.py:5-186` | `edge-agent/ui/data_table_tab.py:36-39` (direct cross-package import), `extraction/field_definitions.py:249-262` resolvers | none |
| `PROVIDER_MODELS` | `extraction/config.py:22-33` | `gui_app.py:72-87,141` | none |
| `get_screenshot_paths` / `infer_screenshots_from_gt` | `extraction/config.py:99` / `extraction/evaluation.py:19` | no caller outside their alias pair (dead public surface) | none |
| `extract_anchors` / `extract_from_screen` (module wrappers) | `extraction/pipeline.py:347,357` | no external caller (backward-compat re-exports, `extraction/__init__.py:112`) | `ExtractionPipeline` |
| `normalize_image` | `extraction/imaging.py:12` | `extraction/pipeline.py:185,196` only | PIL |
| `save_debug_crop` | `extraction/imaging.py:37` | `extraction/pipeline.py:73,107,199,273` | FS write to `DEBUG_CROP_DIR` (`extraction/config.py:94`) |

### `edge-agent/` package

| Exported symbol | Declared at | External callers | External callees |
|-----------------|-------------|------------------|------------------|
| `LocalExtractionClient` | `edge-agent/local_extraction_client.py:32` | `edge-agent/ui/main_window.py:37` (constructed once, shared by 3 tabs + worker) | `create_chat_model`, `ExtractionPipeline` (`edge-agent/local_extraction_client.py:47-54`) |
| `LocalExtractionClient.start_job()` | `edge-agent/local_extraction_client.py:61` | `edge-agent/ui/capture_tab.py:179` | `uuid.uuid4()` |
| `LocalExtractionClient.ingest_frame()` | `edge-agent/local_extraction_client.py:65` | `edge-agent/workers/capture/bper_capture_worker.py:696` (duck-typed via `hasattr(api_client, "ingest_frame")`, `:693`) | `ExtractionPipeline.extract_from_image()` (`:86`), `result_ready.emit` (`:106`) |
| `LocalExtractionClient.export_csv()` | `edge-agent/local_extraction_client.py:112` | `edge-agent/ui/capture_tab.py:347`, `edge-agent/ui/extraction_results_tab.py:218` | in-memory `csv.writer` |
| `LocalExtractionClient.get_results()` / `get_all_job_ids()` | `edge-agent/local_extraction_client.py:147` / `:151` | `edge-agent/ui/extraction_results_tab.py:160,153`, `edge-agent/ui/data_table_tab.py:281,232` | none |
| `LocalExtractionClient.result_ready` (signal) | `edge-agent/local_extraction_client.py:42` | connected at `edge-agent/ui/capture_tab.py:212`, `edge-agent/ui/extraction_results_tab.py:65`, `edge-agent/ui/data_table_tab.py:98` | Qt queued delivery across threads |
| `LocalExtractionClient.requeue_job()` | `edge-agent/local_extraction_client.py:108` | no caller (compat stub) | none |
| `BPERCaptureWorker` | `edge-agent/workers/capture/bper_capture_worker.py:35` | `edge-agent/ui/capture_tab.py:227` | `mss` (`:557-574`), `imagehash.phash` (`:608`), `preprocess_for_ocr` (`:576-583`), router `.route()` (`:635`), `api_client.ingest_frame` (`:696`), `openpyxl` (`:273-291`) |
| `BPERCaptureWorker.force_capture()` | `edge-agent/workers/capture/bper_capture_worker.py:726` | `edge-agent/ui/capture_tab.py:404` (direct call from UI thread) | `_capture_screenshot`, `_upload_page` |
| `BaseCaptureWorker` (`tick`/`error`/`llm_debug` signals) | `edge-agent/workers/capture/base_capture_worker.py:9,17-20` | subclassed at `bper_capture_worker.py:35`, `default_capture_worker.py:16`; signals connected `edge-agent/ui/capture_tab.py:259-267` | QThread run loop (`base_capture_worker.py:39-61`) |
| `DefaultCaptureWorker` | `edge-agent/workers/capture/default_capture_worker.py:16` | `edge-agent/ui/capture_tab.py:249` ("Generico" mode) | `requests.post` to `{api_base}/jobs/{job_id}/frames` (`:62-66`), `pyscreenshot` (`:82-84`) |
| `LLMPageRouter` / `MLPageRouter` / `PageRouter` | `edge-agent/llm_router.py:61,42,37` | `bper_capture_worker.py:123-130,148-155,190` | OpenAI SDK `chat.completions.create` (`llm_router.py:200-209`), `BPERPagePrototypeClassifier` (`llm_router.py:47-54`) |
| `LLMPageRouter.set_expected_page()` / `get_page_hints()` | `edge-agent/llm_router.py:130` / `:134` | no caller (dead surface) | none |
| `BPERPagePrototypeClassifier.classify()` | `edge-agent/page_classifier.py:496` | `llm_router.py:57`, `bper_capture_worker.py:665,672` | torch/DINOv2 (degrades to `(None, 0.0)` if torch missing, `page_classifier.py:9-19`) |
| `AgentConfig` | `edge-agent/config.py:8` | `edge-agent/edge_agent.py:48`, `ui/main_window.py:32`, all workers via `self.config` | `configparser.read` of `config.ini` (`edge-agent/config.py:134`) |
| `AgentConfig.update_from_ui()` | `edge-agent/config.py:273` | `edge-agent/ui/capture_tab.py:217` | none |
| `AgentConfig.save()` | `edge-agent/config.py:289` | no caller (writes `[llm] api_key` back to disk if ever invoked, `edge-agent/config.py:326-332`) | FS write |
| `MainWindow` | `edge-agent/ui/main_window.py:17` | `edge-agent/edge_agent.py:52` | constructs `LocalExtractionClient` (`:37`) → LLM factory → fails fast without API key |
| `preprocess_for_ocr` / `to_png8` / `to_webp_lossless` | `edge-agent/image_ops.py:21,58,67` | `bper_capture_worker.py:576`; `to_png8`/`to_webp_lossless` imported (`bper_capture_worker.py:24`, `edge_agent.py:16`) but never called (dead surface) | PIL |

### Cross-package sys.path bridges

- `edge-agent/local_extraction_client.py:17-19` inserts project root into `sys.path` to import `extraction`.
- `edge-agent/ui/data_table_tab.py:31-33` inserts project root to import `extraction.field_definitions` directly.
- `main.py:16-19` inserts `edge-agent/` into `sys.path` for `--gui`.

## Contracts

### Formal

- `FieldResult` = `{value: Optional[str], confidence: float, evidence_text: Optional[str], section: Optional[str]}` — `extraction/schemas.py:9-13`. The atom of every extracted field.
- `FieldsModel` is generated dynamically with exactly one `Optional[FieldResult]` per key in `FIELD_KEYS` — `extraction/schemas.py:46-49`. Schema/field-list sync is by construction.
- `ExtractionResponse` = `{fields: FieldsModel, soggetti: List[Soggetto], fidi: List[Fido], garanzie: List[Garanzia]}` — `extraction/schemas.py:54-58`; `AnchorResponse` = `{fields: {ndg, denominazione}}` — `extraction/schemas.py:60-65`. Passed to LangChain `.with_structured_output()` at `extraction/vlm_client.py:147,193` and Pydantic-validated manually on the Gemini free-form path at `extraction/vlm_client.py:93`.
- `RouterResult` dataclass = `{page_type: Optional[str], confidence: float, fields: dict, reason, expected}` — `edge-agent/llm_router.py:27-34`; every `PageRouter.route()` must return it (`edge-agent/llm_router.py:37-39`).
- Qt signal signatures: `result_ready(str, dict)` — `edge-agent/local_extraction_client.py:42`; `tick(str)`, `error(Exception)`, `llm_debug(str: JSON)` — `edge-agent/workers/capture/base_capture_worker.py:17-20`.
- `create_chat_model(provider_name, *, model, api_key=None) -> BaseChatModel` raises `ValueError` for: missing key (`extraction/llm_factory.py:41-44`), provider/model mismatch (`:49-53`, `:59-63`), unknown provider (`:77`).
- GT CSV loader raises `ValueError` when no candidate column matches (`extraction/evaluation.py:26-31`); accepted column aliases at `extraction/evaluation.py:38-52`.

### Structural

- **Per-screen result dict** (built in `extraction/pipeline.py:104-180`): keys `screen_id`, `fields` (schema_key → FieldResult-shaped dict), `soggetti`/`fidi`/`garanzie` (lists), `canonical_fields` (sorted entries), `_attempts` (list of `_meta`), `_meta_agg`, `_field_sources`, `_status` ∈ {`"OK"`, `"ANCHOR_UNCERTAIN"`} (`extraction/pipeline.py:175-178`). Leftover keys from the main VLM call also survive: `_meta` (main pass only) and `attempt` (`extraction/vlm_client.py:214-225` — never stripped by the pipeline). `LocalExtractionClient` adds `_page_type`, `_page_no`, `_page_confidence` (`edge-agent/local_extraction_client.py:96-98`) and on failure substitutes a reduced dict `{screen_id, fields:{}, _status:"ERROR", _error}` with **no** `_meta_agg`/`soggetti`/`canonical_fields` (`edge-agent/local_extraction_client.py:89-94`). Consumers guard with `or {}` (`edge-agent/ui/extraction_results_tab.py:165-171`) and fall back from `canonical_fields` to `fields` (`extraction/evaluation.py:186-217`, `edge-agent/ui/data_table_tab.py:161-208`, `gui_app.py:333-368`, `extraction/cli.py:54-65`).
- **`_meta` shape per VLM call**: `{model, screen_id, attempt, latency_ms, prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd}` — produced at `extraction/vlm_client.py:107-116,167-176,214-223`; consumed by `_aggregate_meta` (`extraction/pipeline.py:330-340`), `print_cost_summary` (`extraction/evaluation.py:249-257`), `gui_app.py:308-315`, `edge-agent/ui/extraction_results_tab.py:201-205`.
- **`canonical_fields` entry shape**: `{schema_key, display_name, page_key, page_name, value, confidence, evidence_text, section}` sorted by `PAGE_SHEET_ORDER` then display_name (`extraction/canonical_mapping.py:20-42`); consumed by `extraction/evaluation.py:186-200`, `extraction/cli.py:45-74`, `gui_app.py:333-354`, `edge-agent/ui/data_table_tab.py:161-208`.
- **Two functions named `build_debug_report` with different arities**: module-level `(outputs, gt, out_csv_path)` (`extraction/evaluation.py:125-129`, called at `gui_app.py:274`) vs `Evaluator.build_debug_report(outputs, out_csv_path)` (`extraction/evaluation.py:275-277`, called at `extraction/cli.py:346`).
- **Batch callbacks**: `on_complete(screen_id, result)` / `on_error(screen_id, exc)` run on the thread that called `BatchRunner.run()` (inside the `as_completed` loop, `extraction/cli.py:235-266`), not on worker threads. Without `on_error`, sequential mode re-raises (`extraction/cli.py:266`) while parallel mode only prints (`extraction/cli.py:251`) — error semantics differ by mode.
- **`ingest_frame` keyword contract**: `(job_id, img: PIL.Image, page_no=0, page_type="", confidence=0.0, fields_json="{}")` — `edge-agent/local_extraction_client.py:65-73`; caller passes all kwargs at `edge-agent/workers/capture/bper_capture_worker.py:696-703`. `fields_json` is accepted but never used by the callee.
- **`export_csv` returns `Optional[str]`** (CSV text or `None` when no results) — `edge-agent/local_extraction_client.py:112-116`; both UI callers check for falsy return (`edge-agent/ui/capture_tab.py:348`, `edge-agent/ui/extraction_results_tab.py:219`).
- **`classify_field(gt_val, pred_val, field_key)` returns `(status, reason)`** with status ∈ {OK, WRONG, MISSING, HALLUCINATED, OK_NULL} — `extraction/normalization.py:113-148`; `build_debug_report` overwrites status with `DATASET_MISMATCH` for mismatched screens (`extraction/evaluation.py:148-149`).
- **`classifier.classify(img)` returns `(Optional[str], float)`** — `edge-agent/page_classifier.py:496`; `(None, 0.0)` when disabled (`edge-agent/page_classifier.py:9-19`).
- **CSV separator/encoding conventions differ per writer**: `;` + `utf-8-sig` in `extraction/evaluation.py:172-177,234-239` and `edge-agent/ui/data_table_tab.py:340-341`; plain `,` + `utf-8` in `LocalExtractionClient.export_csv` (`edge-agent/local_extraction_client.py:131-141`).

### Implicit (review priority)

- **Ordering: anchor pass → main pass → merge → tipo-normalize → retry → coherence → flatten → canonical → status** — `extraction/pipeline.py:109-178`. Downstream steps assume prior mutations: `_retry_areas` reads `result["fields"]` already containing merged anchors (`extraction/pipeline.py:252-257`); `_coherence_check` runs after retries so tooltips reflect the best pass (`extraction/pipeline.py:151-152`). **verified at** call sequence `extraction/pipeline.py:110-170`.
- **Ordering: soggetti flatten runs AFTER retry merge and overwrites unconditionally.** `extraction/pipeline.py:161-166` assigns `fields["ndg_N"/"denominazione_N"/"ruolo_N"]` from `soggetti[:4]` regardless of what `pick_best` selected for those same keys during retries (`ndg_1..ruolo_4` are retryable BODY fields, `extraction/config.py:73-76`), and does not update `_field_sources` for them. A `None` value inside a `soggetti` row overwrites a non-null retried field value. **unverified** (no guard; nothing prevents the overwrite).
- **Ordering: `start_job()` must precede worker start.** `BPERCaptureWorker._capture_once()` no-ops when `job_id_getter()` returns falsy (`edge-agent/workers/capture/bper_capture_worker.py:466-469`); CaptureTab sets `self.job_id` before constructing the worker (`edge-agent/ui/capture_tab.py:197-232`). **verified at** `edge-agent/ui/capture_tab.py:207,227`.
- **Ordering: env must be populated before `extraction.config` import.** All config constants are read at module import time (`extraction/config.py:8-56`). `main.py:7-8` loads `.env` before `from extraction import *`; `edge-agent/local_extraction_client.py:22-25` loads `.env` before importing `extraction`. `gui_app.py` imports `extraction` at `gui_app.py:6-14` **without any `load_dotenv`** — it assumes env vars are already exported (grep: no `load_dotenv` in `gui_app.py`). **unverified** for the Tkinter path.
- **State precondition: `extract_from_image()` expects an already-normalized/preprocessed image.** It skips `normalize_image()` by design; the edge-agent preprocesses via `preprocess_for_ocr()` first (`edge-agent/workers/capture/bper_capture_worker.py:576-583`, comment at `edge-agent/local_extraction_client.py:84-85`). Nothing checks image size/quality at the callee. **documented** (`edge-agent/local_extraction_client.py:84-85`) but not enforced.
- **State precondition: anchor gate.** Intended contract: anchors with confidence `< ANCHOR_CONF_MIN` are nulled before use (`extraction/pipeline.py:90-96`). Actual mechanics: (a) `safe_set_field(..., value=None)` cannot overwrite an existing non-null value because of the guard `if value is not None or f.get("value") is None` (`extraction/normalization.py:78-79`); (b) the returned `ndg`/`den` dicts are copies taken *before* the gate (`extraction/pipeline.py:87-88` vs `:91-96`), and it is those copies that feed the `STOP_ON_ANCHOR_UNCERTAIN` early exit (`extraction/pipeline.py:112-113`), the hint prompt (`:205-208`), and `_merge_anchors` (`:212-216`). Net effect: low-confidence anchors are not filtered anywhere downstream. **unverified** (no test; no assertion; behavior diverges from the gate's stated intent and from `CLAUDE.md`'s "zeroes out low-confidence anchors").
- **Side-effect contract: every VLM call must populate `_meta` with cost/token/latency fields** (declared load-bearing in `CLAUDE.md` "Architectural Constraints" #2); all three producer paths comply (`extraction/vlm_client.py:107-116,167-176,214-223`). `estimate_cost_usd` silently returns `0.0` for models absent from `PRICING_PER_1M` (`extraction/vlm_client.py:23-26`) — cost aggregation under-counts without signal.
- **Retry-classification contract: `ValueError` means "do not retry".** `call_vlm_with_retry` re-raises `ValueError` immediately and retries everything else with capped backoff, max 3 attempts (`extraction/vlm_client.py:252-258`). All parse/validation failures are deliberately raised as `ValueError` (`extraction/vlm_client.py:39,44,95,153,200`). Any future exception type introduced in `call_vlm` silently becomes "transient, retry 3x".
- **Retry failure is non-fatal**: a failed area retry keeps main-pass results and only prints a warning (`extraction/pipeline.py:288-292`); the failed call's `_meta` is NOT appended to `attempts_meta` (`extraction/pipeline.py:294` is only reached on success), so `_meta_agg.calls` undercounts failed attempts (tokens may still have been billed by the retry wrapper's earlier attempts).
- **Duck-typing contract between worker and client**: `BPERCaptureWorker._upload_page()` requires only `hasattr(api_client, "ingest_frame")` (`edge-agent/workers/capture/bper_capture_worker.py:693`); anything else logs a client-misconfiguration error (`:711`). `CaptureTab` additionally assumes `api_client` has `start_job()`, `export_csv()`, `result_ready` (`edge-agent/ui/capture_tab.py:179,212,347`).
- **Concurrency: `ExtractionPipeline` and its ChatModels are assumed thread-safe and shared** across batch workers (`extraction/cli.py:159-163,181`) and across nested retry executors (`extraction/pipeline.py:284`). Assumed, stated in comments/docstrings (`extraction/pipeline.py:50-51`); not verified in-repo.
- **Concurrency: `ingest_frame()` runs synchronously in the capture QThread** (`edge-agent/local_extraction_client.py:77-79`); result storage is lock-guarded (`:100-103`); UI updates ride the Qt signal (`:105-106`). A slow extraction blocks the capture loop for its whole duration (FPS loop in `edge-agent/workers/capture/base_capture_worker.py:51-59`).
- **Concurrency: `force_capture()` executes on the UI thread**, not the worker thread — `edge-agent/ui/capture_tab.py:404` invokes the slot directly on the QThread object; it then uses `self._mss_ctx` (`edge-agent/workers/capture/bper_capture_worker.py:739` → `:557-574`), the same mss context the capture loop uses concurrently. No lock protects `_mss_ctx`, `_last_frame_hash`, or `captured_page_types` across the two threads. **unverified**.
- **Concurrency: `stop()` closes `_mss_ctx` from the caller's thread** while the run loop may still be inside `_capture_once()` (`edge-agent/workers/capture/bper_capture_worker.py:214-222`); `CaptureTab` calls `stop()` *then* `wait(5000)` (`edge-agent/ui/capture_tab.py:307-308`). **unverified**.
- **Idempotency: re-ingesting the same page appends a new result** — `LocalExtractionClient._results[job_id]` is append-only (`edge-agent/local_extraction_client.py:100-103`); `force_capture` and re-detection after hash change can produce multiple rows for the same page. Batch-side dedup (`_deduplicate_same_page_outputs`) is implemented but disabled (`extraction/cli.py:268-273`).
- **`screen_id` uniqueness in a batch relies on unique file stems**: `screen_id = splitext(basename(path))[0]` keys the `outputs` dict (`extraction/cli.py:225-227,240`); `a.png` and `a.jpg` collide silently.
- **Edge-agent screen IDs never match GT keys**: `ingest_frame` builds `"{Friendly} — pag. {n}"` (`edge-agent/local_extraction_client.py:80-81`) while GT/eval keys are file stems like `"screen 1"` (`extraction/evaluation.py:79-81`); the evaluation path is only meaningful for CLI/Tkinter outputs.

## Invariants

| Invariant | Scope | Source | Enforcement |
|-----------|-------|--------|-------------|
| `FieldsModel` fields == `FIELD_KEYS` (45 keys) | schemas | `extraction/schemas.py:46-49` | by construction (`create_model` over `FIELD_KEYS`) |
| Every VLM response dict contains `fields`, `soggetti`, `fidi`, `garanzie` (ExtractionResponse) or `fields.{ndg,denominazione}` (AnchorResponse) | vlm_client → pipeline | `extraction/schemas.py:54-65`, `extraction/vlm_client.py:93,147,193` | Pydantic validation; `ValueError` on failure |
| Total VLM calls per screen ≤ `MAX_CALLS_PER_SCREEN` (1 anchor + 1 main + `max(0, MAX-2)` retries) | pipeline | `extraction/pipeline.py:261-266` | runtime slice of the retry areas in `AREA_TO_FIELDS` declaration order; `MAX_CALLS_PER_SCREEN` is derived as `2 + len(AREA_TO_FIELDS)` so the slice covers every area |
| Retry triggers only for fields nullish or confidence < 0.60 | pipeline | `extraction/pipeline.py:251-257` | runtime check (0.60 hardcoded) |
| `pick_best`: non-null beats null; both same nullness → `f1` (current) wins on `c1 >= c2` | normalization | `extraction/normalization.py:87-96` | runtime logic; source attribution depends on object identity (`chosen is candidate`, `extraction/normalization.py:105-107`) |
| `_meta_agg` totals = sum over `_attempts` entries; cost rounded to 6 decimals | pipeline | `extraction/pipeline.py:330-340` | runtime aggregation (only successful calls counted, see Contracts) |
| `_field_sources[k]` ∈ {CONTENT_MAIN, ANCHOR_HEADER, RETRY_HEADER, RETRY_BODY, RETRY_FOOTER} | pipeline | `extraction/pipeline.py:141,216,306` | by construction; NOT updated by the soggetti flatten (`extraction/pipeline.py:161-166`) |
| `_status` == "OK" iff both `ndg` and `denominazione` values are non-None at the end | result dict | `extraction/pipeline.py:173-178` | runtime check |
| `AREA_TO_FIELDS` keys ⊆ `FIELD_KEYS`; 6 fields (`creazione`, all 5 `tooltip_*`) belong to **no** retry area and can never be retried | config | `extraction/config.py:69-82` vs `extraction/fields.py:12-54` | none (no startup guard exists; `CLAUDE.md`'s claimed `if/raise` guards for `FIELD_RETRY_MAP`/`_FIELD_COMPARATORS` are absent from code — grep confirms neither exists) |
| `CSV_TO_SCHEMA` values ⊆ `FIELD_KEYS` | fields/evaluation | `extraction/fields.py:56-100` | none; unmapped GT keys are silently skipped in eval (`extraction/evaluation.py:88-90`) |
| Every `page_key` in `CANONICAL_FIELD_DEFINITIONS` ∈ `PAGE_SHEET_ORDER` (4 keys) | canonical layer | `extraction/field_definitions.py:5-186`, `extraction/page_definitions.py:23-28` | none; unknown keys sort last (`extraction/canonical_mapping.py:12-14`) |
| `confidence` ∈ [0,1] | all field payloads | prompt instruction only (`prompts/*.json`, Italian prompts) | none — model-supplied float trusted everywhere (gates at `extraction/pipeline.py:91,255`, `extraction/cli.py:87-88`) |
| Anchors below `ANCHOR_CONF_MIN` are excluded from downstream use | pipeline | intended at `extraction/pipeline.py:90-96` | **ineffective** — see Contracts → Implicit (anchor gate); copies pre-date the gate and `safe_set_field` cannot null an existing value (`extraction/normalization.py:78-79`) |
| `captured_page_types` grows monotonically within a job; drives operator guidance only | BPER worker | `edge-agent/workers/capture/bper_capture_worker.py:532,760` | runtime set; NOT consulted before re-uploading an already-captured page (`_capture_once` has no membership check, `:491-533`); docstring's "stop automatico quando tutte le pagine previste sono acquisite" (`:45`) has no implementing code |
| A page is uploaded only after the same `page_type` is detected continuously for ≥ 2 s | BPER worker | `edge-agent/workers/capture/bper_capture_worker.py:49,498-527` | runtime stability timer; bypassed by `force_capture` (`:726-764`) |
| Duplicate frames (pHash Hamming ≤ threshold) skip routing except one retry per `route_retry_seconds` | BPER worker | `edge-agent/workers/capture/bper_capture_worker.py:476-489,601-624` | runtime; hash state is only updated when distance > threshold (`:617-624`) |
| Router may only return page names defined in `prompts.json`; others are nulled | LLM router | `edge-agent/llm_router.py:225-230` | runtime hallucination guard (case-insensitive remap) |
| "Altro / Non riconosciuto" is never captured/uploaded | BPER worker + UI | `edge-agent/workers/capture/bper_capture_worker.py:32,491`, `edge-agent/ui/capture_tab.py:34,167` | runtime frozenset checks (duplicated in two files) |
| `_results[job_id]` mutations always under `self._lock`; reads return copies | LocalExtractionClient | `edge-agent/local_extraction_client.py:100-103,147-153` | `threading.Lock` (shallow copies — inner dicts still shared with UI, `:106,149`) |
| 5 consecutive screenshot failures stop the worker | BPER worker | `edge-agent/workers/capture/bper_capture_worker.py:97-98,588-599` | runtime counter |

## Domain Rules

- NDG + DENOMINAZIONE are the identity anchors of a practice; if either disagrees with ground truth (numeric-normalized for NDG, text-normalized for DENOMINAZIONE), the entire screen is flagged `DATASET_MISMATCH` and excluded from FILTERED metrics — `extraction/normalization.py:174-189`, `extraction/evaluation.py:84,99-104,148-149`.
- Anchor identity may be satisfied by the `soggetti` table when the header field is null (`_resolve_anchor_value` falls through fields → soggetti) — `extraction/normalization.py:162-172`.
- `tipo` values "mutui spesa"/"mutuo spesa"/"bpi mutui" canonicalize to "BPI Mutui" — `extraction/normalization.py:10-23`, applied post-main (`extraction/pipeline.py:146,218-223`) and per-retry-candidate (`:298-299`).
- Coherence rule 1: if `tooltip_evidenze_b` has a value, `evidenze` must be "B"; a null or purely-numeric `evidenze` is repaired to "B" — `extraction/pipeline.py:317-322`.
- Coherence rule 2: if `tooltip_descrizione_bmb` has a value and `tipo` is null, `tipo` is set to "BMB" — `extraction/pipeline.py:324-328`.
- Numeric-equality fields: any field whose key contains `importo_euro`, `ndg`, or `n_fido` is compared after currency/thousands normalization (`,`→`.`, strip `€`/spaces) — `extraction/normalization.py:127-133,40-55`. Substring semantics extend this to `ndg_1..4`.
- Text fields longer than 20 chars pass with fuzzy ratio ≥ 0.85 — `extraction/normalization.py:143-146`.
- Nullish vocabulary: `"", "n/d", "nd", "---", "null", "none", "nan"` all count as null — `extraction/normalization.py:28-32`.
- At most 4 soggetti (co-holders) are represented as flat fields `ndg_1..4` / `denominazione_1..4` / `ruolo_1..4` — `extraction/pipeline.py:161-166`, `extraction/fields.py:35-38`.
- The client-facing field universe is grouped into exactly 4 canonical pages in a fixed sheet order: `risultato_ricerca`, `elenco_soggetti`, `gestione_fidi_e_garanzie`, `note_da_richiesta` — `extraction/page_definitions.py:5-28`.
- BPER capture recognizes only pages defined in `edge-agent/assets/templates/bper/prompts.json` (10 defs incl. catch-all); the catch-all is never acquired — `edge-agent/workers/capture/bper_capture_worker.py:294-306,32`.
- Retry table merge prefers more rows; on equal row count, higher mean confidence wins (BODY area only) — `extraction/pipeline.py:225-241`.
- Italian field keys are load-bearing domain terms and must match GT CSV labels via `CSV_TO_SCHEMA` — `extraction/fields.py:56-100` (incl. whitespace-variant keys like `"Evidenze "` at `:65` and `"Valore rilevato "` at `extraction/evaluation.py:45`).

## Assumptions

| Assumption | Status | Evidence |
|-----------|--------|----------|
| `LLM_API_KEY` (or legacy var / GUI input) is set before any model construction | verified | raised at `extraction/llm_factory.py:41-44`; surfaces at `BatchRunner.__init__` (`extraction/cli.py:182`) and app boot (`edge-agent/ui/main_window.py:37`) |
| `mnt/data/dati.csv` exists for CLI runs | verified | `extraction/cli.py:315-316` raises `FileNotFoundError`; file is absent from repo (context-brief Open Questions; `/mnt` gitignored) |
| GT CSV has recognizable screen/key/value columns | verified | `_find_column` raises `ValueError` (`extraction/evaluation.py:26-31,38-52`) |
| Env vars are set before `extraction.config` is imported (import-time reads) | verified for `main.py:7-8` and `edge-agent/local_extraction_client.py:22-25`; **unverified for `gui_app.py`** (no `load_dotenv`; imports at `gui_app.py:6-14`) | `extraction/config.py:8-56` |
| LangChain ChatModel instances are thread-safe for concurrent `.invoke()` | documented | `extraction/cli.py:161-163,181`, `extraction/pipeline.py:50-51`; no in-repo verification |
| GUI-selected provider is compatible with env-derived anchor model (`gui_app` passes `model_main` but never `model_anchor`; anchor falls back to `LLM_MODEL_ANCHOR` default `gpt-4o`) | unverified | `gui_app.py:238-247`, `extraction/cli.py:177,187-191`; mismatch raises at `extraction/llm_factory.py:59-63` when provider=gemini |
| Image passed to `extract_from_image()` is already normalized/preprocessed | documented | `edge-agent/local_extraction_client.py:84-85`; enforcement absent at `extraction/pipeline.py:104-107` |
| Model-returned `confidence` is a sane float in [0,1] | unverified | trusted at `extraction/pipeline.py:91,255`, `extraction/normalization.py:94-96`, `extraction/cli.py:87-88`; only prompt-level instruction |
| Model names used at runtime exist in `PRICING_PER_1M` (else cost silently 0.0) | unverified | `extraction/vlm_client.py:23-26`, `extraction/config.py:36-49` |
| Tkinter widgets may be touched from the worker thread (`log_area.insert`, `messagebox`, `btn_run.config`) | unverified | worker thread started `gui_app.py:225-226`; cross-thread widget access at `gui_app.py:199-201,258-277,279,285`; only `display_results` is marshaled via `self.after(0, ...)` (`gui_app.py:278`) |
| `force_capture` may safely share `_mss_ctx` / worker state with the capture loop across threads | unverified | direct cross-thread call `edge-agent/ui/capture_tab.py:404`; shared state `edge-agent/workers/capture/bper_capture_worker.py:557-574,739` |
| Closing `_mss_ctx` in `stop()` before `wait()` completes is safe | unverified | `edge-agent/workers/capture/bper_capture_worker.py:214-222`, `edge-agent/ui/capture_tab.py:307-308` |
| Qt signal emission from QThread is safe for cross-thread UI updates | documented | `edge-agent/local_extraction_client.py:105-106` ("Qt signal is thread-safe across QThread boundaries") |
| `result_ready` payload dicts are not mutated by receivers (only shallow-copied at emit) | unverified | `dict(result)` shallow copy `edge-agent/local_extraction_client.py:106`; `get_results` shallow list copy `:147-149`; nested dicts shared with UI (`edge-agent/ui/extraction_results_tab.py:175`) |
| `prompts.json` exists and is valid JSON | verified (degraded) | fallback to empty spec `edge-agent/llm_router.py:96-103`; empty pages ⇒ router matches nothing |
| torch/DINOv2 available for ML routing | verified (degraded) | classifier self-disables, `classify() → (None, 0.0)` (`edge-agent/page_classifier.py:9-19`); import guarded `edge-agent/workers/capture/bper_capture_worker.py:18-21` |
| `config.ini [llm] api_key` is a usable OpenAI key (committed secret) | unverified | `edge-agent/config.ini:23` (live-looking `sk-proj-...` key committed); precedence config→`OPENAI_API_KEY`→`LLM_API_KEY` at `edge-agent/workers/capture/bper_capture_worker.py:122` |
| `monitor_index` refers to an existing monitor | verified | fallback to monitor 1 (`edge-agent/workers/capture/bper_capture_worker.py:569-571`) |
| Optional page-sequence sources (`Guida pagine ITA .xlsx`, `Nomenclatura.csv`) may be absent | verified | existence-checked with fallback to `prompts.json` (`edge-agent/workers/capture/bper_capture_worker.py:271,296-306,326-331`); neither file exists in repo |
| Generic-mode backend at `{api.base_url}/jobs/{job_id}/frames` is reachable | unverified | `edge-agent/workers/capture/default_capture_worker.py:61-66`; `config.ini:10` points at `http://localhost:8081`; no such service in repo |
| File stems of input images are unique per batch (screen_id collisions overwrite) | unverified | `extraction/cli.py:225-227,240` |
| `_capture_once` exceptions are non-fatal (loop continues) | verified | caught and emitted per-iteration (`edge-agent/workers/capture/base_capture_worker.py:53-56`) |
| Screens processed by eval exist in both `outputs` and GT (missing screens silently skipped) | verified | `extraction/evaluation.py:80-82,134-136` |

## Integration Hot-Spots

| Type | Location | Direction | Risk class | Notes |
|------|----------|-----------|-----------|-------|
| OpenAI/Gemini API (LangChain, extraction) | `extraction/vlm_client.py:147-149,193-196` (structured), `:76-81` (Gemini free-form) | out | timeout, retry, cost, schema-drift | Retry policy `extraction/vlm_client.py:239-258`; Gemini schema-mode gate `extraction/vlm_client.py:18,134-138`; no explicit timeout configured on ChatModels (`extraction/llm_factory.py:54,75`) |
| OpenAI API (raw SDK, page router) | `edge-agent/llm_router.py:200-209` | out | timeout, retry, hallucination | 2 attempts, 0.5s/1.0s backoff (`:191,249`); `response_format=json_object`, `temperature=0.0`, `timeout` from config.ini; page-name validation `:225-230` |
| Screen capture (mss) | `edge-agent/workers/capture/bper_capture_worker.py:557-574` | in | lifecycle, cross-thread use | Context lazily created in capture thread `:557-560`, closed in `stop()` from caller thread `:214-222`, also used from UI thread via `force_capture` `:739` |
| Screen capture (pyscreenshot) | `edge-agent/workers/capture/default_capture_worker.py:82-84` | in | platform availability | generic mode only |
| Remote frame ingest HTTP | `edge-agent/workers/capture/default_capture_worker.py:62-66` | out | dead-endpoint, timeout 30s | `POST {base_url}/jobs/{id}/frames`; base_url `edge-agent/config.ini:10`; no backend in repo |
| Env vars | `extraction/config.py:8-56,92-94`, `extraction/llm_factory.py:30-44,72-74`, `edge-agent/workers/capture/bper_capture_worker.py:122` | in | missing, wrong-type, import-time snapshot | `int()`/`float()` casts raise on malformed values at import (`extraction/config.py:11,54,56`) |
| `.env` loading | `main.py:7`, `edge-agent/edge_agent.py:9-13`, `edge-agent/local_extraction_client.py:21-25`; absent in `gui_app.py` | in | missing-config path divergence | see Assumptions |
| `config.ini` (committed) | `edge-agent/config.py:128-269` reads; `edge-agent/config.ini:23` contains a committed OpenAI API key | in | secret-leak, stale remote-era sections | `[api]`/`[minio]`/`[dataset]` consumed by no active BPER-path code (`edge-agent/workers/capture/bper_capture_worker.py:713-715` is a no-op stub); `AgentConfig.save()` would re-persist the key (`edge-agent/config.py:326-332`, currently uncalled) |
| GT CSV read | `extraction/evaluation.py:35` (`pd.read_csv`) | in | schema-drift, encoding | column aliasing `:38-52` |
| Screenshot dir scan | `extraction/cli.py:322-327` | in | unexpected files | all `.png/.jpg/.jpeg` in `INPUT_DIR`, sorted lexically |
| Outputs JSON write | `extraction/cli.py:337-340` | out | persisted-shape dependency | `poc_outputs_improved.json` mirrors the full result dict incl. `_meta`, `_attempts` |
| Debug/eval CSV writes | `extraction/evaluation.py:172-177,234-239` | out | delimiter/encoding contract (`;`, utf-8-sig) | `poc_debug_improved.csv`, `poc_results_gui.csv` (via `gui_app.py:251-256,273-274`) |
| Edge-agent CSV/Excel exports | `edge-agent/local_extraction_client.py:112-143`, `edge-agent/ui/data_table_tab.py:325-398`, `edge-agent/ui/capture_tab.py:338-376`, `edge-agent/ui/extraction_results_tab.py:213-229` | out | client-facing shape, delimiter divergence | three distinct CSV shapes for the same data (flat wide, canonical wide `;`, per-field rows) |
| Debug crop writes | `extraction/imaging.py:37-42` | out | disk usage; screen_id used in filename (edge-agent IDs contain `—` and spaces, `edge-agent/local_extraction_client.py:80-81`) | gated by `DEBUG_SAVE_CROPS` (`extraction/config.py:93`) |
| prompts.json / template assets | `edge-agent/llm_router.py:96-103`, `edge-agent/workers/capture/bper_capture_worker.py:255-306`, `edge-agent/ui/capture_tab.py:156-170` | in | drift between 3 independent readers | page-name set is read separately by router, worker, and UI combo |
| Prototype cache JSON | `edge-agent/page_classifier.py:104-107` (`bper_page_prototypes.json`) | in | staleness vs template images | rebuilt/validated inside classifier (`:285`) |
| Optional Excel/CSV page sequence | `edge-agent/workers/capture/bper_capture_worker.py:256-364` (openpyxl, csv) | in | absent files, fuzzy label mapping | difflib best-match normalization `:388-451` |
| Qt signals across threads | `edge-agent/local_extraction_client.py:42,106`; `edge-agent/workers/capture/base_capture_worker.py:17-20`; connects `edge-agent/ui/capture_tab.py:212,259-267`, `edge-agent/ui/extraction_results_tab.py:65`, `edge-agent/ui/data_table_tab.py:98` | in/out | UI-state race, shallow-copied payloads | counter connect/disconnect per session `edge-agent/ui/capture_tab.py:211-214,313-315` |
| Tkinter UI state from worker thread | `gui_app.py:199-201,225-285` | in/out | cross-thread widget access | only `display_results` uses `after(0, ...)` (`gui_app.py:278`) |
| sys.path mutations | `edge-agent/local_extraction_client.py:17-19`, `edge-agent/ui/data_table_tab.py:31-33`, `main.py:16-19` | in | import-order coupling | edge-agent modules import each other by flat name (`edge-agent/workers/capture/bper_capture_worker.py:16,24`) — requires `edge-agent/` on `sys.path` |

## Change Impact Radius

- **`FIELD_KEYS` (`extraction/fields.py:12-54`)** — adding/renaming a key ripples to: `FieldsModel` (auto, `extraction/schemas.py:46-49`), retry coverage (`AREA_TO_FIELDS`, `extraction/config.py:69-82` — a key not added there is never retried), GT mapping (`CSV_TO_SCHEMA`, `extraction/fields.py:56-100`), canonical layer (`CANONICAL_FIELD_DEFINITIONS`/`FIELD_LABEL_ALIASES`, `extraction/field_definitions.py:5-235` — unmapped keys fall back to raw key display, `extraction/fields.py:118-126`), Italian prompt text (`extraction/prompts.py:3-72`), all exports and both GUIs (field iteration at `extraction/evaluation.py:203`, `gui_app.py:357`).
- **Per-screen result dict shape (`extraction/pipeline.py:104-180`)** — consumers: `extraction/cli.py:45-89,337-340` (JSON persist + dedup helpers), `extraction/evaluation.py` (eval `:74-120`, debug report `:125-177`, export `:182-239`, cost `:244-258`), `gui_app.py:287-397`, `edge-agent/local_extraction_client.py:96-143`, `edge-agent/ui/extraction_results_tab.py:159-211`, `edge-agent/ui/data_table_tab.py:161-208,280-306`, capture counter (`edge-agent/ui/capture_tab.py:378-381`).
- **`_meta` / `_meta_agg` keys (`extraction/vlm_client.py:107-116`, `extraction/pipeline.py:330-340`)** — consumers: `extraction/evaluation.py:139,165-168,249-257`, `gui_app.py:308-315`, `edge-agent/ui/extraction_results_tab.py:171-173,201-205`.
- **`ingest_frame()` signature (`edge-agent/local_extraction_client.py:65-73`)** — sole caller `edge-agent/workers/capture/bper_capture_worker.py:696-703`; the duck-typing check `:693` means signature drift fails only at call time.
- **`canonical_fields` entry shape (`extraction/canonical_mapping.py:20-42`)** — consumers: `extraction/evaluation.py:186-200`, `extraction/cli.py:45-74` (currently-disabled dedup), `gui_app.py:333-354`, `edge-agent/ui/data_table_tab.py:161-208`; described as the client-facing contract (`extraction/canonical_mapping.py:1`).
- **`RouterResult` / `route()` contract (`edge-agent/llm_router.py:27-39`)** — consumers: `edge-agent/workers/capture/bper_capture_worker.py:628-675` (detection + hybrid fallback), Debug tab JSON stream (`:636-642`).
- **Persisted data shape dependencies**: `mnt/data/poc_outputs_improved.json` (`extraction/cli.py:337-340`), `poc_outputs_gui.json`/`poc_results_gui.csv`/`poc_debug_gui.csv` (`gui_app.py:250-274`), `poc_debug_improved.csv` (`extraction/cli.py:345-346`), operator-exported CSV/XLSX files (`edge-agent/ui/*`), DINOv2 prototype cache (`edge-agent/page_classifier.py:104-107`), `prompts.json` page names (three independent readers, see Hot-Spots).
- **Tests encoding contracts**: none — no test suite exists in the repo (confirmed by file inventory; `CLAUDE.md` "Missing Infrastructure").
- **Downstream services**: none live. Dead couplings: generic-mode ingest API (`edge-agent/workers/capture/default_capture_worker.py:62-66`), MinIO/dataset config remnants (`edge-agent/config.ini:12-16,25-29`, stub at `edge-agent/workers/capture/bper_capture_worker.py:713-715`).

## Reviewer Hints

> Sections below suggest which reviewer should focus on which anchor.

- **security-auditor**: `## Integration Hot-Spots` (committed API key `edge-agent/config.ini:23`, `AgentConfig.save()` re-persisting secrets, env-var key precedence), `## Assumptions` (unverified rows: committed key, generic-mode endpoint).
- **code-auditor**: `## Invariants` (missing startup guards vs CLAUDE.md claims; retry-coverage gap for `creazione`/tooltips; dead public surface in Call Graph), `## Contracts` (structural: dual `build_debug_report` signatures, divergent CSV conventions, error-result shape).
- **logic-integrity-auditor**: `## Contracts` → Implicit (anchor confidence gate ineffective; soggetti flatten overwrites retry winners; `ValueError`-means-no-retry taxonomy), `## Invariants` (pick_best tie semantics, `_meta_agg` undercount on failed retries), `## Domain Rules` (coherence repairs, numeric-field substring matching), `## Assumptions` (unverified: confidence range, pricing coverage, GUI anchor-model mismatch).
- **distributed-flow-auditor**: `## Integration Hot-Spots` (LangChain vs raw-SDK LLM paths, retry/backoff policies, dead remote endpoint), `## Call Graph` (duck-typed `ingest_frame` boundary, sys.path bridges).
- **chicken-egg-detector**: `## Assumptions` (import-time env snapshot in `extraction/config.py`; `.env` loading order per entry point; `gui_app.py` missing `load_dotenv`), `## Integration Hot-Spots` (Env vars, `config.ini`, prompts.json triple-read).
- **ui-race-auditor**: `## Contracts` → Implicit (concurrency: `force_capture` on UI thread, `stop()` vs run loop, synchronous `ingest_frame` in capture thread), `## Invariants` (lock-guarded `_results`, shallow-copy signal payloads), `## Assumptions` (Tkinter cross-thread widget access rows).
- **api-contract-auditor** (planned, not yet implemented): `## Contracts` (formal: Pydantic schemas, `RouterResult`, canonical_fields client contract).
