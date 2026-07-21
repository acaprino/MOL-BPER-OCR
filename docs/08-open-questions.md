# Domande aperte

Queste sono le cose che il codice da solo non può dirti: decisioni la cui motivazione è invisibile dal sorgente, fatti di dominio che solo chi ha usato l'applicazione BPER può confermare, e code sciolte della storia del progetto (il backend remoto rimosso, la riscrittura della storia git del 2026-07-21). Ogni domanda dichiara cosa è stato osservato e perché la risposta conta. Due di esse costeranno tempo reale a un nuovo sviluppatore fin dal primo giorno se restano senza risposta: dove vive il `mnt/data/dati.csv` canonico, e se la chiave OpenAI trapelata sia stata davvero ruotata.

Le domande sono ordinate, entro ciascuna sezione, per impatto sull'efficacia di un nuovo sviluppatore. Contesto correlato: [Architettura](04-architecture.md), [Workflow](05-workflows.md), [Guida alla configurazione](10-configuration-guide.md).

## Architettura

### Qual è il router di pagina inteso come default, LLM o ML?
Il `edge-agent/config.ini:4` committato imposta `router = llm`, ma il default nel codice è `ml` (`DEFAULT_ROUTER_MODE = "ml"`, `edge-agent/config.py:25`). Il percorso ML scarica DINOv2 ViT-S/14 da GitHub via `torch.hub.load()` al primo uso (`edge-agent/page_classifier.py:203`) e si disabilita in silenzio se torch non è disponibile. Se il routing LLM è lo standard reale, `torch`/`torchvision` (le voci più pesanti di `requirements.txt`) potrebbero diventare extra opzionali. Se il target è ML (o `hybrid`), il download dei pesi al primo avvio va documentato e serve una storia offline. Qual è dei due?

### Il gate di confidenza degli anchor dovrebbe filtrare gli anchor a bassa confidenza?
`extraction/pipeline.py:90-96` intende annullare gli anchor sotto `ANCHOR_CONF_MIN` (0.95), e `CLAUDE.md` lo documenta come "zeroes out low-confidence anchors"; ma il gate è un no-op: i dict `ndg`/`denominazione` che alimentano il prompt con i suggerimenti, l'uscita anticipata e il merge vengono copiati *prima* che il gate giri (`:87-88`), e `safe_set_field(..., None)` non può sovrascrivere un valore non nullo (`extraction/normalization.py:78-79`). L'unico codice che applica la soglia sui valori finali è `_is_confident_output()` dentro l'helper di deduplica disabilitato (`extraction/cli.py:77-89`). Il gate va corretto perché filtri davvero l'uso a valle (cosa che cambierebbe il comportamento dell'accuratezza), oppure il meccanismo inteso è l'istruzione a livello di prompt "restituisci null quando incerto", nel qual caso il codice del gate e l'affermazione di `CLAUDE.md` dovrebbero sparire?

### La GUI Tkinter dovrebbe passare un modello anchor accanto al modello principale?
`gui_app.py:238-247` inoltra a `run_extraction_batch()` il provider selezionato dal menu a tendina e `model_main`, ma mai `model_anchor`, quindi il passaggio anchor ricade sul `LLM_MODEL_ANCHOR` derivato dall'ambiente (default `gpt-4o`). Selezionare Gemini nella GUI mentre l'ambiente contiene i default OpenAI solleva quindi a metà esecuzione il `ValueError` di mismatch provider/modello in `extraction/llm_factory.py:59-63`. La GUI dovrebbe derivare il modello anchor dal provider selezionato, o il percorso Gemini del menu a tendina è notoriamente rotto?

### `preprocess_for_ocr()` è pensata per essere equivalente a `normalize_image()`?
La pipeline ha due entry point per scelta: `extract_from_screen()` normalizza internamente, mentre `extract_from_image()` si fida del chiamante (`extraction/pipeline.py:104-187`; commento con la motivazione a `edge-agent/local_extraction_client.py:84-85`). La `preprocess_for_ocr()` dell'edge-agent (`edge-agent/image_ops.py`) fa upscale adattivo + unsharp + autocontrasto: una trasformazione diversa dalla `normalize_image()` di `extraction/imaging.py`. Le due devono produrre input scalati/nitidi in modo comparabile (così che i numeri di accuratezza siano confrontabili tra CLI e cattura dal vivo), o la divergenza è accettata? Qualsiasi futuro chiamante che passi un'immagine grezza a `extract_from_image()` salta in silenzio ogni normalizzazione, spigolo noto o bug latente?

### Qual è il destino del percorso remoto/generico e dei suoi residui di config?
`DefaultCaptureWorker` fa ancora POST di frame grezzi verso `{api.base_url}/jobs/{job_id}/frames` (`edge-agent/workers/capture/default_capture_worker.py`), ma nessun backend del genere esiste in questo repo e `config.ini` lo punta a `http://localhost:8081`. Le sezioni `[minio]` e `[dataset]` sopravvivono in `edge-agent/config.ini:12-16,25-29` mentre l'upload del dataset è un no-op esplicito ("disabilitata per consolidamento locale", `edge-agent/workers/capture/bper_capture_worker.py:713-715`), e il commento alla riga 710 registra che l'upload remoto è stato rimosso deliberatamente. La modalità di cattura "Generico" e la sua config sono peso morto da eliminare, o è previsto il ritorno di un backend di ingestione remota? La risposta decide se rimuovere `requests`, le sezioni `[api]`/`[minio]` e `DefaultCaptureWorker`.

### La triplice diramazione Gemini è stata validata su ogni modello elencato?
`extraction/vlm_client.py` sceglie tra tre strategie di output strutturato per sottostringa: `_GEMINI_JSON_SCHEMA_MODELS = ("gemini-1.5",)` (riga 18) instrada i modelli 1.5 verso json_mode con `response_schema`, e tutto il resto di Gemini va in JSON a forma libera + validazione Pydantic manuale, perché (a quanto riportato) gli schemi complessi provocano `INVALID_ARGUMENT` su 2.0+/3.x. Questo è stato verificato per tutti i modelli di `PROVIDER_MODELS["gemini"]` (`extraction/config.py:24-32`), inclusi `gemini-3-flash-preview` e `gemini-3.1-flash-lite-preview`, o solo per uno o due? Un futuro nome di modello che non combacia con la sottostringa prende di default il ramo a forma libera. È quello il fallback sicuro inteso?

## Logica di business

### Dove vive il `mnt/data/dati.csv` canonico, e chi ne è il proprietario?
La CLI lo richiede tassativamente (`FileNotFoundError` a `extraction/cli.py:315-316`), il README ne documenta il formato (`README.md:221-241`) e l'intero apparato di valutazione è costruito attorno a esso; eppure il file non esiste né nel working tree né in alcun punto di git (`.gitignore:9` esclude `/mnt`; solo i 9 PNG sono stati aggiunti con force-add). Esiste una copia autorevole (quante righe, quali campi per schermata) e può essere condivisa con ogni sviluppatore? Senza un file di GT comune, `python main.py` non può girare su un clone fresco e i numeri di accuratezza di due sviluppatori non sono confrontabili.

### Le sovrascritture del controllo di coerenza sono regole BPER universalmente valide?
`_coherence_check()` (`extraction/pipeline.py:311-328`) riscrive in silenzio l'output del modello: se `tooltip_evidenze_b` ha un valore, `evidenze` viene forzato a `"B"` (rimpiazzando anche un valore estratto puramente numerico); se `tooltip_descrizione_bmb` ha un valore e `tipo` è null, `tipo` diventa `"BMB"`. Questi valori sintetizzati non sono segnalati in `_field_sources`, quindi a valle sembrano estrazioni pulite. Queste implicazioni valgono per tutte le pratiche BPER, o solo per le 9 schermate campione su cui sono state tarate? Una regola sbagliata qui produce output sbagliato con sicurezza, che la valutazione potrebbe classificare come OK.

### `TIPO_MAPPING` è l'insieme completo dei sinonimi dei tipi di pratica?
`extraction/normalization.py:10-14` canonicalizza esattamente tre varianti minuscole (`mutui spesa`, `mutuo spesa`, `bpi mutui`) in `"BPI Mutui"`. È l'insieme completo delle grafie di `tipo` che la UI BPER può mostrare, o solo ciò che è comparso nei dati campione? Qualsiasi variante non elencata passa non mappata e viene valutata WRONG contro la GT: invisibile finché qualcuno non ispeziona il CSV di debug.

### I binding di pagina canonica dei campi scheda-privati sono intenzionali?
Tutti i 13 campi scheda-privati (`dal`, `professione_principale`, `score_cgs`, `rating_ufficiale`, …) sono legati alla page_key `note_da_richiesta` in `extraction/field_definitions.py:114-165`, benché provengano dalle schermate "scheda privati" (schermate 4-5 secondo `CLAUDE.md`), non dalla pagina delle note. Questo binding guida l'export CSV canonico, il raggruppamento dei risultati Tkinter e la tab *Dati Estratti* dell'edge-agent. Impacchettarli sotto `note_da_richiesta` è una scelta deliberata di layout dei fogli rivolto al cliente (contratto a 4 pagine), o un'assegnazione errata da correggere prima che qualcuno costruisca sull'output canonico?

### L'appiattimento dei soggetti sovrascrive intenzionalmente i vincitori dei retry?
Il passo 8 della pipeline appiattisce incondizionatamente le prime quattro righe di `soggetti` in `ndg_1..4` / `denominazione_1..4` / `ruolo_1..4` (`extraction/pipeline.py:159-166`), dopo che il passaggio di retry ha già scelto i vincitori per campo per quelle stesse chiavi, elencate come campi di retry BODY in `extraction/config.py:73-76`. L'estrazione tabellare batte quindi sempre il retry per campo su queste 12 chiavi, a prescindere dalla confidenza. Precedenza voluta, o due percorsi di codice che si contendono per caso le stesse chiavi?

### Perché `creazione` e i cinque campi `tooltip_*` sono esclusi da ogni area di retry?
`AREA_TO_FIELDS` (`extraction/config.py:69-82`) assegna i campi ai ritagli di retry HEADER/BODY/FOOTER, ma `creazione` e tutte e cinque le chiavi `tooltip_*` non compaiono in nessuna area: se il passaggio principale li restituisce nulli o a bassa confidenza, non vengono mai ritentati. Per i tooltip potrebbe essere deliberato (compaiono solo al passaggio del mouse, quindi uno screenshot statico o li ha o non li ha), ma i tooltip alimentano anche le regole di coerenza viste sopra, quindi un tooltip mancato si propaga a cascata su `evidenze`/`tipo`. Deliberato o svista?

## Infrastruttura

### La chiave OpenAI trapelata è stata ruotata su OpenAI?
Una chiave API OpenAI era stata committata in `edge-agent/config.ini:23`. Il 2026-07-21 è stata ripulita dall'intera storia git (`git filter-repo`, force-push su origin); la riga ora contiene il placeholder `REDACTED_OPENAI_API_KEY`. Ripulire la storia non "de-trapela" un segreto: chiunque abbia mai clonato o fatto fetch del repo potrebbe avere ancora la chiave. È stata revocata/ruotata nella dashboard OpenAI, e l'utilizzo su quella chiave è stato verificato? Finché non c'è conferma, trattala come un incidente di sicurezza aperto, non come pulizia conclusa.

### Tutti i collaboratori hanno ri-clonato dopo la riscrittura della storia?
Poiché la riscrittura ha cambiato ogni hash di commit, qualsiasi clone precedente al 2026-07-21 è incompatibile con origin, e un push o un merge da un clone stantio **reintrodurrebbe la chiave trapelata** nella storia. Ogni collaboratore (e ogni runner CI, bot o mirror, se esistono) ha ri-clonato o fatto hard-reset sulla nuova origin? C'è una checklist che confermi che non restano fork stantii?

### Dove dovrebbero vivere i segreti dell'edge-agent da qui in avanti?
Anche dopo la ripulitura, il design che ha causato la fuga è intatto: `[llm] api_key` è un campo in un file **tracciato**, il router lo preferisce alle variabili d'ambiente (`config.llm_api_key or OPENAI_API_KEY or LLM_API_KEY`, `edge-agent/workers/capture/bper_capture_worker.py:122`), e `AgentConfig.save()` riscrive `llm_api_key` dentro `config.ini` (`edge-agent/config.py:326-332`), attualmente non chiamato, ma a un solo collegamento UI di distanza dal ri-persistere un segreto. La chiave dovrebbe spostarsi solo in `.env` (ribaltando la precedenza a env-first)? `save()` dovrebbe smettere di serializzarla? E `config.ini` dovrebbe acquisire uno split `config.ini.example` come `.env`/`.env.example`? Una decisione qui previene la ripetizione dell'incidente.

### Qual è il target di runtime/deployment previsto?
Non c'è `pyproject.toml`, né lockfile, né Dockerfile, né CI (`CLAUDE.md`, "Missing Infrastructure"); `requirements.txt` è vincolato in modo lasco e lascia LangChain e torch senza pin. L'unico packaging è un `.exe` PyInstaller dell'app Tkinter (`README.md:78-100`), mentre l'edge-agent (l'interfaccia "raccomandata" secondo il README) viene distribuito solo come `run_edge_agent.bat` più un checkout dei sorgenti. È strettamente un POC da laptop dello sviluppatore, o è prevista una build dell'edge-agent installabile dall'operatore? La risposta decide se valga la pena costruire pinning, packaging e un bootstrap offline di DINOv2.

### I file di sequenza pagine sono distribuiti separatamente?
`_load_page_sequence()` cerca `Guida pagine ITA .xlsx` (nota lo spazio prima di `.xlsx`) e ricade su `Nomenclatura.csv` in `edge-agent/assets/templates/bper/` (`edge-agent/workers/capture/bper_capture_worker.py:257,327-328`); nessuno dei due file esiste nel repo, quindi l'ordinamento delle pagine ricade sempre sull'ordine di `prompts.json`. Questi file esistono fuori dal repo (forniti dal cliente?), e l'ordine di fallback corrisponde davvero al flusso di navigazione dell'operatore nell'app BPER?

## Processo

### Come si verifica una modifica senza test e senza una baseline committata?
Non c'è alcuna suite di test automatica; `CLAUDE.md` prescrive "esegui l'estrazione, confronta accuratezza/costi con una baseline"; ma nessuna baseline (`poc_outputs_improved.json` o una cifra di accuratezza nota-buona) è committata da nessuna parte, e `mnt/` è in gitignore. Il team tiene un'esecuzione di riferimento da qualche parte (drive condiviso, wiki, un messaggio pinnato)? Quale delta di accuratezza conta come regressione, e lo smoke test manuale è l'unico gate di merge? Un nuovo sviluppatore oggi non può dire se la propria modifica abbia aiutato o nuociuto senza prima ricostruirsi una baseline da solo.

### Qual è il modello di branching e release sulla storia riscritta?
Il repo ha `master` e `develop` (il lavoro corrente avviene su `develop`). Dopo la riscrittura, tutti i vecchi hash (inclusi quelli citati in note, descrizioni di PR o nella memoria delle persone) sono invalidi. `develop` è il branch di integrazione con `master` come stabile? La review è richiesta prima del merge, e cosa costituisce una "release" per un POC senza versioning né CI? Inoltre: eventuali riferimenti esterni a vecchi hash di commit (ticket, documenti) sono stati riconciliati dopo il passaggio di filter-repo?

### Il contratto "canonico" rivolto al cliente è congelato, e chi lo consuma?
`extraction/canonical_mapping.py` costruisce le voci ordinate `canonical_fields` "for backend/UI/export integration", con una tassonomia fissa a 4 pagine in `extraction/page_definitions.py`; ma nessun consumatore esterno esiste nel repo, e il cliente non è mai nominato. Esiste un contratto esterno concordato (nomi di colonna, chiavi di pagina, ordinamento) a cui questi nomi visualizzati devono corrispondere esattamente? Questo determina con quanta libertà gli sviluppatori possano rinominare qualcosa in `field_definitions.py`/`page_definitions.py`, che altrimenti sembrano rifattorizzabili senza rischi.

## Debito tecnico

### Quando viene riattivata `_deduplicate_same_page_outputs()`?
La funzione è pienamente implementata in `extraction/cli.py` ma il suo punto di chiamata è commentato con "TEMP TEST: keep all outputs until page_key mapping is validated" (`extraction/cli.py:268-273`). Quella validazione si ricollega alla domanda sui binding di pagina più sopra. Cosa valida concretamente la mappatura delle page_key, e chi la riattiva? Fino ad allora, le esecuzioni batch possono portare più output per la stessa pagina canonica, il che tocca l'export canonico e può causare doppi conteggi nei confronti a valle.

### Un modello senza prezzo dovrebbe fallire rumorosamente invece di costare $0.00?
`estimate_cost_usd()` restituisce `0.0` per qualsiasi modello assente da `PRICING_PER_1M` (`extraction/vlm_client.py:21-26`). `LLM_MODEL` è testo libero via env, quindi un nome di snapshot datato (es. un ID in stile `gpt-4o-2024-11-20`) o un nuovo modello preview produce in silenzio un report a costo zero: in un progetto il cui intero scopo include la misurazione dei costi. I modelli sconosciuti dovrebbero avvisare o sollevare un'eccezione, e chi tiene i prezzi preview hardcoded (`gemini-3-flash-preview`, `gemini-3.1-flash-lite-preview`, `extraction/config.py:47-48`) allineati alla fatturazione reale?

### Si possono rimuovere `streamlit` e gli altri residui di Streamlit?
`streamlit` siede in `requirements.txt:5` senza alcun importatore; la docstring di `run_extraction_batch()` dice ancora "Shared by CLI (main) and Streamlit (app.py)" (`extraction/cli.py:296`), ed `extraction/__init__.py:3` menziona "backward compatibility with app.py". L'app Streamlit è stata cancellata da tempo; la terza UI effettiva è la `gui_app.py` Tkinter. C'è qualche ragione per non eliminare la dipendenza e correggere i due commenti in un solo commit?

### La confidenza fornita dal modello andrebbe validata o clampata?
Ogni gate del sistema (la soglia anchor 0.95, il trigger di retry 0.60, gli spareggi di `pick_best()`) si fida del float che il modello restituisce; nulla impone l'intervallo [0, 1] al di là di un'istruzione nel prompt italiano (`extraction/prompts.py:36`; fidato in `extraction/pipeline.py:91,255`, `extraction/normalization.py:94-96`, `extraction/cli.py:87-88`). Un modello che restituisse 1.5 o -0.2 distorcerebbe in silenzio la selezione dei retry e la scelta dei vincitori. Clampare al confine dello schema, o accettare il rischio per un POC?

### L'accesso cross-thread ai widget della GUI Tkinter è accettabile?
Il thread worker avviato a `gui_app.py:225-226` tocca direttamente i widget Tk: `log_area.insert`, `messagebox`, `btn_run.config` (`gui_app.py:199-201`, `:258-285`); solo `display_results` viene smistato al thread UI tramite `self.after(0, ...)` (`gui_app.py:278`). Tkinter non dà alcuna garanzia di thread-safety, quindi questo funziona sul CPython attuale ma può bloccarsi o crashare. Rischio da POC accettato, o vale la pena instradare tutti gli aggiornamenti UI attraverso `after()`?

### `window_title_contains` va implementato o cancellato?
`edge-agent/config.ini:3` imposta `window_title_contains = BPER`, `AgentConfig` lo carica e `update_from_ui()` lo scrive (`edge-agent/config.py:146-149,273-285`), e la CaptureTab lo espone; ma nessun codice di cattura filtra per titolo di finestra; la cattura è dell'intero monitor via mss. È un'impostazione che promette un comportamento che non esiste. Implementare la cattura limitata alla finestra, o rimuovere la manopola?

### Chi riconcilia `CLAUDE.md`/`README.md` con il codice?
Drift confermato: CLAUDE.md documenta guardie `if/raise` di avvio che validano `FIELD_RETRY_MAP` e un dict `_FIELD_COMPARATORS`: nessuno dei due esiste in `extraction/` (grep); CLAUDE.md dice che il passaggio anchor "zeroes out low-confidence anchors" ma il gate è inefficace (vedi la domanda in Architettura sopra); la tabella dei moduli di CLAUDE.md omette `edge-agent/ui/data_table_tab.py` (collegato in `edge-agent/ui/main_window.py`); il README apre con "18 campi" mentre `FIELD_KEYS` ne ha 45 (`extraction/fields.py:12-54`); il commento a `edge-agent/workers/capture/bper_capture_worker.py:42` dice "MobileNetV3" ma il classificatore è DINOv2 ViT-S/14 (`edge-agent/page_classifier.py:203`); `SCREENSHOT_DIR` è documentato ma non letto da nessuna parte. Dato che CLAUDE.md guida il lavoro assistito da AI, le sue guardie fantasma inducono attivamente in errore: la manutenzione della documentazione è responsabilità esplicita di qualcuno?

### Il dict risultato del percorso d'errore dovrebbe combaciare con la forma del percorso di successo?
In caso di fallimento dell'estrazione, `LocalExtractionClient.ingest_frame()` emette un risultato ridotto (`screen_id`, `fields` vuoto, `_status: "ERROR"`, `_error`) senza `_meta_agg`, `canonical_fields`, `_field_sources` né le liste tabellari (`edge-agent/local_extraction_client.py:87-94`). I consumatori UI sopravvivono grazie ad accessi difensivi `.get(..., {})`, ma qualsiasi nuovo consumatore che assuma la forma completa crasherà al primo frame fallito. Normalizzare il risultato d'errore, o dichiarare l'accesso difensivo come contratto ufficiale?

## Riferimenti incrociati

- [Architettura](04-architecture.md) per il diagramma dei componenti attorno a cui ruotano queste domande
- [Stack tecnologico](03-tech-stack.md) per i dettagli sulle dipendenze (in particolare `streamlit`, `torch`, `requests`)
- [Workflow](05-workflows.md) per le sequenze del batch, dell'edge-agent e della pipeline multi-pass
- [Per iniziare](07-getting-started.md) per i passi di setup che danno per risolte molte di queste domande
