# 0038 - Riscontro visivo nelle decisioni del router di pagina

- Data 2026-11-26
- Stato accettato

## Contesto

Nelle catture verificate in `tests/fixtures/frames/tooltips/manifest.json`, il fotogramma
`tooltip-3a.png` mostra un'ipoteca come unica garanzia, in prima riga. Il catalogo chiedeva
al router di usare proprio la posizione per scegliere fra le due varianti. I nomi storici con
«riga 1» e «riga 2» derivano dalla pratica di riferimento.

Le catture in `tests/fixtures/frames/no-tooltip/manifest.json` mostrano sia il pannello
«Nota della richiesta» compresso, sia la linguetta inattiva «Note da Richiesta» accanto alla
«Nota all'istruttoria». Il vecchio prompt ammetteva anche checklist e allegati come prova
della pagina delle note. Durante l'etichettatura, questa regola aveva attirato schermate
di Gestione Documentale nella classe 9, come registrato in `processes/bper-p1.json`.

## Decisione

Il router LLM acquisisce le due varianti di garanzia solo se il modello trascrive dal
tooltip aperto la descrizione compatibile con la classe proposta. Per le Note richiede
il titolo del riquadro centrale, leggibile anche con la nota compressa. Le trascrizioni
accettate sono nei campi `evidence_texts` del catalogo pagine. Il confronto ammette
variazioni di maiuscole, spazi e punteggiatura. Per un'etichetta sconosciuta, una prova
assente o incompatibile, o una confidenza fuori da 0,60–1,00, il router restituisce
«Altro / Non riconosciuto». Un errore del client restituisce invece il motivo del guasto.
Il suggerimento sulla prossima pagina ha solo valore di contesto.

Per le viste dell'elenco il prompt usa le colonne mobili e la barra di scorrimento della
tabella dei risultati. I fotogrammi di riferimento mostrano ABI, NDG e Denom. anche nella
vista estesa. A finestra larga entrambe le viste mostrano colonne di assegnazione e di data.

## La proposta Note del classificatore locale

DINOv2 confondeva pagine finanziarie a finestra larga con le Note anche dopo la normale
inquadratura e il preprocessing del worker. Nei fotogrammi di riferimento la barra del menu
PEF copre circa l'85% della larghezza. In una cattura diretta a 1915 px ne copre il 47%.
Un secondo ritaglio ricostruito da questa barra ha migliorato alcune famiglie ma ha anche
assegnato tooltip al Fido senza popup. Il solo margine di 0,10 avrebbe rifiutato una vera
Nota compressa (`tests/fixtures/frames/no-tooltip/base-9a-chiuso.png`).

La pagina Note usa quindi `ml_excludes_table_sections` nel catalogo distribuito. Solo
quando il prototipo propone quella pagina sopra la soglia di similarità, il classificatore
verifica la disposizione delle barre. Il menu PEF e la scheda identificativa producono
due barre scure allineate a destra. Le tabelle di Soggetti e di Fidi aggiungono proprie
intestazioni scure; il pannello Nota della richiesta ha un'intestazione grigia. Tre barre
scure larghe, distinte e allineate sono un riscontro contrario alle Note. In questo caso
il classificatore si astiene e lascia disponibile l'eventuale verifica LLM in `local-first`.
Il numero di barre da solo non identifica la variante della pagina finanziaria.

Nella misura sulle schermate di dettaglio dell'archivio, escluse la pratica di riferimento
dei prototipi e tutte le pratiche di test, le barre aggiuntive erano visibili su 64/64
Soggetti e Fidi di addestramento e su 7/7 di controllo. Erano assenti su tutte le 17 Note
di addestramento e su entrambe le Note di controllo. I cinque fogli Scheda Privati di
addestramento erano privi della struttura; il controllo da solo non riconosce questi
negativi. Barre parzialmente tagliate dallo scorrimento o un nuovo tema BPER possono far
perdere questo riscontro. Una nuova disposizione delle vere Note richiede di verificarlo
nuovamente. `tests/test_page_classifier.py` esercita sia una falsa Nota reale sia la Nota
compressa con DINOv2.

| Campione di dettaglio | False Note prima → dopo | Vere Note riconosciute prima → dopo |
|---|---:|---:|
| Addestramento, 86 schermate | 39 → 0 su 69 | 16 → 16 su 17 |
| Controllo, 9 schermate | 7 → 0 su 7 | 2 → 2 su 2 |

I rifiuti evitano l'acquisizione con l'etichetta sbagliata. Il titolo della pagina visitata
richiede una lettura ulteriore o uno scatto manuale.

## Verifica e limiti

`tests/test_llm_page_router.py` riproduce le risposte del provider con le diciture presenti
nelle catture curate. Verifica la decisione del codice dopo la lettura visiva. L'accuratezza
della lettura del modello richiede una misura separata su fotogrammi etichettati. Il vincolo
può far perdere una pagina valida se il tooltip è illeggibile o contiene una descrizione nuova.
Anche un testo inventato dal modello può coincidere con una dicitura ammessa. La difficoltà
nel distinguere le due viste di ricerca a elevate risoluzioni resta quella misurata nell'ADR 0012.

Nelle installazioni con personalizzazioni occorre aggiornare insieme il catalogo pagine e
il prompt di sistema del router affinché il modello produca il nuovo campo `evidence`.
