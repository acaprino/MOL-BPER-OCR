# MutuiOnline BPER · Estrazione delle pratiche di credito

Il data entrista individua la pratica in Nuova PEF, apre soggetti, fidi, garanzie e note e raccoglie i dati della Scheda Privati. L’edge-agent segue le viste sul monitor e riunisce i valori in una riga Excel per NDG. Il tracciato comprende **45 campi**. La [guida al data entry](docs/flusso-data-entry.md) mostra dove leggerli e come recuperare una vista saltata.

## Dove iniziare

| Devo… | Riferimento |
|---|---|
| Seguire una pratica avanti e indietro e sapere cosa manca | [Passi dell’operatore](docs/flusso-data-entry.md) · [Navigazione dell’edge-agent](docs/navigazione-edge.md) |
| Riprendere il lavoro dopo un arresto o recuperare un backup | [Recupero ed esportazione delle sessioni](docs/recupero-sessioni.md) |
| Mantenere RapidOCR + LiLT e OCRia-nano-1 di LlamaIndex + LiLT | [Stato dei due percorsi, risultati e ciclo di aggiornamento](docs/ocr-lilt.md) · [Comandi di training](src/training/README.md) |
| Preparare schermate e valori revisionati | [Archivio delle pratiche e suddivisione dei dati](data/README.md) |
| Installare e usare l’app | [Avvio](docs/07-getting-started.md) · [Configurazione](docs/10-configuration-guide.md) |
| Riprodurre una sessione con pratiche sintetiche | [Simulatore](bper-emulator/README.md) · [Prove di cattura e replay](bper-emulator/live_test_README.md) |
| Modificare o integrare il motore | [Architettura](docs/04-architecture.md) · [API Python](docs/12-python-api.md) · [Indice completo](docs/INDEX.md) |

## Eseguire l’applicazione

Da Windows, con Python 3.12 o 3.13, `run_edge_agent.bat` prepara l’ambiente e apre la GUI. Il primo avvio chiede la chiave del provider se manca. Con le dipendenze e `.env` già configurati, dalla radice del repository:

| Comando | Risultato |
|---|---|
| `python src/edge-agent/edge_agent.py` | Cattura dal monitor, guida e correzioni nella tabella **Dati estratti**, export Excel |
| `python main.py` | Estrazione e confronto della pratica di riferimento con i valori di `data/dataset/valori.csv` |
| `python gui_app.py` | Estrazione da file selezionati con GUI Tkinter, con valutazione facoltativa |
| `python bper-emulator/serve_bper_simulator.py` | Simulatore web locale per esercitarsi su dati sintetici |

**Motore in uso.** CLI, Tkinter ed edge-agent estraggono i campi con un VLM OpenAI o Gemini. Il riconoscimento della schermata nell’edge-agent ha un router dedicato. I due percorsi OCR con LiLT si addestrano e si valutano offline. Per ciascuno si misura sia il testo letto sia il valore completo assegnato al campo.

## Chiavi API e cronologia Git

- **2026-07-21**: una chiave OpenAI committata in `src/edge-agent/config.ini` è stata **rimossa dall'intera cronologia git** (`git filter-repo` + force-push). Tutti gli hash dei commit sono cambiati. **Chi ha clonato prima di quella data deve ri-clonare**: un push o merge da un clone vecchio reintrodurrebbe la chiave nella cronologia.
- La riga `api_key` in `src/edge-agent/config.ini` ora è **vuota**. Il file è tracciato in git: **non inserire mai una chiave reale lì**. `AgentConfig` tratta come vuoto anche qualunque valore che inizi per `REDACTED`, perché un placeholder rimasto in giro aveva già oscurato le chiavi da ambiente rompendo il router in silenzio. `build_exe.bat` si rifiuta di impacchettare un `config.ini` con `api_key` non vuota.
- Le chiavi vanno in `.env` (gitignorato): `LLM_API_KEY` è l'unica variabile obbligatoria.
- Il router dell'edge-agent risolve le credenziali separatamente dal motore. La configurazione inclusa usa `router = llm`, mentre il default di `AgentConfig` è `ml`. Quando viene usato il router LLM, `resolve_llm_settings()` sceglie `config.ini [llm] api_key` se non vuota, poi per `gemini` `GEMINI_API_KEY` -> `GOOGLE_API_KEY` -> `LLM_API_KEY`, per `openai` `OPENAI_API_KEY` -> `LLM_API_KEY`. Il riconoscimento ML può essere locale, ma l'estrazione richiede comunque la chiave del provider.
