# 0003 - La chiave della cache prototipi include la geometria di embedding

- **Stato:** Accettato
- **Data:** 2026-08-17
- **Interessa:** `edge-agent/page_classifier.py`
- **Test:** `tests/test_page_classifier.py::test_prototypes_of_another_embedding_geometry_are_not_ready`, `tests/test_page_classifier.py::test_classifier_refuses_prototypes_of_another_embedding_geometry`
- **Nasce da:** [0002](0002-riconoscimento-pagina-roi-e-coseno-centrato.md)

## Contesto

Calcolare i 9 prototipi richiede 9 passaggi in avanti di DINOv2 su CPU, quindi il risultato viene
messo in cache in `edge-agent/assets/templates/bper/bper_page_prototypes.json`. La cache è valida
quando `dataset_hash` coincide, e `_compute_dataset_hash()` lo costruisce su:

- il nome del page_type
- il nome del file
- il digest SHA-1 del **contenuto** del file

Sono tutte proprietà delle immagini. Nessuna riguarda **come** l'immagine viene trasformata in
vettore.

Prototipi e query devono essere immersi nello stesso modo, altrimenti il confronto non ha senso. Ma
`crop_roi`, la transform e il modello non entravano nella chiave: cambiando la ROI,
`cache_is_valid()` continuava a restituire `True` e il classificatore serviva vettori costruiti con
la geometria vecchia mentre le query usavano quella nuova. Nessun errore, nessun avviso, punteggi
plausibili e privi di significato.

Al momento della modifica la cache era per fortuna coerente con il codice: verificato ricostruendo i
prototipi con la geometria corrente e confrontandoli con quelli in cache, coseno 1.000000 su tutti e
9. Ma [0002](0002-riconoscimento-pagina-roi-e-coseno-centrato.md) cambia proprio ROI, transform e
regola di punteggio, quindi la mina sarebbe scattata subito.

## Decisione

Introdurre `embedding_geometry(crop_roi=None) -> str`, che descrive l'identità del procedimento di
embedding: nome del modello, ROI arrotondata, dimensione e modalità di resize, regola di punteggio.

La stringa viene scritta nella cache come campo `geometry` e confrontata sia da `cache_is_valid()`
(usata dal pre-flight, che non importa torch) sia da `_read_shipped_prototypes()`. Se non coincide,
i prototipi non sono validi e vanno ricostruiti fuori dall'app con `tools/build_prototypes.py`
([0030](0030-prototipi-delle-pagine-distribuiti-con-l-app.md)).

Il parametro `crop_roi` esiste perché la ROI è un attributo di istanza, non necessariamente
`DEFAULT_CROP_ROI`: il classificatore passa la propria, mentre `cache_is_valid()` non ha un'istanza e
usa il default.

## Alternative valutate

**Aggiungere la geometria al `dataset_hash` esistente.** Confonde due cose diverse in un solo campo:
"le immagini sono cambiate" e "il procedimento è cambiato" hanno cause e rimedi distinti, e tenerle
separate rende leggibile il motivo di una ricostruzione.

**Cancellare la cache a mano quando si cambia la geometria.** È la procedura che ha appena mancato di
essere seguita, e dipende dal fatto che chi modifica sappia che la cache esiste. Una chiave che si
autoinvalida non richiede che nessuno si ricordi.

**Versione numerica incrementata a mano.** Funziona solo se chi modifica la geometria si ricorda di
incrementarla, cioè ha lo stesso difetto della cancellazione manuale. La stringa derivata dai
parametri reali non richiede che nessuno se ne ricordi.

**Correzione (2026-08-18, peer review finding F10).** La formulazione originale di
questo paragrafo diceva che una stringa derivata dai parametri "non puo' andare fuori
sincrono": e' falso come scritto. `embedding_geometry()` **enumera a mano** un
sottoinsieme, e omette la revisione del modello e i pesi (`DINOV2_HUB_REPO` e
`DINOV2_WEIGHTS_SHA256` in `page_classifier.py`), `InterpolationMode.BICUBIC` e
`T.Normalize(...)`. Cambiando la revisione DINOv2 fissata senza cambiare il nome del
modello, la chiave resta identica e i vettori vecchi vengono confrontati con query nuove.
La chiave copre le modifiche che sono passate per i suoi parametri, non tutte quelle che
influenzano l'embedding.

## Conseguenze

Chiunque cambi ROI, dimensione di embedding, modello o regola di punteggio se ne accorge subito:
l'app rifiuta i prototipi distribuiti, che vanno ricostruiti con `tools/build_prototypes.py`
([0030](0030-prototipi-delle-pagine-distribuiti-con-l-app.md)).

Il formato della cache guadagna un campo. I file di cache scritti da versioni precedenti non hanno
`geometry`, quindi risultano non validi: è il comportamento desiderato, non una migrazione da
gestire.

`embedding_geometry()` è ora parte del contratto del modulo: chi aggiunge un parametro che influenza
l'embedding deve aggiungerlo anche lì. Non esiste un controllo automatico che lo imponga, ed è la
stessa classe di fragilità che `CLAUDE.md` documenta per `AREA_TO_FIELDS` rispetto a `FIELD_KEYS`.
