# 0015 - Eseguire lo scatto manuale nel thread di cattura

- **Stato:** Accettato
- **Data:** 2026-09-11
- **Interessa:** `edge-agent/workers/capture/bper_capture_worker.py`
- **Test:** `tests/test_bper_capture_lifecycle.py`
- **Correlati:** [0014](0014-acquisizione-per-visita-con-esito.md)

## Contesto

«Acquisisci ora» chiama `force_capture()` direttamente dalla UI. Prima della
modifica quel metodo catturava lo schermo, preprocessava e modificava lo stato
usato contemporaneamente dal ciclo automatico. Il contesto mss nasce nel thread
di cattura: usarlo o chiuderlo dal thread UI introduceva anche un accesso fra thread
al medesimo oggetto.

`BPERCaptureWorker` deriva da `QThread`, ma il suo `run()` esegue un ciclo Python e
non avvia un event loop Qt. Il decoratore `pyqtSlot` da solo non cambia il thread
di una chiamata Python diretta e non consegna i comandi a quel ciclo.

## Decisione

Il worker possiede una `queue.Queue` per richieste manuali ed esiti estrattivi.
L'API pubblica `force_capture(page_name)` inserisce soltanto un comando, purché
l'arresto non sia già stato richiesto. `_capture_once()` consuma i comandi nel
thread di cattura; `_execute_manual_capture()` risolve la pagina, acquisisce il
frame e usa lo stesso percorso `_acquire()` della cattura automatica.

Lo scatto manuale bypassa routing e attesa di stabilità. Una richiesta per la
stessa pagina della visita già pendente non accoda una seconda estrazione; dopo
un successo la richiesta esplicita può invece acquisire di nuovo. Un giro che
ha gestito richieste manuali non aggiunge una cattura automatica nello stesso giro.

Se lo scatto manuale fallisce con `ERROR` e l'immagine resta invariata, il retry
dopo il nuovo intervallo stabile conserva la pagina scelta dall'operatore e i
metadati manuali (`confidence=0.0`, campi vuoti). Non eredita etichetta, confidenza
o campi di un routing automatico precedente, anche quando il manuale è il primo
scatto della sessione.

Anche `result_ready` usa la coda. Il collegamento `DirectConnection` esegue solo
`_queue_extraction_result()`, che copia job, sequenza e stato in una tupla accodata.
La modifica di visite, pending e guida avviene quando il ciclo consuma l'ack,
mai nel thread della pipeline o della UI. Questo gestisce anche un risultato
arrivato prima del ritorno di `ingest_frame()`.

`stop()` richiede l'arresto senza chiudere mss. Il flag viene controllato prima
del consumo dei comandi e dopo screenshot o routing, e `_acquire()` lo verifica
prima di accodare un frame. Il `finally` di `run()` chiude mss nel thread che lo
usa e scollega la ricezione degli esiti.

## Alternative valutate

- **Aggiungere soltanto un lock a `force_capture()`.** Impedisce parte della
  sovrapposizione, ma lascia screenshot e preprocess nella UI e non conserva la
  proprietà del contesto mss da parte del thread di cattura.
- **Usare soltanto un segnale Qt accodato.** Il ciclo personalizzato non consuma
  eventi Qt; richiederebbe una diversa organizzazione del worker.
- **Creare una seconda camera per il manuale.** Non risolve gli aggiornamenti
  concorrenti di dedup, stabilità e pending.

## Conseguenze e verifica

La UI invia rapidamente la richiesta; lo scatto avviene quando il ciclo la
raggiunge. Una chiamata router già in corso può ritardarlo: il comando non interrompe
la rete e cattura l'immagine presente quando viene eseguito. L'arresto impedisce
il successivo ingest dopo che il controllo torna al worker; non cancella chiamate
già partite né le estrazioni che proseguono nel pool.

`test_manual_request_waits_for_the_capture_thread` blocca la camera mentre la UI
richiede uno scatto: verifica che l'ingest attenda, che tutte le catture avvengano
in un solo thread diverso dal chiamante e che mss venga chiuso nello stesso thread.
`test_stop_discards_queued_manual_requests` verifica che uno stop prima di `run()`
non esegua i comandi pendenti. I test sul manuale durante pending e dopo successo
proteggono rispettivamente la coalescenza e il recupero esplicito. Sono verifiche
con `QCoreApplication` e camera controllata, senza avviare una GUI o un provider.
`test_first_manual_capture_retries_the_operator_page_after_error` e
`test_manual_retry_does_not_reuse_automatic_route_metadata` proteggono la pagina
scelta e i metadati del retry manuale.
