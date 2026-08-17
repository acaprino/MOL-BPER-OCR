# 0005 - Router pagina ML invece di router LLM

- **Stato:** Accettato
- **Data:** 2026-08-17
- **Interessa:** `edge-agent/config.ini`, `edge-agent/llm_router.py`, `edge-agent/page_classifier.py`
- **Correlati:** [0001](0001-normalizzazione-inquadratura-frame.md), [0002](0002-riconoscimento-pagina-roi-e-coseno-centrato.md)

## Contesto

Il riconoscimento della pagina ha tre modalità già implementate, scelte con `router=` in
`config.ini`:

| modalità | come funziona | costo per frame |
|---|---|---|
| `ml` | `MLPageRouter` su `BPERPagePrototypeClassifier`, DINOv2 locale | nessuno dopo il primo avvio |
| `llm` | `LLMPageRouter`, una chiamata VLM che legge la pagina e la classifica | una chiamata per frame instradato |
| `hybrid` | LLM, con ripiego su ML | come `llm`, più il ripiego |

Quando il router ML si è rivelato non funzionante in esercizio (1 pagina su 9, vedi
[0001](0001-normalizzazione-inquadratura-frame.md)), passare a `router=llm` era la soluzione
immediata: una riga di configurazione, nessun codice nuovo, e la chiave Gemini già disponibile
tramite `resolve_llm_settings()`.

La domanda da risolvere prima di scegliere era se DINOv2 fosse inadeguato al compito o solo mal
configurato.

## Decisione

Restare su `router=ml` e correggere il classificatore.

La misura che ha deciso: con la ROI sull'area applicativa e senza `CenterCrop`, DINOv2 separa
**tutte e 9 le pagine** già col coseno grezzo. Le features non erano il problema. Erano la ROI, la
transform e la regola di punteggio, tutte e tre correggibili senza aggiungere una chiamata di rete
nel ciclo di cattura.

Dettaglio delle misure in [0002](0002-riconoscimento-pagina-roi-e-coseno-centrato.md).

## Alternative valutate

**`router=llm`.** Sarebbe stato più rapido da mettere in esercizio, e resta il ripiego se il
classificatore dovesse cedere su schermate reali diverse dalle 9 previste. Scartata come scelta
predefinita per tre ragioni:

1. Aggiunge una chiamata VLM per frame instradato nel ciclo di cattura. Con `fps = 3` la protezione è
   `route_retry_seconds`, che limita i tentativi sui frame duplicati a uno al secondo: resta
   comunque un ordine di grandezza più costoso di un confronto di vettori locale.
2. Introduce una dipendenza di rete e una latenza in un percorso che l'operatore percepisce come
   interattivo: la stabilità richiede almeno 2 secondi di permanenza della schermata, e una risposta
   lenta o un errore di rete si traduce in schermate mancate.
3. Non era necessaria: il classificatore locale funziona.

**`router=hybrid`.** Prova LLM e ripiega su ML. Con il classificatore ML rotto, il ripiego era senza
valore, quindi in pratica equivaleva a `llm`. Con il classificatore corretto, il ripiego ha valore ma
l'ordine è invertito rispetto a quello utile: conviene tentare prima quello locale e gratuito.

**Router deterministico sul testo.** Le 9 pagine sono distinguibili da testo letterale: il riquadro
"Nota della richiesta", la tab attiva, il tooltip aperto, le colonne estese. Un match su poche
regioni ancora sarebbe esatto e gratuito. Scartata perché richiede codice nuovo e un motore OCR per
ottenere ciò che il classificatore corretto già fa a 9/9. Resta l'opzione più solida se in futuro le
pagine da distinguere aumentassero o diventassero più simili fra loro.

## Conseguenze

Il primo avvio scarica i pesi DINOv2 (~84MB) via torch.hub e richiede rete una volta sola. Senza
torch il classificatore si autodisabilita e il riconoscimento non funziona: `MLPageRouter` degrada a
disattivato invece di far cadere l'applicazione.

Il riconoscimento dipende ora da due condizioni che vanno tenute insieme: l'inquadratura normalizzata
([0001](0001-normalizzazione-inquadratura-frame.md)) e la geometria di embedding
([0002](0002-riconoscimento-pagina-roi-e-coseno-centrato.md)). Rompere l'una vanifica l'altra, ed è
il motivo per cui il test di riconoscimento parte da un frame a schermo intero e non dai prototipi.

`router=llm` resta implementato, configurato e funzionante. È il piano di ripiego, non codice morto:
va tenuto in funzione, e `config.ini` continua a portare le impostazioni del provider necessarie a
usarlo.
