# Addestramento LiLT da `data/dataset`

LiLT assegna ruoli alle parole lette nelle schermate BPER. Il valutatore ricostruisce i campi dalle parole originali, compresi gli eventuali errori OCR. Manteniamo un LiLT per la lettura RapidOCR e un LiLT per quella del rilevatore RapidOCR con riconoscitore OCRia-nano riaddestrato. L'archivio comune contiene schermate, valori revisionati e ruoli delle pratiche. [Confronto, provenienza e manutenzione dei due percorsi](../../docs/ocr-lilt.md) · [Archivio](../../data/README.md)

Eseguire i blocchi PowerShell dalla **radice del repository**, nella stessa sessione. Gli esempi usano `.venv` con le dipendenze di `requirements.txt` e `.venv-ocr` per RapidOCR.

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = (Resolve-Path src).Path
$archive = (Resolve-Path data/dataset).Path
$projectPython = (Resolve-Path .venv/Scripts/python.exe).Path
$runRoot = Join-Path (Get-Location).Path ('outputs/ocr-lilt-' + (Get-Date -Format yyyyMMdd-HHmmss))
```

## 1. OCR

`training.ocr_runner` esegue RapidOCR con profilo CPU `pc4` (4 thread intra-op) o `vdi2` (2 thread intra-op), entrambi con 1 thread inter-op. A1 usa i modelli PP-OCRv6 small per le righe e medium per il testo, A0 usa small per entrambi. Per le configurazioni A2–A4 e le varianti di A1 e A2 consultare `run --help`. Preparare l'ambiente e avviare A1 con:

```powershell
if (-not (Test-Path .venv-ocr/Scripts/python.exe)) { uv venv .venv-ocr --python 3.13 }
uv pip install --python .venv-ocr/Scripts/python.exe -r requirements-ocr.txt
$rapidRun = Join-Path $runRoot 'A1-pc4'
& ./.venv-ocr/Scripts/python.exe -m training.ocr_runner run --config A1 --profile pc4 --archive $archive --out $rapidRun
& $projectPython -m training.ocr_runner report --run $rapidRun --archive $archive
```

Le schermate lette sono quelle delle pratiche di addestramento e di controllo con almeno un valore da misurare. Le pratiche di test si aggiungono con `--include-test` (la lettura OCR è permessa, ADR 0035); i loro valori non servono a scegliere o regolare un modello, e si misurano una volta, quando il candidato è congelato.

Ogni schermata viene salvata appena letta: una prova interrotta riprende dalle schermate mancanti, e una schermata in errore non ferma le altre. `cache.json` nasce solo quando tutte le schermate hanno un risultato, con l'impronta registrata nel manifest insieme a modelli, versioni, thread e tempi. Una cartella non accetta un'altra configurazione o altri modelli. `report` costruisce il dataset derivato e scrive in `ocr_selection.json` disponibilità OCR, NDG dei soggetti, rapporti e letture 6→8 per pratica, per addestramento e controllo.

Le configurazioni lente si possono leggere su Modal, in contenitori solo CPU con 4 core e gli stessi pin e file modello di `.venv-ocr`:

```powershell
$modalOcrRun = Join-Path $runRoot 'rapidocr-modal'
& $projectPython -m modal run --detach -m training.modal_ocr --out-dir $modalOcrRun --configs 'A1,A2,A3'
```

Ogni gruppo di schermate (`--shard-size`, 8 per default; intere per le configurazioni in `--whole`) è una normale prova di `run_ocr()`. In locale `merge_runs()` le unisce in `<config>/run` solo se sono tutte complete, con la stessa configurazione e gli stessi modelli, e coprono ogni schermata una sola volta. Il pannello dei costi (`--panel`, vuoto per saltarlo) legge le stesse schermate con tutte le configurazioni in un solo contenitore, così i tempi si confrontano sulla stessa macchina. Su Modal vanno le schermate; i valori restano in locale. Se il processo locale si ferma, l'app staccata continua: `--collect` con la stessa cartella scarica quello che è finito.

Per ricreare la **cache ibrida** sulla macchina di misura servono la cartella sperimentale `outputs/ocria-nano-bench/scripts/`, i modelli RapidOCR nella `.venv-ocr`, le chiavi della cache A1 delle 149 schermate e l'accesso al lettore addestrato sul volume `ocria-nano-train`. Il comando seguente invia quelle schermate a Modal. Gli script storici incorporano il percorso del repository usato per la prova. [Dettagli per riprendere l'esperimento in un altro ambiente](../../docs/ocr-lilt.md#aggiornare-e-consegnare-i-due-percorsi)

```powershell
$nanoRun = Join-Path $runRoot 'nano-s0'
& $projectPython -m modal run outputs/ocria-nano-bench/scripts/pair_modal.py::caches --runs f-x1.5-s0 --out-dir $nanoRun
```

## 2. Dataset per ciascuna lettura

Il comando `report` ha già costruito e sigillato il dataset A1 in `$rapidRun/dataset`. Per la cache ibrida usare lo stesso allineatore. Se si riparte dalla cache già conservata, impostare `$nanoCache` sul suo percorso.

```powershell
$rapidDataset = Join-Path $rapidRun 'dataset'
$nanoCache = Join-Path $nanoRun 'cache-f-x1.5-s0.json'
$nanoDataset = Join-Path $runRoot 'dataset-nano-s0'
& $projectPython -m training.dataset --archive $archive --ocr $nanoCache --output $nanoDataset
```

Il ruolo di ogni pratica in `pratiche.csv` è il suo split: `addestramento` è `train`, `controllo` è `val`, `test` è `test` (ADR 0027). Ogni schermata ha un esempio solo se ha un valore da misurare (`TRASCRITTO`, `VUOTO`, `NON VISIBILE`) e una lettura OCR; `PARZIALE` e `DERIVATO` etichettano le parole che trovano senza essere un bersaglio, e i valori fuori dai 45 campi (`Chiave` vuota) non lo sono mai. Il tipo di pagina per l'allineamento si ricostruisce da pagina e variante di `schermate.csv`.

Il dataset rifiuta: un'immagine diversa dall'impronta registrata, un ruolo, una schermata o un campo sconosciuti, un esito che non va d'accordo col valore, un campo ripetuto, una lettura OCR di una schermata di test senza `--include-test`, una schermata da misurare senza lettura, e una pratica, un'immagine o un NDG di cliente che attraversano due split. L'NDG di un'istituzione (il Fondo di garanzia per la prima casa, `11153238`) non è un'identità (ADR 0024).

Escono `examples.json` (parole, riquadri, etichette, valori attesi), `roles.json` (ordine delle classi), `alignment_report.csv` (quali osservazioni si possono usare come supervisione), `coverage.json` e `manifest.json`, sigillato con l'impronta del contenuto.

## 3. Addestramento e modello locale

L'addestramento parte dal modello pubblico `nielsr/lilt-xlm-roberta-base`, con una nuova testa di classificazione. Non riutilizza pesi BPER precedenti. Le varianti si applicano solo a copie dell'insieme di addestramento: con `--variants 3` una copia con piccoli spostamenti e cifre cambiate, e due con la pagina inquadrata diversamente (tagliata o più alta, `_reframe()`), perché LiLT legge le posizioni rispetto all'immagine intera e le schermate di addestramento hanno quasi tutte la stessa inquadratura.

Con Modal configurato sull'account che possiede il volume `bper-lilt-spike`:

```powershell
& $projectPython -m modal run -m training.modal_train --data-dir $rapidDataset --out-dir (Join-Path $runRoot 'lilt-A1') --epochs 8 --variants 2 --seed 7 --patience 2
& $projectPython -m modal run -m training.modal_train --data-dir $nanoDataset --out-dir (Join-Path $runRoot 'lilt-nano-s0') --epochs 8 --variants 2 --seed 7 --patience 2
```

L'addestramento richiede una cartella di uscita nuova. Una stessa combinazione di esempi, ruoli, modello base e impostazioni identifica una corsa immutabile sul volume. Il servizio riceve parole OCR, coordinate, etichette e manifest. Ogni corsa usa un container L4, al massimo 45 minuti e 16 epoche (8 per default), con arresto dopo `--patience` epoche senza miglioramento (2 per default, al massimo 4).

Per recuperare la coppia Nano corrente da un clone, eseguire `git lfs install` e `git lfs pull`. Il lettore si trova in `models/ocria-nano-rec/` e il LiLT abbinato in `models/lilt/`. Per riprendere le due corse di riferimento complete, scaricare le directory del volume Modal dagli ID indicati nei rispettivi `download_manifest.json`. Ogni download LiLT include i pesi da circa 1,1 GB. [Inventario e impronta del lettore](../../models/README.md)

```powershell
& $projectPython -m modal volume get bper-lilt-spike model_b47465bd4a400d65 (Join-Path $runRoot 'recupero-lilt-A1')
& $projectPython -m modal volume get bper-lilt-spike model_9042c85d680c6e41 (Join-Path $runRoot 'recupero-lilt-nano-s0')
```

La selezione dell'epoca usa l'accuratezza sul valore completo dei campi di controllo (con spareggio sulla F1 delle parole non-nota e poi sulla F1 micro complessiva). **Il test si esegue solo con `--final-test`, su un candidato congelato**, e solo su un dataset costruito con `--include-test`: senza, il run rifiuta.

La suddivisione in finestre di 512 sottotoken preserva intero il blocco della tabella `FIDI` insieme alla sua intestazione. La cartella `cpu_model` scaricata (`--no-download-weights` lascia i pesi sul volume) contiene pesi e tokenizer caricabili con Transformers su CPU, insieme a etichette, split e manifest. Le predizioni riportano un ruolo per ogni parola OCR. `training.evaluation` ricostruisce i 45 campi e misura corretto, errato, mancante, allucinato e assenza corretta. I campi della tabella `FIDI` vengono dalla sola riga più in alto, quella del primo numero di fido predetto (ADR 0023), letta per colonna sotto la testata della tabella (ADR 0026). Anche i Soggetti si leggono per colonna, e nell'Elenco una parola resta nella colonna del suo ruolo (ADR 0028). Il confronto conserva cifre e punteggiatura, tollerando solo differenze di rappresentazione documentate nei test. Per un estrattore che produce direttamente i valori dei campi, `evaluate_field_values()` applica gli stessi confronti e riepiloghi a `{"fields": {campo: testo o None}, "abstained": [campi]}` per schermata, conta le astensioni e segnala con `complete` una prova priva dell'esito di qualche schermata; la F1 delle parole non si applica.

Questo percorso è un esperimento offline. L'adozione nel flusso di cattura dell'edge-agent richiede una modifica successiva e una verifica su acquisizioni reali.
