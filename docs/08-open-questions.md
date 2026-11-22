# Domande aperte

Queste sono le cose che il codice da solo non può dirti: decisioni la cui motivazione è invisibile dal sorgente, fatti di dominio che solo chi ha usato l'applicazione BPER può confermare, e code sciolte della storia del progetto (il backend remoto rimosso, la riscrittura della storia git del 2026-07-21). Ogni domanda dichiara cosa è stato osservato e perché la risposta conta. Due di esse costeranno tempo reale a un nuovo sviluppatore fin dal primo giorno se restano senza risposta: dove vive il `dati.csv` canonico (risolta il 2026-11-22), e se la chiave OpenAI trapelata sia stata davvero ruotata.

Le domande sono ordinate, entro ciascuna sezione, per impatto sull'efficacia di un nuovo sviluppatore. Contesto correlato: [Architettura](04-architecture.md), [Workflow](05-workflows.md), [Guida alla configurazione](10-configuration-guide.md).

## Architettura

### ~~Qual è il router di pagina inteso come default, LLM o ML?~~ RISOLTA (2026-08-17)
Il file `src/edge-agent/config.ini` spedito usa `router = llm`, mentre `AgentConfig.DEFAULT_ROUTER_MODE` resta `ml` quando l’impostazione manca. Le motivazioni storiche restano negli [ADR 0005](adr/0005-router-ml-invece-di-router-llm.md) e [0006](adr/0006-router-llm-come-predefinito.md). `hybrid` prova LLM e poi ML; `local-first` ha un percorso locale per margine, ma l’inizializzazione attuale gli assegna `MLPageRouter`, senza il fallback remoto previsto nell’ADR 0008.

~~Resta aperto il sotto-problema: **serve una storia offline** per i pesi DINOv2 su rete blindata.~~ **Risolto 2026-11-22:** il pacchetto contiene repo e pesi DINOv2 ([ADR 0031](adr/0031-modello-dinov2-nel-pacchetto.md)).

### La GUI Tkinter dovrebbe passare un modello anchor accanto al modello principale?
`gui_app.py:238-247` inoltra a `run_extraction_batch()` il provider selezionato dal menu a tendina e `model_main`, ma mai `model_anchor`, quindi il passaggio anchor ricade sul `LLM_MODEL_ANCHOR` derivato dall'ambiente (default `gpt-4o`). Selezionare Gemini nella GUI mentre l'ambiente contiene i default OpenAI solleva quindi a metà esecuzione il `ValueError` di mismatch provider/modello in `src/extraction/llm_factory.py:59-63`. La GUI dovrebbe derivare il modello anchor dal provider selezionato, o il percorso Gemini del menu a tendina è notoriamente rotto?

### `preprocess_for_ocr()` è pensata per essere equivalente a `normalize_image()`?
La pipeline ha due entry point per scelta: `extract_from_screen()` normalizza internamente, mentre `extract_from_image()` si fida del chiamante (`src/extraction/pipeline.py:104-187`; commento con la motivazione a `src/edge-agent/local_extraction_client.py:84-85`). La `preprocess_for_ocr()` dell'edge-agent (`src/edge-agent/image_ops.py`) fa upscale adattivo + unsharp + autocontrasto: una trasformazione diversa dalla `normalize_image()` di `src/extraction/imaging.py`. Le due devono produrre input scalati/nitidi in modo comparabile (così che i numeri di accuratezza siano confrontabili tra CLI e cattura dal vivo), o la divergenza è accettata? Qualsiasi futuro chiamante che passi un'immagine grezza a `extract_from_image()` salta in silenzio ogni normalizzazione, spigolo noto o bug latente?

### Qual è il destino del percorso remoto/generico e dei suoi residui di config?
`DefaultCaptureWorker` fa ancora POST di frame grezzi verso `{api.base_url}/jobs/{job_id}/frames` (`src/edge-agent/workers/capture/default_capture_worker.py`), ma nessun backend del genere esiste in questo repo e `config.ini` lo punta a `http://localhost:8081`. Le sezioni `[minio]` e `[dataset]` sopravvivono in `src/edge-agent/config.ini:12-16,25-29` mentre l'upload del dataset è un no-op esplicito ("disabilitata per consolidamento locale", `src/edge-agent/workers/capture/bper_capture_worker.py:713-715`). La modalità di cattura "Generico" e la sua config sono peso morto da eliminare, o è previsto il ritorno di un backend di ingestione remota? La risposta decide se rimuovere `requests`, le sezioni `[api]`/`[minio]` e `DefaultCaptureWorker`.

### La triplice diramazione Gemini è stata validata su ogni modello elencato?
`src/extraction/vlm_client.py` sceglie tra tre strategie di output strutturato per sottostringa: `_GEMINI_JSON_SCHEMA_MODELS = ("gemini-1.5",)` (riga 18) instrada i modelli 1.5 verso json_mode con `response_schema`, e tutto il resto di Gemini va in JSON a forma libera + validazione Pydantic manuale, perché (a quanto riportato) gli schemi complessi provocano `INVALID_ARGUMENT` su 2.0+/3.x. Questo è stato verificato per tutti i modelli di `PROVIDER_MODELS["gemini"]` (`src/extraction/config.py:24-32`), inclusi `gemini-3-flash-preview` e `gemini-3.1-flash-lite-preview`, o solo per uno o due? Un futuro nome di modello che non combacia con la sottostringa prende di default il ramo a forma libera. È quello il fallback sicuro inteso?

## Logica di business

### Dove vive il `dati.csv` canonico, e chi ne è il proprietario?
**Risolta 2026-11-22.** I 77 valori della pratica di riferimento sono stati verificati contro le schermate il 2026-11-07 e stanno in `data/revisione/riferimento-2025-09-09/dati.csv`; la CLI legge i valori corretti di ogni pratica da `data/pratiche/pratiche.xlsx` (ADR 0029). Il resto della sezione è la domanda com'era.

**Aggiornamento 2026-09-29.** Il `dati.csv` ancora presente nella storia git (rimosso in `e8c677c`) descrive 5 screenshot della vecchia interfaccia PEF, non i 9 attuali: non va ripristinato. Per i 9 screenshot attuali esiste una bozza di 77 righe, trascritta a vista e da verificare, copiata in `.tritech/codebase-xray/baselines/2026-09-29-gemini-3.8-flash/dati.csv` (oggi solo nella storia git, `d939ea5`).

La CLI lo richiede tassativamente (`FileNotFoundError` a `src/extraction/cli.py::main`), il README ne documenta il formato (`README.md:221-241`) e l'intero apparato di valutazione è costruito attorno a esso; eppure il file non esiste né nel working tree né in alcun punto di git (`.gitignore:9` esclude `/data`; solo i 9 PNG sono stati aggiunti con force-add). Esiste una copia autorevole (quante righe, quali campi per schermata) e può essere condivisa con ogni sviluppatore? Senza un file di GT comune, `python main.py` non può girare su un clone fresco e i numeri di accuratezza di due sviluppatori non sono confrontabili.

### Le sovrascritture del controllo di coerenza sono regole BPER universalmente valide?
`_coherence_check()` (`src/extraction/pipeline.py:378`) riscrive in silenzio l'output del modello: se `tooltip_evidenze_b` ha un valore ed `evidenze` è nullo o puramente numerico, `evidenze` diventa `"B"`; se `tooltip_descrizione_bmb` ha un valore e `tipo` è null, `tipo` diventa `"BMB"`. Questi valori sintetizzati non sono segnalati in `_field_sources`, quindi a valle sembrano estrazioni pulite. Queste implicazioni valgono per tutte le pratiche BPER, o solo per le 9 schermate campione su cui sono state tarate? Una regola sbagliata qui produce output sbagliato con sicurezza, che la valutazione potrebbe classificare come OK.

### `TIPO_MAPPING` è l'insieme completo dei sinonimi dei tipi di pratica?
`src/extraction/normalization.py:10-14` canonicalizza esattamente tre varianti minuscole (`mutui spesa`, `mutuo spesa`, `bpi mutui`) in `"BPI Mutui"`. È l'insieme completo delle grafie di `tipo` che la UI BPER può mostrare, o solo ciò che è comparso nei dati campione? Qualsiasi variante non elencata passa non mappata e viene valutata WRONG contro la GT: invisibile finché qualcuno non ispeziona il CSV di debug.

### ~~I binding di pagina canonica dei campi scheda-privati sono intenzionali?~~ RISOLTA
I tredici campi usano ora la pagina sorgente `scheda_privati`. Il gruppo di export esplicito resta `note_da_richiesta`, con le stesse 45 colonne e quattro bande. Il risolutore condiviso distingue i due contratti; vedi [ADR 0020](adr/0020-pagina-sorgente-separata-dal-gruppo-export.md).

### ~~L'appiattimento dei soggetti sovrascrive intenzionalmente i vincitori dei retry?~~ RISOLTA
L'[ADR 0018](adr/0018-appiattimento-soggetti-con-merge-e-provenienza.md) applica `pick_best()` anche ai candidati tabellari: il non nullo prevale sul nullo, poi conta la confidenza, con il corrente vincente a parità. La provenienza cambia solo quando vince il candidato tabellare e segue l'origine della tabella accettata. Restano i limiti diagnostici descritti nel [modello dei dati](06-data-model.md#pattern-di-flusso-dei-dati).

### ~~Perché `creazione` e i cinque campi `tooltip_*` sono esclusi da ogni area di retry?~~ RISOLTA
`creazione` appartiene ora a HEADER, nel mapping e nel prompt di retry. I cinque tooltip restano una scelta esplicita in `UNRETRIED_FIELDS`: sono sovrapposizioni transitorie senza un ritaglio fisso affidabile e li legge il main. `tests/test_domain_vocabulary.py` verifica che ogni campo abbia esattamente una politica di retry. Un tooltip non letto può ancora impedire una riparazione di coerenza; l'esclusione non garantisce che il main lo riconosca.

## Infrastruttura

### La chiave OpenAI trapelata è stata ruotata su OpenAI?
Una chiave API OpenAI era stata committata in `src/edge-agent/config.ini`. Il 2026-07-21 è stata ripulita dall'intera storia git (`git filter-repo`, force-push su origin); la riga ora è vuota. Ripulire la storia non "de-trapela" un segreto: chiunque abbia mai clonato o fatto fetch del repo potrebbe avere ancora la chiave. È stata revocata/ruotata nella dashboard OpenAI, e l'utilizzo su quella chiave è stato verificato? Finché non c'è conferma, trattala come un incidente di sicurezza aperto, non come pulizia conclusa.

### Tutti i collaboratori hanno ri-clonato dopo la riscrittura della storia?
Poiché la riscrittura ha cambiato ogni hash di commit, qualsiasi clone precedente al 2026-07-21 è incompatibile con origin, e un push o un merge da un clone stantio **reintrodurrebbe la chiave trapelata** nella storia. Ogni collaboratore (e ogni runner CI, bot o mirror, se esistono) ha ri-clonato o fatto hard-reset sulla nuova origin? C'è una checklist che confermi che non restano fork stantii?

### Dove dovrebbero vivere i segreti dell'edge-agent da qui in avanti?
Anche dopo la ripulitura, il design che ha causato la fuga è intatto: `[llm] api_key` è un campo in un file **tracciato**, il router lo preferisce alle variabili d'ambiente (risoluzione consapevole del provider in `AgentConfig.resolve_llm_settings()`, `src/edge-agent/config.py`), e `AgentConfig.save()` riscrive `llm_api_key` dentro `config.ini` (`src/edge-agent/config.py:326-332`), attualmente non chiamato, ma a un solo collegamento UI di distanza dal ri-persistere un segreto. La prassi è già lasciare la chiave nella `.env`, e `build_exe.bat` rifiuta un INI con chiave valorizzata. Conviene rendere questa separazione obbligatoria anche a runtime? `save()` dovrebbe smettere di serializzarla? E `config.ini` dovrebbe acquisire uno split `config.ini.example` come `.env`/`.env.example`? Una decisione qui previene la ripetizione dell'incidente.

### Quali requisiti deve soddisfare la distribuzione portable?
Esistono `build_exe.bat` e `edge_agent.spec`: generano `dist/EdgeAgent` e uno ZIP datato, con configurazione e prompt modificabili e bootstrap al primo avvio. `pyproject.toml` configura soltanto pytest e `tools/check.py` offre il check rapido; mancano ancora lockfile e CI. Quali ambienti dell’operatore sono supportati, come si convalidano gli aggiornamenti e come si distribuiscono i pesi DINOv2 nelle reti senza accesso esterno?

## Processo

### Dove vive la baseline di accuratezza e costo con provider reali?
**Parzialmente risolta (2026-09-29).** La prima baseline (`gemini-3.8-flash`, tre run, 93,5-94,8%) e la soglia proposta sono nella storia git (`git show d939ea5:.tritech/codebase-xray/baselines/2026-09-29-gemini-3.8-flash/README.md`). Restano aperte la verifica umana del ground truth, l'approvazione della soglia e una baseline su più pratiche.

La suite `tests/` è eseguibile con `python -m pytest tests`. Copre anche i contratti di ordinamento, esito della cattura e scatto manuale. Non sostituisce però una baseline condivisa dei risultati VLM sulle schermate reali: `data/` è ignorata e il CSV di ground truth non è nel repository. Dove si conserva tale baseline, quale variazione di accuratezza è accettabile e chi approva lo smoke test del provider e della GUI?

### Qual è il modello di branching e release sulla storia riscritta?
Il repo ha `master` e `develop` (il lavoro corrente avviene su `develop`). Dopo la riscrittura, tutti i vecchi hash (inclusi quelli citati in note, descrizioni di PR o nella memoria delle persone) sono invalidi. `develop` è il branch di integrazione con `master` come stabile? La review è richiesta prima del merge, e cosa costituisce una "release" per un POC senza versioning né CI? Inoltre: eventuali riferimenti esterni a vecchi hash di commit (ticket, documenti) sono stati riconciliati dopo il passaggio di filter-repo?

### Il contratto "canonico" rivolto al cliente è congelato, e chi lo consuma?
`src/extraction/canonical_mapping.py` costruisce le voci ordinate `canonical_fields` "for backend/UI/export integration", con cinque pagine sorgenti e quattro gruppi di export in `src/extraction/page_definitions.py`; ma nessun consumatore esterno esiste nel repo, e il cliente non è mai nominato. Esiste un contratto esterno concordato (nomi di colonna, chiavi di pagina, ordinamento) a cui questi nomi visualizzati devono corrispondere esattamente? Questo determina con quanta libertà gli sviluppatori possano rinominare qualcosa in `field_definitions.py`/`page_definitions.py`, che altrimenti sembrano rifattorizzabili senza rischi.

## Debito tecnico

### ~~Quando viene riattivata `_deduplicate_same_page_outputs()`?~~ RISOLTA
Il ramo mai chiamato e i suoi helper sono stati rimossi. Il batch conserva ogni schermata elaborata; la sola pagina canonica non identifica una pratica e non autorizza a scartare schermate diverse. Il consolidamento delle pratiche live resta una responsabilità separata.

### Un modello senza prezzo dovrebbe fallire rumorosamente invece di costare $0.00?
`estimate_cost_usd()` restituisce `0.0` per qualsiasi modello assente da `PRICING_PER_1M` (`src/extraction/vlm_client.py:21-26`). `LLM_MODEL` è testo libero via env, quindi un nome di snapshot datato (es. un ID in stile `gpt-4o-2024-11-20`) o un nuovo modello preview produce in silenzio un report a costo zero: in un progetto il cui intero scopo include la misurazione dei costi. I modelli sconosciuti dovrebbero avvisare o sollevare un'eccezione, e chi tiene i prezzi preview hardcoded (`gemini-3-flash-preview`, `gemini-3.1-flash-lite-preview`, `src/extraction/config.py:47-48`) allineati alla fatturazione reale?

### L'accesso cross-thread ai widget della GUI Tkinter è accettabile?
Il thread worker avviato a `gui_app.py:225-226` tocca direttamente i widget Tk: `log_area.insert`, `messagebox`, `btn_run.config` (`gui_app.py:199-201`, `:258-285`); solo `display_results` viene smistato al thread UI tramite `self.after(0, ...)` (`gui_app.py:278`). Tkinter non dà alcuna garanzia di thread-safety, quindi questo funziona sul CPython attuale ma può bloccarsi o crashare. Rischio da POC accettato, o vale la pena instradare tutti gli aggiornamenti UI attraverso `after()`?

### ~~`window_title_contains` va implementato o cancellato?~~ RISOLTA (2026-08-17)
**Implementato.** `frame_normalize.find_window_rect()` cerca la prima finestra visibile il cui titolo contiene la sottostringa e `_grab_raw()` ritaglia il frame su quel rettangolo. La manopola non promette più un comportamento inesistente. Non è stata implementata come *cattura* limitata alla finestra (`mss` continua a prendere il monitor) ma come *ritaglio* successivo, perché serviva anche un ripiego per quando il titolo non corrisponde. Dettagli e limiti in [ADR 0001](adr/0001-normalizzazione-inquadratura-frame.md).

La domanda si è rivelata più importante di come era posta: non era una manopola cosmetica, era il pezzo mancante che faceva riconoscere 1 pagina su 9 in esercizio.

### ~~La mappa campo → pagina in `field_definitions.py` è sbagliata: va corretta o abbandonata?~~ PARZIALMENTE RISOLTA
Il mapping dei tredici campi privati ora indica `scheda_privati`; il gruppo di export conserva il layout precedente ([ADR 0020](adr/0020-pagina-sorgente-separata-dal-gruppo-export.md)). Resta da progettare un gate dei retry basato su una pagina riconosciuta in modo affidabile in tutti gli ingressi: questa correzione non lo attiva. Il filtro dei soggetti descrive una difesa distinta e limitata alle tabelle vuote ([ADR 0019](adr/0019-filtro-soggetti-da-retry-su-tabella-vuota.md)).

### Chi mantiene allineata la guida alle modifiche di comportamento?
Chi aggiorna istruzioni, API e ADR quando cambia il comportamento del codice?

### Servirà una forma unica per risultati riusciti e falliti?
Il contratto attuale è documentato nelle [API Python](12-python-api.md): `LocalExtractionClient._process_frame()` produce un risultato `ERROR` ridotto, con `fields` vuoto, `_error`, metadati pagina e `_capture_sequence`. Lo slot errore avanza comunque il prefisso ordinato; i consumatori devono usare accessi difensivi per i dati opzionali. Un eventuale consumatore esterno richiederà uno schema uniforme per successi ed errori?

## Riferimenti incrociati

- [Architettura](04-architecture.md) per il diagramma dei componenti attorno a cui ruotano queste domande
- [Stack tecnologico](03-tech-stack.md) per i dettagli sulle dipendenze (in particolare `torch`, `requests` e PyInstaller)
- [Workflow](05-workflows.md) per le sequenze del batch, dell'edge-agent e della pipeline multi-pass
- [Per iniziare](07-getting-started.md) per i passi di setup che danno per risolte molte di queste domande
