# Per iniziare

Questo è un proof-of-concept Python che estrae campi strutturati da screenshot bancari BPER italiani con una pipeline Vision-LLM multi-pass. Prima di toccare il codice, interiorizza tre fatti. Primo, tutta la logica di business vive in un unico package senza UI, `extraction/`; la CLI (`main.py`), la GUI Tkinter (`gui_app.py`) e l'edge-agent PyQt6 (`edge-agent/`) sono front-end sottili sopra di esso. Secondo, non ci sono test, CI né Docker: le modifiche si verificano eseguendo la pipeline e confrontando i numeri di accuratezza e costo che stampa. Terzo, ogni esecuzione chiama un'API LLM a pagamento; non esiste modalità offline o mock, quindi ti serve una chiave OpenAI (o Gemini) con credito fin dal primo minuto.

Due cose ti bloccheranno il primo giorno se non le conosci: il file di ground truth `mnt/data/dati.csv` **non è nel repository** (la CLI si rifiuta di partire senza, `extraction/cli.py:315-316`), e la storia git è stata **riscritta il 2026-07-21** per ripulire una chiave API trapelata: se hai clonato prima di quella data, ri-clona prima di fare qualsiasi altra cosa. Entrambe sono coperte in [Trabocchetti](#trabocchetti) e in [Domande aperte](08-open-questions.md).

Leggi questo documento insieme ad [Architettura](04-architecture.md), [Stack tecnologico](03-tech-stack.md) e [Workflow](05-workflows.md).

## Prerequisiti

- **Python 3.13** (3.12 accettabile). La documentazione dichiara 3.8+ (`README.md` riga 3), ma il launcher Windows sonda deliberatamente `py -3.13`, poi `py -3.12`, ed evita gli interpreti più recenti privi di wheel per torch (`run_edge_agent.bat:44-58`). La 3.13 è il runtime noto-buono sulla macchina di sviluppo.
- **Una chiave API LLM con credito.** OpenAI di default; Gemini come provider alternativo. Senza chiave, la costruzione del modello solleva `ValueError: API key required` (`extraction/llm_factory.py:41-44`): scatta all'avvio sia per il batch runner della CLI sia per il `LocalExtractionClient` dell'edge-agent.
- **`mnt/data/dati.csv`**: richiesto solo per il percorso di valutazione della CLI. È assente sia dal working tree sia da git (`.gitignore:9` ignora `/mnt`; solo i 9 PNG sono stati aggiunti con force-add). Richiedi il file canonico al team: vedi [Domande aperte](08-open-questions.md#logica-di-business).
- **(Opzionale) Una macchina in grado di far girare torch/torchvision** per il router di pagina ML. La config spedita usa `router = llm`, che riconosce le pagine leggendone il testo e non richiede torch. Serve solo passando a `router = ml` o `hybrid`; senza torch il classificatore si disabilita con grazia (`edge-agent/page_classifier.py:9-19`).
- **(Opzionale) Un monitor che mostri l'applicazione BPER** per la cattura dal vivo. L'edge-agent cattura un intero monitor per indice (`monitor_index = 1` in `edge-agent/config.ini`), non una finestra.

Nota di piattaforma: lo sviluppo avviene su Windows 11. La pipeline di estrazione in sé è indipendente dalla piattaforma; l'unica dipendenza condizionale è `pyscreenshot`, marcata solo-Linux in `requirements.txt:10`. I comandi qui sotto sono PowerShell-first, con l'equivalente bash dove la sintassi differisce.

## Setup

### 0. Se hai clonato prima del 2026-07-21: ri-clona

L'intera storia git è stata riscritta con `git filter-repo` e force-pushata per ripulire una chiave OpenAI trapelata da `edge-agent/config.ini`. Tutti gli hash dei commit sono cambiati. Un clone stantio non riuscirà a pushare in modo pulito, e, peggio, un push da lì **reintrodurrebbe la chiave trapelata nella storia**. Non mergiare e non pushare da un vecchio clone; riparti da zero:

```powershell
git clone <origin-url> poc-data-extraction
cd poc-data-extraction
```

### 1. Percorso rapido (Windows): il launcher fa tutto

```powershell
.\run_edge_agent.bat
```

Crea `.venv` con Python 3.13 (o 3.12), installa `requirements.txt` (torch è grande, la prima esecuzione richiede diversi minuti) e lancia l'edge-agent. Auto-ripara anche un venv rotto il cui interprete base è stato spostato o disinstallato (`run_edge_agent.bat:19-29`). Eventuali argomenti vengono inoltrati all'app, per esempio `.\run_edge_agent.bat --debug`.

### 2. Percorso manuale (tutte le piattaforme)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Un solo `requirements.txt` copre tutto: core di estrazione ed edge-agent. Nota che `streamlit` (`requirements.txt:5`) è orfano: il vecchio `app.py` Streamlit è stato cancellato e nulla lo importa.

### 3. Crea il tuo `.env`

```powershell
copy .env.example .env
```

```bash
cp .env.example .env
```

Apri `.env` e imposta come minimo:

```
LLM_API_KEY=<la tua chiave>
```

Tutti e tre gli entry point auto-caricano `.env` via `python-dotenv` (`main.py:7`, `edge-agent/edge_agent.py:9-13`, `edge-agent/local_extraction_client.py:21-25`), quindi per un'esecuzione normale non devi mai esportare variabili nella shell. Il template ha come default `LLM_PROVIDER=openai` e `LLM_MODEL=gpt-4o`.

Per Gemini invece:

```
LLM_PROVIDER=gemini
LLM_API_KEY=<la tua chiave Gemini>
LLM_MODEL=gemini-1.5-flash
```

La factory rifiuta le coppie disallineate: un modello `gemini-*` con `LLM_PROVIDER=openai` (o `gpt-*` con `gemini`) solleva `ValueError` (`extraction/llm_factory.py:49-63`).

### 4. Fornisci il CSV di ground truth (solo CLI)

Colloca `dati.csv` in `mnt/data/` usando il formato long documentato in `README.md` righe 221-241:

```
Fotogramma,Denominazione da attribuire,Valore rilevato
screen 1,NDG,31943680
screen 1,DENOMINAZIONE,"TICCHI SERENA, CABRAS LUCA"
screen 1,Tipo,BPI Mutui
```

Il loader tollera nomi di colonna alternativi (`Screenshot`/`Screen`, `Campo`/`Field`, `Valore`/`Value`, `_find_column()` in `extraction/evaluation.py`). La GUI Tkinter e l'edge-agent funzionano **senza** questo file; solo `python main.py` lo richiede tassativamente.

### 5. Esegui

```powershell
python main.py                            # batch CLI su ogni immagine in mnt/data/
python gui_app.py                         # GUI desktop Tkinter (scegli i file a mano)
python main.py --gui                      # edge-agent (PyQt6) con cattura dal vivo
python edge-agent/edge_agent.py           # edge-agent, lanciato direttamente
python edge-agent/edge_agent.py --debug   # edge-agent + tab Debug del router LLM
```

`main.py --gui` si limita a inserire `edge-agent/` in `sys.path` e a chiamare `edge_agent.main()` (`main.py:15-20`). Il flag `--debug` sblocca la tab Debug LLM (`edge-agent/edge_agent.py:51`), che richiede in aggiunta `show_llm_tab = true` nella sezione `[debug]` di `edge-agent/config.ini`.

## File chiave da leggere per primi

Ordinati per valore di apprendimento: dal contratto dati verso l'orchestrazione e la UI.

1. **`extraction/fields.py`**: `FIELD_KEYS` (45 chiavi, righe 12-54) è l'unica fonte di verità per tutto ciò che il sistema estrae. Lo schema Pydantic, la mappatura CSV, le metriche e la mappa di retry si agganciano tutti a questa lista; leggila per prima e il vocabolario di dominio (`ndg`, `fido`, `professione_principale`) smette di essere rumore.
2. **`extraction/schemas.py`**: Il contratto di output dell'LLM: `FieldResult` (value/confidence/evidence/section), `Soggetto`, `Fido`, `Garanzia`, `ExtractionResponse`, `AnchorResponse`. `FieldsModel` è generato dinamicamente da `FIELD_KEYS`, motivo per cui `fields.py` viene prima.
3. **`extraction/pipeline.py`**: `ExtractionPipeline`, il cuore del sistema: passaggio anchor → passaggio principale → retry condizionali per area → controllo di coerenza → appiattimento dei soggetti. Se leggi un solo file, leggi questo; nota i due entry point `extract_from_screen()` (CLI/Tkinter) ed `extract_from_image()` (edge-agent, normalizzazione bypassata di proposito).
4. **`extraction/config.py`**: Ogni manopola regolabile: config da variabili d'ambiente, coordinate di ritaglio (`CONTENT_CROP`, `HEADER_IN_CONTENT`, `RETRY_AREAS`), la mappa campo-area di retry (`AREA_TO_FIELDS`) e la tabella dei prezzi (`PRICING_PER_1M`). Le variabili d'ambiente vengono lette **al momento dell'import** (`os.getenv` a livello di modulo), il che conta: vedi Trabocchetti.
5. **`extraction/cli.py`**: `BatchRunner` e `run_extraction_batch()`, il motore batch condiviso usato sia dalla CLI sia dalla GUI Tkinter. Mostra il modello di threading: ChatModel creati una volta, condivisi sul `ThreadPoolExecutor`. `main()` alla riga 314 è il flusso CLI end-to-end.
6. **`extraction/vlm_client.py`**: Le chiamate LLM di basso livello e le strategie di output strutturato per provider (`.with_structured_output()` per OpenAI, json_mode per Gemini 1.5, JSON in forma libera + validazione manuale per Gemini 2.0+/3.x, discriminati da `_GEMINI_JSON_SCHEMA_MODELS` alla riga 18). È anche dove viene popolato il tracciamento dei costi `_meta`.
7. **`extraction/evaluation.py`**: `load_ground_truth()`, `eval_outputs()` e la classificazione OK / WRONG / MISSING / HALLUCINATED / OK_NULL; spiega la separazione tra metriche RAW e FILTERED guidata da `dataset_mismatch_guard()`.
8. **`edge-agent/local_extraction_client.py`**: Corto e portante: il ponte QObject tra la UI PyQt6 e `ExtractionPipeline`, la giuntura `ingest_frame()` e il segnale `result_ready` che riattraversa il confine verso il thread della UI.
9. **`edge-agent/workers/capture/bper_capture_worker.py`**: Il loop di cattura: screenshot mss, `preprocess_for_ocr()`, deduplica pHash, routing di pagina, gate di stabilità di 2 secondi, poi la chiamata sincrona a `ingest_frame()` (riga 696). Il file più grande di `edge-agent/`; leggilo per ultimo, quando la pipeline è chiara.

## Dove si trovano le cose

| Per fare questo… | Guarda qui |
|---|---|
| Aggiungere o rinominare un campo estratto | `extraction/fields.py` (`FIELD_KEYS`, `CSV_TO_SCHEMA`), poi `extraction/field_definitions.py` (`CANONICAL_FIELD_DEFINITIONS`, `FIELD_LABEL_ALIASES`) ed `extraction/config.py` (`AREA_TO_FIELDS`) |
| Cambiare cosa viene chiesto al VLM | `prompts/*.json` (`extraction_main`, `extraction_anchor`, `extraction_retry_*`) - in italiano per scelta, caricati da `prompt_store.py`; se aggiungi un `{placeholder}` aggiorna anche `CATALOG` |
| Regolare le regioni di ritaglio | `extraction/config.py` (`CONTENT_CROP`, `HEADER_IN_CONTENT`, `RETRY_AREAS`) |
| Aggiungere un modello o correggere i prezzi | `extraction/config.py` (`PROVIDER_MODELS`, `PRICING_PER_1M`) |
| Cambiare la selezione provider/chiave | `extraction/llm_factory.py` (`create_chat_model()`) - l'unica factory LLM |
| Regolare la logica multi-pass (gate, tetti di retry) | `extraction/pipeline.py` + le variabili d'ambiente `ANCHOR_CONF_MIN`, `MAX_CALLS_PER_SCREEN`, `STOP_ON_ANCHOR_UNCERTAIN` |
| Cambiare la valutazione o il caricamento della GT | `extraction/normalization.py` (`classify_field`, `pick_best`, `dataset_mismatch_guard`) ed `extraction/evaluation.py` |
| Cambiare il flusso batch | `extraction/cli.py` - non re-implementare il suo threading altrove; CLI e Tkinter usano entrambe `run_extraction_batch()` |
| Modificare la UI desktop Tkinter | `gui_app.py` (file unico) |
| Modificare la UI dell'edge-agent | `edge-agent/ui/` (`main_window.py`, `capture_tab.py`, `extraction_results_tab.py`, `data_table_tab.py`, `debug_tab.py`, `overlay.py`) |
| Cambiare il comportamento di cattura (FPS, dedup, stabilità, monitor) | `edge-agent/workers/capture/bper_capture_worker.py` + `edge-agent/config.ini` |
| Cambiare il riconoscimento pagina | `edge-agent/llm_router.py`, `edge-agent/page_classifier.py`; modalità via `router =` in `edge-agent/config.ini`; definizioni delle pagine in `edge-agent/assets/templates/bper/prompts.json` |
| Configurare l'edge-agent | `edge-agent/config.ini` - **non** le variabili d'ambiente (solo la chiave del router ricade sull'env) |

## Attività comuni

### Eseguire un'estrazione completa e valutarla (CLI)

```powershell
python main.py
```

Elabora ogni `.png`/`.jpg`/`.jpeg` in `INPUT_DIR` (`extraction/cli.py:322-327`), poi:

- scrive `mnt/data/poc_outputs_improved.json` (risultati completi per schermata, `extraction/cli.py:337`);
- stampa l'accuratezza RAW e FILTERED con il dettaglio per campo;
- scrive `mnt/data/poc_debug_improved.csv`: separatore punto e virgola, `utf-8-sig` (amichevole per Excel, `extraction/evaluation.py:172-176`);
- stampa chiamate/token/USD per schermata via `print_cost_summary()`.

Non c'è alcuna baseline committata, quindi "la mia modifica ha aiutato?" significa confrontare questi numeri con un'esecuzione che hai salvato tu stesso prima di cambiare qualsiasi cosa. Salva prima il JSON precedente e il riepilogo stampato.

### Estrarre qualche immagine senza ground truth (Tkinter)

```powershell
python gui_app.py
```

Il campo della chiave API si pre-compila da `LLM_API_KEY` (o dalla legacy `OPENAI_API_KEY`, `gui_app.py:24`); scegli provider/modello dai menu a tendina, seleziona le immagini, opzionalmente un CSV di GT, ed esegui. Gli output finiscono nella directory corrente: `poc_outputs_gui.json`, `poc_results_gui.csv` e (se è stato indicato un CSV di GT) `poc_debug_gui.csv` (`gui_app.py:250-273`).

### Smoke test della cattura dal vivo (edge-agent)

```powershell
.\run_edge_agent.bat --debug
```

Nella tab *Cattura*, scegli la modalità BPER e premi *Avvia*. Ogni frame viene catturato a schermo intero, riportato sulla finestra applicativa (`frame_normalize.normalize_frame()`), preprocessato, deduplicato via pHash, instradato verso un tipo di pagina (router LLM di default, `router = llm` in `edge-agent/config.ini`), tenuto in una finestra di stabilità di 2 secondi, poi estratto localmente via `ingest_frame()`. Verifica che i risultati compaiano nell'albero *Risultati* e nel foglio *Dati Estratti*. Usa *Acquisisci ora* per forzare la cattura di una pagina selezionata manualmente. La tab Debug LLM (con `--debug`) mostra il prompt/risposta grezzo del router: il primo posto dove guardare quando le pagine non vengono riconosciute.

### Aggiungere un nuovo campo

`FIELD_KEYS` si dirama ampiamente; un nuovo campo tocca quattro o cinque file:

1. Aggiungi la chiave a `FIELD_KEYS` in `extraction/fields.py`: il `FieldsModel` Pydantic si rigenera automaticamente da lì.
2. Mappa l'etichetta del CSV di ground truth in `CSV_TO_SCHEMA` (`extraction/fields.py`).
3. Aggiungi `display_name` + `page_key` in `CANONICAL_FIELD_DEFINITIONS` e l'alias in `FIELD_LABEL_ALIASES` (`extraction/field_definitions.py`), così l'export canonico e il raggruppamento per pagina della UI lo intercettano.
4. Assegnalo a un'area di retry in `AREA_TO_FIELDS` (`extraction/config.py:69-82`) se va ritentato quando è nullo o a bassa confidenza.
5. Descrivilo nel prompt italiano (`prompts/extraction_main.json`), così il modello sa di doverlo cercare.

### Fare debug di un'estrazione sbagliata

```powershell
$env:DEBUG_MODE = "1"
$env:DEBUG_SAVE_CROPS = "1"
python main.py
```

`DEBUG_MODE` attiva il logging batch verboso (`extraction/config.py:92`; nota che manca da `.env.example`), e `DEBUG_SAVE_CROPS` scarica ogni ritaglio intermedio in `mnt/data/debug_crops/` (`extraction/config.py:93-94`). Vedere esattamente quale ritaglio è andato al modello è il modo più rapido per diagnosticare un campo sbagliato. Incrocia con `_field_sources` nel JSON di output per scoprire quale passaggio (ANCHOR_HEADER / CONTENT_MAIN / RETRY_*) ha prodotto il valore finale.

### "Deploy" - compilare l'eseguibile Windows

L'unico percorso di packaging è una build PyInstaller dell'app Tkinter (`README.md:78-100`):

```powershell
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name "AI_Data_Extractor" --add-data "extraction;extraction" --collect-all langchain_google_genai --collect-all langchain_openai gui_app.py
```

Output: `dist/AI_Data_Extractor.exe`. I flag `--collect-all` sono portanti: i package provider di LangChain usano import dinamici che PyInstaller altrimenti perde. Non esiste distribuzione pacchettizzata per l'edge-agent; `run_edge_agent.bat` è il suo unico launcher.

## Trabocchetti

- **La CLI muore subito senza `mnt/data/dati.csv`.** Garantito su un clone fresco: `/mnt` è in gitignore (`.gitignore:9`) e solo i 9 screenshot sono stati aggiunti con force-add, quindi `python main.py` solleva `FileNotFoundError: Ground truth CSV not found: mnt/data/dati.csv` (`extraction/cli.py:315-316`). Procurati il file dal team prima di tentare un'esecuzione CLI; le due GUI funzionano senza.

- **La storia git è stata riscritta il 2026-07-21: i cloni stantii sono pericolosi.** Una chiave OpenAI era stata committata in `edge-agent/config.ini`; è stata ripulita dall'intera storia con `git filter-repo` e force-pushata. Ogni hash di commit è cambiato. Se il tuo clone precede la riscrittura, ri-clona (o fai hard-reset sulla nuova origin): un push o un merge da un clone stantio rimetterebbe la chiave trapelata nella storia.

- **Mai mettere una chiave reale in `edge-agent/config.ini`.** La riga `[llm] api_key` è in un file tracciato e ora è **vuota**. La ricerca della chiave del router preferisce il valore INI rispetto all'ambiente ed è consapevole del provider (`AgentConfig.resolve_llm_settings()`): per `gemini` ricade su `GEMINI_API_KEY` → `GOOGLE_API_KEY` → `LLM_API_KEY`, per `openai` su `OPENAI_API_KEY` → `LLM_API_KEY`. Il pattern sicuro è: lascia la riga vuota nell'INI e imposta la chiave in `.env`. Qualunque valore che inizi per `REDACTED` viene trattato come vuoto, perché un placeholder rimasto in giro aveva già oscurato le chiavi da ambiente rompendo il router in silenzio. Trappola aggiuntiva: `AgentConfig.save()` scrive `llm_api_key` di nuovo dentro `config.ini` (`edge-agent/config.py:326-332`); al momento nulla chiama `save()`, ma collegarlo a un pulsante della UI ri-persisterebbe segreti in un file tracciato.

- **Ogni esecuzione spende denaro, e i modelli sconosciuti riportano $0.00.** Per schermata: 1 chiamata anchor + 1 chiamata principale + fino a `MAX_CALLS_PER_SCREEN - 2` retry, uno per area debole (`extraction/pipeline.py:261`), in parallelo tra le schermate. Il default di `MAX_CALLS_PER_SCREEN` è derivato da `2 + len(AREA_TO_FIELDS)` (= 5), quindi il caso peggiore è 5 chiamate. `estimate_cost_usd()` restituisce `0.0` per qualsiasi modello assente da `PRICING_PER_1M` (`extraction/vlm_client.py:21-26`): dato che `LLM_MODEL` è testo libero, un nome di modello sbagliato o datato (es. `gpt-4o-2024-11-20`) azzera in silenzio il report dei costi invece di fallire.

- **Le variabili d'ambiente vengono lette al momento dell'import.** `extraction/config.py` valuta ogni `os.getenv()` all'import del modulo. Gli entry point caricano `.env` prima di importare `extraction`, quindi le esecuzioni normali vanno bene, ma in una REPL o in un notebook imposta le variabili d'ambiente *prima* di `import extraction`, o le tue modifiche vengono ignorate.

- **L'edge-agent si configura via INI, non via env.** FPS, modalità router, indice del monitor, soglia di dedup: tutto da `edge-agent/config.ini`. Modificare `.env` cambia solo l'LLM di estrazione e il fallback della chiave del router.

- **La cattura è dell'intero monitor, ma il frame viene ritagliato sulla finestra.** `_grab_raw()` prende il monitor via `mss`, poi `frame_normalize.normalize_frame()` lo riporta sulla finestra applicativa: prima cercando il titolo che contiene `window_title_contains` (`config.ini`), poi deducendo il rettangolo dallo sfondo del desktop, altrimenti lasciando il frame com'è. Non è un dettaglio cosmetico: ogni ritaglio a valle (ROI del classificatore, bande `RETRY_AREAS` della pipeline) è una frazione tarata su screenshot di finestra, e su un monitor intero cade altrove. Senza il ritaglio il riconoscimento pagina passa da 9 corrette su 9 a 1 su 9 ([ADR 0001](adr/0001-normalizzazione-inquadratura-frame.md)).

- **`CLAUDE.md` e `README.md` derivano rispetto al codice: fidati del codice.** Drift noto: CLAUDE.md descrive guardie `if/raise` di avvio e un dict `_FIELD_COMPARATORS` che non esistono in `extraction/`; il README dice "18 campi" ma `FIELD_KEYS` ne ha 45; la docstring di `run_extraction_batch()` dice ancora "Shared by CLI (main) and Streamlit (app.py)" (`extraction/cli.py:296`) benché `app.py` sia sparito da tempo; il commento a `edge-agent/workers/capture/bper_capture_worker.py:42` dice "MobileNetV3" ma il classificatore è DINOv2 ViT-S/14 (`edge-agent/page_classifier.py:203`); `SCREENSHOT_DIR` nella tabella di CLAUDE.md non viene letto da nessuna parte.

- **Il router di pagina ML scarica i pesi da internet al primo uso.** `torch.hub.load('facebookresearch/dinov2', 'dinov2_vits14')` (`edge-agent/page_classifier.py:203`) scarica da GitHub alla prima esecuzione con `router = ml`/`hybrid`. Su una rete blindata il classificatore fallirà e si disabiliterà in silenzio; il routing di pagina non troverà mai corrispondenze, e sembrerà che "la cattura gira ma non viene mai acquisito nulla".

- **L'estrazione blocca il thread di cattura.** `ingest_frame()` esegue l'intera pipeline VLM multi-chiamata in modo sincrono dentro il QThread di cattura (`edge-agent/local_extraction_client.py:77-86`, chiamato da `bper_capture_worker.py:696`). Mentre una pagina è in estrazione, il loop FPS è fermo. Intenzionale, ma sorprendente se ti aspetti elaborazione in background.

- **L'italiano è intenzionale.** I prompt del VLM, le chiavi dei campi (`professione_principale`), le stringhe UI di PyQt6/Tkinter e le intestazioni CSV sono termini di dominio italiani: non tradurli. Codice, identificatori, commenti e messaggi di commit restano in inglese (policy linguistica in `CLAUDE.md`).

## Vedi anche

- [Stack tecnologico](03-tech-stack.md): analisi dettagliata di ogni dipendenza e di cosa è opzionale
- [Anatomia del progetto](09-project-anatomy.md): la tabella completa delle variabili d'ambiente e il catalogo dei file di configurazione
- [Guida alla configurazione](10-configuration-guide.md): ricette per cambiare provider, abilitare i ritagli di debug e risolvere errori comuni
- [Workflow](05-workflows.md): flussi passo passo per il batch CLI, la cattura dell'edge-agent e la pipeline multi-pass
- [Domande aperte](08-open-questions.md): discrepanze e decisioni irrisolte che influenzeranno la tua prima modifica
