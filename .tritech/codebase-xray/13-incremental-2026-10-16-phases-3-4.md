# Aggiornamento incrementale 2026-10-16 — Fasi 3 e 4

Analisi mirata sopra il run `poc-data-extraction-20260912-175144` e gli incrementi
successivi. Base: branch `develop`, commit `3be17a8`, più le modifiche non committate
elencate qui. Il commit contiene le Fasi 1–2; non include la migrazione X-ray già
staged né lo stato condiviso aggiornato da un'altra attività. I documenti 01–08 e
gli incrementi precedenti conservano il proprio snapshot: questo documento aggiorna
soltanto i contratti e i finding indicati sotto.

## Perimetro ed esclusioni

Sono realizzate le Fasi 3–4 del piano allegato: pagina sorgente dei campi privati,
filtro del retry che inizializza i soggetti, avvio Tkinter, rimozione dei helper
batch inutilizzati e selezione della suite rapida. Restano fuori l'addestramento
locale in `training/` e i relativi test, la revisione della ground truth riportata
nel documento 12, la migrazione staged di 178 file X-ray e `.gitignore`.

Queste attività concorrenti vengono preservate. La suite completa può includere
anche i loro test presenti nel workspace; questo non estende il perimetro della
revisione o attribuisce quei sorgenti a questa modifica.

## Decisioni applicate

- La pagina sorgente diventa `scheda_privati` per i tredici campi interessati.
  Il gruppo esplicito di export resta `note_da_richiesta`: si conservano tutte le
  45 posizioni delle colonne e le quattro bande UI/Excel. Il payload canonico
  emette la pagina corretta senza nuove chiavi. Decisione: ADR 0020.
- Il filtro richiesto per la tabella soggetti vuota opera per riga, prima della
  selezione calibrata o fuori calibrazione. Ogni riga deve raggiungere
  `RETRY_CONF_MIN` e avere NDG o denominazione non nullish. Una media elevata non
  deve far passare righe anonime o deboli insieme a quelle valide. Decisione:
  ADR 0019. Le regole delle tabelle già popolate e di fidi/garanzie restano invariate.
- I test di crop usano ora una riga identificata al posto del precedente fixture
  con tutti gli identificativi nulli. Le asserzioni geometriche non sono state
  allentate; il nuovo test dedicato protegge il rifiuto delle righe anonime.
- La GUI carica dotenv prima del motore e usa provider e modello effettivi.
  L'ambiente già esportato prevale; il menu non resetta un modello configurato
  soltanto perché non compare nei suggerimenti. Decisione: ADR 0021.
- Si rimuove la deduplica batch mai chiamata, invece di abilitarla: i risultati
  devono conservare le schermate, comprese varianti e pratiche diverse. La sola
  pagina del primo campo canonico non è un'identità della pratica.
- `get_screenshot_paths()` era già assente nel sorgente corrente: non si dichiara
  di averlo rimosso. Si corregge il riferimento obsoleto nelle istruzioni.
- `pyproject.toml` contiene solo configurazione pytest. `tools/check.py` seleziona
  `not slow` e inoltra argomenti pytest usando l'interprete attivo dalla radice
  del repository. Solo i 18 casi con inferenza DINOv2 sono slow; i due test puri
  della cache restano rapidi. Nessun filtro predefinito sulla suite completa,
  metadato di packaging, nuova dipendenza o CI introdotti. Non si promette un
  tempo inferiore a due secondi per import SDK e test GUI in processi separati.

## Owner, interfacce e flussi aggiornati

| Componente | Contratto corrente |
|---|---|
| `extraction/field_definitions.py:278` | `page_key` indica la sorgente; `export_group_key` è l'override di gruppo per i tredici campi privati. `resolve_field_export_group_key()` applica l'override o il fallback alla pagina. |
| `extraction/page_definitions.py` | Cinque pagine sorgenti con nome/alias; `PAGE_SHEET_ORDER` descrive i quattro gruppi export precedenti. Il catalogo del router non cambia. |
| `extraction/canonical_mapping.py:9` | Emette la pagina reale ma conserva l'ordinamento precedente tramite il risolutore di gruppo. Non ordina quindi per sola pagina sorgente. |
| `edge-agent/excel_export.py:96` | Sort e `build_columns()` usano il risolutore condiviso; `ColumnSpec.page_key/page_name` restano il gruppo visualizzato. La UI usa gli stessi descrittori. |
| `extraction/pipeline.py:266`, `:278` | `_merge_tables()` filtra soltanto l'inizializzazione di `soggetti` vuoto dal retry BODY. Righe valide → selezione tabella → origine locale → flatten con merge e fonte del vincitore. |
| `extraction/cli.py:38`, `:192` | Rimossi `_deduplicate_same_page_outputs()`, i suoi quattro helper, l'import `ANCHOR_CONF_MIN` inutilizzato e il blocco commentato. Nessun chiamante operativo trovato. `Tuple` resta usato dal worker. |
| `gui_app.py:8` | dotenv → import motore/config → creazione widget con impostazioni effettive → batch condiviso. Nessun cambiamento al bootstrap dell'edge-agent. |
| `pyproject.toml`, `tools/check.py` | Marker slow registrato e ingresso di check rapido; suite completa ancora eseguibile con `python -m pytest tests`. |

Queste descrizioni aggiornano gli argomenti corrispondenti nei report 01–04 e
07–08 senza attribuire una nuova verifica alle loro vecchie citazioni. Le fonti
puntuali e gli hash del candidato vengono registrati nel manifest della verifica.

## Finding e documentazione

| Finding / tema | Esito mirato |
|---|---|
| XQ-D02 | Ridotto: ramo batch morto rimosso; lo stub `LocalExtractionClient.requeue_job` non è oggetto della modifica e resta aperto. |
| Mapping sorgente/export, ADR 0004 | Corretto per i tredici campi privati con compatibilità del layout verificata. Non abilita automaticamente gating dei retry per pagina. |
| Righe soggetti spurie, ADR 0004 | Mitigato: righe deboli o anonime non inizializzano più la tabella. Righe allucinate ma confidenti e identificate possono ancora passare; non dichiarare eliminato ogni falso positivo. |
| DQ-04 / copertura e check | Aggiornati i comandi e il significato del marker; nessuna versione storica dei risultati viene ripubblicata come verifica corrente. |
| Configurazione GUI | Rimossa l'asimmetria dotenv e corretti i selettori iniziali. Non introduce ricaricamento della configurazione dopo l'import. |
| XQ-A01, XQ-D01, XQ-R08, XQ-D04 | Restano gli esiti dell'incremento 11: i primi due risolti nel perimetro dichiarato, gli ultimi due parziali. Nessun nuovo fix su n_fido o provenienza delle riparazioni di coerenza. |

La guida e le istruzioni vengono aggiornate sul comportamento corrente; gli ADR
0004, 0010 e 0018 conservano il contesto storico e ricevono rimandi dai nuovi ADR,
senza riscriverne le decisioni accettate. Report di esecuzione solo nello X-ray.

## Verifiche osservate

| Area | RED prima del fix | GREEN mirato |
|---|---|---|
| Pagina sorgente e compatibilità export | 30 failed, 18 passed in 15.02s | 85 passed in 10.15s, inclusi metadata, export, vocabolario e post-processing |
| Inizializzazione soggetti | 12 failed, 4 passed in 13.39s | 63 passed in 10.20s, inclusi crop e post-processing |
| Configurazione Tkinter | 5 failed, 1 passed in 51.17s | 6 passed in 42.07s, widget reali; zero skip |
| Selezione slow | 0/18 casi DINO marcati prima della modifica | Esattamente 18 casi esclusi, due controlli cache mantenuti; questi ultimi 2 passed, 18 deselected in 0.11s |

I processi GUI usano soltanto `.env` sintetiche in directory temporanee. Le due
directory temporanee iniziali sono state spostate sotto `.tritech/local/` dopo
verifica dei percorsi; nessun file dell'utente eliminato. Il primo check rapido
nel sandbox ha incontrato errori di setup nella directory Temp e un blocco dei
socket locali; è stato interrotto, senza attribuirgli un successo.

La prima verifica completa ha dato **1 failed, 415 passed, 3 warnings in 147.51s**:
`tests/test_training_dataset.py::test_supervises_verified_validation_date_without_ocr_typo`.
Il codice di training era in modifica concorrente. Senza modifiche da questa attività,
la riesecuzione del solo test sul sorgente corrente ha dato **1 passed in 1.81s**.
Il log iniziale è preservato come
[pytest-full-first.txt](checks/2026-10-16-phases-3-4/pytest-full-first.txt).

Le verifiche finali, fuori dal sandbox per il limite dei socket locali, usano Python
3.13.14 della venv, directory temporanee distinte sotto `.tritech/local/` e thread
OpenBLAS/OMP/MKL limitati a uno:

| Comando | Risultato finale |
|---|---|
| `.venv/Scripts/python.exe -u -m pytest tests -q --basetemp .tritech/local/pytest-phase34-full-final-20261016-01` | **429 passed, 3 warnings in 103.97s**, exit 0 |
| `.venv/Scripts/python.exe -u tools/check.py -q --basetemp .tritech/local/pytest-phase34-fast-final-20261016-01` | **411 passed, 18 deselected in 71.46s**, exit 0 |

Log: [suite completa](checks/2026-10-16-phases-3-4/pytest-full.txt),
[check rapido](checks/2026-10-16-phases-3-4/pytest-fast.txt). I tre avvisi sono quelli
di xFormers non disponibile per DINOv2. Nessun test saltato, fallito o in errore
nella suite finale. Il check rapido mantiene i due casi puri della cache; il tempo
misurato include anche import SDK, processi GUI e test del training concorrente,
e non soddisfa un obiettivo di due secondi per l'intera selezione.

I 37 file di test e sorgenti training osservati prima delle due esecuzioni finali
sono rimasti invariati fino al controllo successivo: nessun hash cambiato o file
aggiunto. Evidenza in
[test-input-stability.json](checks/2026-10-16-phases-3-4/test-input-stability.json).
Il training resta fuori dal perimetro della revisione e delle modifiche qui descritte.

Revisione indipendente dei contratti integrati, separata dall'implementazione GUI:
nessun finding concreto di correttezza o sicurezza. Controllati **254 collegamenti
locali, zero rotti**; `git diff --check` exit 0. La guida include anche la distinzione
pagina/gruppo nel glossario e nella panoramica, e riferimenti CLI aggiornati a funzioni
al posto delle vecchie righe. Gli ADR accettati precedenti non sono stati riscritti.

Manifest del candidato, revisione e hash:
[snapshot.json](checks/2026-10-16-phases-3-4/snapshot.json). Lo stato condiviso X-ray
viene aggiornato preservando il record della revisione ground truth e gli altri
aggiornamenti concorrenti. Le modifiche delle Fasi 3–4 restano nel working tree;
il commit richiesto delle Fasi 1–2 è `3be17a8`. Le loro verifiche storiche restano
nel report 11. Nessuna nuova estrazione VLM o sessione di cattura bancaria eseguita.
