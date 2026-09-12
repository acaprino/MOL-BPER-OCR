# Verifica del riallineamento

## Perimetro
Analisi del working tree su `f8f57e6124e0` (develop), incluse le modifiche documentali non ancora committate. Nessun sorgente applicativo è stato modificato durante questa analisi. I dettagli dei file e dei simboli sono in `../snapshot/manifest.json`; il confronto col run precedente è in `../changes.md`.

## Esecuzione attuale dei test
`python -m pytest tests`: **173 passed, 3 warnings in 38.20s**, exit code 0. È una nuova esecuzione, distinta dai risultati storici. Log completo: `pytest.txt`; comando e override ambientali: `test-command.json`. Gli avvisi sono relativi a xFormers assente. Le prove usano confini simulati per i provider, non una sessione bancaria reale. Non sono state invocate API di estrazione. OMP/MKL sono limitati a due thread per questa sola esecuzione; nessuna configurazione persistente è cambiata.

## Verifica delle correzioni prioritarie
| Rilievo storico | Stato | Evidenza corrente |
|---|---|---|
| XQ-R01, risultati nell'ordine di completamento | Risolto nel percorso get_results → consolidamento | `edge-agent/local_extraction_client.py:127` (`LocalExtractionClient.ingest_frame`), `:200` (pubblicazione del prefisso), `:222` (`get_results`); `tests/test_local_extraction_client.py:117` (`test_out_of_order_completions_preserve_practice_assignment`). Il segnale result_ready resta in ordine di completamento. |
| XQ-R02, pagina consumata prima dell'esito e per tutta la sessione | Risolto per il contratto di visita ed esito | `edge-agent/workers/capture/bper_capture_worker.py:299` (`_complete_capture`), `:329` (`_observe_frame`), `:422` (`_acquire`); `tests/test_bper_capture_lifecycle.py:105`, `:122`, `:132`, `:141`, `:151`, `:165`. |
| XQ-R03, scatto manuale sul thread UI | Risolto | `edge-agent/workers/capture/bper_capture_worker.py:722` (`force_capture`) accoda; `:284` (`_drain_commands`) esegue; `tests/test_bper_capture_lifecycle.py:183` verifica thread di acquisizione e chiusura della camera. |

Queste chiusure non equivalgono alla risoluzione degli altri rilievi: il timeout di arresto, il fallback local-first e gli altri contratti vengono valutati separatamente nei rapporti correnti. Lo storico precedente viene conservato senza modifiche; `parent-integrity.json` registra gli hash antecedenti al riallineamento.
