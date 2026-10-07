# 0016 - Un adapter per famiglia di modelli

- **Stato:** Accettato
- **Data:** 2026-09-29
- **Interessa:** `extraction/model_adapters.py`, `extraction/llm_factory.py`, `extraction/vlm_client.py`
- **Test:** `tests/test_llm_factory.py`, `tests/test_vlm_call.py`
- **Misura:** `.codebase-xray/baselines/2026-09-29-gemini-3.8-flash-thinking-low/`
- **Correlati:** [0004](0004-budget-retry-derivato-dalle-aree.md)

## Contesto

Ciò che cambia da una famiglia di modelli all'altra era deciso da controlli
sulla stringa del nome, sparsi in due moduli:

- `llm_factory.py` inviava `LLM_THINKING_LEVEL` solo se il nome conteneva
  `thinking`, e rifiutava provider e modello incoerenti con i prefissi `gpt-` e
  `gemini`;
- `vlm_client.py` sceglieva la strategia di output con `"gemini" in model` e con
  la sottostringa `gemini-1.5`, e ripeteva tre volte la costruzione di `_meta`.

Il 2026-09-29 la prima baseline su `gemini-3.8-flash` ha mostrato il costo
concreto: il `.env` chiedeva `LLM_THINKING_LEVEL=low`, ma nessun modello Gemini 3
ha `thinking` nel nome, quindi il valore spariva senza avviso e il modello
lavorava al suo default, `high`. Per Gemini 3 LangChain usa `thinking_level`
(`low`/`medium`/`high`); per Gemini 2.5 `thinking_budget` in token; per i modelli
di ragionamento OpenAI `reasoning_effort`. Una regola sul nome non può reggere
tre meccanismi diversi.

## Decisione

`extraction/model_adapters.py` contiene un adapter per famiglia. Ogni adapter sa
come costruire il modello LangChain (safety settings, profondità di
ragionamento) e come chiedere e leggere una risposta strutturata:

| Famiglia (prefisso) | Output strutturato | Ragionamento |
|---|---|---|
| `gpt-*`, `o1*`, `o3*`, `o4*` | `with_structured_output` | non gestito |
| `gemini-1.5*` | `json_mode` con schema | non supportato |
| `gemini-3*` | JSON libero + validazione Pydantic | `thinking_level` |
| altri `gemini-*` (2.0, 2.5) | JSON libero + validazione Pydantic | non gestito |

`adapter_for()` è l'unica regola nome → famiglia, con la prima corrispondenza
vincente (le famiglie specifiche prima del genitore). Un nome fuori da ogni
famiglia viene rifiutato, non trattato come OpenAI. `create_chat_model()` tiene
la risoluzione della chiave e verifica che il provider sia quello della famiglia;
`call_vlm()` delega all'adapter e costruisce `_meta` una volta sola.

`LLM_THINKING_LEVEL` vuoto lascia il default del modello; un valore fuori da
`low`/`medium`/`high` blocca la creazione del modello; un livello chiesto a una
famiglia che non lo gestisce produce un `UserWarning` e viene ignorato. Nessun
caso resta silenzioso.

## Alternative valutate

- **Catalogo esplicito modello per modello** (famiglia e prezzo in una tabella
  unica). Più rigido e avrebbe eliminato anche il costo a zero dei modelli senza
  prezzo, ma ogni nuovo modello avrebbe richiesto una modifica al codice. Scelta
  dell'utente: regole per famiglia, così un nuovo `gemini-3.x` funziona senza
  toccare nulla.
- **Correggere solo la condizione su `thinking`.** Chiudeva il sintomo e lasciava
  le altre quattro regole sul nome dove erano.
- **Mappare i livelli su `thinking_budget` per Gemini 2.5 e su `reasoning_effort`
  per OpenAI.** Rimandato: nessun modello del catalogo lo usa e su questa macchina
  non c'è una chiave OpenAI per verificarlo. Oggi quelle famiglie avvisano.

## Conseguenze e verifica

Con `LLM_THINKING_LEVEL=low` il livello arriva ora a `gemini-3.8-flash`. Misura
su 3 run per livello, stesse 9 schermate e stesso ground truth: accuratezza
totale identica (218 su 231 valutazioni con `high` e con `low`, NDG e
denominazioni sempre corretti), token di output -65%, costo per schermata da
circa $0,039 a $0,024, latenza per schermata dimezzata. Con `low` la
`filiale_relazione` troncata passa da 5 a 9 casi su 18 mentre gli errori di sola
spaziatura scendono da 5 a 1: con 3 run la differenza può essere rumore. Il
default spedito nel pacchetto non cambia con questa decisione.

`gemini-2.0-flash-thinking-exp`, che prima riceveva `thinking_level` perché il
nome conteneva `thinking`, ora appartiene alla famiglia Gemini 2.x e avvisa.

`test_thinking_level_reaches_gemini_3_models`, `test_thinking_level_on_a_family_without_it_warns`,
`test_invalid_thinking_level_is_refused` e `test_model_outside_every_family_is_refused`
sono falliti sul codice precedente e passano ora. I sei test di `test_vlm_call.py`
fissano, con l'SDK del provider finto, il comportamento per famiglia che il
refactoring doveva conservare: sono passati prima e dopo, e falliscono se si
altera la strategia di Gemini 1.5, il ruolo del prompt OpenAI o la richiesta di
JSON a Gemini 3.

Il router dell'edge-agent (`edge-agent/llm_router.py`, SDK OpenAI senza
LangChain) non passa dagli adapter e non invia un livello di ragionamento:
anche lui lavora al default del modello.
