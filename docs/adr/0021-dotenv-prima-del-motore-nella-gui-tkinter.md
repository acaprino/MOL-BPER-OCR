# 0021 - Caricare dotenv prima del motore nella GUI Tkinter

- **Stato:** Accettato
- **Data:** 2026-10-16
- **Interessa:** `gui_app.py`
- **Test:** `tests/test_gui_config.py`

## Contesto

La configurazione del motore viene letta all'import di `extraction`. L'ingresso
diretto Tkinter importava il motore senza prima caricare `.env`, a differenza
della CLI. Mostrava inoltre `openai` e `gpt-4o` anche quando l'ambiente chiedeva
un altro provider o modello.

## Decisione

`gui_app.py` chiama `load_dotenv()` prima di importare `extraction`. Rimane la
precedenza predefinita della libreria: le variabili già esportate nell'ambiente
non vengono sovrascritte dal file. I selettori iniziali usano le costanti
effettive `LLM_PROVIDER` e `LLM_MODEL` del motore.

Il menu dei suggerimenti parte dal provider selezionato. La creazione del menu
non cambia il modello configurato, anche quando è un nome valido non presente
nel catalogo dei suggerimenti. Un successivo cambio esplicito di provider
mantiene il comportamento preesistente del relativo gestore.

## Alternative valutate

- **Chiedere di esportare sempre le variabili prima dell'avvio.** Mantiene
  l'asimmetria fra ingressi e rende invisibile la configurazione di `.env`.
- **Caricare `.env` dopo `extraction`.** È troppo tardi per le costanti lette
  dal motore all'import.
- **Invocare il cambio provider durante la costruzione dei widget.** Il gestore
  resetta il modello e perderebbe la selezione configurata, inclusi nomi non
  elencati nei suggerimenti.

## Conseguenze e verifica

L'avvio diretto della GUI legge la stessa configurazione iniziale del motore.
Non cambia il bootstrap dell'edge-agent e non introduce ricaricamento dinamico
della configurazione. L'utente può ancora inserire la chiave nel campo previsto.

I test avviano processi separati con `.env` sintetiche e controllano l'ordine
di import, la precedenza dell'ambiente e i widget Tk reali, mantenuti nascosti.
Non richiedono chiavi reali o chiamate VLM. Nei sistemi privi di display i soli
controlli dei widget possono essere saltati; il controllo di import resta attivo.
