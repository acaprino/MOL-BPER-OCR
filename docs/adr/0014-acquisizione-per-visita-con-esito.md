# 0014 - Acquisire per visita e confermare l'esito dell'estrazione

- **Stato:** Accettato
- **Data:** 2026-09-11
- **Interessa:** `edge-agent/workers/capture/bper_capture_worker.py`
- **Test:** `tests/test_bper_capture_lifecycle.py`, `tests/test_bper_capture_framing.py`
- **Integra:** [0007](0007-conferma-stabilita-su-frame-invariato.md)
- **Correlati:** [0013](0013-risultati-nell-ordine-di-acquisizione.md), [0015](0015-scatto-manuale-nel-thread-di-cattura.md)

## Contesto

Il blocco automatico per nome pagina durava per l'intero job. Visitare la stessa
pagina su una seconda pratica poteva quindi essere ignorato. Inoltre il nome veniva
aggiunto a `captured_page_types` dopo il tentativo di invio, prima di sapere se il
frame fosse stato accettato o se l'estrazione fosse riuscita. Un errore consumava
l'acquisizione automatica e richiedeva il recupero manuale.

La conferma senza una seconda risposta del router, introdotta da [0007], resta
utile. Cambiano il criterio che distingue una nuova visita e il momento in cui
l'acquisizione viene dichiarata completata. Il ramo globale «già acquisita» descritto
nelle conseguenze di quell'ADR non è più il blocco di deduplicazione corrente.

## Decisione

Una **visita** è la permanenza di un'immagine normalizzata invariata. Prima del
preprocess il worker confronta dimensioni, modalità colore e digest BLAKE2b a 128
bit dei pixel. Un'identità diversa apre una nuova visita e resetta candidato e
tempo di stabilità, anche quando il router riconosce lo stesso nome pagina.
Questo confronto non usa una soglia percettiva: anche un piccolo cambiamento
visibile dell'NDG può riarmare la cattura.

Il pHash resta nel percorso di conferma del routing. Un duplicato può confermare
il candidato solo se il suo nome coincide con l'ultima pagina riconosciuta; la
permanenza minima di 2 secondi continua ad applicarsi. L'etichetta resta sostenuta
da una sola risposta del router, con il compromesso già esplicitato da [0007].

L'ingest accettato porta la visita in attesa. Il worker registra
`(job_id, _capture_sequence) → (visita, pagina)` e attende l'esito. Finché i pixel
restano invariati, sia l'attesa sia il completamento bloccano nuovi invii automatici
e nuove chiamate al router. `captured_page_types` contiene soltanto i nomi delle
pagine elaborate senza errore e serve alla guida dell'operatore, non alla dedup del job.

- Il rifiuto dell'ingest non consuma la visita e riavvia l'intervallo di stabilità.
- `_status=ERROR` libera l'attesa solo se sequenza e visita corrispondono ancora
  alla cattura corrente. Prima del retry deve maturare un nuovo intervallo stabile.
- Gli altri esiti completano la visita. Anche `ANCHOR_UNCERTAIN` può contenere
  campi utili di una schermata senza header: ripeterla automaticamente senza limite
  produrrebbe nuove chiamate a pagamento senza una nuova immagine.
- L'esito di una vecchia visita può aggiornare il riepilogo delle pagine elaborate,
  ma non libera né completa la cattura pendente di una visita successiva.

Gli esiti entrano nella coda descritta da [0015]. La registrazione della sequenza
precede il consumo dell'ack anche se il client termina prima che l'ingest ritorni.

## Alternative valutate

- **Mantenere il blocco per nome.** Impedisce il retry e le pratiche successive
  all'interno dello stesso job.
- **Riarmare soltanto con il pHash.** La somiglianza dell'intero layout può
  nascondere la variazione di poche cifre. Non è una misura di identità dei dati.
- **Ritagliare una banda fissa per l'NDG.** Reintroduce l'assunzione di una posizione
  dell'header valida per ogni inquadratura, già esclusa da [0010](0010-ritaglio-autorizzato-dal-percorso-e-dalla-famiglia.md).
- **Riprovare a ogni frame dopo un errore.** Elimina l'attesa proprio durante un
  guasto e moltiplica i tentativi; il nuovo intervallo stabile limita la cadenza.

## Conseguenze e verifica

Tornare A → B → A permette una nuova acquisizione di A. Anche una modifica locale
che resta sotto la soglia pHash può aprire una visita. L'identità riguarda tutti i
pixel catturati: animazioni o altre variazioni ripetute fanno ripartire la stabilità,
possono ritardare l'acquisizione automatica e richiedere ulteriori chiamate di routing.
La scelta privilegia il rilevamento dei cambiamenti piccoli; «Acquisisci ora» resta
disponibile quando la schermata non si ferma. Una schermata immobile già pendente
o completata non paga una nuova estrazione automatica.

I test `test_small_identity_change_on_the_same_page_can_be_acquired` e
`test_returning_to_a_page_is_a_new_visit` proteggono il riarmo. Il caso
`test_stationary_page_is_not_rerouted_after_completion` verifica un solo ingest e
una sola route. Gli altri test del lifecycle coprono accodamento senza conferma,
errore e rifiuto recuperabili, ack vecchio e `ANCHOR_UNCERTAIN` senza ricatture
infinite. `test_an_unchanged_screen_is_acquired_without_a_second_route` mantiene
la garanzia di [0007]. I test usano camera, router e client controllati; non
misurano latenza, costo o stabilità visiva in una sessione bancaria reale.

[0007]: 0007-conferma-stabilita-su-frame-invariato.md
[0015]: 0015-scatto-manuale-nel-thread-di-cattura.md
