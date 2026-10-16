# Funzionalità

Il progetto fa una cosa sola al suo cuore (trasformare uno screenshot bancario BPER in dati strutturati e valutati) e la avvolge in tre interfacce più un layer di intelligenza per la cattura dal vivo. Le funzionalità sono raggruppate qui per ciò che fanno per te, non per directory. Ognuna indica il proprio entry point nel codice. Per le tracce end-to-end vedi [Workflow](05-workflows.md); per le forme dei dati vedi [Data Model](06-data-model.md); per le definizioni in parole semplici dei termini bancari italiani (`ndg`, `fido`, `soggetti`, …) vedi il [Glossario](11-glossary.md).

## Motore di estrazione

Tutto il resto esiste per alimentare questo motore o per riferire sui suoi risultati. Vive interamente nel pacchetto senza UI **`extraction/`**.

### Lettura multi-pass degli screenshot

Consegni al motore un'immagine e ricevi un record con ogni campo che è riuscito a leggere. Lavora in tre passaggi anziché uno, perché un singolo prompt che copre 45 campi su una schermata bancaria densa legge peggio di più prompt mirati. L'orchestrazione è `ExtractionPipeline.extract_from_image()` / `extract_from_screen()` in **`extraction/pipeline.py`**:

- **Passaggio anchor** (`extract_anchors()`) legge la striscia di intestazione sulla famiglia calibrata, l’immagine intera fuori calibrazione, ed estrae `ndg` e `denominazione` contro `AnchorResponse`. Annulla i valori sotto `ANCHOR_CONF_MIN` (0.95); con `STOP_ON_ANCHOR_UNCERTAIN=1` esce in anticipo se entrambi gli anchor risultano nulli dopo il filtro.
- **Passaggio principale** invia la regione del contenuto (`CONTENT_CROP` sulla famiglia calibrata, il frame intero altrimenti: ADR 0010) con i suggerimenti degli anchor ("NDG atteso: …") ed estrae tutti i campi scalari più le tabelle `soggetti` / `fidi` / `garanzie` in un'unica chiamata.
- **Passaggio di retry** individua le aree (HEADER / BODY / FOOTER, mappate in `AREA_TO_FIELDS`) che contengono campi nulli o con confidenza sotto `RETRY_CONF_MIN` (default 0.60) e rilegge ciascuna con un ritaglio dedicato da `RETRY_AREAS`, contrasto e nitidezza extra e un prompt specifico per area. I retry girano in un thread pool annidato, con tetto di passaggi logici a `MAX_CALLS_PER_SCREEN - 2` (i tentativi di rete interni possono essere più numerosi), e le aree vengono scelte nell'ordine di dichiarazione di `AREA_TO_FIELDS` (non alfabetico). `MAX_CALLS_PER_SCREEN` è derivato da `2 + len(AREA_TO_FIELDS)` (= 5) perché il tetto copra un retry per area: con un tetto minore le aree in coda restano irraggiungibili, e su una pagina a sezione singola sono proprio quelle a contenere il dato utile ([ADR 0004](adr/0004-budget-retry-derivato-dalle-aree.md)). Per ogni campo, `pick_best()` in **`extraction/normalization.py`** decide il vincitore (il non-nullo batte il nullo; a parità vince la confidenza più alta); le tabelle si fondono per numero di righe e poi per confidenza in `_merge_tables()`.

> **Gate applicato**: gli anchor a bassa confidenza vengono azzerati nelle copie effettivamente restituite da `extract_anchors()`, prima dei suggerimenti al main, dell’uscita anticipata e del merge (`extraction/pipeline.py`).

Quando il retry BODY riempie una tabella `soggetti` vuota, ammette solo righe con confidenza almeno `RETRY_CONF_MIN` e con NDG o denominazione non nulli, sia sulla famiglia calibrata sia fuori calibrazione. Le righe deboli o anonime vengono scartate singolarmente prima del flatten. I criteri di sostituzione delle tabelle già popolate e quelli di `fidi`/`garanzie` restano invariati ([ADR 0019](adr/0019-filtro-soggetti-da-retry-su-tabella-vuota.md)).

I due metodi di ingresso differiscono per scelta progettuale: `extract_from_screen(path)` (CLI, GUI Tkinter) prima normalizza l'immagine; `extract_from_image(img, screen_id)` (edge-agent) salta `normalize_image()` perché il frame è già stato pre-elaborato a monte.

I prompt vivono in **`prompts/*.json`** (un file per prompt) e vengono caricati una sola volta all'avvio da `prompt_store.py` (nella root, fuori da `extraction/`, così leggere un prompt non tira dentro LangChain); `extraction/prompts.py` si limita a esporre le costanti storiche (`PROMPT`, `ANCHOR_PROMPT`, `FIELD_RETRY_PROMPTS`) lette dal catalogo. Sono scritti in italiano di proposito: le schermate, le etichette e i termini bancari sono italiani, e le chiavi di campo (`professione_principale`, `filiale_relazione`, …) sono vocabolario di dominio portante che non va tradotto.

### Backend LLM indipendente dal provider

Una sola variabile d'ambiente (`LLM_PROVIDER`) commuta tra OpenAI (default, `gpt-4o`) e Google Gemini; nient'altro cambia. La factory unica è `create_chat_model()` in **`extraction/llm_factory.py`**: importa in modo lazy il pacchetto del provider giusto, applica le safety settings di Gemini, delega a un adapter per famiglia di modelli (`extraction/model_adapters.py`) costruzione, profondità di ragionamento (`LLM_THINKING_LEVEL`, oggi per la famiglia Gemini 3) e strategia di output, e rifiuta con un errore chiaro sia i nomi che non appartengono a nessuna famiglia sia le combinazioni provider/modello incoerenti. Le chiamate passano per `call_vlm()` / `call_vlm_with_retry()` in **`extraction/vlm_client.py`**; i retry coprono solo gli errori transitori, mentre i fallimenti di parsing (`ValueError`) vengono risollevati subito. L'unica eccezione deliberata alla factory: `LLMPageRouter` nell'edge-agent usa l'SDK `openai` grezzo, solo per il routing delle pagine. Vedi [Architettura](04-architecture.md) per il perché questa cucitura conta.

### Output strutturato e validato da schema

Ogni risposta deve rispettare uno schema Pydantic: OpenAI e Gemini 1.5 usano l’output strutturato di LangChain, mentre le famiglie Gemini recenti ricevono lo schema nel prompt e passano per una validazione manuale del JSON. Gli schemi sono in **`extraction/schemas.py`**: `FieldResult` (valore + confidenza + evidenza + sezione), `Soggetto`, `Fido`, `Garanzia` e i top-level `ExtractionResponse` / `AnchorResponse`. Il modello per-campo è generato dinamicamente con `create_model()` a partire da `FIELD_KEYS` in **`extraction/fields.py`**, quindi lo schema e l'elenco dei campi non possono divergere. Le stranezze dei provider sono gestite in `vlm_client.py`: Gemini 1.5 usa json_mode, Gemini 2.0+/3.x riceve lo schema iniettato nel prompt con validazione Pydantic manuale.

### Confidenza e provenienza per campo

La mappa `_field_sources`, costruita in `extraction/pipeline.py` ed esposta come `source_attempt` nel report di debug, registra il passaggio vincente (`ANCHOR_HEADER`, `CONTENT_MAIN` o `RETRY_{HEADER|BODY|FOOTER}`). L'appiattimento dei soggetti confronta ciascuna delle dodici chiavi `ndg_1..4`/`denominazione_1..4`/`ruolo_1..4` con il valore scalare già presente usando `pick_best()`: il non nullo prevale sul nullo, poi conta la confidenza e a parità resta il corrente. Se vince il valore tabellare, la sorgente diventa quella della tabella accettata, `CONTENT_MAIN` o `RETRY_BODY` ([ADR 0018](adr/0018-appiattimento-soggetti-con-merge-e-provenienza.md)). Restano limiti diagnostici: il main assegna una sorgente anche ai campi assenti e le correzioni di coerenza non registrano una nuova provenienza. I campi prodotti dal flatten non aggiungono `evidence_text` (vedi [Data Model](06-data-model.md)).

### Regole di coerenza di dominio e normalizzazione

Dopo il merge, regole bancarie cablate riparano l'output (`_coherence_check()` in `extraction/pipeline.py`): un `tooltip_evidenze_b` presente forza `evidenze` a "B", un `tooltip_descrizione_bmb` presente forza `tipo` a "BMB", e `normalize_tipo()` collassa i sinonimi del tipo. La normalizzazione al momento del confronto (uguaglianza numerica, parsing delle date, fuzzy matching per il testo libero lungo) vive in **`extraction/normalization.py`**, così le differenze di pura formattazione non contano come errori.

### Mappatura canonica di campi e pagine

Un layer di denominazione rivolto al cliente mappa ogni chiave di schema a un nome visualizzato e a una delle cinque pagine di origine: `risultato_ricerca`, `elenco_soggetti`, `gestione_fidi_e_garanzie`, `note_da_richiesta`, `scheda_privati`. I tredici campi Scheda Privati hanno `page_key=scheda_privati` e `export_group_key=note_da_richiesta`: `resolve_field_export_group_key()` conserva quattro gruppi e 45 colonne nell'Excel e l'ordine delle voci canoniche. I pezzi sono **`extraction/field_definitions.py`**, **`extraction/page_definitions.py`** e `build_canonical_field_entries()` in **`extraction/canonical_mapping.py`**. CSV e albero Tkinter leggono le voci canoniche; tabella ed Excel live usano i campi consolidati e il gruppo di export ([ADR 0020](adr/0020-pagina-sorgente-separata-dal-gruppo-export.md)). Il metadato di origine non riduce i retry e non dipende dal nome restituito dal router.

## Valutazione di accuratezza e costi

Leggere le schermate è metà del punto; il progetto esiste per misurare quanto bene legge e quanto costa farlo.

### Valutazione su ground truth

Ogni campo estratto viene confrontato con il valore atteso di `mnt/data/dati.csv` (formato lungo: `Fotogramma` / `Denominazione da attribuire` / `Valore rilevato`; il loader in **`extraction/evaluation.py`** tollera nomi di colonna alternativi via `_find_column()`). `classify_field()` in `extraction/normalization.py` etichetta ogni campo come **OK**, **WRONG**, **MISSING** (atteso un valore, ricevuto null), **HALLUCINATED** (atteso null, prodotto un valore) o **OK_NULL**. Avvertenza: `dati.csv` è attualmente assente sia dal working tree sia da git (`/mnt` è in `.gitignore`; solo i 9 PNG sono tracciati), e `cli.main()` lo richiede obbligatoriamente (`extraction/cli.py::main`): un clone fresco non può eseguire la valutazione CLI finché non si procura il file. Tracciato in [Domande Aperte](08-open-questions.md).

### Metriche RAW e FILTERED

L'accuratezza viene riportata due volte. **RAW** conta ogni schermata; **FILTERED** scarta le schermate in cui `dataset_mismatch_guard()` (`extraction/normalization.py`) rileva che `ndg`/`denominazione` estratti non concordano con la ground truth: se il motore ha letto il cliente sbagliato, valutare gli altri campi sarebbe solo rumore. Gli NDG, compresi `ndg_1..4`, vengono confrontati con `normalize_ndg()`, la stessa funzione usata dal consolidamento live: separatori e zeri iniziali dei soli identificatori numerici non creano differenze, mentre i suffissi alfanumerici restano distinti ([ADR 0017](adr/0017-identita-ndg-condivisa-tra-valutazione-e-consolidamento.md)).

### Conteggio di token e costi

Ogni chiamata VLM popola un blocco `_meta` (modello, token di prompt/completion, latenza, `estimated_cost_usd` da `PRICING_PER_1M` in `extraction/config.py`), aggregato per schermata in `_meta_agg` e stampato da `print_cost_summary()` in `extraction/evaluation.py`. Avvertenza: i modelli assenti dalla tabella prezzi costano silenziosamente $0.00 (`estimate_cost_usd()` in `vlm_client.py`), quindi i report possono sottostimare per i nomi di modello in anteprima.

### Esportazione del report di debug

`build_debug_report()` in `extraction/evaluation.py` scrive un CSV per schermata e per campo (separato da punto e virgola, `poc_debug_improved.csv`) con il valore estratto, quello atteso, la classificazione e il passaggio vincente: l'artefatto che leggi quando l'accuratezza regredisce.

## Interfacce

Tre interfacce, un motore. Nessuna reimplementa l'estrazione; la CLI e la GUI Tkinter condividono persino lo stesso runner batch, `run_extraction_batch()` in **`extraction/cli.py`**: non duplicare altrove la sua logica di thread pool.

### Runner batch da CLI

`python main.py` elabora ogni immagine in `INPUT_DIR`, scrive `mnt/data/poc_outputs_improved.json`, stampa l'accuratezza RAW + FILTERED e il riepilogo dei costi, e scrive il CSV di debug. **`main.py`** è uno shim sottile (carica `.env`, importa `extraction`); il vero lavoro è `BatchRunner` in `extraction/cli.py`, che crea una sola volta i due ChatModel LangChain condivisi (sono trattati come thread-safe) e distribuisce il lavoro su un `ThreadPoolExecutor` (`PARALLEL_WORKERS`, default 4). Conserva gli output delle schermate elaborate senza deduplicarli per pagina canonica.

### GUI desktop Tkinter

`python gui_app.py` apre un'app a finestra (**`gui_app.py`**, Tkinter di libreria standard): carica `.env` prima del motore e inizializza provider e modello dalla configurazione effettiva, conservando anche un modello personalizzato. Puoi inserire la chiave API, cambiare provider/modello, selezionare screenshot e un CSV di ground truth opzionale ed eseguire in un thread in background. Chiama lo stesso `run_extraction_batch()`, scrive `poc_outputs_gui.json` / `poc_results_gui.csv` e, con un CSV di GT, `poc_debug_gui.csv`. I risultati sono mostrati per pagina di origine con i totali di accuratezza e costo ([ADR 0021](adr/0021-dotenv-prima-del-motore-nella-gui-tkinter.md)).

### Edge-agent PyQt6

`python edge-agent/edge_agent.py` (oppure `python main.py --gui` o `run_edge_agent.bat`) apre l’app PyQt6. `ui/main_window.py` contiene Cattura e Dati Estratti, più Debug LLM con `--debug`; per vedere il traffico del router serve anche `show_llm_tab=true`. `LocalExtractionClient.ingest_frame()` accoda il frame su un pool di thread daemon e restituisce la sequenza di acquisizione. Il loop può continuare mentre `ExtractionPipeline.extract_from_image()` lavora. Il backend applicativo è locale, ma l’estrazione invia immagini al provider LLM via rete. Dati Estratti consolida in una riga per pratica con `practice_consolidation.py` ed esporta Excel tramite `excel_export.py`; confidenza, costi e provenienza restano nei log.

## Cattura dal vivo (edge-agent)

Queste funzionalità trasformano il motore batch in uno strumento in tempo reale. Si configurano tramite **`edge-agent/config.ini`**, non con variabili d'ambiente.

### Cattura del monitor e pre-elaborazione

`BPERCaptureWorker` (**`edge-agent/workers/capture/bper_capture_worker.py`**, un QThread) cattura il monitor configurato via `mss` agli FPS configurati, poi pre-elabora ogni frame (upscale adattivo, unsharp mask, autocontrasto) via `preprocess_for_ocr()` in **`edge-agent/image_ops.py`**. Poiché la pre-elaborazione avviene qui, l'estrazione usa `extract_from_image()` e bypassa intenzionalmente `normalize_image()` del motore.

### Rilevamento e routing delle pagine

Prima di estrarre, l'agente decide quale pagina BPER è a schermo, con la strategia impostata da `router=` in `config.ini` (implementata in **`edge-agent/llm_router.py`**):

- **`llm`**: `LLMPageRouter` invia un frame ridotto più la ROI dell'intestazione al modello configurato in `config.ini [llm]` (il file spedito usa `gemini-3.8-flash` sull'endpoint OpenAI-compatibile di Google) con i suggerimenti di pagina da **`edge-agent/assets/templates/bper/prompts.json`** (10 definizioni di pagina, incluso il catch-all "Altro / Non riconosciuto"). Una guardia anti-allucinazione rifiuta qualsiasi nome di pagina non presente nelle definizioni. **È l'impostazione corrente dal 2026-08-18** ([ADR 0006](adr/0006-router-llm-come-predefinito.md)): riconosce la pagina dal testo, quindi è invariante a dimensione, posizione e annidamento della finestra, che è ciò che il contesto reale di esercizio richiede. Costo: una chiamata per frame instradato, e 4-5 secondi di latenza.
- **`ml`** (ripiego; resta il default nel codice quando `config.ini` manca, così l'avvio senza configurazione non fa chiamate di rete): `MLPageRouter` avvolge `BPERPagePrototypeClassifier` (**`edge-agent/page_classifier.py`**): embedding DINOv2 ViT-S/14 (384 dimensioni) della ROI sull'area applicativa `(0.0, 0.20, 1.0, 0.98)`, schiacciata a 224x224, confrontati con i prototipi in cache in `assets/templates/bper/bper_page_prototypes.json` per **similarità del coseno centrata**: al vettore della query e a quelli dei prototipi viene sottratto il centroide dei prototipi, così resta soltanto ciò che distingue una pagina dalle altre. Soglia 0.35 sul punteggio centrato. Se torch non si importa, il classificatore si disabilita con grazia invece di andare in crash. Il perché della centratura, con le misure, è in [ADR 0002](adr/0002-riconoscimento-pagina-roi-e-coseno-centrato.md).
- **`hybrid`**: prima l’LLM, fallback su ML.
- **`local-first`**: prova la decisione locale per margine o classe di scarto. L’inizializzazione attuale crea però `MLPageRouter`, quindi i casi incerti tornano al router ML, senza escalation all’LLM descritta nell’ADR 0008. Vedi [Workflow](05-workflows.md).

### Deduplica dei frame e gate di stabilità

Il worker confronta prima i pixel del frame normalizzato: ogni cambiamento avvia una nuova visita, anche se riguarda un solo carattere dell’NDG. Il pHash limita il lavoro di routing sui frame simili; la stabilità richiede poi 2 secondi senza cambiamenti. L’invio mette la visita in attesa: solo un esito diverso da `ERROR` la completa. Un errore o un invio rifiutato consente un nuovo tentativo dopo la stabilizzazione. Tornare su una pagina o cambiare pratica consente quindi una nuova acquisizione; `captured_page_types` serve solo alla guida ([ADR 0014](adr/0014-acquisizione-per-visita-con-esito.md)). Animazioni persistenti possono impedire la cattura automatica: resta disponibile lo scatto manuale.

### Guida all'operatore e forzatura manuale

Il worker annuncia gli esiti e suggerisce quale pagina aprire dopo secondo il registro pagine. «Acquisisci ora» accoda un comando: il loop di cattura esegue lo scatto nel proprio thread e mantiene la pagina scelta anche dopo un errore di estrazione, finché il frame non cambia. Il comando non interrompe un routing già in corso ([ADR 0015](adr/0015-scatto-manuale-nel-thread-di-cattura.md)). I contatori distinguono frame inviati ed elaborati; gli errori non sono annunciati come estrazioni riuscite. Un bordo rosso (`ui/overlay.py`) marca il monitor osservato.

### Risultati dal vivo ed esportazione Excel

Ogni completamento emette `result_ready(job_id, result)` con `_capture_sequence`; il segnale può arrivare fuori ordine. La UI rilegge `get_results(job_id)`, che espone solo il prefisso completato in ordine di acquisizione. `practice_consolidation.consolidate()` unisce poi i frame per NDG e `excel_export.export_results()` scrive una riga per pratica. I contatori di Cattura distinguono gli invii dai completamenti, inclusi gli errori; non misurano il numero di pratiche visibili.

### Modalità di cattura generica (legacy)

Selezionando "Generico" nella scheda di cattura si esegue `DefaultCaptureWorker` (**`edge-agent/workers/capture/default_capture_worker.py`**), che invia i frame grezzi in POST a `{api.base_url}/jobs/{job_id}/frames` (`http://localhost:8081` in `config.ini`). Nessun backend del genere esiste in questo repo: è un residuo dell'architettura pre-solo-locale, conservato ma inutilizzabile così com'è.

## Note sulla maturità

La suite `tests/` copre la logica locale, la cattura e i contratti asincroni. `python tools/check.py` esclude i soli casi DINOv2 marcati `slow`; la suite completa resta `python -m pytest tests`. Accuratezza e costo richiedono una baseline con provider reale. Nell’edge-agent `get_results()` pubblica solo il prefisso completato nell’ordine di acquisizione: un frame precedente lento ritarda quelli successivi, evitando di associare una schermata senza NDG alla pratica sbagliata ([ADR 0013](adr/0013-risultati-nell-ordine-di-acquisizione.md), [API Python](12-python-api.md)).

Una nota di sicurezza per chiunque tocchi `edge-agent/config.ini`: una chiave API OpenAI era stata committata nella sua sezione `[llm]` (riga 23). Il 2026-07-21 la chiave è stata rimossa dall'**intera cronologia git** (`git filter-repo` + force-push) e la riga ora è **vuota**; `AgentConfig` tratta come vuoto anche qualunque valore che inizi per `REDACTED`, perché un placeholder rimasto in giro aveva già oscurato le chiavi da ambiente rompendo il router in silenzio. La rotazione della chiave originale è ancora da confermare: va trattata come compromessa finché non è ruotata. Chi ha clonato il repo prima del 2026-07-21 deve riclonare. Fornisci la chiave reale solo in locale, e preferisci i fallback da ambiente risolti da `AgentConfig.resolve_llm_settings()` in base al provider (`GEMINI_API_KEY` / `GOOGLE_API_KEY` / `LLM_API_KEY` per gemini, `OPENAI_API_KEY` / `LLM_API_KEY` per openai): `config.ini` è tracciato, e `build_exe.bat` si rifiuta di impacchettarlo con `api_key` non vuota.
