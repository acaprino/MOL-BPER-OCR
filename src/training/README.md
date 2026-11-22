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
python -m training.dataset --workbook data/revisione/riscontro-2026-10-07/Revisione_ground_truth_v3_1.xlsx --screenshots data/pratiche --ocr data/training/ocr-cache/rapid_v6_small_1x.json --output data/training/ground-truth-v3.1
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

### Più lotti: `ground-truth-v3.2`

La versione 3.2 unisce il riscontro v3.1 e il lotto 2026-08-21, revisionato per
trascrizione (`Trascrizione` + `Esito`) e assegnato ai gruppi G8 da
`data/revisione/lotto-2026-08-21/assegnazione_g8.py`. Ogni lotto si passa con
`--lot WORKBOOK ASSEGNAZIONE CORREZIONI OCR` (`-` dove un file manca):

```powershell
cd src
../.venv/Scripts/python.exe -m training.dataset --workbook ../data/revisione/riscontro-2026-10-07/Revisione_ground_truth_v3_1.xlsx --screenshots ../data/pratiche --ocr ../data/training/ocr-runs/A1/cache.json --output ../data/training/ground-truth-v3.2 --lot ../data/revisione/lotto-2026-08-21/Revisione_10_pratiche_agosto_v1.0.xlsx ../data/revisione/lotto-2026-08-21/g8_assegnazione.json ../data/revisione/lotto-2026-08-21/correzioni.json ../data/training/validazione-estesa/ocr-A1/cache.json
../.venv/Scripts/python.exe -m training.truth_export --bundle ../data/training/ground-truth-v3.2 --out ../data/training/ground-truth-v3.2/ground_truth.xlsx
```

La verità è un database di tre tabelle, derivate e mai modificate a mano:
`practices.csv` (pratica, lotto, gruppo), `screens.csv` (schermata, percorso,
impronte SHA-256 del file e dei pixel, dimensioni, se ha un esempio) e
`ground_truth.csv` (schermata, campo, valore, esito, stato di revisione, lotto,
gruppo, riga Excel di origine, correzione applicata con il valore originale). Gli
esiti sono quelli della trascrizione: `TRASCRITTO`, `VUOTO`, `NON VISIBILE`,
`PARZIALE`, `NON LEGGIBILE`; per il workbook v3.1, che non li distingue, una cella
vuota vale `VUOTO`. `truth_export` scrive le tre tabelle in un solo workbook
(fogli Info, Pratiche, Schermate, Valori), con ogni testo salvato come testo.

Gli esempi esistono solo dove l'OCR è ammesso: gli split v3.1 e la validazione
estesa G8 (`val_ext`, 5 pratiche). `PARZIALE` e `NON LEGGIBILE` restano nella
verità ma non diventano un bersaglio. Il gruppo di conferma (`conferma`, 5
pratiche) è sigillato: nel bundle ha valori e impronte, nessun esempio, e una sua
schermata in una cache OCR fa fallire la costruzione. Le identità in comune con
v3.1 (una pratica condivide l'NDG del Fondo di garanzia per la prima casa) sono
registrate in `leakage_audit.recorded_overlaps` e non escludono nessuna pratica;
fra validazione estesa e conferma non ne è ammessa nessuna (`truth_isolation`).
La versione la decide la composizione dei lotti (`DATASET_VERSIONS`) e la
convalida di `validate_reviewed_dataset()` confronta conteggi e split con il
contratto della versione dichiarata: una cartella rinominata non è una versione.

### Ogni pratica ha un ruolo: `ground-truth-v3.4`

Addestramento 18 (train, la pratica di riferimento `51350695`, validazione estesa con `--also-train`), controllo 2,
test 13 (test storico e conferma sigillata): colonna `Ruolo` di `practices.csv`, ADR 0027. La
costruzione della versione più recente rifiuta una cartella di `data/pratiche` senza ruolo. Il
lotto `riferimento-2025-09-09` è un CSV (`read_reference_truth()`): si passa con `--lots` come gli
altri, con `dati.csv`, `g8_assegnazione.json`, `fotogrammi.json` e la sua cache OCR.

### Un foglio per pratica: `ground-truth-v3.3`

Il lotto 2026-11-05 è consegnato con un foglio per pratica e un valore per pagina, senza
esiti: `training.practice_sheets` lo legge, trasforma date e importi in testo come sullo
schermo, tratta `vuoto` come assenza e tiene nella verità, senza chiave di campo, i valori
fuori vocabolario. `correzioni.json` dice cosa mostra ogni schermata delle pratiche di
validazione estesa (`non_visibili`, `parziali`, `tooltip`) e corregge i valori controllati
contro lo schermo; una pratica sigillata non ha voce e tiene i valori sulla prima schermata
di ogni pagina. Il lettore è scelto dalla forma del workbook, la versione dalla composizione
dei lotti.

Tutti i passaggi girano su Modal, perché questo PC resta spesso senza memoria. Da `src/`,
con il proxy tolto (`env -u HTTPS_PROXY -u HTTP_PROXY`), dopo aver copiato i PNG in
`data/pratiche/<pratica>/` con i nomi di `screen_name()`:

```powershell
../.venv/Scripts/python.exe -m modal run -m training.modal_lot --lot lotto-2026-11-05 --workbook ABS --zips ABS,ABS --truth-dir ABS/ground-truth-v3.2 --previous ABS/lotto-2026-08-21/g8_assegnazione.json --out ABS/g8_assegnazione.json
../.venv/Scripts/python.exe -m modal run --detach -m training.modal_ocr --out-dir ABS-NUOVO --configs A1 --panel "" --assignment ABS/g8_assegnazione.json --practices P1,P2
../.venv/Scripts/python.exe -m modal run -m training.modal_bundle --workbook ABS --ocr ABS --lots "WORKBOOK,ASSEGNAZIONE,CORREZIONI,OCR;..." --out ABS-NUOVO --model model_v3_1_33da126207bf6876
../.venv/Scripts/python.exe -m training.truth_export --bundle ABS-NUOVO --out ../data/pratiche/pratiche.xlsx --per-practice
```

L'ultimo comando rigenera l'archivio delle pratiche, `data/pratiche/pratiche.xlsx`, dalla nuova verità: un foglio
`Indice` con lotto, gruppo e ruolo e un foglio per pratica con i valori corretti.

`modal_lot` applica le regole del piano §5.4 e scrive il manifest; `modal_ocr` rifiuta una
pratica fuori dalla validazione estesa; `modal_bundle` costruisce il bundle e misura il
modello sul volume, sulla sola validazione estesa. L'NDG del Fondo di garanzia non è
un'identità in nessun controllo (`INSTITUTIONAL_NDGS`, ADR 0024). Per i test,
dalla radice del repository: `modal run tools/modal_tests.py --args "tests -q -m 'not slow'"`.

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
../.venv/Scripts/python.exe -m training.ocr_runner report --run CARTELLA-NUOVA --workbook ../data/revisione/riscontro-2026-10-07/Revisione_ground_truth_v3_1.xlsx --screenshots ../data
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
di addestramento potrebbe sovrapporsi alle pratiche di prova. Le varianti si applicano
solo a copie dell'insieme di addestramento: con `--variants 3` una copia con piccoli
spostamenti e cifre cambiate, e due con la pagina inquadrata diversamente (tagliata o più
alta, `_reframe()`), perché LiLT legge le posizioni rispetto all'immagine intera e le
schermate di addestramento hanno quasi tutte la stessa inquadratura.

Con Modal configurato sull'account che possiede il volume `bper-lilt-spike`:

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = 'src'
modal run -m training.modal_train --data-dir D:/Projects/poc-data-extraction/data/training/ground-truth-v3.1 --out-dir D:/Projects/poc-data-extraction/data/training/runs/NOME-NUOVO
```

La cartella di uscita deve essere nuova. L'esecuzione è limitata a un container L4,
45 minuti, massimo 16 epoche (8 per default) e nessun tentativo automatico. Senza
miglioramento in validazione si ferma dopo `--patience` epoche (2 per default, al
massimo 4). Il servizio riceve le
parole OCR, le coordinate, le etichette e i manifest; gli screenshot e l'Excel
rimangono locali. I risultati remoti hanno un nome derivato dall'esperimento e non
sovrascrivono i modelli precedenti.

La selezione dell'epoca usa l'accuratezza sul valore completo dei campi di
validazione (con spareggio sulla F1 delle parole non-nota e poi sulla F1 micro
complessiva). Il test storico si esegue solo con `--final-test`, su un candidato
congelato; ogni run misura invece la validazione estesa (`extended_predictions.json`), e
`--also-train` sposta pratiche di validazione estesa nell'addestramento per quel run.
La suddivisione in finestre
di 512 sottotoken preserva intero il blocco della tabella `FIDI` insieme alla sua
intestazione. La cartella `cpu_model` scaricata (`--no-download-weights` lascia i pesi sul volume) contiene pesi e tokenizer
caricabili con Transformers su CPU, insieme a etichette, split e manifest. Le
predizioni riportano un ruolo per ogni parola OCR. `training.evaluation` ricostruisce
i 45 campi e misura corretto, errato, mancante, allucinato e assenza corretta sul
ground truth completo. I campi della tabella `FIDI` vengono dalla sola riga più in
alto, quella del primo numero di fido predetto (ADR 0023), letta per colonna sotto la testata della tabella (ADR 0026). Anche i Soggetti si leggono
per colonna, e nell'Elenco una parola resta nella colonna del suo ruolo (ADR 0028). Il confronto conserva cifre e punteggiatura, tollerando
solo differenze di rappresentazione documentate nei test. Per un estrattore che
produce direttamente i valori dei campi, `evaluate_field_values()` applica gli
stessi confronti e riepiloghi a `{"fields": {campo: testo o None}, "abstained":
[campi]}` per schermata, conta le astensioni e segnala con `complete` una prova
priva dell'esito di qualche schermata; la F1 delle parole non si applica.

Questo percorso è un esperimento offline. L'adozione nel flusso di cattura
dell'edge-agent richiede una modifica successiva e una verifica su acquisizioni reali.
I risultati delle esecuzioni sono conservati accanto ai run in `data/training/`,
separati da questa guida.
