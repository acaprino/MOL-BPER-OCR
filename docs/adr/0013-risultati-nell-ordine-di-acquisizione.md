# 0013 - Pubblicare i risultati nell'ordine di acquisizione

- **Stato:** Accettato
- **Data:** 2026-09-11
- **Interessa:** `edge-agent/local_extraction_client.py`, i consumatori di `get_results()`
- **Test:** `tests/test_local_extraction_client.py`
- **Correlati:** [0014](0014-acquisizione-per-visita-con-esito.md)

## Contesto

L'estrazione usa più thread e può terminare in un ordine diverso dalla cattura.
`consolidate()` associa un frame senza NDG alla pratica precedente nella lista che
riceve. Accodare i risultati al termine dell'estrazione poteva quindi spostare una
nota sulla pratica sbagliata.

Esempio: l'operatore acquisisce la pratica 111, una nota senza NDG, poi la pratica
222. Se la nota termina per ultima, l'ordine di completamento diventa 111, 222,
nota: il consolidamento attribuisce la nota a 222. La regola di associazione richiede
l'ordine di acquisizione, anche quando la velocità dei servizi esterni varia.

## Decisione

`LocalExtractionClient.ingest_frame()` assegna una sequenza intera, a partire da
zero e distinta per job, a ogni frame accettato. La restituisce subito dopo
l'accodamento. La sequenza compare nel risultato come `_capture_sequence`, anche
quando la pipeline produce `_status=ERROR`.

I risultati completati vengono conservati per sequenza. `get_results(job_id)`
espone soltanto il **prefisso contiguo completato**: se sono pronti 0 e 2, restituisce
solo 0; quando termina 1, restituisce 0, 1, 2. Un esito di errore occupa il proprio
posto e permette di pubblicare i successivi. Un job lento non blocca gli altri job.

Anche un errore diagnostico non deve lasciare un buco nella sequenza. La chiamata
a `_log_extraction()` è protetta da `except Exception`: il client conserva dati e
`_status`, aggiunge `_diagnostic_error` ai metadati e prosegue con pubblicazione e
segnale. Un output di log non scrivibile non annulla un'estrazione completata.

`result_ready(job_id, result)` continua a notificare ciascun completamento senza
attendere il prefisso. Il segnale serve anche ai contatori e alla conferma della
cattura; non è una lista già ordinata. La tabella e gli export leggono
`get_results()` prima di consolidare, mantenendo `consolidate()` e `pick_best()`
come unico percorso di associazione e fusione dei campi.

Il pool chiuso rifiuta un nuovo ingest con `RuntimeError`, senza emettere
`frame_queued` e senza consumare una sequenza. L'accettazione e l'arresto del pool
sono protetti dallo stesso lock del client.

## Alternative valutate

- **Ordinare soltanto i risultati già pronti.** Non basta: se la cattura è 111,
  222, nota e manca ancora il risultato 222, la lista ordinata dei soli pronti è
  111, nota. Anche questa attribuisce temporaneamente la nota alla pratica errata,
  e un export in quel momento conserva l'errore.
- **Eseguire una sola estrazione alla volta.** Conserva l'ordine, ma elimina il
  parallelismo anche quando non ci sono dipendenze fra le chiamate.
- **Cambiare la fusione dei campi.** Non ricostruisce un ordine perso. La sequenza
  appartiene al confine di accettazione dei frame, prima dell'esecuzione parallela.

## Conseguenze e verifica

Un risultato già terminato può apparire in tabella ed essere esportabile solo dopo
un predecessore lento. Il contatore dei completamenti può avanzare prima della
tabella: misura un evento diverso dalla disponibilità del prefisso. Il ritardo è
accettato per evitare attribuzioni temporanee scorrette. La regola resta valida
solo per l'ordine osservato: non può recuperare l'NDG che un frame non contiene.

`test_out_of_order_completions_preserve_practice_assignment` forza entrambi gli
ordini problematici con il pool reale e un confine di estrazione controllato, e
verifica la nota nella pratica corretta prima e dopo il completamento mancante.
`test_slow_job_does_not_delay_another_jobs_results` protegge l'indipendenza dei job;
`test_error_completion_releases_the_following_ordered_results` protegge gli slot
di errore; `test_rejected_ingest_does_not_emit_frame_queued` protegge il rifiuto.
`test_log_write_error_does_not_block_ordered_results` verifica che un errore di
scrittura del log non impedisca di pubblicare e notificare i risultati ordinati.
Queste verifiche non misurano l'accuratezza dei modelli o una sessione GUI reale.
