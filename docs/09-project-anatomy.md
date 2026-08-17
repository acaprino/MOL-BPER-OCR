# Anatomia del progetto

Questa è la mappa operativa di `poc-data-extraction`: dove vive ogni cosa, cosa controlla ciascun file di configurazione, ogni variabile d'ambiente che il codice legge davvero, i comandi eseguibili e l'ordine in cui ogni front-end si avvia. Tutto è stato verificato sul codice sorgente (verifica del 2026-07-21); dove `CLAUDE.md`, `README.md` o `.env.example` divergono dal codice, questo documento segue il codice e lo segnala. Per il design ad alto livello, vedi [Architettura](04-architecture.md); per il setup passo per passo, vedi [Come iniziare](07-getting-started.md).

Tre fatti orientano la lettura di tutto il resto:

- **Non esiste un manifesto di build** -- niente `pyproject.toml`, niente `Makefile`, niente `setup.py`. Ogni comando è una semplice invocazione `python ...`, più un launcher batch per Windows (`run_edge_agent.bat`).
- **Non esistono Docker, CI né test suite.** La validazione è manuale (confronto di accuratezza e costi tra esecuzioni).
- **Coesistono due sistemi di configurazione indipendenti:** la pipeline di estrazione è configurata **interamente da variabili d'ambiente** (`extraction/config.py`), l'edge-agent **da un file INI** (`edge-agent/config.ini`). L'unica sovrapposizione è il fallback della API key, descritto più avanti.

## Albero delle directory

Il repository si divide in due package Python -- **`extraction/`** (il motore, senza UI) ed **`edge-agent/`** (l'app PyQt6 di cattura live) -- più gli entry point alla radice. L'edge-agent non è installato come package: raggiunge `extraction/` inserendo la root del progetto in `sys.path` (`edge-agent/local_extraction_client.py:17-19`), e `main.py --gui` fa l'inverso (`main.py:16-19`).

```
poc-data-extraction/
  main.py                      # Shim di ingresso: carica .env, `from extraction import *`; default = CLI batch, --gui = edge-agent
  gui_app.py                   # Entry point GUI Tkinter (campo API key, dropdown provider/modello, batch + export)
  run_edge_agent.bat           # Launcher Windows: bootstrap auto-riparante della .venv (preferisce Python 3.13) + avvio edge-agent
  claude_.bat                  # Helper di sviluppo (non tracciato): avvia Claude Code con il flag agent-teams
  requirements.txt             # Unica lista dipendenze per tutto (vincoli laschi, non pinnata)
  prompt_store.py              # Loader del catalogo prompt: solo stdlib, fuori da extraction/ per non tirarsi dietro LangChain
  prompts/                     # Catalogo prompt LLM: un JSON per prompt, letto e validato una volta all'avvio
  .env.example                 # Template delle env var (commenti in italiano); da copiare in .env
  .env                         # Segreti locali (in gitignore, presente solo in locale)
  .gitignore                   # Esclude .env*, /mnt, .venv/, build/, dist/, *.spec, src/, temp_uploads/, test_no_gt/
  CLAUDE.md                    # Guida di progetto per l'assistente AI
  README.md                    # README in italiano, incl. la ricetta di build PyInstaller

  extraction/                  # Package del motore -- pipeline, valutazione, nessuna UI
    __init__.py                # Re-export dell'API pubblica (la superficie di `from extraction import *`)
    config.py                  # TUTTE le letture di env var della pipeline + coordinate crop, pricing, mappe aree di retry
    fields.py                  # FIELD_KEYS (45 chiavi), mappatura CSV_TO_SCHEMA per la ground truth
    field_definitions.py       # Display-name canonico + page_key per ogni chiave schema
    page_definitions.py        # Chiavi/nomi canonici delle pagine e ordine dei fogli (4 pagine)
    canonical_mapping.py       # build_canonical_field_entries() -- forma di output client-facing
    schemas.py                 # Modelli Pydantic: ExtractionResponse, AnchorResponse, FieldResult, ...
    prompts.py                 # Costanti dei prompt VLM (main, anchor, 3 retry per area) lette da prompts/*.json
    normalization.py           # Normalizzazione testo, classify_field(), pick_best(), dataset_mismatch_guard()
    imaging.py                 # normalize_image(), crop_relative(), codifica PNG, salvataggio debug crop
    vlm_client.py              # call_vlm() / call_vlm_with_retry(), stima costi, percorsi schema Gemini
    llm_factory.py             # create_chat_model() -- l'unica factory di provider LLM (legge LLM_API_KEY)
    pipeline.py                # ExtractionPipeline: orchestrazione anchor -> main -> retry
    evaluation.py              # Loader ground truth, eval_outputs(), report di debug, riepilogo costi
    cli.py                     # main() CLI + BatchRunner + run_extraction_batch() (condiviso con la GUI Tkinter)

  edge-agent/                  # App PyQt6 di cattura live (import a nome piatto; richiede edge-agent/ in sys.path)
    edge_agent.py              # Entry point Qt: carica .env, tema qt-material, AgentConfig, MainWindow
    config.py                  # AgentConfig: parsa config.ini con default per singola chiave
    config.ini                 # INI committato -- l'intera configurazione dell'edge-agent (vedi sotto)
    local_extraction_client.py # Ponte QObject: ingest_frame() -> ExtractionPipeline, segnale result_ready
    llm_router.py              # PageRouter base + LLMPageRouter (OpenAI Vision) + MLPageRouter
    page_classifier.py         # BPERPagePrototypeClassifier -- prototype matching DINOv2 ViT-S/14
    image_ops.py               # preprocess_for_ocr() (scala/unsharp/autocontrast), encoder png8/webp
    frame_normalize.py         # normalize_frame(): dal monitor intero alla finestra applicativa
    ui/
      main_window.py           # Tab: Cattura, Risultati, Dati Estratti (+ Debug LLM con --debug)
      capture_tab.py           # Start/stop, combo modalità, FPS, cattura forzata, log, export CSV
      extraction_results_tab.py# Albero pagine + tabella campi + JSON grezzo per risultato
      data_table_tab.py        # Vista a foglio di calcolo: righe = schermate, colonne = campi canonici
      debug_tab.py             # Visualizzatore prompt/risposta del router LLM
      overlay.py               # Bordo rosso sul monitor catturato
    workers/capture/
      base_capture_worker.py   # Loop FPS su QThread; segnali tick / error / llm_debug
      bper_capture_worker.py   # Flusso BPER: dedup pHash, routing pagina, stabilità, ingest_frame()
      default_capture_worker.py# Flusso generico: POST di frame grezzi a un'API remota (nessun backend nel repo)
    assets/templates/bper/
      prompts.json             # 10 definizioni di pagina BPER -- fonte di verità per routing LLM + combo UI
      bper_page_prototypes.json# Embedding prototipo DINOv2 in cache per il router ML
      screen 1..9.png          # Screenshot template (sorgenti dei prototipi)
      transitions/             # Screenshot di riferimento di pagine BPER intermedie (non letti dal codice)

  mnt/data/                    # Directory dati (INPUT_DIR di default); /mnt è in gitignore, i PNG sono stati forzati
    screen 1..9.png            # I 9 screenshot di test (tracciati)
    dati.csv                   # CSV di ground truth -- ATTESO qui ma NON nel repository (vedi sotto)
    poc_outputs_improved.json  # Output CLI (generato a runtime)
    poc_debug_improved.csv     # Report di debug CLI (generato a runtime)
    debug_crops/               # Crop intermedi, solo con DEBUG_SAVE_CROPS=1

  docs/                  # Questa documentazione narrativa in italiano (INDEX + doc 00-12)
  .codebase-map/               # Mappa del codebase generata automaticamente (controparti inglesi)
  .claude/                     # Impostazioni locali Claude Code (solo settings.local.json)
  .idea/                       # File di progetto PyCharm
  .venv/                       # Virtualenv locale (in gitignore; creato da run_edge_agent.bat)
```

## File di configurazione

### Configurazione dell'applicazione

- **`.env.example`** (committato) -- il template delle variabili d'ambiente della pipeline, con commenti in italiano. Copialo in `.env` e imposta `LLM_API_KEY`; tutto il resto ha un default funzionante. Documenta 10 delle 12 variabili vive -- mancano `DEBUG_MODE` e i fallback legacy delle chiavi (vedi la tabella più avanti). **`.env`** è in gitignore (`.gitignore:12-14`) e viene caricato automaticamente da `main.py:7`, `edge-agent/edge_agent.py:9-13` e `edge-agent/local_extraction_client.py:21-25` -- ma **non** da `gui_app.py`, che non chiama `load_dotenv` e conta su variabili già esportate nella shell (oppure sulla API key digitata nella sua UI).

- **`edge-agent/config.ini`** (committato, tracciato) -- l'intera configurazione dell'edge-agent, parsata da `AgentConfig` (`edge-agent/config.py:109-269`). Le chiavi mancanti ricadono su default per singola chiave, quindi il file funziona out of the box tranne che per la chiave del router LLM. Sezioni:
  - `[agent]` -- la sezione viva. `fps` (frequenza di cattura), `router = ml` (modalità di routing pagina: `ml` | `llm` | `hybrid`), `monitor_index = 1` (numerazione monitor di mss, 1..N), `show_capture_border = true` (overlay rosso), `route_retry_seconds = 1.0` (throttle del routing sui frame duplicati), `window_title_contains = BPER` (usata da `frame_normalize.find_window_rect()` per ritagliare il frame sulla finestra applicativa dopo la cattura del monitor intero). La sezione accetta anche chiavi di preprocessing non presenti nel file committato (`image_scale`, `unsharp_amount`, `unsharp_radius`, `unsharp_threshold`, `upload_format`, `dedup_threshold`, `required_pages_only`, `required_pages_csv` -- default in `edge-agent/config.py:39-49`).
  - `[llm]` -- il router di pagina in modalità `llm`, inattivo con la configurazione spedita (`router = ml`): `provider = gemini`, `base_url = https://generativelanguage.googleapis.com/v1beta/openai/` (endpoint OpenAI-compatibile di Google), `model = gemini-3.6-flash`, `timeout = 60` e `api_key` **vuota**. La risoluzione avviene in `AgentConfig.resolve_llm_settings()` ed è consapevole del provider: i valori INI espliciti sono autorevoli, i default del provider riempiono solo le voci vuote, e la chiave si cerca come `config.ini [llm] api_key` → (per `gemini`) `GEMINI_API_KEY` → `GOOGLE_API_KEY` → `LLM_API_KEY`, oppure (per `openai`) `OPENAI_API_KEY` → `LLM_API_KEY`. Il ripiego su ambiente scatta **solo se il valore INI è vuoto**, e un valore che inizi per `REDACTED` conta come vuoto. Qui era stata esposta una chiave reale, rimossa dall'intera cronologia git il 2026-07-21. Attenzione anche a `AgentConfig.save()`: riscriverebbe nel file tracciato qualunque chiave sia in memoria (`edge-agent/config.py:326-332`) -- oggi non ha chiamanti, ma è un motivo in più per tenere la chiave fuori dall'INI.
  - `[api]` -- `base_url = http://localhost:8081`. Usata **solo** dalla modalità di cattura legacy "Generico" (`edge-agent/workers/capture/default_capture_worker.py:62-66`); nessun backend simile esiste in questo repo. Inerte nel flusso BPER di default.
  - `[minio]` -- endpoint/credenziali/bucket che puntano a `http://localhost:9000`. Residuo del backend remoto rimosso; nessun percorso di codice attivo la usa.
  - `[dataset]` -- `enabled = true` più soglie, ma il codice consumatore è uno stub no-op (`edge-agent/workers/capture/bper_capture_worker.py:713-715`). Inerte.
  - `[debug]` -- `show_llm_tab = true` abilita l'emissione del segnale `llm_debug`; il tab Debug LLM richiede in aggiunta il flag CLI `--debug` (`edge-agent/edge_agent.py:51`). Servono entrambi per vedere il traffico del router.

- **`edge-agent/assets/templates/bper/prompts.json`** (committato) -- 10 definizioni di pagina BPER (nome, indizi visivi, campi attesi), incluso il catch-all "Altro / Non riconosciuto". Il file è letto indipendentemente da tre consumatori: il router LLM (`edge-agent/llm_router.py:96-103`), la sequenza pagine del capture worker (`edge-agent/workers/capture/bper_capture_worker.py:255-306`) e la combo di cattura forzata nella UI (`edge-agent/ui/capture_tab.py:156-170`). Modificandolo cambiano tutti e tre insieme -- ma non c'è validazione di schema, quindi un refuso degrada il routing in silenzio.

- **`edge-agent/assets/templates/bper/bper_page_prototypes.json`** (non tracciato, rigenerato) -- embedding prototipo DINOv2 in cache per il router ML. La cache è valida solo se coincidono **sia** l'hash del dataset (nome page_type + nome file + digest del contenuto) **sia** `embedding_geometry()`, che descrive modello, ROI, resize e regola di punteggio. Cambiando una qualsiasi delle due, i prototipi si ricostruiscono al primo avvio. Senza la seconda condizione la cache servirebbe in silenzio vettori costruiti con una geometria diversa da quella delle query ([ADR 0003](adr/0003-chiave-cache-prototipi-con-geometria.md)).

### Build / tooling

- **`requirements.txt`** -- l'unico manifesto delle dipendenze, condiviso dai tre front-end. Versioni con vincoli laschi, nessun lock file. `streamlit` è elencato ma orfano (il suo importatore, il vecchio `app.py`, è stato eliminato). `torch`/`torchvision` sono le installazioni pesanti e servono solo al router ML di pagina, che degrada con grazia a disabilitato se mancano (`edge-agent/page_classifier.py:9-19`).
- **`run_edge_agent.bat`** -- vedi Script più avanti; è di fatto anche lo strumento di setup ambiente su Windows.
- Non esistono linter, formatter, pytest, tox, pre-commit, Dockerfile né workflow CI in nessun punto del repo.

### Editor / IDE

- **`.claude/settings.local.json`** -- solo impostazioni di permesso locali di Claude Code.
- **`.idea/`** -- metadati di progetto PyCharm; `.idea/.gitignore` esclude le parti volatili.

### Committato vs. gitignore

Committati: `.env.example`, `edge-agent/config.ini`, i due JSON di asset, `requirements.txt`, i 9 screenshot sotto `mnt/data/` (forzati oltre la regola di ignore su `/mnt`). In gitignore (`.gitignore`): `.env` e varianti, `/mnt` (così gli output di runtime e `dati.csv` non finiscono mai in git), `.venv/`, `__pycache__/`, `build/`, `dist/`, `*.spec`, `src/`, `temp_uploads/`, `test_no_gt/`.

## Variabili d'ambiente

Tutte le variabili della pipeline sono lette via `os.getenv()` **al momento dell'import del modulo** in `extraction/config.py` -- vengono fotografate in costanti quando `extraction` viene importato la prima volta. Conseguenze: (a) vanno impostate prima di qualsiasi `import extraction`, ed è per questo che ogni entry point tranne `gui_app.py` chiama prima `load_dotenv()`; (b) valori numerici malformati (`PARALLEL_WORKERS`, `MAX_CALLS_PER_SCREEN`, `ANCHOR_CONF_MIN`) sollevano `ValueError` all'import, non all'uso (`extraction/config.py:10,58,102`).

| Variabile | Default | Obbligatoria | Scopo | Letta in |
|---|---|---|---|---|
| `LLM_API_KEY` | -- | **sì** (a meno di digitarla nella GUI Tkinter o di avere una var legacy) | Credenziale API per OpenAI o Gemini | `extraction/llm_factory.py:30`; precompilazione GUI `gui_app.py:24` |
| `OPENAI_API_KEY` | -- | no | Fallback legacy per `LLM_API_KEY` (emette `DeprecationWarning`); anche seconda scelta per la chiave del router edge-agent | `extraction/llm_factory.py:32-40`; `edge-agent/workers/capture/bper_capture_worker.py:122,147` |
| `GEMINI_API_KEY` | -- | no | Fallback legacy quando `LLM_PROVIDER=gemini` (emette `DeprecationWarning`) | `extraction/llm_factory.py:10-13,32-40` |
| `LLM_PROVIDER` | `openai` | no | Selettore di provider: `openai` o `gemini` | `extraction/config.py:17` |
| `LLM_MODEL` | `gpt-4o` | no | Modello per il passaggio principale | `extraction/config.py:18` |
| `LLM_MODEL_ANCHOR` | = `LLM_MODEL` | no | Modello per il passaggio anchor | `extraction/config.py:19` |
| `LLM_THINKING_LEVEL` | non impostata | no | `low`/`medium`/`high`; applicata solo se il nome modello contiene `thinking` | `extraction/config.py:20`, `extraction/llm_factory.py:72-74` |
| `INPUT_DIR` | `mnt/data` | no | Directory dati: screenshot, `dati.csv`, output CLI | `extraction/config.py:8` |
| `PARALLEL_ENABLED` | `1` | no | `0` disabilita il thread pool del batch | `extraction/config.py:12` |
| `PARALLEL_WORKERS` | `4` | no | Dimensione del thread pool batch | `extraction/config.py:11` |
| `MAX_CALLS_PER_SCREEN` | `2 + len(AREA_TO_FIELDS)` (= `5`) | no | Tetto duro di chiamate VLM per screenshot (1 anchor + 1 main + un retry per area). Il default è derivato: abbassarlo affama le aree in coda a `AREA_TO_FIELDS` | `extraction/config.py:102-103` |
| `ANCHOR_CONF_MIN` | `0.95` | no | Soglia di confidenza del passaggio anchor -- azzeramento previsto ma oggi senza effetto pratico nella pipeline (vedi [Flussi di lavoro](05-workflows.md)) | `extraction/config.py:56` |
| `STOP_ON_ANCHOR_UNCERTAIN` | `0` | no | `1` = abbandona in anticipo una schermata quando entrambi gli anchor sono null | `extraction/config.py:55` |
| `DEBUG_MODE` | `0` | no | Log `[DEBUG]` verboso nel batch runner. **Non documentata** in `.env.example` né in `CLAUDE.md` -- il codice è l'unica fonte | `extraction/config.py:92` |
| `DEBUG_SAVE_CROPS` | `0` | no | Salva i crop intermedi in `INPUT_DIR/debug_crops` | `extraction/config.py:93-94` |
| `PROMPTS_DIR` | *(non impostata)* | no | Percorso alternativo del catalogo prompt. È l'unica variabile della pipeline letta **fuori** da `config.py`; se impostata diventa l'unico candidato, senza fallback sulla copia nel bundle | `prompt_store.py:222` |

Due non-variabili da conoscere: `SCREENSHOT_DIR` compare nella tabella di `CLAUDE.md` ma da nessuna parte nel codice (grep conferma -- è inerte, e non è più nemmeno in `.env.example`), e l'edge-agent non ha **nessuna** env var dedicata: è configurato da `config.ini`, con fallback su `OPENAI_API_KEY`/`LLM_API_KEY` solo per la chiave del router.

Setup locale: `Copy-Item .env.example .env` (o `cp` su POSIX), imposta `LLM_API_KEY`, e -- per Gemini -- imposta `LLM_PROVIDER=gemini` più un modello Gemini in `LLM_MODEL` (i nomi modello incrociati tra provider vengono rifiutati all'avvio, `extraction/llm_factory.py:49-63`).

## Script ed eseguibili

Non esiste un registro di script; questi sono tutti gli eseguibili del repo.

### Sviluppo / esecuzione

- `python main.py` -- estrazione batch CLI + valutazione. Richiede obbligatoriamente `mnt/data/dati.csv` (`extraction/cli.py:315-316` solleva `FileNotFoundError` -- garantito su un clone fresco, perché il file non è tracciato) e una `LLM_API_KEY` valida. Elabora ogni `.png`/`.jpg`/`.jpeg` in `INPUT_DIR` (ordinati lessicalmente), poi scrive `mnt/data/poc_outputs_improved.json` e `mnt/data/poc_debug_improved.csv` e stampa le accuratezze RAW/FILTERED più la tabella dei costi per schermata (`extraction/cli.py:333-352`).
- `python main.py --gui` -- stesso shim, ma inserisce `edge-agent/` in `sys.path` e avvia l'edge-agent (`main.py:15-20`).
- `python gui_app.py` -- GUI desktop Tkinter. Esegue `run_extraction_batch()` su un thread in background; scrive `poc_outputs_gui.json`, `poc_results_gui.csv` e (se è stato selezionato un CSV di ground truth) `poc_debug_gui.csv` nella **directory di lavoro corrente** (`gui_app.py:250-273`), non in `INPUT_DIR`. Ricorda: questo entry point non carica `.env`.
- `python edge-agent/edge_agent.py [--debug]` -- l'edge-agent PyQt6 direttamente. `--debug` aggiunge il tab "Debug LLM" (`edge-agent/edge_agent.py:51`).
- `run_edge_agent.bat [--debug]` -- launcher Windows. Sonda `.venv\Scripts\python.exe` e ricostruisce la venv se il suo interprete di base è sparito (self-heal); alla prima esecuzione crea la venv (preferendo `py -3.13`, poi `py -3.12`, poi `python` -- deliberatamente non il semplice `py -3`, che potrebbe scegliere una 3.14 senza wheel di torch) e installa `requirements.txt`, quindi avvia l'edge-agent inoltrando tutti gli argomenti (`run_edge_agent.bat:19-75`).

### Setup / build

- `py -3.13 -m venv .venv` + `pip install -r requirements.txt` -- setup manuale dell'ambiente (il batch automatizza esattamente questo). torch rende lenta la prima installazione.
- Packaging PyInstaller della GUI Tkinter (documentato in `README.md:91`):

  ```powershell
  pip install pyinstaller
  pyinstaller --noconfirm --onefile --windowed --name "AI_Data_Extractor" --add-data "extraction;extraction" --collect-all langchain_google_genai --collect-all langchain_openai gui_app.py
  ```

  L'output finisce in `dist/AI_Data_Extractor.exe`; `build/`, `dist/` e `*.spec` sono in gitignore.

### Utility

- `claude_.bat` -- wrapper di comodo per Claude Code; non fa parte dell'applicazione.

Non esistono comandi di test, lint, migrazione o deployment -- quell'infrastruttura non esiste.

## Avvio e sequenza di boot

### CLI (`python main.py`)

1. **`main.py`** sopprime gli `UserWarning` di pydantic/langchain (`main.py:3-5`), poi carica `.env` (`main.py:7`).
2. `from extraction import *` -- questo import è il momento della configurazione: `extraction/config.py` fotografa tutte le env var in costanti adesso.
3. `extraction.cli.main()` (`extraction/cli.py:314`): verifica che `GROUND_TRUTH_CSV` esista → carica la ground truth → raccoglie gli screenshot da `INPUT_DIR` → `BatchRunner` costruisce i due ChatModel LangChain condivisi (main + anchor) **una volta sola, prima del pool** (`extraction/cli.py:182-191`) -- una API key mancante/invalida fallisce qui con `ValueError: API key required...` (`extraction/llm_factory.py:41-44`) → `ThreadPoolExecutor` (se `PARALLEL_ENABLED`) esegue `ExtractionPipeline.extract_from_screen()` per immagine → output salvati, valutazione e riepilogo costi stampati.
4. **Verifica di funzionamento:** l'esecuzione termina con le righe `Saved outputs: ...` / `Saved debug report: ...` più le tabelle di accuratezza e costo su stdout.

### GUI Tkinter (`python gui_app.py`)

1. L'import del modulo trascina subito `extraction` (`gui_app.py:6-14`) -- **senza** `load_dotenv`, quindi esporta prima le env var nella shell oppure affidati al campo API key in-app (precompilato da `LLM_API_KEY`, poi `OPENAI_API_KEY`, `gui_app.py:24`).
2. La finestra si apre con i dropdown provider/modello alimentati da `PROVIDER_MODELS` (`extraction/config.py:22-33`). L'estrazione parte solo alla pressione del pulsante; la costruzione dei modelli (e quindi la validazione della chiave) avviene dentro `run_extraction_batch()` in quel momento.
3. **Verifica:** l'albero dei risultati si popola, il pannello di riepilogo mostra accuratezza/costi, i file di output compaiono nella directory di lavoro.

### Edge-agent (`python edge-agent/edge_agent.py`, `run_edge_agent.bat`, oppure `python main.py --gui`)

1. **`edge-agent/edge_agent.py`** carica la `.env` della root del progetto (`edge-agent/edge_agent.py:9-13`), crea la `QApplication` e applica il tema qt-material `dark_cyan.xml` (opzionale -- saltato se `qt_material` manca).
2. `AgentConfig` parsa `edge-agent/config.ini` (`edge-agent/edge_agent.py:47-48`).
3. Viene costruita `MainWindow` (`edge-agent/edge_agent.py:52`), che costruisce subito `LocalExtractionClient` (`edge-agent/ui/main_window.py:37`), il quale costruisce **entrambi** i ChatModel nel suo `__init__` (`edge-agent/local_extraction_client.py:47-48`). Questo è il punto di fail-fast: senza `LLM_API_KEY` (o var legacy) la finestra non si apre proprio -- l'edge-agent **crasha all'avvio**, non alla prima cattura.
4. Vengono aggiunti i tab: **Cattura**, **Risultati**, **Dati Estratti** e -- solo con `--debug` -- **Debug LLM** (`edge-agent/ui/main_window.py:73-77`). Parte il loop di eventi Qt.
5. L'estrazione inizia quando l'operatore clicca "Avvia": `start_job()` genera un UUID, `BPERCaptureWorker` avvia il suo loop QThread, e ogni pagina stabile e riconosciuta passa per `ingest_frame()`, che accoda il frame e ritorna subito; l'estrazione gira su `PARALLEL_WORKERS` thread daemon che condividono una `ExtractionPipeline`. Con `router = ml` (la configurazione spedita) il riconoscimento è locale e non serve alcuna chiave; con `router = llm` o `hybrid` il router risolve chiave, endpoint e modello per conto proprio via `AgentConfig.resolve_llm_settings()`, e senza chiave restituisce silenziosamente nessun match -- visibile solo nel tab Debug LLM.
6. **Verifica:** il bordo rosso di cattura appare sul monitor configurato, il log di Cattura annuncia le pagine riconosciute, e compaiono righe in Risultati / Dati Estratti man mano che `result_ready` scatta.

### Dipendenze di servizio all'avvio

Solo i provider LLM (OpenAI e/o Google Gemini via HTTPS). Nessun database, nessuna cache, nessun message broker. Lo stack torch/DINOv2 è opzionale -- il classificatore ML di pagina si disabilita da solo se torch non è importabile (`edge-agent/page_classifier.py:9-19`). Alla prima esecuzione del classificatore ML, `torch.hub` scarica il modello DINOv2 ViT-S/14 (serve internet la prima volta; poi resta in cache in `~/.cache/torch/hub/`).

## Porte, URL ed endpoint dei servizi

Questo progetto **non apre nessuna porta in ascolto** e non espone endpoint di health-check o amministrazione. Tutto il traffico di rete è in uscita:

| Endpoint | Usato da | Stato |
|---|---|---|
| `https://api.openai.com/v1` (e l'API Gemini quando `LLM_PROVIDER=gemini`) | Passaggi di estrazione (`extraction/vlm_client.py`) e router LLM di pagina (`edge-agent/llm_router.py:200-209`; base URL da `edge-agent/config.ini:20`) | Attivo |
| `http://localhost:8081` -- `POST {base_url}/jobs/{job_id}/frames` | Solo modalità di cattura "Generico" (`edge-agent/workers/capture/default_capture_worker.py:62-66`; URL da `edge-agent/config.ini:10`) | Morto -- nessun backend esiste in questo repo |
| `http://localhost:9000` (MinIO) | Niente -- la config `[minio]` è un residuo del backend remoto rimosso | Morto |

Per confermare che l'app è in salute si leggono i suoi output, non una porta: la CLI stampa il report su stdout, le GUI mostrano i risultati nei loro tab, e `DEBUG_MODE=1` / `DEBUG_SAVE_CROPS=1` / `--debug` sono le leve diagnostiche (vedi [Come iniziare](07-getting-started.md) per la prima esecuzione e [Architettura](04-architecture.md) per come i pezzi si connettono). Le ricette di configurazione per gli scenari comuni sono nella [Guida alla configurazione](10-configuration-guide.md).
