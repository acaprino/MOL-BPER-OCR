# poc-data-extraction - Guida al codice

Un proof of concept in Python che estrae campi strutturati dagli screenshot dell'applicativo bancario italiano BPER con una pipeline Vision-LLM multi-pass (OpenAI / Gemini via LangChain), poi valuta ogni campo rispetto a un CSV di ground truth e riporta l'accuratezza per campo e il costo per chiamata. Un solo motore di estrazione, tre interfacce: batch da CLI, GUI desktop Tkinter e un edge-agent PyQt6 con cattura dal vivo dello schermo.

## Documenti

| # | Documento | Descrizione |
|---|----------|-------------|
| 0 | [Sintesi per tutti](00-executive-summary.md) | Cosa fa il progetto, perché esiste e il suo stato onesto: in parole semplici, senza bisogno di background tecnico. |
| 1 | [Panoramica](01-overview.md) | Cosa fa il progetto, a chi serve e perché è un banco di misura più che un prodotto. |
| 2 | [Funzionalità](02-features.md) | Le capacità, raggruppate: estrazione multi-pass, astrazione dei provider, valutazione di accuratezza/costi e lo stack di cattura dal vivo dell'edge-agent. |
| 3 | [Tech Stack](03-tech-stack.md) | Ogni dipendenza e cosa fa davvero, più i pacchetti orfani e il pinning incoerente. |
| 4 | [Architettura](04-architecture.md) | Il core `extraction/` senza UI, la cucitura della factory LLM, il sottosistema edge-agent e il flusso dati del result dict. |
| 5 | [Workflow](05-workflows.md) | Tracce passo passo della pipeline, dell'esecuzione batch CLI, della valutazione di accuratezza, della cattura dal vivo e del routing delle pagine. |
| 6 | [Data Model](06-data-model.md) | Il result dict, gli schemi Pydantic costruiti da `FIELD_KEYS` e la tassonomia canonica a quattro pagine. |
| 7 | [Getting Started](07-getting-started.md) | Configurazione al primo avvio, i file da leggere per primi, dove fare le modifiche più comuni e le insidie che mordono il primo giorno. |
| 8 | [Domande Aperte](08-open-questions.md) | Discrepanze codice-vs-documentazione, l'incidente della chiave trapelata e i fatti di dominio BPER che solo il team può confermare. |
| 9 | [Anatomia del progetto](09-project-anatomy.md) | L'albero delle directory, i file di configurazione, le env var reali (verificate sul codice), i comandi di esecuzione e le sequenze di avvio. |
| 10 | [Guida alla configurazione](10-configuration-guide.md) | Percorso guidato di configurazione, profili OpenAI-vs-Gemini, ricette copia-incolla e troubleshooting errore per errore. |
| 11 | [Glossario](11-glossary.md) | Definizioni in parole semplici dei termini bancari italiani (`ndg`, `fido`, `soggetti`, …) e del vocabolario tecnico usato ovunque altrove. |

## Percorsi di lettura

- **Lettori non tecnici:** parti dalla [Sintesi per tutti](00-executive-summary.md) e tieni aperto il [Glossario](11-glossary.md) accanto a qualsiasi altra cosa tu legga. Il ponte tra la sintesi e i documenti tecnici è la [Panoramica](01-overview.md).
- **Nuovo al progetto (sviluppatore):** [Panoramica](01-overview.md) → [Funzionalità](02-features.md) → [Getting Started](07-getting-started.md) → [Workflow](05-workflows.md). Poi scorri [Domande Aperte](08-open-questions.md) prima di eseguire qualsiasi cosa: il `dati.csv` mancante, il `CLAUDE.md` non aggiornato e la riscrittura della cronologia per la chiave trapelata altrimenti ti costeranno tempo.
- **Devi correggere un bug o estrarre un nuovo campo:** [Getting Started](07-getting-started.md) (mappa dei file) → [Data Model](06-data-model.md) (le ramificazioni di `FIELD_KEYS`) → [Workflow](05-workflows.md) (interni della pipeline) → [Guida alla configurazione](10-configuration-guide.md) (flag di debug, troubleshooting).
- **Stai rivedendo l'architettura o le scelte tecnologiche:** [Architettura](04-architecture.md) → [Tech Stack](03-tech-stack.md) → [Anatomia del progetto](09-project-anatomy.md) → [Domande Aperte](08-open-questions.md) per gli spigoli noti e le assunzioni non verificate.

## Fatti chiave

- **Linguaggio:** Python 3.8+ dichiarato; 3.12/3.13 nella pratica (il launcher Windows preferisce il 3.13)
- **Framework core:** LangChain (`langchain-core`, `langchain-openai`, `langchain-google-genai`)
- **Provider LLM:** OpenAI (default, `gpt-4o`) oppure Google Gemini, commutati da `LLM_PROVIDER`
- **Toolkit UI:** Tkinter (`gui_app.py`) e PyQt6 + qt-material (`edge-agent/`)
- **Dominio:** 9 schermate BPER, 45 chiavi di campo italiane in `FIELD_KEYS`, 4 pagine canoniche
- **Classificatore ML pagine:** DINOv2 ViT-S/14 (opzionale; degrada senza torch)
- **Persistenza:** nessun database, dizionari in memoria scritti su file JSON/CSV
- **Entry point:** `main.py` (CLI; `--gui` → edge-agent), `gui_app.py` (Tkinter), `edge-agent/edge_agent.py` (PyQt6)
- **Stato:** proof of concept. Nessun test, nessuna CI, nessun Docker, nessun linter configurato. `develop` è il branch di lavoro, `master` il principale.
- **Sicurezza:** una chiave API OpenAI committata in `edge-agent/config.ini:23` è stata rimossa dall'intera cronologia git il 2026-07-21 (`git filter-repo` + force-push; la riga ora contiene il placeholder `REDACTED_OPENAI_API_KEY`). La rotazione della chiave è ancora da confermare; chi ha clonato prima del 2026-07-21 deve riclonare.

> Nota sull'autorevolezza: dove questi documenti e il `CLAUDE.md`/`README.md` del progetto non concordano, questi documenti seguono il codice. Tre fatti da tenere dritti: la terza UI è la GUI Tkinter `gui_app.py` (non esiste alcuna `app.py` Streamlit); il classificatore ML delle pagine è DINOv2 ViT-S/14 (non MobileNetV3); e il gate di confidenza degli anchor descritto in `CLAUDE.md` è attualmente inefficace nel codice.

---
*Generato da codebase-mapper*
