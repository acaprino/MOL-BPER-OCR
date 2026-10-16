# Aggiornamento incrementale 2026-10-16 — hardening, Fasi 1 e 2

Aggiornamento mirato sopra il run `poc-data-extraction-20260912-175144` e gli incrementi
09–10; non è una nuova analisi completa. Riferimento: branch `develop`, HEAD
`7826bdb9469133c7a3d3b20197a69c519711c98a`, più le modifiche non committate descritte qui.
I documenti 01–08 e i run storici conservano il proprio snapshot: per gli argomenti
elencati sotto, questo aggiornamento sostituisce le descrizioni precedenti.

Lo spostamento già staged da `.codebase-xray/` a `.tritech/codebase-xray/` e la modifica
preesistente a `.gitignore` sono lavoro dell'utente, preservato. I rimandi assoluti
al vecchio percorso nei run storici non vengono reinterpretati come verifiche odierne.

## Perimetro e decisioni di esecuzione

L'allegato propone quattro fasi e conclude proponendo l'implementazione delle prime
due. Questa modifica realizza le Fasi 1–2; page/export mapping, filtro delle righe
allucinate, GUI, rimozione di codice morto e infrastruttura fast/CI restano Fasi 3–4.

- Il retry di `creazione` richiede sia il mapping sia il prompt HEADER: il testo
  precedente chiedeva esplicitamente solo otto campi, senza la data di creazione.
- `normalize_ndg()` mantiene la semantica già usata dal consolidamento; viene spostata,
  non riscritta. `n_fido` e gli importi conservano il confronto numerico precedente.
- Il flatten usa `merge_field_sources()` / `pick_best()` anche quando un valore scalare
  e una riga di tabella sono in conflitto. Un valore presente batte un nullo; altrimenti
  vince la confidenza maggiore, con precedenza al valore corrente in caso di parità.
- L'origine delle tabelle vive in un dizionario locale alla singola estrazione, passato
  ai helper tramite keyword opzionale. Nessuno stato condiviso sulla pipeline e nessun
  nuovo metadato `_table_sources` nell'output. Le regole di accettazione delle tabelle
  restano quelle precedenti, comprese le protezioni fuori calibrazione.
- I test di caratterizzazione della Fase 2 proteggono comportamenti già corretti; non
  si introducono modifiche funzionali artificiali per ottenere un primo risultato rosso.
  La loro sensibilità viene verificata separatamente con mutazioni isolate in memoria.

## Struttura e interfacce aggiornate

| File / riferimento corrente | Contratto verificato |
|---|---|
| `extraction/config.py:105`, `:122` | `creazione` appartiene a HEADER; i cinque tooltip appartengono a `UNRETRIED_FIELDS`. Ogni campo ha una sola politica di retry. |
| `prompts/extraction_retry_header.json` | La lista esplicita e la descrizione includono nove campi, compreso `creazione`. Catalogo e placeholder restano invariati. |
| `extraction/normalization.py:40` | Unico owner di `normalize_ndg()`: caratteri alfanumerici in maiuscolo, zeri iniziali eliminati solo per identificativi interamente numerici, `None` per valori nullish. |
| `extraction/normalization.py:150`, `:218` | `classify_field()` usa l'identità per `ndg`/`ndg_1..4`; `dataset_mismatch_guard()` usa lo stesso confronto anche quando legge l'NDG dalla tabella soggetti. |
| `edge-agent/practice_consolidation.py` | Importa il normalizzatore condiviso; resta possibile importare il simbolo dal modulo precedente. Consolidamento invariato. |
| `extraction/pipeline.py:181`, `:209`, `:268`, `:304` | Le tabelle adottate dal retry ricevono l'origine effettiva; il flatten aggiorna valore e fonte insieme, preservando gli scalari migliori. I nuovi parametri `table_sources` sono opzionali. |
| `tests/test_domain_vocabulary.py` | Uguaglianza fra campi, definizioni canoniche e valori CSV; copertura esclusiva retry/esclusioni; crop e prompt presenti per ciascuna area. |
| `tests/test_normalization.py` | Identità numerica e alfanumerica, collisioni da arrotondamento/suffisso, null e guard; confronti quantitativi preservati. |
| `tests/test_pipeline_postprocessing.py` | Gate e hint anchor, stop precoce, precedenza anchor, tipo main/retry, coerenza tooltip e preservazione dei valori, merge e fonte del flatten, tabelle fuori calibrazione. |

Queste righe aggiornano gli argomenti in `01-structure.md:174,438`,
`02-interfaces.md:140,693,736` e `04-semantics.md:83,106–107`. L'assenza di
`FIELD_RETRY_MAP` resta vera: il consumer itera `AREA_TO_FIELDS` direttamente.

## Flussi aggiornati

Il flusso in `03-flows.md:23` diventa: anchor → main → merge anchor → normalizzazione
tipo → retry → coerenza → flatten con `pick_best()` e fonte della tabella vincente →
campi canonici → stato. La precedenza delle fasi, il budget e il conteggio dei costi
non cambiano. La canonizzazione legge quindi il valore sopravvissuto al merge.

Nel flusso di consolidamento (`03-flows.md:55`), l'identità NDG proviene da
`extraction.normalization.normalize_ndg`, la stessa funzione usata dalla valutazione.
`12.345` e `0012345` corrispondono a `12345`; `12345/A` resta distinto da `12345/B`
e da `12345`. Gli zeri iniziali di `0012345/A` vengono conservati.

`08-interconnect-map.md` resta valido per la partizione unica; il cambiamento di owner
è interno alla partizione e non aggiunge sistemi o chiamate esterne.

## Riconciliazione dei finding

Le righe seguenti sostituiscono, nel solo perimetro verificato, le corrispondenti
conclusioni in `05-risks.md` e `07-final-report.md:218–239`.

| Finding | Stato dopo la modifica |
|---|---|
| XQ-A01 | Risolto per la completezza del vocabolario dichiarato: i test impediscono omissioni, assegnazioni multiple e mapping canonici/CSV incompleti; `creazione` viene ritentato e i tooltip sono esclusioni esplicite. Non sono state aggiunte guardie a import-time né verifiche semantiche di pagina/export. |
| XQ-R08 | Parzialmente risolto: confronti NDG e mismatch guard corretti; `n_fido` resta intenzionalmente nel ramo quantitativo e richiede una decisione separata. |
| XQ-D01 | Risolto nel perimetro gate, merge, tipo, coerenza e flatten: test comportamentali verdi e nove mutazioni isolate rilevate. Esito della verifica riportato sotto, distinto dalla presenza dei test nei percorsi storici. |
| XQ-D04 | Parzialmente risolto: flatten preserva il vincitore e la sua fonte. Restano l'inizializzazione CONTENT_MAIN per campi assenti e le riparazioni di coerenza senza origine distinta. |

Non si dichiara risolto il rischio di righe BODY allucinate: la selezione delle tabelle
non riceve nuovi filtri di confidenza/identità in questa modifica (Fase 3.2).

## Documentazione aggiornata

AGENTS/CLAUDE e le sezioni funzionali di `docs/02-features.md`, `04-architecture.md`,
`05-workflows.md`, `06-data-model.md`, `07-getting-started.md`, `08-open-questions.md`
e `how-it-works.md` descrivono la nuova copertura retry, l'owner del normalizzatore,
il merge del flatten e i residui di provenienza. ADR 0017 registra l'identità condivisa;
ADR 0018 registra merge e fonte dei soggetti. Gli ADR accettati precedenti non cambiano.

Questo aggiorna gli argomenti di `06-documentation.md:19,22,30,44–45,53`:
il gap di copertura core viene colmato; il limite di provenienza è ridotto, non chiuso;
l'assenza di `evidence_text` nei candidati prodotti dal flatten resta un limite distinto.
Il conteggio storico dei test non è ripubblicato come dato corrente nelle guide utente.

## Verifiche della modifica

Evidenza RED prima delle modifiche funzionali:

| Comando | Risultato osservato |
|---|---|
| `.venv/Scripts/python.exe -m pytest tests/test_domain_vocabulary.py tests/test_pipeline_retry.py -q` | 3 failed, 6 passed: copertura di retry incompleta, esclusioni non dichiarate, `creazione` non innesca HEADER. |
| `.venv/Scripts/python.exe -m pytest tests/test_normalization.py -q` | 36 failed, 39 passed: NDG con punti/suffissi e collisioni nei confronti. |
| `.venv/Scripts/python.exe -m pytest tests/test_pipeline_postprocessing.py -q` | 12 failed, 19 passed: scalari cancellati/sovrascritti e fonte della tabella di retry persa. I 19 test già verdi sono caratterizzazioni. |

Evidenza GREEN mirata: vocabolario/retry/catalogo **41 passed in 9.75s**;
normalizzazione/consolidamento **91 passed in 9.03s**. Il primo tentativo combinato
post-processing/crop/retry ha prodotto **42 passed, 5 errors in 12.17s**: tutti e cinque
gli errori erano nel setup `tmp_path`, impossibilitato a creare directory nel Temp del
sandbox. Anche il primo controllo catalogo ha avuto 24 errori di setup analoghi, poi
risolti usando `--basetemp` nel workspace. Nessuna asserzione è stata allentata.

La prima suite completa è stata interrotta senza riepilogo; il secondo tentativo
diagnostico ha individuato un blocco nel sandbox: `ChatGoogleGenerativeAI.__del__()`
crea un event loop e resta in `socket._fallback_socketpair().accept()`. Il traceback
è conservato in `checks/2026-10-16-phases-1-2/pytest-sandbox-blocked.txt`; il primo
output parziale è `pytest-interrupted.txt`. Nessuna modifica al prodotto o ai test
è stata introdotta per aggirare quel blocco.

La suite completa è stata quindi eseguita fuori dal sandbox con lo stesso interprete,
directory temporanea nel workspace e `OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1`:

```text
.venv/Scripts/python.exe -u -m pytest tests -q --basetemp .tritech/local/pytest-phase12-full-20261016-03
303 passed, 3 warnings in 40.09s
exit code: 0
```

I tre avvisi riguardano xFormers non disponibile per DINOv2 (SwiGLU, Attention,
Block). Nessun test fallito, saltato o in errore nella verifica finale. Log integrale:
[pytest.txt](checks/2026-10-16-phases-1-2/pytest.txt).

La verifica con mutazioni isolate, senza scritture nel sorgente applicativo, ha dato
baseline **31 passed** e **9/9 mutazioni rilevate** tramite 14 asserzioni fallite,
exit 1 atteso e zero errori di setup. Copre entrambi i lati della soglia anchor,
early exit, priorità anchor, tipo main/retry, due regole di coerenza e protezione delle
tabelle fuori calibrazione. L'hash del sorgente è rimasto invariato; procedura e
risultati sono in [mutation_check.py](checks/2026-10-16-phases-1-2/mutation_check.py)
e [mutations.json](checks/2026-10-16-phases-1-2/mutations.json). Il primo tentativo
parallelo ha esaurito memoria OpenBLAS; i suoi esiti sono preservati come storia,
non contati come mutazioni rilevate. La verifica sequenziale con thread numerici
limitati ha completato tutti i casi.

Revisione indipendente di codice e test integrati: nessun finding di correttezza
azionabile. Controllo della documentazione: **131 link locali, zero rotti**.
`git diff --check`: exit 0. Manifest con revisione, file coperti e hash:
[snapshot.json](checks/2026-10-16-phases-1-2/snapshot.json).

Non sono state eseguite nuove estrazioni su provider reali né una sessione GUI bancaria;
queste verifiche non misurano accuratezza o costo sui dati reali. I precedenti 173/190
test dei run storici non sono evidenza odierna. Nessun commit o staging effettuato.
