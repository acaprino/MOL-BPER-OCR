# X-Ray Change Set

Parent run: poc-data-extraction-20260911-154206. Worktree at f8f57e6124e0 (dirty).

## Code changes

22 modified, 6 added, 0 removed, of 232 in the snapshot.

**Modified:**
- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `docs/00-executive-summary.md`
- `docs/01-overview.md`
- `docs/02-features.md`
- `docs/03-tech-stack.md`
- `docs/04-architecture.md`
- `docs/05-workflows.md`
- `docs/06-data-model.md`
- `docs/07-getting-started.md`
- `docs/08-open-questions.md`
- `docs/09-project-anatomy.md`
- `docs/10-configuration-guide.md`
- `docs/11-glossary.md`
- `docs/INDEX.md`
- `docs/adr/README.md`
- `docs/how-it-works.md`
- `edge-agent/local_extraction_client.py`
- `edge-agent/ui/capture_tab.py`
- `edge-agent/workers/capture/bper_capture_worker.py`
- `tests/test_local_extraction_client.py`

**Added:**
- `docs/12-python-api.md`
- `docs/adr/0013-risultati-nell-ordine-di-acquisizione.md`
- `docs/adr/0014-acquisizione-per-visita-con-esito.md`
- `docs/adr/0015-scatto-manuale-nel-thread-di-cattura.md`
- `docs/mappa-codice.md`
- `tests/test_bper_capture_lifecycle.py`

| Symbol | File | Kind | Change |
|---|---|---|---|
| `LocalExtractionClient` | `edge-agent/local_extraction_client.py` | class | changed |
| `LocalExtractionClient.__init__` | `edge-agent/local_extraction_client.py` | method | changed |
| `LocalExtractionClient._process_frame` | `edge-agent/local_extraction_client.py` | method | changed |
| `LocalExtractionClient.get_results` | `edge-agent/local_extraction_client.py` | method | changed |
| `LocalExtractionClient.ingest_frame` | `edge-agent/local_extraction_client.py` | method | changed |
| `LocalExtractionClient.shutdown` | `edge-agent/local_extraction_client.py` | method | changed |
| `CaptureTab` | `edge-agent/ui/capture_tab.py` | class | changed |
| `CaptureTab._on_force_capture` | `edge-agent/ui/capture_tab.py` | method | changed |
| `CaptureTab._on_result_ready_count` | `edge-agent/ui/capture_tab.py` | method | changed |
| `CaptureTab._update_session_label` | `edge-agent/ui/capture_tab.py` | method | changed |
| `BPERCaptureWorker` | `edge-agent/workers/capture/bper_capture_worker.py` | class | changed |
| `BPERCaptureWorker.__init__` | `edge-agent/workers/capture/bper_capture_worker.py` | method | changed |
| `BPERCaptureWorker._acquire` | `edge-agent/workers/capture/bper_capture_worker.py` | method | changed |
| `BPERCaptureWorker._capture_once` | `edge-agent/workers/capture/bper_capture_worker.py` | method | changed |
| `BPERCaptureWorker._upload_page` | `edge-agent/workers/capture/bper_capture_worker.py` | method | changed |
| `BPERCaptureWorker.force_capture` | `edge-agent/workers/capture/bper_capture_worker.py` | method | changed |
| `BPERCaptureWorker.run` | `edge-agent/workers/capture/bper_capture_worker.py` | method | changed |
| `BPERCaptureWorker._complete_capture` | `edge-agent/workers/capture/bper_capture_worker.py` | method | added |
| `BPERCaptureWorker._drain_commands` | `edge-agent/workers/capture/bper_capture_worker.py` | method | added |
| `BPERCaptureWorker._execute_manual_capture` | `edge-agent/workers/capture/bper_capture_worker.py` | method | added |
| `BPERCaptureWorker._observe_frame` | `edge-agent/workers/capture/bper_capture_worker.py` | method | added |
| `BPERCaptureWorker._queue_extraction_result` | `edge-agent/workers/capture/bper_capture_worker.py` | method | added |
| `BPERCaptureWorker._restart_stability` | `edge-agent/workers/capture/bper_capture_worker.py` | method | added |
| `Camera` | `tests/test_bper_capture_lifecycle.py` | class | added |
| `Camera.__init__` | `tests/test_bper_capture_lifecycle.py` | method | added |
| `Camera.close` | `tests/test_bper_capture_lifecycle.py` | method | added |
| `Camera.grab` | `tests/test_bper_capture_lifecycle.py` | method | added |
| `CaptureClient` | `tests/test_bper_capture_lifecycle.py` | class | added |
| `CaptureClient.__init__` | `tests/test_bper_capture_lifecycle.py` | method | added |
| `CaptureClient.complete` | `tests/test_bper_capture_lifecycle.py` | method | added |
| `CaptureClient.ingest_frame` | `tests/test_bper_capture_lifecycle.py` | method | added |
| `Router` | `tests/test_bper_capture_lifecycle.py` | class | added |
| `Router.__init__` | `tests/test_bper_capture_lifecycle.py` | method | added |
| `Router.route` | `tests/test_bper_capture_lifecycle.py` | method | added |
| `acquire` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `app` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `capture` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `test_failed_extraction_rearms_the_stationary_page` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `test_first_manual_capture_retries_the_operator_page_after_error` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `test_manual_request_after_success_can_capture_again` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `test_manual_request_during_pending_extraction_is_coalesced` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `test_manual_request_waits_for_the_capture_thread` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `test_manual_retry_does_not_reuse_automatic_route_metadata` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `test_old_failure_does_not_release_the_current_pending_visit` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `test_queued_page_is_not_reported_as_completed` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `test_rejected_enqueue_does_not_consume_the_page` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `test_returning_to_a_page_is_a_new_visit` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `test_small_identity_change_on_the_same_page_can_be_acquired` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `test_stationary_page_is_not_rerouted_after_completion` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `test_stop_discards_queued_manual_requests` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `test_uncertain_anchor_does_not_trigger_endless_recapture` | `tests/test_bper_capture_lifecycle.py` | function | added |
| `ControlledPipeline` | `tests/test_local_extraction_client.py` | class | added |
| `ControlledPipeline.__init__` | `tests/test_local_extraction_client.py` | method | added |
| `ControlledPipeline.extract_from_image` | `tests/test_local_extraction_client.py` | method | added |
| `ControlledPipeline.release_all` | `tests/test_local_extraction_client.py` | method | added |
| `_field` | `tests/test_local_extraction_client.py` | function | added |
| `test_error_completion_releases_the_following_ordered_results` | `tests/test_local_extraction_client.py` | function | added |
| `test_log_write_error_does_not_block_ordered_results` | `tests/test_local_extraction_client.py` | function | added |
| `test_out_of_order_completions_preserve_practice_assignment` | `tests/test_local_extraction_client.py` | function | added |
| `test_rejected_ingest_does_not_emit_frame_queued` | `tests/test_local_extraction_client.py` | function | added |
| `test_slow_job_does_not_delay_another_jobs_results` | `tests/test_local_extraction_client.py` | function | added |
| `BPERCaptureWorker._capture_screenshot` | `edge-agent/workers/capture/bper_capture_worker.py` | method | removed |
| `BPERCaptureWorker.stop` | `edge-agent/workers/capture/bper_capture_worker.py` | method | removed |

## Blast radius

| Importer | Imports |
|---|---|
| `edge-agent/ui/__init__.py` | `edge-agent/ui/capture_tab.py` |
| `edge-agent/ui/main_window.py` | `edge-agent/local_extraction_client.py`, `edge-agent/ui/capture_tab.py` |
| `edge-agent/workers/capture/__init__.py` | `edge-agent/workers/capture/bper_capture_worker.py` |
| `tests/test_bper_capture_framing.py` | `edge-agent/workers/capture/bper_capture_worker.py` |
| `tests/test_bper_capture_lifecycle.py` | `edge-agent/workers/capture/bper_capture_worker.py` |

## Affected claims

| Phase file | Line | Section | Cites | Reason |
|---|---|---|---|---|
| 01-structure.md | 27 | ## File Inventory | `edge-agent/local_extraction_client.py:1` | line-outside-known-symbol |
| 01-structure.md | 32 | ## File Inventory | `edge-agent/ui/__init__.py:1` | importer |
| 01-structure.md | 33 | ## File Inventory | `edge-agent/ui/capture_tab.py:1` | line-outside-known-symbol |
| 01-structure.md | 36 | ## File Inventory | `edge-agent/ui/main_window.py:1` | importer |
| 01-structure.md | 39 | ## File Inventory | `edge-agent/workers/capture/__init__.py:1` | importer |
| 01-structure.md | 41 | ## File Inventory | `edge-agent/workers/capture/bper_capture_worker.py:1` | line-outside-known-symbol |
| 01-structure.md | 63 | ## File Inventory | `tests/test_bper_capture_framing.py:1` | importer |
| 01-structure.md | 68 | ## File Inventory | `tests/test_local_extraction_client.py:1` | line-outside-known-symbol |
| 01-structure.md | 149 | ## Dependency Graph (cross-partition view) | `edge-agent/edge_agent.py:63`, `edge-agent/edge_agent.py:74`, `edge-agent/ui/capture_tab.py:224`, `edge-agent/ui/main_window.py:36` | importer |
| 01-structure.md | 150 | ## Dependency Graph (cross-partition view) | `edge-agent/workers/capture/bper_capture_worker.py:299`, `edge-agent/workers/capture/bper_capture_worker.py:318`, `edge-agent/workers/capture/bper_capture_worker.py:392`, `edge-agent/workers/capture/bper_capture_worker.py:625` | line-outside-known-symbol |
| 01-structure.md | 151 | ## Dependency Graph (cross-partition view) | `edge-agent/local_extraction_client.py:114`, `edge-agent/local_extraction_client.py:159`, `extraction/cli.py:195` | line-outside-known-symbol |
| 01-structure.md | 158 | ## Dependency Graph (cross-partition view) | `edge-agent/local_extraction_client.py:20`, `main.py:14`, `tests/conftest.py:9` | line-outside-known-symbol |
| 01-structure.md | 169 | ## Global Entry Points | `edge-agent/local_extraction_client.py:76`, `edge-agent/workers/capture/base_capture_worker.py:9` | line-outside-known-symbol |
| 01-structure.md | 189 | ### Partition: root | `edge-agent/local_extraction_client.py:114`, `extraction/cli.py:232`, `extraction/llm_factory.py:27`, `extraction/pipeline.py:337` | line-outside-known-symbol |
| 01-structure.md | 190 | ### Partition: root | `edge-agent/local_extraction_client.py:159`, `edge-agent/workers/capture/bper_capture_worker.py:392`, `extraction/pipeline.py:223` | line-outside-known-symbol |
| 01-structure.md | 192 | ### Partition: root | `edge-agent/config.py:26`, `edge-agent/workers/capture/bper_capture_worker.py:173`, `edge-agent/workers/capture/bper_capture_worker.py:541`, `tests/test_bper_capture_framing.py:212` | importer |
| 01-structure.md | 193 | ### Partition: root | `edge-agent/assets/templates/bper/prompts.json:104`, `edge-agent/workers/capture/bper_capture_worker.py:308`, `edge-agent/workers/capture/bper_capture_worker.py:643`, `processes/bper-p1.json:259`, `processes/bper-p1.json:368` | line-outside-known-symbol |
| 01-structure.md | 194 | ### Partition: root | `edge-agent/ui/main_window.py:36`, `edge-agent/workers/capture/bper_capture_worker.py:625`, `edge-agent/workers/capture/default_capture_worker.py:34` | line-outside-known-symbol |
| 01-structure.md | 195 | ### Partition: root | `edge-agent/local_extraction_client.py:175`, `edge-agent/practice_consolidation.py:125` | line-outside-known-symbol |
| 01-structure.md | 205 | ### Partition: root | `edge-agent/local_extraction_client.py:125`, `edge-agent/workers/capture/base_capture_worker.py:81` | line-outside-known-symbol |
| 01-structure.md | 219 | ### Partition: root | `edge-agent/ui/main_window.py:85`, `edge-agent/ui/overlay.py:30`, `extraction/normalization.py:104` | importer |
| 02-interfaces.md | 9 | ### Partition: root | `edge-agent/__init__.py:1`, `edge-agent/ui/__init__.py:1`, `edge-agent/workers/__init__.py:3`, `edge-agent/workers/capture/__init__.py:3`, `extraction/__init__.py:11`, `extraction/__init__.py:47`, `extraction/config.py:16`, `extraction/prompts.py:6`, `extraction/schemas.py:68` | importer |
| 02-interfaces.md | 264 | ##### `edge-agent/local_extraction_client.py` | `edge-agent/local_extraction_client.py:90` | line-outside-known-symbol |
| 02-interfaces.md | 266 | ##### `edge-agent/local_extraction_client.py` | `edge-agent/local_extraction_client.py:125` | line-outside-known-symbol |
| 02-interfaces.md | 269 | ##### `edge-agent/local_extraction_client.py` | `edge-agent/local_extraction_client.py:188` | line-outside-known-symbol |
| 02-interfaces.md | 270 | ##### `edge-agent/local_extraction_client.py` | `edge-agent/local_extraction_client.py:195` | line-outside-known-symbol |
| 02-interfaces.md | 287 | ##### `edge-agent/workers/capture/bper_capture_worker.py` | `edge-agent/workers/capture/bper_capture_worker.py:44` | line-outside-known-symbol |
| 02-interfaces.md | 288 | ##### `edge-agent/workers/capture/bper_capture_worker.py` | `edge-agent/workers/capture/bper_capture_worker.py:201` | line-outside-known-symbol |
| 02-interfaces.md | 289 | ##### `edge-agent/workers/capture/bper_capture_worker.py` | `edge-agent/workers/capture/bper_capture_worker.py:210` | line-outside-known-symbol |
| 02-interfaces.md | 290 | ##### `edge-agent/workers/capture/bper_capture_worker.py` | `edge-agent/workers/capture/bper_capture_worker.py:643` | line-outside-known-symbol |
| 02-interfaces.md | 319 | ##### `edge-agent/ui/main_window.py` | `edge-agent/ui/main_window.py:31` | importer |
| 02-interfaces.md | 320 | ##### `edge-agent/ui/main_window.py` | `edge-agent/ui/main_window.py:85` | importer |
| 02-interfaces.md | 374 | ## Cross-Partition Exports | `edge-agent/excel_export.py:227`, `edge-agent/local_extraction_client.py:159`, `gui_app.py:238` | line-outside-known-symbol |
| 02-interfaces.md | 393 | #### Campi, righe e output di estrazione | `edge-agent/local_extraction_client.py:160`, `extraction/pipeline.py:216` | line-outside-known-symbol |
| 02-interfaces.md | 433 | #### Prompt, configurazione e cataloghi pagina | `edge-agent/assets/templates/bper/prompts.json:104`, `edge-agent/workers/capture/bper_capture_worker.py:308`, `processes/bper-p1.json:259`, `processes/bper-p1.json:282`, `processes/bper-p1.json:368`, `tools/label_frames.py:174` | line-outside-known-symbol |
| 02-interfaces.md | 451 | #### Cattura, concorrenza e segnali Qt | `edge-agent/workers/capture/bper_capture_worker.py:201`, `edge-agent/workers/capture/bper_capture_worker.py:255`, `edge-agent/workers/capture/bper_capture_worker.py:339`, `edge-agent/workers/capture/bper_capture_worker.py:392`, `edge-agent/workers/capture/bper_capture_worker.py:643` | line-outside-known-symbol |
| 02-interfaces.md | 454 | #### Cattura, concorrenza e segnali Qt | `edge-agent/local_extraction_client.py:121`, `edge-agent/local_extraction_client.py:125`, `edge-agent/local_extraction_client.py:168`, `edge-agent/local_extraction_client.py:87` | line-outside-known-symbol |
| 02-interfaces.md | 455 | #### Cattura, concorrenza e segnali Qt | `edge-agent/local_extraction_client.py:180`, `edge-agent/local_extraction_client.py:184`, `edge-agent/local_extraction_client.py:188`, `edge-agent/local_extraction_client.py:195` | line-outside-known-symbol |
| 02-interfaces.md | 456 | #### Cattura, concorrenza e segnali Qt | `edge-agent/ui/capture_tab.py:299`, `edge-agent/ui/capture_tab.py:417`, `edge-agent/ui/data_table_tab.py:194`, `edge-agent/ui/main_window.py:85` | importer |
| 02-interfaces.md | 460 | #### Pratica consolidata e workbook | `edge-agent/local_extraction_client.py:175`, `edge-agent/practice_consolidation.py:105`, `edge-agent/practice_consolidation.py:30`, `edge-agent/practice_consolidation.py:46`, `edge-agent/practice_consolidation.py:85` | line-outside-known-symbol |
| 02-interfaces.md | 482 | ## External Dependencies | `edge-agent/edge_agent.py:31`, `edge-agent/local_extraction_client.py:24`, `main.py:4`, `requirements.txt:5` | line-outside-known-symbol |
| 02-interfaces.md | 495 | ### Partition: root | `tests/conftest.py:19`, `tests/test_bper_capture_framing.py:212`, `tests/test_content_crop.py:79`, `tests/test_excel_export.py:14`, `tests/test_page_classifier.py:50` | importer |
| 03-flows.md | 40 | #### Sessione live, routing e stabilità | `edge-agent/ui/capture_tab.py:192`, `edge-agent/workers/capture/base_capture_worker.py:41`, `edge-agent/workers/capture/bper_capture_worker.py:201`, `edge-agent/workers/capture/bper_capture_worker.py:552` | line-outside-known-symbol |
| 03-flows.md | 42 | #### Sessione live, routing e stabilità | `edge-agent/page_registry.py:69`, `edge-agent/workers/capture/bper_capture_worker.py:246`, `edge-agent/workers/capture/bper_capture_worker.py:255` | line-outside-known-symbol |
| 03-flows.md | 43 | #### Sessione live, routing e stabilità | `edge-agent/stability.py:10`, `edge-agent/stability.py:46`, `edge-agent/stability.py:76`, `edge-agent/workers/capture/bper_capture_worker.py:282` | line-outside-known-symbol |
| 03-flows.md | 49 | #### Acquisizione, coda, risultati e chiusura | `edge-agent/local_extraction_client.py:125`, `edge-agent/workers/capture/bper_capture_worker.py:331`, `edge-agent/workers/capture/bper_capture_worker.py:609` | line-outside-known-symbol |
| 03-flows.md | 50 | #### Acquisizione, coda, risultati e chiusura | `edge-agent/extraction_pool.py:23`, `edge-agent/local_extraction_client.py:144`, `extraction/pipeline.py:337` | line-outside-known-symbol |
| 03-flows.md | 51 | #### Acquisizione, coda, risultati e chiusura | `edge-agent/ui/capture_tab.py:405`, `edge-agent/workers/capture/bper_capture_worker.py:643` | line-outside-known-symbol |
| 03-flows.md | 52 | #### Acquisizione, coda, risultati e chiusura | `edge-agent/extraction_pool.py:44`, `edge-agent/llm_router.py:228`, `edge-agent/local_extraction_client.py:180`, `edge-agent/ui/capture_tab.py:292`, `edge-agent/ui/main_window.py:85`, `edge-agent/workers/capture/base_capture_worker.py:73`, `edge-agent/workers/capture/bper_capture_worker.py:210`, `extraction/pipeline.py:337` | line-outside-known-symbol |
| 03-flows.md | 80 | ### Partition: root | `edge-agent/workers/capture/bper_capture_worker.py:270`, `extraction/pipeline.py:223`, `extraction/pipeline.py:318` | line-outside-known-symbol |
| 03-flows.md | 81 | ### Partition: root | `edge-agent/local_extraction_client.py:121`, `edge-agent/local_extraction_client.py:154`, `extraction/imaging.py:29`, `extraction/vlm_client.py:123` | line-outside-known-symbol |
| 03-flows.md | 82 | ### Partition: root | `edge-agent/local_extraction_client.py:168`, `extraction/pipeline.py:180`, `extraction/pipeline.py:365` | line-outside-known-symbol |
| 03-flows.md | 97 | ### Partition: root | `edge-agent/local_extraction_client.py:156`, `extraction/cli.py:249`, `extraction/pipeline.py:148` | line-outside-known-symbol |
| 03-flows.md | 101 | ### Partition: root | `edge-agent/extraction_pool.py:55`, `edge-agent/local_extraction_client.py:172`, `edge-agent/workers/capture/bper_capture_worker.py:635` | line-outside-known-symbol |
| 03-flows.md | 110 | ### Partition: root | `edge-agent/local_extraction_client.py:116`, `edge-agent/local_extraction_client.py:195`, `edge-agent/ui/data_table_tab.py:179`, `edge-agent/workers/capture/bper_capture_worker.py:44` | line-outside-known-symbol |
| 03-flows.md | 111 | ### Partition: root | `edge-agent/edge_agent.py:15`, `edge-agent/local_extraction_client.py:41`, `edge-agent/ui/capture_tab.py:388`, `edge-agent/ui/data_table_tab.py:210` | line-outside-known-symbol |
| 03-flows.md | 156 | ##### Selezione della pagina live | `edge-agent/workers/capture/bper_capture_worker.py:255` | line-outside-known-symbol |
| 03-flows.md | 182 | ##### Pool e terminazione | `edge-agent/local_extraction_client.py:125` | line-outside-known-symbol |
| 03-flows.md | 184 | ##### Pool e terminazione | `edge-agent/ui/main_window.py:85` | importer |
| 03-flows.md | 251 | ##### Ripresa manuale | `edge-agent/ui/capture_tab.py:405` | line-outside-known-symbol |
| 03-flows.md | 252 | ##### Ripresa manuale | `edge-agent/workers/capture/bper_capture_worker.py:643` | line-outside-known-symbol |
| 03-flows.md | 292 | ##### Operatore → Excel | `edge-agent/local_extraction_client.py:144` | line-outside-known-symbol |
| 04-semantics.md | 35 | #### Acquisizione desktop e presentazione | `edge-agent/workers/capture/base_capture_worker.py:41`, `edge-agent/workers/capture/bper_capture_worker.py:255`, `edge-agent/workers/capture/default_capture_worker.py:34` | line-outside-known-symbol |
| 04-semantics.md | 36 | #### Acquisizione desktop e presentazione | `edge-agent/extraction_pool.py:23`, `edge-agent/local_extraction_client.py:125`, `edge-agent/local_extraction_client.py:144`, `extraction/vlm_client.py:197` | line-outside-known-symbol |
| 04-semantics.md | 38 | #### Acquisizione desktop e presentazione | `edge-agent/ui/capture_tab.py:192`, `edge-agent/ui/data_table_tab.py:161`, `edge-agent/ui/data_table_tab.py:194`, `edge-agent/ui/main_window.py:31`, `edge-agent/ui/main_window.py:85` | importer |
| 04-semantics.md | 40 | #### Acquisizione desktop e presentazione | `edge-agent/__init__.py:1`, `edge-agent/ui/__init__.py:1`, `edge-agent/workers/__init__.py:3`, `edge-agent/workers/capture/__init__.py:3` | importer |
| 04-semantics.md | 51 | #### Strumenti e test | `tests/test_base_capture_worker.py:30`, `tests/test_bper_capture_framing.py:64`, `tests/test_extraction_pool.py:9`, `tests/test_local_extraction_client.py:41`, `tests/test_stability.py:8` | importer |
| 04-semantics.md | 59 | ### Partition: root | `docs/how-it-works.md:7`, `extraction/pipeline.py:244`, `extraction/pipeline.py:284`, `extraction/pipeline.py:78`, `prompts/extraction_anchor.json:18` | line-outside-known-symbol |
| 04-semantics.md | 63 | ### Partition: root | `edge-agent/extraction_pool.py:14`, `edge-agent/extraction_pool.py:44`, `edge-agent/local_extraction_client.py:125`, `extraction/pipeline.py:337` | line-outside-known-symbol |
| 04-semantics.md | 66 | ### Partition: root | `edge-agent/llm_router.py:228`, `edge-agent/local_extraction_client.py:159`, `edge-agent/workers/capture/default_capture_worker.py:65`, `extraction/vlm_client.py:197` | line-outside-known-symbol |
| 04-semantics.md | 87 | #### ADR 0001 — Normalizzare prima dei consumer | `docs/adr/0001-normalizzazione-inquadratura-frame.md:95`, `edge-agent/frame_normalize.py:113`, `edge-agent/frame_normalize.py:72`, `edge-agent/workers/capture/bper_capture_worker.py:274` | line-outside-known-symbol |
| 04-semantics.md | 112 | #### ADR 0006 — LLM come scelta distribuita, ML come default del codice | `README.md:49`, `docs/adr/0006-router-llm-come-predefinito.md:44`, `edge-agent/config.py:33`, `edge-agent/workers/capture/bper_capture_worker.py:108` | line-outside-known-symbol |
| 04-semantics.md | 119 | #### ADR 0007 — Confermare sul duplicato | `docs/adr/0007-conferma-stabilita-su-frame-invariato.md:35`, `edge-agent/stability.py:76`, `edge-agent/workers/capture/bper_capture_worker.py:275` | line-outside-known-symbol |
| 04-semantics.md | 156 | ### Partition: root | `edge-agent/local_extraction_client.py:175`, `edge-agent/practice_consolidation.py:121` | line-outside-known-symbol |
| 04-semantics.md | 157 | ### Partition: root | `edge-agent/workers/capture/bper_capture_worker.py:308`, `edge-agent/workers/capture/bper_capture_worker.py:643` | line-outside-known-symbol |
| 04-semantics.md | 161 | ### Partition: root | `edge-agent/frame_normalize.py:113`, `edge-agent/local_extraction_client.py:154`, `extraction/vlm_client.py:123` | line-outside-known-symbol |
| 04-semantics.md | 162 | ### Partition: root | `edge-agent/local_extraction_client.py:114`, `extraction/cli.py:236`, `extraction/pipeline.py:337`, `extraction/pipeline.py:58` | line-outside-known-symbol |
| 04-semantics.md | 184 | ### Partition: root | `edge-agent/stability.py:71`, `edge-agent/workers/capture/bper_capture_worker.py:282`, `edge-agent/workers/capture/bper_capture_worker.py:302` | line-outside-known-symbol |
| 04-semantics.md | 185 | ### Partition: root | `edge-agent/extraction_pool.py:33`, `edge-agent/local_extraction_client.py:139`, `edge-agent/workers/capture/bper_capture_worker.py:339` | line-outside-known-symbol |
| 04-semantics.md | 187 | ### Partition: root | `edge-agent/local_extraction_client.py:159`, `edge-agent/page_classifier.py:607`, `edge-agent/workers/capture/bper_capture_worker.py:392`, `tools/build_prototypes.py:67` | line-outside-known-symbol |
| 04-semantics.md | 190 | ### Partition: root | `edge-agent/edge_agent.py:86`, `edge-agent/local_extraction_client.py:41`, `edge-agent/ui/main_window.py:49`, `edge-agent/workers/capture/bper_capture_worker.py:555` | importer |
| 04-semantics.md | 196 | ### Partition: root | `edge-agent/local_extraction_client.py:160`, `edge-agent/workers/capture/bper_capture_worker.py:191`, `extraction/vlm_client.py:253`, `prompt_store.py:262` | line-outside-known-symbol |
| 04-semantics.md | 200 | ### Partition: root | `edge-agent/extraction_pool.py:23`, `edge-agent/ui/capture_tab.py:417`, `extraction/cli.py:236`, `extraction/pipeline.py:337` | line-outside-known-symbol |
| 04-semantics.md | 201 | ### Partition: root | `README.md:19`, `extraction/cli.py:285`, `extraction/pipeline.py:400`, `extraction/pipeline.py:410`, `extraction/schemas.py:92` | line-outside-known-symbol |
| 05-risks.md | 5 | # Phase 5: Pattern & Risk Detection | `README.md:7`, `tests/conftest.py:19`, `tests/test_local_extraction_client.py:15` | line-outside-known-symbol |
| 05-risks.md | 11 | ## Anti-Patterns Found (by severity) | `docs/how-it-works.md:37`, `extraction/config.py:101`, `extraction/field_definitions.py:5`, `extraction/fields.py:12`, `extraction/pipeline.py:295`, `prompts/extraction_main.json:10` | line-outside-known-symbol |
| 05-risks.md | 14 | ## Anti-Patterns Found (by severity) | `edge-agent/page_classifier.py:202`, `edge-agent/workers/capture/bper_capture_worker.py:28` | line-outside-known-symbol |
| 05-risks.md | 20 | ## Red Flags (by severity) | `README.md:21`, `edge-agent/excel_export.py:227`, `edge-agent/local_extraction_client.py:159`, `edge-agent/practice_consolidation.py:118`, `edge-agent/ui/data_table_tab.py:195` | line-outside-known-symbol |
| 05-risks.md | 21 | ## Red Flags (by severity) | `edge-agent/local_extraction_client.py:160`, `edge-agent/ui/capture_tab.py:198`, `edge-agent/workers/capture/bper_capture_worker.py:308` | line-outside-known-symbol |
| 05-risks.md | 22 | ## Red Flags (by severity) | `edge-agent/ui/capture_tab.py:417`, `edge-agent/workers/capture/bper_capture_worker.py:666` | line-outside-known-symbol |
| 05-risks.md | 23 | ## Red Flags (by severity) | `edge-agent/extraction_pool.py:23`, `edge-agent/llm_router.py:219`, `edge-agent/ui/capture_tab.py:187`, `edge-agent/ui/capture_tab.py:299`, `edge-agent/ui/main_window.py:85`, `extraction/pipeline.py:337` | importer |
| 05-risks.md | 25 | ## Red Flags (by severity) | `edge-agent/bootstrap.py:245`, `edge-agent/bootstrap.py:40`, `edge-agent/edge_agent.py:63`, `edge-agent/edge_agent.py:73`, `edge-agent/ui/main_window.py:36`, `extraction/config.py:16`, `extraction/llm_factory.py:12`, `main.py:5` | importer |
| 05-risks.md | 26 | ## Red Flags (by severity) | `edge-agent/llm_router.py:260`, `edge-agent/local_extraction_client.py:160`, `extraction/pipeline.py:342`, `extraction/pipeline.py:392`, `extraction/vlm_client.py:242`, `extraction/vlm_client.py:26` | line-outside-known-symbol |
| 05-risks.md | 38 | ### Partition: root | `edge-agent/local_extraction_client.py:175`, `edge-agent/workers/capture/bper_capture_worker.py:108`, `tests/test_bper_capture_framing.py:212`, `tests/test_local_extraction_client.py:39`, `tests/test_practice_consolidation.py:44` | line-outside-known-symbol |
| 05-risks.md | 41 | ### Partition: root | `AGENTS.md:199`, `extraction/normalization.py:126`, `extraction/pipeline.py:375` | line-outside-known-symbol |
| 05-risks.md | 54 | ### Partition: root | `edge-agent/extraction_pool.py:24`, `edge-agent/local_extraction_client.py:140` | line-outside-known-symbol |
| 06-documentation.md | 3 | # Phase 6: Documentation Health | `docs/INDEX.md` | file-modified |
| 06-documentation.md | 5 | # Phase 6: Documentation Health | `README.md` | file-modified |
| 06-documentation.md | 13 | ### Partition: root | `AGENTS.md:66`, `docs/01-overview.md:37`, `docs/02-features.md:17`, `docs/04-architecture.md:163`, `docs/05-workflows.md:41`, `docs/08-open-questions.md:15`, `docs/10-configuration-guide.md:184`, `docs/INDEX.md:44`, `docs/how-it-works.md:13`, `extraction/pipeline.py:105` | line-outside-known-symbol |
| 06-documentation.md | 14 | ### Partition: root | `docs/04-architecture.md:56`, `docs/05-workflows.md:191`, `docs/07-getting-started.md:223`, `docs/how-it-works.md:94`, `edge-agent/extraction_pool.py:23`, `edge-agent/llm_router.py:228`, `edge-agent/local_extraction_client.py:139` | line-outside-known-symbol |
| 06-documentation.md | 15 | ### Partition: root | `README.md:241`, `docs/02-features.md:105`, `docs/04-architecture.md:50`, `docs/06-data-model.md:222`, `docs/10-configuration-guide.md:277`, `edge-agent/excel_export.py:177`, `edge-agent/local_extraction_client.py:180`, `edge-agent/ui/capture_tab.py:361`, `edge-agent/ui/data_table_tab.py:270`, `edge-agent/ui/main_window.py:60` | line-outside-known-symbol |
| 06-documentation.md | 16 | ### Partition: root | `AGENTS.md:90`, `README.md:7`, `docs/00-executive-summary.md:30`, `docs/01-overview.md:96`, `docs/02-features.md:113`, `docs/07-getting-started.md:3`, `docs/08-open-questions.md:69`, `docs/10-configuration-guide.md:295`, `docs/INDEX.md:41`, `tests/test_excel_export.py:14`, `tests/test_frame_normalize.py:1`, `tests/test_local_extraction_client.py:39`, `tests/test_practice_consolidation.py:44` | line-outside-known-symbol |
| 06-documentation.md | 17 | ### Partition: root | `docs/06-data-model.md:230`, `docs/08-open-questions.md:89`, `extraction/schemas.py:21`, `extraction/vlm_client.py:94` | line-outside-known-symbol |
| 06-documentation.md | 18 | ### Partition: root | `README.md:148`, `README.md:159`, `docs/05-workflows.md:79`, `docs/10-configuration-guide.md:194`, `docs/how-it-works.md:23`, `extraction/config.py:59`, `extraction/config.py:65`, `extraction/pipeline.py:298`, `extraction/vlm_client.py:242` | line-outside-known-symbol |
| 06-documentation.md | 19 | ### Partition: root | `docs/04-architecture.md:152`, `docs/06-data-model.md:206`, `edge-agent/llm_router.py:273`, `extraction/pipeline.py:342`, `extraction/pipeline.py:392`, `extraction/vlm_client.py:200`, `extraction/vlm_client.py:26` | line-outside-known-symbol |
| 06-documentation.md | 20 | ### Partition: root | `README.md:24`, `docs/09-project-anatomy.md:198`, `docs/adr/0008-classificatore-locale-prototipi-reali-e-classi-di-scarto.md:99`, `edge-agent/workers/capture/bper_capture_worker.py:173` | line-outside-known-symbol |
| 06-documentation.md | 21 | ### Partition: root | `docs/02-features.md:37`, `extraction/normalization.py:148`, `extraction/pipeline.py:374` | line-outside-known-symbol |
| 06-documentation.md | 22 | ### Partition: root | `AGENTS.md:214`, `README.md:5`, `docs/01-overview.md:98`, `docs/08-open-questions.md:105`, `extraction/fields.py:12` | line-outside-known-symbol |
| 06-documentation.md | 24 | ### Partition: root | `docs/INDEX.md:38`, `docs/how-it-works.md:119`, `edge-agent/llm_router.py:228`, `extraction/cli.py:185` | line-outside-known-symbol |
| 06-documentation.md | 26 | ### Partition: root | `docs/10-configuration-guide.md:3`, `docs/adr/0008-classificatore-locale-prototipi-reali-e-classi-di-scarto.md:90` | line-outside-known-symbol |
| 06-documentation.md | 38 | ### Partition: root | `README.md:21`, `docs/how-it-works.md:83`, `docs/superpowers/specs/2026-08-17-edge-agent-excel-export-design.md:93`, `edge-agent/local_extraction_client.py:125`, `edge-agent/practice_consolidation.py:105` | line-outside-known-symbol |
| 06-documentation.md | 39 | ### Partition: root | `edge-agent/extraction_pool.py:44`, `edge-agent/local_extraction_client.py:188`, `edge-agent/ui/capture_tab.py:341`, `edge-agent/workers/capture/base_capture_worker.py:73`, `edge-agent/workers/capture/bper_capture_worker.py:643` | line-outside-known-symbol |
| 06-documentation.md | 40 | ### Partition: root | `docs/10-configuration-guide.md:222`, `edge-agent/bootstrap.py:489`, `edge-agent/config.py:292`, `extraction/llm_factory.py:18`, `main.py:5` | line-outside-known-symbol |
| 06-documentation.md | 43 | ### Partition: root | `README.md:81`, `tools/build_prototypes.py:147`, `tools/build_prototypes.py:85`, `tools/label_frames.py:156`, `tools/label_frames.py:278`, `tools/relocalize.py:38` | line-outside-known-symbol |
| 06-documentation.md | 45 | ### Partition: root | `AGENTS.md:235`, `README.md:81`, `docs/adr/0010-ritaglio-autorizzato-dal-percorso-e-dalla-famiglia.md:37`, `docs/how-it-works.md:37`, `edge-agent/page_registry.py:40`, `edge-agent/workers/capture/bper_capture_worker.py:225`, `extraction/imaging.py:52`, `extraction/pipeline.py:123`, `prompt_store.py:239` | line-outside-known-symbol |
| 06-documentation.md | 53 | ### Partition: root | `AGENTS.md:421`, `README.md:17`, `docs/04-architecture.md:7`, `docs/09-project-anatomy.md:81` | line-outside-known-symbol |
| 06-documentation.md | 54 | ### Partition: root | `docs/06-data-model.md:222`, `docs/10-configuration-guide.md:277`, `edge-agent/excel_export.py:217`, `edge-agent/local_extraction_client.py:76` | line-outside-known-symbol |
| 06-documentation.md | 55 | ### Partition: root | `AGENTS.md:212`, `AGENTS.md:320`, `extraction/cli.py:326` | line-outside-known-symbol |
| 06-documentation.md | 57 | ### Partition: root | `README.md:25`, `extraction/cli.py:319` | line-outside-known-symbol |

## Partitions

| Partition | Action | Affected files |
|---|---|---|
| root | re-analyzed | 32 |

## Esito della riconciliazione

Il confronto meccanico sopra descrive le affermazioni del precedente run da ricontrollare,
non i rilievi ancora aperti. La partizione `root` è stata riesaminata integralmente sul
codice a `f8f57e6124e0`, includendo la documentazione e le istruzioni locali non ancora
committate. Le correzioni applicative sono già presenti in quel commit.

- `XQ-R01`, `XQ-R02` e `XQ-R03` sono risolti; le prove sono riportate in [05-risks.md](05-risks.md).
- Restano 14 rilievi: 11 di gravità media e 3 bassa; nessuno critico o alto.
- Dei dieci temi documentali precedenti, sette sono risolti e tre parzialmente risolti.
  Le discrepanze residue sono descritte in [06-documentation.md](06-documentation.md).
- La nuova esecuzione completa dei test ha prodotto 173 passed, 3 warnings in 38.20s,
  con codice di uscita 0. I dettagli sono in [validation/README.md](validation/README.md).

Il run storico `poc-data-extraction-20260911-154206` resta invariato. Questo aggiornamento
modifica solo gli artefatti X-ray; non introduce ulteriori correzioni applicative o documentali.
