# poc-data-extraction

**Python 3.8+ | LangChain | OpenAI GPT-4o / Google Gemini | Pillow | Pandas | PyQt6**

Estrazione automatica di dati strutturati da screenshot bancari italiani tramite pipeline VLM (Vision Language Model) multi-pass con **LangChain**. Supporta l'acquisizione in tempo reale tramite un **Edge Agent** (PyQt6) che si collega direttamente alla pipeline di estrazione locale. Estrae 18 campi da ogni schermata, valuta l'accuratezza rispetto a un ground truth CSV e produce metriche per campo e breakdown dei costi.

## Cosa fa

Il sistema riceve screenshot (da file o cattura in tempo reale) e, attraverso tre passaggi VLM successivi (anchor, main, retry), estrae i campi strutturati con valori di confidenza. Ogni campo viene restituito con `value`, `confidence`, `evidence_text` e `section`. Il pipeline include un meccanismo di retry mirato per i campi con confidenza bassa o valore nullo tramite ritagli (crop) specifici dell'immagine.

## Stato Attuale

Il sistema integra l'acquisizione automatica degli screenshot con l'estrazione intelligente, eliminando la necessità di microservizi esterni.
Supporta i principali VLM sul mercato:
- **OpenAI**: `gpt-4o`, `gpt-4o-mini`, `o1`.
- **Google Gemini**: `gemini-1.5-flash`, `gemini-1.5-pro`, `gemini-2.0-flash`, `gemini-3-flash-preview`.

Caratteristiche principali:
- **Edge Agent (GUI)**: Cattura screenshot in tempo reale da monitor selezionati, riconosce la pagina corrente e avvia l'estrazione locale.
- **Parallelismo**: Supporta l'elaborazione simultanea di più immagini nella modalità CLI.
- **Resilienza**: Meccanismo di "Anchor Check" per garantire che i dati estratti appartengano effettivamente al soggetto corretto.
- **Retry Intelligente**: Esegue crop mirati delle aree dell'immagine dove l'estrazione iniziale è fallita.
- **Valutazione Automatica**: Confronta i risultati con un file Ground Truth (`dati.csv`).

## Scopo dei Componenti

### Core Pipeline (`extraction/`)
Il package `extraction` contiene tutta la logica di business, separata dall'interfaccia utente:
- `pipeline.py`: Orchestratore principale dei 3 passaggi (Anchor -> Main -> Retry).
- `llm_factory.py`: Gestisce la creazione dei modelli LangChain per i diversi provider.
- `vlm_client.py`: Interfaccia di basso livello per le chiamate ai modelli con supporto per output strutturato (Pydantic).
- `imaging.py`: Gestisce la manipolazione delle immagini (crop, normalizzazione, compressione).
- `evaluation.py`: Calcola le metriche di accuratezza (OK, WRONG, MISSING) e genera i report di debug.
- `schemas.py`: Definisce la struttura dati dei campi estratti e dei soggetti.
- `config.py`: Centralizza tutte le costanti, le coordinate dei crop e le impostazioni ambientali.

### Interfacce Utente
- **Edge Agent (`main.py --gui`)**: Interfaccia principale per la cattura real-time e l'estrazione locale. Basata su **PyQt6**.
- **Batch CLI (`main.py`)**: Ideale per processamenti batch massivi di file già salvati su disco.
- **Desktop UI (`gui_app.py`)**: Applicazione nativa **Tkinter** per processing locale di file selezionati manualmente.

---

## Come Avviarlo

### 1. Setup Ambiente
```bash
# Installazione dipendenze
pip install -r requirements.txt

# Configurazione (opzionale se si usa la GUI)
cp .env.example .env
# Modificare .env con le proprie API Key
```

### 2. Avvio interfacce

#### Edge Agent (Consigliato)
Per la cattura real-time e l'estrazione intelligente:
```bash
python main.py --gui
```

#### Batch CLI
Per un processing veloce di tutti i file già presenti in `mnt/data/`:
```bash
python main.py
```

#### Desktop App (Tkinter)
Per l'applicazione desktop nativa:
```bash
python gui_app.py
```

---

## Generazione Eseguibile (.exe)

È possibile pacchettizzare l'applicazione Desktop (`gui_app.py`) in un unico file eseguibile per Windows utilizzando **PyInstaller**.

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
- `--add-data "extraction;extraction"`: Include i moduli necessari del progetto.
- `--collect-all`: Forza l'inclusione delle dipendenze dinamiche di LangChain.

L'eseguibile risultante si troverà nella cartella `dist/AI_Data_Extractor.exe`.

## I 18 campi estratti (Principali)

Oltre ai dati dei soggetti (fino a 4 cointestatari con NDG e Ruolo), il sistema estrae:

| # | Campo | Descrizione | Area Crop |
|---|-------|-------------|-----------|
| 1 | `ndg` | Numero di Gestione | HEADER |
| 2 | `denominazione` | Nome del soggetto principale | HEADER |
| 3 | `tipo` | Tipo pratica (es. BPI Mutui) | HEADER |
| 4 | `evidenze` | Evidenze associate | HEADER |
| 5 | `filiale_relazione` | Filiale di relazione | HEADER |
| 6 | `ultima_validazione` | Data ultima validazione scheda | HEADER |
| 7 | `professione_principale` | Professione principale | BODY |
| 8 | `retribuzione_annua_netta` | Reddito annuo | BODY |
| 9 | `tipo_contratto` | Tempo determ./indeterm. | BODY |
| 10 | `numero_mensilita` | Numero mensilità | BODY |
| 11 | `datore_di_lavoro` | Azienda / Anagrafica | BODY |
| 12 | `dal` | Data inizio rapporto lavoro | BODY |
| 13 | `rating_ufficiale` | Rating banca | BODY |
| 14 | `score_cgs` | Score di credito | BODY |
| 15 | `nr_componenti_nucleo` | Nucleo familiare | BODY |
| 16 | `percepiscono_reddito` | Numero redditi in famiglia | BODY |
| 17 | `importo_totale_annuo` | Reddito totale nucleo | BODY |
| 18 | `note` | Note libere della richiesta | FOOTER |

## Configurazione

Tutte le variabili sono configurabili via environment. Vedi [`.env.example`](.env.example) per il template completo.

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `LLM_PROVIDER` | `openai` | Provider: `openai` o `gemini` |
| `LLM_API_KEY` | *(obbligatoria)* | Chiave API (OpenAI o Gemini a seconda del provider) |
| `LLM_MODEL` | `gpt-4o` | Modello per estrazione principale |
| `LLM_MODEL_ANCHOR` | come `LLM_MODEL` | Modello per il pass anchor |
| `LLM_THINKING_LEVEL` | *(nessuno)* | Gemini 3+ thinking budget: `low`, `medium`, `high` |
| `INPUT_DIR` | `mnt/data` | Directory dati (screenshot + ground truth) |
| `PARALLEL_WORKERS` | `4` | Numero thread paralleli |
| `MAX_CALLS_PER_SCREEN` | `4` | Massimo chiamate VLM per screenshot |
| `ANCHOR_CONF_MIN` | `0.95` | Confidenza minima per accettare gli anchor |
| `STOP_ON_ANCHOR_UNCERTAIN` | `0` | Fermare il processing se anchor e' incerto (`1` per attivare) |
| `DEBUG_SAVE_CROPS` | `0` | Salvare i crop intermedi su disco per debug |

## Output JSON

Ogni screenshot produce un oggetto con questa struttura:

```json
{
  "screen_id": "screen 1",
  "attempt": "CONTENT_MAIN",
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
  "_meta_agg": {
    "calls": 3,
    "prompt_tokens": 12500,
    "completion_tokens": 800,
    "estimated_cost_usd": 0.035,
    "latency_ms": 8500
  },
  "_field_sources": { "ndg": "ANCHOR_HEADER", "tipo": "CONTENT_MAIN", "note": "RETRY_note" },
  "_status": "OK"
}
```

## Valutazione accuratezza

Il sistema classifica ogni campo estratto con uno dei 5 status:

| Status | Significato |
|--------|-------------|
| **OK** | Valore estratto corrisponde al ground truth |
| **WRONG** | Valore estratto non corrisponde |
| **MISSING** | Ground truth ha un valore, estrazione ha restituito null |
| **HALLUCINATED** | Ground truth e' nullo, ma l'estrazione ha prodotto un valore |
| **OK_NULL** | Entrambi nulli — corretto |

Le metriche sono calcolate in due varianti:
- **RAW**: tutti gli screen, inclusi quelli con mismatch dataset (NDG/DENOMINAZIONE estratti diversi dal GT)
- **FILTERED**: esclude screen con mismatch, per evitare falsi negativi

## Struttura progetto

```
poc-data-extraction/
  main.py                  # Entry point (CLI o --gui)
  gui_app.py               # Entry point Desktop (Tkinter)
  edge-agent/              # Codice dell'Edge Agent (PyQt6)
    edge_agent.py          # Entry point GUI
    local_extraction_client.py # Ponte tra GUI e ExtractionPipeline
  extraction/
    __init__.py            # Re-export API pubblica
    config.py              # Configurazione env-var, crop, pricing
    fields.py              # 18 field keys + CSV_TO_SCHEMA mapping
    schemas.py             # Pydantic models per output strutturato
    prompts.py             # Prompt italiano per VLM
    normalization.py       # Normalizzazione testo, classify_field, pick_best
    imaging.py             # Crop, resize, conversione immagini
    vlm_client.py          # LangChain structured output + retry
    llm_factory.py         # LangChain ChatModel factory (create_chat_model)
    pipeline.py            # Pipeline 3-pass (anchor -> main -> retry)
    evaluation.py          # Metriche accuratezza + debug report
    cli.py                 # Batch runner con ThreadPoolExecutor
  mnt/data/
    dati.csv               # Ground truth
    screen *.png           # Screenshot di test (5 immagini)
  .env.example             # Template variabili d'ambiente
```

## Ground truth CSV

Il file `mnt/data/dati.csv` ha il formato:

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

Il loader (`load_ground_truth()`) supporta nomi colonna alternativi: `Screenshot`/`Screen` per la colonna screen, `Valore`/`Value` per i valori, `Campo`/`Field` per le chiavi.

Per aggiungere nuovi screenshot: inserire le righe nel CSV e posizionare l'immagine `.png` nella stessa directory con nome corrispondente alla colonna `Fotogramma`.
