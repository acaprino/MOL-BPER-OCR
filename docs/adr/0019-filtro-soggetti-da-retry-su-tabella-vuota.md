# 0019 - Filtrare i soggetti del retry che riempie una tabella vuota

- **Stato:** Accettato
- **Data:** 2026-10-16
- **Interessa:** `extraction/pipeline.py`
- **Test:** `tests/test_pipeline_retry_subjects.py`, `tests/test_content_crop.py`
- **Correlati:** [0004](0004-budget-retry-derivato-dalle-aree.md), [0010](0010-ritaglio-autorizzato-dal-percorso-e-dalla-famiglia.md), [0018](0018-appiattimento-soggetti-con-merge-e-provenienza.md)

## Contesto

L'assenza di soggetti è normale su molte pagine. I campi BODY mancanti possono
comunque innescare un retry; una riga inventata rendeva la tabella più lunga e
veniva accettata, anche con confidenza bassa o soltanto un ruolo senza identità.
Il flatten rendeva poi quella riga visibile nei campi numerati della pratica.

L'ADR 0004 ha lasciato esplicitamente aperto questo rischio. La protezione fuori
calibrazione impedisce di sostituire tabelle esistenti, ma consente di riempire
quelle vuote e quindi non lo elimina.

## Decisione

Quando la tabella `soggetti` corrente è vuota, `_merge_tables()` filtra le righe
proposte da RETRY_BODY prima della selezione della tabella. Ogni riga accettata
deve avere `confidence >= RETRY_CONF_MIN` e almeno uno fra `ndg` e `denominazione`
non nullo secondo `is_nullish()`. La soglia include il valore esatto e riusa la
configurazione esistente, senza aggiungere una nuova variabile d'ambiente.

Il filtro opera per riga: una riga affidabile sopravvive anche accanto a righe
anonime o deboli. Solo le righe filtrate possono raggiungere il flatten. La
regola si applica sia alle immagini calibrate sia ai frame fuori calibrazione;
la fonte RETRY_BODY viene attribuita soltanto se una tabella viene accettata.

Non cambiano la selezione delle tabelle `soggetti` già popolate, i criteri per
`fidi`/`garanzie`, le passate richieste né il budget di chiamate. Non viene
introdotto un gate basato sulla pagina riconosciuta.

## Alternative valutate

- **Usare la sola confidenza media della tabella.** Righe molto sicure possono
  nascondere altre righe deboli o anonime; il controllo per riga evita che queste
  ultime vengano accettate insieme alle prime.
- **Rifiutare l'intera tabella mista.** Perderebbe le righe che soddisfano entrambi
  i requisiti e che possono recuperare dati mancanti.
- **Disabilitare BODY sulle pagine senza soggetti.** Richiede una classificazione
  di pagina disponibile e affidabile in tutti gli ingressi, non presente nel
  contratto attuale della pipeline.

## Conseguenze e verifica

Una riga priva di identificativi non può più inizializzare la tabella soltanto
perché è più lunga di una lista vuota. Confidenza e presenza di un identificativo
non provano però che la riga esista nell'immagine: una riga allucinata con entrambi
i requisiti può ancora passare. Non si dichiara un miglioramento misurato di
accuratezza o una riduzione delle chiamate al provider.

I test coprono soglia, nullish, identificativo singolo e tabelle miste su entrambi
i percorsi geometrici. Il fixture dei test di crop ora contiene un NDG leggibile:
quelle asserzioni mantengono il vincolo di inquadratura, mentre i casi anonimi
vengono verificati dalla nuova suite dedicata senza allentare le asserzioni.
