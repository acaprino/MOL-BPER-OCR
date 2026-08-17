# Edge-Agent Async Capture & Page Registry — Design

Date: 2026-08-17
Status: approved in chat (option B, "ristrutturazione vera")

## Problem

A real capture session (log 13:38:03-13:38:42, packaged exe, router=ml) showed three defects:

1. **Blind window during extraction.** `BPERCaptureWorker._upload_page()` calls
   `LocalExtractionClient.ingest_frame()` synchronously in the capture QThread
   (`bper_capture_worker.py:710-721`, `local_extraction_client.py:81-90`). One screen's
   multi-pass extraction took ~30s (13:38:11 to 13:38:41) during which no frame was
   captured or routed. The operator scrolled through nearly all screens inside that
   window; the session captured 1 of 9.
2. **Fragile stability gate.** A single unrecognized frame resets the 2s wall-clock
   stability timer (`_reset_stability()` at `bper_capture_worker.py:492-494`). Screen 9
   was recognized at 13:38:04-05 and lost at 13:38:06 to one below-threshold frame.
3. **Broken page identity.** The "19 schermate da acquisire" total is the blind union
   of 9 template stems ("screen 1..9") and 10 semantic page names from `prompts.json`
   (`_valid_page_keys`, `bper_capture_worker.py:366`). The two vocabularies never map to
   each other: in `ml` mode the DINOv2 classifier can only return "screen N" labels, so
   the 10 semantic names are unreachable (max 9/19), the operator guidance asks for
   pages the router cannot match, `page_order` lookups miss (uuid filenames), and
   `_normalize_page_label()` papers over the gap with difflib fuzzy matching.

A fourth defect follows from #1: sitting on a page longer than ~3s re-captures it
(there is no `captured_page_types` membership check in `_capture_once()`), currently
masked by the synchronous extraction. Going async makes this a real double-cost bug,
so the fix must include the membership check.

`capture_tab.py:307-312` uses `QThread.terminate()` to kill the worker blocked in a VLM
call; with extraction out of the capture thread this hack becomes unnecessary.

## Decision

Producer/consumer restructuring (approved option B):

1. **Worker = eyes only.** `BPERCaptureWorker` captures, dedups, routes, tracks
   stability, and enqueues stable frames. It never blocks on extraction.
2. **`LocalExtractionClient` = parallel consumer.** `ingest_frame()` enqueues and
   returns immediately. A pool of `PARALLEL_WORKERS` daemon threads runs
   `ExtractionPipeline.extract_from_image()` on the shared pipeline, the exact pattern
   already in production in `BatchRunner` (`extraction/cli.py:194,235`; the pipeline
   holds no per-call mutable state, only 4 model refs). Results flow through the
   existing `result_ready` signal; a new `frame_queued` signal feeds the UI counter.
   Daemon threads (hand-rolled pool, not `ThreadPoolExecutor`) guarantee the process
   exits immediately on window close even mid-LLM-call, replacing the `terminate()`
   hack and the a288ee0 force-stop rationale.
3. **Single page registry.** `prompts.json` entries gain `"order"` and `"template"`
   fields (the catch-all gains `"catchall": true`). A new pure module
   `edge-agent/page_registry.py` loads it into `PageDef(name, order, template, slug)`
   and resolves any router label (LLM name or ML template stem, case-insensitive) to
   the canonical page. The canonical id is the `prompts.json` `name` verbatim (what the
   LLM router already returns and what the UI displays); `slug` is only for filenames.
   Totals become router-mode-aware: `ml` counts only pages with a template (9/9).
   Excel/CSV sequence loading, difflib fuzzy matching, and `_friendly_name()` regex
   transforms are deleted.
4. **Count-based stability with miss tolerance.** A pure `StabilityTracker` replaces
   the wall-clock-only gate: capture when the candidate has >= 2 concordant
   observations AND >= 2.0s of presence; 1 discordant/null observation is tolerated;
   two consecutive concordant observations of a different page switch the candidate
   immediately. This fixes the 13:38:06 loss while keeping anti-mid-scroll protection.

## Template-to-page mapping (verified by reading the 9 PNGs)

| order | template | name | evidence |
|---|---|---|---|
| 1 | screen 1 | Risultato ricerca | BStore list, h-scrollbar left, base columns |
| 2 | screen 2 | Risultato ricerca - Colonne estese | list scrolled: Data Ass./Del., Assegnata, Dest. |
| 3 | screen 3 | Risultato ricerca - Tooltip mostrata | scrolled right + tooltip "Origination BSTORE" |
| 4 | screen 4 | Elenco Soggetti | soggetti table, 3 rows with ruolo |
| 5 | screen 5 | Gestione Fidi e Garanzie | FIDI + GARANZIE tables, no tooltip |
| 6 | screen 6 | Gestione Fidi e Garanzie - Tooltip Descrizione Fidi | tooltip "340176 - MUTUO FOND PRIV CONSAP >=80%" on FIDI row |
| 7 | screen 7 | Gestione Fidi e Garanzie - Tooltip Descrizione Garanzie (riga 1) | tooltip "457-IMP. FID. FDO 1 CASA DR SOSTEGNI BIS" on GARANZIE row 1 |
| 8 | screen 8 | Gestione Fidi e Garanzie - Tooltip Descrizione Garanzie (riga 2) | tooltip "55-IPOTECA DI PRIMO GRADO" on GARANZIE row 2 |
| 9 | screen 9 | Note da Richiesta | Note da Richiesta tab, nota text block |

The mapping is 1:1 and follows the `prompts.json` array order.

## Component summary

- `edge-agent/page_registry.py` (new, stdlib-only): `PageDef`, `PageRegistry.load()`,
  `.empty()` (permissive fallback when prompts.json is broken), `.resolve(label)`,
  `.acquirable(router_mode)`, `.names(router_mode)`, `slugify()`.
- `edge-agent/stability.py` (new, stdlib-only): `StabilityConfig(min_matches=2,
  min_seconds=2.0, miss_tolerance=1)`, `StabilityTracker.observe(page, now) ->
  Optional[str]`, `.reset()`, `.candidate`.
- `edge-agent/extraction_pool.py` (new, stdlib-only): `DaemonThreadPool(max_workers)`
  with `submit()`, `pending()`, `stop()` (drains queue, running tasks finish alone,
  daemon threads never block interpreter exit).
- `edge-agent/local_extraction_client.py`: constructor gains optional `pipeline`
  injection (testability); `ingest_frame()` becomes enqueue-and-return; new
  `frame_queued(str, str)` signal; new `shutdown()`; `screen_id` uses the canonical
  page name as-is (no `.title()` mangling).
- `edge-agent/workers/capture/bper_capture_worker.py`: registry + tracker driven;
  captured-membership check; filenames `{order:02d}-{slug}.png`; deletions listed in
  the plan (Excel/CSV sequence, `_normalize_page_label`, `_friendly_name`,
  `_maybe_upload_dataset`, `PAGE_ORDER_FALLBACK`, `_SKIP_PAGE_TYPES`).
- `edge-agent/ui/capture_tab.py`: signals connected once in `__init__`; label
  "Acquisite: X | Estratte: Y"; stop without `terminate()`; queue keeps draining after
  stop; force-capture combo from the registry.
- `edge-agent/ui/main_window.py`: `closeEvent` also calls
  `extraction_client.shutdown()`.
- `edge-agent/ui/extraction_results_tab.py`: `_friendly_name` deleted, canonical names
  shown as-is.
- `edge-agent/config.py`: `required_pages_only` / `required_pages_csv` removed
  (dead with the CSV sequence logic; not present in the shipped config.ini).
- `tests/` (new, first in the repo): pytest suites for registry, tracker, pool, and an
  async client test with a fake pipeline. `requirements-dev.txt` adds pytest.

## Behavior changes visible to the operator

- The startup list shows 9 pages with the real BPER names; guidance only ever asks for
  recognizable pages.
- After a page is captured its extraction runs in background; scrolling continues
  immediately. The session label separates captured from extracted counts.
- Staying on an already-captured page logs "già acquisita" once instead of re-paying
  for a duplicate extraction.
- Stop is instant; queued extractions keep landing in the tabs afterwards. Closing the
  window kills everything immediately.

## Out of scope

- `DefaultCaptureWorker` (generic mode) untouched.
- LLM router prompt building untouched (it reads `name`/`hints` only; new JSON fields
  are additive).
- `docs/` narrative guide not updated (CLAUDE.md is).
- `dist/EdgeAgent` refresh happens via `build_exe.bat` after the source smoke test.

## Risks / accepted tradeoffs

- Up to `PARALLEL_WORKERS` (default 4) concurrent multi-pass extractions can hit
  Gemini rate limits; the value is already env-tunable and 4 is the CLI's production
  default on this account.
- Queued PIL images hold memory until processed (~10-15MB each preprocessed; 9 frames
  peak ~100-140MB transient). Acceptable for a desktop agent.
- On window close, in-flight LLM calls are abandoned (daemon threads die with the
  process). This is the intended semantic, matching the old force-stop goal without
  `terminate()`.
