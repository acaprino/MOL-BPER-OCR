# poc-data-extraction

**Python 3.8+ | LangChain | OpenAI GPT-4o / Google Gemini | Pillow | Pandas | Streamlit**

Estrazione automatica di dati strutturati da screenshot bancari italiani tramite pipeline VLM (Vision Language Model) multi-pass con **LangChain**. Supporta OpenAI e Google Gemini come provider tramite un'unica factory LangChain. Estrae 18 campi da ogni schermata, valuta l'accuratezza rispetto a un ground truth CSV e produce metriche per campo e breakdown dei costi.

## Cosa fa

Il sistema riceve screenshot di schermate bancarie e, attraverso tre passaggi VLM successivi (anchor, main, retry), estrae 18 campi strutturati con valori di confidenza. Ogni campo viene restituito con `value`, `confidence`, `evidence_text` e `section`. Il pipeline include un meccanismo di retry mirato per i campi con confidenza bassa o valore nullo.

## Quick Start

### Prerequisiti

- Python 3.8+
- Chiave API OpenAI **oppure** Google Gemini

### Setup

```bash
pip install -r requirements.txt

# Configurare le variabili d'ambiente
cp .env.example .env
# Editare .env e inserire le proprie chiavi API
```

### Esecuzione con OpenAI (default)

```bash
export LLM_API_KEY="sk-..."
python main.py                  # CLI batch
streamlit run app.py            # Web UI su localhost:8501
```

### Esecuzione con Google Gemini

```bash
export LLM_PROVIDER=gemini
export LLM_API_KEY="AI..."
export LLM_MODEL=gemini-1.5-flash
python main.py                  # CLI batch
streamlit run app.py            # Web UI su localhost:8501
```

### Cambio provider da Streamlit

Nella sidebar della web UI si puo' selezionare il provider (OpenAI / Gemini) e il modello direttamente dall'interfaccia, senza modificare variabili d'ambiente.

## Architettura — Pipeline Multi-Pass

```
Screenshot (.png)
    |
    v
[normalize + crop contenuto]
    |
    +---> Pass 1: ANCHOR (crop header)
    |         Estrae NDG + DENOMINAZIONE (conf >= 0.95)
    |         Se incerto → ANCHOR_UNCERTAIN
    |
    +---> Pass 2: MAIN (crop contenuto intero)
    |         Estrae tutti i 18 campi + soggetti
    |         Con hint: "NDG atteso: ..., Denominazione attesa: ..."
    |
    +---> Pass 3: RETRY (crop mirati per campo)
              Solo campi con value=null o confidence < 0.55
              Ogni campo ha una regione di crop dedicata
              Valore migliore selezionato via pick_best()
    |
    v
Output JSON strutturato + _meta (costi, token, latenza)
```

## I 18 campi estratti

| # | Campo | Descrizione |
|---|-------|-------------|
| 1 | `ndg` | Numero di Gestione |
| 2 | `denominazione` | Nome del soggetto |
| 3 | `tipo` | Tipo pratica (es. BPI Mutui) |
| 4 | `evidenze` | Evidenze associate |
| 5 | `filiale_relazione` | Filiale di relazione |
| 6 | `ultima_validazione` | Data ultima validazione |
| 7 | `professione_principale` | Professione principale |
| 8 | `numero_mensilita` | Numero mensilita' |
| 9 | `retribuzione_annua_netta` | Retribuzione annua netta |
| 10 | `tipo_contratto` | Tipo di contratto |
| 11 | `anagrafica` | Datore di lavoro / anagrafica |
| 12 | `dal` | Data inizio |
| 13 | `rating_ufficiale` | Rating ufficiale |
| 14 | `score_cgs` | Score CGS |
| 15 | `nr_altri_componenti_nucleo_familiare` | Numero altri componenti nucleo |
| 16 | `di_cui_percepiscono_reddito` | Di cui percepiscono reddito |
| 17 | `importo_totale_annuo_altri_componenti` | Importo totale annuo altri componenti |
| 18 | `note` | Note libere |

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
  main.py                  # Entry point CLI (shim)
  app.py                   # Entry point Streamlit
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
