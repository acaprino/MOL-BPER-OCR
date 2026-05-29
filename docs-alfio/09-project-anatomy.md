# Anatomia del progetto

Questo documento è la mappa pratica per configurare, eseguire e orientarsi in `poc-data-extraction`. Copre ogni directory, file di configurazione, variabile d'ambiente, comando eseguibile e comportamento di avvio -- ciò che serve fin dal primo giorno per smettere di tirare a indovinare e iniziare a lavorare. Per il design ad alto livello, vedi [Architettura](04-architecture.md); per il setup passo per passo, vedi [Come iniziare](07-getting-started.md).

## Albero delle directory

```
poc-data-extraction/
  main.py                              # Entry point CLI; il flag --gui avvia l'edge-agent
  gui_app.py                           # GUI desktop Tkinter standalone per estrazione manuale
  requirements.txt                     # Tutte le dipendenze Python (extraction + edge-agent insieme)
  .env.example                         # Template delle variabili d'ambiente (committato)
  .env                                 # Variabili d'ambiente reali con le API key (in gitignore)
  .gitignore                           # Esclude .env, __pycache__, /mnt, build/, dist/, .venv/
  CLAUDE.md                            # Documentazione completa del progetto (276 righe)
  README.md                            # README in italiano con guida all'uso
  prompts_immagini.txt                 # Prompt di generazione immagini solo di riferimento (non usati dalla pipeline)
  extraction/                          # Package Python centrale: tutta la logica di business dell'estrazione
    __init__.py                        # Re-export dell'API pubblica (46 simboli in __all__)
    config.py                          # Config da env-var, coordinate di ritaglio, tabelle di pricing, helper
    fields.py                          # Lista FIELD_KEYS (40+ campi), mappatura CSV_TO_SCHEMA
    field_definitions.py               # Definizioni canoniche dei campi (display_name, page_key)
    page_definitions.py                # Nomi canonici delle pagine, alias, ordinamento dei fogli
    canonical_mapping.py               # Converte i campi estratti in voci canoniche per il backend
    schemas.py                         # Modelli Pydantic: ExtractionResponse, AnchorResponse, ecc.
    prompts.py                         # Prompt VLM in italiano (PROMPT, ANCHOR_PROMPT, prompt di retry)
    normalization.py                   # Normalizzazione testo, classificazione campi, pick_best
    imaging.py                         # normalize_image, crop_relative, img_to_png_bytes
    vlm_client.py                      # call_vlm, call_vlm_with_retry, estimate_cost_usd
    llm_factory.py                     # create_chat_model -- factory ChatModel (OpenAI/Gemini)
    pipeline.py                        # ExtractionPipeline: multi-pass anchor -> main -> retry
    evaluation.py                      # Evaluator, eval_outputs, debug_report, cost_summary
    cli.py                             # BatchRunner, run_extraction_batch, entry point CLI main()
  edge-agent/                          # Agente desktop PyQt6 per la cattura dello schermo dal vivo
    __init__.py                        # Marcatore di package vuoto
    edge_agent.py                      # Entry point dell'app: carica .env, AgentConfig, MainWindow
    config.py                          # Classe AgentConfig: carica config.ini
    config.ini                         # Config INI con 6 sezioni (agent, api, minio, llm, dataset, debug)
    local_extraction_client.py         # LocalExtractionClient: collega la cattura alla pipeline di estrazione
    llm_router.py                      # PageRouter, MLPageRouter, LLMPageRouter
    page_classifier.py                 # BPERPagePrototypeClassifier (DINOv2 + similarità coseno)
    image_ops.py                       # preprocess_for_ocr, to_png8, to_webp_lossless
    ui/                                # Componenti UI PyQt6
      main_window.py                   # MainWindow: 4 tab (Cattura/Risultati/Dati/Debug)
      capture_tab.py                   # CaptureTab: start/stop, FPS, cattura forzata, log
      extraction_results_tab.py        # Albero pagine, tabella campi, JSON grezzo, export CSV
      data_table_tab.py                # Vista a foglio di calcolo, rinomina colonne, export CSV/Excel
      debug_tab.py                     # Output di debug JSON grezzo del router LLM
      overlay.py                       # CaptureBorderOverlay: bordo rosso sul monitor catturato
    workers/capture/                   # Worker di cattura screenshot (basati su QThread)
      base_capture_worker.py           # BaseCaptureWorker(QThread): loop FPS, segnali
      bper_capture_worker.py           # BPERCaptureWorker: deduplica, routing, stabilità
      default_capture_worker.py        # DefaultCaptureWorker: modalità generica di upload remoto
    assets/templates/bper/             # Asset di riconoscimento specifici per BPER
      prompts.json                     # Definizioni pagina del router LLM (5 pagine)
      bper_page_prototypes.json        # Embedding dei prototipi DINOv2 in cache
      screen 1-9.png                   # Immagini prototipo per il matching ML delle pagine
      transitions/                     # ~25 screenshot di stati di transizione per l'addestramento del riconoscimento
  mnt/data/                            # Directory dei dati di test (in gitignore tramite /mnt)
    screen 1-9.png                     # 9 screenshot bancari BPER per i test
    dati.csv                           # Dataset di ground truth
  .idea/                               # Config di progetto PyCharm (non in gitignore, ma non essenziale)
  .claude/                             # Impostazioni dell'assistente Claude AI
  .venv/                               # Ambiente virtuale Python (in gitignore)
```

## File di configurazione

### Configurazione dell'applicazione

**`extraction/config.py`** -- Il modulo di configurazione centrale per la pipeline di estrazione. Legge tutte le variabili d'ambiente all'import tramite `os.getenv()` e le espone come costanti a livello di modulo. Contiene le coordinate di ritaglio (`CONTENT_CROP`, `HEADER_IN_CONTENT`, `RETRY_AREAS`), le tabelle di pricing degli LLM (`PRICING_PER_1M`), la mappatura campo-area di retry (`FIELD_RETRY_MAP`, `AREA_TO_FIELDS`) e l'helper `get_screenshot_paths()`. Committato. Funziona out of the box con i default; vedi la sezione Variabili d'ambiente più avanti per la regolazione.

**`edge-agent/config.ini`** -- Configurazione in formato INI per l'applicazione desktop edge-agent. Sei sezioni: `[agent]` (FPS, modalità router, indice monitor, parametri di preprocessing), `[api]` (URL di base), `[minio]` (endpoint, credenziali, bucket), `[llm]` (provider, model, timeout, API key), `[dataset]` (impostazioni di raccolta per una futura CNN) e `[debug]` (toggle del tab di debug LLM). Caricato da `AgentConfig` in `edge-agent/config.py`. Committato nel repository. **Attenzione:** la riga 23 di questo file contiene una API key OpenAI in chiaro. È una fuga di credenziali nella history git.

**`.env.example`** -- Template per il file `.env`. Elenca ogni variabile d'ambiente riconosciuta dalla pipeline di estrazione, con spiegazioni in italiano nei commenti. Copia questo file in `.env` e compila `LLM_API_KEY` prima di eseguire. Committato.

**`.env`** -- Il file d'ambiente effettivo caricato da `python-dotenv` all'avvio. Contiene le API key reali. In gitignore -- mai committato.

### Configurazione di dipendenze e build

**`requirements.txt`** -- Tutte le dipendenze Python sia per la pipeline di estrazione sia per l'edge-agent, combinate in un unico file. Versioni fissate al minimo (la maggior parte dei pacchetti non è pinnata, alcuni hanno limiti inferiori `>=`). Include `torch` e `torchvision` per la classificazione ML delle pagine, `PyQt6` per la GUI dell'edge-agent e `streamlit` (anche se l'entry point Streamlit `app.py` non esiste su questo branch). Committato.

### Asset di riconoscimento

**`edge-agent/assets/templates/bper/prompts.json`** -- Definisce 5 tipi di pagina BPER (Risultato ricerca, Elenco Soggetti, Gestione Fidi e Garanzie, Note da Richiesta, Altro / Non riconosciuto) con `hints` in italiano usati dal router pagina LLM. Committato.

**`edge-agent/assets/templates/bper/bper_page_prototypes.json`** -- Embedding DINOv2 ViT-S/14 pre-calcolati (384 dimensioni) per ogni pagina prototipo. Usati da `BPERPagePrototypeClassifier` in modalità di riconoscimento pagina ML. Committato.

### Editor e IDE

**`.idea/`** -- Configurazione di progetto PyCharm. Il file `.iml` fa riferimento a Python 3.13 ed esclude `.venv/`, `mnt/` ed `edge-agent/` dall'indicizzazione. Committato ma non essenziale per lo sviluppo.

**`.claude/settings.local.json`** -- Regole di permesso dell'assistente Claude AI. Non rilevanti per il funzionamento dell'applicazione.

### Configurazione Git

**`.gitignore`** -- Esclude `build/`, `dist/`, `*.spec` (artefatti PyInstaller), `/mnt` (dati di test), `.env` e `.env.local` (segreti), `temp_uploads/`, `test_no_gt/`, `__pycache__/`, `*.pyc` e `.venv/`. Committato.

## Variabili d'ambiente

Ogni variabile d'ambiente viene letta in `extraction/config.py` all'import del modulo tramite `os.getenv()`, eccetto `LLM_API_KEY` e le variabili di chiave legacy, che vengono lette in `extraction/llm_factory.py` e `edge-agent/workers/capture/bper_capture_worker.py`. Il file `.env` viene caricato da `python-dotenv` in cima a `main.py` (riga 7), `edge-agent/edge_agent.py` (riga 11) e `edge-agent/local_extraction_client.py` (riga 23).

Per impostare un ambiente locale, copia il template e modificalo:

```bash
cp .env.example .env
# Modifica .env -- come minimo, imposta LLM_API_KEY
```

### Variabili obbligatorie

| Variabile | Scopo | Letta in | Default |
|----------|---------|---------|---------|
| `LLM_API_KEY` | Credenziale API per OpenAI o Google Gemini, a seconda di `LLM_PROVIDER` | `extraction/llm_factory.py` (riga 30) | Nessuno -- **deve essere impostata** |

### Variabili opzionali -- Configurazione LLM

| Variabile | Scopo | Letta in | Default |
|----------|---------|---------|---------|
| `LLM_PROVIDER` | Selezione del provider LLM: `openai` o `gemini` | `extraction/config.py` (riga 17) | `openai` |
| `LLM_MODEL` | Nome del modello per il passaggio di estrazione principale | `extraction/config.py` (riga 18) | `gpt-4o` |
| `LLM_MODEL_ANCHOR` | Nome del modello per il passaggio anchor (NDG + denominazione) | `extraction/config.py` (riga 19) | Uguale a `LLM_MODEL` |
| `LLM_THINKING_LEVEL` | Thinking budget per Gemini 2.0+/3.x: `low`, `medium` o `high`. Si applica solo quando il nome del modello contiene "thinking". | `extraction/config.py` (riga 20, costante inutilizzata), `extraction/llm_factory.py` (riga 72, il controllo effettivo) | Di fatto non impostata. Il default `medium` in `config.py` è codice morto; `llm_factory.py` legge la env var con un default vuoto. |

### Variabili opzionali -- Esecuzione

| Variabile | Scopo | Letta in | Default |
|----------|---------|---------|---------|
| `INPUT_DIR` | Directory contenente gli screenshot e il CSV di ground truth | `extraction/config.py` (riga 8) | `mnt/data` |
| `PARALLEL_WORKERS` | Dimensione del thread pool per l'estrazione batch | `extraction/config.py` (riga 11) | `12` nel codice; `.env.example` indica `4` |
| `PARALLEL_ENABLED` | Abilita l'elaborazione parallela (`1`) o seriale (`0`) | `extraction/config.py` (riga 12) | `1` |
| `MAX_CALLS_PER_SCREEN` | Numero massimo di chiamate API VLM per screenshot (anchor + main + retry) | `extraction/config.py` (riga 50) | `4` |
| `ANCHOR_CONF_MIN` | Soglia minima di confidenza per accettare NDG/denominazione dell'anchor | `extraction/config.py` (riga 52) | `0.95` |
| `STOP_ON_ANCHOR_UNCERTAIN` | Interrompe l'elaborazione di uno screen se entrambi gli anchor sono null (`1` per abilitare) | `extraction/config.py` (riga 51) | `0` (disabilitato) |

### Variabili opzionali -- Debug

| Variabile | Scopo | Letta in | Default |
|----------|---------|---------|---------|
| `DEBUG_MODE` | Abilita il logging di debug verboso nelle esecuzioni batch CLI | `extraction/config.py` (riga 88) | `0` (disabilitato) |
| `DEBUG_SAVE_CROPS` | Salva su disco le immagini di ritaglio intermedie per l'ispezione | `extraction/config.py` (riga 89) | `0` (disabilitato) |

### Variabili legacy / deprecate

| Variabile | Scopo | Letta in | Default |
|----------|---------|---------|---------|
| `OPENAI_API_KEY` | Chiave OpenAI legacy; usata come fallback quando `LLM_API_KEY` non è impostata | `extraction/llm_factory.py` (riga 34), `gui_app.py` (riga 24), `edge-agent/workers/capture/bper_capture_worker.py` (riga 122) | Nessuno |
| `GEMINI_API_KEY` | Chiave Gemini legacy; usata come fallback quando `LLM_API_KEY` non è impostata | `extraction/llm_factory.py` (riga 34) | Nessuno |
| `SCREENSHOT_DIR` | Documentata in `.env.example` (riga 17) e `CLAUDE.md` (riga 113) ma **mai letta da alcun codice Python**. Non ha effetto. | Da nessuna parte | N/D |

### Discrepanze note nei default

Due variabili hanno default che differiscono tra codice e documentazione:

- **`PARALLEL_WORKERS`**: il default nel codice è `12` (`extraction/config.py` riga 11). Il template `.env.example` e `CLAUDE.md` indicano entrambi `4`. Se ti affidi al default senza impostare la variabile, ottieni 12 worker.
- **`LLM_THINKING_LEVEL`**: `extraction/config.py` riga 20 memorizza un default `medium` in una costante a livello di modulo, ma quella costante non viene di fatto consumata da nessuna parte. Il gate che conta è in `extraction/llm_factory.py` riga 72, che rilegge `os.getenv("LLM_THINKING_LEVEL", "")` con un default vuoto e lo applica solo quando sia il valore è in `{low, medium, high}` sia il nome del modello contiene `thinking` (riga 73). Quindi in pratica, se lasci la env var non impostata (come suggeriscono `.env.example` e `CLAUDE.md`), la modalità thinking resta disattivata indipendentemente da ciò che dice `config.py`. La documentazione e il codice divergono in superficie ma a runtime si comportano in modo identico.

## Script ed eseguibili

Questo progetto non ha Makefile, né script npm, né un sistema di build formale. Tutti i comandi vengono invocati direttamente con Python.

### Comandi di sviluppo

| Comando | Cosa fa | Quando usarlo |
|---------|-------------|----------------|
| `pip install -r requirements.txt` | Installa tutte le dipendenze (extraction + edge-agent + ML) | Setup iniziale o dopo aver scaricato nuove dipendenze |
| `cp .env.example .env` | Crea il file env locale dal template | Setup iniziale |

### Esecuzione dell'applicazione

| Comando | Cosa fa | Quando usarlo |
|---------|-------------|----------------|
| `python main.py` | Estrazione batch da CLI: elabora tutti i `.png`/`.jpg` in `INPUT_DIR`, valuta rispetto alla ground truth, salva JSON + CSV di debug | Elaborazione batch di screenshot salvati |
| `python main.py --gui` | Avvia l'applicazione desktop PyQt6 edge-agent per la cattura dello schermo dal vivo | Estrazione in tempo reale da un'applicazione BPER in esecuzione |
| `python gui_app.py` | Avvia la GUI desktop Tkinter per la selezione manuale dei file e l'estrazione | Estrazione estemporanea senza valutazione di ground truth |
| `python edge-agent/edge_agent.py` | Avvia l'edge-agent direttamente (senza passare per `main.py`) | Alternativa al flag `--gui`, utile per lo sviluppo |
| `python edge-agent/edge_agent.py --debug` | Avvia l'edge-agent con il tab di debug LLM visibile | Ispezione del prompt/risposta JSON del router LLM |

### Build e packaging

| Comando | Cosa fa | Quando usarlo |
|---------|-------------|----------------|
| `pip install pyinstaller` | Installa PyInstaller per il packaging `.exe` | Prima di costruire un eseguibile standalone |
| `pyinstaller --noconfirm --onefile --windowed --name "AI_Data_Extractor" --add-data "extraction;extraction" --collect-all langchain_google_genai --collect-all langchain_openai gui_app.py` | Costruisce un `.exe` Windows standalone da `gui_app.py` | Distribuzione della GUI Tkinter come file unico |

L'`.exe` risultante finisce in `dist/AI_Data_Extractor.exe`. Questo è documentato in `README.md` (riga 91).

### File di output

L'estrazione batch da CLI (`python main.py`) genera questi file nella directory `INPUT_DIR`:

| File | Contenuto |
|------|----------|
| `poc_outputs_improved.json` | Risultati completi di estrazione per tutti gli screenshot |
| `poc_debug_improved.csv` | Dettaglio dell'accuratezza per campo rispetto alla ground truth |

La GUI Tkinter (`gui_app.py`) scrive nella directory di lavoro corrente:

| File | Contenuto |
|------|----------|
| `poc_outputs_gui.json` | JSON dei risultati di estrazione |
| `poc_results_gui.csv` | Dati estratti in formato CSV |
| `poc_debug_gui.csv` | Report di debug (solo quando viene fornito un CSV di ground truth) |

Quando `DEBUG_SAVE_CROPS=1`, le immagini di ritaglio intermedie vengono salvate in `{INPUT_DIR}/debug_crops/`.

## Avvio e sequenza di boot

### Modalità batch CLI (`python main.py`)

1. `main.py` (riga 7): `python-dotenv` carica `.env` dalla root del progetto.
2. `main.py` (riga 8): `from extraction import *` innesca `extraction/__init__.py`, che importa `extraction/config.py`. A questo punto tutte le variabili d'ambiente vengono lette in costanti a livello di modulo.
3. `extraction/cli.py::main()` (riga 315): verifica che `mnt/data/dati.csv` (o qualunque sia il valore risolto di `GROUND_TRUTH_CSV`) esista; solleva `FileNotFoundError` se manca.
4. Carica la ground truth tramite `load_ground_truth()` da `extraction/evaluation.py`.
5. Individua tutti i file `.png`/`.jpg`/`.jpeg` in `INPUT_DIR`.
6. Crea un `BatchRunner` (riga 333), che internamente chiama `create_chat_model()` due volte (una per il modello principale, una per il modello anchor) e costruisce un'`ExtractionPipeline`.
7. Esegue l'estrazione in parallelo tramite `ThreadPoolExecutor` (oppure in serie se `PARALLEL_ENABLED=0`).
8. Salva il JSON in `poc_outputs_improved.json`, valuta l'accuratezza, salva il CSV di debug, stampa il riepilogo dei costi.

### Modalità edge-agent (`python main.py --gui`)

1. `main.py` (riga 7): `python-dotenv` carica `.env`.
2. `main.py` (riga 16): inserisce la directory `edge-agent/` in `sys.path`.
3. `edge-agent/edge_agent.py::main()` (riga 24): crea `QApplication`.
4. Applica il tema `qt-material` dark_cyan (righe 38-43); degrada con grazia se il pacchetto manca.
5. Carica `edge-agent/config.ini` in `AgentConfig` (riga 48).
6. Crea `MainWindow`, che crea `LocalExtractionClient` (riga 37 in `edge-agent/ui/main_window.py`). Il client chiama `create_chat_model()` due volte e costruisce un'`ExtractionPipeline`.
7. `MainWindow` crea quattro tab: CaptureTab, ExtractionResultsTab, DataTableTab e, opzionalmente, DebugTab (se è presente il flag `--debug`).
8. Entra nel loop di eventi Qt (`app.exec()`).

### Modalità GUI Tkinter (`python gui_app.py`)

1. Importa il package `extraction` (riga 6), che innesca il caricamento di `.env` e il parsing della config.
2. Crea una finestra `tk.Tk()` con due tab (Configurazione & Log, Risultati).
3. Pre-popola il campo API key dalle variabili d'ambiente `LLM_API_KEY` o `OPENAI_API_KEY` (riga 24).
4. Attende l'interazione dell'utente -- nessuna estrazione viene eseguita finché l'utente non seleziona i file e clicca il pulsante di avvio.

### Ordine di caricamento della configurazione

La configurazione viene caricata in quest'ordine, dove i valori successivi non sovrascrivono quelli precedenti (ogni sorgente riempie il proprio ambito):

1. `python-dotenv` legge `.env` e imposta le variabili d'ambiente a livello di OS.
2. `extraction/config.py` legge quelle variabili d'ambiente tramite `os.getenv()` all'import.
3. Solo per l'edge-agent: `AgentConfig` legge `edge-agent/config.ini` per le impostazioni specifiche dell'agente (FPS, modalità router, indice monitor, ecc.). Il file INI ha una propria sezione `[llm]` con provider/model/api_key, usata per il router pagina -- separata dalla configurazione da env-var della pipeline di estrazione.

### Come verificare che l'app sia in esecuzione

- **CLI**: la console stampa `Parallel enabled: workers=N, screens=N` e poi `Done screen 1`, `Done screen 2`, ecc. man mano che ogni screen viene completato. Un'esecuzione completa termina con le metriche di accuratezza e il riepilogo dei costi.
- **Edge-agent**: appare la MainWindow con il tab "Cattura". Cliccando "Avvia" si avvia il worker di cattura. Un overlay con bordo rosso appare sul monitor catturato. L'area di log mostra i messaggi di tick FPS e i risultati del riconoscimento pagina.
- **GUI Tkinter**: la finestra si apre con il tab "Configurazione & Log". Il campo API key dovrebbe mostrare caratteri mascherati se `LLM_API_KEY` è impostata nell'ambiente.

## Porte, URL ed endpoint dei servizi

Questo progetto opera principalmente come un'applicazione locale che chiama API LLM esterne. Non espone alcun server HTTP nel funzionamento normale.

### Endpoint API esterni

| Servizio | URL | Usato da |
|---------|-----|---------|
| OpenAI API | `https://api.openai.com/v1` | `extraction/llm_factory.py` (tramite `langchain-openai`), `edge-agent/config.ini` (riga 20) |
| Google Gemini API | `https://generativelanguage.googleapis.com` | `extraction/llm_factory.py` (tramite `langchain-google-genai`) |

### Riferimenti interni (edge-agent config.ini)

| Porta | URL | Scopo | Stato |
|------|-----|---------|--------|
| 8081 | `http://localhost:8081` | URL di base dell'API nella sezione `[api]` di `edge-agent/config.ini` (riga 10) | **Inutilizzato in modalità local-only**. Il `DefaultCaptureWorker` vi fa riferimento per l'upload remoto, ma `BPERCaptureWorker` con `LocalExtractionClient` lo aggira completamente. |
| 9000 | `http://localhost:9000` | Endpoint MinIO/S3 nella sezione `[minio]` di `edge-agent/config.ini` (riga 13) | **Inutilizzato**. `_maybe_upload_dataset()` nel worker di cattura è un no-op. L'integrazione MinIO è ridotta a uno stub. |

### Download del modello DINOv2

Alla prima esecuzione del classificatore ML delle pagine, `torch.hub.load('facebookresearch/dinov2', 'dinov2_vits14')` scarica il modello DINOv2 ViT-S/14 da GitHub/PyTorch Hub. Questo richiede l'accesso a internet la prima volta; le esecuzioni successive usano il modello in cache in `~/.cache/torch/hub/`.
