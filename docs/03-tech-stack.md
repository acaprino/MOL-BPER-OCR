# Tech Stack

Questo è un proof of concept interamente in Python che tratta il vision LLM come un componente intercambiabile. Ogni chiamata di estrazione passa da **LangChain**, così un'unica funzione factory (`create_chat_model()` in **`src/extraction/llm_factory.py`**) sceglie a runtime tra OpenAI e Google Gemini a partire da una sola variabile d'ambiente, e il resto dello stack è disposto attorno a quella cucitura: Pillow per il ritaglio e il miglioramento delle immagini, Pandas per il confronto con la ground truth, Tkinter e PyQt6 per le due interfacce desktop, e un classificatore opzionale PyTorch/DINOv2 per il riconoscimento delle pagine sul dispositivo. Non c'è web server, non c'è database, la build portable usa `build_exe.bat` e `edge_agent.spec`; le dipendenze applicative sono in `requirements.txt`.

## Linguaggi

| Linguaggio | Versione | Dove è configurato |
|----------|---------|-----------------|
| Python | Target pratico 3.12/3.13 | `run_edge_agent.bat` prova `py -3.13`, poi `py -3.12`, infine `python` sul PATH. Non c’è un vincolo formale di runtime in un `pyproject.toml`. |

Python è l'unico linguaggio di implementazione. La codebase mescola però deliberatamente due lingue *naturali*: codice, identificatori, commenti e messaggi di commit sono in inglese, mentre i prompt VLM (**`prompts/*.json`**), le chiavi di campo (`professione_principale`, `filiale_relazione`, …), le stringhe delle GUI e le intestazioni CSV sono in italiano, perché il target dell'estrazione è la UI bancaria italiana di BPER e le chiavi di campo sono termini di dominio portanti che devono combaciare con il CSV di ground truth (`src/extraction/fields.py`, `CSV_TO_SCHEMA`). Non tradurle.

## Framework

| Framework | Ruolo | Vincolo di versione |
|-----------|------|--------------------|
| LangChain | Il layer di astrazione LLM e la dipendenza portante del progetto. `create_chat_model()` (`src/extraction/llm_factory.py:16`) restituisce un `BaseChatModel`; `call_vlm()` (`src/extraction/vlm_client.py:122`) pilota l'output strutturato Pydantic via `.with_structured_output()`. Entrambi i provider, tutti e tre i passaggi, tutte le interfacce ci passano attraverso. | `langchain-core`, `langchain-openai`, `langchain-google-genai`, tutti senza vincolo (`requirements.txt:1-3`) |
| PyQt6 | UI desktop dell'edge-agent (cattura dal vivo dello schermo). Entry `src/edge-agent/edge_agent.py`; finestra e schede in `src/edge-agent/ui/`; i worker di cattura sono sottoclassi di `QThread` e i risultati tornano al thread UI tramite segnali Qt. | `PyQt6>=6.4.0` (`requirements.txt:7`) |
| tema proprio | Token di colore e stylesheet in `src/edge-agent/theme.py`, chiaro o scuro come Windows (ADR 0033). Nessuna dipendenza esterna: ha sostituito `qt-material`. | `src/edge-agent/theme.py` |
| Tkinter | La GUI desktop standalone `gui_app.py` (selettore immagini, menu provider/modello, vista dei risultati, esportazione CSV/JSON). Libreria standard, quindi nessuna voce in `requirements.txt`. | stdlib |
| PyTorch / torchvision | Classificatore locale `BPERPagePrototypeClassifier`: embedding DINOv2 ViT-S/14 (384 dimensioni) confrontati con prototipi tramite coseno centrato. È usato da `ml`, dal fallback `hybrid` e da `local-first`. Se l’import fallisce, il classificatore si disabilita. `config.ini` spedisce `llm`, mentre `AgentConfig.DEFAULT_ROUTER_MODE` resta `ml`. | `torch`, `torchvision`, senza vincolo (`requirements.txt`) |

## Dipendenze principali

Raggruppate per scopo. Tutto vive nell'unico **`requirements.txt`** alla radice; le dipendenze transitive sono omesse salvo dove contano.

### Accesso LLM
- **`langchain-core` / `langchain-openai` / `langchain-google-genai`** (`requirements.txt:1-3`), trattate sotto Framework. I pacchetti dei provider sono importati in modo lazy dentro `create_chat_model()`, quindi a runtime deve funzionare davvero solo il pacchetto del provider selezionato (`src/extraction/llm_factory.py:47,57`).
- **`openai`** (`requirements.txt:16`, `>=1.51.0`), l'SDK OpenAI *grezzo*, usato solo dal `LLMPageRouter` dell'edge-agent per la classificazione delle pagine (`src/edge-agent/llm_router.py:200-209`), con `response_format=json_object`, `temperature=0.0` e timeout da configurazione. La pipeline di estrazione non tocca mai questo SDK; è l'unica eccezione ammessa alla regola della factory unica.
- **`pydantic`** (transitiva via LangChain), definisce gli schemi di output strutturato in `src/extraction/schemas.py` (`FieldResult`, `ExtractionResponse`, `AnchorResponse`) e valida manualmente il percorso JSON in forma libera di Gemini (`src/extraction/vlm_client.py:93`).

### Immagini e cattura
- **`Pillow`** (`requirements.txt:11`, `>=10.0.0`), tutto il lavoro di ritaglio/ridimensionamento/miglioramento: `normalize_image()`, `crop_relative()`, `img_to_png_bytes()` in `src/extraction/imaging.py` per la pipeline; `preprocess_for_ocr()` (upscale adattivo, unsharp mask, autocontrasto) in `src/edge-agent/image_ops.py` e la normalizzazione dell'inquadratura in `src/edge-agent/frame_normalize.py` per la cattura.
- **`mss`** (`requirements.txt:9`, `>=9.0.0`), cattura veloce del monitor nel loop dell'edge-agent (`src/edge-agent/workers/capture/bper_capture_worker.py:557-574`).
- **`imagehash`** (`>=4.3.0`), pHash per contenere il routing sui frame simili. L’identità della visita usa invece `hashlib.blake2b` della libreria standard sui pixel normalizzati, per distinguere anche piccole variazioni dell’NDG (`bper_capture_worker.py`).
- **`pyscreenshot`** (`requirements.txt:10`, `>=3.1`, **marker d'ambiente solo Linux** `sys_platform == 'linux'`), grabber di fallback usato solo da `DefaultCaptureWorker` (modalità generica). Su Windows non viene proprio installato, il che va bene perché il percorso BPER usa `mss`.

### Dati e valutazione
- **`pandas`** (`requirements.txt:4`), carica il CSV di ground truth con auto-rilevamento dei nomi di colonna (`load_ground_truth()`, `src/extraction/evaluation.py:33`) e scrive i CSV di debug/risultati (separatore `;`, `utf-8-sig`).
- **`openpyxl`** (`>=3.1.2`), scrittura del workbook finale con `src/edge-agent/excel_export.py`: una riga per pratica, intestazione a due livelli.

### Configurazione e bootstrap
- **`python-dotenv`** (`requirements.txt:6`), carica `.env` prima che il pacchetto `extraction` venga importato, cosa che conta perché `src/extraction/config.py` legge ogni variabile d'ambiente al momento dell'import. Caricato in `main.py:7`, `src/edge-agent/edge_agent.py:9-13` e `src/edge-agent/local_extraction_client.py:22-25`, ma **non** in `gui_app.py`, che presume le variabili già esportate (vedi [Domande Aperte](08-open-questions.md)).
- **`requests`** (`requirements.txt:13`, `>=2.31.0`), l'upload HTTP dei frame usato solo dalla modalità di cattura generica legacy (`src/edge-agent/workers/capture/default_capture_worker.py:62-66`), che invia POST a un backend che non esiste in questo repo.

### Build e test
- **`pyinstaller>=6.10,<7`** è in `requirements.txt` e serve alla build portable `build_exe.bat`, anche se non viene importato dal codice applicativo.
- **`pytest>=8.0`** è in `requirements-dev.txt` e avvia la suite `tests/`. `streamlit` è stato rimosso dalle dipendenze.

## Infrastruttura

Non c’è database né broker esterno. Esistono code locali in memoria (`extraction_pool.py` e i comandi del worker) e i prototipi DINOv2 delle pagine, distribuiti con l'app (ADR 0030). `LocalExtractionClient` conserva i risultati sotto lock e pubblica il prefisso completato in ordine di acquisizione. CLI e Tkinter esportano JSON/CSV; la UI dell’edge-agent consolida le schermate per pratica ed esporta Excel. La memoria della sessione non è un archivio persistente.

Servizi esterni vivi (tutti HTTPS in uscita):
- **API OpenAI**: provider di estrazione via LangChain (`gpt-4o` come default del codice) e provider possibile per il router tramite SDK OpenAI.
- **API Google Gemini**: provider di estrazione alternativo e provider del router nella configurazione INI spedita, attraverso l’endpoint compatibile OpenAI. «Locale» descrive l’orchestrazione, non un’estrazione offline.
- **torch.hub**: il pacchetto contiene repo e pesi DINOv2 nella sua `torch-cache` (ADR 0031), quindi il riconoscimento funziona senza rete; da sorgente i pesi si scaricano una volta al primo avvio.

Infrastruttura morta, referenziata nella configurazione ma inutilizzata nel flusso BPER solo-locale, residui dell'era del backend remoto rimosso (commit `ea04ef7`):
- Un'API di ingestione frame su `http://localhost:8081` (`src/edge-agent/config.ini:10`, `[api]`), raggiungibile solo dalla modalità generica legacy.
- MinIO su `http://localhost:9000` (`config.ini` `[minio]`); l'unico aspirante consumatore, `_maybe_upload_dataset()`, è uno stub no-op (`bper_capture_worker.py:713-715`).

## Strumenti di sviluppo

| Strumento | Ruolo | Stato |
|------|------|--------|
| PyInstaller | Build portable dell’edge-agent con `build_exe.bat` e `edge_agent.spec`, output `dist/EdgeAgent` e ZIP datato. | In `requirements.txt`, vincolo `>=6.10,<7` |
| `run_edge_agent.bat` | Launcher Windows: verifica/ricostruisce una `.venv` obsoleta (preferendo Python 3.13), installa `requirements.txt`, lancia l'edge-agent inoltrando gli argomenti. | Committato, funzionante |
| Linter / formatter | Nessuno. Nessun `ruff`, `flake8`, `black` o configurazione `pyproject.toml` da nessuna parte. | Assente |
| Test runner | pytest: `python -m pytest tests`. | `requirements-dev.txt`, suite `tests/` |
| CI/CD | Nessuna. Nessun `.github/workflows` o configurazione di pipeline. | Assente |
| Docker | Nessuno. Nessun `Dockerfile`. | Assente |

Le lacune sono coerenti con la maturità da POC e sono riconosciute in `CLAUDE.md` "Missing Infrastructure".

## Gestione delle dipendenze

pip con un **unico `requirements.txt` piatto** alla radice del repo: dipendenze del core di estrazione e dell'edge-agent combinate, nessuna suddivisione per componente, pytest separato in `requirements-dev.txt`, nessun lockfile, nessun `pyproject.toml`.

Coesistono questi stili di vincolo:
- **Senza vincolo:** il trio LangChain, `pandas`, `python-dotenv`, `torch`, `torchvision`. I pacchetti LangChain non pinnati sono l'elemento a rischio più alto: il comportamento di output strutturato su cui `src/extraction/vlm_client.py` si dirama per provider/famiglia di modello (`_GEMINI_JSON_SCHEMA_MODELS`, `vlm_client.py:18,134-138`) è sensibile alla deriva di versione di LangChain.
- **Intervallo di versione:** `pyinstaller>=6.10,<7`.
- **Limite inferiore (`>=`):** `PyQt6`, `mss`, `pyscreenshot`, `Pillow`, `imagehash`, `requests`, `openai`, `openpyxl`.

Nulla è pinnato in modo esatto, quindi un `pip install -r requirements.txt` fresco non è riproducibile da un giorno all'altro: versioni diverse di LangChain o torch possono arrivare in silenzio. `pyscreenshot` porta un marker di piattaforma (solo Linux), quindi le installazioni cross-platform differiscono di proposito; torch resta fra i componenti più pesanti.

---

Vedi anche: [Architettura](04-architecture.md) per come questi pezzi si incastrano, [Funzionalità](02-features.md) per cosa forniscono e [Workflow](05-workflows.md) per i percorsi end-to-end che li attraversano.
