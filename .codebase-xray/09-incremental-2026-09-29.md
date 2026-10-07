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

## Seconda parte: adapter per famiglia di modelli (non committata sopra `a4f4cda`)

Stato alla data dell'analisi. Questa parte è stata poi committata il 2026-10-07 in `acb0cc0`, senza altre modifiche.

| File | Modifica |
|---|---|
| `extraction/model_adapters.py` | **Nuovo.** `ModelAdapter` e le famiglie `OpenAIAdapter`, `GeminiAdapter` (2.x), `Gemini15Adapter`, `Gemini3Adapter` (`extraction/model_adapters.py:83`, `:118`, `:137`, `:184`, `:196`); `_FAMILIES` e `adapter_for` (`:207`, `:218`) sono l'unica regola nome → famiglia; `validate_thinking_level` (`:228`). Contiene ora `_extract_json_str` (`:61`) e le due istruzioni del catalogo prompt usate per l'output. |
| `extraction/llm_factory.py` | `create_chat_model` (`extraction/llm_factory.py:21`) accetta `thinking_level` (default `LLM_THINKING_LEVEL`), rifiuta nomi fuori famiglia e provider incoerenti, delega la costruzione all'adapter. |
| `extraction/vlm_client.py` | `call_vlm` (`extraction/vlm_client.py:22`) delega all'adapter e costruisce `_meta` una volta; eliminati `_GEMINI_JSON_SCHEMA_MODELS` e `_call_vlm_gemini_freeform`. `estimate_cost_usd` ora a `:14`, `call_vlm_with_retry` a `:63`. |
| `tests/test_llm_factory.py`, `tests/test_vlm_call.py` | 6 + 6 test (vedi sotto). |
| `docs/adr/0016-adapter-per-famiglia-di-modelli.md` e indice | Decisione, alternative, misura. |
| `CLAUDE.md`, `AGENTS.md`, `README.md`, `docs/02`, `docs/04`, `docs/09`, `docs/10`, `docs/how-it-works.md` | Vincolo 5, riga `LLM_THINKING_LEVEL`, elenco moduli, conteggio test 190, riferimenti di riga. |

Riferimenti superati: XQ-R11 cita `_extract_json_str` a `extraction/vlm_client.py:42`, ora
`extraction/model_adapters.py:61`; XQ-R07 cita `estimate_cost_usd` a `extraction/vlm_client.py:26` e
il parsing a `:198`, ora `:14` e `extraction/model_adapters.py:161` (`GeminiAdapter.invoke`). Il
contenuto dei due finding non cambia.

### Verifiche di questa parte

| Verifica | Esito |
|---|---|
| `tests/test_vlm_call.py` sul codice **precedente** | 6 passed (caratterizzazione). Con strategia Gemini 1.5, ruolo del prompt OpenAI e MIME JSON alterati: 3 falliti, poi ripristinato. |
| `tests/test_llm_factory.py` sul codice precedente, con il solo parametro aggiunto | 4 falliti per le ragioni attese (livello `None` invece di `low`, nessun avviso, livello non valido e modello fuori famiglia accettati), 2 passati (default e provider incoerente, invariati). |
| `python -m pytest tests` dopo il refactoring | **190 passed, 3 warnings in 50.39s** (solo xFormers). |
| `python main.py`, `gemini-3.8-flash`, `LLM_THINKING_LEVEL=low`, 3 run | 72, 73, 73 su 77, identico a `high`; costo $0,211-0,222 contro $0,332-0,364; token di output -65%; latenza per schermata dimezzata. `filiale_relazione` troncata 9/18 contro 5/18. [Dettagli](baselines/2026-09-29-gemini-3.8-flash-thinking-low/README.md). |

### Rischio collegato, non introdotto ma ampliato

`edge-agent/edge_agent.py::main` crea `MainWindow(config)` fuori dal `try` che protegge l'import:
un `ValueError` da `create_chat_model` (chiave mancante o provider incoerente già prima; ora anche
livello di ragionamento non valido o modello fuori famiglia) chiude l'eseguibile windowed senza
finestra, con la sola traccia in `edge-agent.log`. Con il template spedito non si verifica.

## Terza parte: benchmark OCR su CPU e prova di fine-tuning (nessuna modifica al codice)

Solo misure: nessun file sorgente, test o configurazione modificato. Rapporto completo in
[baselines/2026-09-29-ocr-cpu-benchmark](baselines/2026-09-29-ocr-cpu-benchmark/README.md).

- OCR classici e VLM confrontati su profili CPU `pc4` (4 core) e `vdi2` (2 core) su Modal: RapidOCR
  PP-OCRv6 small legge 64/72 valori in 1,9 s (2,5 s su 2 core); i VLM (LightOnOCR, PaddleOCR-VL)
  richiedono minuti per schermata; Falcon-OCR non esegue su CPU.
- Prima prova RapidOCR + LiLT (MIT) addestrato su 38 scatti live con etichette Gemini: 61% dei
  campi sulla pratica LUNARDI mai vista, +0,45 s su 4 core. Limite: dati di addestramento.
- Osservazione che tocca il vincolo 13: gli scatti live sono finestre "Pool01-VDI" a ~1890 px, fuori
  dalla famiglia calibrata; la baseline Gemini del 2026-09-29 ha girato tutta sul percorso file
  calibrato (`_content_crop: calibrated` su 9/9), quindi non rappresenta il percorso live.
- Dal conteggio delle sorgenti nelle 6 baseline Gemini: il retry HEADER, quando decide il valore,
  sbaglia 14 volte su 16; il passaggio anchor non decide mai un valore valutato.
- Risorsa esterna creata: volume Modal `bper-lilt-spike` con i pesi addestrati (dati BPER), da cancellare.
