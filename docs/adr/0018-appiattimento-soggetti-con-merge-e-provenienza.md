# 0018 - Appiattire i soggetti con merge e provenienza del vincitore

- **Stato:** Accettato
- **Data:** 2026-10-16
- **Interessa:** `extraction/pipeline.py`
- **Test:** `tests/test_pipeline_postprocessing.py`, `tests/test_content_crop.py`
- **Correlati:** [0010](0010-ritaglio-autorizzato-dal-percorso-e-dalla-famiglia.md)

## Contesto

La pipeline legge i soggetti sia nei dodici campi numerati sia nella lista
`soggetti`. Dopo il merge dei retry, l'appiattimento delle prime quattro righe
sovrascriveva gli scalari anche con valori nulli o con confidenza inferiore.
Un valore corretto conservato da `pick_best()` poteva quindi andare perso
nell'ultimo passaggio. `_field_sources` manteneva inoltre la sorgente dello
scalare precedente, anche quando il valore finale proveniva dalla tabella.

Il motore è condiviso fra estrazioni concorrenti. La provenienza di una
tabella deve quindi appartenere alla singola estrazione e seguire soltanto
le tabelle effettivamente accettate.

## Decisione

L'ordine del post-processing resta invariato. Per ciascuno dei primi quattro
soggetti, ogni valore `ndg`, `denominazione` e `ruolo` diventa un candidato
per il campo numerato corrispondente. Il candidato conserva la confidenza
della riga e la sezione `soggetti_table` e compete con lo scalare corrente
tramite `merge_field_sources()`, che usa `pick_best()`:

- un valore non nullo prevale su uno nullo;
- a parità di nullità prevale la confidenza maggiore;
- a parità di confidenza resta lo scalare corrente.

Se vince il candidato tabellare, `_field_sources` riceve l'origine della
tabella accettata: `CONTENT_MAIN` oppure `RETRY_BODY`. Se vince lo scalare,
la sua sorgente resta invariata. Una lista vuota non propone candidati.

Un dizionario `table_sources`, locale a `extract_from_image()`, parte da
`CONTENT_MAIN` e viene passato come argomento keyword facoltativo a
`_retry_areas()` e `_merge_tables()`. Solo un retry BODY la cui tabella viene
accettata aggiorna la relativa origine. Il risultato pubblico non aggiunge
metadati di provenienza delle tabelle.

I criteri di accettazione delle tabelle restano quelli esistenti: sulla
famiglia calibrata prevalgono più righe, poi la confidenza media maggiore a
parità di righe; fuori calibrazione BODY può soltanto riempire una tabella
vuota, come stabilito dall'ADR 0010. Un retry rifiutato conserva sia la
tabella corrente sia la sua origine.

## Alternative valutate

- **Lasciare la tabella sempre prioritaria.** Continua a perdere scalari
  migliori e tratta un valore nullo come una correzione affidabile.
- **Usare le righe solo per gli scalari mancanti.** Evita di cancellare valori,
  ma impedisce a una lettura tabellare con confidenza maggiore di migliorarli.
- **Memorizzare l'origine sull'istanza della pipeline.** Espone estrazioni
  concorrenti a uno stato condiviso che appartiene al singolo risultato.
- **Aggiungere un nuovo campo diagnostico all'output.** Allarga il contratto
  pubblico senza necessità per attribuire i dodici scalari finali.

## Conseguenze e verifica

Appiattimento, retry e consolidamento usano la stessa preferenza fra valori.
La provenienza degli scalari provenienti dai soggetti segue il vincitore
senza modificare selezione delle tabelle, budget o campi canonici.

Restano limiti espliciti: i candidati tabellari del flatten non aggiungono
`evidence_text`, il main assegna `CONTENT_MAIN` anche ai campi assenti e le
regole di coerenza non registrano una nuova origine. `_field_sources` non è
quindi una cronologia completa delle trasformazioni.

`test_flatten_preserves_the_better_scalar_value` protegge valori nulli,
confidenze inferiori e parità sulle tre colonne dei soggetti.
`test_flatten_adopts_a_better_main_table_value` e
`test_flatten_reports_the_retry_source_for_an_adopted_table` verificano le
origini dei candidati vincenti. Gli altri casi di
`test_pipeline_postprocessing.py` coprono riempimento fuori calibrazione,
rifiuto e sostituzione calibrata delle tabelle, con la rispettiva provenienza.
`test_content_crop.py` mantiene il vincolo geometrico sulle tabelle dei retry.
