# Anatomia del progetto

Questa è la mappa operativa di `poc-data-extraction`: moduli, configurazione, comandi e avvio. Per il design vedi [Architettura](04-architecture.md), per il setup [Come iniziare](07-getting-started.md), per firme e segnali le [API Python](12-python-api.md).

Tre fatti orientano la lettura di tutto il resto:

- **Gli entry point sono script Python**, con launcher Windows `run_edge_agent.bat` e build portable `build_exe.bat` + `edge_agent.spec`. `pyproject.toml` registra solo i marker pytest; non esistono metadati di build, `Makefile` o `setup.py`.
- **Esiste una suite pytest** in `tests/`, con dipendenza di sviluppo in `requirements-dev.txt`. CI e Docker restano assenti; l’accuratezza con provider reali richiede una baseline esterna.
- **Coesistono due sistemi di configurazione:** ambiente per il motore, INI per cattura e routing. Il router risolve chiave, endpoint e modello tramite `AgentConfig.resolve_llm_settings()` con fallback ambientali; il motore continua a leggere le proprie variabili.

## Albero delle directory

Il repository raccoglie i sorgenti in **`src/`** (`src/extraction/`, `src/edge-agent/`, `src/training/`, `src/prompt_store.py`) più gli entry point alla radice (`main.py`, `gui_app.py`, `run_edge_agent.bat`, `build_exe.bat`, `edge_agent.spec`). L'edge-agent raggiunge `src/` inserendolo in `sys.path` tramite `app_paths.src_dir()` (`src/edge-agent/local_extraction_client.py:18-20`), mentre `main.py` e `gui_app.py` inseriscono `src/` (e `src/edge-agent/` con `--gui`) all'avvio.

```
poc-data-src/extraction/
  main.py                      # Shim di ingresso: aggiunge src/ a sys.path, carica .env, `from extraction import *`; --gui avvia l'edge-agent
  gui_app.py                   # Entry point GUI Tkinter (aggiunge src/ a sys.path, carica .env prima di extraction)
  run_edge_agent.bat           # Launcher Windows: bootstrap auto-riparante della .venv + avvio src/edge-agent/edge_agent.py
  requirements.txt             # Dipendenze applicative, training offline e PyInstaller (vincoli laschi)
  requirements-dev.txt         # pytest
  pyproject.toml               # Configurazione pytest (pythonpath = ["src", "src/edge-agent"]) e marker slow
  build_exe.bat                # Build e ZIP portable dell’edge-agent
  edge_agent.spec              # Specifica PyInstaller (punta a src/edge-agent/ e src/)
  tests/                       # Suite automatica della logica locale (estrazione, edge-agent, training)
  tools/                       # Script di verifica (check.py) e calibrazione prototipi/frame
  processes/                   # Definizioni JSON del processo BPER (bper-p1.json)
  prompts/                     # Catalogo prompt LLM: un JSON per prompt, letto e validato una volta all'avvio
  .env.example                 # Template delle env var (commenti in italiano); da copiare in .env
  .env                         # Segreti locali (in gitignore, presente solo in locale)
  .gitignore                   # Esclude .env*, /data, .venv/, build/, dist/, *.spec, temp_uploads/, test_no_gt/
  AGENTS.md / CLAUDE.md        # Guide operative e vincoli architetturali per gli assistenti AI
  README.md                    # README in italiano, incl. la ricetta di build PyInstaller

  src/                         # Sorgenti applicativi e di addestramento
    prompt_store.py            # Loader del catalogo prompt: solo stdlib, fuori da src/extraction/ per non tirarsi dietro LangChain
    training/                  # Package offline per dataset supervisionato e addestramento LiLT
      schema.py                # Vocabolario dei 45 campi e 37 ruoli semantici (letto da src/extraction/fields.py)
      alignment.py             # Allineamento dei valori revisionati sui token RapidOCR e geometria delle celle
      dataset.py               # Costruzione bundle train/val/test da Excel v3.1, supervisione e audit anti-leakage
      model.py                 # Chunking senza taglio tabella FIDI, augmentation, training LiLT e inferenza CPU/GPU
      evaluation.py            # Decoder campi e metriche rigorose (disponibilità OCR, F1 parole, accuratezza campi)
      modal_train.py           # Entry point remoto Modal per training GPU e scaricamento cpu_model
      README.md                # Istruzioni per preparazione dataset e training locale/remoto
    extraction/                # Package del motore -- pipeline, valutazione, nessuna UI
      __init__.py              # Re-export dell'API pubblica (la superficie di `from extraction import *`)
      config.py                # Configurazione import-time della pipeline + coordinate crop, pricing, mappe aree di retry
      fields.py                # FIELD_KEYS (45 chiavi), mappatura CSV_TO_SCHEMA per la ground truth
      field_definitions.py     # Display-name canonico + page_key per ogni chiave schema
      page_definitions.py      # Chiavi/nomi canonici delle pagine e cinque pagine sorgenti e quattro gruppi export
      canonical_mapping.py     # build_canonical_field_entries() -- forma di output client-facing
      schemas.py               # Modelli Pydantic: ExtractionResponse, AnchorResponse, FieldResult, ...
      prompts.py               # Costanti dei prompt VLM (main, anchor, 3 retry per area) lette da prompts/*.json
      normalization.py         # Normalizzazione testo, classify_field(), pick_best(), dataset_mismatch_guard()
      imaging.py               # normalize_image(), crop_relative(), codifica PNG, salvataggio debug crop
      vlm_client.py            # call_vlm() / call_vlm_with_retry(), stima costi, percorsi schema Gemini
      llm_factory.py           # create_chat_model() -- l'unica factory di provider LLM (legge LLM_API_KEY)
      model_adapters.py        # Adapter per famiglia di modelli (OpenAI, Gemini 1.5/2.x/3.x)
      pipeline.py              # ExtractionPipeline: orchestrazione anchor -> main -> retry
      evaluation.py            # Loader ground truth, eval_outputs(), report di debug, riepilogo costi
      cli.py                   # main() CLI + BatchRunner + run_extraction_batch() (condiviso con la GUI Tkinter)
    edge-agent/                # App PyQt6 di cattura live (import a nome piatto; richiede src/edge-agent/ in sys.path)
      edge_agent.py            # Entry point Qt: carica .env, applica il tema (theme.py), AgentConfig, MainWindow
      config.py                # AgentConfig: parsa config.ini con default per singola chiave
      config.ini               # INI committato -- l'intera configurazione dell'edge-agent (vedi sotto)
      local_extraction_client.py # Accoda frame e pubblica risultati in ordine di acquisizione
      extraction_pool.py       # Pool di estrazione daemon
      practice_consolidation.py# Raggruppa frame per NDG, una pratica per riga
      excel_export.py          # Workbook con intestazione a due livelli
      app_paths.py             # Percorsi da sorgente e bundle
      bootstrap.py             # Preflight prima dell’import della UI
      error_report.py          # sys.excepthook: un errore in uno slot Qt viene registrato e mostrato, non chiude l'app
      llm_router.py            # PageRouter base + LLMPageRouter (OpenAI Vision) + MLPageRouter
      page_classifier.py       # BPERPagePrototypeClassifier -- prototype matching DINOv2 ViT-S/14
      image_ops.py             # preprocess_for_ocr() (scala/unsharp/autocontrast), encoder png8/webp
      frame_normalize.py       # normalize_frame(): dal monitor intero alla finestra applicativa
      theme.py                 # Token di colore, stylesheet, chiaro/scuro come Windows (top-level: non importa ui né extraction)
      ui/
        main_window.py         # Navigazione laterale, barra di stato (Avvia/Ferma), pagine Cattura e Dati (+ Debug LLM con --debug), avviso alla chiusura
        shell.py               # NavRail e StatusHeader
        widgets.py             # Card, CollapsiblePanel, nome file di export
        icons.py               # Icone SVG (Lucide) colorate al momento del disegno
        capture_tab.py         # Impostazioni, scatto manuale accodato, export, registro richiudibile
        data_table_tab.py      # Vista a foglio: righe = pratiche, colonne = campi canonici, ricerca, correzione dei valori
        frozen_table.py        # Tabella con le prime colonne fisse (NDG e denominazione)
        debug_tab.py           # Visualizzatore prompt/risposta del router LLM
        overlay.py             # Bordo rosso sul monitor catturato
      workers/capture/
        base_capture_worker.py # Loop FPS su QThread; segnali tick / error / llm_debug
        bper_capture_worker.py # Flusso BPER: dedup pHash, routing pagina, stabilità, ingest_frame()
        default_capture_worker.py # Flusso generico: POST di frame grezzi a un'API remota (nessun backend nel repo)
      assets/templates/bper/
        prompts.json           # 10 definizioni di pagina BPER -- fonte di verità per routing LLM + combo UI
        bper_page_prototypes.json # Prototipi DINOv2 delle pagine, distribuiti con l'app (ADR 0030)

  data/                        # Dati versionati in git (ADR 0032): solo l'archivio pulito data/dataset
    README.md                  # Mappa dell'archivio
    dataset/                   # Archivio pulito (ADR 0032): pratiche/<id>/<pagina>-<NN>.png (INPUT_DIR predefinito: pratiche/51350695),
                               # valori.csv, schermate.csv, pratiche.csv

  docs/                  # Questa documentazione narrativa in italiano (INDEX + doc 00-12)
  .claude/                     # Impostazioni locali Claude Code (solo settings.local.json)
  .idea/                       # File di progetto PyCharm
  .venv/                       # Virtualenv locale (in gitignore; creato da run_edge_agent.bat)
```

## File di configurazione

### Configurazione dell'applicazione

- **`.env.example`** (committato) -- il template delle variabili d'ambiente della pipeline, con commenti in italiano. Copialo in `.env` e imposta `LLM_API_KEY`; tutto il resto ha un default funzionante. La tabella più avanti include anche le variabili lette dal codice che il template non elenca. **`.env`** è in gitignore (`.gitignore:12-14`) e viene caricato automaticamente da `main.py:7`, `src/edge-agent/edge_agent.py:9-13` e `src/edge-agent/local_extraction_client.py:21-25` e da `gui_app.py`, che carica dotenv prima di importare il motore. La GUI consente anche di digitare la chiave nella sua UI.

- **`src/edge-agent/config.ini`** (committato, tracciato) -- l'intera configurazione dell'edge-agent, parsata da `AgentConfig` (`src/edge-agent/config.py:109-269`). Le chiavi mancanti ricadono su default per singola chiave; le credenziali restano esterne al file. Sezioni:
  - `[agent]` -- la sezione viva. `fps` (frequenza di cattura), `router = llm` (modalità di routing pagina: `ml` | `llm` | `hybrid` | `local-first`), `monitor_index = 1` (numerazione monitor di mss, 1..N), `show_capture_border = true` (overlay rosso), `route_retry_seconds = 1.0` (throttle del routing sui frame duplicati), `window_title_contains = BPER` (usata da `frame_normalize.find_window_rect()` per ritagliare il frame sulla finestra applicativa dopo la cattura del monitor intero). La sezione accetta anche chiavi di preprocessing non presenti nel file committato (`image_scale`, `unsharp_amount`, `unsharp_radius`, `unsharp_threshold`, `upload_format`, `dedup_threshold`, `required_pages_only`, `required_pages_csv` -- default in `src/edge-agent/config.py:39-49`).
  - `[llm]` -- il router di pagina in modalità `llm`, attivo con la configurazione spedita (`router = llm`): `provider = gemini`, `base_url = https://generativelanguage.googleapis.com/v1beta/openai/` (endpoint OpenAI-compatibile di Google), `model = gemini-3.8-flash`, `timeout = 60` e `api_key` **vuota**. La risoluzione avviene in `AgentConfig.resolve_llm_settings()` ed è consapevole del provider: i valori INI espliciti sono autorevoli, i default del provider riempiono solo le voci vuote, e la chiave si cerca come `config.ini [llm] api_key` → (per `gemini`) `GEMINI_API_KEY` → `GOOGLE_API_KEY` → `LLM_API_KEY`, oppure (per `openai`) `OPENAI_API_KEY` → `LLM_API_KEY`. Il ripiego su ambiente scatta **solo se il valore INI è vuoto**, e un valore che inizi per `REDACTED` conta come vuoto. Qui era stata esposta una chiave reale, rimossa dall'intera cronologia git il 2026-07-21. Attenzione anche a `AgentConfig.save()`: riscriverebbe nel file tracciato qualunque chiave sia in memoria (`src/edge-agent/config.py:326-332`) -- oggi non ha chiamanti, ma è un motivo in più per tenere la chiave fuori dall'INI.
  - `[api]` -- `base_url = http://localhost:8081`. Usata **solo** dalla modalità di cattura legacy "Generico" (`src/edge-agent/workers/capture/default_capture_worker.py:62-66`); nessun backend simile esiste in questo repo. Inerte nel flusso BPER di default.
  - `[minio]` -- endpoint/credenziali/bucket che puntano a `http://localhost:9000`. Residuo del backend remoto rimosso; nessun percorso di codice attivo la usa.
  - `[dataset]` -- `enabled = true` più soglie, ma il codice consumatore è uno stub no-op (`src/edge-agent/workers/capture/bper_capture_worker.py:713-715`). Inerte.
  - `[debug]` -- `show_llm_tab = true` abilita l'emissione del segnale `llm_debug`; il tab Debug LLM richiede in aggiunta il flag CLI `--debug` (`src/edge-agent/edge_agent.py:51`). Servono entrambi per vedere il traffico del router.

- **`src/edge-agent/assets/templates/bper/prompts.json`** -- catalogo delle pagine, distinto dai prompt di estrazione. `PageRegistry.load()` valida nomi, ordine e template, condividendo identità e ordinamento tra worker e combo UI. Il router LLM legge anche indizi e campi attesi. Se il registro non si carica, worker e UI gestiscono l’errore e usano un registro vuoto; il catalogo LLM `prompts/*.json` resta invece fail-fast. Non sono più lette sequenze da XLSX o CSV.

- **`src/edge-agent/assets/templates/bper/bper_page_prototypes.json`** (tracciato, distribuito con l'app) -- i prototipi DINOv2 delle 9 pagine e delle 3 classi di scarto, costruiti fuori dall'app da `tools/build_prototypes.py` (ADR 0030). L'app li carica e non legge immagini; li rifiuta se la loro `embedding_geometry()`, che descrive modello, ROI, resize e regola di punteggio, non coincide con quella del codice. Senza la seconda condizione la cache servirebbe in silenzio vettori costruiti con una geometria diversa da quella delle query ([ADR 0003](adr/0003-chiave-cache-prototipi-con-geometria.md)).

### Build / tooling

- **`requirements.txt`** -- il manifesto delle dipendenze applicative, condiviso dai tre front-end. Versioni con vincoli laschi, nessun lock file. `streamlit` è stato rimosso; PyInstaller è presente per la build. `torch`/`torchvision` sono le installazioni pesanti e servono solo al router ML di pagina, che degrada con grazia a disabilitato se mancano (`src/edge-agent/page_classifier.py:9-19`).
- **`run_edge_agent.bat`** -- vedi Script più avanti; è di fatto anche lo strumento di setup ambiente su Windows.
- **`requirements-dev.txt`** installa pytest; esegui `python -m pytest tests`. Non sono configurati linter, formatter, tox, pre-commit, Docker o CI.

### Editor / IDE

- **`.claude/settings.local.json`** -- solo impostazioni di permesso locali di Claude Code.
- **`.idea/`** -- metadati di progetto PyCharm; `.idea/.gitignore` esclude le parti volatili.

### Committato vs. gitignore

Committati: `.env.example`, `src/edge-agent/config.ini`, il catalogo delle pagine e i JSON dei prompt, `requirements.txt`, `data/` per intero, salvo i pesi dei modelli. In gitignore (`.gitignore`): `.env` e varianti, `*.safetensors`, `/outputs/` (risultati della CLI), `.venv/`, `__pycache__/`, `build/`, `dist/`, `*.spec` (salvo `edge_agent.spec`), `temp_uploads/`, `test_no_gt/`, `.tritech/local/`.

## Variabili d'ambiente

Tutte le variabili della pipeline sono lette via `os.getenv()` **al momento dell'import del modulo** in `src/extraction/config.py` -- vengono fotografate in costanti quando `extraction` viene importato la prima volta. Conseguenze: (a) vanno impostate prima di qualsiasi `import extraction`, ed è per questo che gli entry point CLI e Tkinter chiamano prima `load_dotenv()`, mentre l’edge-agent completa il preflight prima di importare il motore; (b) valori numerici malformati (`PARALLEL_WORKERS`, `MAX_CALLS_PER_SCREEN`, `ANCHOR_CONF_MIN`) sollevano `ValueError` all'import, non all'uso (`src/extraction/config.py:10,58,102`).

| Variabile | Default | Obbligatoria | Scopo | Letta in |
|---|---|---|---|---|
| `LLM_API_KEY` | -- | **sì** (a meno di digitarla nella GUI Tkinter o di avere una var legacy) | Credenziale API per OpenAI o Gemini | `src/extraction/llm_factory.py:30`; precompilazione GUI `gui_app.py:24` |
| `OPENAI_API_KEY` | -- | no | Fallback legacy per `LLM_API_KEY` (emette `DeprecationWarning`); anche seconda scelta per la chiave del router edge-agent | `src/extraction/llm_factory.py:32-40`; `src/edge-agent/workers/capture/bper_capture_worker.py:122,147` |
| `GOOGLE_API_KEY` | -- | no | Fallback della chiave del router Gemini, dopo `GEMINI_API_KEY` | `src/edge-agent/config.py` |
| `TORCH_HOME` | cache torch utente; nel portable cache locale se non impostata | no | Directory dei pesi, configurata da `bootstrap.py` | `src/edge-agent/bootstrap.py`, `src/edge-agent/app_paths.py` |
| `EDGE_AGENT_SMOKE` | non impostata | no | Con `1` evita i dialoghi di preflight e chiude automaticamente la finestra dopo 5 secondi; hook di smoke test | `src/edge-agent/bootstrap.py`, `src/edge-agent/edge_agent.py` |
| `GEMINI_API_KEY` | -- | no | Fallback legacy quando `LLM_PROVIDER=gemini` (emette `DeprecationWarning`) | `src/extraction/llm_factory.py:10-13,32-40` |
| `LLM_PROVIDER` | `openai` | no | Selettore di provider: `openai` o `gemini` | `src/extraction/config.py:17` |
| `LLM_MODEL` | `gpt-4o` | no | Modello per il passaggio principale | `src/extraction/config.py:18` |
| `LLM_MODEL_ANCHOR` | = `LLM_MODEL` | no | Modello per il passaggio anchor | `src/extraction/config.py:19` |
| `LLM_THINKING_LEVEL` | non impostata | no | `low`/`medium`/`high`; inviata come `thinking_level` alla famiglia Gemini 3, ignorata con avviso dalle altre, rifiutata se non valida | `src/extraction/config.py:19`, `src/extraction/model_adapters.py:196`, `src/extraction/model_adapters.py:228` |
| `INPUT_DIR` | `data/dataset/pratiche/51350695` | no | Cartella degli screenshot; verità da `dati.csv` o da `valori.csv` (ADR 0032) | `src/extraction/config.py` |
| `OUTPUT_DIR` | `outputs/<cartella di INPUT_DIR>` | no | Risultati della CLI e `debug_crops/` | `src/extraction/config.py` |
| `PARALLEL_ENABLED` | `1` | no | `0` disabilita il thread pool del batch | `src/extraction/config.py:12` |
| `PARALLEL_WORKERS` | `4` | no | Worker del batch e del pool asincrono dell’edge-agent | `src/extraction/config.py`, `src/edge-agent/local_extraction_client.py` |
| `MAX_CALLS_PER_SCREEN` | `2 + len(AREA_TO_FIELDS)` (= `5`) | no | Budget di passaggi: massimo `N - 2` retry per area. Non limita le richieste di rete ritentate dal client; sotto 2 restano anchor e main salvo uscita anticipata | `src/extraction/config.py`, `src/extraction/pipeline.py` |
| `ANCHOR_CONF_MIN` | `0.95` | no | Annulla gli anchor sotto soglia prima di hint, merge ed eventuale uscita anticipata | `src/extraction/config.py`, `src/extraction/pipeline.py` |
| `RETRY_CONF_MIN` | `0.60` | no | Soglia sotto cui un campo seleziona la propria area per retry | `src/extraction/config.py`, `src/extraction/pipeline.py` |
| `MAX_IMAGE_LONG_SIDE` | `2000` | no | Limite del lato lungo all’ingresso di `extract_from_image()`; riduce le immagini più grandi preservando le proporzioni | `src/extraction/config.py`, `src/extraction/imaging.py` |
| `STOP_ON_ANCHOR_UNCERTAIN` | `0` | no | `1` = abbandona in anticipo una schermata quando entrambi gli anchor sono null | `src/extraction/config.py:55` |
| `DEBUG_MODE` | `0` | no | Log `[DEBUG]` verboso nel batch runner | `src/extraction/config.py` |
| `DEBUG_SAVE_CROPS` | `0` | no | Salva i crop intermedi in `INPUT_DIR/debug_crops` | `src/extraction/config.py:93-94` |
| `PROMPTS_DIR` | *(non impostata)* | no | Percorso alternativo del catalogo prompt. È l'unica variabile della pipeline letta **fuori** da `config.py`; se impostata diventa l'unico candidato, senza fallback sulla copia nel bundle | `src/prompt_store.py:222` |

`SCREENSHOT_DIR` non è letto dal codice: usa `INPUT_DIR`. Per il router, `AgentConfig.resolve_llm_settings()` considera anche `GOOGLE_API_KEY` nel ramo Gemini e i default di modello/endpoint per provider descritti nella [Guida alla configurazione](10-configuration-guide.md). `PARALLEL_ENABLED` governa solo il batch: il client live usa sempre il proprio pool.

Setup locale: `Copy-Item .env.example .env` (o `cp` su POSIX), imposta `LLM_API_KEY`, e -- per Gemini -- imposta `LLM_PROVIDER=gemini` più un modello Gemini in `LLM_MODEL` (i nomi modello incrociati tra provider vengono rifiutati all'avvio, `src/extraction/llm_factory.py:49-63`).

## Script ed eseguibili

Non esiste un registro di script; questi sono tutti gli eseguibili del repo.

### Sviluppo / esecuzione

- `python main.py` -- estrazione batch CLI + valutazione. Legge la verità da un `dati.csv` in `INPUT_DIR` o dalle righe della pratica in `data/dataset/valori.csv` (`src/extraction/cli.py::main` solleva `FileNotFoundError` se non trova né l'uno né l'altro) e una `LLM_API_KEY` valida. Elabora ogni `.png`/`.jpg`/`.jpeg` in `INPUT_DIR` (ordinati lessicalmente), poi scrive `poc_outputs_improved.json` e `poc_debug_improved.csv` in `OUTPUT_DIR` e stampa le accuratezze RAW/FILTERED più la tabella dei costi per schermata (`src/extraction/cli.py::main`).
- `python main.py --gui` -- stesso shim, ma inserisce `src/edge-agent/` in `sys.path` e avvia l'edge-agent (`main.py:15-20`).
- `python gui_app.py` -- GUI desktop Tkinter. Esegue `run_extraction_batch()` su un thread in background; scrive `poc_outputs_gui.json`, `poc_results_gui.csv` e (se è stato selezionato un CSV di ground truth) `poc_debug_gui.csv` nella **directory di lavoro corrente** (`gui_app.py:250-273`), non in `INPUT_DIR`. Carica `.env` prima del motore e usa provider/modello effettivi nei selettori iniziali.
- `python src/edge-agent/edge_agent.py [--debug]` -- l'edge-agent PyQt6 direttamente. `--debug` aggiunge il tab "Debug LLM" (`src/edge-agent/edge_agent.py:51`).
- `run_edge_agent.bat [--debug]` -- launcher Windows. Sonda `.venv\Scripts\python.exe` e ricostruisce la venv se il suo interprete di base è sparito (self-heal); alla prima esecuzione crea la venv (preferendo `py -3.13`, poi `py -3.12`, poi `python` -- deliberatamente non il semplice `py -3`, che potrebbe scegliere una 3.14 senza wheel di torch) e installa `requirements.txt`, quindi avvia l'edge-agent inoltrando tutti gli argomenti (`run_edge_agent.bat:19-75`).

### Setup / build

- `py -3.13 -m venv .venv` + `pip install -r requirements.txt` -- setup manuale dell'ambiente (il batch automatizza esattamente questo). torch rende lenta la prima installazione.
- `build_exe.bat` -- costruisce il portable con `edge_agent.spec`, copia configurazione, prompt e asset e genera `dist/EdgeAgent_<data>.zip`. Distribuire tutta la cartella, non il solo eseguibile. Rifiuta un `config.ini` con `api_key` valorizzata; può invece precompilare la chiave nel `.env` del pacchetto tramite `src/edge-agent/env_key.py` (zip `_CON-CHIAVE`).
- `pip install -r requirements-dev.txt` e `python -m pytest tests` -- installazione ed esecuzione della suite completa. `python tools/check.py` seleziona `not slow`, mantenendo i controlli puri della cache ed escludendo le inferenze DINOv2.

### Utility

- `claude_.bat` -- wrapper di comodo per Claude Code; non fa parte dell'applicazione.

Non esistono comandi di lint o migrazione database; il progetto non avvia un server da distribuire.

## Avvio e sequenza di boot

### CLI (`python main.py`)

1. **`main.py`** sopprime gli `UserWarning` di pydantic/langchain (`main.py:3-5`), poi carica `.env` (`main.py:7`).
2. `from extraction import *` -- questo import è il momento della configurazione: `src/extraction/config.py` fotografa tutte le env var in costanti adesso.
3. `extraction.cli.main()` (`src/extraction/cli.py::main`): verifica che `GROUND_TRUTH_CSV` esista → carica la ground truth → raccoglie gli screenshot da `INPUT_DIR` → `BatchRunner` costruisce i due ChatModel LangChain condivisi (main + anchor) **una volta sola, prima del pool** (`src/extraction/cli.py::BatchRunner.__init__`) -- una API key mancante/invalida fallisce qui con `ValueError: API key required...` (`src/extraction/llm_factory.py:41-44`) → `ThreadPoolExecutor` (se `PARALLEL_ENABLED`) esegue `ExtractionPipeline.extract_from_screen()` per immagine → output salvati, valutazione e riepilogo costi stampati.
4. **Verifica di funzionamento:** l'esecuzione termina con le righe `Saved outputs: ...` / `Saved debug report: ...` più le tabelle di accuratezza e costo su stdout.

### GUI Tkinter (`python gui_app.py`)

1. `gui_app.py` carica `.env` prima di importare `extraction`. La configurazione già esportata prevale sul file; la chiave può anche essere inserita nel campo in-app ([ADR 0021](adr/0021-dotenv-prima-del-motore-nella-gui-tkinter.md)).
2. La finestra si apre con provider e modello effettivi e suggerimenti del provider selezionato; la creazione del menu conserva anche un modello configurato fuori catalogo. I suggerimenti sono alimentati da `PROVIDER_MODELS` (`src/extraction/config.py:22-33`). L'estrazione parte solo alla pressione del pulsante; la costruzione dei modelli (e quindi la validazione della chiave) avviene dentro `run_extraction_batch()` in quel momento.
3. **Verifica:** l'albero dei risultati si popola, il pannello di riepilogo mostra accuratezza/costi, i file di output compaiono nella directory di lavoro.

### Edge-agent (`python src/edge-agent/edge_agent.py`, `run_edge_agent.bat`, oppure `python main.py --gui`)

1. `src/edge-agent/edge_agent.py` carica la `.env` risolta da `app_paths` (root da sorgente, accanto all’eseguibile nel portable), crea Qt e applica il tema.
2. `bootstrap.run_preflight()` controlla file, chiave e pesi e restituisce `AgentConfig`; se l’operatore annulla, l’avvio termina. Il preflight può creare o caricare la `.env` al primo avvio.
3. Solo dopo il preflight viene importata `ui.main_window`, che carica il client e quindi la configurazione della pipeline. Spostare questo import prima congelerebbe le variabili d’ambiente troppo presto.
4. `MainWindow` costruisce `LocalExtractionClient` con i due ChatModel e il pool; apre Cattura, Dati Estratti e, con `--debug`, Debug LLM.
5. «Avvia» crea un job e avvia `BPERCaptureWorker`. `ingest_frame()` restituisce subito una sequenza; il pool estrae senza bloccare il loop. `llm`/`hybrid` richiedono anche le credenziali del router; `ml` usa il classificatore locale, ma l’estrazione continua a chiamare il provider via rete.
6. `result_ready` segnala ogni completamento. La tabella legge il prefisso ordinato con `get_results()` e consolida una riga per pratica. Un frame lento può ritardare la visualizzazione dei successivi; un errore libera lo slot e consente al worker di ritentare la visita.

### Dipendenze di servizio all'avvio

Solo i provider LLM (OpenAI e/o Google Gemini via HTTPS). Nessun database o message broker esterno. I pesi e i prototipi usano cache locali. Lo stack torch/DINOv2 è opzionale -- il classificatore ML di pagina si disabilita da solo se torch non è importabile (`src/edge-agent/page_classifier.py:9-19`). Alla prima esecuzione del classificatore ML, `torch.hub` scarica il modello DINOv2 ViT-S/14 (serve internet la prima volta; poi resta in cache in `~/.cache/torch/hub/`).

## Porte, URL ed endpoint dei servizi

Questo progetto **non apre nessuna porta in ascolto** e non espone endpoint di health-check o amministrazione. Tutto il traffico di rete è in uscita:

| Endpoint | Usato da | Stato |
|---|---|---|
| `https://api.openai.com/v1` (e l'API Gemini quando `LLM_PROVIDER=gemini`) | Passaggi di estrazione (`src/extraction/vlm_client.py`) e router LLM di pagina (`src/edge-agent/llm_router.py:200-209`; base URL da `src/edge-agent/config.ini:20`) | Attivo |
| `http://localhost:8081` -- `POST {base_url}/jobs/{job_id}/frames` | Solo modalità di cattura "Generico" (`src/edge-agent/workers/capture/default_capture_worker.py:62-66`; URL da `src/edge-agent/config.ini:10`) | Morto -- nessun backend esiste in questo repo |
| `http://localhost:9000` (MinIO) | Niente -- la config `[minio]` è un residuo del backend remoto rimosso | Morto |

Per confermare che l'app è in salute si leggono i suoi output, non una porta: la CLI stampa il report su stdout, le GUI mostrano i risultati nei loro tab, e `DEBUG_MODE=1` / `DEBUG_SAVE_CROPS=1` / `--debug` sono le leve diagnostiche (vedi [Come iniziare](07-getting-started.md) per la prima esecuzione e [Architettura](04-architecture.md) per come i pezzi si connettono). Le ricette di configurazione per gli scenari comuni sono nella [Guida alla configurazione](10-configuration-guide.md).
