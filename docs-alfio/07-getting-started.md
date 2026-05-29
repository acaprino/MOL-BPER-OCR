# Per iniziare

Questa è un'applicazione Python proof of concept (prototipo) che estrae dati strutturati da screenshot bancari BPER italiani usando modelli di linguaggio visivo (GPT-4o, Gemini) tramite LangChain. Prima di mettere mano a qualsiasi cosa, tieni presente che il progetto ha tre interfacce separate -- uno strumento batch da CLI, una GUI desktop Tkinter e un edge-agent PyQt6 con cattura dal vivo dello schermo -- che condividono tutte lo stesso pacchetto core `extraction/`. Non ci sono test, niente CI, niente Docker e nessuna configurazione di linter. Il codebase è funzionante ma volutamente grezzo nei dettagli, trattandosi di un POC.

## Prerequisiti

**Richiesti:**
- Python 3.8 o superiore (il team ha usato la 3.13 a giudicare dagli artefatti .pyc compilati)
- Una chiave API OpenAI (per il provider predefinito `gpt-4o`) *oppure* una chiave API Google Gemini
- Git (il repo usa `develop` come branch di lavoro, `master` come principale)

**Richiesti per la classificazione pagina ML dell'edge-agent:**
- PyTorch e torchvision (il modello DINOv2 viene scaricato automaticamente al primo avvio dal torch hub di Facebook Research)

**Facoltativi:**
- PyInstaller (solo se devi compilare un `.exe` autonomo della GUI Tkinter)

**Note sulla piattaforma:**
- La libreria `mss` gestisce la cattura degli screenshot multipiattaforma. Su Linux, `pyscreenshot>=3.1` viene incluso come fallback (vedi il marker di piattaforma in `requirements.txt` riga 11: `pyscreenshot>=3.1; sys_platform == 'linux'`).
- L'overlay dell'edge-agent (`edge-agent/ui/overlay.py`) usa flag di finestra PyQt6 che si comportano diversamente tra Windows e Linux. Lo sviluppo è avvenuto su Windows.

## Setup

**1. Clona e passa al branch di lavoro:**

```bash
git clone <repo-url> poc-data-extraction
cd poc-data-extraction
git checkout develop
```

**2. Crea un ambiente virtuale e installa le dipendenze:**

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

L'unico `requirements.txt` copre sia la pipeline di estrazione sia l'edge-agent. Dipendenze come `torch` e `torchvision` sono pesanti (~2 GB). Se ti serve solo lo strumento batch da CLI, puoi ometterle: il classificatore di pagina ML dell'edge-agent degrada in modo controllato alla modalità `DISABLED` quando torch non è disponibile (`edge-agent/page_classifier.py`).

**3. Configura le variabili d'ambiente:**

```bash
cp .env.example .env
```

Apri `.env` e imposta come minimo:

```
LLM_API_KEY=sk-your-openai-key-here
```

Per Gemini, cambia anche:

```
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
```

Ogni altra variabile ha un valore predefinito sensato. Vedi `.env.example` per l'elenco completo.

**4. Aggiungi i dati di test:**

La directory `mnt/data/` è esclusa da git. Servono i 9 screenshot bancari BPER (da `screen 1.png` a `screen 9.png`) e la ground truth CSV (`dati.csv`) collocati in `mnt/data/`. Richiedi questi file al team: contengono screenshot reali dell'interfaccia bancaria.

```bash
mkdir -p mnt/data
# Copia screen 1.png ... screen 9.png e dati.csv in mnt/data/
```

**5. Esegui l'estrazione batch da CLI:**

```bash
python main.py
```

Questo carica la ground truth CSV, elabora tutti i PNG in `mnt/data/` e stampa su console le metriche di accuratezza e un riepilogo dei costi. Gli output vengono salvati in `mnt/data/poc_outputs_improved.json` e `mnt/data/poc_debug_improved.csv`.

**6. Avvia l'edge-agent (GUI PyQt6):**

```bash
python main.py --gui
```

Oppure direttamente:

```bash
cd edge-agent
python edge_agent.py
```

**7. Avvia la GUI desktop Tkinter:**

```bash
python gui_app.py
```

Questa ti permette di inserire la chiave API nell'interfaccia, scegliere i file manualmente e selezionare provider/modello da un menu a discesa.

## File chiave da leggere per primi

Leggili in questo ordine. Ciascuno si basa sul precedente.

1. **`extraction/config.py`** -- Tutta la gestione delle variabili d'ambiente, le coordinate di ritaglio, le tabelle di prezzo e la `FIELD_RETRY_MAP`. Qui scopri quali manopole esistono e quali sono davvero i valori predefiniti (nota: `PARALLEL_WORKERS` ha valore predefinito `12` nel codice nonostante la documentazione dica `4`).

2. **`extraction/fields.py`** -- L'elenco `FIELD_KEYS` definisce ogni campo che il sistema estrae (oltre 40 campi). `CSV_TO_SCHEMA` mappa i nomi delle colonne italiane della ground truth alle chiavi di schema. Questo è il contratto dati tra l'output del VLM e il sistema di valutazione.

3. **`extraction/schemas.py`** -- Modelli Pydantic (`ExtractionResponse`, `AnchorResponse`, `FieldResult`, `Soggetto`, `Fido`, `Garanzia`) che definiscono l'output strutturato che il VLM deve produrre. `FieldsModel` viene generato dinamicamente da `FIELD_KEYS` in fase di import.

4. **`extraction/pipeline.py`** -- La classe `ExtractionPipeline` orchestra l'estrazione a tre passaggi (anchor, principale, retry). Questo è l'algoritmo centrale. Comprendere `extract_from_image()` è essenziale prima di cambiare qualsiasi cosa.

5. **`extraction/vlm_client.py`** -- Come avvengono effettivamente le chiamate LLM: output strutturato LangChain per OpenAI, JSON in forma libera con parsing manuale Pydantic per i modelli Gemini più recenti. Qui vive la logica di retry con backoff esponenziale.

6. **`extraction/prompts.py`** -- I prompt in lingua italiana (`PROMPT`, `ANCHOR_PROMPT`) inviati al VLM. Sono finemente calibrati sul layout dell'interfaccia bancaria BPER e influenzano direttamente l'accuratezza dell'estrazione.

7. **`extraction/evaluation.py`** -- Caricamento della ground truth, classificazione dell'accuratezza per campo (OK/WRONG/MISSING/HALLUCINATED/OK_NULL) e la suddivisione tra metriche RAW e FILTERED. Leggi questo per capire come vengono misurati i risultati.

8. **`extraction/cli.py`** -- La classe `BatchRunner` e la funzione `main()`. Mostra come i modelli vengono creati una sola volta e condivisi su un `ThreadPoolExecutor`. Contiene anche la funzione commentata `_deduplicate_same_page_outputs()`.

9. **`edge-agent/edge_agent.py`** e **`edge-agent/config.ini`** -- L'entry point PyQt6 e la sua configurazione basata su INI. L'edge-agent ha un proprio sistema di configurazione separato dalle variabili `.env`.

10. **`CLAUDE.md`** -- La documentazione interna del progetto stesso. Esaustiva con le sue 276 righe, copre architettura, convenzioni e vincoli. Alcuni riferimenti sono superati (es. l'entry point Streamlit `app.py` non esiste più).

## Dove si trovano le cose

**Per capire la logica di estrazione:**
Guarda in `extraction/pipeline.py` per l'orchestrazione multi-passaggio. I tre passaggi (anchor, principale, retry) sono metodi di `ExtractionPipeline`. Le coordinate di ritaglio sono in `extraction/config.py` (`CONTENT_CROP`, `HEADER_IN_CONTENT`, `RETRY_AREAS`).

**Per aggiungere o modificare un campo estratto:**
Parti da `extraction/fields.py` -- aggiungi la chiave a `FIELD_KEYS` e aggiungi la mappatura della ground truth a `CSV_TO_SCHEMA`. Poi aggiungi i metadati del campo in `extraction/field_definitions.py` (nome visualizzato e assegnazione di pagina). Lo schema Pydantic in `extraction/schemas.py` si auto-genera da `FIELD_KEYS`, quindi lì non serve alcuna modifica.

**Per cambiare come vengono fatte le chiamate LLM:**
`extraction/vlm_client.py` gestisce tutta la comunicazione VLM. `extraction/llm_factory.py` è la factory che crea le istanze di `ChatModel` LangChain. Il comportamento specifico del provider (output strutturato OpenAI vs JSON in forma libera Gemini) è in `vlm_client.py`.

**Per modificare i prompt del VLM:**
`extraction/prompts.py` contiene `PROMPT` (passaggio principale), `ANCHOR_PROMPT` (passaggio sulla sola intestazione) e `FIELD_RETRY_PROMPTS` (prompt di retry per area). Sono in italiano e calibrati sulla terminologia dell'interfaccia BPER.

**Per cambiare la pre-elaborazione delle immagini:**
`extraction/imaging.py` gestisce la normalizzazione (ridimensionamento, contrasto, unsharp mask) e il ritaglio per la pipeline di estrazione. `edge-agent/image_ops.py` gestisce la pre-elaborazione per il percorso di cattura dal vivo (logica separata).

**Per lavorare sull'interfaccia dell'edge-agent:**
Le implementazioni delle schede sono in `edge-agent/ui/` -- `capture_tab.py` (avvio/stop cattura), `extraction_results_tab.py` (visualizzazione risultati), `data_table_tab.py` (esportazione a foglio di calcolo), `debug_tab.py` (debug del router LLM). La finestra principale le assembla in `edge-agent/ui/main_window.py`.

**Per cambiare il riconoscimento pagina nell'edge-agent:**
`edge-agent/llm_router.py` ha `LLMPageRouter` (OpenAI Vision) e `MLPageRouter` (similarità del coseno DINOv2). La modalità del router si imposta in `edge-agent/config.ini` sotto `[agent] router=`. I prototipi di pagina e le definizioni LLM sono in `edge-agent/assets/templates/bper/`.

**Per cambiare come viene valutata l'accuratezza:**
`extraction/evaluation.py` per il framework di valutazione. `extraction/normalization.py` per la funzione `classify_field()` e la logica di normalizzazione del testo usata per il confronto.

## Attività comuni

### Eseguire l'estrazione batch da CLI e vedere l'accuratezza

```bash
python main.py
```

Questo richiede `mnt/data/dati.csv` (ground truth) e i PNG degli screenshot in `mnt/data/`. Stampa su stdout l'accuratezza per campo (metriche RAW e FILTERED) e un riepilogo dei costi. Gli output finiscono in `mnt/data/poc_outputs_improved.json`.

Per abilitare l'output di debug:

```bash
DEBUG_MODE=1 python main.py
```

Per salvare le immagini di ritaglio intermedie:

```bash
DEBUG_SAVE_CROPS=1 python main.py
```

I ritagli vengono salvati in `mnt/data/debug_crops/`.

### Cambiare provider LLM

Modifica `.env`:

```bash
# Per Gemini
LLM_PROVIDER=gemini
LLM_API_KEY=AI...
LLM_MODEL=gemini-2.0-flash
```

Oppure usa direttamente le variabili d'ambiente:

```bash
LLM_PROVIDER=gemini LLM_API_KEY=AI... LLM_MODEL=gemini-2.0-flash python main.py
```

Anche l'interfaccia Tkinter `gui_app.py` permette di scegliere provider e modello da un menu a discesa a runtime.

### Compilare un eseguibile Windows autonomo

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name "AI_Data_Extractor" --add-data "extraction;extraction" --collect-all langchain_google_genai --collect-all langchain_openai gui_app.py
```

L'`.exe` compare in `dist/AI_Data_Extractor.exe`. Questo impacchetta solo la GUI Tkinter, non l'edge-agent.

### Testare manualmente un singolo screenshot

Non esiste un comando CLI per singola immagine. Il percorso più rapido è collocare un'immagine in `mnt/data/`, assicurarsi che la ground truth CSV abbia righe corrispondenti ed eseguire `python main.py`. Oppure usare `gui_app.py` per selezionare singoli file tramite l'esploratore file.

### Esportare i risultati dell'edge-agent in CSV/Excel

Nella GUI dell'edge-agent, la scheda Dati Estratti (`edge-agent/ui/data_table_tab.py`) fornisce i pulsanti di esportazione CSV ed Excel. Il metodo `LocalExtractionClient.export_csv()` (`edge-agent/local_extraction_client.py`) gestisce la logica di esportazione. L'esportazione Excel usa `openpyxl`.

## Trabocchetti

**Disallineamento del valore predefinito di PARALLEL_WORKERS.** Il codice in `extraction/config.py` riga 11 ha valore predefinito `12`, ma sia `.env.example` sia `CLAUDE.md` dicono `4`. Se esegui senza `.env`, ottieni 12 worker paralleli, che possono saturare i rate limit di una chiave API di fascia gratuita.

**LLM_THINKING_LEVEL sembra incoerente ma di fatto non è impostato.** `extraction/config.py` riga 20 memorizza un valore predefinito `medium` in una costante a livello di modulo, ma quella costante non viene usata da nessuna parte. Il controllo attivo in `extraction/llm_factory.py` riga 72 rilegge la variabile d'ambiente con valore predefinito vuoto, quindi lasciarla non impostata (come fanno sia `.env.example` sia `CLAUDE.md`) tiene disattivata la modalità thinking. Questo riguarda solo i modelli Gemini il cui nome contiene "thinking".

**La directory `mnt/` è esclusa da git.** Non otterrai i dati di test dal repo. La ground truth CSV (`mnt/data/dati.csv`) e tutti i 9 PNG degli screenshot devono essere reperiti separatamente. Senza di essi, `python main.py` solleva `FileNotFoundError`.

**Chiave API in un file di configurazione committato.** Il file `edge-agent/config.ini` riga 23 contiene quella che sembra essere una chiave API OpenAI reale nella sezione `[llm]`. Questa chiave è committata nel controllo di versione. Verifica con il team se vada ruotata.

**App Streamlit mancante.** `CLAUDE.md` fa riferimento a `app.py` come entry point dell'interfaccia web Streamlit, e `streamlit` è in `requirements.txt`, ma nessun `app.py` esiste nel repository. L'interfaccia Streamlit è stata rimossa oppure non è mai stata committata su questo branch.

**L'edge-agent ha un proprio sistema di configurazione.** La pipeline di estrazione usa le variabili d'ambiente `.env` (`extraction/config.py`). L'edge-agent usa `edge-agent/config.ini` analizzato da `edge-agent/config.py`. Sono sistemi separati: cambiare `.env` non influisce sulle impostazioni del router LLM dell'edge-agent, e viceversa. L'edge-agent carica comunque `.env` per la `LLM_API_KEY` della pipeline di estrazione, ma le impostazioni LLM del router provengono da `config.ini`.

**La deduplica è disabilitata.** `_deduplicate_same_page_outputs()` in `extraction/cli.py` (righe 268-275) è implementata ma commentata. Il batch runner attualmente mantiene tutti gli output, anche se più screenshot mappano alla stessa pagina canonica.

**La configurazione viene caricata in fase di import.** `extraction/config.py` legge le variabili d'ambiente all'import del modulo, cosa che avviene quando `main.py` esegue `from extraction import *`. Se imposti le variabili d'ambiente dopo l'import, non avranno effetto. Il file `.env` deve essere caricato prima che il pacchetto extraction venga importato -- `main.py` gestisce correttamente questo con `load_dotenv()` prima dell'import.

**I nomi dei campi italiani sono parte portante.** Chiavi di campo come `professione_principale`, `retribuzione_annua_netta` e `denominazione` non sono traducibili: devono corrispondere allo schema del dominio bancario BPER. Anche i prompt del VLM sono in italiano. Non tradurli.

**torch è una dipendenza opzionale pesante.** Il `requirements.txt` include `torch` e `torchvision` per il classificatore di pagina ML dell'edge-agent. Si tratta di download da ~2 GB. Se ti serve solo l'estrazione da CLI, puoi ometterli. Il classificatore ML degrada in modo controllato alla modalità `DISABLED` (`edge-agent/page_classifier.py`), e l'edge-agent può usare `router = llm` in `config.ini` come alternativa.

## Vedi anche

- [Stack tecnologico](03-tech-stack.md) -- analisi dettagliata di ogni dipendenza, vincoli di versione e cosa è opzionale
- [Anatomia del progetto](09-project-anatomy.md) -- la tabella completa delle variabili d'ambiente e il catalogo dei file di configurazione
- [Guida alla configurazione](10-configuration-guide.md) -- ricette per cambiare provider, abilitare i ritagli di debug e risolvere errori comuni
- [Workflow](05-workflows.md) -- flussi passo passo per il batch da CLI, la cattura dell'edge-agent e la pipeline multi-passaggio
- [Domande aperte](08-open-questions.md) -- discrepanze e decisioni irrisolte che influenzeranno la tua prima modifica
