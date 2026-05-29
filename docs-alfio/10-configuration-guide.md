# Guida alla configurazione e all'uso

Questa guida accompagna la configurazione di poc-data-extraction da un clone pulito fino a un'esecuzione di estrazione funzionante, copre i comandi di tutti i giorni che digiterai davvero e documenta i messaggi di errore in cui ti imbatterai quando qualcosa si rompe. Il progetto ha due sistemi di configurazione indipendenti -- variabili d'ambiente (`.env`) per la pipeline di estrazione principale, e un file INI (`edge-agent/config.ini`) per l'agente desktop di cattura -- e capire quale dei due controlla cosa fa risparmiare tempo reale di debugging.

## Procedura di configurazione

### Passo 1: Installare le dipendenze

```bash
pip install -r requirements.txt
```

Il `requirements.txt` alla radice del progetto (`D:\Projects\poc-data-extraction\requirements.txt`) copre sia la pipeline di estrazione sia l'edge-agent. Due dipendenze pesanti meritano attenzione:

- **torch / torchvision** -- necessarie solo per il classificatore ML delle pagine nell'edge-agent. Se le ometti, il classificatore degrada in modalità `DISABLED` e l'agente continua comunque a funzionare (ricade sul router pagina LLM). L'installazione occupa molto spazio su disco.
- **PyQt6 / qt-material** -- necessarie solo per la GUI dell'edge-agent (`main.py --gui` o `edge-agent/edge_agent.py`). Non servono per la modalità batch da CLI.

Se ti serve solo l'estrazione batch da CLI, funziona un'installazione minimale:

```bash
pip install langchain-core langchain-openai langchain-google-genai pillow pandas python-dotenv
```

### Passo 2: Creare il file .env

```bash
cp .env.example .env
```

Il template si trova in `D:\Projects\poc-data-extraction\.env.example`. Un solo valore è obbligatorio -- tutto il resto ha default funzionanti.

**Devi impostare:**

| Variabile | Cosa inserire qui |
|----------|-----------------|
| `LLM_API_KEY` | La tua chiave API OpenAI o Google Gemini |

**Puoi lasciare i default:**

| Variabile | Default | Perché va bene |
|----------|---------|---------------|
| `LLM_PROVIDER` | `openai` | Funziona se la tua chiave è una chiave OpenAI |
| `LLM_MODEL` | `gpt-4o` | Migliore accuratezza per l'estrazione |
| `INPUT_DIR` | `mnt/data` | Posizione standard della directory dei dati |
| `PARALLEL_WORKERS` | `4` (in .env.example) | Adatto alla maggior parte delle macchine |
| `MAX_CALLS_PER_SCREEN` | `4` | Bilancia accuratezza e costo |
| `ANCHOR_CONF_MIN` | `0.95` | L'asticella alta per l'accettazione dell'anchor è intenzionale |

**Importante discrepanza nei default:** Il codice in `extraction/config.py` (riga 11) imposta come default `PARALLEL_WORKERS` a `12` quando la variabile d'ambiente non è definita. Il template `.env.example` la imposta a `4`. Se crei `.env` dal template, ottieni 4 worker. Se salti del tutto la creazione di `.env`, ne ottieni 12. Impostala esplicitamente per evitare sorprese.

### Passo 3: Preparare i dati di test

La modalità batch da CLI si aspetta gli screenshot e un CSV di ground truth in `INPUT_DIR` (default: `mnt/data/`). Questa directory è in gitignore (`/mnt` in `.gitignore`), quindi non sarà presente dopo il clone.

```bash
mkdir -p mnt/data
```

Colloca i tuoi screenshot bancari BPER (`.png` o `.jpg`) in `mnt/data/`. Per la valutazione dell'accuratezza, fornisci anche `mnt/data/dati.csv` -- un CSV con tre colonne:

```
Fotogramma,Denominazione da attribuire,Valore rilevato
screen 1,NDG,31943680
screen 1,DENOMINAZIONE,"TICCHI SERENA"
screen 1,Tipo,BPI Mutui
```

Il loader del CSV in `extraction/evaluation.py` (funzione `_find_column()`, riga 26) rileva automaticamente nomi di colonna alternativi: `Screenshot`/`Screen`/`screen` per la colonna della schermata, `Valore`/`Value` per i valori, `Campo`/`Field` per le chiavi.

### Passo 4: Configurare l'Edge Agent (opzionale)

L'edge-agent ha il proprio file di configurazione in `D:\Projects\poc-data-extraction\edge-agent\config.ini`. È un normale file INI con sei sezioni. Le impostazioni più importanti da rivedere:

```ini
[agent]
router = llm          # ml | llm | hybrid
monitor_index = 1     # which monitor to capture (1-based)

[llm]
provider = openai
model = gpt-4o-mini
api_key = <your-key>  # or leave blank and rely on .env LLM_API_KEY
```

**Nota di sicurezza:** Il `config.ini` committato contiene una chiave API alla riga 23. Sostituiscila con la tua oppure cancellala e affidati invece al file `.env`. L'edge-agent carica `.env` dalla radice del progetto all'avvio (`edge-agent/edge_agent.py`, righe 9-12), e il `LLMPageRouter` ricade sulle variabili d'ambiente `OPENAI_API_KEY` e `LLM_API_KEY` (`bper_capture_worker.py`, riga 122).

### Ordine di caricamento della configurazione

I valori si risolvono con questa priorità (vince il primo):

1. File `.env` -- caricato da `python-dotenv` in cima a `main.py` (riga 7) e `edge-agent/edge_agent.py` (riga 11)
2. `extraction/config.py` -- legge `os.getenv()` al momento dell'import con default cablati nel codice
3. `edge-agent/config.ini` -- letto da `AgentConfig.__init__()` in `edge-agent/config.py` (riga 109)

La pipeline di estrazione legge solo le variabili d'ambiente. L'edge-agent legge sia `.env` (per `LLM_API_KEY`) sia `config.ini` (per impostazioni specifiche dell'agente come FPS, modalità del router, indice del monitor).

## Profili d'ambiente

Questo progetto non ha profili d'ambiente formali (niente `NODE_ENV`, nessuna separazione staging/produzione). Tutta la configurazione passa attraverso un unico file `.env` e il `config.ini` dell'edge-agent.

### Passare da un provider all'altro

Alterna tra OpenAI e Gemini cambiando due variabili in `.env`:

**OpenAI (default):**
```
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o
```

**Google Gemini:**
```
LLM_PROVIDER=gemini
LLM_API_KEY=AI...
LLM_MODEL=gemini-2.0-flash
```

La factory in `extraction/llm_factory.py` valida le combinazioni provider-modello e solleva `ValueError` se non corrispondono (es. un modello `gpt-` con provider `gemini`, o viceversa).

### Modalità debug vs. modalità normale

Abilita l'output di debug impostando due variabili in `.env`:

```
DEBUG_MODE=1
DEBUG_SAVE_CROPS=1
```

`DEBUG_MODE` (letta in `extraction/config.py`, riga 88) abilita righe di log `[DEBUG]` verbose da `BatchRunner` in `extraction/cli.py`. `DEBUG_SAVE_CROPS` (riga 89) scrive ogni immagine di ritaglio intermedia in `{INPUT_DIR}/debug_crops/` tramite `save_debug_crop()` in `extraction/imaging.py` (riga 37).

Per l'edge-agent, l'output di debug è controllato in `config.ini`:

```ini
[debug]
show_llm_tab = true
```

Questo mostra la scheda di debug LLM nell'interfaccia dell'edge-agent, esponendo le coppie grezze prompt/risposta del router pagina. Puoi anche avviare con il flag `--debug`: `python edge-agent/edge_agent.py --debug`.

## Ricette di configurazione

### Usare un modello più economico per iterare più velocemente

In `.env`:
```
LLM_MODEL=gpt-4o-mini
```

Oppure per Gemini:
```
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
```

I modelli supportati sono elencati in `extraction/config.py` righe 22-32 (dict `PROVIDER_MODELS`):
- OpenAI: `gpt-4o`, `gpt-4o-mini`, `o1`, `o1-mini`
- Gemini: `gemini-1.5-pro`, `gemini-1.5-flash`, `gemini-2.0-flash`, `gemini-2.0-flash-exp`, `gemini-2.0-flash-thinking-exp`, `gemini-3-flash-preview`

### Usare un modello diverso per il passaggio anchor

Il passaggio anchor estrae solo NDG e DENOMINAZIONE dalla striscia di intestazione. Puoi assegnargli un modello più veloce/economico mantenendo l'estrazione principale su un modello più potente:

```
LLM_MODEL=gpt-4o
LLM_MODEL_ANCHOR=gpt-4o-mini
```

Se `LLM_MODEL_ANCHOR` non è impostata, ricade su qualunque sia `LLM_MODEL` (`extraction/config.py`, riga 19).

### Puntare a una directory di screenshot diversa

```
INPUT_DIR=path/to/my/screenshots
```

Il CSV di ground truth è atteso in `{INPUT_DIR}/dati.csv` (`extraction/config.py`, riga 9). Anche i file di output finiscono in `INPUT_DIR`:
- `poc_outputs_improved.json` -- risultati dell'estrazione
- `poc_debug_improved.csv` -- report di debug per singolo campo

### Disabilitare l'elaborazione parallela

```
PARALLEL_ENABLED=0
```

Questo forza l'estrazione sequenziale, uno screenshot alla volta. Utile per il debug o quando si incontrano i limiti di frequenza delle API. Definito in `extraction/config.py`, riga 12.

### Ridurre le chiamate VLM per screenshot

```
MAX_CALLS_PER_SCREEN=2
```

La pipeline usa sempre 2 chiamate minimo (1 anchor + 1 principale). I passaggi di retry consumano chiamate aggiuntive. Impostando questo valore a `2` si disabilitano tutti i retry. Il default di `4` consente fino a 2 aree di retry. Definito in `extraction/config.py`, riga 50.

### Abilitare la modalità thinking di Gemini

Per i modelli "thinking" di Gemini 3+:

```
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash-thinking-exp
LLM_THINKING_LEVEL=low
```

Valori validi: `low`, `medium`, `high`. Il livello di thinking viene applicato solo quando il nome del modello contiene "thinking" (`extraction/llm_factory.py`, riga 73). Nota: `extraction/config.py` riga 20 memorizza anche un default `medium`, ma quella costante non viene mai consumata -- `llm_factory.py` legge la variabile d'ambiente direttamente con un default vuoto. Se non imposti la variabile in `.env`, la modalità thinking resta disattivata.

### Cambiare il router pagina dell'edge-agent

In `edge-agent/config.ini`, sezione `[agent]`:

```ini
# ML-only (requires torch):
router = ml

# LLM-only (requires API key, no torch needed):
router = llm

# Try LLM first, fall back to ML:
router = hybrid
```

Il router ML usa il prototype matching DINOv2 (`edge-agent/page_classifier.py`). Il router LLM usa OpenAI Vision (`edge-agent/llm_router.py`). La modalità hybrid prova prima l'LLM e ricade sull'ML in caso di fallimento.

### Cambiare il monitor catturato

In `edge-agent/config.ini`:

```ini
[agent]
monitor_index = 2
```

Usa l'indicizzazione a partire da 1 (convenzione mss). Se l'indice è fuori intervallo, ricade sul monitor 1 (`bper_capture_worker.py`, righe 569-571).

### Interrompere l'elaborazione su anchor incerti

```
STOP_ON_ANCHOR_UNCERTAIN=1
```

Quando abilitato, se sia NDG che DENOMINAZIONE tornano nulli dal passaggio anchor, la pipeline si ferma immediatamente e restituisce lo stato `ANCHOR_UNCERTAIN` invece di procedere al passaggio principale. Questo risparmia costi API sugli screenshot illeggibili. Definito in `extraction/config.py`, riga 51; controllato in `extraction/pipeline.py`, riga 112.

## Operazioni comuni

### Eseguire l'estrazione batch da CLI

```bash
python main.py
```

Elabora tutti i file `.png`/`.jpg`/`.jpeg` in `INPUT_DIR`, esegue su ciascuno la pipeline multi-passaggio, valuta rispetto al ground truth e stampa le metriche di accuratezza e il riepilogo dei costi. Output:
- `mnt/data/poc_outputs_improved.json` -- risultati completi dell'estrazione
- `mnt/data/poc_debug_improved.csv` -- confronto di debug per singolo campo

L'output atteso in console include:
```
Parallel enabled: workers=4, screens=9
Done screen 1
Done screen 2
...
OVERALL (RAW):      35/40 = 87.50%
OVERALL (FILTERED): 33/38 = 86.84%

COST SUMMARY (per screen):
  screen 1    calls= 3  tokens=12500  cost=$0.0350  status=OK
  ...
TOTAL: calls=27  tokens=112000  cost=$0.3150
```

### Avviare la GUI dell'edge-agent

```bash
python main.py --gui
```

Oppure direttamente:

```bash
cd edge-agent
python edge_agent.py
```

Il flag `--debug` abilita la scheda di debug LLM:

```bash
python edge-agent/edge_agent.py --debug
```

### Avviare la GUI desktop Tkinter

```bash
python gui_app.py
```

Questa GUI autonoma (`D:\Projects\poc-data-extraction\gui_app.py`) fornisce la selezione dei file, un menu a tendina provider/modello e un visualizzatore dei risultati. Legge `LLM_API_KEY` dall'ambiente ma ha anche un campo di input per la chiave API nell'interfaccia (riga 24).

### Compilare un eseguibile Windows

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name "AI_Data_Extractor" --add-data "extraction;extraction" --collect-all langchain_google_genai --collect-all langchain_openai gui_app.py
```

L'output finisce in `dist/AI_Data_Extractor.exe`. Questo impacchetta solo la GUI Tkinter, non l'edge-agent.

### Visualizzare i ritagli di debug

Imposta `DEBUG_SAVE_CROPS=1` in `.env`, poi esegui l'estrazione. Le immagini dei ritagli vengono salvate in `{INPUT_DIR}/debug_crops/` con nomi come `screen 1__CONTENT.png`, `screen 1__HEADER_IN_CONTENT.png`, `screen 1__RETRY_HEADER.png`. Questo aiuta a verificare che le coordinate di ritaglio della pipeline cadano sulle regioni corrette.

### Esportare i risultati dall'edge-agent

Nell'interfaccia dell'edge-agent:
1. **Scheda Risultati** -- clicca sull'esportazione CSV per salvare i risultati per singolo campo
2. **Scheda Dati** -- vista a foglio di calcolo con esportazione CSV ed Excel (Excel tramite `openpyxl`)

Il metodo `LocalExtractionClient.export_csv()` (`edge-agent/local_extraction_client.py`, riga 112) genera un CSV piatto con colonne `{field}_value` e `{field}_conf`.

## Risoluzione dei problemi

### "API key required. Set LLM_API_KEY env var or pass api_key="

**Sintomo:** `ValueError: API key required. Set LLM_API_KEY env var or pass api_key=.`

**Causa:** Nessuna chiave API è stata trovata. La factory in `extraction/llm_factory.py` (riga 42) controlla `LLM_API_KEY`, poi ricade sulle variabili legacy `OPENAI_API_KEY` / `GEMINI_API_KEY` (righe 30-38). Erano tutte vuote.

**Soluzione:** Imposta `LLM_API_KEY` nel tuo file `.env`. Verifica che il file sia nella radice del progetto e che `python-dotenv` sia installato (`pip install python-dotenv`). Se usi la GUI Tkinter, puoi anche incollare la chiave direttamente nel campo API Key.

### "Unknown provider" o discrepanza modello-provider

**Sintomo:** `ValueError: Unknown provider: 'xyz'. Available: ['openai', 'gemini']`
oppure: `ValueError: Model 'gemini-2.0-flash' looks like a Gemini model but provider is 'openai'.`

**Causa:** `LLM_PROVIDER` non corrisponde al nome del modello, o è impostata su qualcosa di diverso da `openai` o `gemini`. La validazione è in `extraction/llm_factory.py`, righe 49-53 e 59-62.

**Soluzione:** Assicurati che `LLM_PROVIDER` e `LLM_MODEL` siano coerenti:
```
# OpenAI models: gpt-4o, gpt-4o-mini, o1, o1-mini
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o

# Gemini models: gemini-1.5-flash, gemini-2.0-flash, etc.
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
```

### "Ground truth CSV not found"

**Sintomo:** `FileNotFoundError: Ground truth CSV not found: mnt/data/dati.csv`

**Causa:** L'entry point della CLI (`extraction/cli.py`, riga 316) richiede che `dati.csv` esista in `{INPUT_DIR}/dati.csv`. La directory `mnt/` è in gitignore e non è presente dopo un clone pulito.

**Soluzione:** Crea la directory e fornisci il CSV:
```bash
mkdir -p mnt/data
# copy your dati.csv and screenshot files here
```

Oppure cambia `INPUT_DIR` in `.env` per puntare al punto in cui risiedono i tuoi dati:
```
INPUT_DIR=path/to/my/data
```

### "Cannot find column in CSV"

**Sintomo:** `ValueError: Cannot find screen column in CSV. Columns=['Col1', 'Col2', ...]`

**Causa:** Il CSV di ground truth non contiene nessuno dei nomi di colonna attesi. Il loader in `extraction/evaluation.py` (funzione `_find_column()`, riga 26) cerca candidati specifici:
- Colonna della schermata: `Screenshot`, `Fotogramma`, `Screen`, `screen`
- Colonna del valore: `Valore rilevato`, `Valore rilevato ` (con spazio finale), `Valore`, `Value`
- Colonna della chiave: `Denominazione da attribuire`, `Denominazione`, `Campo`, `Field`

**Soluzione:** Rinomina le colonne del tuo CSV per farle corrispondere a uno dei nomi attesi. Il formato più comune è:
```csv
Fotogramma,Denominazione da attribuire,Valore rilevato
```

### "No images found in INPUT_DIR"

**Sintomo:** La console stampa `No images found in mnt/data` ed esce senza elaborare.

**Causa:** Nessun file `.png`, `.jpg` o `.jpeg` esiste nell'`INPUT_DIR` configurato. La scoperta dei file è in `extraction/cli.py`, righe 322-327.

**Soluzione:** Colloca i file degli screenshot nella directory `INPUT_DIR`. Verifica il percorso: `ls mnt/data/*.png`

### "No JSON object found in model response"

**Sintomo:** `ValueError: No JSON object found in model response: '...'`

**Causa:** Il modello Gemini ha restituito testo in forma libera invece di JSON. Questo accade con il percorso freeform di Gemini in `extraction/vlm_client.py` (riga 39) quando i modelli Gemini più recenti (2.0+) producono risposte senza un oggetto JSON valido. Si tratta di un `ValueError`, quindi la logica di retry non lo riprova -- fallisce immediatamente (righe 252-253).

**Soluzione:** Prova un modello Gemini diverso. `gemini-1.5-flash` e `gemini-1.5-pro` usano la modalità JSON basata su schema, che è più affidabile. Per i modelli 2.0+, il codice ricade sul parsing JSON in forma libera, intrinsecamente meno stabile.

### "Pydantic validation failed" o "Structured output parsing failed"

**Sintomo:** `ValueError: Pydantic validation failed for screen 1/CONTENT_MAIN: ...` oppure `ValueError: Structured output parsing failed for screen 1/CONTENT_MAIN: ...`

**Causa:** L'LLM ha restituito JSON che non corrisponde allo schema Pydantic atteso. Il fallimento del parsing dell'output strutturato OpenAI viene catturato in `extraction/vlm_client.py`, righe 199-202. Il fallimento della validazione freeform di Gemini è alle righe 95-98.

**Soluzione:** Questi errori sono non ripetibili per scelta progettuale. Tipicamente indicano che il modello ha avuto difficoltà con l'immagine. Opzioni: prova un modello più capace (`gpt-4o` invece di `gpt-4o-mini`), oppure verifica che lo screenshot sia una schermata bancaria BPER valida.

### "mss non disponibile"

**Sintomo:** L'edge-agent si ferma con `RuntimeError: mss non disponibile: ...`

**Causa:** La libreria di screenshot `mss` non è riuscita a inizializzarsi. Questo errore viene sollevato in `edge-agent/workers/capture/bper_capture_worker.py`, riga 562. Comune negli ambienti privi di display server.

**Soluzione:** Assicurati di eseguire su una macchina con un display. Su Windows dovrebbe funzionare immediatamente. Su Linux, assicurati che X11 o Wayland siano in esecuzione. Installa `mss` se manca: `pip install mss>=9.0.0`.

### "Cattura fallita N volte consecutive"

**Sintomo:** L'edge-agent si ferma automaticamente con `RuntimeError: Cattura fallita 5 volte consecutive. Ultimo errore: ...`

**Causa:** Cinque catture di screenshot consecutive sono fallite. Il contatore è in `bper_capture_worker.py`, righe 589-598. Di solito significa che l'indice del monitor configurato non esiste.

**Soluzione:** Controlla `monitor_index` in `edge-agent/config.ini`. Impostalo a `1` per il monitor primario. Se hai più monitor, usa `2`, `3`, ecc. L'indice parte da 1 secondo la convenzione `mss`.

### Classificatore ML disabilitato / fallimento dell'import di torch

**Sintomo:** Il log dell'edge-agent mostra `[BPER-ML] import_error: ...` oppure `[BPER] Router disabilitato.`

**Causa:** `torch` o `torchvision` non sono riusciti a importarsi. `page_classifier.py` è progettato per degradare con grazia -- si imposta in modalità `DISABLED` e `classify()` restituisce `(None, 0.0)`. Vedi `edge-agent/page_classifier.py`, righe 137-165.

**Soluzione:** Se ti serve la classificazione ML delle pagine, installa PyTorch: `pip install torch torchvision`. Se non ti serve, passa al router LLM in `config.ini`:
```ini
[agent]
router = llm
```

### "LLM client non inizializzato (manca API key o import OpenAI fallito)"

**Sintomo:** La scheda di debug LLM dell'edge-agent mostra questo errore. Il riconoscimento pagina non restituisce corrispondenze.

**Causa:** Il `LLMPageRouter` in `edge-agent/llm_router.py` (riga 148) non è riuscito a creare un client OpenAI. O il pacchetto `openai` non è installato, oppure non è stata fornita alcuna chiave API.

**Soluzione:** Assicurati che `openai` sia installato (`pip install openai>=1.51.0`). Imposta la chiave API in `edge-agent/config.ini` sotto `[llm] api_key = ...` oppure in `.env` come `LLM_API_KEY=...` o `OPENAI_API_KEY=...`.

### Limiti di frequenza ed errori API transitori

**Sintomo:** L'estrazione è lenta con fallimenti intermittenti, poi alla fine riesce o fallisce dopo i retry.

**Causa:** La logica di retry in `extraction/vlm_client.py` (funzione `call_vlm_with_retry`, righe 240-258) gestisce gli errori transitori con backoff esponenziale: `min(8.0, 2^i * 0.8) + 0.05*i` secondi, fino a 3 retry. Le eccezioni `ValueError` (fallimenti di parsing) non vengono ripetute.

**Soluzione:** Riduci `PARALLEL_WORKERS` per abbassare le chiamate API concorrenti. Se usi una chiave API di livello gratuito, imposta `PARALLEL_WORKERS=1` e `PARALLEL_ENABLED=0`.

### Avviso di deprecazione: "OPENAI_API_KEY is deprecated. Use LLM_API_KEY instead."

**Sintomo:** `DeprecationWarning: OPENAI_API_KEY is deprecated. Use LLM_API_KEY instead.`

**Causa:** Hai `OPENAI_API_KEY` o `GEMINI_API_KEY` impostate nel tuo ambiente ma non `LLM_API_KEY`. La factory in `extraction/llm_factory.py` (righe 36-40) accetta ancora i nomi legacy ma avvisa al riguardo.

**Soluzione:** Rinomina la variabile nel tuo `.env`:
```
# Before:
OPENAI_API_KEY=sk-...

# After:
LLM_API_KEY=sk-...
```

## Riferimento rapido

| Attività | Comando | Note |
|------|---------|-------|
| Installare le dipendenze | `pip install -r requirements.txt` | Installazione completa incluso l'edge-agent |
| Creare la configurazione | `cp .env.example .env` | Poi imposta `LLM_API_KEY` |
| Eseguire l'estrazione batch da CLI | `python main.py` | Servono screenshot in `INPUT_DIR` + `dati.csv` |
| Avviare l'edge-agent | `python main.py --gui` | Cattura dal vivo + estrazione con PyQt6 |
| Avviare l'edge-agent (diretto) | `python edge-agent/edge_agent.py` | Come sopra, salta lo shim main.py |
| Avviare l'edge-agent (debug) | `python edge-agent/edge_agent.py --debug` | Mostra la scheda di debug LLM |
| Avviare la GUI Tkinter | `python gui_app.py` | App desktop autonoma |
| Passare a Gemini | Imposta `LLM_PROVIDER=gemini` e `LLM_MODEL=gemini-2.0-flash` in `.env` | Cambia anche `LLM_API_KEY` con la chiave Gemini |
| Abilitare i ritagli di debug | Imposta `DEBUG_SAVE_CROPS=1` in `.env` | Ritagli salvati in `{INPUT_DIR}/debug_crops/` |
| Disabilitare il parallelismo | Imposta `PARALLEL_ENABLED=0` in `.env` | Elaborazione sequenziale |
| Compilare il .exe Windows | `pyinstaller --noconfirm --onefile --windowed --name "AI_Data_Extractor" --add-data "extraction;extraction" --collect-all langchain_google_genai --collect-all langchain_openai gui_app.py` | Impacchetta solo la GUI Tkinter |
| Cambiare il router dell'edge-agent | Imposta `router = ml` o `llm` o `hybrid` in `edge-agent/config.ini` | ML richiede torch |
| Cambiare il monitor di cattura | Imposta `monitor_index = N` in `edge-agent/config.ini` | Indice a partire da 1 |

---

Riferimenti incrociati: [Anatomia del progetto](09-project-anatomy.md) per il catalogo completo delle variabili d'ambiente, dei file di configurazione e delle loro posizioni. [Per iniziare](07-getting-started.md) per il setup iniziale e la prima esecuzione. [Tech Stack](03-tech-stack.md) per i dettagli sulle dipendenze e i vincoli di versione.
