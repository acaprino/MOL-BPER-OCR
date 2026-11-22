# Addestramento LiLT da `data/dataset`

Questo percorso addestra il riconoscitore locale dei campi BPER a partire dall'archivio pulito `data/dataset` (schermate, valori corretti e ruolo di ogni pratica: vedi `data/README.md`). Legge le parole di una lettura OCR, non chiama Gemini e non modifica le schermate. Il modello riconosce il ruolo delle parole OCR; il testo viene ricostruito dalle parole originali, quindi gli errori di lettura dell'OCR restano visibili.

Il flusso, da `src/` con `PYTHONPATH=src`:

1. **OCR** delle schermate dell'archivio (`ocr_runner`, o `modal_ocr` su Modal).
2. **Dataset**: allineamento dei valori alle parole e sigillo (`training.dataset`).
3. **Addestramento** su Modal (`modal_train`) e **valutazione** locale (`evaluation`).

Ogni passo parte da `data/dataset` e da nient'altro: l'OCR, il dataset e i modelli si rigenerano, non si conservano come fonti.

## 1. OCR

`training.ocr_runner` legge le schermate con una configurazione dello Stadio A del piano (`A0`..`A4`) e un profilo CPU (`pc4`: 4 thread, `vdi2`: 2). Richiede un ambiente separato con RapidOCR, descritto in `requirements-ocr.txt`:

```powershell
uv venv .venv-ocr --python 3.13
uv pip install --python .venv-ocr/Scripts/python.exe -r requirements-ocr.txt
cd src
../.venv-ocr/Scripts/python.exe -m training.ocr_runner run --config A1 --profile pc4 --archive ../data/dataset --out CARTELLA-NUOVA
../.venv/Scripts/python.exe -m training.ocr_runner report --run CARTELLA-NUOVA --archive ../data/dataset
```

Le schermate lette sono quelle delle pratiche di addestramento e di controllo con almeno un valore da misurare. **Le pratiche di test non si leggono** (`--include-test` le aggiunge): si leggono una volta, quando il candidato è congelato.

Ogni schermata viene salvata appena letta: una prova interrotta riprende dalle schermate mancanti, e una schermata in errore non ferma le altre. `cache.json` nasce solo quando tutte le schermate hanno un risultato, con l'impronta registrata nel manifest insieme a modelli, versioni, thread e tempi. Una cartella non accetta un'altra configurazione o altri modelli. `report` costruisce il dataset derivato e scrive in `ocr_selection.json` disponibilità OCR, NDG dei soggetti, rapporti e letture 6→8 per pratica, per addestramento e controllo.

Le configurazioni lente si possono leggere su Modal, in contenitori solo CPU con 4 core e gli stessi pin e file modello di `.venv-ocr`:

```powershell
cd src
env -u HTTPS_PROXY -u HTTP_PROXY ../.venv/Scripts/python.exe -m modal run --detach -m training.modal_ocr --out-dir PERCORSO-ASSOLUTO-NUOVO --configs A1,A2,A3
```

Ogni gruppo di schermate (`--shard-size`, 8 per default; intere per le configurazioni in `--whole`) è una normale prova di `run_ocr()`. In locale `merge_runs()` le unisce in `<config>/run` solo se sono tutte complete, con la stessa configurazione e gli stessi modelli, e coprono ogni schermata una sola volta. Il pannello dei costi (`--panel`, vuoto per saltarlo) legge le stesse schermate con tutte le configurazioni in un solo contenitore, così i tempi si confrontano sulla stessa macchina. Su Modal vanno le schermate; i valori restano in locale. Se il processo locale si ferma, l'app staccata continua: `--collect` con la stessa cartella scarica quello che è finito.

## 2. Dataset

```powershell
cd src
../.venv/Scripts/python.exe -m training.dataset --archive ../data/dataset --ocr CARTELLA-NUOVA/cache.json --output CARTELLA-DATASET
```

Il ruolo di ogni pratica in `pratiche.csv` è il suo split: `addestramento` è `train`, `controllo` è `val`, `test` è `test` (ADR 0027). Ogni schermata ha un esempio solo se ha un valore da misurare (`TRASCRITTO`, `VUOTO`, `NON VISIBILE`) e una lettura OCR; `PARZIALE` e `DERIVATO` etichettano le parole che trovano senza essere un bersaglio, e i valori fuori dai 45 campi (`Chiave` vuota) non lo sono mai. Il tipo di pagina per l'allineamento si ricostruisce da pagina e variante di `schermate.csv`.

Il dataset rifiuta: un'immagine diversa dall'impronta registrata, un ruolo, una schermata o un campo sconosciuti, un esito che non va d'accordo col valore, un campo ripetuto, una lettura OCR di una schermata di test senza `--include-test`, una schermata da misurare senza lettura, e una pratica, un'immagine o un NDG di cliente che attraversano due split. L'NDG di un'istituzione (il Fondo di garanzia per la prima casa, `11153238`) non è un'identità (ADR 0024).

Escono `examples.json` (parole, riquadri, etichette, valori attesi), `roles.json` (ordine delle classi), `alignment_report.csv` (quali osservazioni si possono usare come supervisione), `coverage.json` e `manifest.json`, sigillato con l'impronta del contenuto.

## 3. Addestramento e modello locale

L'addestramento parte dal modello pubblico `nielsr/lilt-xlm-roberta-base`, con una nuova testa di classificazione. Non riutilizza pesi BPER precedenti. Le varianti si applicano solo a copie dell'insieme di addestramento: con `--variants 3` una copia con piccoli spostamenti e cifre cambiate, e due con la pagina inquadrata diversamente (tagliata o più alta, `_reframe()`), perché LiLT legge le posizioni rispetto all'immagine intera e le schermate di addestramento hanno quasi tutte la stessa inquadratura.

Con Modal configurato sull'account che possiede il volume `bper-lilt-spike`:

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = 'src'
modal run -m training.modal_train --data-dir D:/Projects/poc-data-extraction/CARTELLA-DATASET --out-dir D:/Projects/poc-data-extraction/CARTELLA-MODELLO-NUOVA
```

La cartella di uscita deve essere nuova. L'esecuzione è limitata a un container L4, 45 minuti, massimo 16 epoche (8 per default) e nessun tentativo automatico. Senza miglioramento in validazione si ferma dopo `--patience` epoche (2 per default, al massimo 4). Il servizio riceve le parole OCR, le coordinate, le etichette e i manifest; le schermate restano locali. I risultati remoti hanno un nome derivato dall'esperimento e non sovrascrivono i modelli precedenti.

La selezione dell'epoca usa l'accuratezza sul valore completo dei campi di controllo (con spareggio sulla F1 delle parole non-nota e poi sulla F1 micro complessiva). **Il test si esegue solo con `--final-test`, su un candidato congelato**, e solo su un dataset costruito con `--include-test`: senza, il run rifiuta.

La suddivisione in finestre di 512 sottotoken preserva intero il blocco della tabella `FIDI` insieme alla sua intestazione. La cartella `cpu_model` scaricata (`--no-download-weights` lascia i pesi sul volume) contiene pesi e tokenizer caricabili con Transformers su CPU, insieme a etichette, split e manifest. Le predizioni riportano un ruolo per ogni parola OCR. `training.evaluation` ricostruisce i 45 campi e misura corretto, errato, mancante, allucinato e assenza corretta. I campi della tabella `FIDI` vengono dalla sola riga più in alto, quella del primo numero di fido predetto (ADR 0023), letta per colonna sotto la testata della tabella (ADR 0026). Anche i Soggetti si leggono per colonna, e nell'Elenco una parola resta nella colonna del suo ruolo (ADR 0028). Il confronto conserva cifre e punteggiatura, tollerando solo differenze di rappresentazione documentate nei test. Per un estrattore che produce direttamente i valori dei campi, `evaluate_field_values()` applica gli stessi confronti e riepiloghi a `{"fields": {campo: testo o None}, "abstained": [campi]}` per schermata, conta le astensioni e segnala con `complete` una prova priva dell'esito di qualche schermata; la F1 delle parole non si applica.

Questo percorso è un esperimento offline. L'adozione nel flusso di cattura dell'edge-agent richiede una modifica successiva e una verifica su acquisizioni reali.
