# 0032 — `data/` contiene un solo archivio pulito, `data/dataset`

- Data: 2026-11-22
- Stato: Accettato. Supera in parte l'ADR 0029: l'archivio delle pratiche e la verità della CLI passano da `data/pratiche` e `pratiche.xlsx` a `data/dataset`.

## Contesto

`data/` portava la storia di come le pratiche erano arrivate: `pratiche/` e `revisione/` con lotti
dai nomi diversi (`riscontro-2026-10-07`, `lotto-…`, `riferimento-…`), le verità `ground-truth-v3.1`
… `v3.5`, le letture OCR e i run dei modelli, uno spike archiviato. Le schermate avevano due schemi
di nome (`Elenco_dx`, `Elenco_tooltip1` e `Elenco2`, `GestioneFidi3`) e i dati di una stessa consegna
stavano in tre cartelle. Il responsabile del progetto ha chiesto il 2026-11-22 di dimenticare il
passato e di ripartire da zero: un archivio pulito di pratiche, come se il modello si addestrasse
ex novo, senza lasciare accanto quello vecchio.

## Decisione

- `data/` contiene solo `dataset/` e il suo `README.md`:
  - `pratiche/<id>/<pagina>-<NN>.png`: le 240 schermate in perimetro delle 33 pratiche, con nomi uniformi
    (`elenco`, `soggetti`, `gestione-fidi`, `note`, `scheda-privati`; base per prima, due cifre).
    Le 22 schermate off-topic non entrano.
  - `schermate.csv`, `valori.csv`, `pratiche.csv`: schermata (pagina, numero, variante, impronta,
    dimensioni), verità (2.051 valori con campo, chiave canonica ed esito) e ruolo di ogni pratica.
- Non ci sono lotti, gruppi, versioni, OCR, run né modelli: si rigenerano dall'archivio.
- Il ruolo di ogni pratica (addestramento 18, controllo 2, test 13, ADR 0027) è conservato; lotto e
  gruppo no.
- `tools/build_dataset_archive.py` ha prodotto l'archivio dalla v3.5 e dal vecchio archivio delle
  pratiche, verificando l'impronta di ogni immagine prima di scrivere. Rifiuta una destinazione
  non vuota.
- `resolve_ground_truth()` legge i valori di una cartella da `dati.csv` se c'è, altrimenti da
  `valori.csv` due livelli sopra (`load_dataset_truth()`, chiavi come `elenco-01`); resta, per ultimo,
  il `pratiche.xlsx` accanto alla cartella. L'input predefinito della CLI è
  `data/dataset/pratiche/51350695`.
- `dati.csv` e `fotogrammi.json` della pratica di riferimento (`screen 1..9`), che il simulatore e i
  test del catalogo di pagine leggono, stanno in `tools/reference/`.

## `src/training`

Il pacchetto costruisce ora il dataset dall'archivio: `read_archive()` legge e controlla le tre
tabelle, `ocr_screens()` dice quali schermate leggere, `build_dataset()` allinea i valori alle
parole e sigilla il bundle. Il ruolo di una pratica è il suo split (`addestramento` è `train`,
`controllo` è `val`, `test` è `test`) e le pratiche di test si leggono solo con `include_test`.
Sono usciti i moduli che costruivano da workbook, lotti e assegnazione ai gruppi (`g8_assignment`,
`practice_sheets`, `truth_export`, `modal_lot`, `modal_bundle`), le versioni `ground-truth-v3.x`
e la validazione estesa (`also_train`, lo split `val_ext`); `validate_reviewed_dataset()` accetta
il dataset dell'archivio e ne controlla manifest, conteggi e impronta del contenuto.

## Conseguenze e verifica

- Il vecchio albero resta nella storia git: `git checkout b2d4b80 -- data` lo ripristina. I due
  `model.safetensors` (1,1 GB ciascuno), che git non ha mai avuto, sono stati spostati in
  una cartella fuori dal repository.
- L'archivio ha le stesse 33 pratiche, 240 schermate e 2.051 valori della v3.5, ogni immagine con la
  stessa impronta e ogni valore su una schermata esistente.
- Per `51350695` la CLI carica dalle nuove tabelle le stesse 77 terne (schermata, campo, valore) del
  vecchio foglio, a parte la chiave della schermata (`Elenco_dx` diventa `elenco-02`); le nove
  schermate di riferimento hanno gli stessi byte.
- Suite completa (compresi i 18 test del classificatore DINOv2 che leggono le schermate di
  `51350695`) verde; test nuovi in `tests/test_dataset_archive.py`, `tests/test_practice_truth.py` e
  `tests/test_training_dataset.py`.
- Il dataset ricostruito dall'archivio con le vecchie letture OCR di 149 schermate di addestramento e
  controllo (rinominate) dà 147 esempi identici a quelli della v3.5 per valori, etichette, esito degli
  allineamenti e impronte; negli altri 2 una parola è spostata fino a 3 px. L'audit degli split passa.
- Non verificato in locale: i test di browser del simulatore (`tests/browser`); i loro percorsi sono
  stati aggiornati ma non eseguiti.
