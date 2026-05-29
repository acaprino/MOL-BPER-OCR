# Tech Stack

Questo è un progetto interamente in Python, costruito attorno a LangChain per l'integrazione multi-LLM, Pillow per l'elaborazione delle immagini e Pydantic per la validazione dell'output strutturato. Dialoga con Vision-Language Model in cloud (OpenAI GPT-4o, Google Gemini) per estrarre dati strutturati dagli screenshot bancari, senza alcun database locale -- tutto vive in memoria o in file piatti. Le UI desktop usano due toolkit diversi: Tkinter per la GUI standalone e PyQt6 per l'edge-agent.

## Linguaggi

| Linguaggio | Versione | Dove è configurato |
|----------|---------|-----------------|
| Python | 3.8+ richiesto; 3.13 osservato nei file `.pyc` compilati | Non esiste alcun `pyproject.toml` o `setup.py`. Il bytecode `.pyc` in `__pycache__/` (es. `extraction/__pycache__/fields.cpython-313.pyc`) conferma che l'ambiente di sviluppo gira su 3.13. |

Non c'è alcun vincolo esplicito sulla versione di Python in nessun punto del repository. Il codice usa `from __future__ import annotations` in alcuni moduli dell'edge-agent (`edge-agent/edge_agent.py`, `edge-agent/local_extraction_client.py`, `edge-agent/llm_router.py`, `edge-agent/page_classifier.py`) per type hint forward-compatible, e la sintassi delle union di Python 3.10+ (`float | None`) appare in `edge-agent/config.py` alla riga 39 -- quindi 3.10 è il minimo pratico, nonostante la documentazione dichiari 3.8+.

## Framework

### LangChain (langchain-core, langchain-openai, langchain-google-genai)

L'astrazione centrale per tutta la comunicazione con gli LLM. `extraction/llm_factory.py` usa una funzione factory `create_chat_model()` che importa in modo lazy `langchain_openai.ChatOpenAI` oppure `langchain_google_genai.ChatGoogleGenerativeAI` a seconda del provider configurato. La pipeline chiama `.with_structured_output()` di LangChain sul modello risultante per ottenere JSON validato da Pydantic direttamente dalla risposta dell'LLM (`extraction/vlm_client.py` righe 147, 193). In `requirements.txt` non è specificato alcun vincolo di versione.

### PyQt6 (>= 6.4.0)

Guida l'applicazione desktop edge-agent. L'entry point è `edge-agent/edge_agent.py`, che crea una `QApplication`, applica un tema Material Design tramite `qt-material` e avvia una `MainWindow` con quattro schede (Cattura, Risultati, Dati, Debug). I thread worker estendono `QThread` e comunicano con la UI tramite `pyqtSignal`. Configurato in `requirements.txt` riga 8.

### Tkinter (libreria standard)

Fornisce la GUI desktop standalone in `gui_app.py`. È un'interfaccia più semplice: selezione file, scelta provider/modello, avvio dell'estrazione a lotti e treeview dei risultati. Non richiede dipendenze esterne -- è inclusa in Python.

### qt-material (>= 2.14)

Libreria di theming per l'app PyQt6. Applicata in `edge-agent/edge_agent.py` righe 38-43 con il tema `dark_cyan.xml`. Degrada con grazia se non è installata (`except ImportError: pass`).

## Dipendenze principali

### Integrazione LLM

| Dipendenza | Ruolo | Configurata in |
|-----------|------|---------------|
| `langchain-core` | Astrazioni di base (`BaseChatModel`, `HumanMessage`, `SystemMessage`) | `requirements.txt` riga 1; usata in tutto `extraction/vlm_client.py`, `extraction/llm_factory.py` |
| `langchain-openai` | Wrapper `ChatOpenAI` per l'API OpenAI | `requirements.txt` riga 2; importata in modo lazy in `extraction/llm_factory.py` riga 47 |
| `langchain-google-genai` | Wrapper `ChatGoogleGenerativeAI` per l'API Gemini | `requirements.txt` riga 3; importata in modo lazy in `extraction/llm_factory.py` riga 57 |
| `openai` (>= 1.51.0) | Usata direttamente (non tramite LangChain) dal `LLMPageRouter` dell'edge-agent per la classificazione delle pagine via Vision API | `requirements.txt` riga 19; `edge-agent/llm_router.py` riga 23 |
| `pydantic` | Transitiva via LangChain. Tutti gli schemi di estrazione (`FieldResult`, `ExtractionResponse`, `AnchorResponse`) sono sottoclassi di `BaseModel` Pydantic. `FieldsModel` è generato dinamicamente via `create_model()`. | `extraction/schemas.py` |

### Elaborazione delle immagini

| Dipendenza | Ruolo | Configurata in |
|-----------|------|---------------|
| `Pillow` (>= 10.0.0) | Operazioni core sulle immagini: resize, ritaglio, miglioramento del contrasto, unsharp mask, conversione di formato | `requirements.txt` righe 4, 12 (elencata due volte); `extraction/imaging.py`, `edge-agent/image_ops.py` |
| `imagehash` (>= 4.3.0) | Perceptual hashing (pHash) per la deduplica dei frame nel worker di cattura. Distanza di Hamming <= soglia significa "stesso frame" | `requirements.txt` riga 13; `edge-agent/workers/capture/bper_capture_worker.py` riga 8 |

### Machine Learning (classificazione delle pagine)

| Dipendenza | Ruolo | Configurata in |
|-----------|------|---------------|
| `torch` | Runtime PyTorch per l'estrazione delle feature DINOv2 ViT-S/14. Caricato via `torch.hub.load('facebookresearch/dinov2', 'dinov2_vits14')` | `requirements.txt` riga 17; `edge-agent/page_classifier.py` riga 203 |
| `torchvision` | Fornisce le `transforms` (Resize, CenterCrop, Normalize) per il pre-trattamento delle immagini prima di DINOv2 | `requirements.txt` riga 18; `edge-agent/page_classifier.py` riga 162 |

Entrambe sono opzionali. Se `torch` non riesce a importarsi (DLL mancante, ambiente incompatibile), il classificatore entra in modalità DISABLED e `classify()` restituisce `(None, 0.0)`. L'applicazione continua a funzionare con il solo riconoscimento via LLM. Vedi `edge-agent/page_classifier.py` righe 153-170.

### Gestione dei dati

| Dipendenza | Ruolo | Configurata in |
|-----------|------|---------------|
| `pandas` | Lettura del CSV per la ground truth (`pd.read_csv`), costruzione di DataFrame per i report di debug e le esportazioni (`pd.DataFrame.to_csv`) | `requirements.txt` riga 5; `extraction/evaluation.py` |
| `openpyxl` (>= 3.1.2) | Esportazione Excel dalla DataTableTab nella UI dell'edge-agent | `requirements.txt` riga 20 |

### Utility

| Dipendenza | Ruolo | Configurata in |
|-----------|------|---------------|
| `python-dotenv` | Carica il file `.env` all'avvio. Chiamata in `main.py` riga 7, `edge-agent/edge_agent.py` riga 11 e `edge-agent/local_extraction_client.py` riga 23 | `requirements.txt` riga 7 |
| `mss` (>= 9.0.0) | Cattura veloce e cross-platform degli screenshot del monitor per l'edge-agent | `requirements.txt` riga 10; usata da `BaseCaptureWorker` |
| `pyscreenshot` (>= 3.1) | Libreria di fallback per gli screenshot solo su Linux. Installazione condizionale: `sys_platform == 'linux'` | `requirements.txt` riga 11 |
| `requests` (>= 2.31.0) | Chiamate HTTP in `DefaultCaptureWorker` (la modalità di cattura generica, non-BPER) | `requirements.txt` riga 14 |

### Dipendenze dormienti / abbozzate

| Dipendenza | Stato | Note |
|-----------|--------|-------|
| `boto3` (>= 1.35.0) | Elencata in `requirements.txt` riga 15. `edge-agent/config.ini` ha una sezione `[minio]`. Il percorso di upload del dataset (`_maybe_upload_dataset`) è un no-op nel codice attuale. | Probabilmente previsto per l'archiviazione dei frame su S3/MinIO. |
| `keyboard` (== 0.13.5) | Pinnata in modo esatto in `requirements.txt` riga 16. Nessun uso attivo trovato in alcun file sorgente. | Probabilmente un residuo di una funzionalità di hotkey rimossa. |
| `streamlit` | Elencata in `requirements.txt` riga 6. Citata in `CLAUDE.md` come `app.py`. Nel repo non esiste alcun `app.py`. | Era probabilmente una UI web Streamlit rimossa o mai committata in questo branch. |

## Infrastruttura

Non c'è alcun database. Tutto lo stato vive in dizionari Python durante un'esecuzione.

| Componente | Ruolo | Stato |
|-----------|------|--------|
| Ground truth CSV (`mnt/data/dati.csv`) | Conserva i valori attesi dei campi per ogni screenshot, per la valutazione dell'accuratezza | Escluso da git (`/mnt` in `.gitignore` riga 9). Deve essere fornito esternamente. |
| JSON di output (`mnt/data/poc_outputs_improved.json`) | Risultati dell'estrazione a lotti | Scritto da `extraction/cli.py` riga 339 |
| CSV di debug (`mnt/data/poc_debug_improved.csv`) | Dettaglio dell'accuratezza per campo | Scritto da `extraction/cli.py` riga 346 |
| MinIO / S3 | Object storage per i frame catturati | Configurato in `edge-agent/config.ini` righe 12-16 (endpoint `localhost:9000`). Il codice di upload è abbozzato -- non attivo. |
| API OpenAI | LLM in cloud per l'estrazione + il riconoscimento delle pagine | Accessibile via LangChain (`langchain-openai`) e direttamente (SDK `openai`) |
| API Google Gemini | LLM in cloud alternativo per l'estrazione | Accessibile via LangChain (`langchain-google-genai`) |
| DINOv2 (Facebook Research) | Modello visivo pre-addestrato scaricato al primo avvio via `torch.hub` | `edge-agent/page_classifier.py` riga 203. Messo in cache localmente da PyTorch Hub. |

## Strumenti di sviluppo

| Strumento | Scopo | Configurazione |
|------|---------|--------------|
| PyInstaller | Pacchettizzazione di `gui_app.py` come `.exe` standalone | Documentato in `README.md`. Nessun file `.spec` è committato (`.gitignore` esclude `*.spec`). |

Notevolmente assenti:

- **Nessuna configurazione di linter o formatter.** Nessun `ruff.toml`, `.flake8`, `pyproject.toml [tool.black]` o simili.
- **Nessun framework di test.** Nessun `pytest.ini`, directory `tests/` o file di test in alcun punto del repo.
- **Nessuna pipeline CI/CD.** Nessun `.github/workflows/`, `Jenkinsfile` o equivalente.
- **Nessuna configurazione di type checking.** Nessun `mypy.ini` o marker `py.typed`, nonostante l'uso intensivo delle annotazioni di tipo.

## Gestione delle dipendenze

Le dipendenze sono gestite tramite un unico `requirements.txt` nella radice del progetto (`D:\Projects\poc-data-extraction\requirements.txt`). Non c'è alcun `pyproject.toml`, `setup.py`, `setup.cfg` o `Pipfile`.

**Strategia di pinning:** La maggior parte delle dipendenze usa vincoli di versione minimi o assenti. Solo alcune specificano un minimo (es. `PyQt6>=6.4.0`, `openai>=1.51.0`). Una dipendenza è pinnata in modo rigido: `keyboard==0.13.5`. I pacchetti LangChain (`langchain-core`, `langchain-openai`, `langchain-google-genai`) e `pillow` (in cima al file) non hanno alcun vincolo di versione, mentre `Pillow>=10.0.0` appare di nuovo più in basso nel file come duplicato con un minimo.

**Non esiste alcun lockfile.** Non c'è alcun `requirements.lock`, output di `pip-compile` o `poetry.lock`. Le build non sono riproducibili tra ambienti diversi senza intervento manuale.

**Ambiente virtuale:** È presente una directory `.venv/` (esclusa da git). Il percorso di setup documentato è il classico `pip install -r requirements.txt`.

**Le dipendenze dell'edge-agent sono combinate** nello stesso `requirements.txt` del core di estrazione. Non c'è separazione tra le esigenze dello strumento CLI (LangChain, pandas) e quelle dell'agente desktop (PyQt6, torch, mss). È necessario installare tutto, indipendentemente da quale interfaccia intendi usare.

## Vedi anche

- [Architettura](04-architecture.md) -- come questi pacchetti si collegano a runtime e quali moduli dialogano con quali API
- [Anatomia del progetto](09-project-anatomy.md) -- il catalogo completo dei file di configurazione e delle variabili d'ambiente che queste dipendenze consumano
- [Getting Started](07-getting-started.md) -- guida all'installazione e il sottoinsieme minimo necessario per il lavoro solo via CLI
- [Domande Aperte](08-open-questions.md) -- problemi irrisolti attorno alle dipendenze `boto3`, `keyboard` e `streamlit` senza chiamanti attivi
