# poc-data-extraction

**Python 3.12/3.13 | LangChain | OpenAI GPT-4o / Google Gemini | Pillow | Pandas | PyQt6**

Estrazione automatica di dati strutturati da screenshot bancari italiani (applicazione BPER) tramite pipeline VLM (Vision Language Model) multi-pass con **LangChain**. Supporta l'acquisizione in tempo reale tramite un **Edge Agent** (PyQt6) che si collega direttamente alla pipeline di estrazione locale. Estrae **45 campi** (`FIELD_KEYS` in `extraction/fields.py`) da 9 tipi di schermata, valuta l'accuratezza rispetto a un ground truth CSV e produce metriche per campo e breakdown dei costi.

> **Avviso (2026-07-21):** la cronologia git è stata **riscritta e force-pushata** per rimuovere una chiave API committata per errore. Se hai clonato il repository **prima del 2026-07-21, ri-clona da zero**; non fare push/merge da un clone vecchio. Dettagli in [Sicurezza: chiavi API](#sicurezza-chiavi-api-e-cronologia-git).

## Cosa fa

Il sistema riceve screenshot (da file o cattura in tempo reale) e, attraverso tre passaggi VLM successivi (anchor, main, retry), estrae i campi strutturati con valori di confidenza. Ogni campo viene restituito con `value`, `confidence`, `evidence_text` e `section`. La pipeline include un meccanismo di retry mirato per i campi con confidenza bassa o valore nullo tramite ritagli (crop) per area (HEADER / BODY / FOOTER) dell'immagine.

## Stato Attuale

Il sistema integra l'acquisizione automatica degli screenshot con l'estrazione locale, senza microservizi esterni o backend remoti.
Modelli supportati (`PROVIDER_MODELS` in `extraction/config.py`):
- **OpenAI**: `gpt-4o`, `gpt-4o-mini`, `o1`, `o1-mini`.
- **Google Gemini**: `gemini-1.5-pro`, `gemini-1.5-flash`, `gemini-2.0-flash`, `gemini-2.0-flash-exp`, `gemini-2.0-flash-thinking-exp`, `gemini-3-flash-preview`, `gemini-3.1-flash-lite-preview`.

Caratteristiche principali:
- **Edge Agent (GUI)**: Cattura screenshot in tempo reale dal monitor selezionato, riconosce la pagina corrente (router LLM o ML) e avvia l'estrazione locale.
- **Parallelismo**: Elaborazione simultanea di più immagini in modalità CLI (`ThreadPoolExecutor`).
- **Anchor Check**: Un primo pass estrae solo NDG e DENOMINAZIONE dall'header per ancorare l'estrazione al soggetto corretto; il `dataset_mismatch_guard()` esclude dalle metriche gli screen con mismatch.
- **Retry Intelligente**: Crop mirati per area dove l'estrazione iniziale è fallita, con tetto di chiamate per screenshot (`MAX_CALLS_PER_SCREEN`).
- **Valutazione Automatica**: Confronta i risultati con un file Ground Truth (`dati.csv`, **non incluso nel repo**, vedi sotto).

Limiti noti (è un POC): nessuna test suite automatica, nessuna CI/CD, nessun Dockerfile, dipendenze non pinnate (un solo `requirements.txt` alla radice).

## Scopo dei Componenti

### Core Pipeline (`extraction/`)
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
- **Edge Agent (`python edge-agent/edge_agent.py`, oppure `python main.py --gui`, oppure `run_edge_agent.bat` su Windows)**: Interfaccia per la cattura real-time e l'estrazione locale. Basata su **PyQt6**.
- **Batch CLI (`python main.py`)**: Processamento batch dei file già salvati in `mnt/data/`. **Richiede** il ground truth `mnt/data/dati.csv`.
- **Desktop UI (`python gui_app.py`)**: Applicazione nativa **Tkinter** per processing di file selezionati manualmente (il CSV ground truth qui è opzionale).

---

## Come Avviarlo

### 1. Setup Ambiente

Python consigliato: **3.13** (o 3.12). Il launcher Windows `run_edge_agent.bat` cerca deliberatamente `py -3.13`, poi `py -3.12` (le versioni più nuove spesso non hanno wheel torch). Tutte le dipendenze stanno in un unico `requirements.txt` alla radice.

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

> **Attenzione - ground truth mancante:** il file `mnt/data/dati.csv` **non è nel repository** (`/mnt` è in `.gitignore`; solo i 9 PNG sono tracciati). Su un clone fresco `python main.py` fallisce subito con `FileNotFoundError: Ground truth CSV not found: mnt/data/dati.csv` (`extraction/cli.py:315-316`). Procurarsi il file e metterlo in `mnt/data/` prima di usare la CLI: formato in [Ground truth CSV](#ground-truth-csv). GUI Tkinter ed Edge Agent funzionano anche senza.

### 2. Avvio interfacce

#### Edge Agent
Per la cattura real-time e l'estrazione locale:
```bash
python edge-agent/edge_agent.py        # avvio diretto (--debug aggiunge il tab Debug LLM)
python main.py --gui                   # equivalente
run_edge_agent.bat                     # Windows: bootstrap venv + avvio
```

#### Batch CLI
Per un processing di tutti i file già presenti in `mnt/data/` (richiede `dati.csv`, vedi sopra):
```bash
python main.py
```

#### Desktop App (Tkinter)
Per l'applicazione desktop nativa:
```bash
python gui_app.py
```

---

## Sicurezza: chiavi API e cronologia git

- **2026-07-21**: una chiave OpenAI committata in `edge-agent/config.ini` è stata **rimossa dall'intera cronologia git** (`git filter-repo` + force-push). Tutti gli hash dei commit sono cambiati. **Chi ha clonato prima di quella data deve ri-clonare**: un push o merge da un clone vecchio reintrodurrebbe la chiave nella cronologia.
- `edge-agent/config.ini:23` ora contiene il placeholder `api_key = REDACTED_OPENAI_API_KEY`. Il file è tracciato in git: **non inserire mai una chiave reale lì**.
- Le chiavi vanno in `.env` (gitignorato): `LLM_API_KEY` è l'unica variabile obbligatoria.
- Nota sul router LLM dell'Edge Agent: la precedenza della chiave è `config.ini [llm] api_key` -> `OPENAI_API_KEY` -> `LLM_API_KEY` (`edge-agent/workers/capture/bper_capture_worker.py:122`). Il valore nell'INI **vince** se non vuoto; quindi con il placeholder presente il router non funziona finché non lo si svuota (lasciando l'env fallback) o non si mette una chiave in locale senza committarla.

---

## Generazione Eseguibile (.exe)

È possibile pacchettizzare l'applicazione Desktop Tkinter (`gui_app.py`) in un unico file eseguibile per Windows utilizzando **PyInstaller**. (Non esiste un pacchetto per l'Edge Agent: il suo unico launcher è `run_edge_agent.bat`.)

### Prerequisiti
```bash
pip install pyinstaller
```

### Build
Per generare l'eseguibile, posizionarsi nella root del progetto e lanciare:

```bash
pyinstaller --noconfirm --onefile --windowed --name "AI_Data_Extractor" --add-data "extraction;extraction" --collect-all langchain_google_genai --collect-all langchain_openai gui_app.py
```

**Note sulla build:**
- `--onefile`: Crea un singolo file .exe (nella cartella `dist/`).
- `--windowed`: Impedisce l'apertura della console all'avvio dell'app.
- `--add-data "extraction;extraction"`: Include il package `extraction` del progetto.
- `--collect-all`: Forza l'inclusione delle dipendenze dinamiche di LangChain (import dinamici che PyInstaller non rileva da solo).

L'eseguibile risultante si troverà in `dist/AI_Data_Extractor.exe`.

## I 45 campi estratti

`FIELD_KEYS` in `extraction/fields.py` definisce 45 chiavi, raggruppate così:

| Gruppo | Campi | Area retry |
|---|---|---|
| Identificatori header | `ndg`, `denominazione` | HEADER |
| Metadati pratica | `tipo`, `stato`, `fase`, `creazione`, `evidenze` | HEADER |
| Dati fido | `filiale_relazione`, `n_fido`, `rapporto`, `descrizione`, `scadenza`, `importo_euro`, `tipo_op` | HEADER / BODY |
| Note e tooltip | `note_della_richiesta`, `tooltip_descrizione_bmb`, `tooltip_evidenze_b`, `tooltip_descrizione_m_consap`, `tooltip_descrizione_consap_dr_bis`, `tooltip_descrizione_ipoteca` | FOOTER |
| Soggetti appiattiti (screen 2-3) | `ndg_1..4`, `denominazione_1..4`, `ruolo_1..4` (fino a 4 cointestatari) | BODY |
| Scheda privati (screen 4-5) | `dal`, `datore_di_lavoro_anagrafica`, `di_cui_percepiscono_reddito`, `importo_totale_annuo_nucleo`, `note_scheda_privati`, `nr_altri_componenti_nucleo`, `numero_mensilita`, `professione_principale`, `rating_ufficiale`, `retribuzione_annua_netta`, `score_cgs`, `tipo_contratto`, `ultima_validazione_scheda` | BODY / FOOTER |

Le chiavi sono termini di dominio bancario in italiano e non vanno tradotte. Il mapping campo -> area di retry è in `AREA_TO_FIELDS` (`extraction/config.py`).

## Configurazione

Tutte le variabili sono configurabili via environment (lette a import time da `extraction/config.py`). Vedi [`.env.example`](.env.example) per il template.

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `LLM_PROVIDER` | `openai` | Provider: `openai` o `gemini` |
| `LLM_API_KEY` | *(obbligatoria)* | Chiave API (OpenAI o Gemini a seconda del provider). Fallback legacy `OPENAI_API_KEY`/`GEMINI_API_KEY` con DeprecationWarning |
| `LLM_MODEL` | `gpt-4o` | Modello per estrazione principale |
| `LLM_MODEL_ANCHOR` | come `LLM_MODEL` | Modello per il pass anchor |
| `LLM_THINKING_LEVEL` | *(nessuno)* | Thinking budget `low`/`medium`/`high`; applicato solo ai modelli il cui nome contiene `thinking` |
| `INPUT_DIR` | `mnt/data` | Directory dati (screenshot + ground truth) |
| `PARALLEL_WORKERS` | `4` | Numero thread paralleli |
| `PARALLEL_ENABLED` | `1` | Elaborazione parallela (`0` per disattivarla) |
| `MAX_CALLS_PER_SCREEN` | `4` | Massimo chiamate VLM per screenshot (1 anchor + 1 main + retry) |
| `ANCHOR_CONF_MIN` | `0.95` | Confidenza minima per accettare gli anchor |
| `STOP_ON_ANCHOR_UNCERTAIN` | `0` | Fermare il processing se l'anchor è incerto (`1` per attivare) |
| `DEBUG_MODE` | `0` | Log `[DEBUG]` verbosi del batch |
| `DEBUG_SAVE_CROPS` | `0` | Salvare i crop intermedi in `INPUT_DIR/debug_crops` |

L'Edge Agent si configura invece via `edge-agent/config.ini` (fps, router `ml`/`llm`/`hybrid`, monitor, ecc.), non via env, con l'eccezione del fallback della chiave del router descritto sopra. Provider e modello devono essere coerenti: la factory rifiuta ad esempio un modello `gemini-*` con `LLM_PROVIDER=openai` (`extraction/llm_factory.py`).

## Output JSON

Ogni screenshot produce un oggetto con questa struttura (costruita in `extraction/pipeline.py`):

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
poc-data-extraction/
  main.py                  # Entry point (CLI batch; --gui avvia l'Edge Agent)
  gui_app.py               # Entry point Desktop (Tkinter)
  run_edge_agent.bat       # Launcher Windows: bootstrap .venv + avvio Edge Agent
  requirements.txt         # Unico file dipendenze (core + edge-agent)
  prompt_store.py          # Loader del catalogo prompt (solo stdlib), condiviso da core ed Edge Agent
  prompts/                 # Catalogo prompt LLM: un file JSON per prompt, letto all'avvio
  edge-agent/              # Edge Agent (PyQt6)
    edge_agent.py          # Entry point GUI
    config.py / config.ini # Configurazione agent (fps, router, monitor, [llm])
    local_extraction_client.py # Ponte tra GUI e ExtractionPipeline
    llm_router.py          # Router pagine: LLM (OpenAI Vision) e ML (DINOv2)
    page_classifier.py     # Classificatore prototipi DINOv2 ViT-S/14
    image_ops.py           # Preprocessing cattura (scale, unsharp, autocontrast)
    ui/                    # MainWindow, tab Cattura/Risultati/Dati Estratti/Debug
    workers/capture/       # QThread di cattura (BPER + generico)
    assets/templates/bper/ # prompts.json (definizioni pagine), embeddings, template
  extraction/
    __init__.py            # Re-export API pubblica
    config.py              # Configurazione env-var, crop, pricing
    fields.py              # 45 field keys + CSV_TO_SCHEMA mapping
    field_definitions.py   # Display name + pagina canonica per campo
    page_definitions.py    # Nomi canonici delle pagine
    canonical_mapping.py   # build_canonical_field_entries() per output client
    schemas.py             # Pydantic models per output strutturato
    prompts.py             # Costanti dei prompt VLM, lette dal catalogo prompts/
    normalization.py       # Normalizzazione testo, classify_field, pick_best
    imaging.py             # Crop, resize, conversione immagini
    vlm_client.py          # LangChain structured output + retry + costi
    llm_factory.py         # LangChain ChatModel factory (create_chat_model)
    pipeline.py            # Pipeline 3-pass (anchor -> main -> retry)
    evaluation.py          # Metriche accuratezza + debug report
    cli.py                 # Batch runner con ThreadPoolExecutor
  mnt/data/
    dati.csv               # Ground truth - NON incluso nel repo, da procurarsi a parte
    screen *.png           # Screenshot di test (9 immagini, tracciate)
  docs/              # Documentazione narrativa in italiano (INDEX.md)
  .env.example             # Template variabili d'ambiente
```

## Ground truth CSV

Il file `mnt/data/dati.csv` **non è versionato** (`/mnt` è in `.gitignore`): va ottenuto dal team e posizionato manualmente. La CLI non parte senza. Formato atteso (long format, 3 colonne):

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

Il loader (`load_ground_truth()` in `extraction/evaluation.py`) supporta nomi colonna alternativi: `Screenshot`/`Screen` per la colonna screen, `Campo`/`Field` per le chiavi, `Valore`/`Value` per i valori.

Per aggiungere nuovi screenshot: inserire le righe nel CSV e posizionare l'immagine `.png` nella stessa directory con nome corrispondente alla colonna `Fotogramma`.
