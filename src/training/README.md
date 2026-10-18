# Addestramento LiLT dal ground truth revisionato

Questo percorso prepara e addestra il riconoscitore locale dei campi BPER a partire
dai valori approvati nella revisione Excel 3.1. Riutilizza i risultati RapidOCR
salvati: non esegue chiamate a Gemini e non modifica gli screenshot o l'Excel.
Il modello prodotto riconosce il ruolo delle parole OCR; il testo viene ricostruito
dalle parole originali. Gli errori di lettura dell'OCR restano quindi visibili.

## Preparazione

Dalla radice del repository, nell'ambiente con le dipendenze di `requirements.txt`:

```powershell
$env:PYTHONPATH = 'src'
python -m training.dataset --workbook data/revisione/revisione/Revisione_ground_truth_v3_1.xlsx --screenshots data/pratiche --ocr data/training/ocr-cache/rapid_v6_small_1x.json --output data/training/ground-truth-v3.1
```

La cache OCR è quella da cui è costruito il bundle (SHA-256 `e261c05b…`); il
`manifest.json` del bundle conserva il percorso in cui si trovava prima del
riordino del repository. Una ricostruzione riproduce etichette, testi, allineamenti
e copertura, ma non l'impronta di `examples.json` byte per byte: alcune coordinate
orizzontali delle parole differiscono per arrotondamenti numerici.

`examples.json` contiene parole, riquadri, etichette e valori attesi; `roles.json`
stabilisce l'ordine delle classi. `ground_truth.csv` conserva tutti i valori
revisionati, comprese le assenze. `alignment_report.csv` descrive quali osservazioni
si possono usare come supervisione; `coverage.json` distingue i campi presenti nei
tre insiemi. Il manifest registra sorgenti, impronte dei dati e controlli.

Le 12 pratiche sono separate in 8 per addestramento, 2 per scelta del modello e 2
per prova finale. Anche gli NDG dei soggetti e le immagini identiche devono restare
nello stesso insieme. I campi privi di esempi positivi nelle pratiche di prova sono
elencati esplicitamente: per questi campi non si può dichiarare generalizzazione.

La supervisione usa il testo approvato per individuare parole realmente presenti
nell'OCR. Non riscrive le parole lette male. Una parola incerta riceve `IGNORE` e
non contribuisce alla funzione di perdita; quando un campo non è risolto, il
mascheramento è circoscritto alla regione candidata del campo anziché all'intera
schermata. Nelle note, nella data di validazione, nella scadenza e nel tipo
operazione si possono supervisionare le singole parole esatte anche quando un'altra
parola della cella è errata. Le celle multi-riga sono ordinate per righe visive
interne alla cella. Il confronto finale resta sul valore completo. `N/D` è testo
visibile; una cella effettivamente vuota rappresenta un'assenza.

## Confronto dei motori OCR

`training.ocr_runner` legge tutte le schermate revisionate con una configurazione
dello Stadio A del piano (`A0`..`A4`) e un profilo CPU (`pc4`: 4 thread, `vdi2`: 2).
Richiede un ambiente separato con RapidOCR, descritto in `requirements-ocr.txt`:

```powershell
uv venv .venv-ocr --python 3.13
uv pip install --python .venv-ocr/Scripts/python.exe -r requirements-ocr.txt
cd src
../.venv-ocr/Scripts/python.exe -m training.ocr_runner run --config A1 --profile pc4 --examples ../data/training/ground-truth-v3.1/examples.json --screenshots ../data --out CARTELLA-NUOVA
../.venv/Scripts/python.exe -m training.ocr_runner report --run CARTELLA-NUOVA --workbook ../data/revisione/revisione/Revisione_ground_truth_v3_1.xlsx --screenshots ../data
```

Ogni schermata viene salvata appena letta: una prova interrotta riprende dalle
schermate mancanti, e una schermata in errore non ferma le altre. `cache.json`
nasce solo quando tutte le schermate hanno un risultato, con l'impronta registrata
nel manifest insieme a modelli, versioni, thread e tempi. Una cartella non accetta
un'altra configurazione o altri modelli. `report` costruisce il dataset derivato e
scrive in `ocr_selection.json` disponibilità OCR, NDG dei soggetti, rapporti e
letture 6→8 per pratica, solo per addestramento e validazione: il test storico non
partecipa alla scelta del motore. Il dataset derivato serve alle misure e non
sostituisce il bundle sigillato.

Le configurazioni lente si possono leggere su Modal, in contenitori solo CPU con 4
core e gli stessi pin e file modello di `.venv-ocr`:

```powershell
cd src
env -u HTTPS_PROXY -u HTTP_PROXY ../.venv/Scripts/python.exe -m modal run --detach -m training.modal_ocr --out-dir PERCORSO-ASSOLUTO-NUOVO --configs A1,A2,A3
```

Ogni gruppo di schermate (`--shard-size`, 8 per default; intere per le configurazioni
in `--whole`) è una normale prova di `run_ocr()`. In locale `merge_runs()` le unisce in
`<config>/run` solo se sono tutte complete, con la stessa configurazione e gli stessi
modelli, e coprono ogni schermata una sola volta. `report` legge poi `<config>/run`
come una prova locale. Il pannello dei costi (`--panel`, vuoto per saltarlo) legge le
stesse schermate con tutte le configurazioni in un solo contenitore, così i tempi si
confrontano sulla stessa macchina. Su Modal vanno le schermate revisionate; workbook ed
etichette restano in locale. Se il processo locale si ferma, l'app staccata continua:
`--collect` con la stessa cartella scarica quello che è finito.

## Addestramento e modello locale

L'addestramento parte dal modello pubblico `nielsr/lilt-xlm-roberta-base`, con una
nuova testa di classificazione. Non riutilizza i precedenti pesi BPER, la cui storia
di addestramento potrebbe sovrapporsi alle pratiche di prova. Le varianti geometriche
e numeriche si applicano solo a copie dell'insieme di addestramento.

Con Modal configurato sull'account che possiede il volume `bper-lilt-spike`:

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = 'src'
modal run -m training.modal_train --data-dir D:/Projects/poc-data-extraction/data/training/ground-truth-v3.1 --out-dir D:/Projects/poc-data-extraction/data/training/runs/NOME-NUOVO
```

La cartella di uscita deve essere nuova. L'esecuzione è limitata a un container L4,
30 minuti, massimo 16 epoche (8 per default) e nessun tentativo automatico. Senza
miglioramento in validazione si ferma dopo `--patience` epoche (2 per default, al
massimo 4). Il servizio riceve le
parole OCR, le coordinate, le etichette e i manifest; gli screenshot e l'Excel
rimangono locali. I risultati remoti hanno un nome derivato dall'esperimento e non
sovrascrivono i modelli precedenti.

La selezione dell'epoca usa l'accuratezza sul valore completo dei campi di
validazione (con spareggio sulla F1 delle parole non-nota e poi sulla F1 micro
complessiva); il test viene eseguito dopo la selezione. La suddivisione in finestre
di 512 sottotoken preserva intero il blocco della tabella `FIDI` insieme alla sua
intestazione. La cartella `cpu_model` scaricata contiene pesi e tokenizer
caricabili con Transformers su CPU, insieme a etichette, split e manifest. Le
predizioni riportano un ruolo per ogni parola OCR. `training.evaluation` ricostruisce
i 45 campi e misura corretto, errato, mancante, allucinato e assenza corretta sul
ground truth completo. I campi della tabella `FIDI` vengono dalla sola riga più in
alto, quella del primo numero di fido predetto (ADR 0023). Il confronto conserva cifre e punteggiatura, tollerando
solo differenze di rappresentazione documentate nei test. Per un estrattore che
produce direttamente i valori dei campi, `evaluate_field_values()` applica gli
stessi confronti e riepiloghi a `{"fields": {campo: testo o None}, "abstained":
[campi]}` per schermata, conta le astensioni e segnala con `complete` una prova
priva dell'esito di qualche schermata; la F1 delle parole non si applica.

Questo percorso è un esperimento offline. L'adozione nel flusso di cattura
dell'edge-agent richiede una modifica successiva e una verifica su acquisizioni reali.
I risultati delle esecuzioni sono conservati accanto ai run in `data/training/`,
separati da questa guida.
