# Funzionalità

poc-data-extraction converte gli screenshot bancari BPER in dati strutturati combinando elaborazione delle immagini, chiamate a Vision LLM e valutazione dell'accuratezza. Offre tre modi per eseguire l'estrazione (CLI, GUI desktop, cattura dal vivo dello schermo), una pipeline multi-passaggio che ripete i tentativi sui risultati deboli, un sistema di riconoscimento pagina ML/LLM intercambiabile e un framework di valutazione integrato che confronta i risultati con la ground truth.

## Pipeline di estrazione multi-passaggio

Il cuore del progetto. Ogni screenshot attraversa fino a quattro chiamate VLM, ciascuna mirata a una regione diversa con un prompt specializzato. Vedi [Architettura](04-architecture.md) e [Workflow](05-workflows.md) per il flusso dati completo.

### Passaggio anchor

Estrae solo l'NDG del cliente (identificatore) e la Denominazione (nome) da una striscia di intestazione ritagliata. Questi due campi fanno da àncora per l'intera estrazione: se il modello non riesce a leggerli con confidenza elevata (soglia predefinita: 0.95), i valori vengono azzerati.

- Entry point: `ExtractionPipeline.extract_anchors()` in `D:\Projects\poc-data-extraction\extraction\pipeline.py`
- Usa lo schema `AnchorResponse` da `D:\Projects\poc-data-extraction\extraction\schemas.py`
- Prompt definito come `ANCHOR_PROMPT` in `D:\Projects\poc-data-extraction\extraction\prompts.py`
- Regione di ritaglio: striscia di intestazione alle coordinate relative `(0.00, 0.00, 1.00, 0.22)` all'interno dell'area di contenuto, configurata in `D:\Projects\poc-data-extraction\extraction\config.py`

### Passaggio principale

Invia l'intera area di contenuto (sidebar rimossa) al VLM con il prompt di estrazione completo in italiano. Il prompt include suggerimenti dal passaggio anchor ("NDG atteso: ...", "Denominazione attesa: ...") così il modello può validare ciò che legge. Restituisce tutti i 45 campi, più tabelle strutturate per soggetti (soggetti), fidi (fidi) e garanzie (garanzie).

- Entry point: la sezione del passaggio principale di `ExtractionPipeline.extract_from_image()` in `D:\Projects\poc-data-extraction\extraction\pipeline.py`
- Usa lo schema `ExtractionResponse` (costruito dinamicamente da `FIELD_KEYS`) in `D:\Projects\poc-data-extraction\extraction\schemas.py`
- Prompt completo in `PROMPT` in `D:\Projects\poc-data-extraction\extraction\prompts.py`
- Ritaglio del contenuto: `(0.18, 0.12, 0.98, 0.98)` rimuove la sidebar BPER

### Passaggio di retry

Dopo il passaggio principale, la pipeline ispeziona ogni campo. Qualsiasi campo tornato null o con confidenza inferiore a 0.60 attiva un retry per la sua area (HEADER, BODY o FOOTER). Ogni area ottiene un ritaglio più stretto, contrasto e nitidezza migliorati e un prompt specifico per area. I retry vengono eseguiti in parallelo. I risultati si fondono tramite `pick_best()`: vince il valore con la confidenza più alta.

- Entry point: `ExtractionPipeline._retry_areas()` in `D:\Projects\poc-data-extraction\extraction\pipeline.py`
- Definizioni delle aree e mappatura campo-area in `RETRY_AREAS` e `AREA_TO_FIELDS` in `D:\Projects\poc-data-extraction\extraction\config.py`
- Prompt specifici per area (`RETRY_PROMPT_HEADER`, `RETRY_PROMPT_BODY`, `RETRY_PROMPT_FOOTER`) in `D:\Projects\poc-data-extraction\extraction\prompts.py`
- Budget: limitato a `MAX_CALLS_PER_SCREEN - 2` retry (predefinito: 2 retry dopo i passaggi anchor + principale)

### Controllo di coerenza

Un passaggio di post-elaborazione che usa i campi tooltip per correggere i campi principali. Se `tooltip_evidenze_b` ha un valore ma `evidenze` è null o sembra numerico, `evidenze` viene impostato a "B". Se `tooltip_descrizione_bmb` ha un valore ma `tipo` è null, `tipo` viene impostato a "BMB".

- Entry point: `ExtractionPipeline._coherence_check()` in `D:\Projects\poc-data-extraction\extraction\pipeline.py`

## Supporto LLM multi-provider

Il motore di estrazione funziona sia con modelli OpenAI sia con Google Gemini tramite un pattern factory. Si cambia provider tramite la variabile d'ambiente `LLM_PROVIDER`. Ogni provider ha una gestione diversa dell'output strutturato. Vedi la [Guida alla configurazione](10-configuration-guide.md#passare-da-un-provider-allaltro) per le ricette `.env` esatte.

### LLM Factory

Crea istanze thread-safe di `ChatModel` LangChain. Usa import lazy in modo che venga caricato solo il pacchetto del provider installato. Verifica che il nome del modello corrisponda al provider (impedisce di usare `gpt-4o` con Gemini o `gemini-2.0-flash` con OpenAI).

- Entry point: `create_chat_model()` in `D:\Projects\poc-data-extraction\extraction\llm_factory.py`
- Provider e modelli supportati elencati in `PROVIDER_MODELS` in `D:\Projects\poc-data-extraction\extraction\config.py`

### Output strutturato OpenAI

Usa `.with_structured_output(PydanticModel)` di LangChain per ottenere JSON garantito conforme allo schema dai modelli OpenAI. Il prompt viene inviato come `SystemMessage` e lo screenshot come `image_url` codificato in base64 in un `HumanMessage`.

- Implementazione: il ramo OpenAI di `call_vlm()` in `D:\Projects\poc-data-extraction\extraction\vlm_client.py`

### Output strutturato Gemini

I modelli Gemini 1.5 usano `json_mode` di LangChain con `response_schema`. I modelli Gemini più recenti (2.0+, 3.x) rifiutano gli schemi complessi, quindi il codice ripiega su JSON in forma libera: lo schema JSON Pydantic viene iniettato nel testo del prompt, il modello risponde con tipo MIME `application/json` e la risposta viene analizzata e validata manualmente con Pydantic.

- Implementazione: `_call_vlm_gemini_freeform()` e il ramo Gemini di `call_vlm()` in `D:\Projects\poc-data-extraction\extraction\vlm_client.py`
- La selezione della modalità schema è controllata da `_GEMINI_JSON_SCHEMA_MODELS` nello stesso file

### Retry con backoff

Gli errori API transitori (rate limit, timeout) ottengono retry con backoff esponenziale fino a 3 tentativi. Gli errori di parsing e validazione (`ValueError`) vengono sollevati immediatamente: non sono transitori.

- Entry point: `call_vlm_with_retry()` in `D:\Projects\poc-data-extraction\extraction\vlm_client.py`
- Formula del backoff: `min(8.0, 2^i * 0.8) + 0.05*i` secondi

## Elaborazione delle immagini

Gli screenshot passano per una normalizzazione prima di qualsiasi chiamata VLM.

### Normalizzazione

Ridimensiona l'immagine in modo che il lato lungo sia di 1800 pixel, applica un leggero aumento di contrasto (1.05x) ed esegue un filtro unsharp mask per migliorare i bordi. Questo produce un input più pulito per il VLM senza alterare drasticamente l'immagine.

- Entry point: `normalize_image()` in `D:\Projects\poc-data-extraction\extraction\imaging.py`

### Ritaglio relativo

Tutte le regioni di ritaglio sono definite come coordinate relative `(left, top, right, bottom)` nell'intervallo 0.0-1.0. Questo rende i ritagli indipendenti dalla risoluzione. Il ritaglio principale del contenuto a `(0.18, 0.12, 0.98, 0.98)` rimuove la sidebar di navigazione BPER e la barra superiore.

- Entry point: `crop_relative()` in `D:\Projects\poc-data-extraction\extraction\imaging.py`
- Definizioni di ritaglio: `CONTENT_CROP`, `HEADER_IN_CONTENT` e `RETRY_AREAS` in `D:\Projects\poc-data-extraction\extraction\config.py`

### Salvataggio dei ritagli di debug

Quando `DEBUG_SAVE_CROPS=1`, ogni immagine di ritaglio intermedia viene salvata in `mnt/data/debug_crops/` per l'ispezione visiva.

- Entry point: `save_debug_crop()` in `D:\Projects\poc-data-extraction\extraction\imaging.py`

## Definizioni dei campi e schemi

Il progetto estrae 45 campi attraverso nove schermate BPER. I campi sono definiti una sola volta e usati ovunque.

### Field Keys

Un unico elenco ordinato di tutti i nomi di campo estraibili. Questo elenco guida la creazione dinamica del modello Pydantic, la logica di valutazione e l'esportazione CSV.

- Definizione: `FIELD_KEYS` in `D:\Projects\poc-data-extraction\extraction\fields.py`
- Include campi di intestazione (ndg, denominazione, tipo, stato, fase), campi di tabella (n_fido, rapporto, ecc.), campi soggetto appiattiti (da ndg_1 a ruolo_4), campi anagrafici (professione_principale, retribuzione_annua_netta) e campi tooltip

### Schema Pydantic dinamico

`FieldsModel` viene creato in fase di import usando `create_model()` di Pydantic, generando un attributo `Optional[FieldResult]` per ogni voce di `FIELD_KEYS`. Questo significa che aggiungere un nuovo campo richiede solo di aggiungere il suo nome all'elenco: nessuna modifica alla classe del modello. Vedi [Modello dati](06-data-model.md#fieldsmodel) per la forma completa dell'entità.

- Definizione: `FieldsModel` in `D:\Projects\poc-data-extraction\extraction\schemas.py`
- Ogni `FieldResult` porta con sé: `value`, `confidence` (0.0-1.0), `evidence_text` e `section`

### Metadati canonici dei campi

Ogni chiave di schema mappa a un nome visualizzato (per la presentazione nell'interfaccia) e a una chiave di pagina (a quale schermata BPER appartiene). Sono definite quattro pagine canoniche: `risultato_ricerca`, `elenco_soggetti`, `gestione_fidi_e_garanzie` e `note_da_richiesta`.

- Definizioni: `D:\Projects\poc-data-extraction\extraction\field_definitions.py` e `D:\Projects\poc-data-extraction\extraction\page_definitions.py`
- Utilizzati da: `build_canonical_field_entries()` in `D:\Projects\poc-data-extraction\extraction\canonical_mapping.py`

### Mappatura CSV-schema

Mappa le intestazioni di colonna italiane dalla ground truth CSV (es. "n FIDO", "Importo (E)", "Denom.") alle chiavi interne dello schema (es. `n_fido`, `importo_euro`, `denominazione`). Gestisce varianti di ortografia e spazi finali.

- Definizione: `CSV_TO_SCHEMA` in `D:\Projects\poc-data-extraction\extraction\fields.py`

## Elaborazione a lotti (batch) da CLI

Elabora tutti gli screenshot in una directory, valuta rispetto alla ground truth e ottiene report di accuratezza e costi. Vedi [Workflow](05-workflows.md) per il flusso passo passo.

### Batch Runner

Crea le istanze del modello LLM una sola volta e le condivide tra tutti i worker di estrazione. Supporta l'esecuzione parallela tramite `ThreadPoolExecutor` (worker configurabili, predefinito 12 nel codice). Accetta callback per il completamento per singola schermata e la gestione degli errori.

- Entry point: classe `BatchRunner` e wrapper `run_extraction_batch()` in `D:\Projects\poc-data-extraction\extraction\cli.py`
- Avviato da: `main()` in `D:\Projects\poc-data-extraction\extraction\cli.py`, chiamato da `D:\Projects\poc-data-extraction\main.py`

### Artefatti di output

La CLI salva due file: un file JSON (`poc_outputs_improved.json`) con i risultati completi dell'estrazione inclusi i metadati per campo, e un CSV di debug delimitato da punto e virgola (`poc_debug_improved.csv`) con i verdetti di accuratezza per campo. Entrambi finiscono nella directory `INPUT_DIR` (predefinito: `mnt/data/`).

- Salvataggio JSON: `main()` in `D:\Projects\poc-data-extraction\extraction\cli.py`
- CSV di debug: `build_debug_report()` in `D:\Projects\poc-data-extraction\extraction\evaluation.py`

### Deduplica delle pagine (sperimentale)

Esiste una funzione di deduplica che manterrebbe solo il miglior risultato per pagina canonica su più screenshot. Valuta gli output in base al numero di campi riempiti e alla confidenza. Attualmente questa funzionalità è implementata ma commentata nel batch runner.

- Implementazione: `_deduplicate_same_page_outputs()` in `D:\Projects\poc-data-extraction\extraction\cli.py` (righe 92-152, disabilitata alle righe 268-275)

## Valutazione dell'accuratezza

La valutazione integrata confronta i risultati dell'estrazione con una ground truth CSV.

### Classificazione dei campi

Ogni campo estratto viene classificato con uno di cinque stati: `OK` (corrisponde alla ground truth), `OK_NULL` (entrambi null), `WRONG` (i valori differiscono), `MISSING` (la ground truth ha un valore ma l'estrazione ha restituito null) o `HALLUCINATED` (l'estrazione ha prodotto un valore ma la ground truth è null). I campi numerici usano un confronto di numeri normalizzati. I campi di testo lungo (oltre 20 caratteri) usano un fuzzy matching con soglia 0.85.

- Entry point: `classify_field()` in `D:\Projects\poc-data-extraction\extraction\normalization.py`

### Guardia di disallineamento del dataset

Rileva quando la riga di ground truth non appartiene allo stesso cliente del risultato dell'estrazione confrontando NDG e Denominazione. Le schermate disallineate vengono escluse dalla metrica di accuratezza filtrata.

- Entry point: `dataset_mismatch_guard()` in `D:\Projects\poc-data-extraction\extraction\normalization.py`

### Doppia metrica di accuratezza

Riporta sia l'accuratezza RAW (tutti i campi, tutte le schermate) sia l'accuratezza FILTERED (esclude le schermate con disallineamento del dataset). La suddivisione per campo mostra quali campi il modello gestisce bene e con quali fatica.

- Entry point: `eval_outputs()` in `D:\Projects\poc-data-extraction\extraction\evaluation.py`

### Tracciamento dei costi

Ogni chiamata VLM registra i token di prompt, i token di completion, la latenza e il costo stimato in USD. Questi vengono aggregati per schermata e riportati nel riepilogo su console. Le tabelle di prezzo per tutti i modelli supportati sono mantenute in `PRICING_PER_1M`.

- Stima dei costi: `estimate_cost_usd()` in `D:\Projects\poc-data-extraction\extraction\vlm_client.py`
- Output di riepilogo: `print_cost_summary()` in `D:\Projects\poc-data-extraction\extraction\evaluation.py`
- Tabelle di prezzo: `PRICING_PER_1M` in `D:\Projects\poc-data-extraction\extraction\config.py`

## GUI desktop Tkinter

Un'applicazione desktop autonoma per l'estrazione a lotti interattiva.

### Selezione di provider e modello

Menu a discesa permettono di scegliere il provider LLM (OpenAI o Gemini) e il modello. L'elenco dei modelli si aggiorna dinamicamente quando si cambia provider. La chiave API si inserisce direttamente nell'interfaccia.

- Entry point: classe `App` in `D:\Projects\poc-data-extraction\gui_app.py`

### Selezione dei file ed estrazione a lotti

Una finestra di dialogo di esplorazione file seleziona una o più immagini di screenshot. Facoltativamente carica una ground truth CSV per il confronto di accuratezza. L'estrazione viene eseguita in un thread in background usando lo stesso `run_extraction_batch()` della CLI.

- Implementazione: `run_process()` in `D:\Projects\poc-data-extraction\gui_app.py`

### Visualizzazione dei risultati

Un'interfaccia a schede mostra un riepilogo dei costi, le metriche di accuratezza (se è stata caricata la ground truth) e una vista ad albero di tutti i campi estratti organizzati per schermata. Ogni campo mostra il proprio valore e il punteggio di confidenza.

- Implementazione: `display_results()` in `D:\Projects\poc-data-extraction\gui_app.py`

## Edge Agent (cattura dal vivo dello schermo)

Un'applicazione desktop PyQt6 che osserva il monitor dell'operatore ed estrae dati dalle schermate BPER in tempo reale. È l'interfaccia più complessa. Vedi [Architettura](04-architecture.md) per le relazioni tra i componenti e [Workflow](05-workflows.md) per il flusso di cattura.

### Cattura dal vivo degli screenshot

Cattura il monitor configurato a un FPS configurabile usando la libreria `mss`. Le immagini vengono pre-elaborate con stretching del contrasto e unsharp masking. Un overlay con bordo rosso segna l'area del monitor catturato.

- Entry point: `BPERCaptureWorker._capture_screenshot()` in `D:\Projects\poc-data-extraction\edge-agent\workers\capture\bper_capture_worker.py`
- Overlay: `CaptureBorderOverlay` in `D:\Projects\poc-data-extraction\edge-agent\ui\overlay.py`
- Pre-elaborazione: `preprocess_for_ocr()` in `D:\Projects\poc-data-extraction\edge-agent\image_ops.py`

### Deduplica dei frame

Ogni frame catturato ottiene un hash percettivo (pHash). Se la distanza di Hamming dal frame precedente è inferiore a una soglia (predefinito: 3), il frame è considerato un duplicato e viene saltato. Questo evita di sprecare chiamate LLM su schermate statiche.

- Implementazione: `BPERCaptureWorker._is_duplicate_frame()` in `D:\Projects\poc-data-extraction\edge-agent\workers\capture\bper_capture_worker.py`

### Riconoscimento pagina

Tre strategie di routing, selezionabili tramite `config.ini`:

**ML Router** -- Usa il vision transformer DINOv2 ViT-S/14 di Facebook per calcolare gli embedding delle immagini e li confronta con embedding prototipo pre-calcolati per ogni pagina BPER nota tramite similarità del coseno. Gli embedding prototipo sono memorizzati in cache in JSON. Degrada in modo controllato alla modalità disabilitata se PyTorch non è installato.

- Implementazione: `BPERPagePrototypeClassifier` in `D:\Projects\poc-data-extraction\edge-agent\page_classifier.py`
- Prototipi: `D:\Projects\poc-data-extraction\edge-agent\assets\templates\bper\bper_page_prototypes.json`
- Wrapper: `MLPageRouter` in `D:\Projects\poc-data-extraction\edge-agent\llm_router.py`

**LLM Router** -- Invia lo screenshot (ridotto a 1280px) più un ritaglio della ROI di intestazione a OpenAI Vision con un prompt strutturato di identificazione pagina. Restituisce tipo di pagina, confidenza e motivazione facoltativa. Valida i risultati rispetto ai nomi di pagina noti.

- Implementazione: `LLMPageRouter` in `D:\Projects\poc-data-extraction\edge-agent\llm_router.py`
- Definizioni di pagina: `D:\Projects\poc-data-extraction\edge-agent\assets\templates\bper\prompts.json`

**Hybrid** -- Prova prima il router LLM; ripiega su ML se l'LLM non restituisce alcuna corrispondenza.

### Stabilità temporale

Una pagina rilevata deve rimanere stabile per 2 secondi prima che parta l'estrazione. Se l'operatore si sposta altrove prima dei 2 secondi, il rilevamento si azzera. Questo evita di estrarre schermate transitorie o caricate solo in parte.

- Implementazione: logica di stabilità in `BPERCaptureWorker._capture_once()` in `D:\Projects\poc-data-extraction\edge-agent\workers\capture\bper_capture_worker.py`

### Guida all'operatore

Dopo ogni cattura riuscita, l'agente comunica all'operatore quale pagina BPER aprire successivamente. La sequenza delle pagine viene caricata da un file Excel se presente, ripiegando sulle definizioni di pagina di `prompts.json`. Il messaggio di guida si aggiorna solo quando cambia il prossimo obiettivo, evitando di intasare il log.

- Implementazione: `BPERCaptureWorker._next_pending_page()` e `_load_page_sequence()` in `D:\Projects\poc-data-extraction\edge-agent\workers\capture\bper_capture_worker.py`

### Bridge di estrazione locale

Connette il worker di cattura alla pipeline di estrazione senza chiamate di rete. Quando viene rilevata una pagina stabile, `LocalExtractionClient.ingest_frame()` esegue l'intera pipeline multi-passaggio nel thread di cattura, memorizza il risultato ed emette un segnale Qt per aggiornare le schede dell'interfaccia.

- Entry point: `LocalExtractionClient` in `D:\Projects\poc-data-extraction\edge-agent\local_extraction_client.py`

### Interfaccia a quattro schede

La finestra dell'edge agent ha quattro schede:

- **Cattura**: controlli di avvio/stop, configurazione FPS, selezione della modalità (BPER vs. generica), pulsante di cattura forzata per l'invio manuale della pagina, log in tempo reale. Entry point: `D:\Projects\poc-data-extraction\edge-agent\ui\capture_tab.py`
- **Risultati**: vista ad albero delle pagine estratte con indicatori di stato, tabella dei campi, visualizzatore JSON grezzo, esportazione CSV. Entry point: `D:\Projects\poc-data-extraction\edge-agent\ui\extraction_results_tab.py`
- **Dati Estratti**: vista a foglio di calcolo di tutti i dati estratti, rinomina delle colonne, esportazione CSV ed Excel tramite openpyxl. Entry point: `D:\Projects\poc-data-extraction\edge-agent\ui\data_table_tab.py`
- **Debug LLM** (visibile con il flag `--debug`): JSON grezzo dell'ultima richiesta/risposta del router LLM per la diagnostica del riconoscimento pagina. Entry point: `D:\Projects\poc-data-extraction\edge-agent\ui\debug_tab.py`

### Cattura forzata

Gli operatori possono attivare manualmente la cattura per una pagina specifica indicandone il nome, bypassando il router e i controlli di stabilità. Il nome della pagina viene normalizzato rispetto alle definizioni note di asset e prompt.

- Entry point: `BPERCaptureWorker.force_capture()` in `D:\Projects\poc-data-extraction\edge-agent\workers\capture\bper_capture_worker.py`

## Normalizzazione del testo

I risultati dell'estrazione passano per diversi passaggi di normalizzazione prima della valutazione o della visualizzazione.

### Normalizzazione del Tipo

Mappa le varianti di ortografia del campo "Tipo" a valori canonici (es. "mutui spesa" e "mutuo spesa" diventano entrambi "BPI Mutui").

- Implementazione: `normalize_tipo()` in `D:\Projects\poc-data-extraction\extraction\normalization.py`

### Normalizzazione di numeri e testo

`norm_number_str()` rimuove i simboli di valuta, normalizza i separatori delle migliaia e le virgole decimali, e formatta a due cifre decimali. `norm_text()` riduce gli spazi bianchi e converte in minuscolo per il confronto.

- Implementazione: entrambe in `D:\Projects\poc-data-extraction\extraction\normalization.py`

### Fusione dei campi

Quando arrivano i risultati del retry, `pick_best()` sceglie tra il valore esistente e il candidato in base alla nullità e alla confidenza. `merge_field_sources()` traccia quale passaggio della pipeline ha prodotto il valore vincente per ciascun campo.

- Implementazione: `pick_best()` e `merge_field_sources()` in `D:\Projects\poc-data-extraction\extraction\normalization.py`

## Esportazione dei dati

### Esportazione JSON

Output strutturato completo che include campi, tabelle (soggetti, fidi, garanzie), voci canoniche dei campi, aggregazione dei metadati, sorgenti dei campi e stato.

- Output CLI: `poc_outputs_improved.json` scritto da `main()` in `D:\Projects\poc-data-extraction\extraction\cli.py`
- Output GUI: `poc_outputs_gui.json` scritto da `run_process()` in `D:\Projects\poc-data-extraction\gui_app.py`

### Esportazione CSV

CSV piatto con una riga per campo per schermata. Include nomi visualizzati canonici, assegnazioni di pagina, valori, confidenza e testo di evidenza. Usa il punto e virgola come delimitatore e la codifica UTF-8 con BOM.

- Entry point: `export_to_csv()` in `D:\Projects\poc-data-extraction\extraction\evaluation.py`
- CSV dell'edge agent: `LocalExtractionClient.export_csv()` in `D:\Projects\poc-data-extraction\edge-agent\local_extraction_client.py`

### Esportazione Excel

Disponibile nella scheda Dati Estratti dell'edge agent tramite openpyxl.

- Entry point: `DataTableTab` in `D:\Projects\poc-data-extraction\edge-agent\ui\data_table_tab.py`
