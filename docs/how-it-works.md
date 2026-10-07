# How It Works -- poc-data-extraction

English reference for the extraction pipeline, its three entry points and live capture.
The official Italian guide covers [architecture](04-architecture.md),
[workflows](05-workflows.md), [data](06-data-model.md) and [Python APIs](12-python-api.md).

## Multi-pass extraction pipeline

Each screenshot is processed in three stages by `ExtractionPipeline` in `extraction/pipeline.py`
(`extract_from_screen()` / `extract_from_image()`):

1. **Anchor pass** -- `extract_anchors()` reads the header region on calibrated file images,
   or the whole image off calibration, and extracts only NDG +
   DENOMINAZIONE. A confidence gate (`>= 0.95`, `ANCHOR_CONF_MIN`) nulls the `value` of any anchor
   read below the threshold, and it **is** effective: `safe_field()` returns a fresh dict
   (`normalization.py:77-86`) and the gate mutates those same dicts in place before returning them
   (`pipeline.py:98-103`). Below threshold the value reaches neither `_merge_anchors()` nor the
   main-pass hint, so the model-reported confidence is a binary switch here, not a soft signal.
   With `STOP_ON_ANCHOR_UNCERTAIN=1` the pipeline exits early when both anchor *values* are null.
2. **Main pass** -- the selected content crop, or the whole image when cropping is not
   authorized or calibrated, is sent to the VLM together with anchor hints
   (`extraction_anchor_hints`, framed as non-authoritative clues the model must verify against the
   image). Extracts all scalar fields plus the soggetti / fidi / garanzie arrays in one call.
3. **Conditional retry** -- an area (HEADER / BODY / FOOTER) is retried when any of its fields is
   nullish or below `RETRY_CONF_MIN` (default `0.60`). Each area gets a dedicated crop and an
   area-specific Italian prompt; only BODY (contrast 1.3 / sharpness 2.5) and HEADER (1.4 / 3.5)
   also get an image boost, FOOTER gets none (`pipeline.py:274-282`). At most
   `max(0, MAX_CALLS_PER_SCREEN - 2)` areas are retried (anchor + main already count,
   `pipeline.py:305-317`), selected in `AREA_TO_FIELDS` declaration order and then executed
   concurrently. `MAX_CALLS_PER_SCREEN` therefore
   defaults to `2 + len(AREA_TO_FIELDS)` (= 5), derived rather than a literal: below that the
   trailing areas are structurally unreachable. A page showing a single section makes every *other*
   area look weak (their fields legitimately are not there), so those areas consume the whole budget
   before the area holding the page's payload is ever retried. That is how FOOTER, which owns
   `note_della_richiesta`, used to lose its retry on the Note da Richiesta page.
   The per-field winner is chosen by
   `pick_best()`: non-null beats null; on equal nullness the current value wins unless the candidate
   has strictly higher confidence. Only the retried area's own fields are merged back, and the
   arrays only for BODY (`pipeline.py:305-318`).
   **Retry coverage gap:** `creazione` and the 5 `tooltip_*` fields belong to *no* retry area
   (`AREA_TO_FIELDS`, `extraction/config.py:81`), so they can never be retried. A failed area
   retry is non-fatal (main-pass values are kept, warning printed).

The call budget counts logical passes, not HTTP requests. `call_vlm_with_retry()` can
attempt each pass up to three times. It immediately re-raises `ValueError`, `KeyError`
and `IndexError`; other exceptions enter backoff. Anchor and main still run when the
configured budget is below two, unless the early anchor exit applies.
<!-- Source: extraction/vlm_client.py:63; extraction/pipeline.py:151; extraction/pipeline.py:305 -->

Post-processing order is load-bearing (`pipeline.py:154-176`): anchors are merged back and `tipo`
normalized *before* retries; the coherence check (repairs `evidenze` / `tipo` from their tooltips)
runs *after* retries; then `soggetti[:4]` are flattened to `ndg_1..4` / `denominazione_1..4` /
`ruolo_1..4` for CSV-style evaluation. This flatten runs after the retry merge and overwrites those
fields from the soggetti rows (even with `None` values) without updating `_field_sources`
(`pipeline.py:169-176`) -- but only for rows actually present, so with an empty `soggetti` the flat
values the model produced survive.

Two entry methods exist by design:
- `extract_from_screen(path)` -- used by CLI and the Tkinter GUI; normalizes the image internally
  and permits the content crop only when the image belongs to the calibrated family.
- `extract_from_image(img, screen_id)` -- used by `LocalExtractionClient`; the image is already
  preprocessed by the edge-agent, so `normalize_image()` is intentionally bypassed. Content
  cropping defaults to disabled; the method still clamps the long side to
  `MAX_IMAGE_LONG_SIDE` (default 2000 pixels).

## Three run modes

- **CLI** (`python main.py`): batch-processes every `.png/.jpg/.jpeg` in `INPUT_DIR`, writes JSON
  results, prints accuracy metrics and a cost summary. Hard-requires `mnt/data/dati.csv`
  (`FileNotFoundError` at `extraction/cli.py:320`); the CSV is **not** in the repo -- see
  Data & Evaluation.
- **Tkinter GUI** (`python gui_app.py`): desktop window for uploading screenshots, picking
  provider/model, viewing per-screen results, and exporting CSV/JSON. Imports
  `run_extraction_batch()` from the `extraction` package.
- **Edge-agent** (`python edge-agent/edge_agent.py`, or `python main.py --gui`): PyQt6 app that
  captures BPER screens in real time, detects the page type, and runs extraction locally via
  `LocalExtractionClient`. The direct entry runs preflight before importing the UI and engine;
  `main.py --gui` has already imported `extraction` and requires the environment to be ready.

CLI and the Tkinter GUI share `run_extraction_batch()` in `extraction/cli.py` -- do not duplicate the
`ThreadPoolExecutor` logic.

## Edge-agent capture flow

The edge-agent coordinates live extraction locally, without a separate application backend.
The extraction models still call external providers.

```
BPERCaptureWorker (QThread)
  ├── Drains queued manual requests and extraction acknowledgements
  ├── Captures screenshot via mss (whole monitor)
  ├── Normalizes framing to the app window via frame_normalize.normalize_frame()
  ├── Compares pixel identity: changed frame starts a new visit and stability interval
  ├── Skips unchanged visits whose extraction is pending or completed
  ├── Uses pHash to confirm an existing candidate without another router call
  ├── Preprocesses (scale, unsharp, autocontrast) when routing or extraction needs the image
  ├── Detects page type via router (LLM or ML)
  ├── Stability check (StabilityTracker: >= 2 concordant matches AND >= 2.0s presence, 1 miss tolerated)
  └── _upload_page() → LocalExtractionClient.ingest_frame() -- returns accepted capture sequence
                           └── DaemonThreadPool (PARALLEL_WORKERS daemon threads, shared ExtractionPipeline)
                                   └── ExtractionPipeline.extract_from_image()
                                           ├── Anchor pass (whole live image → NDG + DENOMINAZIONE)
                                           ├── Main pass (full content → all fields)
                                           └── Retry pass (low-confidence fields only)
                                       → logs diagnostics → stores result by capture sequence
                                       → publishes the contiguous completed prefix to get_results()
                                       → emits result_ready(job_id, result)
                                             ├── queues acknowledgement for the capture worker
                                             └── DataTableTab (Dati Estratti)
                                                     └── get_results() → consolidate() → one row per practice
```

- **Detection hook:** `BPERCaptureWorker._upload_page()` detects `LocalExtractionClient` via
  `hasattr(api_client, "ingest_frame")` and calls it directly (asynchronously: the frame is queued and
  extracted on `LocalExtractionClient`'s internal daemon pool). A rejected enqueue raises
  `RuntimeError`; it emits no `frame_queued` event and does not consume a capture sequence.
- **Capture order:** accepted frames get a zero-based sequence per job. Results carry
  `_capture_sequence`, including errors. `result_ready` reports each completion as it happens;
  `get_results()` exposes only the contiguous completed prefix in capture order. The table and
  exports consolidate that prefix so a late anonymous frame stays with the preceding captured
  practice. A slow earlier result can delay later rows even when the completion counter has advanced.
  An error occupies its sequence and releases following results; jobs progress independently.
  See [ADR 0013](adr/0013-risultati-nell-ordine-di-acquisizione.md).
- **Visits and acknowledgements:** the worker compares size, color mode and a BLAKE2b digest of
  normalized raw pixels before preprocessing. Any changed identity starts a new visit, even on the
  same page. Pending and completed visits suppress automatic duplicates and further router calls
  while the image stays unchanged. Only the matching job/sequence acknowledgement can complete or
  release the current pending capture. `ERROR` restarts the stability interval before retry;
  non-error results, including `ANCHOR_UNCERTAIN`, complete the visit because headerless pages can
  still contain useful fields. `captured_page_types` is guidance about successfully processed page
  names, not a job-wide acquisition gate. Pixel identity detects small identifier changes that pHash
  can miss, but animation can keep restarting stability and cause further routing calls.
  See [ADR 0014](adr/0014-acquisizione-per-visita-con-esito.md), which integrates ADR 0007.
- **Manual capture and stop:** `force_capture()` only enqueues a command. The capture loop performs
  the screenshot, preprocessing and submission, bypassing routing and stability. A request for the
  same page already pending in the current visit is coalesced; a request after success may capture
  again. The result signal also only enqueues an acknowledgement; the loop applies it. An ongoing
  router call can delay a manual shot. Stop checks prevent later submission once control returns;
  the worker closes mss in `run()`'s `finally`, on the capture thread. Already running extraction
  calls continue in the daemon pool. See [ADR 0015](adr/0015-scatto-manuale-nel-thread-di-cattura.md).
- **Frame framing is load-bearing** -- `_grab_raw()` grabs the whole monitor, then
  `frame_normalize.normalize_frame()` crops back to the application window: first the OS window rect
  (`find_window_rect()`, ctypes/user32, driven by `config.ini` `window_title_contains`), else the
  rectangle inferred from a uniform desktop background, else the frame unchanged. Both consumers
  downstream use *relative* coordinates calibrated on window-sized screenshots (the classifier's
  `DEFAULT_CROP_ROI` and the pipeline's `RETRY_AREAS` bands; `CONTENT_CROP` no longer applies on the live path, ADR 0010), so on a full-monitor frame those coordinates
  land on different content. See `docs/adr/0001-normalizzazione-inquadratura-frame.md`.
- **Page routing modes** (set in `edge-agent/config.ini` `router=`). The shipped `config.ini` is
  `llm`; the code default `DEFAULT_ROUTER_MODE` stays `ml` **on purpose**, as the safe behaviour when
  `config.ini` is missing: starting up with network calls under a key that may not be configured is
  worse than starting up with a local recognizer. See
  `docs/adr/0006-router-llm-come-predefinito.md`:
  - `ml` (**fallback since 2026-08-18**) -- `MLPageRouter` wraps `BPERPagePrototypeClassifier`
    (DINOv2 ViT-S/14, 384-dim, prototype
    matching via **centered** cosine similarity: the prototype centroid is subtracted from both
    prototypes and query, because pages of the same application share almost every pixel and the raw
    cosine put all 9 between 0.91 and 1.00 with margins of 0.003). ROI is
    `DEFAULT_CROP_ROI = (0.0, 0.20, 1.0, 0.98)` on the application area, squashed to 224x224 with no
    CenterCrop. Threshold `DEFAULT_SIMILARITY_THRESHOLD = 0.35` on the centered score. Degrades
    gracefully to disabled if torch is unavailable. First run downloads the DINOv2 weights (~84MB)
    via torch.hub (needs internet once). See
    `docs/adr/0002-riconoscimento-pagina-roi-e-coseno-centrato.md`.
  - `llm` (**shipped default**) -- recognizes the page from the *text* on screen, so it is invariant
    to window size, position and nesting depth. The prototype comparison can never be: a global
    embedding is by construction a function of the whole frame, hence of the framing, and the
    production framing varies per operator (local Chrome, or a remote session at any size and
    position, possibly both within one job). Measured 8/9 against the prototype classifier's 4/9 on
    frames nested inside a desktop, at the cost of one VLM call per routed frame and 4-5 s of
    latency. Via the OpenAI client, provider-aware:
    `AgentConfig.resolve_llm_settings()` (`edge-agent/config.py`) picks key/endpoint/model from
    `[llm] provider`; explicit INI values are authoritative, provider defaults fill only blank
    entries (config.ini ships `gemini` + `gemini-3.8-flash` through Google's OpenAI-compatible
    endpoint); reads page definitions from `assets/templates/bper/prompts.json`. Router failures
    are logged in the capture feed (deduped per distinct error).
  - `hybrid` -- tries LLM first, falls back to ML.
