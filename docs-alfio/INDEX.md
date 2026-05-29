# poc-data-extraction - Guida al codice

Un proof of concept (prototipo) Python che usa i Vision Language Model (OpenAI GPT-4o, Google Gemini) per estrarre 45 campi strutturati dagli screenshot dell'applicativo bancario italiano BPER. Si presenta come tre interfacce costruite su un'unica pipeline `extraction/` condivisa: un runner a lotti via CLI, una GUI desktop Tkinter e un edge-agent PyQt6 con cattura dal vivo dello schermo.

## Documenti

| # | Documento | Descrizione |
|---|----------|-------------|
| 0 | [Sintesi per tutti](00-executive-summary.md) | Panoramica in parole semplici, senza gergo, per chiunque, anche per lettori non tecnici. |
| 1 | [Panoramica](01-overview.md) | Cosa fa il progetto, a chi è rivolto e come la pipeline VLM multi-pass trasforma gli screenshot in JSON strutturato. |
| 2 | [Funzionalità](02-features.md) | La pipeline anchor/principale/retry, la factory LLM multi-provider, l'elaborazione delle immagini, la CLI, la GUI Tkinter e le capacità dell'edge-agent, tutto in un unico posto. |
| 3 | [Tech Stack](03-tech-stack.md) | Versioni di Python, dipendenze LangChain + PyQt6 + Pillow + Pydantic + torch e cosa è dormiente o solo abbozzato (`boto3`, `keyboard`, `streamlit`). |
| 4 | [Architettura](04-architecture.md) | La struttura hub-and-spokes con il core `extraction/` che alimenta tre entry point, incluso un diagramma dei componenti e l'ordine di caricamento della configurazione. |
| 5 | [Workflow](05-workflows.md) | Flowchart passo passo e diagrammi di sequenza per l'elaborazione a lotti via CLI, la cattura dal vivo dell'edge-agent, l'estrazione multi-pass e la valutazione dell'accuratezza. |
| 6 | [Data Model](06-data-model.md) | Gli schemi Pydantic (`FieldResult`, `Soggetto`, `Fido`, `Garanzia`, `ExtractionResponse`, `AnchorResponse`), il dizionario di output della pipeline a runtime e il contratto del CSV di ground truth. |
| 7 | [Getting Started](07-getting-started.md) | Configurazione al primo avvio: clone, venv, `.env`, dati di test e un ordine di lettura per il codice stesso. |
| 8 | [Domande Aperte](08-open-questions.md) | Elenco onesto di decisioni irrisolte, codice abbozzato e discrepanze tra documentazione e codice da portare alla tua prima conversazione di team. |
| 9 | [Anatomia del progetto](09-project-anatomy.md) | Catalogo completo di directory, file di configurazione, variabili d'ambiente, comandi e sequenze di avvio. |
| 10 | [Guida alla configurazione](10-configuration-guide.md) | Ricette quotidiane per cambiare provider, regolare il parallelismo, configurare il router dell'edge-agent e risolvere gli errori più comuni. |
| 11 | [Glossario](11-glossary.md) | Definizioni in parole semplici dei termini di dominio bancario (NDG, fido, garanzia...) e dei termini tecnici (VLM, passaggio anchor, DINOv2...). |
| 12 | [Come funziona, sotto il cofano](12-come-funziona-sotto-il-cofano.md) | 🇮🇹 Approfondimento in parole semplici (in italiano) su *come* funziona davvero: niente OCR (è tutto VLM), i filtri della cattura dal vivo (deduplica pHash, router pagina, stabilità), i ritagli delle immagini spiegati con diagrammi, la pipeline a 3 passaggi anchor/principale/retry, la disambiguazione dell'omonimia dei campi, i controlli di coerenza e il tracciamento di confidenza/costi. |

## Percorsi di lettura

**Non tecnico (10 minuti):** Leggi la [Sintesi per tutti](00-executive-summary.md). Tieni aperto il [Glossario](11-glossary.md) per ogni parola sconosciuta. È tutto ciò che ti serve per capire cos'è questo progetto e cosa produce.

**Vuoi capire *come* funziona senza leggere codice (30 minuti):** Leggi [Come funziona, sotto il cofano](12-come-funziona-sotto-il-cofano.md). Spiega ogni meccanismo interno — OCR vs VLM, i filtri di cattura, i ritagli delle immagini, la pipeline a 3 passaggi, la disambiguazione dei campi, i costi — in parole semplici e con diagrammi. È il ponte concettuale tra la Sintesi per tutti e la documentazione tecnica densa.

**Nuovo al progetto (prima ora):** Leggi [Panoramica](01-overview.md) e [Funzionalità](02-features.md) per capire cos'è il progetto, poi leggi [Come funziona, sotto il cofano](12-come-funziona-sotto-il-cofano.md) per i meccanismi, poi scorri [Architettura](04-architecture.md) per la disposizione dei componenti e infine salta a [Getting Started](07-getting-started.md) per configurare l'ambiente ed eseguire `python main.py`. Tieni a portata di mano [Domande Aperte](08-open-questions.md) per le insidie.

**Correggere un bug o aggiungere un campo:** Parti da [Data Model](06-data-model.md) per gli schemi Pydantic e il contratto `FIELD_KEYS`, poi leggi [Workflow](05-workflows.md) per la sequenza della pipeline multi-pass, poi apri [Architettura](04-architecture.md) per individuare il modulo che devi toccare. Controlla [Guida alla configurazione](10-configuration-guide.md) per le variabili d'ambiente che controllano il comportamento senza modifiche al codice.

**Rivedere l'architettura o pianificare un refactoring:** Leggi insieme [Architettura](04-architecture.md) e [Tech Stack](03-tech-stack.md) per il quadro completo, poi [Data Model](06-data-model.md) per le strutture delle entità e infine [Domande Aperte](08-open-questions.md) per il debito tecnico accumulato.

**Deploy o configurazione per un nuovo ambiente:** Leggi [Anatomia del progetto](09-project-anatomy.md) per il catalogo completo delle variabili d'ambiente e [Guida alla configurazione](10-configuration-guide.md) per le ricette, e confronta con [Tech Stack](03-tech-stack.md) per le dipendenze opzionali che puoi saltare.

## Fatti chiave

- **Linguaggio:** Python 3.8+ richiesto; 3.13 osservato nel bytecode compilato
- **Framework core:** LangChain (`langchain-core`, `langchain-openai`, `langchain-google-genai`)
- **Provider LLM:** OpenAI (GPT-4o, 4o-mini, o1) e Google Gemini (1.5/2.0/3.x Flash e Pro)
- **Toolkit UI:** Tkinter (`gui_app.py`) e PyQt6 + qt-material (`edge-agent/`)
- **Framework ML:** PyTorch + torchvision per la classificazione delle pagine DINOv2 ViT-S/14 (opzionale, degrada al solo riconoscimento via LLM)
- **Database:** Nessuno. Dizionari in memoria, ground truth CSV, file JSON di output
- **Entry point:** `main.py` (CLI e shim `--gui`), `gui_app.py` (Tkinter), `edge-agent/edge_agent.py` (PyQt6 diretto)
- **Stato:** Proof of concept (prototipo). Nessun test, nessuna CI, nessun Docker, nessuna configurazione del linter. `develop` è il branch di lavoro, `master` è il principale.

---
*Generato da codebase-mapper*
