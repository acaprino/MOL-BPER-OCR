# Funzionalità

Il progetto fa una cosa sola al suo cuore (trasformare uno screenshot bancario BPER in dati strutturati e valutati) e la avvolge in tre interfacce più un layer di intelligenza per la cattura dal vivo. Le funzionalità sono raggruppate qui per ciò che fanno per te, non per directory. Ognuna indica il proprio entry point nel codice. Per le tracce end-to-end vedi [Workflow](05-workflows.md); per le forme dei dati vedi [Data Model](06-data-model.md); per le definizioni in parole semplici dei termini bancari italiani (`ndg`, `fido`, `soggetti`, …) vedi il [Glossario](11-glossary.md).

## Motore di estrazione

Tutto il resto esiste per alimentare questo motore o per riferire sui suoi risultati. Vive interamente nel pacchetto senza UI **`extraction/`**.

### Lettura multi-pass degli screenshot

Consegni al motore un'immagine e ricevi un record con ogni campo che è riuscito a leggere. Lavora in tre passaggi anziché uno, perché un singolo prompt che copre 45 campi su una schermata bancaria densa legge peggio di più prompt mirati. L'orchestrazione è `ExtractionPipeline.extract_from_image()` / `extract_from_screen()` in **`extraction/pipeline.py`**:

- **Passaggio anchor** (`extract_anchors()`) ritaglia la striscia di intestazione (`HEADER_IN_CONTENT` in `extraction/config.py`) ed estrae solo `ndg` e `denominazione` contro lo schema minimale `AnchorResponse`. I valori sotto `ANCHOR_CONF_MIN` (0.95) *dovrebbero* essere azzerati, ma il gate è attualmente inefficace (vedi il riquadro qui sotto); con `STOP_ON_ANCHOR_UNCERTAIN=1` la pipeline esce in anticipo quando il modello restituisce entrambi gli anchor nulli.
- **Passaggio principale** invia il ritaglio completo del contenuto (`CONTENT_CROP`) con i suggerimenti degli anchor ("NDG atteso: …") ed estrae tutti i campi scalari più le tabelle `soggetti` / `fidi` / `garanzie` in un'unica chiamata.
- **Passaggio di retry** individua le aree (HEADER / BODY / FOOTER, mappate in `AREA_TO_FIELDS`) che contengono campi nulli o con confidenza sotto 0.60 e rilegge ciascuna con un ritaglio dedicato da `RETRY_AREAS`, contrasto e nitidezza extra e un prompt specifico per area. I retry girano in un thread pool annidato, con tetto a `MAX_CALLS_PER_SCREEN - 2`. Per ogni campo, `pick_best()` in **`extraction/normalization.py`** decide il vincitore (il non-nullo batte il nullo; a parità vince la confidenza più alta); le tabelle si fondono per numero di righe e poi per confidenza in `_merge_tables()`.

> ⚠ **Incoerenza nota**: il gate di confidenza degli anchor non filtra davvero nulla. I dict `ndg`/`denominazione` che alimentano il prompt dei suggerimenti, l'uscita anticipata e il merge vengono copiati *prima* che il gate venga eseguito, e `safe_set_field(..., None)` non può sovrascrivere un valore non nullo (`extraction/pipeline.py:87-96` vs `extraction/normalization.py:78-79`). Il "zeroes out low-confidence anchors" di `CLAUDE.md` descrive l'intenzione, non il comportamento. Analisi completa in [Workflow](05-workflows.md); tracciata in [Domande Aperte](08-open-questions.md).

I due metodi di ingresso differiscono per scelta progettuale: `extract_from_screen(path)` (CLI, GUI Tkinter) prima normalizza l'immagine; `extract_from_image(img, screen_id)` (edge-agent) salta `normalize_image()` perché il frame è già stato pre-elaborato a monte.

I prompt vivono in **`prompts/*.json`** (un file per prompt) e vengono caricati una sola volta all'avvio da `prompt_store.py` (nella root, fuori da `extraction/`, così leggere un prompt non tira dentro LangChain); `extraction/prompts.py` si limita a esporre le costanti storiche (`PROMPT`, `ANCHOR_PROMPT`, `FIELD_RETRY_PROMPTS`) lette dal catalogo. Sono scritti in italiano di proposito: le schermate, le etichette e i termini bancari sono italiani, e le chiavi di campo (`professione_principale`, `filiale_relazione`, …) sono vocabolario di dominio portante che non va tradotto.

### Backend LLM indipendente dal provider

Una sola variabile d'ambiente (`LLM_PROVIDER`) commuta tra OpenAI (default, `gpt-4o`) e Google Gemini; nient'altro cambia. La factory unica è `create_chat_model()` in **`extraction/llm_factory.py`**: importa in modo lazy il pacchetto del provider giusto, applica le safety settings di Gemini, onora `LLM_THINKING_LEVEL` solo per i modelli con "thinking" nel nome e rifiuta le combinazioni provider/modello incoerenti con un errore chiaro. Le chiamate passano per `call_vlm()` / `call_vlm_with_retry()` in **`extraction/vlm_client.py`**; i retry coprono solo gli errori transitori, mentre i fallimenti di parsing (`ValueError`) vengono risollevati subito. L'unica eccezione deliberata alla factory: `LLMPageRouter` nell'edge-agent usa l'SDK `openai` grezzo, solo per il routing delle pagine. Vedi [Architettura](04-architecture.md) per il perché questa cucitura conta.

### Output strutturato e validato da schema

Al modello non viene mai chiesto testo libero. Ogni chiamata è legata a uno schema Pydantic tramite `.with_structured_output()` di LangChain, così una risposta o si parsea nella forma attesa o fallisce rumorosamente. Gli schemi sono in **`extraction/schemas.py`**: `FieldResult` (valore + confidenza + evidenza + sezione), `Soggetto`, `Fido`, `Garanzia` e i top-level `ExtractionResponse` / `AnchorResponse`. Il modello per-campo è generato dinamicamente con `create_model()` a partire da `FIELD_KEYS` in **`extraction/fields.py`**, quindi lo schema e l'elenco dei campi non possono divergere. Le stranezze dei provider sono gestite in `vlm_client.py`: Gemini 1.5 usa json_mode, Gemini 2.0+/3.x riceve lo schema iniettato nel prompt con validazione Pydantic manuale.

### Confidenza e provenienza per campo

Ogni campo registra quale passaggio ha prodotto il suo valore finale (`ANCHOR_HEADER`, `CONTENT_MAIN` o `RETRY_{HEADER|BODY|FOOTER}`) nella mappa `_field_sources` costruita in `extraction/pipeline.py`, esposta come colonna `source_attempt` del report di debug. Un'eccezione: l'appiattimento dei soggetti sovrascrive le dodici chiavi `ndg_1..4`/`denominazione_1..4`/`ruolo_1..4` senza aggiornarne la sorgente, quindi la provenienza di quelle chiavi può risultare obsoleta (vedi [Data Model](06-data-model.md)). È così che capisci non solo *cosa* è stato estratto ma *come*, ed è ciò su cui si basa la logica di retry.

### Regole di coerenza di dominio e normalizzazione

Dopo il merge, regole bancarie cablate riparano l'output (`_coherence_check()` in `extraction/pipeline.py`): un `tooltip_evidenze_b` presente forza `evidenze` a "B", un `tooltip_descrizione_bmb` presente forza `tipo` a "BMB", e `normalize_tipo()` collassa i sinonimi del tipo. La normalizzazione al momento del confronto (uguaglianza numerica, parsing delle date, fuzzy matching per il testo libero lungo) vive in **`extraction/normalization.py`**, così le differenze di pura formattazione non contano come errori.

### Mappatura canonica di campi e pagine

Un layer di denominazione rivolto al cliente mappa ogni chiave di schema a un nome visualizzato e a una delle quattro chiavi di pagina canoniche (`risultato_ricerca`, `elenco_soggetti`, `gestione_fidi_e_garanzie`, `note_da_richiesta`). I pezzi sono **`extraction/field_definitions.py`**, **`extraction/page_definitions.py`** e `build_canonical_field_entries()` in **`extraction/canonical_mapping.py`**; ogni result dict porta la lista ordinata `canonical_fields`. I consumatori oggi: l'esportazione CSV, l'albero dei risultati Tkinter e la tabella Dati Estratti dell'edge-agent (`edge-agent/ui/data_table_tab.py`). Questo layer è recente (commit `e9f22a1`, `5709f66`) e il suo consumatore esterno non è nominato nel repo: vedi [Domande Aperte](08-open-questions.md).

## Valutazione di accuratezza e costi

Leggere le schermate è metà del punto; il progetto esiste per misurare quanto bene legge e quanto costa farlo.

### Valutazione su ground truth

Ogni campo estratto viene confrontato con il valore atteso di `mnt/data/dati.csv` (formato lungo: `Fotogramma` / `Denominazione da attribuire` / `Valore rilevato`; il loader in **`extraction/evaluation.py`** tollera nomi di colonna alternativi via `_find_column()`). `classify_field()` in `extraction/normalization.py` etichetta ogni campo come **OK**, **WRONG**, **MISSING** (atteso un valore, ricevuto null), **HALLUCINATED** (atteso null, prodotto un valore) o **OK_NULL**. Avvertenza: `dati.csv` è attualmente assente sia dal working tree sia da git (`/mnt` è in `.gitignore`; solo i 9 PNG sono tracciati), e `cli.main()` lo richiede obbligatoriamente (`extraction/cli.py:315-316`): un clone fresco non può eseguire la valutazione CLI finché non si procura il file. Tracciato in [Domande Aperte](08-open-questions.md).

### Metriche RAW e FILTERED

L'accuratezza viene riportata due volte. **RAW** conta ogni schermata; **FILTERED** scarta le schermate in cui `dataset_mismatch_guard()` (`extraction/normalization.py`) rileva che `ndg`/`denominazione` estratti non concordano con la ground truth: se il motore ha letto il cliente sbagliato, valutare gli altri campi sarebbe solo rumore.

### Conteggio di token e costi

Ogni chiamata VLM popola un blocco `_meta` (modello, token di prompt/completion, latenza, `estimated_cost_usd` da `PRICING_PER_1M` in `extraction/config.py`), aggregato per schermata in `_meta_agg` e stampato da `print_cost_summary()` in `extraction/evaluation.py`. Avvertenza: i modelli assenti dalla tabella prezzi costano silenziosamente $0.00 (`estimate_cost_usd()` in `vlm_client.py`), quindi i report possono sottostimare per i nomi di modello in anteprima.

### Esportazione del report di debug

`build_debug_report()` in `extraction/evaluation.py` scrive un CSV per schermata e per campo (separato da punto e virgola, `poc_debug_improved.csv`) con il valore estratto, quello atteso, la classificazione e il passaggio vincente: l'artefatto che leggi quando l'accuratezza regredisce.

## Interfacce

Tre interfacce, un motore. Nessuna reimplementa l'estrazione; la CLI e la GUI Tkinter condividono persino lo stesso runner batch, `run_extraction_batch()` in **`extraction/cli.py`**: non duplicare altrove la sua logica di thread pool.

### Runner batch da CLI

`python main.py` elabora ogni immagine in `INPUT_DIR`, scrive `mnt/data/poc_outputs_improved.json`, stampa l'accuratezza RAW + FILTERED e il riepilogo dei costi, e scrive il CSV di debug. **`main.py`** è uno shim sottile (carica `.env`, importa `extraction`); il vero lavoro è `BatchRunner` in `extraction/cli.py`, che crea una sola volta i due ChatModel LangChain condivisi (sono thread-safe) e distribuisce il lavoro su un `ThreadPoolExecutor` (`PARALLEL_WORKERS`, default 4). È il percorso più maturo: è quello che le istruzioni di validazione manuale del progetto prendono di mira. Esiste anche un passo di deduplica degli output per stessa pagina, ma è attualmente disabilitato (`_deduplicate_same_page_outputs()`, commentato a `extraction/cli.py:268-273` in attesa della validazione delle page_key).

### GUI desktop Tkinter

`python gui_app.py` apre un'app a finestra (**`gui_app.py`**, Tkinter di libreria standard): inserisci una chiave API, scegli provider/modello dai menu a discesa alimentati da `PROVIDER_MODELS`, selezioni gli screenshot e un CSV di ground truth opzionale, ed esegui in un thread in background. Chiama lo stesso `run_extraction_batch()`, scrive `poc_outputs_gui.json` / `poc_results_gui.csv` e (se è stato scelto un CSV di GT) esegue la stessa valutazione producendo `poc_debug_gui.csv`. I risultati sono mostrati raggruppati per nomi di pagina canonici con i totali di accuratezza e costo.

### Edge-agent PyQt6

`python edge-agent/edge_agent.py` (oppure `python main.py --gui`, oppure `run_edge_agent.bat` su Windows) lancia l'app di cattura dal vivo (**`edge-agent/edge_agent.py`**, PyQt6 + qt-material). La sua finestra (**`edge-agent/ui/main_window.py`**) ha schede per il controllo della cattura (`ui/capture_tab.py`), i risultati per pagina con JSON grezzo (`ui/extraction_results_tab.py`), una vista a foglio di calcolo dei campi canonici (la terza scheda "Dati Estratti" (`ui/data_table_tab.py`)) e una vista di debug del router LLM (`ui/debug_tab.py`, richiede sia `show_llm_tab=true` in `config.ini` sia il flag `--debug`). L'estrazione è interamente locale: `LocalExtractionClient` (**`edge-agent/local_extraction_client.py`**) collega `ingest_frame()` direttamente a `ExtractionPipeline.extract_from_image()` ed emette i risultati sul segnale Qt `result_ready`. In questo percorso non c'è alcun backend remoto.

## Cattura dal vivo (edge-agent)

Queste funzionalità trasformano il motore batch in uno strumento in tempo reale. Si configurano tramite **`edge-agent/config.ini`**, non con variabili d'ambiente.

### Cattura del monitor e pre-elaborazione

`BPERCaptureWorker` (**`edge-agent/workers/capture/bper_capture_worker.py`**, un QThread) cattura il monitor configurato via `mss` agli FPS configurati, poi pre-elabora ogni frame (upscale adattivo, unsharp mask, autocontrasto) via `preprocess_for_ocr()` in **`edge-agent/image_ops.py`**. Poiché la pre-elaborazione avviene qui, l'estrazione usa `extract_from_image()` e bypassa intenzionalmente `normalize_image()` del motore.

### Rilevamento e routing delle pagine

Prima di estrarre, l'agente decide quale pagina BPER è a schermo, con la strategia impostata da `router=` in `config.ini` (implementata in **`edge-agent/llm_router.py`**):

- **`llm`** (impostazione corrente): `LLMPageRouter` invia un frame ridotto più la ROI dell'intestazione a OpenAI `gpt-4o-mini` con i suggerimenti di pagina da **`edge-agent/assets/templates/bper/prompts.json`** (10 definizioni di pagina, incluso il catch-all "Altro / Non riconosciuto"). Una guardia anti-allucinazione rifiuta qualsiasi nome di pagina non presente nelle definizioni.
- **`ml`**: `MLPageRouter` avvolge `BPERPagePrototypeClassifier` (**`edge-agent/page_classifier.py`**): embedding DINOv2 ViT-S/14 (384 dimensioni) confrontati per similarità del coseno con i prototipi in cache in `assets/templates/bper/bper_page_prototypes.json`. Se torch non si importa, il classificatore si disabilita con grazia invece di andare in crash.
- **`hybrid`**: prima l'LLM, fallback su ML.

### Deduplica dei frame e gate di stabilità

I frame consecutivi vengono confrontati per hash percettivo (pHash di `imagehash`, distanza di Hamming ≤ `dedup_threshold`); i quasi-duplicati vengono saltati e il re-routing è limitato da `route_retry_seconds`. Una pagina riconosciuta deve poi restare ferma per 2 secondi (`STABILITY_SECONDS`) prima della cattura, così l'agente non estrae mai a metà scroll. Entrambi vivono in `bper_capture_worker.py`.

### Guida all'operatore e forzatura manuale

Il worker annuncia ogni pagina acquisita e quale pagina aprire dopo (stringhe UI in italiano), seguendo un ordinamento che ripiega su `prompts.json` quando l'Excel/CSV opzionale con la sequenza delle pagine è assente. "Acquisisci ora" nella scheda di cattura forza la cattura di una pagina selezionata manualmente (`force_capture()`). Un bordo rosso (`CaptureBorderOverlay`, **`edge-agent/ui/overlay.py`**) marca lo schermo monitorato.

### Risultati dal vivo ed esportazione CSV

Ogni risultato finisce sotto il proprio job ID e scatena `result_ready(job_id, result)`, aggiornando l'albero Risultati, la tabella Dati Estratti e il contatore delle catture. `LocalExtractionClient.export_csv()` scrive un CSV piatto, una riga per schermata.

### Modalità di cattura generica (legacy)

Selezionando "Generico" nella scheda di cattura si esegue `DefaultCaptureWorker` (**`edge-agent/workers/capture/default_capture_worker.py`**), che invia i frame grezzi in POST a `{api.base_url}/jobs/{job_id}/frames` (`http://localhost:8081` in `config.ini`). Nessun backend del genere esiste in questo repo: è un residuo dell'architettura pre-solo-locale, conservato ma inutilizzabile così com'è.

## Note sulla maturità

Il motore di estrazione e il percorso di valutazione via CLI sono le parti più esercitate della codebase; l'edge-agent è ricco di funzionalità ma porta con sé residui legacy (sezioni di config `[api]` / `[minio]` che nessun codice del percorso BPER legge; un hook di upload del dataset ridotto a no-op a `bper_capture_worker.py:713-715`). Il passo di deduplica degli output nella CLI è implementato ma disabilitato in attesa di validazione. Non esiste alcuna suite di test automatici: la validazione è il confronto manuale dei report di accuratezza e costo con una baseline.

Una nota di sicurezza per chiunque tocchi `edge-agent/config.ini`: una chiave API OpenAI era stata committata nella sua sezione `[llm]` (riga 23). Il 2026-07-21 la chiave è stata rimossa dall'**intera cronologia git** (`git filter-repo` + force-push) e la riga contiene ora il placeholder `REDACTED_OPENAI_API_KEY`. La rotazione della chiave originale è ancora da confermare: va trattata come compromessa finché non è ruotata. Chi ha clonato il repo prima del 2026-07-21 deve riclonare. Fornisci la chiave reale solo in locale (config.ini è tracciato, quindi preferisci i fallback via variabile d'ambiente `OPENAI_API_KEY` / `LLM_API_KEY` letti a `bper_capture_worker.py:122`) e non committarne mai più una.
