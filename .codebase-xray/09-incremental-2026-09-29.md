# Aggiornamento incrementale 2026-09-29

Aggiornamento mirato sopra il run `poc-data-extraction-20260912-175144`, non una nuova analisi
completa. Copre il commit `4b5cac6` (branch `develop`) più le modifiche **non committate** elencate
sotto. I file 01–08 restano quelli del run del 2026-09-12: dove questo documento li contraddice,
vale questo documento per il solo perimetro indicato.

## Modifiche coperte (working tree non committato)

| File | Modifica |
|---|---|
| `edge-agent/env_key.py` | **Nuovo**, solo stdlib. `sanitize_key` (`edge-agent/env_key.py:25`), `write_key` (`edge-agent/env_key.py:39`), `main` (`edge-agent/env_key.py:66`): unico punto che scrive `LLM_API_KEY` in un `.env`; eseguibile come script con la chiave in `EDGE_AGENT_PACKAGE_KEY`. |
| `edge-agent/bootstrap.py` | Rimossi `_save_env_key` e `_sanitize_key_input` (duplicati di quanto sopra); `_ensure_api_key` (`edge-agent/bootstrap.py:196`) usa `env_key.sanitize_key` e `env_key.write_key` (`edge-agent/bootstrap.py:211`, `:220`). Il dialog dice a chi chiedere la chiave. |
| `build_exe.bat` | Chiede all'avvio una chiave opzionale (`build_exe.bat:10`), la scrive solo in `dist\EdgeAgent\.env` via `env_key.py` (`build_exe.bat:103`) e nomina lo zip `_CON-CHIAVE`; chiave non valida → uscita 1 senza zip. Il guard sul `config.ini` resta. File normalizzato a CRLF. |
| `tests/test_env_key.py` | 3 test sul `.env` del pacchetto letto con python-dotenv. |
| Modello di default `gemini-3.8-flash` | Su richiesta dell'utente: `edge-agent/defaults/env.template:3`, `.env.example:9`, fallback `edge-agent/bootstrap.py:37`, `edge-agent/config.ini:21` (router), `AgentConfig.DEFAULT_GEMINI_MODEL` (`edge-agent/config.py:36`). Aggiunto a `PROVIDER_MODELS` e a `PRICING_PER_1M` (`extraction/config.py:32`, `:54`; $0,75/$3,75 fino al 2026-12-31). `gemini-3.6-flash` resta disponibile. |
| `tests/test_pricing.py` | Ogni modello di default spedito (`env.template`, `.env.example`) deve avere un prezzo: senza, `estimate_cost_usd` restituisce 0 in silenzio. Fallito sul 3.8 prima del prezzo, verde dopo. |
| `.codebase-xray/baselines/2026-09-29-gemini-3.8-flash/` | Prima baseline con provider reale: ground truth bozza, 3 run, riepilogo, soglia proposta. |
| `README.md`, `docs/02`, `docs/07`, `docs/08`, `docs/09`, `docs/10`, `docs/how-it-works.md`, `CLAUDE.md`, `AGENTS.md` | Documentano chiave precompilata, modello 3.8, baseline; conteggio test 178; avviso sul `dati.csv` storico. |
| `claude_.bat` | Eliminazione preesistente, non parte di questo aggiornamento. |

Riferimenti superati dal refactoring: `03-flows.md:81` cita `_ensure_api_key` a
`edge-agent/bootstrap.py:236` (ora `:196`); il run storico `20260911` cita `_save_env_key`, che non
esiste più. I run storici non sono stati modificati.

## Verifiche eseguite oggi

| Verifica | Esito |
|---|---|
| `python -m pytest tests` (`.venv`, Python 3.13) | Dopo la chiave precompilata: **176 passed, 3 warnings in 30.88s**. Dopo modello e prezzo 3.8: **178 passed, 3 warnings in 20.94s**, exit 0 (avvisi xFormers come nel run precedente). Esecuzioni nuove, non il 173 del 2026-09-12. |
| Mutazione di `env_key.main`: niente `sanitize_key`, niente guard sulle andate a capo | I 2 test di rifiuto falliscono (verificato), poi modulo ripristinato. |
| Blocco chiave di `build_exe.bat` estratto in un harness, eseguito con `cmd /c` su `dist\EdgeAgent` fittizia | Con chiave: zip `_CON-CHIAVE`, `.env` con chiave, exit 0. Senza: prompt, zip normale, `.env` vuoto, exit 0. Chiave con `=`: messaggio, nessuno zip, exit 1. Build PyInstaller completa **non** eseguita. |
| `python main.py` con `gemini-3.6-flash` e `gemini-3.7-flash` | **Fallito**: la chiave del `.env` locale era rifiutata da Google (`400 API_KEY_INVALID`, confermato su `GET /v1beta/models`), ed è stata sostituita dall'utente. |
| `python main.py` con `gemini-3.8-flash`, 3 run | **72/77, 73/77, 73/77** (93,5-94,8%); $0,33-0,36 per 9 schermate; NDG e denominazioni corretti in tutti i run. Dettagli in [baselines/2026-09-29-gemini-3.8-flash](baselines/2026-09-29-gemini-3.8-flash/README.md). |

## Stato dei finding

| ID | Stato | Nota |
|---|---|---|
| DQ-04 | **risolto** | `CLAUDE.md` e `AGENTS.md` dichiarano 176 test, pari all'esecuzione di oggi. |
| XQ-R12 · media · **nuovo** · `verified` | aperto | Con tutte le schermate in errore (es. chiave non valida) `extraction/cli.py::main` (`extraction/cli.py:318`) stampa `OVERALL (RAW): 0/0 = 0.00%` e un costo di `$0.0000` ed esce con **codice 0**: gli errori per schermata sono solo righe `ERROR extracting` (`extraction/cli.py:254`). Un run di baseline fallito per intero è indistinguibile, per exit code, da un run riuscito. Stessa famiglia di XQ-R09. |
| XQ-D05 · bassa · **nuovo** · `verified` | aperto | Il `mnt/data/dati.csv` presente nella storia git (rimosso in `e8c677c`) descrive 5 screenshot della vecchia interfaccia PEF (pratica TICCHI/CABRAS, ~2152x1180), non i 9 attuali "Nuova PEF 3.0" (pratica LUNARDI, 848x679). Ripristinarlo produrrebbe una valutazione sistematicamente falsa. Documentato in `CLAUDE.md`. |

Un ground truth **bozza** per i 9 screenshot attuali (77 righe) è stato trascritto a vista in
`mnt/data/dati.csv` (ignorato da git) e copiato nella cartella della baseline. Non è ancora
verificato da una persona: finché non lo è, la soglia proposta resta una proposta.

Osservazioni dalla baseline, non ancora promosse a finding:

- `filiale_relazione` troncato al codice (`3749`) dal retry HEADER su 5 valutazioni su 18; `_attempts`
  non conserva i valori per passaggio, quindi la fusione retry/main non è verificabile dagli output.
- Il budget di retry è consumato per intero su tutte le 9 schermate (45 chiamate), coerente con
  OPEN_POINTS 1.1.
- `LLM_THINKING_LEVEL` si applica solo ai modelli con `thinking` nel nome, quindi non a
  `gemini-3.8-flash`, che pure supporta i livelli di ragionamento. I token di completamento
  (5-7 mila per schermata) pesano circa il 57% del costo; se includano il ragionamento non è
  stato verificato.
