# Phase 4: Semantic Understanding

Lettura semantica del working tree a `f8f57e6124e008aa47ff6d8320aa508e9ef7976c`; modifiche documentali non committate incluse come dichiarazioni, non prove runtime. `verified` = codice letto; `documented` = intenzione o motivazione dichiarata; `unverified` = assunzione non garantita; `disputed` = divergenza tra dichiarazione e implementazione. Nessuna misura storica viene presentata come nuova esecuzione. Nessuna partizione sorella.

## Module Purposes (by partition)

### Partition: root

| Stato | Moduli / scopo e prova |
|---|---|
| verified | `main.py` seleziona l'interfaccia; `gui_app.py::App.run_process` rende il batch utilizzabile con selezione immagini/modello e GT facoltativo (`main.py:4`; `gui_app.py:228`). `extraction/cli.py::BatchRunner` concentra creazione modelli, parallelismo e callback condivisi (`extraction/cli.py:164`, `extraction/cli.py:210`). |
| verified | `extraction/pipeline.py::ExtractionPipeline` compone evidenze visive in più passaggi; `extraction/vlm_client.py::call_vlm` concentra formati messaggi, validazione e metadati; `extraction/llm_factory.py::create_chat_model` sceglie l'adapter provider estrattivo (`extraction/pipeline.py:122`; `extraction/vlm_client.py:123`; `extraction/llm_factory.py:18`). |
| verified | `extraction/config.py` conserva budget/geometria/prezzi; `extraction/imaging.py::normalize_image` e `select_content_crop` distinguono preprocessing da autorizzazione del crop (`extraction/config.py:56`; `extraction/imaging.py:19`, `extraction/imaging.py:52`). `prompt_store.py` carica e valida dati testuali; `extraction/prompts.py` li lega a costanti dei consumatori (`prompt_store.py::load_prompts`, `prompt_store.py:239`; `extraction/prompts.py:1`). |
| verified | `extraction/fields.py` contiene vocabolario/mapping GT; `field_definitions` e `page_definitions` descrivono nomi e raggruppamenti; `canonical_mapping` rende ogni payload leggibile dai client (`extraction/fields.py:1`; `extraction/fields.py::get_canonical_field_metadata`, `extraction/fields.py:112`; `extraction/canonical_mapping.py::build_canonical_field_entries`, `extraction/canonical_mapping.py:20`). `schemas.py` valida i payload estrattivi, senza validare i successivi metadati liberi (`extraction/schemas.py:67`, `extraction/schemas.py:76`). |
| verified | `extraction/normalization.py::pick_best` dà una semantica unica alla scelta tra campi; `classify_field` e `dataset_mismatch_guard` servono invece alla valutazione; `extraction/evaluation.py` carica GT ed esporta diagnostica/CSV (`extraction/normalization.py:104`, `extraction/normalization.py:134`, `extraction/normalization.py:195`; `extraction/evaluation.py::load_ground_truth`, `extraction/evaluation.py:47`). |
| verified | `edge-agent/app_paths.py` separa percorsi sorgente/bundle; `bootstrap.py` prepara la distribuzione portable; `config.py::AgentConfig` gestisce INI/router; `edge_agent.py::main` garantisce l'ordine preflight/UI nel percorso diretto (`edge-agent/app_paths.py::app_dir`, `edge-agent/app_paths.py:14`; `edge-agent/bootstrap.py::run_preflight`, `edge-agent/bootstrap.py:489`; `edge-agent/config.py:58`; `edge-agent/edge_agent.py:38`). |
| verified | `BaseCaptureWorker` è il ciclo cooperativo Qt; `BPERCaptureWorker` possiede camera, visite, dedup, routing e comandi; `DefaultCaptureWorker` conserva il diverso percorso upload generico (`edge-agent/workers/capture/base_capture_worker.py:41`; `edge-agent/workers/capture/bper_capture_worker.py:216`, `edge-agent/workers/capture/bper_capture_worker.py:346`; `edge-agent/workers/capture/default_capture_worker.py:34`). |
| verified | `frame_normalize` riconduce coordinate monitor a finestra; `image_ops` applica il preprocessing OCR; `stability` decide quando una pagina può essere acquisita senza dipendere da Qt (`edge-agent/frame_normalize.py::normalize_frame`, `edge-agent/frame_normalize.py:209`; `edge-agent/workers/capture/bper_capture_worker.py::BPERCaptureWorker._preprocess`, `edge-agent/workers/capture/bper_capture_worker.py:528`; `edge-agent/stability.py::StabilityTracker.observe`, `edge-agent/stability.py:46`). |
| verified | `page_registry` traduce nome/template in identità pagina; `page_classifier` produce classe, score, margine e scarto; `llm_router` adatta ML o servizio LLM a un risultato comune (`edge-agent/page_registry.py::PageRegistry.resolve`, `edge-agent/page_registry.py:69`; `edge-agent/page_classifier.py::BPERPagePrototypeClassifier.classify_detailed`, `edge-agent/page_classifier.py:660`; `edge-agent/llm_router.py::RouterResult`, `edge-agent/llm_router.py:29`). |
| verified | `local_extraction_client` disaccoppia accettazione, completamento e pubblicazione ordinata; `extraction_pool` permette task estrattivi daemon; `practice_consolidation` unisce la pratica e `excel_export` applica un unico layout esportabile (`edge-agent/local_extraction_client.py:127`, `edge-agent/local_extraction_client.py:193`; `edge-agent/extraction_pool.py:23`; `edge-agent/practice_consolidation.py:105`; `edge-agent/excel_export.py:217`). |
| verified | `ui/main_window` condivide client e sessione; `capture_tab` comanda la cattura e mostra contatori; `data_table_tab` ricostruisce righe di pratica; `debug_tab` e `overlay` sono viste opzionali collegate dalla UI (`edge-agent/ui/main_window.py::MainWindow._init_ui`, `edge-agent/ui/main_window.py:43`; `edge-agent/ui/capture_tab.py:249`, `edge-agent/ui/capture_tab.py:265`, `edge-agent/ui/capture_tab.py:378`; `edge-agent/ui/data_table_tab.py:194`). |
| verified | Gli strumenti `extract_frames`, `label_frames`, `make_contact_sheets`, `build_frame_registry` costruiscono un corpus con provenienza e revisione; `relocalize` corregge rettangoli e `build_prototypes` genera dataset del classificatore (`tools/extract_frames.py:108`; `tools/label_frames.py:156`; `tools/make_contact_sheets.py:32`; `tools/build_frame_registry.py:74`; `tools/relocalize.py:38`; `tools/build_prototypes.py:85`). |
| verified | `make_framing_corpus` e `benchmark_backbones` isolano la localizzazione con rettangoli noti e alternative DINOv2/DINOv3; `measure_classifier`, `measure_reject_prototypes`, `measure_tooltip_prototypes` confrontano configurazioni sperimentali, senza sostituire il runtime (`tools/make_framing_corpus.py:91`; `tools/benchmark_backbones.py:139`; `tools/measure_classifier.py:60`; `tools/measure_reject_prototypes.py:93`; `tools/measure_tooltip_prototypes.py:95`). |

Gli `__init__.py` senza comportamento sostanziale sono confini di import/facciate, non servizi ulteriori; l'inventario dei simboli e dei test è nella fase strutturale di questa esecuzione. La suite non è stata eseguita da questo worker.

## Design Decisions (by partition)

### Partition: root

- **verified** — Accuratezza e costo sono governati per stadi: due letture distinte degli identificatori e un main generalista, poi crop mirati solo per aree deboli. I costi sono somme di metadati dei passaggi riusciti; prezzi assenti producono zero e il router resta fuori dall'aggregazione estrattiva (`extraction/pipeline.py::ExtractionPipeline.extract_from_image`, `extraction/pipeline.py:147`; `_retry_areas`, `extraction/pipeline.py:294`; `_aggregate_meta`, `extraction/pipeline.py:383`; `extraction/vlm_client.py::estimate_cost_usd`, `extraction/vlm_client.py:26`; `edge-agent/llm_router.py::LLMPageRouter.route`, `edge-agent/llm_router.py:172`). **unverified**: interpretare questa somma come fattura totale o latenza percepita.
- **verified** — La prudenza geometrica è asimmetrica: fuori famiglia si paga l'immagine intera; il retry BODY non sostituisce array già presenti. Il criterio dipende dal percorso e dalla famiglia, non dal solo aspect (`extraction/pipeline.py:139`, `extraction/pipeline.py:258`; `extraction/imaging.py::select_content_crop`, `extraction/imaging.py:52`). **documented**: evitare mutilazioni silenziose ha priorità sul risparmio token (`docs/adr/0010-ritaglio-autorizzato-dal-percorso-e-dalla-famiglia.md:37`).
- **verified** — La concorrenza riguarda le invocazioni, la cronologia riguarda l'accettazione dei frame: `get_results` è una vista materializzata del prefisso, mentre `result_ready` è un evento di completamento (`edge-agent/local_extraction_client.py:127`, `edge-agent/local_extraction_client.py:193`). Il ritardo di un predecessore impedisce l'esposizione temporanea di note attribuibili alla pratica sbagliata (`edge-agent/practice_consolidation.py::consolidate`, `edge-agent/practice_consolidation.py:121`).
- **verified** — La visita è un'immagine invariata, non una pagina di catalogo né una pratica bancaria. Un cambiamento minimo riavvia osservazione e permette la stessa pagina per più NDG; `captured_page_types` ha solo ruolo di guida (`edge-agent/workers/capture/bper_capture_worker.py::BPERCaptureWorker._observe_frame`, `edge-agent/workers/capture/bper_capture_worker.py:329`; `_complete_capture`, `edge-agent/workers/capture/bper_capture_worker.py:299`). Conseguenza: animazioni persistenti possono impedire la stabilità automatica.
- **verified** — Manuale e automatico condividono camera e transizioni nel thread di cattura. L'API UI accoda senza catturare; l'ack diretto accoda senza modificare stato. Si rinuncia a interrompere una chiamata router già partita (`edge-agent/workers/capture/bper_capture_worker.py:278`, `edge-agent/workers/capture/bper_capture_worker.py:284`, `edge-agent/workers/capture/bper_capture_worker.py:722`; `edge-agent/llm_router.py:172`).
- **verified** — “Locale” indica assenza di backend applicativo nel flusso BPER; i modelli estrattivi inviano comunque immagini ai provider e possono farlo anche con routing ML (`edge-agent/workers/capture/bper_capture_worker.py:703`; `edge-agent/local_extraction_client.py:173`; `extraction/vlm_client.py:197`). Il worker generico è un'altra architettura e non dimostra l'esistenza di un server nel progetto (`edge-agent/workers/capture/default_capture_worker.py:65`).
- **verified** — Cache runtime e benchmark hanno finalità diverse: DINOv2 runtime usa CLS e geometria pinnata, il benchmark confronta localizzatori patch con alternative non pinnate e adapter transformers DINOv3 (`edge-agent/page_classifier.py:33`, `edge-agent/page_classifier.py:140`, `edge-agent/page_classifier.py:650`; `tools/benchmark_backbones.py:44`, `tools/benchmark_backbones.py:53`, `tools/benchmark_backbones.py:166`). **unverified**: generalizzare l'IoU del corpus sintetico all'accuratezza dei campi o alla qualità della cattura reale.

## Architecture Decision Records (per partition)

### Partition: root

Queste schede sintetizzano decisioni riscontrate nel codice. Le alternative sono `documented` quando attribuite a un ADR; non sono presentate come nuovi ADR accettati.

### Prefisso ordinato, ADR 0013

- **Decision:** **verified** — assegnare sequenza all'ingest accettato e pubblicare soltanto il prefisso contiguo (`edge-agent/local_extraction_client.py::LocalExtractionClient.ingest_frame`, `edge-agent/local_extraction_client.py:144`; `_process_frame`, `edge-agent/local_extraction_client.py:193`).
- **Context:** **verified** — l'associazione degli anonimi dipende dall'ultima pratica precedente nella lista (`edge-agent/practice_consolidation.py::consolidate`, `edge-agent/practice_consolidation.py:121`).
- **Alternatives rejected:** **documented** — ordinare soltanto i risultati già pronti lascia buchi semantici; serializzare tutte le estrazioni perde parallelismo; cambiare merge non ricostruisce cronologia (`docs/adr/0013-risultati-nell-ordine-di-acquisizione.md:48`).
- **Consequences:** **verified** — contatore/ack possono avanzare prima della tabella; errore pipeline e errore diagnostico non lasciano uno slot mancante (`edge-agent/local_extraction_client.py:174`, `edge-agent/local_extraction_client.py:187`, `edge-agent/local_extraction_client.py:204`; `edge-agent/ui/capture_tab.py:388`).

### Visita con esito, ADR 0014

- **Decision:** **verified** — distinguere nuova visita, accettazione e completamento, confermando il risultato con job/sequenza e identità visita (`edge-agent/workers/capture/bper_capture_worker.py::BPERCaptureWorker._observe_frame`, `edge-agent/workers/capture/bper_capture_worker.py:329`; `_acquire`, `edge-agent/workers/capture/bper_capture_worker.py:422`; `_complete_capture`, `edge-agent/workers/capture/bper_capture_worker.py:299`).
- **Context:** **documented** — il blocco per nome pagina durava troppo e un errore poteva consumare l'acquisizione (`docs/adr/0014-acquisizione-per-visita-con-esito.md:10`).
- **Alternatives rejected:** **documented** — dedup globale per nome, solo pHash, banda fissa NDG e retry a ogni frame non rispettano rispettivamente riacquisizione, piccoli cambiamenti, geometria variabile e cadenza di errore (`docs/adr/0014-acquisizione-per-visita-con-esito.md:55`).
- **Consequences:** **verified** — `ANCHOR_UNCERTAIN` completa la visita, `ERROR` la riarma solo se corrente; un ritorno a una pagina permette un nuovo ingest, mentre una pagina immobile completata viene saltata (`edge-agent/workers/capture/bper_capture_worker.py:308`, `edge-agent/workers/capture/bper_capture_worker.py:337`, `edge-agent/workers/capture/bper_capture_worker.py:370`).

### Comandi nel thread della camera, ADR 0015

- **Decision:** **verified** — manuale e ack entrano in una `queue.Queue`; il ciclo la drena e il `finally` chiude mss nel medesimo thread (`edge-agent/workers/capture/bper_capture_worker.py:58`, `edge-agent/workers/capture/bper_capture_worker.py:216`, `edge-agent/workers/capture/bper_capture_worker.py:284`, `edge-agent/workers/capture/bper_capture_worker.py:722`).
- **Context:** **verified** — la UI chiama direttamente `force_capture` e il worker ha un ciclo Python, non un loop eventi Qt (`edge-agent/ui/capture_tab.py::CaptureTab._on_force_capture`, `edge-agent/ui/capture_tab.py:417`; `edge-agent/workers/capture/base_capture_worker.py::BaseCaptureWorker.run`, `edge-agent/workers/capture/base_capture_worker.py:53`).
- **Alternatives rejected:** **documented** — un lock solo lascia la camera in UI; un segnale accodato richiederebbe un event loop; una seconda camera non risolve stato condiviso (`docs/adr/0015-scatto-manuale-nel-thread-di-cattura.md:51`).
- **Consequences:** **verified** — comando ritardato da lavoro già in corso, acquisizione al momento dell'esecuzione, coalescenza sulla stessa pagina pending, retry con selezione manuale e metadati vuoti (`edge-agent/workers/capture/bper_capture_worker.py:727`, `edge-agent/workers/capture/bper_capture_worker.py:753`, `edge-agent/workers/capture/bper_capture_worker.py:759`, `edge-agent/workers/capture/bper_capture_worker.py:428`).

### Catalogo validato e due politiche di fallback

- **Decision:** **verified** — prompt estrattivi caricati interamente e validati all'import; page catalog del router degrada a spec vuota (`prompt_store.py::load_prompts`, `prompt_store.py:239`; `edge-agent/llm_router.py::LLMPageRouter._load_spec`, `edge-agent/llm_router.py:102`).
- **Context:** **documented** — un prompt corrotto potrebbe produrre dati credibili ma errati; la mancata identificazione pagina è osservabile dall'operatore (`AGENTS.md:254`).
- **Alternatives rejected:** **verified** — niente reload parziale né fallback all'override esplicito; i moduli vincolano costanti da un catalogo unico (`prompt_store.py:220`, `prompt_store.py:284`; `extraction/pipeline.py:47`). Il motivo storico oltre quello dichiarato rimane **unverified**.
- **Consequences:** **verified** — copie bundle alternative possono recuperare un catalogo editabile rotto, ma con override esplicito il guasto resta visibile; bootstrap non riscrive prompt già popolati (`prompt_store.py:227`; `edge-agent/bootstrap.py::_ensure_files`, `edge-agent/bootstrap.py:213`).

### Cronologia riscontrata

**verified** — `git log` e `git blame` attribuiscono digest visita e pubblicazione prefisso a `f8f57e6` (“Fix capture ordering, retry state, and manual capture threading”, 11 settembre 2026); il codice corrente è a `edge-agent/workers/capture/bper_capture_worker.py:329` e `edge-agent/local_extraction_client.py:193`. `ff7ec6f` introduce il gate di famiglia, anchor interi e protezione array, presenti in `extraction/pipeline.py:139`, `extraction/pipeline.py:258`. `3abba24` aggiunge l'adapter transformers al benchmark (`tools/benchmark_backbones.py::HFBackbone`, `tools/benchmark_backbones.py:53`). La cronologia è contesto di intenzione; non dimostra accuratezza né prestazioni.

## Cross-Partition ADR

Nessun ADR attraversa partizioni distinte. Le decisioni di integrazione tra pipeline, client, cattura e UI sono interne a `root` e restano integralmente riportate nella sezione precedente.

## Embedded Assumptions (consolidated)

- **unverified** — NDG equivale a pratica e un frame senza NDG appartiene al precedente: il codice applica questa euristica ma non può provare che una nuova pratica non sia iniziata senza identificatore leggibile (`edge-agent/practice_consolidation.py::consolidate`, `edge-agent/practice_consolidation.py:118`). La normalizzazione elimina separatori e leading zero solo per numeri; suffissi alfanumerici restano (`normalize_ndg`, `edge-agent/practice_consolidation.py:46`).
- **unverified** — L'immutabilità dei pixel identifica abbastanza bene una visita d'operatore. La scelta è precisa sui piccoli cambiamenti, ma nessuna eccezione per animazioni/ore/cursori è applicata (`edge-agent/workers/capture/bper_capture_worker.py::BPERCaptureWorker._observe_frame`, `edge-agent/workers/capture/bper_capture_worker.py:336`).
- **unverified** — La finestra più grande con titolo compatibile è quella corretta; titolo/geometria non verificano contenuto e occlusione (`edge-agent/frame_normalize.py::select_window_rect`, `edge-agent/frame_normalize.py:140`).
- **unverified** — I modelli condivisi ammettono invocazioni concorrenti senza interferenze: il progetto li riusa senza lock, mentre protegge soltanto gli accumulatori live (`extraction/cli.py::BatchRunner.__init__`, `extraction/cli.py:184`; `edge-agent/local_extraction_client.py:110`, `edge-agent/local_extraction_client.py:119`). Questa lettura non valida i provider.
- **unverified** — Confidenza del modello è una misura calibrata. Il gate anchor usa 0.95, retry 0.60 e merge confronta numeri; `_status=OK` dopo main/retry richiede presenza, non confidenza finale ≥0.95 (`extraction/config.py:57`; `extraction/pipeline.py:214`).
- **disputed** — “local-first con fallback LLM” è dichiarato, ma l'inizializzatore costruisce ML per quel valore e preflight non lo include nei modi preparati (`edge-agent/config.py:30`; `edge-agent/workers/capture/bper_capture_worker.py::BPERCaptureWorker._init_router`, `edge-agent/workers/capture/bper_capture_worker.py:188`; `edge-agent/bootstrap.py:510`).
- **unverified** — Chiusura processo immediata in ogni fase: il pool esterno è daemon, ma il retry interno usa `ThreadPoolExecutor`; stop non cancella chiamate già attive e la UI può superare i 5 s (`edge-agent/extraction_pool.py:27`; `extraction/pipeline.py:337`; `edge-agent/ui/capture_tab.py:299`).

### Cross-partition assumptions

Nessuna assunzione tra partizioni; le assunzioni interne restano distinte dai comportamenti verificati.

## Hidden Contracts (cross-partition)

Nessun contratto tra partizioni. La notazione ↔ nella tabella seguente identifica componenti interni alla stessa `root`.

### Hidden Contracts (internal to root)

| Stato | Accordo implicito e conseguenza |
|---|---|
| verified | `LocalExtractionClient ↔ consolidate`: i consumatori devono leggere il prefisso, non accumulare i payload del segnale in ordine di arrivo. Entrambi gli export e il tab dati rispettano il confine (`edge-agent/local_extraction_client.py:204`, `edge-agent/local_extraction_client.py:222`; `edge-agent/ui/data_table_tab.py:195`; `edge-agent/ui/capture_tab.py:341`). |
| verified | `BPERCaptureWorker ↔ LocalExtractionClient`: `ingest_frame` deve restituire una sequenza, ogni risultato deve conservare `_capture_sequence`; il vecchio contratto che ritornava `None` farebbe leggere un successo come mancata accettazione (`edge-agent/workers/capture/bper_capture_worker.py:431`; `edge-agent/local_extraction_client.py:155`, `edge-agent/local_extraction_client.py:185`). |
| verified | `DirectConnection ↔ polling loop`: lo slot deve solo accodare; mutare direttamente pending consentirebbe a un completamento rapidissimo di precedere la registrazione dell'accettazione (`edge-agent/workers/capture/bper_capture_worker.py:64`, `edge-agent/workers/capture/bper_capture_worker.py:278`, `edge-agent/workers/capture/bper_capture_worker.py:435`). |
| verified | `pick_best ↔ merge_field_sources`: il vincitore deve essere uno degli argomenti per identità, perché la provenienza usa `chosen is candidate` (`extraction/normalization.py:104`, `extraction/normalization.py:126`). Coerenza e flatten restano fuori da questo aggiornamento (`extraction/pipeline.py:200`, `extraction/pipeline.py:365`). |
| verified | Vocabolario ↔ retry/prompts/schema: `FieldsModel` è costruito da `FIELD_KEYS`, ma le aree sono dichiarate separatamente e non contengono tutti i campi. `creazione` e i tooltip non attivano retry propri (`extraction/schemas.py:67`; `extraction/config.py:101`; `extraction/pipeline.py:295`). Non esiste una copertura automatica completa. |
| verified | Router ↔ client: `fields_json` viene passato ma `_process_frame` non lo applica ai campi estratti; la pipeline rilegge l'immagine. La confidenza pagina è solo `_page_confidence`, non quella dei campi (`edge-agent/workers/capture/bper_capture_worker.py:703`; `edge-agent/local_extraction_client.py:157`, `edge-agent/local_extraction_client.py:173`, `edge-agent/local_extraction_client.py:184`). |
| verified | CSV ↔ XLSX: il CSV neutralizza formule con apostrofo, i valori XLSX con `data_type='s'`. Le etichette Excel seguono `_write_labels` e non `_set_text` (`extraction/evaluation.py::_write_csv`, `extraction/evaluation.py:15`; `extraction/normalization.py::escape_csv_formula`, `extraction/normalization.py:62`; `edge-agent/excel_export.py:124`, `edge-agent/excel_export.py:160`). |
| verified | Runtime ↔ dataset prototipi: geometria query e prototipi deve coincidere; la chiave cache comprende modello/ROI/resize/scoring/scarti oltre al contenuto. Le immagini generate dai tool non devono già subire la stessa ROI (`edge-agent/page_classifier.py::embedding_geometry`, `edge-agent/page_classifier.py:140`; `tools/build_prototypes.py::widen_for_roi`, `tools/build_prototypes.py:67`). |
| verified | Shutdown ↔ ordine: scartare task in coda non pubblica errori sintetici; dopo shutdown gli slot accettati scartati possono lasciare incompleto il prefisso, e `requeue_job` è un no-op (`edge-agent/extraction_pool.py::DaemonThreadPool.stop`, `edge-agent/extraction_pool.py:44`; `edge-agent/local_extraction_client.py:206`, `edge-agent/local_extraction_client.py:214`). |

## Conventions Observed

- **Error handling — verified:** errori strutturali dei prompt fail-fast; confini UI/router/capture prevalentemente best-effort; pipeline anchor/main fail-fast, retry-area non fatale (`prompt_store.py:262`; `edge-agent/workers/capture/bper_capture_worker.py:206`; `extraction/pipeline.py:339`).
- **Logging — verified:** `print` per motore e diagnostica, segnali Qt per avanzamento cattura; la redirezione su file avviene quando stdout/stderr mancano, non sempre da sorgente (`edge-agent/local_extraction_client.py:41`; `edge-agent/workers/capture/base_capture_worker.py:17`; `edge-agent/edge_agent.py:15`).
- **Configuration — verified:** snapshot ambiente estrattivo, INI mutabile per cattura/router e catalogo JSON statico; le tre fonti non hanno un unico reload né una precedenza unica delle chiavi (`extraction/config.py:7`; `edge-agent/config.py:292`; `prompt_store.py:284`).
- **Domain — verified:** chiavi canoniche italiane mantenute lungo validazione, fusione e presentazione; nomi visuali sono metadati separati e le rinomine UI non riordinano i campi (`extraction/schemas.py:67`; `edge-agent/practice_consolidation.py:87`; `edge-agent/ui/data_table_tab.py:178`).
- **History — documented:** gli ADR registrano alternative e compromessi; risultati sperimentali dichiarati nei documenti richiedono una nuova esecuzione prima di essere usati come baseline attuale (`docs/adr/0013-risultati-nell-ordine-di-acquisizione.md:59`; `docs/adr/0015-scatto-manuale-nel-thread-di-cattura.md:61`).

### Cross-partition convention conflicts

Non applicabile alla partizione unica; le differenze interne di logging e configurazione rimangono documentate sopra.
