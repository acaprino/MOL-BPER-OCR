# Guida alla configurazione e all'uso

Questo progetto si configura quasi interamente con variabili d'ambiente, con un'eccezione: l'edge-agent PyQt6 legge le proprie impostazioni da `edge-agent/config.ini`. Non c'è database da predisporre né server da avviare. La CLI legge screenshot e ground truth; Tkinter accetta immagini con valutazione opzionale, mentre l’edge-agent acquisisce il monitor senza CSV di riferimento. Questa guida costruisce una configurazione funzionante da zero, spiega la scelta OpenAI-vs-Gemini che guida la maggior parte del setup, offre ricette copia-incolla per le manopole che girerai davvero, elenca i comandi ricorrenti (Windows/PowerShell-first -- la macchina di sviluppo è Windows 11 con Python 3.13) e documenta gli errori che incontrerai quando qualcosa non va.

Per il catalogo completo di ogni variabile d'ambiente e chiave di configurazione, vedi [Anatomia del progetto](09-project-anatomy.md). Per il primo setup, vedi [Come iniziare](07-getting-started.md). Per dipendenze e dettagli sui provider, vedi [Tech Stack](03-tech-stack.md).

## Procedura di configurazione

La pipeline legge tutta la sua configurazione al momento dell'import. **`extraction/config.py`** esegue le chiamate `os.getenv()` al caricamento del modulo, quindi i valori si congelano nel momento in cui `from extraction import *` viene eseguito in `main.py:8`. Impostare una variabile d'ambiente dopo l'avvio del processo non ha effetto. Questo conta per l'ordine dei passi qui sotto.

**Passo 1 -- Creare l'ambiente virtuale.** Su Windows, `run_edge_agent.bat` lo fa per te (preferisce Python 3.13, poi 3.12, e installa `requirements.txt` alla prima esecuzione -- `run_edge_agent.bat:50-54,67-69`; se la venv esistente ha l'interprete di base rotto, la ricostruisce da sola). Manualmente:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Il download di torch/torchvision è la parte lenta; serve solo al router ML di pagina dell'edge-agent. Se ti serve solo la CLI, basta un'installazione minimale (`langchain-core langchain-openai langchain-google-genai pillow pandas python-dotenv`).

**Passo 2 -- Creare il tuo `.env`.** Copia il template:

```powershell
Copy-Item .env.example .env
```

`main.py:7` chiama `load_dotenv()` prima di importare il package `extraction`, quindi tutto ciò che sta in `.env` è nell'ambiente prima che `extraction/config.py` lo legga. L'edge-agent carica esplicitamente la stessa `.env` di root (`edge-agent/edge_agent.py:9-13`). `.env` è in gitignore (`.gitignore` copre `.env*`) -- che rimanga così.

**Passo 3 -- Impostare l'unico valore obbligatorio.** `LLM_API_KEY` è la sola variabile che devi fornire; tutto il resto ha default funzionanti. Senza, `create_chat_model()` solleva in `extraction/llm_factory.py:41-44`:

```
API key required. Set LLM_API_KEY env var or pass api_key=.
```

Sostituisci il placeholder di `.env.example` con una chiave reale. Anche `gui_app.py` carica `.env` prima del motore, senza sovrascrivere le variabili già esportate. Il campo API key resta precompilato da `LLM_API_KEY`, con fallback `OPENAI_API_KEY`, e consente di inserire la chiave manualmente. I selettori iniziali usano provider e modello effettivi ([ADR 0021](adr/0021-dotenv-prima-del-motore-nella-gui-tkinter.md)).

**Passo 4 -- Scegliere provider e modello (opzionale).** I default in `extraction/config.py:17-18` sono `LLM_PROVIDER=openai` e `LLM_MODEL=gpt-4o`. Con una chiave OpenAI non cambi nulla. Per passare a Gemini, vedi Profili d'ambiente -- provider e modello devono muoversi insieme o la factory li rifiuta.

**Passo 5 -- Mettere i dati dove la CLI li cerca.** La CLI legge screenshot e CSV di ground truth da `INPUT_DIR`, default `mnt/data` (`extraction/config.py:8`); il percorso della ground truth ne deriva come `mnt/data/dati.csv` (`extraction/config.py:9`). **`dati.csv` non è nel repository** (`/mnt` è in gitignore; solo i 9 file `screen *.png` sono stati forzati), e la CLI fallisce duramente senza (`extraction/cli.py::main`) -- vedi Risoluzione dei problemi. Procurati il file separatamente e mettilo in `mnt/data/` prima di lanciare `python main.py`. La GUI Tkinter e l'edge-agent non ne hanno bisogno: la GUI Tkinter è l'alternativa per estrarre **senza** ground truth.

**Passo 6 -- Solo edge-agent in modalità `llm`: fornire la chiave del router.** Serve con la configurazione spedita, che usa `router = llm`. In quel caso `[llm] api_key` nel `config.ini` spedito è **vuota** per scelta, e la chiave viene raccolta dall'ambiente in base al provider -- vedi la ricetta più avanti.

### Dipendenze d'ordine che mordono

- `INPUT_DIR` va impostata **prima** dell'avvio del processo: `GROUND_TRUTH_CSV` e `DEBUG_CROP_DIR` sono calcolate da essa all'import (`extraction/config.py:9,94`). Esportarla dopo il lancio non fa nulla.
- `LLM_PROVIDER` e `LLM_MODEL` devono essere coerenti (provider OpenAI vuole un modello OpenAI e viceversa). La factory lo impone -- vedi Risoluzione dei problemi.
- L’edge-agent esegue `bootstrap.run_preflight()` prima dell’import di `ui.main_window`: prepara file e chiave, poi costruisce i ChatModel. Non anticipare l’import di `extraction` rispetto al preflight, che può creare/caricare la `.env` al primo avvio.

## Profili d'ambiente

Non ci sono profili dev/staging/prod -- nessun file di config per ambiente e nessun selettore di profilo. La configurazione è un unico insieme piatto di variabili d'ambiente più un file INI. Ciò che varia davvero tra i setup sono tre interruttori ortogonali: **quale provider LLM** esegue l'estrazione, **quale modalità di riconoscimento pagina** usa l'edge-agent, e **se l'output di debug è acceso**.

### OpenAI vs Gemini (la scelta principale)

Il provider si seleziona con `LLM_PROVIDER` e si risolve in `create_chat_model()` (`extraction/llm_factory.py:46-77`). I due profili differiscono in tre variabili.

**Profilo OpenAI (default).** Nulla oltre la chiave:

```
LLM_PROVIDER=openai
LLM_API_KEY=sk-la-tua-chiave-openai
LLM_MODEL=gpt-4o
```

Modelli OpenAI validi secondo `PROVIDER_MODELS` (`extraction/config.py:22-23`): `gpt-4o`, `gpt-4o-mini`, `o1`, `o1-mini`.

**Profilo Gemini.** Cambia provider, chiave e modello insieme:

```
LLM_PROVIDER=gemini
LLM_API_KEY=la-tua-chiave-gemini
LLM_MODEL=gemini-1.5-flash
```

Modelli Gemini validi (`extraction/config.py:24-32`): `gemini-1.5-pro`, `gemini-1.5-flash`, `gemini-2.0-flash`, `gemini-2.0-flash-exp`, `gemini-2.0-flash-thinking-exp`, `gemini-3-flash-preview`, `gemini-3.1-flash-lite-preview`. Il ramo Gemini imposta tutte e quattro le categorie di `safety_settings` a `BLOCK_NONE` (`extraction/llm_factory.py:64-71`). Anche l'output strutturato prende strade diverse per generazione di modello: `gemini-1.5*` usa json_mode con response schema, mentre 2.0+/3.x ricadono su JSON in forma libera più validazione Pydantic manuale (`extraction/vlm_client.py:15-18,134-183`).

Due manopole extra:

- `LLM_MODEL_ANCHOR` (`extraction/config.py:19`) fa usare al passaggio anchor (economico) un modello diverso dal main; default = `LLM_MODEL`.
- `LLM_THINKING_LEVEL` (`extraction/config.py:19`) -- `low`/`medium`/`high`. La decide la famiglia del modello (`extraction/model_adapters.py`, [ADR 0016](adr/0016-adapter-per-famiglia-di-modelli.md)): la famiglia Gemini 3 la riceve come `thinking_level`; se non la imposti vale il default del modello, che per Gemini 3 è `high`, il più lento e costoso. Le altre famiglie la ignorano con un avviso all'avvio; un valore diverso dai tre ammessi blocca l'avvio con un errore.

> **Servizio esterno:** entrambi i profili chiamano un'API a pagamento di terzi (OpenAI o Google) via rete. Serve una chiave valida e con credito per il provider scelto. La suite locale sostituisce il confine di rete; le esecuzioni dell’applicazione richiedono il provider reale.

### Modalità di riconoscimento pagina dell'edge-agent

L'edge-agent sceglie come riconoscere quale schermata BPER è a video tramite la chiave `router` in `[agent]` di **`edge-agent/config.ini`**, letta in `AgentConfig.router_mode` (`edge-agent/config.py:160`):

- `ml` -- prototype matching DINOv2, locale e gratuito per frame (richiede `torch`/`torchvision`). Default nel codice (`edge-agent/config.py:25`).
- `llm` -- il router usa l’SDK OpenAI con provider, endpoint e modello risolti dall’INI. È la modalità spedita; il file corrente seleziona Gemini tramite endpoint compatibile OpenAI.
- `hybrid` -- prima LLM, fallback su ML.
- `local-first` -- prova il margine del classificatore e le classi di scarto; nel cablaggio attuale ricade su `MLPageRouter`, senza escalation all’LLM. Non usarlo aspettandosi il fallback remoto progettato nell’ADR 0008: vedi [Workflow](05-workflows.md).

Le modalità `ml`/`hybrid` degradano con grazia: se l'import di torch fallisce, il classificatore entra in modalità DISABLED e non restituisce classificazioni invece di crashare (`edge-agent/page_classifier.py:50,158`).

### Profilo di debug

Tre interruttori indipendenti, nessuno legato a un "ambiente":

- `DEBUG_MODE=1` -- stampa log `[DEBUG]` di batch/pipeline (`extraction/cli.py::_debug_log`; default `0` in `extraction/config.py:92`). **Non elencata in `.env.example`** -- esiste solo nel codice.
- `DEBUG_SAVE_CROPS=1` -- scrive i crop intermedi in `mnt/data/debug_crops` (`extraction/config.py:93-94`).
- Flag `--debug` dell'edge-agent -- aggiunge il tab "Debug LLM" con prompt/risposta grezzi del router (`edge-agent/edge_agent.py:51`). La chiave `[debug] show_llm_tab=true` in `config.ini:32` abilita in aggiunta l'emissione del segnale di debug; servono entrambi per vedere il traffico del router.

## Ricette di configurazione

Ogni ricetta elenca cosa cambiare, dove, e cosa dovresti vedere. Sono inclusi solo scenari che il codice supporta.

### Usare Google Gemini invece di OpenAI

In `.env`:

```
LLM_PROVIDER=gemini
LLM_API_KEY=la-tua-chiave-gemini
LLM_MODEL=gemini-1.5-flash
```

Risultato: `create_chat_model()` costruisce una `ChatGoogleGenerativeAI` (`extraction/llm_factory.py:56-75`). Richiede `langchain-google-genai`, importato pigramente solo su questo ramo.

### Passaggio anchor più economico del main

In `.env`:

```
LLM_MODEL=gpt-4o
LLM_MODEL_ANCHOR=gpt-4o-mini
```

Risultato: l'estrazione anchor dell'intestazione usa il modello economico mentre il passaggio main sull'intero contenuto usa `gpt-4o`. Entrambi i nomi fluiscono in `BatchRunner` (`extraction/cli.py::BatchRunner.__init__`), che crea due istanze ChatModel condivise separate (`extraction/cli.py::BatchRunner.__init__`).

### Puntare la pipeline a un'altra cartella dati

In `.env`:

```
INPUT_DIR=C:\data\bper_screens
```

Risultato: la CLI elenca `*.png`/`*.jpg`/`*.jpeg` da quella directory (`extraction/cli.py::main`), si aspetta `dati.csv` al suo interno (`extraction/config.py:9`) e vi scrive `poc_outputs_improved.json` / `poc_debug_improved.csv` (`extraction/cli.py::main`). Da impostare prima del lancio.

### Modificare i prompt o puntare a un catalogo alternativo

I prompt non stanno più nel codice: vivono in `prompts/`, un file JSON per prompt, letti e validati una volta all'avvio da `prompt_store.py`. Per cambiare cosa viene chiesto al modello si edita il JSON e si riavvia; non serve toccare Python né ricompilare. Nel pacchetto portable vale la copia accanto all'exe, che ha la precedenza su quella inclusa nel bundle.

Per lavorare su un catalogo separato (A/B di prompt, prove locali), in `.env`:

```
PROMPTS_DIR=C:\lavoro\prompt_alternativi
```

Risultato: quella directory diventa l'**unico** candidato (`prompt_store.py:222`), senza fallback sul catalogo del repo o del bundle: se è incompleta o malformata l'avvio fallisce, di proposito. La directory effettivamente caricata viene stampata come `[PROMPTS] catalog loaded from ...` dalla CLI e da `LocalExtractionClient`.

Due vincoli quando si edita un JSON: le graffe sono significative solo nei prompt che il codice formatta (`extraction_json_schema_instruction`, `extraction_anchor_hints`, `page_router_system`, `page_router_user`) e vanno raddoppiate (`{{`) se servono letterali; aggiungere un nuovo `{placeholder}` richiede anche una riga in `CATALOG` dentro `prompt_store.py`.

### Abilitare log di debug e salvataggio dei crop

In `.env`:

```
DEBUG_MODE=1
DEBUG_SAVE_CROPS=1
```

Risultato: la console mostra righe `[DEBUG]` per batch e avanzamento per schermata, e ogni crop intermedio finisce in `INPUT_DIR/debug_crops` (nomi tipo `screen 1__CONTENT.png`, `screen 1__HEADER_IN_CONTENT.png`, `screen 1__RETRY_HEADER.png`). Al termine la CLI stampa `Saved debug crops to: ...` (`extraction/cli.py::main`).

### Regolare il parallelismo

In `.env`:

```
PARALLEL_WORKERS=8
PARALLEL_ENABLED=1
```

Risultato: il batch runner usa un `ThreadPoolExecutor` a 8 thread quando c'è più di una schermata (`extraction/cli.py::BatchRunner.run`). Default: `4` e `1` (`extraction/config.py:11-12`) -- il default nel codice e quello in `.env.example` oggi coincidono. Imposta `PARALLEL_ENABLED=0` per forzare l'elaborazione sequenziale -- utile per leggere l'output per schermata o isolare un guasto.

### Far fermare una schermata sull'incertezza degli anchor

In `.env`:

```
STOP_ON_ANCHOR_UNCERTAIN=1
ANCHOR_CONF_MIN=0.95
```

Risultato: quando entrambi gli anchor sono nulli dopo l’applicazione di `ANCHOR_CONF_MIN`, la pipeline ritorna `_status="ANCHOR_UNCERTAIN"` e salta main e retry. Il gate azzera effettivamente i valori a bassa confidenza (`extraction/pipeline.py`). Nell’edge-agent questo stato completa la visita senza innescare un ciclo infinito di tentativi automatici.

### Limitare il costo per schermata

In `.env`:

```
MAX_CALLS_PER_SCREEN=5
```

Risultato: limita i passaggi logici di retry, non le richieste effettive al provider. La pipeline riserva anchor e main e assegna al retry `max(0, MAX_CALLS_PER_SCREEN - 2)` aree. Con 2 o meno restano i due passaggi iniziali, salvo uscita anticipata sugli anchor. Ogni passaggio può ritentare errori transitori dentro `call_vlm_with_retry()`, quindi il valore non è un tetto di rete o di spesa.

Il default è **derivato**, non un letterale: `2 + len(AREA_TO_FIELDS)` = `5` (`extraction/config.py:102-103`). Abbassarlo non riduce il costo in modo uniforme: taglia le aree in **coda** all'ordine di dichiarazione di `AREA_TO_FIELDS`, che è HEADER, BODY, FOOTER. Con `4` le aree ritentabili diventano due e `FOOTER` non viene mai riletta; siccome `FOOTER` possiede `note_della_richiesta`, su una pagina di note si perde esattamente il campo per cui quella pagina viene acquisita. Il perché in [ADR 0004](adr/0004-budget-retry-derivato-dalle-aree.md).

### Passare l'edge-agent al riconoscimento pagina ML

In `edge-agent/config.ini`, sezione `[agent]`:

```ini
router = ml
```

Risultato: il prototype matching DINOv2 sostituisce la chiamata VLM per frame -- nessuna chiave né costo per il router. È l'impostazione in vigore, sia come default nel codice sia nel `config.ini` spedito ([ADR 0005](adr/0005-router-ml-invece-di-router-llm.md)). Richiede `torch`/`torchvision`; se non disponibili il classificatore risulta DISABLED e non matcha mai.

Il confronto avviene sulla ROI dell'area applicativa `DEFAULT_CROP_ROI = (0.0, 0.20, 1.0, 0.98)` (`edge-agent/page_classifier.py:44`), schiacciata a 224x224, con **coseno centrato** e soglia `0.35` (`:51`). Tre valori che non vanno toccati alla leggera: sono l'esito di una misura, e la configurazione precedente riconosceva 1 pagina su 9 in esercizio ([ADR 0002](adr/0002-riconoscimento-pagina-roi-e-coseno-centrato.md)). Cambiandone uno, la cache dei prototipi si invalida da sé perché `embedding_geometry()` fa parte della sua chiave ([ADR 0003](adr/0003-chiave-cache-prototipi-con-geometria.md)): il primo avvio successivo ricostruisce i 9 prototipi.

### Configurare quale monitor cattura l'edge-agent

In `edge-agent/config.ini`, sezione `[agent]`:

```ini
monitor_index = 2
```

Risultato: `mss` cattura il monitor 2 (indicizzazione a partire da 1). Letto in `edge-agent/config.py:163-167` (valori sotto 1 ricadono sul default); indici fuori intervallo ricadono sul monitor 1 nel loop di cattura (`edge-agent/workers/capture/bper_capture_worker.py:554,569`). Un overlay a bordo rosso marca il monitor catturato quando `show_capture_border = true` (`config.ini:6`).

### Fornire la API key del router dell'edge-agent

Serve solo con `router = llm` o `hybrid`. La risoluzione avviene in `AgentConfig.resolve_llm_settings()` (`edge-agent/config.py`) ed è **consapevole del provider**: i valori espliciti in `config.ini [llm]` sono autorevoli, i default del provider riempiono soltanto le voci lasciate vuote.

Precedenza della chiave:

| provider | ordine |
|---|---|
| qualsiasi | `config.ini [llm] api_key` se non vuota |
| `gemini` | poi `GEMINI_API_KEY` → `GOOGLE_API_KEY` → `LLM_API_KEY` |
| `openai` | poi `OPENAI_API_KEY` → `LLM_API_KEY` |

Il `config.ini` spedito usa `provider = gemini`, `model = gemini-3.8-flash` e l'endpoint OpenAI-compatibile di Google, con `api_key` **vuota**: la chiave arriva dall'ambiente. Lasciala vuota. L'INI è tracciato in git, quindi qualunque chiave incollata lì è a un commit di distanza dalla fuga, e `build_exe.bat` si rifiuta di impacchettare un `config.ini` con `api_key` non vuota.

> **Nota di sicurezza:** una chiave OpenAI era stata committata in `edge-agent/config.ini` ed è stata rimossa dall'intera cronologia git il 2026-07-21 (riscrittura con filter-repo + force-push). La riga ora è vuota. `AgentConfig` tratta inoltre qualunque valore che inizi per `REDACTED` come vuoto: un placeholder rimasto in giro aveva già oscurato le chiavi da ambiente rompendo il router in silenzio. La rotazione della chiave esposta è da confermare. Chi ha clonato il repo **prima del 2026-07-21** deve ri-clonare (la cronologia è stata riscritta). Ricorda anche che `AgentConfig.save()` ri-persisterebbe nella copia tracciata qualunque chiave in memoria (`edge-agent/config.py:326-332`) -- oggi non ha chiamanti, ma non committare mai una chiave reale in questo file.

## Operazioni comuni

Non ci sono database, migrazioni, cache né server long-running -- molte operazioni "standard" semplicemente non si applicano. Eseguili dalla root del progetto con la venv attiva (`.venv\Scripts\Activate.ps1`).

### Eseguire l'estrazione batch da CLI

```powershell
python main.py
```

Cosa fa (`extraction/cli.py::main`): verifica che `mnt/data/dati.csv` esista, elenca ogni immagine in `INPUT_DIR`, esegue l'estrazione multi-passaggio (in parallelo con più di un'immagine), valuta rispetto alla ground truth e scrive i risultati. Output atteso, grosso modo in ordine:

- `Parallel enabled: workers=4, screens=9` (`extraction/cli.py::BatchRunner.run`)
- `Done screen 1` ... per ogni schermata completata (`extraction/cli.py::BatchRunner.run`)
- Tabelle di accuratezza RAW e FILTERED da `evaluator.eval()` (`extraction/cli.py::main`)
- Un riepilogo token/costi per schermata da `print_cost_summary()` (`extraction/cli.py::main`)
- `Saved outputs: mnt/data\poc_outputs_improved.json` e `Saved debug report: mnt/data\poc_debug_improved.csv` (`extraction/cli.py::main`)

### Avviare la GUI desktop Tkinter

```powershell
python gui_app.py
```

Apre una finestra nativa con campo API key, dropdown provider/modello e selettori di file/CSV. Il CSV di ground truth qui è opzionale (`gui_app.py:263`), quindi questa è la via per estrarre screenshot estemporanei senza `dati.csv`. Gli output vengono scritti nella **directory di lavoro corrente**: `poc_outputs_gui.json`, `poc_results_gui.csv` e (se è stato selezionato un CSV di GT) `poc_debug_gui.csv` (`gui_app.py:250-256,273-274`).

### Dimensioni delle immagini e soglia dei retry

`MAX_IMAGE_LONG_SIDE=2000` limita il lato lungo delle immagini all’ingresso della pipeline senza ingrandire quelle più piccole. `RETRY_CONF_MIN=0.60` seleziona le aree con campi sotto soglia; i valori nulli richiedono comunque un retry se il budget lo consente. Entrambe sono lette all’import (`extraction/config.py`).

### Avviare l’edge-agent (cattura live)

```powershell
.\run_edge_agent.bat            # raccomandato su Windows: crea/ripara la .venv, poi avvia
# equivalenti una volta che esiste una venv:
python edge-agent/edge_agent.py
python main.py --gui
```

`run_edge_agent.bat` sonda la `.venv` esistente, la ricostruisce se il suo interprete di base è sparito (`run_edge_agent.bat:23-29`) e inoltra qualsiasi argomento. Aggiungi `--debug` per il tab Debug LLM:

```powershell
.\run_edge_agent.bat --debug
```

Nell’app: scegli BPER in Cattura, premi «Avvia» e naviga sul monitor selezionato. I frame stabili vengono accodati; l’estrazione usa thread separati e invia le immagini al provider. Dati Estratti mostra una riga per pratica e consente l’export Excel. «Acquisisci ora» accoda uno scatto della pagina scelta nel thread di cattura: non interrompe un routing già in corso. Un errore consente un nuovo tentativo; una visita completata non viene ripetuta finché il frame resta identico. I contatori «Inviate» ed «Elaborate» misurano fasi diverse; `get_results()` attende i risultati precedenti prima di rendere visibili quelli successivi ([API Python](12-python-api.md), ADR [0013](adr/0013-risultati-nell-ordine-di-acquisizione.md), [0014](adr/0014-acquisizione-per-visita-con-esito.md), [0015](adr/0015-scatto-manuale-nel-thread-di-cattura.md)).

### Creare il portable Windows dell’edge-agent

```powershell
.\build_exe.bat
```

Usa `edge_agent.spec` e produce `dist/EdgeAgent` più uno ZIP datato. Il pacchetto contiene configurazione, prompt e asset; l’avvio esegue il preflight prima di importare la UI. La chiave va nella `.env` locale: la build rifiuta un `config.ini` con `api_key` valorizzata. Per consegnare un pacchetto che non chiede nulla al tester, la build può precompilare la chiave nel `.env` del pacchetto (richiesta all'avvio della build, oppure `EDGE_AGENT_PACKAGE_KEY`); lo zip prende il suffisso `_CON-CHIAVE`. Vedi [Come iniziare](07-getting-started.md) per la consegna del pacchetto.

### Controllare risultati e log

La CLI stampa su stdout. Nel portable senza console, `edge-agent/edge_agent.py` reindirizza stdout/stderr su `edge-agent.log`; `_log_extraction()` conserva stato, confidenza, costi e provenienza, mentre la UI mostra i dati di business. Dopo un’esecuzione CLI, ispeziona:

- `mnt/data/poc_outputs_improved.json` -- risultati completi per schermata, inclusi `_meta_agg` (chiamate, token, `estimated_cost_usd`) e `_field_sources`.
- `mnt/data/poc_debug_improved.csv` -- classificazione per (schermata, campo); separato da `;`, `utf-8-sig` (si apre pulito in Excel).

La suite locale si esegue con `python -m pytest tests` dopo `pip install -r requirements-dev.txt`. Non esistono migrazioni database, seeding o comandi di avvio di un server.

## Risoluzione dei problemi

Ogni sintomo qui sotto è ancorato a una stringa d'errore o a un comportamento reale del codebase.

### CSV di ground truth non trovato

**Sintomo:**

```
FileNotFoundError: Ground truth CSV not found: mnt/data\dati.csv
```

**Causa:** `python main.py` controlla la presenza di `dati.csv` in `INPUT_DIR` prima di ogni altra cosa (`extraction/cli.py::main`). Il file è assente dal repository (`/mnt` è in gitignore; solo i PNG sono tracciati), quindi questo fallimento è garantito su un clone fresco.

**Soluzione:** procurati `dati.csv` e mettilo in `mnt/data/` (formato in `README.md:221-241`: colonne `Fotogramma`, `Denominazione da attribuire`, `Valore rilevato`). Per estrarre senza ground truth, usa `python gui_app.py` -- lì il CSV è opzionale (`gui_app.py:263`). Dove risieda il `dati.csv` canonico è una questione aperta -- vedi [Domande aperte](08-open-questions.md).

### API key mancante o non valida

**Sintomo (avvio CLI/Tkinter/edge-agent):**

```
ValueError: API key required. Set LLM_API_KEY env var or pass api_key=.
```

**Causa:** né `LLM_API_KEY` né una legacy `OPENAI_API_KEY`/`GEMINI_API_KEY` è impostata (`extraction/llm_factory.py:30-44`). Le variabili legacy funzionano ma emettono un `DeprecationWarning`. Nell'edge-agent questo si manifesta come crash all'avvio, perché `LocalExtractionClient` costruisce entrambi i ChatModel nel costruttore di `MainWindow` (`edge-agent/ui/main_window.py:37`, `edge-agent/local_extraction_client.py:47-48`).

**Soluzione:** imposta `LLM_API_KEY` nella `.env` di root, oppure incolla la chiave nel campo della GUI Tkinter (la GUI si blocca con la finestra `Inserisci la API Key!` se lasciato vuoto, `gui_app.py:214-215`).

### Discrepanza provider / modello

**Sintomo:** uno tra (`extraction/llm_factory.py:49-53,59-63,77`):

```
ValueError: Model 'gemini-1.5-flash' looks like a Gemini model but provider is 'openai'. Set LLM_PROVIDER=gemini or choose an OpenAI model.
ValueError: Model 'gpt-4o' looks like an OpenAI model but provider is 'gemini'. Set LLM_MODEL to a Gemini model (e.g. 'gemini-1.5-flash').
ValueError: Unknown provider: 'azure'. Available: ['openai', 'gemini']
```

**Causa:** `LLM_PROVIDER` e `LLM_MODEL` non concordano, o il provider non è `openai`/`gemini`.

**Soluzione:** cambiali insieme, scegliendo da `PROVIDER_MODELS` (`extraction/config.py:22-33`).

### Catalogo dei prompt non caricabile

**Sintomo:** all'avvio, prima di qualsiasi chiamata al modello (`prompt_store.py`):

```
prompt_store.PromptStoreError: no usable prompt catalog (set PROMPTS_DIR to point at a valid one):
  cannot read ...\prompts\extraction_main.json: Expecting ',' delimiter: line 8 column 5
prompt_store.PromptStoreError: prompt 'page_router_system': unknown placeholder(s) ['"page_type"']; ...
prompt_store.PromptStoreError: ... is missing prompt(s): extraction_anchor
```

**Causa:** un JSON del catalogo è malformato, manca, oppure contiene una graffa non prevista in un prompt che il codice formatta. Il fallimento è voluto e immediato: un prompt corrotto non blocca la pipeline, la fa produrre campi sbagliati che sembrano giusti.

**Soluzione:** correggi il file indicato nel messaggio (raddoppia le graffe letterali, `{{`); dichiara ogni nuovo `{placeholder}` in `CATALOG` dentro `prompt_store.py`. Da sorgente, `git checkout prompts/` ripristina il catalogo. Nel pacchetto portable basta cancellare la cartella `prompts/` accanto all'exe: il loader usa la copia dentro il bundle e il bootstrap la risemina al riavvio successivo.

### Risposta del modello non parsabile

**Sintomo:** uno tra (`extraction/vlm_client.py:39,44,95-98,199-203`):

```
ValueError: No JSON object found in model response: ...
ValueError: JSON decode error in model response: ...
ValueError: Pydantic validation failed for screen 1/CONTENT_MAIN: ...
ValueError: Structured output parsing failed for screen 1/CONTENT_MAIN: ...
```

**Causa:** il VLM ha restituito output che non corrisponde allo schema Pydantic. Questi errori **non vengono ritentati** per scelta -- `call_vlm_with_retry()` rilancia `ValueError` immediatamente (`extraction/vlm_client.py:252-253`). I guasti API transitori (rate limit, timeout) sono diversi: quelli si ritentano fino a 3 volte con backoff esponenziale con tetto (`extraction/vlm_client.py:254-257`).

**Soluzione:** di solito il modello scelto è troppo debole per l'estrazione visiva strutturata. Passa a uno più forte (`gpt-4o`, `gemini-1.5-pro`). Nota che il fallimento di un solo retry non è fatale -- la pipeline conserva i risultati del main e stampa `Warning: retry {AREA} for {screen} failed (keeping main-pass results)` (`extraction/pipeline.py:291`).

### Colonna del CSV non riconosciuta

**Sintomo:**

```
ValueError: Cannot find Screenshot column in CSV. Columns=[...]
```

**Causa:** `load_ground_truth()` non ha trovato una colonna richiesta sotto i suoi alias noti (`extraction/evaluation.py:31`). Riconosciuti: `Fotogramma`/`Screenshot`/`Screen`, `Denominazione da attribuire`/`Campo`/`Field`, `Valore rilevato`/`Valore`/`Value`.

**Soluzione:** rinomina le intestazioni del CSV con uno dei nomi riconosciuti.

### Edge-agent: la cattura dello schermo fallisce

**Sintomo:** nel log di Cattura, uno tra (`edge-agent/workers/capture/bper_capture_worker.py:562,594-596`):

```
mss non disponibile: ...
Cattura fallita 5 volte consecutive. Ultimo errore: ...
```

**Causa:** la libreria `mss` non si è inizializzata, oppure 5 errori di cattura consecutivi hanno fatto scattare l'auto-stop (`_MAX_CONSECUTIVE_CAPTURE_ERRORS = 5`, `bper_capture_worker.py:98`) -- spesso un `monitor_index` sbagliato.

**Soluzione:** conferma che `mss` sia installato (`pip install -r requirements.txt`); controlla `monitor_index` in `edge-agent/config.ini:5` (a partire da 1; gli indici fuori intervallo ricadono sul monitor 1).

### Edge-agent: le pagine non vengono mai riconosciute (router LLM)

**Sintomo:** la cattura gira, l'overlay del bordo compare, ma nessuna pagina viene rilevata e nessuna estrazione parte. Con `--debug`, il tab Debug LLM mostra (`edge-agent/llm_router.py:148`):

```
LLM client non inizializzato (manca API key o import OpenAI fallito)
```

**Causa:** il router non ha una chiave utilizzabile per il provider configurato. Restituisce un risultato senza pagina; quando contiene una motivazione, il worker la mostra nel log di Cattura come errore di riconoscimento.

**Soluzione:** lascia vuota la riga `api_key` in `config.ini` e imposta la chiave nella `.env` di root, con il nome che il provider si aspetta: con `provider = gemini` va bene `GEMINI_API_KEY`, `GOOGLE_API_KEY` o `LLM_API_KEY`; con `provider = openai`, `OPENAI_API_KEY` o `LLM_API_KEY`. Il ripiego su ambiente scatta solo quando il valore INI è vuoto, e un valore che inizi per `REDACTED` conta come vuoto. La riga di log all'avvio `[BPER-LLM] Router LLM inizializzato (provider=..., model=..., pages=..., api_key=yes|no)` ti dice se una chiave è stata trovata -- ma non se è valida.

Prima di indagare la chiave, verifica di avere davvero bisogno del router LLM: la configurazione spedita è `router = llm`, quindi la chiave serve davvero.

### Edge-agent: il riconoscimento ML non fa nulla in silenzio

**Sintomo:** con `router = ml` o `hybrid`, le pagine non vengono mai riconosciute; il log mostra `[BPER-ML] import_error: ...` (`bper_capture_worker.py:200-201`).

**Causa:** `torch`/`torchvision` non si sono importati, quindi `BPERPagePrototypeClassifier` gira in modalità DISABLED e non restituisce classificazioni (`edge-agent/page_classifier.py:50,158`). Un errore correlato, `FileNotFoundError: templates_dir non trovato: ...` (`edge-agent/page_classifier.py:143`), significa che `edge-agent/assets/templates/bper/` manca.

**Soluzione:** installa torch/torchvision (Python 3.13 o 3.12, preferiti dal launcher; verificare la compatibilità dell’ambiente installato), oppure passa a `router = llm`.

### Edge-agent: la pagina viene riconosciuta sempre con lo stesso nome sbagliato

**Sintomo:** il router riconosce una pagina a ogni frame, con punteggio plausibile ma sempre lo stesso nome, indipendentemente da cosa c'è a schermo. Il log può ripetere un riconoscimento sbagliato:

```
[Router] Riconosciuta: «Note da Richiesta» (score=0.848)
```

e la schermata indicata è proprio quella che l'operatore ha davanti. Un nome pagina errato può confondere la guida e i metadati del frame.

**Causa:** disallineamento di inquadratura fra i prototipi e il frame. I prototipi sono screenshot di **finestra**; se il frame che arriva al classificatore è un monitor intero, le ROI relative cadono su contenuto diverso e la scelta fra le 9 pagine diventa arbitraria. Il nome in `captured_page_types` oggi serve soltanto alla guida: non blocca altre visite della stessa pagina. La normalizzazione resta necessaria per classificare correttamente.

**Come confermarlo:** confronta i valori estratti con le schermate di riferimento in `mnt/data`. Se corrispondono a una pagina **diversa** da quella nel log, l'estrazione sta funzionando e il problema è il routing.

**Soluzione:** verificare che la normalizzazione dell'inquadratura stia agendo. `_grab_raw()` riporta il frame sulla finestra applicativa (`edge-agent/frame_normalize.py`), prima via titolo della finestra usando `window_title_contains` in `config.ini`, poi dedotta dallo sfondo del desktop. Se il titolo della finestra non contiene la sottostringa configurata **e** il desktop attorno alla finestra non è uniforme (altre finestre visibili agli angoli), entrambe le strategie rinunciano e il frame passa a schermo intero: allinea `window_title_contains` al titolo reale della finestra. Contesto completo in [ADR 0001](adr/0001-normalizzazione-inquadratura-frame.md).

### Launcher: nessun Python adatto / venv rotta

**Sintomo:** `run_edge_agent.bat` stampa uno tra:

```
[edge-agent] ERROR: no suitable Python found (need 3.12 or 3.13).
[edge-agent] ERROR: dependency installation failed.
```

**Causa:** nessun `py -3.13`/`py -3.12`/`python` sul PATH (`run_edge_agent.bat:50-58`), oppure `pip install -r requirements.txt` è fallito nella venv fresca (`run_edge_agent.bat:69-74`).

**Soluzione:** installa Python 3.13 da python.org, poi elimina `.venv` e rilancia il launcher. Una venv il cui interprete di base è stato spostato/disinstallato viene rilevata e ricostruita automaticamente (`run_edge_agent.bat:23-29`).

### Errore di estrazione su una singola schermata in un batch

**Sintomo:** `ERROR extracting screen 3: <messaggio>` nell'output CLI, o `Warning: File not found <path>` all'inizio del batch.

**Causa:** un singolo screenshot ha sollevato durante l'estrazione; il runner parallelo lo cattura per schermata e continua (`extraction/cli.py::BatchRunner.run`). Il warning di file mancante significa che un percorso elencato non esiste (`extraction/cli.py::BatchRunner.run`).

**Soluzione:** leggi il messaggio sottostante (immagine corrotta, retry API esauriti). Il batch si completa e riporta sulle schermate riuscite. Nell'edge-agent la stessa situazione produce un risultato memorizzato con `_status: "ERROR"` (`edge-agent/local_extraction_client.py:87-92`).

### Porta già in uso

Non può accadere da questo progetto -- non apre **nessuna** porta. Le voci `http://localhost:8081` (`edge-agent/config.ini:10`) e MinIO `:9000` (`config.ini:13`) appartengono al percorso remoto legacy che il flusso BPER-local non tocca mai. Qualsiasi conflitto di porta è di un altro processo.

### Dipendenze mancanti / versioni discordanti

`requirements.txt` usa vincoli laschi e non c'è lockfile; `pyproject.toml` contiene soltanto la configurazione dei marker pytest, non dipendenze o metadati di build. Se un import fallisce, reinstalla nella venv. Occhio agli import pigri: `langchain-google-genai` si carica solo con `LLM_PROVIDER=gemini` (`extraction/llm_factory.py:57`), quindi un pacchetto Gemini mancante emerge solo quando cambi provider; `qt-material` è opzionale e la sua assenza fa solo perdere il tema (`edge-agent/edge_agent.py:37-44`).

## Riferimento rapido

| Attività | Comando | Note |
|---|---|---|
| Bootstrap su Windows | `.\run_edge_agent.bat` | Crea/ripara la `.venv`, installa le dipendenze, avvia l'edge-agent |
| Installare le dipendenze a mano | `pip install -r requirements.txt` | torch serve solo per router `ml`/`hybrid` |
| Creare la configurazione | `Copy-Item .env.example .env` | Poi imposta `LLM_API_KEY` |
| Eseguire il batch CLI | `python main.py` | Richiede `mnt/data/dati.csv`; scrive JSON + CSV di debug |
| Avviare la GUI Tkinter | `python gui_app.py` | CSV di GT opzionale; chiave incollabile in-app; output nella CWD |
| Avviare l'edge-agent | `python edge-agent/edge_agent.py` | Equivalente a `python main.py --gui` |
| Edge-agent + tab di debug | `.\run_edge_agent.bat --debug` | Richiede anche `show_llm_tab = true` in `config.ini:32` |
| Usare Gemini | `LLM_PROVIDER=gemini` + `LLM_MODEL=gemini-1.5-flash` | Provider e modello devono concordare |
| Anchor più economico | `LLM_MODEL_ANCHOR=gpt-4o-mini` | Default = `LLM_MODEL` |
| Cambiare directory dati | `INPUT_DIR=...` | Prima del lancio; `dati.csv` deve stare al suo interno |
| Modificare un prompt | edita `prompts/<id>.json` | Nessun rebuild; nuovi `{placeholder}` vanno dichiarati in `CATALOG` |
| Catalogo prompt alternativo | `PROMPTS_DIR=...` | Diventa l'unico candidato: nessun fallback, fallisce chiuso |
| Log / crop di debug | `DEBUG_MODE=1` / `DEBUG_SAVE_CROPS=1` | I crop finiscono in `INPUT_DIR/debug_crops` |
| Esecuzione sequenziale | `PARALLEL_ENABLED=0` | Output più leggibile / guasti isolabili |
| Limitare i passaggi di retry | `MAX_CALLS_PER_SCREEN=N` | Massimo `N - 2` aree; non è un tetto di rete o spesa |
| Monitor / router dell'edge-agent | modifica `monitor_index` / `router` in `edge-agent/config.ini` | A partire da 1; `ml` \| `llm` \| `hybrid` \| `local-first` |
| Creare il portable | `.\build_exe.bat` | Cartella `dist/EdgeAgent` e ZIP datato |
| Eseguire i test | `python -m pytest tests` | Prima installare `requirements-dev.txt` |

---

Riferimenti incrociati: [Anatomia del progetto](09-project-anatomy.md) per il catalogo completo di variabili d'ambiente e file di configurazione. [Come iniziare](07-getting-started.md) per il primo setup. [Tech Stack](03-tech-stack.md) per dipendenze e vincoli di versione.
