# Tech Stack

Questo è un proof of concept interamente in Python che tratta il vision LLM come un componente intercambiabile. Ogni chiamata di estrazione passa da **LangChain**, così un'unica funzione factory (`create_chat_model()` in **`extraction/llm_factory.py`**) sceglie a runtime tra OpenAI e Google Gemini a partire da una sola variabile d'ambiente, e il resto dello stack è disposto attorno a quella cucitura: Pillow per il ritaglio e il miglioramento delle immagini, Pandas per il confronto con la ground truth, Tkinter e PyQt6 per le due interfacce desktop, e un classificatore opzionale PyTorch/DINOv2 per il riconoscimento delle pagine sul dispositivo. Non c'è web server, non c'è database, non c'è build system; il progetto gira come script da un unico `requirements.txt` piatto.

## Linguaggi

| Linguaggio | Versione | Dove è configurato |
|----------|---------|-----------------|
| Python | 3.8+ dichiarato (`CLAUDE.md`, `README.md`); 3.12/3.13 nella pratica | Non esiste alcun `pyproject.toml`, quindi nulla dichiara formalmente una versione. `run_edge_agent.bat` (righe 50-52) cerca prima Python 3.13, poi 3.12 (la preferenza è guidata dalla disponibilità delle wheel di torch), e il bytecode committato in `extraction/__pycache__/` è CPython 3.13. Considera 3.12+ il target reale. |

Python è l'unico linguaggio di implementazione. La codebase mescola però deliberatamente due lingue *naturali*: codice, identificatori, commenti e messaggi di commit sono in inglese, mentre i prompt VLM (**`prompts/*.json`**), le chiavi di campo (`professione_principale`, `filiale_relazione`, …), le stringhe delle GUI e le intestazioni CSV sono in italiano, perché il target dell'estrazione è la UI bancaria italiana di BPER e le chiavi di campo sono termini di dominio portanti che devono combaciare con il CSV di ground truth (`extraction/fields.py`, `CSV_TO_SCHEMA`). Non tradurle.

## Framework

| Framework | Ruolo | Vincolo di versione |
|-----------|------|--------------------|
| LangChain | Il layer di astrazione LLM e la dipendenza portante del progetto. `create_chat_model()` (`extraction/llm_factory.py:16`) restituisce un `BaseChatModel`; `call_vlm()` (`extraction/vlm_client.py:122`) pilota l'output strutturato Pydantic via `.with_structured_output()`. Entrambi i provider, tutti e tre i passaggi, tutte le interfacce ci passano attraverso. | `langchain-core`, `langchain-openai`, `langchain-google-genai`, tutti senza vincolo (`requirements.txt:1-3`) |
| PyQt6 | UI desktop dell'edge-agent (cattura dal vivo dello schermo). Entry `edge-agent/edge_agent.py`; finestra e schede in `edge-agent/ui/`; i worker di cattura sono sottoclassi di `QThread` e i risultati tornano al thread UI tramite segnali Qt. | `PyQt6>=6.4.0` (`requirements.txt:7`) |
| qt-material | Tema Material (`dark_cyan.xml`) applicato all'avvio dell'edge-agent (`edge-agent/edge_agent.py`). Opzionale: l'avvio degrada allo stile di default se l'import fallisce. | `qt-material>=2.14` (`requirements.txt:8`) |
| Tkinter | La GUI desktop standalone `gui_app.py` (selettore immagini, menu provider/modello, vista dei risultati, esportazione CSV/JSON). Libreria standard, quindi nessuna voce in `requirements.txt`. | stdlib |
| PyTorch / torchvision | Sostiene il classificatore ML delle pagine `BPERPagePrototypeClassifier` (`edge-agent/page_classifier.py`), che è il router in vigore: embedding DINOv2 ViT-S/14 (384 dimensioni) della ROI sull'area applicativa, confrontati con prototipi in cache per similarità del coseno **centrata** (centroide dei prototipi sottratto a entrambi i lati). Se l'import di torch fallisce, il classificatore si auto-disabilita e `classify()` restituisce `(None, 0.0)` invece di andare in crash (`edge-agent/page_classifier.py:9-19`), ma in quello stato nessuna pagina viene riconosciuta. | `torch`, `torchvision`, senza vincolo (`requirements.txt:14-15`) |

## Dipendenze principali

Raggruppate per scopo. Tutto vive nell'unico **`requirements.txt`** alla radice (17 righe); le dipendenze transitive sono omesse salvo dove contano.

### Accesso LLM
- **`langchain-core` / `langchain-openai` / `langchain-google-genai`** (`requirements.txt:1-3`), trattate sotto Framework. I pacchetti dei provider sono importati in modo lazy dentro `create_chat_model()`, quindi a runtime deve funzionare davvero solo il pacchetto del provider selezionato (`extraction/llm_factory.py:47,57`).
- **`openai`** (`requirements.txt:16`, `>=1.51.0`), l'SDK OpenAI *grezzo*, usato solo dal `LLMPageRouter` dell'edge-agent per la classificazione delle pagine (`edge-agent/llm_router.py:200-209`), con `response_format=json_object`, `temperature=0.0` e timeout da configurazione. La pipeline di estrazione non tocca mai questo SDK; è l'unica eccezione ammessa alla regola della factory unica.
- **`pydantic`** (transitiva via LangChain), definisce gli schemi di output strutturato in `extraction/schemas.py` (`FieldResult`, `ExtractionResponse`, `AnchorResponse`) e valida manualmente il percorso JSON in forma libera di Gemini (`extraction/vlm_client.py:93`).

### Immagini e cattura
- **`Pillow`** (`requirements.txt:11`, `>=10.0.0`), tutto il lavoro di ritaglio/ridimensionamento/miglioramento: `normalize_image()`, `crop_relative()`, `img_to_png_bytes()` in `extraction/imaging.py` per la pipeline; `preprocess_for_ocr()` (upscale adattivo, unsharp mask, autocontrasto) in `edge-agent/image_ops.py` e la normalizzazione dell'inquadratura in `edge-agent/frame_normalize.py` per la cattura.
- **`mss`** (`requirements.txt:9`, `>=9.0.0`), cattura veloce del monitor nel loop dell'edge-agent (`edge-agent/workers/capture/bper_capture_worker.py:557-574`).
- **`imagehash`** (`requirements.txt:12`, `>=4.3.0`), hashing percettivo (pHash) per la deduplica dei frame; i frame entro la distanza di Hamming `dedup_threshold` (default 3) saltano il routing (`bper_capture_worker.py:601-624`).
- **`pyscreenshot`** (`requirements.txt:10`, `>=3.1`, **marker d'ambiente solo Linux** `sys_platform == 'linux'`), grabber di fallback usato solo da `DefaultCaptureWorker` (modalità generica). Su Windows non viene proprio installato, il che va bene perché il percorso BPER usa `mss`.

### Dati e valutazione
- **`pandas`** (`requirements.txt:4`), carica il CSV di ground truth con auto-rilevamento dei nomi di colonna (`load_ground_truth()`, `extraction/evaluation.py:33`) e scrive i CSV di debug/risultati (separatore `;`, `utf-8-sig`).
- **`openpyxl`** (`requirements.txt:17`, `>=3.1.2`), legge il workbook opzionale della sequenza pagine `Guida pagine ITA .xlsx` (`bper_capture_worker.py:273-291`; il file è assente dal repo, con fallback controllato su `prompts.json`) e sostiene l'esportazione Excel in `edge-agent/ui/data_table_tab.py`.

### Configurazione e bootstrap
- **`python-dotenv`** (`requirements.txt:6`), carica `.env` prima che il pacchetto `extraction` venga importato, cosa che conta perché `extraction/config.py` legge ogni variabile d'ambiente al momento dell'import. Caricato in `main.py:7`, `edge-agent/edge_agent.py:9-13` e `edge-agent/local_extraction_client.py:22-25`, ma **non** in `gui_app.py`, che presume le variabili già esportate (vedi [Domande Aperte](08-open-questions.md)).
- **`requests`** (`requirements.txt:13`, `>=2.31.0`), l'upload HTTP dei frame usato solo dalla modalità di cattura generica legacy (`edge-agent/workers/capture/default_capture_worker.py:62-66`), che invia POST a un backend che non esiste in questo repo.

### Orfane
- **`streamlit`** (`requirements.txt:5`): nulla la importa. È un residuo della UI web Streamlit rimossa (`app.py`, cancellato nel commit `ea04ef7`). Candidata alla rimozione; anche `CLAUDE.md` la segnala. È l'unica dipendenza orfana rimasta.

## Infrastruttura

Non c'è database, coda di messaggi o cache. I risultati vivono in dizionari in memoria (nell'edge-agent, un dict `_results` protetto da `threading.Lock` dentro `LocalExtractionClient`) e vengono persistiti solo come file: `mnt/data/poc_outputs_improved.json` e `poc_debug_improved.csv` dalla CLI, `poc_outputs_gui.json` / `poc_results_gui.csv` / `poc_debug_gui.csv` dalla GUI Tkinter, e i CSV/XLSX esportati dall'operatore nell'edge-agent.

Servizi esterni vivi (tutti HTTPS in uscita):
- **API OpenAI**: estrazione principale via LangChain (`gpt-4o` di default) e routing delle pagine via SDK grezzo (`gpt-4o-mini`).
- **API Google Gemini**: provider di estrazione alternativo (`LLM_PROVIDER=gemini`).
- **torch.hub**: i pesi DINOv2 vengono scaricati una volta al primo avvio del router ML.

Infrastruttura morta, referenziata nella configurazione ma inutilizzata nel flusso BPER solo-locale, residui dell'era del backend remoto rimosso (commit `ea04ef7`):
- Un'API di ingestione frame su `http://localhost:8081` (`edge-agent/config.ini:10`, `[api]`), raggiungibile solo dalla modalità generica legacy.
- MinIO su `http://localhost:9000` (`config.ini` `[minio]`); l'unico aspirante consumatore, `_maybe_upload_dataset()`, è uno stub no-op (`bper_capture_worker.py:713-715`).

## Strumenti di sviluppo

| Strumento | Ruolo | Stato |
|------|------|--------|
| PyInstaller | Pacchettizza `gui_app.py` in un `.exe` Windows (`AI_Data_Extractor`), con flag `--collect-all` per gli import dinamici di LangChain. | Ricetta documentata solo in `README.md` righe 78-100; non in `requirements.txt` |
| `run_edge_agent.bat` | Launcher Windows: verifica/ricostruisce una `.venv` obsoleta (preferendo Python 3.13), installa `requirements.txt`, lancia l'edge-agent inoltrando gli argomenti. | Committato, funzionante |
| Linter / formatter | Nessuno. Nessun `ruff`, `flake8`, `black` o configurazione `pyproject.toml` da nessuna parte. | Assente |
| Test runner | Nessuno. Non esiste una suite di test; la validazione è manuale (esegui `python main.py`, confronta accuratezza e costi con una baseline, fai lo smoke test delle GUI: `CLAUDE.md` "Testing & Validation"). | Assente |
| CI/CD | Nessuna. Nessun `.github/workflows` o configurazione di pipeline. | Assente |
| Docker | Nessuno. Nessun `Dockerfile`. | Assente |

Le lacune sono coerenti con la maturità da POC e sono riconosciute in `CLAUDE.md` "Missing Infrastructure".

## Gestione delle dipendenze

pip con un **unico `requirements.txt` piatto** alla radice del repo: dipendenze del core di estrazione e dell'edge-agent combinate, nessuna suddivisione per componente, nessun gruppo di dipendenze di sviluppo, nessun lockfile, nessun `pyproject.toml`.

Coesistono due stili di vincolo:
- **Senza vincolo:** il trio LangChain, `pandas`, `streamlit`, `python-dotenv`, `torch`, `torchvision`. I pacchetti LangChain non pinnati sono l'elemento a rischio più alto: il comportamento di output strutturato su cui `extraction/vlm_client.py` si dirama per provider/famiglia di modello (`_GEMINI_JSON_SCHEMA_MODELS`, `vlm_client.py:18,134-138`) è sensibile alla deriva di versione di LangChain.
- **Limite inferiore (`>=`):** `PyQt6`, `qt-material`, `mss`, `pyscreenshot`, `Pillow`, `imagehash`, `requests`, `openai`, `openpyxl`.

Nulla è pinnato in modo esatto, quindi un `pip install -r requirements.txt` fresco non è riproducibile da un giorno all'altro: versioni diverse di LangChain o torch possono arrivare in silenzio. Altre due cose da segnalare: `pyscreenshot` porta un marker di piattaforma (solo Linux), quindi le installazioni cross-platform differiscono di proposito; e `streamlit` è un puro orfano che gonfia un'installazione già pesante (torch ne è il grosso).

---

Vedi anche: [Architettura](04-architecture.md) per come questi pezzi si incastrano, [Funzionalità](02-features.md) per cosa forniscono e [Workflow](05-workflows.md) per i percorsi end-to-end che li attraversano.
