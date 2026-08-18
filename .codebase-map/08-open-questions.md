# Open Questions

These are the things the code cannot answer on its own: decisions whose rationale is invisible from the source, domain facts only someone who has used the BPER application can confirm, and loose ends from the project's history (the removed remote backend, the 2026-07-21 git-history rewrite). Each question states what was observed and why the answer matters. Two of them will cost a new developer real time on day one if left unanswered: where the canonical `mnt/data/dati.csv` lives, and whether the leaked OpenAI key was actually rotated.

Questions are ordered within each section by impact on a new developer's effectiveness. Related background: [Architecture](04-architecture.md), [Workflows](05-workflows.md), [Configuration Guide](10-configuration-guide.md).

## Architecture

### Which page router is the intended default: LLM or ML?
**RESOLVED 2026-08-18: LLM.** The 17 August answer was ML; it was superseded the next day by [ADR 0006](../docs/adr/0006-router-llm-come-predefinito.md), once it emerged that the browser may sit locally or inside a remote session, at any size and position, and that both can occur within one job. Without a normalizable framing the prototype comparison cannot work: 8/9 against 4/9 on nested framings. The shipped `config.ini` uses `router = llm`; the code default stays `ml` deliberately, as the safe behaviour when `config.ini` is missing. Earlier history: shipped config and code default agreed on `router = ml`, recorded in [ADR 0005](../docs/adr/0005-router-ml-invece-di-router-llm.md). `torch`/`torchvision` are now needed only for the ML fallback, so they become candidates for optional extras, which ADR 0005 had ruled out.

Still open: **an offline story for the DINOv2 weights** on a locked-down network. First run currently needs internet once.

### Is the anchor confidence gate supposed to filter low-confidence anchors?
`extraction/pipeline.py:90-96` intends to null anchors below `ANCHOR_CONF_MIN` (0.95), and `CLAUDE.md` documents it as "zeroes out low-confidence anchors", but the gate is a no-op: the `ndg`/`denominazione` dicts feeding the hint prompt, the early exit, and the merge are copied *before* the gate runs (`:87-88`), and `safe_set_field(..., None)` cannot overwrite a non-null value (`extraction/normalization.py:78-79`). The only code that enforces the threshold on final values is `_is_confident_output()` inside the disabled dedup helper (`extraction/cli.py:77-89`). Should the gate be fixed to actually filter downstream use (which would change accuracy behavior), or is the prompt-level "return null when uncertain" instruction the intended mechanism, in which case the gate code and the `CLAUDE.md` claim should go?

### Should the Tkinter GUI pass an anchor model alongside the main model?
`gui_app.py:238-247` forwards the dropdown-selected provider and `model_main` to `run_extraction_batch()` but never `model_anchor`, so the anchor pass falls back to the env-derived `LLM_MODEL_ANCHOR` (default `gpt-4o`). Selecting Gemini in the GUI while the env holds OpenAI defaults therefore raises the provider/model mismatch `ValueError` at `extraction/llm_factory.py:59-63` mid-run. Should the GUI derive the anchor model from the selected provider, or is the Gemini dropdown path known-broken?

### Is `preprocess_for_ocr()` meant to be equivalent to `normalize_image()`?
The pipeline has two entry points by design: `extract_from_screen()` normalizes internally, while `extract_from_image()` trusts the caller (`extraction/pipeline.py:104-187`; rationale comment at `edge-agent/local_extraction_client.py:84-85`). The edge-agent's `preprocess_for_ocr()` (`edge-agent/image_ops.py`) does adaptive upscale + unsharp + autocontrast, a different transform from `normalize_image()` in `extraction/imaging.py`. Are the two supposed to produce comparably scaled/sharpened inputs (so accuracy numbers are comparable between CLI and live capture), or is the divergence accepted? Any future caller passing a raw image to `extract_from_image()` silently skips normalization entirely: known sharp edge or latent bug?

### What is the fate of the remote/generic path and its config remnants?
`DefaultCaptureWorker` still POSTs raw frames to `{api.base_url}/jobs/{job_id}/frames` (`edge-agent/workers/capture/default_capture_worker.py`), but no such backend exists in this repo and `config.ini` points it at `http://localhost:8081`. The `[minio]` and `[dataset]` sections survive in `edge-agent/config.ini:12-16,25-29` while the dataset upload is a hard no-op ("disabilitata per consolidamento locale", `edge-agent/workers/capture/bper_capture_worker.py:713-715`), and the comment at line 710 records that remote upload was deliberately removed. Is the "Generico" capture mode and its config dead weight to delete, or is a remote ingestion backend planned to return? The answer decides whether `requests`, the `[api]`/`[minio]` sections, and `DefaultCaptureWorker` should be removed.

### Was the Gemini three-way branching validated against every listed model?
`extraction/vlm_client.py` picks among three structured-output strategies by substring: `_GEMINI_JSON_SCHEMA_MODELS = ("gemini-1.5",)` (line 18) routes 1.5 models to json_mode with `response_schema`, and everything else Gemini goes free-form JSON + manual Pydantic validation because complex schemas reportedly trigger `INVALID_ARGUMENT` on 2.0+/3.x. Was this verified for all of `PROVIDER_MODELS["gemini"]` (`extraction/config.py:24-32`), including `gemini-3-flash-preview` and `gemini-3.1-flash-lite-preview`, or only for one or two? A future model name that doesn't match the substring takes the free-form branch by default; is that the intended safe fallback?

## Business Logic

### Where does the canonical `mnt/data/dati.csv` live, and who owns it?
The CLI hard-requires it (`FileNotFoundError` at `extraction/cli.py:315-316`), the README documents its format (`README.md:221-241`), and the whole evaluation harness is built around it, yet the file exists neither in the working tree nor anywhere in git (`.gitignore:9` excludes `/mnt`; only the 9 PNGs were force-added). Is there an authoritative copy (how many rows, which fields per screen) and can it be shared with every developer? Without a common GT file, `python main.py` cannot run on a fresh clone and no two developers' accuracy numbers are comparable.

### Are the coherence-check overrides universally valid BPER rules?
`_coherence_check()` (`extraction/pipeline.py:311-328`) silently rewrites model output: if `tooltip_evidenze_b` has a value, `evidenze` is forced to `"B"` (even replacing a purely numeric extracted value); if `tooltip_descrizione_bmb` has a value and `tipo` is null, `tipo` becomes `"BMB"`. These synthesized values are not flagged in `_field_sources`, so they look like clean extractions downstream. Do these implications hold for all BPER practices, or only for the 9 sample screens they were tuned on? A wrong rule here produces confidently wrong output that evaluation may score as OK.

### Is `TIPO_MAPPING` the complete synonym set for practice types?
`extraction/normalization.py:10-14` canonicalizes exactly three lowercase variants (`mutui spesa`, `mutuo spesa`, `bpi mutui`) to `"BPI Mutui"`. Is this the full set of `tipo` spellings the BPER UI can display, or just what appeared in the sample data? Any unlisted variant passes through unmapped and gets scored WRONG against the GT, invisible until someone inspects the debug CSV.

### Are the canonical page bindings for the scheda-privati fields intentional?
All 13 scheda-privati fields (`dal`, `professione_principale`, `score_cgs`, `rating_ufficiale`, …) are bound to page_key `note_da_richiesta` in `extraction/field_definitions.py:114-165`, even though they come from the "scheda privati" screens (screens 4-5 per `CLAUDE.md`), not the notes page. This binding drives the canonical CSV export, the Tkinter results grouping, and the edge-agent's *Dati Estratti* tab. Is packing them under `note_da_richiesta` a deliberate client-facing sheet layout (4-page contract), or a mis-assignment to fix before anyone builds on the canonical output?

### Does the soggetti flatten intentionally overwrite retry winners?
Step 7 of the pipeline unconditionally flattens the first four `soggetti` rows into `ndg_1..4` / `denominazione_1..4` / `ruolo_1..4` (`extraction/pipeline.py:159-166`), after the retry pass has already merged per-field winners for those same keys, which are listed as BODY retry fields in `extraction/config.py:73-76`. Table extraction therefore always beats per-field retry for these 12 keys, regardless of confidence. Intended precedence, or two code paths accidentally fighting over the same keys?

### Why are `creazione` and the five `tooltip_*` fields excluded from every retry area?
`AREA_TO_FIELDS` (`extraction/config.py:69-82`) assigns fields to HEADER/BODY/FOOTER retry crops, but `creazione` and all five `tooltip_*` keys appear in no area; if the main pass returns them null or low-confidence, they are never re-attempted. For tooltips this may be deliberate (they only render on hover, so a static screenshot either has them or not), but the tooltips also feed the coherence rules above, so a missed tooltip cascades into `evidenze`/`tipo`. Deliberate or oversight?

## Infrastructure

### Has the leaked OpenAI key been rotated at OpenAI?
An OpenAI API key was committed in `edge-agent/config.ini`. On 2026-07-21 it was scrubbed from the entire git history (`git filter-repo`, force-pushed to origin); the line now ships blank. History scrubbing does not un-leak a secret: anyone who ever cloned or fetched the repo may still have the key. Has it been revoked/rotated in the OpenAI dashboard, and was usage on that key audited? Until confirmed, treat this as an open security incident, not closed cleanup.

### Have all collaborators re-cloned since the history rewrite?
Because the rewrite changed every commit hash, any clone from before 2026-07-21 is incompatible with origin, and a push or merge from a stale clone would **reintroduce the leaked key** into history. Has every collaborator (and every CI runner, bot, or mirror, if any exist) re-cloned or hard-reset to the new origin? Is there a checklist confirming no stale forks remain?

### Where should edge-agent secrets live going forward?
Even after the scrub, the design that caused the leak is intact: `[llm] api_key` is a field in a **tracked** file, the router prefers it over env vars (`config.llm_api_key or OPENAI_API_KEY or LLM_API_KEY`, `edge-agent/workers/capture/bper_capture_worker.py:122`), and `AgentConfig.save()` writes `llm_api_key` back into `config.ini` (`edge-agent/config.py:326-332`), currently uncalled, but one UI wiring away from re-persisting a secret. Should the key move to `.env` only (flipping the precedence to env-first), should `save()` stop serializing it, and should `config.ini` grow a `config.ini.example` split like `.env`/`.env.example`? One decision here prevents a repeat incident.

### What is the intended runtime/deployment target?
There is no `pyproject.toml`, no lockfile, no Dockerfile, no CI (`CLAUDE.md` "Missing Infrastructure"); `requirements.txt` is loosely bounded and leaves LangChain and torch unpinned. The only packaging is a PyInstaller `.exe` of the Tkinter app (`README.md:78-100`), while the edge-agent (the "recommended" interface per the README) ships only as `run_edge_agent.bat` plus a source checkout. Is this strictly a developer-laptop POC, or is an operator-installable edge-agent build planned? That answer decides whether pinning, packaging, and an offline DINOv2 bootstrap are worth building.

### Are the page-sequence files distributed separately?
`_load_page_sequence()` looks for `Guida pagine ITA .xlsx` (note the space before `.xlsx`) and falls back to `Nomenclatura.csv` in `edge-agent/assets/templates/bper/` (`edge-agent/workers/capture/bper_capture_worker.py:257,327-328`); neither file exists in the repo, so page ordering always falls back to `prompts.json` order. Do these files exist outside the repo (client-provided?), and does the fallback order actually match the operator's navigation flow through the BPER app?

## Process

### How is a change verified without tests or a committed baseline?
There is no automated test suite; `CLAUDE.md` prescribes "run extraction, compare accuracy/cost against a baseline", but no baseline (`poc_outputs_improved.json` or a known-good accuracy figure) is committed anywhere, and `mnt/` is gitignored. Does the team keep a reference run somewhere (shared drive, wiki, a pinned message)? What accuracy delta counts as a regression, and is manual smoke-testing the only merge gate? A new developer currently cannot tell whether their change helped or hurt without first reconstructing a baseline themselves.

### What is the branching and release model on the rewritten history?
The repo has `master` and `develop` (current work happens on `develop`). Post-rewrite, all old hashes (including any referenced in notes, PR descriptions, or people's memory) are invalid. Is `develop` the integration branch with `master` as stable? Is review required before merge, and what constitutes a "release" for a POC with no versioning or CI? Also: were any external references to old commit hashes (tickets, docs) reconciled after the filter-repo pass?

### Is the client-facing "canonical" contract frozen, and who consumes it?
`extraction/canonical_mapping.py` builds sorted `canonical_fields` entries "for backend/UI/export integration", with a fixed 4-page taxonomy in `extraction/page_definitions.py`, but no external consumer exists in the repo, and the client is never named. Is there an agreed external contract (column names, page keys, ordering) that these display names must match exactly? This determines how freely developers may rename anything in `field_definitions.py`/`page_definitions.py`, which otherwise look safely refactorable.

## Technical Debt

### When does `_deduplicate_same_page_outputs()` get switched back on?
The function is fully implemented in `extraction/cli.py` but its call site is commented out with "TEMP TEST: keep all outputs until page_key mapping is validated" (`extraction/cli.py:268-273`). That validation ties back to the page-binding question above. What concretely validates the page_key mapping, and who flips this back on? Until then, batch runs can carry multiple outputs for the same canonical page, which affects the canonical export and possibly double-counts in downstream comparisons.

### Should an unpriced model fail loudly instead of costing $0.00?
`estimate_cost_usd()` returns `0.0` for any model absent from `PRICING_PER_1M` (`extraction/vlm_client.py:21-26`). `LLM_MODEL` is free-form via env, so a dated snapshot name (e.g. a `gpt-4o-2024-11-20` style ID) or a new preview model silently produces a zero-cost report, in a project whose entire point includes cost measurement. Should unknown models warn or raise, and who keeps the hardcoded preview prices (`gemini-3-flash-preview`, `gemini-3.1-flash-lite-preview`, `extraction/config.py:47-48`) in sync with actual billing?

### Can `streamlit` and the other Streamlit remnants be removed?
`streamlit` sits in `requirements.txt:5` with no importer anywhere; the `run_extraction_batch()` docstring still says "Shared by CLI (main) and Streamlit (app.py)" (`extraction/cli.py:296`), and `extraction/__init__.py:3` mentions "backward compatibility with app.py". The Streamlit app was deleted long ago; the actual third UI is Tkinter's `gui_app.py`. Any reason not to drop the dependency and fix the two comments in one commit?

### Should model-supplied confidence be validated or clamped?
Every gate in the system (the 0.95 anchor threshold, the 0.60 retry trigger, `pick_best()` tie-breaks) trusts the float the model returns; nothing enforces the [0, 1] range beyond an instruction in the Italian prompt (`prompts/extraction_anchor.json`; trusted at `extraction/pipeline.py:91,255`, `extraction/normalization.py:94-96`, `extraction/cli.py:87-88`). A model returning 1.5 or -0.2 would silently skew retry selection and winner picking. Clamp at the schema boundary, or accept the risk for a POC?

### Is the Tkinter GUI's cross-thread widget access acceptable?
The worker thread started at `gui_app.py:225-226` touches Tk widgets directly: `log_area.insert`, `messagebox`, `btn_run.config` (`gui_app.py:199-201`, `:258-285`); only `display_results` is marshaled to the UI thread via `self.after(0, ...)` (`gui_app.py:278`). Tkinter makes no thread-safety guarantee, so this works on current CPython but can hang or crash. Accepted POC risk, or worth routing all UI updates through `after()`?

### ~~Should `window_title_contains` be implemented or deleted?~~ RESOLVED 2026-08-17
**Implemented.** `frame_normalize.find_window_rect()` finds the first visible window whose title contains the substring, and `_grab_raw()` crops the frame to that rectangle. The knob no longer promises behavior that does not exist. It was implemented as a post-capture *crop* rather than window-scoped *capture* (`mss` still grabs the monitor), because a fallback was needed for when the title does not match. Details and limits in [ADR 0001](../docs/adr/0001-normalizzazione-inquadratura-frame.md).

The question turned out to matter more than it was posed: this was not a cosmetic knob, it was the missing piece that made page recognition score 1 out of 9 in the field.

### The field → page map in `field_definitions.py` is wrong: fix it or drop it?
`CANONICAL_FIELD_DEFINITIONS` assigns a `page_key` per field, but the scheda privati fields are mislabelled: `dal`, `professione_principale`, `rating_ufficiale`, `score_cgs`, `tipo_contratto`, `numero_mensilita`, `retribuzione_annua_netta`, `nr_altri_componenti_nucleo`, `di_cui_percepiscono_reddito`, `importo_totale_annuo_nucleo`, `note_scheda_privati`, `datore_di_lavoro_anagrafica` and `ultima_validazione_scheda` are tagged `note_da_richiesta` while they live on screens 4 and 5. Today the map only feeds `resolve_field_page_key()` for client-facing output, so the visible effect is a wrong page label in the result.

The real cost is indirect: that map is the natural way to scope retries by the recognized page, which would fix the waste described in [ADR 0004](../docs/adr/0004-budget-retry-derivato-dalle-aree.md) at the root. While it is unreliable, the retry logic cannot be built on it. Fix the map, or derive field → page from another source (`prompts.json` already lists expected fields per page)?

### Who reconciles `CLAUDE.md`/`README.md` with the code?
Confirmed drift: CLAUDE.md documents startup `if/raise` guards validating `FIELD_RETRY_MAP` and a `_FIELD_COMPARATORS` dict: neither exists in `extraction/` (grep); CLAUDE.md says the anchor pass "zeroes out low-confidence anchors" but the gate is ineffective (see the Architecture question above); CLAUDE.md's module table omits `edge-agent/ui/data_table_tab.py` (wired in `edge-agent/ui/main_window.py`); README leads with "18 campi" while `FIELD_KEYS` has 45 (`extraction/fields.py:12-54`); the comment at `edge-agent/workers/capture/bper_capture_worker.py:42` says "MobileNetV3" but the classifier is DINOv2 ViT-S/14 (`edge-agent/page_classifier.py:203`); `SCREENSHOT_DIR` is documented but read nowhere. Since CLAUDE.md steers AI-assisted work, its phantom guards actively mislead: is doc upkeep anyone's explicit responsibility?

### Should the error-path result dict match the success-path shape?
On extraction failure, `LocalExtractionClient.ingest_frame()` emits a stripped result (`screen_id`, empty `fields`, `_status: "ERROR"`, `_error`) without `_meta_agg`, `canonical_fields`, `_field_sources`, or the table lists (`edge-agent/local_extraction_client.py:87-94`). UI consumers survive via defensive `.get(..., {})`, but any new consumer assuming the full shape will crash on the first failed frame. Normalize the error result, or declare defensive access the official contract?
