# poc-data-extraction

**Python 3.12/3.13 | LangChain | OpenAI GPT-4o / Google Gemini | Pillow | Pandas | PyQt6**

Estrazione automatica di dati strutturati da screenshot bancari italiani (applicazione BPER) tramite pipeline VLM (Vision Language Model) multi-pass con **LangChain**. Supporta l'acquisizione in tempo reale tramite un **Edge Agent** (PyQt6) che si collega direttamente alla pipeline di estrazione locale. Estrae **45 campi** (`FIELD_KEYS` in `src/extraction/fields.py`) da 9 tipi di schermata, valuta l'accuratezza rispetto a un ground truth CSV e produce metriche per campo e breakdown dei costi.

La **[documentazione ufficiale](docs/INDEX.md)** raccoglie [istruzioni di avvio](docs/07-getting-started.md), [architettura](docs/04-architecture.md), [flussi di elaborazione](docs/05-workflows.md), [modello dei dati](docs/06-data-model.md) e [API Python](docs/12-python-api.md). Le decisioni sono spiegate negli [ADR](docs/adr/README.md).

> **Avviso (2026-07-21):** la cronologia git è stata **riscritta e force-pushata** per rimuovere una chiave API committata per errore. Se hai clonato il repository **prima del 2026-07-21, ri-clona da zero**; non fare push/merge da un clone vecchio. Dettagli in [Sicurezza: chiavi API](#sicurezza-chiavi-api-e-cronologia-git).

## Cosa fa

Il sistema riceve screenshot (da file o cattura in tempo reale) e, attraverso tre passaggi VLM successivi (anchor, main, retry), estrae i campi strutturati con valori di confidenza. Lo schema dei campi prevede `value`, `confidence`, `evidence_text` e `section`; i candidati prodotti dall'appiattimento dei soggetti non aggiungono `evidence_text`. La pipeline include un meccanismo di retry mirato per i campi con confidenza bassa o valore nullo tramite ritagli (crop) per area (HEADER / BODY / FOOTER) dell'immagine.

## Stato Attuale

Il coordinamento dell'estrazione e i risultati risiedono nell'applicazione. La lettura delle immagini chiama i provider AI configurati e richiede rete; non serve un backend applicativo separato per il percorso BPER.
Modelli elencati nel catalogo locale (`PROVIDER_MODELS` in `src/extraction/config.py`; la disponibilità presso il provider va verificata quando si configura l'applicazione):
- **OpenAI**: `gpt-4o`, `gpt-4o-mini`, `o1`, `o1-mini`.
- **Google Gemini**: `gemini-1.5-pro`, `gemini-1.5-flash`, `gemini-2.0-flash`, `gemini-2.0-flash-exp`, `gemini-2.0-flash-thinking-exp`, `gemini-3-flash-preview`, `gemini-3.1-flash-lite-preview`, `gemini-3.6-flash`, `gemini-3.8-flash` (default).

Caratteristiche principali:
- **Edge Agent (GUI)**: Cattura screenshot in tempo reale dal monitor selezionato, riconosce la pagina corrente (router LLM o ML) e avvia l'estrazione locale.
- **Parallelismo**: Elaborazione simultanea di file nel batch e di frame nell'edge-agent. Tabella ed export live usano i risultati nell'ordine di acquisizione, anche quando terminano fuori ordine.
- **Anchor Check**: Un primo pass estrae NDG e DENOMINAZIONE e azzera i valori sotto `ANCHOR_CONF_MIN`. Il `dataset_mismatch_guard()` esclude dalle metriche FILTERED gli screenshot con mismatch; le metriche RAW li includono.
- **Retry mirato**: Ritagli per le aree con valori nulli o poco affidabili, entro `MAX_CALLS_PER_SCREEN`. Il budget conta i passaggi logici; i tentativi di trasporto possono produrre più richieste di rete.
- **Valutazione Automatica**: Confronta i risultati con un file Ground Truth (`dati.csv`, **non incluso nel repo**, vedi sotto).

Il progetto è un POC con dipendenze non bloccate a versioni esatte. Per eseguire i test e valutare l'accuratezza dell'estrazione, consulta [Avvio e sviluppo](docs/07-getting-started.md).

## Scopo dei Componenti

### Core Pipeline (`src/extraction/`)
Il package `extraction` contiene tutta la logica di business, separata dall'interfaccia utente:
- `pipeline.py`: Orchestratore principale dei 3 passaggi (Anchor -> Main -> Retry).
- `fields.py`: I 45 field keys (`FIELD_KEYS`) e il mapping CSV -> schema (`CSV_TO_SCHEMA`).
- `llm_factory.py`: `create_chat_model()`, factory unica dei modelli LangChain per i diversi provider.
- `vlm_client.py`: Interfaccia di basso livello per le chiamate ai modelli con output strutturato (Pydantic) e tracking dei costi.
- `imaging.py`: Manipolazione immagini (crop, normalizzazione, compressione).
- `evaluation.py`: Metriche di accuratezza (OK, WRONG, MISSING, ...) e report di debug.
- `schemas.py`: Struttura dati Pydantic dei campi estratti, soggetti, fidi e garanzie.
- `config.py`: Costanti, coordinate dei crop, pricing e variabili d'ambiente.
- `cli.py`: `run_extraction_batch()`, il batch runner condiviso da CLI e GUI Tkinter.

### Interfacce Utente
- **Edge Agent (`python src/edge-agent/edge_agent.py`, oppure `python main.py --gui`, oppure `run_edge_agent.bat` su Windows)**: Interfaccia per la cattura real-time e l'estrazione locale. Basata su **PyQt6**.
- **Batch CLI (`python main.py`)**: Processamento batch dei file già salvati in `data/reference/`. **Richiede** il ground truth `data/reference/dati.csv`.
- **Desktop UI (`python gui_app.py`)**: Applicazione nativa **Tkinter** per processing di file selezionati manualmente (il CSV ground truth qui è opzionale).

---

## Come Avviarlo

### 1. Setup Ambiente

I runtime di riferimento sono **Python 3.13 e 3.12**. Il launcher Windows prova `py -3.13`, poi `py -3.12`, infine il comando `python` disponibile senza verificarne la versione. Le dipendenze dell'applicazione stanno in `requirements.txt`; `requirements-dev.txt` aggiunge pytest.

```bash
# Installazione dipendenze
pip install -r requirements.txt

# Configurazione (opzionale se si usa la GUI Tkinter, che accetta la chiave da campo)
cp .env.example .env
# Modificare .env impostando LLM_API_KEY (mai committare chiavi in file tracciati)
```

Su Windows il modo più rapido è il launcher, che crea/ripara la `.venv`, installa le dipendenze e avvia l'Edge Agent:

```bat
run_edge_agent.bat
```

> **Nota su `data/reference/dati.csv`:** `data/` è versionata nel repository (inclusi `data/reference/dati.csv` e `data/pratiche/`, con la sola esclusione dei pesi binari `*.safetensors` > 1 GB). Se `INPUT_DIR` viene puntato a una cartella priva di `dati.csv`, `python main.py` solleva `FileNotFoundError` (`src/extraction/cli.py::main`); GUI Tkinter ed Edge Agent funzionano anche senza ground truth.

### 2. Avvio interfacce

#### Edge Agent
Per la cattura real-time e l'estrazione locale:
```bash
python src/edge-agent/edge_agent.py        # avvio diretto (--debug aggiunge il tab Debug LLM)
python main.py --gui                   # importa extraction prima del preflight: ambiente già pronto
run_edge_agent.bat                     # Windows: bootstrap venv + avvio
```

#### Batch CLI
Per un processing di tutti i file già presenti in `data/reference/` (richiede `dati.csv`, vedi sopra):
```bash
python main.py
```

#### Desktop App (Tkinter)
Per l'applicazione desktop nativa:
```bash
python gui_app.py
```

Tkinter carica `.env` prima di importare il motore e inizializza provider e modello dalla configurazione effettiva, conservando anche un modello personalizzato. La chiave può essere inserita nella GUI. Per il primo avvio dell'edge-agent usare il launcher o `src/edge-agent/edge_agent.py`, che eseguono il preflight prima di importare la UI e il motore. Le procedure complete sono in [Avvio e sviluppo](docs/07-getting-started.md).

---

## Sicurezza: chiavi API e cronologia git

- **2026-07-21**: una chiave OpenAI committata in `src/edge-agent/config.ini` è stata **rimossa dall'intera cronologia git** (`git filter-repo` + force-push). Tutti gli hash dei commit sono cambiati. **Chi ha clonato prima di quella data deve ri-clonare**: un push o merge da un clone vecchio reintrodurrebbe la chiave nella cronologia.
- La riga `api_key` in `src/edge-agent/config.ini` ora è **vuota**. Il file è tracciato in git: **non inserire mai una chiave reale lì**. `AgentConfig` tratta come vuoto anche qualunque valore che inizi per `REDACTED`, perché un placeholder rimasto in giro aveva già oscurato le chiavi da ambiente rompendo il router in silenzio. `build_exe.bat` si rifiuta di impacchettare un `config.ini` con `api_key` non vuota.
- Le chiavi vanno in `.env` (gitignorato): `LLM_API_KEY` è l'unica variabile obbligatoria.
- Il router dell'edge-agent risolve le credenziali separatamente dal motore. La configurazione inclusa usa `router = llm`, mentre il default di `AgentConfig` è `ml`. Quando viene usato il router LLM, `resolve_llm_settings()` sceglie `config.ini [llm] api_key` se non vuota, poi per `gemini` `GEMINI_API_KEY` -> `GOOGLE_API_KEY` -> `LLM_API_KEY`, per `openai` `OPENAI_API_KEY` -> `LLM_API_KEY`. Il riconoscimento ML può essere locale, ma l'estrazione richiede comunque la chiave del provider.

---

## Generazione Eseguibile (.exe)

Il repository include il build portable dell'edge-agent tramite [build_exe.bat](build_exe.bat) e [edge_agent.spec](edge_agent.spec). Dalla radice, su Windows:

```bat
build_exe.bat
```

Lo script prepara Python e le dipendenze se mancanti, rimuove la precedente `dist/EdgeAgent` e genera un bundle PyInstaller `onedir`. Copia configurazione, asset e prompt, include un template `.env` e produce `dist/EdgeAgent_YYYY-MM-DD.zip`.

**Pacchetto già configurato.** Un tester non deve sapere cos'è una chiave API: all'avvio lo script chiede la chiave da includere (INVIO per nessuna), oppure la legge da `EDGE_AGENT_PACKAGE_KEY`. La chiave finisce solo nel `.env` del pacchetto, mai nel `config.ini` tracciato, e lo zip prende il suffisso `_CON-CHIAVE`. Chi riceve quello zip può leggerla: usa una chiave dedicata alla beta, con limite di spesa, e revocala alla fine.

```bat
set EDGE_AGENT_PACKAGE_KEY=<chiave dedicata alla beta>
build_exe.bat
```

Consegnare l'intera cartella del pacchetto, non soltanto l'eseguibile. Il build rifiuta un `config.ini` con `api_key` valorizzata. Al primo avvio il preflight prepara i componenti e, se il pacchetto non ha la chiave, la richiede. Dettagli in [Avvio e sviluppo](docs/07-getting-started.md).

## I 45 campi estratti

`FIELD_KEYS` in `src/extraction/fields.py` definisce 45 chiavi, raggruppate così:

| Gruppo | Campi | Area retry |
|---|---|---|
| Identificatori header | `ndg`, `denominazione` | HEADER |
| Metadati pratica | `tipo`, `stato`, `fase`, `creazione`, `evidenze` | HEADER |
| Dati fido | `filiale_relazione`, `n_fido`, `rapporto`, `descrizione`, `scadenza`, `importo_euro`, `tipo_op` | HEADER / BODY |
| Note e tooltip | `note_della_richiesta`, `tooltip_descrizione_bmb`, `tooltip_evidenze_b`, `tooltip_descrizione_m_consap`, `tooltip_descrizione_consap_dr_bis`, `tooltip_descrizione_ipoteca` | FOOTER per la nota; i cinque tooltip sono esclusi dai retry |
| Soggetti appiattiti (screen 2-3) | `ndg_1..4`, `denominazione_1..4`, `ruolo_1..4` (fino a 4 cointestatari) | BODY |
| Scheda privati (screen 4-5) | `dal`, `datore_di_lavoro_anagrafica`, `di_cui_percepiscono_reddito`, `importo_totale_annuo_nucleo`, `note_scheda_privati`, `nr_altri_componenti_nucleo`, `numero_mensilita`, `professione_principale`, `rating_ufficiale`, `retribuzione_annua_netta`, `score_cgs`, `tipo_contratto`, `ultima_validazione_scheda` | HEADER / BODY / FOOTER |

Le chiavi sono termini di dominio bancario in italiano e non vanno tradotte. Il mapping campo -> area di retry è in `AREA_TO_FIELDS` (`src/extraction/config.py`); `UNRETRIED_FIELDS` dichiara l'esclusione dei cinque tooltip. Un retry riempie una tabella `soggetti` vuota solo con righe a confidenza almeno `RETRY_CONF_MIN` e con NDG o denominazione leggibili. Le voci canoniche distinguono cinque pagine di origine dai quattro gruppi dell'Excel: i tredici campi Scheda Privati riportano `page_key=scheda_privati`, conservando il gruppo di export `note_da_richiesta` e le stesse 45 colonne.

## Configurazione

Tutte le variabili sono configurabili via environment (lette a import time da `src/extraction/config.py`). Vedi [`.env.example`](.env.example) per il template.

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `LLM_PROVIDER` | `openai` | Provider: `openai` o `gemini` |
| `LLM_API_KEY` | *(obbligatoria)* | Chiave API (OpenAI o Gemini a seconda del provider). Fallback legacy `OPENAI_API_KEY`/`GEMINI_API_KEY` con DeprecationWarning |
| `LLM_MODEL` | `gpt-4o` | Modello per estrazione principale |
| `LLM_MODEL_ANCHOR` | come `LLM_MODEL` | Modello per il pass anchor |
| `LLM_THINKING_LEVEL` | *(nessuno)* | Profondità di ragionamento `low`/`medium`/`high`, inviata come `thinking_level` alla famiglia Gemini 3; se assente vale il default del modello (`high` per Gemini 3). Le altre famiglie la ignorano con un avviso; un valore diverso blocca l'avvio |
| `INPUT_DIR` | `data/reference` | Directory dati (screenshot + ground truth) |
| `PARALLEL_WORKERS` | `4` | Numero thread paralleli |
| `PARALLEL_ENABLED` | `1` | Elaborazione parallela (`0` per disattivarla) |
| `MAX_CALLS_PER_SCREEN` | `2 + len(AREA_TO_FIELDS)` (= `5`) | Budget dei passaggi: 1 anchor + 1 main + un retry per area. Ridurlo elimina le aree in coda a `AREA_TO_FIELDS`; non limita i tentativi di trasporto |
| `ANCHOR_CONF_MIN` | `0.95` | Confidenza minima per accettare gli anchor |
| `RETRY_CONF_MIN` | `0.60` | Confidenza sotto cui un campo rende candidata al retry la propria area |
| `MAX_IMAGE_LONG_SIDE` | `2000` | Limite del lato lungo all'ingresso di `extract_from_image()` |
| `STOP_ON_ANCHOR_UNCERTAIN` | `0` | Fermare il processing se l'anchor è incerto (`1` per attivare) |
| `DEBUG_MODE` | `0` | Log `[DEBUG]` verbosi del batch |
| `DEBUG_SAVE_CROPS` | `0` | Salvare i crop intermedi in `INPUT_DIR/debug_crops` |
| `PROMPTS_DIR` | *(non impostata)* | Directory alternativa del catalogo prompt; viene letta da `src/prompt_store.py` e un override non valido interrompe il caricamento |

La cattura e il routing dell'edge-agent si configurano via `src/edge-agent/config.ini`; il motore di estrazione continua a leggere le variabili d'ambiente. Le modalità `ml`, `llm`, `hybrid` e `local-first` sono descritte nei [Workflow](docs/05-workflows.md), inclusi i limiti del percorso `local-first` corrente. Provider e modello devono essere coerenti: la factory rifiuta ad esempio un modello `gemini-*` con `LLM_PROVIDER=openai` (`src/extraction/llm_factory.py`).

## Output JSON

Ogni screenshot produce un oggetto con questa struttura (costruita in `src/extraction/pipeline.py`):

```json
{
  "screen_id": "screen 1",
  "fields": {
    "ndg": {
      "value": "31943680",
      "confidence": 0.99,
      "evidence_text": "NDG 31943680",
      "section": "header"
    },
    "denominazione": { "value": "...", "confidence": 0.98, "..." : "..." }
  },
  "soggetti": [
    { "ndg": "31943680", "denominazione": "TICCHI SERENA", "ruolo": "INTESTATARIO", "confidence": 0.95, "evidence_text": "..." }
  ],
  "fidi": [],
  "garanzie": [],
  "canonical_fields": [ { "schema_key": "ndg", "display_name": "...", "page_key": "...", "page_name": "...", "value": "...", "confidence": 0.99, "...": "..." } ],
  "_attempts": [ { "attempt": "ANCHOR_HEADER", "prompt_tokens": 1000, "...": "..." } ],
  "_meta_agg": {
    "model_main": "gpt-4o",
    "model_anchor": "gpt-4o",
    "calls": 3,
    "prompt_tokens": 12500,
    "completion_tokens": 800,
    "total_tokens": 13300,
    "estimated_cost_usd": 0.035,
    "latency_ms": 8500
  },
  "_field_sources": { "ndg": "ANCHOR_HEADER", "tipo": "CONTENT_MAIN", "note_della_richiesta": "RETRY_FOOTER" },
  "_status": "OK"
}
```

`_field_sources` registra quale pass ha prodotto il valore finale di ogni campo: `ANCHOR_HEADER`, `CONTENT_MAIN` o `RETRY_{HEADER|BODY|FOOTER}`. `_status` può essere `OK` o `ANCHOR_UNCERTAIN` (l'Edge Agent aggiunge anche `ERROR`).

## Valutazione accuratezza

Il sistema classifica ogni campo estratto con uno dei 5 status:

| Status | Significato |
|--------|-------------|
| **OK** | Valore estratto corrisponde al ground truth |
| **WRONG** | Valore estratto non corrisponde |
| **MISSING** | Ground truth ha un valore, estrazione ha restituito null |
| **HALLUCINATED** | Ground truth e' nullo, ma l'estrazione ha prodotto un valore |
| **OK_NULL** | Entrambi nulli - corretto |

Le metriche sono calcolate in due varianti:
- **RAW**: tutti gli screen, inclusi quelli con mismatch dataset (NDG/DENOMINAZIONE estratti diversi dal GT)
- **FILTERED**: esclude screen con mismatch, per evitare falsi negativi

## Struttura progetto

```
poc-data-src/extraction/
  main.py                  # Entry point (CLI batch; --gui avvia l'Edge Agent)
  gui_app.py               # Entry point Desktop (Tkinter)
  run_edge_agent.bat       # Launcher Windows: bootstrap .venv + avvio Edge Agent
  requirements.txt         # Unico file dipendenze (core + edge-agent + training)
  pyproject.toml           # Configurazione pytest (pythonpath = ["src", "src/edge-agent"]) e marker slow
  tools/check.py           # Verifica rapida: esclude i casi DINOv2 marcati slow
  prompts/                 # Catalogo prompt LLM: un file JSON per prompt, letto all'avvio
  src/                     # Sorgenti applicativi e di training
    prompt_store.py        # Loader del catalogo prompt (solo stdlib), condiviso da core ed Edge Agent
    edge-agent/            # Edge Agent (PyQt6)
      edge_agent.py        # Entry point GUI
      config.py / config.ini # Configurazione agent (fps, router, monitor, [llm])
      local_extraction_client.py # Ponte tra GUI e ExtractionPipeline
      llm_router.py        # Router pagine: LLM (Vision) e ML (DINOv2, in vigore)
      page_classifier.py   # Classificatore prototipi DINOv2 ViT-S/14, coseno centrato
      frame_normalize.py   # Dal monitor intero alla finestra applicativa
      image_ops.py         # Preprocessing cattura (scale, unsharp, autocontrast)
      ui/                  # MainWindow, tab Cattura/Dati Estratti e Debug LLM opzionale
      workers/capture/     # QThread di cattura (BPER + generico)
      assets/templates/bper/ # prompts.json (definizioni pagine), embeddings, template
    extraction/            # Motore di estrazione VLM
      __init__.py          # Re-export API pubblica
      config.py            # Configurazione env-var, crop, pricing
      fields.py            # 45 field keys + CSV_TO_SCHEMA mapping
      field_definitions.py # Display name + pagina di origine e gruppo export
      page_definitions.py  # Cinque pagine di origine, quattro gruppi export
      canonical_mapping.py # build_canonical_field_entries() per output client
      schemas.py           # Pydantic models per output strutturato
      prompts.py           # Costanti dei prompt VLM, lette dal catalogo prompts/
      normalization.py     # Normalizzazione testo, classify_field, pick_best
      imaging.py           # Crop, resize, conversione immagini
      vlm_client.py        # LangChain structured output + retry + costi
      llm_factory.py       # LangChain ChatModel factory (create_chat_model)
      pipeline.py          # Pipeline 3-pass (anchor -> main -> retry)
      evaluation.py        # Metriche accuratezza + debug report
      cli.py               # Batch runner con ThreadPoolExecutor
    training/              # Pipeline offline di allineamento OCR, dataset e training LiLT
      schema.py            # Vocabolario canonico dei 45 campi e 37 ruoli semantici
      alignment.py         # Allineamento geometrico/testuale dei valori revisionati sui token OCR
      dataset.py           # Lettura revisione Excel v3.1, supervisione BIO, audit anti-leakage e manifest
      model.py             # Chunking 512 token, augmentation, training LiLT, selezione checkpoint e inferenza CPU/GPU
      evaluation.py        # Ricostruzione rigorosa dei 45 campi e metriche per campo/ruolo/split
      modal_train.py       # Esecuzione GPU limitata su Modal e download del modello CPU
      README.md            # Guida operativa per la rigenerazione del dataset e l'addestramento
  tests/                   # Suite pytest (motore, edge-agent, classificatore DINOv2 e training LiLT)
  data/reference/
    dati.csv               # Ground truth - NON incluso nel repo, da procurarsi a parte
    screen *.png           # Screenshot di test (9 immagini, tracciate)
  docs/                    # Documentazione narrativa in italiano (INDEX.md) e ADR (docs/adr/)
  .tritech/codebase-map/   # Mappa del codice generata dal plugin codebase-map
  .env.example             # Template variabili d'ambiente
```

## Ground truth CSV

Il file `data/reference/dati.csv` **non è versionato** (`/data` è in `.gitignore`): va ottenuto dal team e posizionato manualmente. La CLI non parte senza. Formato atteso (long format, 3 colonne):

```
Fotogramma,Denominazione da attribuire,Valore rilevato
screen 1,NDG,31943680
screen 1,DENOMINAZIONE,"TICCHI SERENA, CABRAS LUCA"
screen 1,Tipo,BPI Mutui
...
```

| Colonna | Descrizione |
|---------|-------------|
| `Fotogramma` | Identificativo dello screenshot (es. "screen 1") |
| `Denominazione da attribuire` | Nome del campo (es. "NDG", "Tipo contratto") |
| `Valore rilevato` | Valore atteso per quel campo |

Il loader (`load_ground_truth()` in `src/extraction/evaluation.py`) supporta nomi colonna alternativi: `Screenshot`/`Screen` per la colonna screen, `Campo`/`Field` per le chiavi, `Valore`/`Value` per i valori.

Per aggiungere nuovi screenshot: inserire le righe nel CSV e posizionare l'immagine `.png` nella stessa directory con nome corrispondente alla colonna `Fotogramma`.
