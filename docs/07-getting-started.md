# Per iniziare

Il progetto estrae campi da screenshot BPER tramite il motore Python `src/extraction/`.
Puoi lavorare su file con CLI o Tkinter, oppure acquisire dal vivo con l'edge-agent
PyQt6. La suite pytest verifica diversi comportamenti senza chiamare i provider;
per un'estrazione reale servono connessione e credenziali LLM. La CLI richiede
anche il CSV di riferimento, mentre le due GUI possono lavorare senza.
<!-- Source: src/extraction/cli.py::main; gui_app.py:238; src/edge-agent/local_extraction_client.py:90; tests/test_local_extraction_client.py:46 -->

Leggi questa guida insieme ad [Architettura](04-architecture.md),
[Workflow](05-workflows.md) e [API Python](12-python-api.md). I comandi seguenti
partono dalla radice del repository; gli esempi di configurazione sono segnaposto.

## Prerequisiti

- **Python 3.13 o 3.12** come target pratico. Il launcher cerca prima queste versioni,
  poi ripiega sul comando `python` senza verificarne la versione; non c'è un vincolo
  di runtime dichiarato in un file di packaging.
- **Credenziale OpenAI o Gemini** per l'estrazione reale. Il motore usa OpenAI e
  `gpt-4o` come default del codice; un modello deve essere compatibile con il provider.
- **CSV `INPUT_DIR/dati.csv`** soltanto per la CLI. Il dataset non è distribuito nel
  repository; va ottenuto separatamente prima di eseguire la valutazione.
- **Ambiente desktop e monitor BPER** per la cattura live. Il frame del monitor viene
  riportato sulla finestra applicativa prima di routing ed estrazione.
- **torch/torchvision e pesi DINOv2** per il riconoscimento ML. Le dipendenze sono nel
  file comune; il preflight dell'edge-agent gestisce preparazione e warm-up. Il primo
  avvio da sorgente scarica i pesi DINOv2; il pacchetto li contiene già (ADR 0031), come i prototipi
  delle pagine.

<!-- Source: run_edge_agent.bat:43; src/extraction/config.py:16; src/extraction/llm_factory.py:18; src/extraction/cli.py::main; src/edge-agent/workers/capture/bper_capture_worker.py:442; src/edge-agent/bootstrap.py:489; requirements.txt:13 -->

I comandi sono PowerShell-first, con l'equivalente bash per il setup manuale.
`pyscreenshot` è una dipendenza condizionale per Linux; i launcher `.bat` e la build
portable sono destinati a Windows.
<!-- Source: requirements.txt:9; run_edge_agent.bat:1; build_exe.bat:5 -->

## Setup

### 0. Se hai clonato prima del 2026-07-21: ri-clona

L'intera storia git è stata riscritta con `git filter-repo` e force-pushata per ripulire una chiave OpenAI trapelata da `src/edge-agent/config.ini`. Tutti gli hash dei commit sono cambiati. Un clone precedente può contenere la vecchia storia e rischia di reintrodurre la chiave in un merge o push. Non mergiare e non pushare da un vecchio clone; riparti da zero:

```powershell
git clone <origin-url> poc-data-extraction
cd poc-data-extraction
```

### 1. Percorso rapido (Windows): il launcher fa tutto

```powershell
.\run_edge_agent.bat
```

Crea `.venv` con il primo interprete disponibile, preferendo Python 3.13 e 3.12, installa `requirements.txt` quando crea l’ambiente e lancia l’edge-agent. Un ambiente già valido viene riutilizzato senza reinstallare le dipendenze. Auto-ripara anche un venv rotto il cui interprete base è stato spostato o disinstallato. Eventuali argomenti vengono inoltrati all'app, per esempio `.\run_edge_agent.bat --debug`.
<!-- Source: run_edge_agent.bat:19-29 -->

### 2. Percorso manuale (tutte le piattaforme)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Un solo `requirements.txt` copre motore, GUI e strumenti di build. Per sviluppare installa anche pytest:

```powershell
python -m pip install -r requirements-dev.txt
```

<!-- Source: requirements.txt:1; requirements-dev.txt:1 -->

### 3. Crea il tuo `.env`

```powershell
copy .env.example .env
```

```bash
cp .env.example .env
```

Apri `.env` e imposta come minimo:

```
LLM_API_KEY=<la tua chiave>
```

`main.py` e `gui_app.py` caricano `.env` prima di importare `extraction`. Tkinter
inizializza provider e modello dalla configurazione effettiva e conserva anche
un modello personalizzato. L'avvio diretto dell'edge-agent carica l'ambiente e
completa il preflight prima di importare la UI, che a sua volta importa il motore.
Puoi anche esportare le variabili o inserire la chiave nella GUI. Per esempio, in PowerShell:

```powershell
$env:LLM_API_KEY = "<la tua chiave>"
python gui_app.py
```

<!-- Source: main.py:4; src/edge-agent/edge_agent.py:28; src/edge-agent/edge_agent.py:63; gui_app.py:1; gui_app.py:24 -->

Per Gemini invece:

```
LLM_PROVIDER=gemini
LLM_API_KEY=<la tua chiave Gemini>
LLM_MODEL=<modello Gemini abilitato per la tua chiave>
```

La factory rifiuta le coppie disallineate: un modello `gemini-*` con `LLM_PROVIDER=openai` (o `gpt-*` con `gemini`) solleva `ValueError`.
<!-- Source: src/extraction/llm_factory.py:49-63 -->

### 4. Fornisci il CSV di ground truth (solo CLI)

Per le pratiche dell'archivio non serve nulla: con `INPUT_DIR` su una cartella di `data/dataset/pratiche` (default
`data/dataset/pratiche/51350695`, la pratica di riferimento) la CLI legge i valori dalle righe della pratica in
`data/dataset/valori.csv` (ADR 0032). Per un'altra cartella colloca un `dati.csv` in `INPUT_DIR`: formato
long, con intestazioni `Fotogramma`, `Denominazione da attribuire` e `Valore rilevato`.
`Fotogramma` deve coincidere con il nome dell'immagine senza estensione: per
`screen 1.png` usa `screen 1`, non `1` né `screen 1.png`. Il loader non converte
automaticamente questi identificativi. Formati e intestazioni alternative sono
nel [modello dati](06-data-model.md#ground-truth-csv).
<!-- Source: src/extraction/config.py:8; src/extraction/evaluation.py:49; src/extraction/imaging.py:29 -->

La GUI Tkinter e l'edge-agent funzionano senza; la CLI si ferma se non trova né
`dati.csv` né il foglio della pratica. Non usare dati di esempio come baseline di
accuratezza: serve il dataset di riferimento autorizzato.
<!-- Source: src/extraction/cli.py::main; gui_app.py:263 -->

### 5. Esegui

```powershell
python main.py                            # batch CLI sulla pratica di riferimento data/dataset/pratiche/51350695
python gui_app.py                         # GUI desktop Tkinter (scegli i file a mano)
python main.py --gui                      # edge-agent (PyQt6) con cattura dal vivo
python src/edge-agent/edge_agent.py           # edge-agent, lanciato direttamente
python src/edge-agent/edge_agent.py --debug   # edge-agent + tab Debug del router LLM
```

`main.py --gui` inoltra l’avvio a `edge_agent.main()`, ma ha già importato `extraction` prima del preflight: per il primo avvio preferisci il launcher o `python src/edge-agent/edge_agent.py`, così l’ambiente può essere predisposto prima della lettura della configurazione del motore. Il flag `--debug` sblocca la tab Debug LLM, che richiede in aggiunta `show_llm_tab = true` nella sezione `[debug]` di `src/edge-agent/config.ini`.
<!-- Source: src/edge-agent/edge_agent.py:87 -->

## File chiave da leggere per primi

Ordinati per valore di apprendimento: dal contratto dati verso l'orchestrazione e la UI.

1. **`src/extraction/fields.py`**: `FIELD_KEYS` (45 chiavi, righe 12-54) è l'unica fonte di verità per tutto ciò che il sistema estrae. Lo schema Pydantic, la mappatura CSV, le metriche e la mappa di retry si agganciano tutti a questa lista; leggila per prima e il vocabolario di dominio (`ndg`, `fido`, `professione_principale`) smette di essere rumore.
2. **`src/extraction/schemas.py`**: Il contratto di output dell'LLM: `FieldResult` (value/confidence/evidence/section), `Soggetto`, `Fido`, `Garanzia`, `ExtractionResponse`, `AnchorResponse`. `FieldsModel` è generato dinamicamente da `FIELD_KEYS`, motivo per cui `fields.py` viene prima.
3. **`src/extraction/pipeline.py`**: `ExtractionPipeline`, il cuore del sistema: passaggio anchor → passaggio principale → retry condizionali per area → controllo di coerenza → appiattimento dei soggetti. Se leggi un solo file, leggi questo; nota i due entry point `extract_from_screen()` (CLI/Tkinter) ed `extract_from_image()` (edge-agent, immagine già preprocessata dalla cattura, con il limite dimensionale comunque applicato dalla pipeline).
4. **`src/extraction/config.py`**: Ogni manopola regolabile: config da variabili d'ambiente, coordinate di ritaglio (`CONTENT_CROP`, `HEADER_IN_CONTENT`, `RETRY_AREAS`), la mappa campo-area di retry (`AREA_TO_FIELDS`) e la tabella dei prezzi (`PRICING_PER_1M`). Le variabili d'ambiente vengono lette **al momento dell'import** (`os.getenv` a livello di modulo), il che conta: vedi Trabocchetti.
5. **`src/extraction/cli.py`**: `BatchRunner` e `run_extraction_batch()`, il motore batch condiviso usato sia dalla CLI sia dalla GUI Tkinter. Mostra il modello di threading: ChatModel creati una volta, condivisi sul `ThreadPoolExecutor`. `main()` è il flusso CLI end-to-end.
6. **`src/extraction/vlm_client.py`**: Le chiamate LLM di basso livello e le strategie di output strutturato per provider (`.with_structured_output()` per OpenAI, json_mode per Gemini 1.5, JSON in forma libera + validazione manuale per Gemini 2.0+/3.x, discriminati da `_GEMINI_JSON_SCHEMA_MODELS`). È anche dove viene popolato il tracciamento dei costi `_meta`.
7. **`src/extraction/evaluation.py`**: `load_ground_truth()`, `eval_outputs()` e la classificazione OK / WRONG / MISSING / HALLUCINATED / OK_NULL; spiega la separazione tra metriche RAW e FILTERED guidata da `dataset_mismatch_guard()`.
8. **`src/edge-agent/local_extraction_client.py`**: Corto e portante: il ponte QObject tra la UI PyQt6 e `ExtractionPipeline`, la giuntura `ingest_frame()` e il segnale `result_ready` che riattraversa il confine verso il thread della UI.
9. **`src/edge-agent/workers/capture/bper_capture_worker.py`**: Il loop di cattura: screenshot mss, `preprocess_for_ocr()`, deduplica pHash, routing di pagina, gate di stabilità di 2 secondi, poi l’accodamento asincrono con `ingest_frame()` e la conferma dell’esito; anche lo scatto manuale passa dal loop del worker. Leggilo dopo avere compreso la pipeline.

<!-- Source: src/extraction/fields.py:12; src/extraction/schemas.py:31; src/extraction/pipeline.py:122; src/extraction/pipeline.py:231; src/extraction/config.py:7; src/extraction/cli.py::BatchRunner.__init__; src/extraction/vlm_client.py:123; src/extraction/evaluation.py:88; src/edge-agent/local_extraction_client.py:127; src/edge-agent/workers/capture/bper_capture_worker.py:346 -->

## Dove intervenire e cosa verificare

| Se vuoi cambiare… | Parti da… | Verifica… |
|---|---|---|
| Un campo estratto | `src/extraction/fields.py`, `schemas.py`, `field_definitions.py`, `config.py` e `prompts/` | Chiave, mapping CSV, area di retry o esclusione esplicita e colonna canonica coerenti; test del vocabolario, retry ed Excel. |
| Lettura o fusione dei valori | `src/extraction/pipeline.py`, `src/extraction/normalization.py` | Anchor, budget e ordine dei passaggi; `test_pipeline_retry.py`, `test_content_crop.py`. |
| Inquadratura e ritagli | `src/edge-agent/frame_normalize.py`, `src/extraction/imaging.py`, `src/edge-agent/page_classifier.py` | `test_frame_normalize.py`, `test_bper_capture_framing.py`, `test_page_classifier.py`, `test_content_crop.py`. |
| Quando acquisire di nuovo | `src/edge-agent/workers/capture/bper_capture_worker.py`, `src/edge-agent/stability.py` | `test_bper_capture_lifecycle.py`: cambiamenti piccoli, errori, conferme vecchie e scatto manuale. |
| Ordine e parallelismo live | `src/edge-agent/local_extraction_client.py`, `src/edge-agent/extraction_pool.py` | `test_local_extraction_client.py`: frame senza NDG, completamenti fuori ordine, errori e diagnostica non scrivibile. |
| Una riga per pratica o l'Excel | `src/edge-agent/practice_consolidation.py`, `src/edge-agent/excel_export.py` | `test_practice_consolidation.py`, `test_excel_export.py`; riusare `pick_best()`. |
| Prompt o placeholder | `prompts/*.json`, `src/prompt_store.py` | `test_prompt_store.py`; aggiornare `CATALOG` insieme al JSON e riavviare. |
| Provider o costi stimati | `src/extraction/llm_factory.py`, `src/extraction/vlm_client.py`, `src/extraction/config.py` | Errori di configurazione e parsing, metadati, modello nella tabella prezzi. |
| Valutazione o caricamento GT | `src/extraction/evaluation.py`, `src/extraction/normalization.py` | Join sugli ID delle immagini e confronto con una baseline autorizzata. |
| Flusso batch | `src/extraction/cli.py` | CLI e Tkinter condividono `run_extraction_batch()`; le callback operano sul thread chiamante. |
| UI desktop | `gui_app.py` oppure `src/edge-agent/ui/` | Prova del percorso interessato; la UI live mostra Cattura e Dati Estratti, con Debug LLM facoltativo. |
| Riconoscimento pagina | `src/edge-agent/llm_router.py`, `page_classifier.py`, `page_registry.py` e catalogo pagine | `test_page_registry.py`, `test_page_classifier.py`; modalità in `config.ini`. |
| Impostazioni di cattura | `src/edge-agent/config.py`, `src/edge-agent/config.ini` | Monitor, FPS, routing e risoluzione delle credenziali separata dal motore. |

<!-- Source: src/extraction/fields.py:12; src/extraction/pipeline.py:295; src/extraction/normalization.py:120; src/edge-agent/frame_normalize.py:209; src/edge-agent/workers/capture/bper_capture_worker.py:299; src/edge-agent/local_extraction_client.py:194; src/edge-agent/excel_export.py:217; src/prompt_store.py:62; src/extraction/cli.py::BatchRunner.run; src/edge-agent/ui/main_window.py:66; src/edge-agent/config.py:292 -->

I percorsi di test indicati nella tabella sono sotto `tests/`. Le firme complete,
i valori restituiti e gli errori delle API principali sono nel
[riferimento Python](12-python-api.md).

## Test prima della prova con il modello

```powershell
python -m pytest tests
```

Per una verifica senza i casi che eseguono DINOv2:

```powershell
python tools/check.py
# equivalente: python -m pytest tests -m "not slow"
```

Il marker `slow`, registrato in `pyproject.toml`, riguarda i 18 casi di inferenza
del classificatore. I due controlli puri della cache restano nella verifica rapida.
`tools/check.py` usa l'interprete attivo e accetta altri argomenti pytest, per
esempio `python tools/check.py -q`. Il comando completo non applica filtri
predefiniti; la durata di entrambi dipende anche dagli import e dall'ambiente.

La suite comprende catalogo prompt, coerenza dei vocabolari di campo, geometria
e ritagli, riconoscimento pagina, retry, gate anchor, merge scalare, coerenza dei
tooltip e appiattimento dei soggetti con provenienza. Verifica anche l'identità
NDG condivisa fra valutazione e consolidamento, pool, client asincrono, ciclo di
cattura ed Excel. Comprende anche ammissione dei soggetti da retry, separazione
pagina di origine/gruppo di export e avvio Tkinter dalla configurazione. Le prove
del client usano una pipeline finta sul confine con il provider; non misurano
l'accuratezza di lettura del modello. `test_page_classifier.py` usa DINOv2 su CPU,
può ricostruire la cache e viene saltato se torch non è disponibile; al primo uso
dei pesi può essere necessaria la rete.
<!-- Source: tests/test_domain_vocabulary.py:11; tests/test_pipeline_postprocessing.py:60; tests/test_normalization.py:22; tests/test_local_extraction_client.py:18; tests/test_page_classifier.py:1; tests/test_excel_export.py:22; tests/test_bper_capture_lifecycle.py:105 -->

Per una modifica al comportamento, esegui prima la regressione mirata e poi la
suite completa; per l'accuratezza estrattiva serve anche il confronto sul dataset.

## Attività comuni

### Eseguire un'estrazione completa e valutarla (CLI)

```powershell
python main.py
```

Elabora ogni `.png`/`.jpg`/`.jpeg` in `INPUT_DIR`, poi:
<!-- Source: src/extraction/cli.py::main -->

- scrive `outputs/51350695/poc_outputs_improved.json` (risultati completi per schermata, `src/extraction/cli.py::main`);
- stampa l'accuratezza RAW e FILTERED con il dettaglio per campo;
- scrive `outputs/51350695/poc_debug_improved.csv`: separatore punto e virgola, `utf-8-sig` (amichevole per Excel, `src/extraction/evaluation.py:15`);
- stampa chiamate/token/USD per schermata via `print_cost_summary()`.

La prima baseline con un provider reale (2026-09-29, `gemini-3.8-flash`, tre run: 93,5-94,8%, circa $0,04 a schermata) è nella storia git (`git show d939ea5:.tritech/codebase-xray/baselines/2026-09-29-gemini-3.8-flash/README.md`), con il ground truth che l'ha prodotta e la soglia di accettazione proposta. Per sapere se una modifica ha aiutato, rilancia sullo stesso `dati.csv` e confronta con quei numeri; se cambi il ground truth, salva prima il JSON precedente e il riepilogo stampato.

### Estrarre qualche immagine senza ground truth (Tkinter)

```powershell
python gui_app.py
```

Il campo della chiave API si pre-compila da `LLM_API_KEY` (o dalla legacy `OPENAI_API_KEY`, `gui_app.py:24`); scegli provider/modello dai menu a tendina, seleziona le immagini, opzionalmente un CSV di GT, ed esegui. Gli output finiscono nella directory corrente: `poc_outputs_gui.json`, `poc_results_gui.csv` e (se è stato indicato un CSV di GT) `poc_debug_gui.csv`.
<!-- Source: gui_app.py:250-273 -->

### Smoke test della cattura dal vivo (edge-agent)

```powershell
.\run_edge_agent.bat --debug
```

Nella tab *Cattura*, scegli BPER e premi *Avvia*. Il frame viene normalizzato sulla
finestra, riconosciuto e atteso fino alla stabilità; l'estrazione prosegue poi sul
pool senza bloccare la cattura. Controlla in *Dati Estratti* che i frame della
stessa pratica producano una sola riga, poi esporta l'Excel e verifica le due
righe di intestazione e le 45 colonne.
<!-- Source: src/edge-agent/workers/capture/bper_capture_worker.py:346; src/edge-agent/local_extraction_client.py:127; src/edge-agent/ui/data_table_tab.py:194; src/edge-agent/excel_export.py:177 -->

*Acquisisci ora* accoda uno scatto per la pagina selezionata: il thread di cattura
lo esegue senza routing e senza attesa di stabilità. Se il router è già occupato,
il comando può attendere: viene acquisita la schermata visibile al momento
dell'esecuzione. Le animazioni riavviano l'attesa automatica e possono richiedere
lo scatto manuale. Un errore di estrazione permette una nuova acquisizione;
una pagina accodata non è ancora una pagina estratta.
<!-- Source: src/edge-agent/workers/capture/bper_capture_worker.py:299; src/edge-agent/workers/capture/bper_capture_worker.py:329; src/edge-agent/workers/capture/bper_capture_worker.py:722; tests/test_bper_capture_lifecycle.py:183 -->

Confidenza, costi, token e provenienza sono diagnostica del client, visibile sulla
console o in `edge-agent.log` nel bundle senza console. Il log include valori
estratti. La tab Debug LLM richiede sia `--debug` sia `[debug] show_llm_tab = true`;
mostra il traffico del router, non sostituisce la diagnostica dell'estrazione.
<!-- Source: src/edge-agent/local_extraction_client.py:41; src/edge-agent/edge_agent.py:15; src/edge-agent/edge_agent.py:87; src/edge-agent/workers/capture/bper_capture_worker.py:123 -->

### Aggiungere un nuovo campo

`FIELD_KEYS` si dirama ampiamente; un nuovo campo tocca quattro o cinque file:

1. Aggiungi la chiave a `FIELD_KEYS` in `src/extraction/fields.py`: il `FieldsModel` Pydantic si rigenera automaticamente da lì.
2. Mappa l'etichetta del CSV di ground truth in `CSV_TO_SCHEMA` (`src/extraction/fields.py`).
3. Aggiungi `display_name` + `page_key` in `CANONICAL_FIELD_DEFINITIONS` e l'alias in `FIELD_LABEL_ALIASES` (`src/extraction/field_definitions.py`), così l'export canonico e il raggruppamento per pagina della UI lo intercettano.
4. Assegnalo a un'area di retry in `AREA_TO_FIELDS` se va ritentato quando è nullo o a bassa confidenza.
<!-- Source: src/extraction/config.py:105 -->
5. Descrivilo nel prompt italiano (`prompts/extraction_main.json`), così il modello sa di doverlo cercare.

### Fare debug di un'estrazione sbagliata

```powershell
$env:DEBUG_MODE = "1"
$env:DEBUG_SAVE_CROPS = "1"
python main.py
```

`DEBUG_MODE` attiva il logging batch verboso e `DEBUG_SAVE_CROPS` salva i ritagli intermedi in `INPUT_DIR/debug_crops/`. Vedere esattamente quale ritaglio è andato al modello è il modo più rapido per diagnosticare un campo sbagliato. Incrocia con `_field_sources` nel JSON di output per scoprire quale passaggio (ANCHOR_HEADER / CONTENT_MAIN / RETRY_*) ha prodotto il valore finale.
<!-- Source: src/extraction/config.py:129 -->

### Creare il pacchetto portable Windows

```powershell
.\build_exe.bat
```

Lo script usa `edge_agent.spec` per una build PyInstaller `onedir`, produce
`dist/EdgeAgent/` e lo ZIP `dist/EdgeAgent_YYYY-MM-DD.zip`. Copia configurazione,
asset e prompt modificabili, oltre al template dell'ambiente. Il preflight del
pacchetto prepara i componenti mancanti e, se la chiave manca, la chiede al primo
avvio. Non basta consegnare il solo `.exe`: va distribuita l'intera cartella.
<!-- Source: build_exe.bat:85; build_exe.bat:91; build_exe.bat:99; build_exe.bat:113; edge_agent.spec:1; src/edge-agent/bootstrap.py:450 -->

Per un tester che non sa cosa sia una chiave API, la build può consegnare il
pacchetto già configurato. All'avvio lo script chiede la chiave da includere
(INVIO per nessuna), oppure la legge da `EDGE_AGENT_PACKAGE_KEY`:

```powershell
$env:EDGE_AGENT_PACKAGE_KEY = "<chiave dedicata alla beta>"
.\build_exe.bat
```

`src/edge-agent/env_key.py`, lo stesso modulo che salva la chiave inserita nel dialog
di primo avvio, la scrive solo nel `.env` del pacchetto e rifiuta valori vuoti,
multi-riga o con `=`. Lo zip prende il suffisso `_CON-CHIAVE` e il preflight non
chiede nulla. Chi riceve quello zip può leggere la chiave: usane una dedicata alla
beta, con limite di spesa, e revocala alla fine.
<!-- Source: build_exe.bat:10; build_exe.bat:103; src/edge-agent/env_key.py:66; tests/test_env_key.py:39 -->

La build rimuove la precedente `dist/EdgeAgent` e rifiuta un `api_key` non vuoto
nell'INI. Se Python 3.13/3.12 è assente, lo script tenta anche l'installazione
automatica: avvialo su una macchina di build predisposta a queste operazioni.
<!-- Source: build_exe.bat:19; build_exe.bat:68; build_exe.bat:76 -->

## Trabocchetti

- **La CLI si arresta senza verità.** Se `INPUT_DIR` non contiene un `dati.csv` e non sta in una cartella con `pratiche.xlsx` accanto, `python main.py` solleva `FileNotFoundError`; le due GUI funzionano senza.
<!-- Source: src/extraction/cli.py::main -->

- **La storia git è stata riscritta il 2026-07-21: i cloni stantii sono pericolosi.** Una chiave OpenAI era stata committata in `src/edge-agent/config.ini`; è stata ripulita dall'intera storia con `git filter-repo` e force-pushata. Ogni hash di commit è cambiato. Se il clone precede la riscrittura, conserva separatamente il lavoro locale utile e usa un clone nuovo; evita merge o push della vecchia storia.

- **Mai mettere una chiave reale in `src/edge-agent/config.ini`.** La riga `[llm] api_key` è in un file tracciato e ora è **vuota**. La ricerca della chiave del router preferisce il valore INI rispetto all'ambiente ed è consapevole del provider (`AgentConfig.resolve_llm_settings()`): per `gemini` ricade su `GEMINI_API_KEY` → `GOOGLE_API_KEY` → `LLM_API_KEY`, per `openai` su `OPENAI_API_KEY` → `LLM_API_KEY`. Il pattern sicuro è: lascia la riga vuota nell'INI e imposta la chiave in `.env`. Qualunque valore che inizi per `REDACTED` viene trattato come vuoto, perché un placeholder rimasto in giro aveva già oscurato le chiavi da ambiente rompendo il router in silenzio. Trappola aggiuntiva: `AgentConfig.save()` scrive `llm_api_key` di nuovo dentro `config.ini`; al momento nulla chiama `save()`, ma collegarlo a un pulsante della UI ri-persisterebbe segreti in un file tracciato.
<!-- Source: src/edge-agent/config.py:339 -->

- **Le estrazioni reali chiamano un provider, e i modelli sconosciuti riportano $0.00.** Per schermata: 1 chiamata anchor + 1 chiamata principale + fino a `MAX_CALLS_PER_SCREEN - 2` retry, uno per area debole, in parallelo tra le schermate. Il default di `MAX_CALLS_PER_SCREEN` è derivato da `2 + len(AREA_TO_FIELDS)` (= 5), quindi sono ammessi fino a 5 passaggi logici. I retry di trasporto possono portare a più richieste di rete, e il router LLM effettua chiamate separate. `estimate_cost_usd()` restituisce `0.0` per qualsiasi modello assente da `PRICING_PER_1M`: dato che `LLM_MODEL` è testo libero, un nome di modello sbagliato o datato (es. `gpt-4o-2024-11-20`) azzera in silenzio il report dei costi invece di fallire.
<!-- Source: src/extraction/pipeline.py:317; src/extraction/vlm_client.py:26 -->

- **Le variabili d'ambiente vengono lette al momento dell'import.** `src/extraction/config.py` valuta ogni `os.getenv()` all'import del modulo. In una REPL o in un notebook imposta l’ambiente prima di `import extraction`. Tkinter carica `.env` prima del motore; l’avvio diretto dell’edge-agent rinvia l’import della UI fino al preflight. La scorciatoia `main.py --gui` ha già importato il motore prima di quel passaggio.

- **L'edge-agent si configura via INI, non via env.** FPS, modalità router, indice del monitor, soglia di dedup: tutto da `src/edge-agent/config.ini`. Il motore di estrazione legge invece l’ambiente; `resolve_llm_settings()` gestisce separatamente credenziale, endpoint e modello del router.

- **La cattura è dell'intero monitor, ma il frame viene ritagliato sulla finestra.** `_grab_raw()` prende il monitor via `mss`, poi `frame_normalize.normalize_frame()` lo riporta sulla finestra applicativa: prima cercando il titolo che contiene `window_title_contains` (`config.ini`), poi deducendo il rettangolo dallo sfondo del desktop, altrimenti lasciando il frame com'è. Non è un dettaglio cosmetico: ogni ritaglio a valle (ROI del classificatore, bande `RETRY_AREAS` della pipeline) è una frazione tarata su screenshot di finestra, e su un monitor intero cade altrove. Senza il ritaglio il riconoscimento pagina passa da 9 corrette su 9 a 1 su 9 ([ADR 0001](adr/0001-normalizzazione-inquadratura-frame.md)).

- **Le definizioni dei campi devono restare allineate.** Il modello Pydantic deriva
  da `FIELD_KEYS`, ma non ci sono guardie di avvio che confrontino tutte le chiavi
  con mapping CSV, retry e colonne canoniche. Una nuova chiave va propagata alle
  strutture indicate sopra. Le firme da usare sono nel [riferimento API](12-python-api.md).
  <!-- Source: src/extraction/schemas.py:68; src/extraction/config.py:105; src/edge-agent/excel_export.py:92 -->

- **Il riconoscimento ML richiede pesi disponibili.** L'edge-agent prepara i pesi
  durante il preflight nelle modalità `ml` e `hybrid`; il caricamento del modello
  usa `torch.hub` con il repository DINOv2 fissato a una revisione. Su una rete
  senza accesso esterno occorre predisporre la cache: un download fallito può
  impedire il completamento del preflight. La [guida alla configurazione](10-configuration-guide.md)
  descrive il percorso operativo.
  <!-- Source: src/edge-agent/bootstrap.py:489; src/edge-agent/page_classifier.py:33; src/edge-agent/page_classifier.py:363 -->

- **I completamenti sono paralleli, la visualizzazione segue l'ordine di cattura.**
  Un frame già estratto può attendere quello precedente prima di comparire. Non
  costruire una lista dai segnali `result_ready`: rileggi `get_results()` per
  preservare l'associazione delle note senza NDG. Arrestare il pool scarta la coda,
  non attende tutte le estrazioni della sessione.
  <!-- Source: src/edge-agent/local_extraction_client.py:194; src/edge-agent/local_extraction_client.py:214; tests/test_local_extraction_client.py:117 -->

- **L'italiano è intenzionale.** I prompt del VLM, le chiavi dei campi (`professione_principale`), le stringhe UI di PyQt6/Tkinter e le intestazioni CSV sono termini di dominio italiani: non tradurli. Codice, identificatori, commenti e messaggi di commit restano in inglese (policy linguistica nelle istruzioni del repository).

## Vedi anche

- [API Python](12-python-api.md): firme, segnali, valori restituiti ed errori dei punti di integrazione
- [Modello dati](06-data-model.md): risultato per frame, pratica consolidata e formato Excel
- [Stack tecnologico](03-tech-stack.md): analisi dettagliata di ogni dipendenza e di cosa è opzionale
- [Anatomia del progetto](09-project-anatomy.md): la tabella completa delle variabili d'ambiente e il catalogo dei file di configurazione
- [Guida alla configurazione](10-configuration-guide.md): ricette per cambiare provider, abilitare i ritagli di debug e risolvere errori comuni
- [Workflow](05-workflows.md): flussi passo passo per il batch CLI, la cattura dell'edge-agent e la pipeline multi-pass
- [Domande aperte](08-open-questions.md): discrepanze e decisioni irrisolte che influenzeranno la tua prima modifica
