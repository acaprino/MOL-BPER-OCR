# Architecture Decision Records

Un ADR registra **una** decisione architetturale: il contesto in cui è stata presa, le alternative
scartate e le conseguenze che ci si porta dietro. Serve a rispondere alla domanda che nasce sei mesi
dopo, quando qualcuno guarda una costante e la trova arbitraria: *perché è così?*

## Perché questa cartella esiste

Il codice dice **cosa** fa. I commenti dicono **come**. Nessuno dei due dice quali alternative sono
state misurate e scartate, né quali numeri giustificano una soglia. Quel materiale, se non viene
scritto, si perde: resta la costante, si perde la ragione, e alla prima pulizia qualcuno la
"semplifica" ripristinando il difetto.

Il caso che ha fatto nascere la cartella è esattamente questo. Il router pagina aveva
`crop_roi = (0.0, 0.12, 1.0, 0.30)` e un `CenterCrop(224)`: due valori che sembrano tuning innocuo e
insieme facevano riconoscere 1 pagina su 9 in esercizio. Nessun commento diceva su cosa fossero
tarati, e nessun test lo verificava.

## Convenzioni

- **Un file per decisione**, numerato progressivamente: `NNNN-titolo-in-kebab-case.md`.
- **Lingua italiana** per il corpo, coerente con `docs/`. Identificatori, nomi di file e simboli
  restano in inglese come nel codice.
- **Immutabili una volta accettati.** Un ADR non si riscrive: se la decisione cambia, si scrive un
  ADR nuovo che *supera* il precedente, e sul vecchio si aggiorna solo il campo `Stato` con il
  rimando. La storia delle decisioni vale quanto la decisione corrente.
- **Numeri, non impressioni.** Se una decisione poggia su una misura, la misura va nell'ADR con
  quello che è stato misurato e come. Un ADR che dice "sembrava più robusto" non serve a nessuno.
- **Ogni ADR che cambia comportamento cita il test che lo protegge.** L'ADR spiega il perché, il
  test impedisce la regressione. Senza il test, l'ADR è un desiderio.

## Stati

| Stato | Significato |
|---|---|
| `Proposto` | Scritto, non ancora deciso |
| `Accettato` | In vigore, il codice lo rispetta |
| `Superato da NNNN` | Non più in vigore: la decisione è stata sostituita |
| `Rifiutato` | Valutato e scartato. Si conserva: sapere cosa è stato escluso e perché evita di riproporlo |

## Indice

| # | Titolo | Stato |
|---|---|---|
| [0001](0001-normalizzazione-inquadratura-frame.md) | Normalizzare l'inquadratura del frame sulla finestra applicativa | Accettato |
| [0002](0002-riconoscimento-pagina-roi-e-coseno-centrato.md) | Riconoscimento pagina: ROI sul contenuto e coseno centrato | Accettato |
| [0003](0003-chiave-cache-prototipi-con-geometria.md) | La chiave della cache prototipi include la geometria di embedding | Accettato |
| [0004](0004-budget-retry-derivato-dalle-aree.md) | Budget di retry derivato dal numero di aree | Accettato |
| [0005](0005-router-ml-invece-di-router-llm.md) | Router pagina ML invece di router LLM | Superato da 0006 |
| [0006](0006-router-llm-come-predefinito.md) | Router LLM come predefinito, ML come ripiego | Accettato |
| [0007](0007-conferma-stabilita-su-frame-invariato.md) | Confermare la stabilità con un frame invariato | Accettato |

## Da scrivere

Le scelte già portanti nel codice, elencate in `CLAUDE.md` sotto *Architectural Constraints*, non
hanno ancora un ADR. Vanno recuperate a ritroso quando si lavora sulla zona che le riguarda, non
tutte in una volta: un ADR scritto senza ricostruire il contesto reale è peggio di un ADR assente.

Candidati, in ordine di quanto costerebbe scoprirli nel modo sbagliato:

- Pipeline multi-passata anchor → main → retry, e perché l'ordine di post-processing è vincolante
- Prompt come dati in `prompts/*.json`, e l'asimmetria voluta fra fail-fast del catalogo prompt e
  degrado silenzioso del catalogo pagine
- Edge-agent solo locale, senza backend remoto
- Configurazione via variabili d'ambiente lette a import-time, e l'ordine di bootstrap che ne dipende
- Cattura ed estrazione disaccoppiate su un pool di thread daemon
- Output strutturato via Pydantic, con il ripiego a JSON libero sui Gemini recenti
