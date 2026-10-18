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
30 minuti, massimo 8 epoche e nessun tentativo automatico. Il servizio riceve le
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
ground truth completo. Il confronto conserva cifre e punteggiatura, tollerando
solo differenze di rappresentazione documentate nei test.

Questo percorso è un esperimento offline. L'adozione nel flusso di cattura
dell'edge-agent richiede una modifica successiva e una verifica su acquisizioni reali.
I risultati delle esecuzioni sono conservati nella X-ray, separati da questa guida.
