# 0003 - La chiave della cache prototipi include la geometria di embedding

- **Stato:** Accettato
- **Data:** 2026-08-17
- **Interessa:** `edge-agent/page_classifier.py`
- **Test:** `tests/test_page_classifier.py::test_cache_is_stale_when_the_embedding_geometry_changed`
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
(usata dal pre-flight, che non importa torch) sia da `_load_or_build_prototypes()`. Se non coincide,
i prototipi si ricostruiscono.

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
parametri reali non può andare fuori sincrono con essi.

## Conseguenze

Chiunque cambi ROI, dimensione di embedding, modello o regola di punteggio ottiene automaticamente
una ricostruzione dei prototipi, con qualche secondo di attesa al primo avvio.

Il formato della cache guadagna un campo. I file di cache scritti da versioni precedenti non hanno
`geometry`, quindi risultano non validi e vengono ricostruiti: è il comportamento desiderato, non una
migrazione da gestire.

`embedding_geometry()` è ora parte del contratto del modulo: chi aggiunge un parametro che influenza
l'embedding deve aggiungerlo anche lì. Non esiste un controllo automatico che lo imponga, ed è la
stessa classe di fragilità che `CLAUDE.md` documenta per `AREA_TO_FIELDS` rispetto a `FIELD_KEYS`.
