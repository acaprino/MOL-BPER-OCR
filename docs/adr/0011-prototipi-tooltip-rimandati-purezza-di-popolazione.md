# 0011 - Prototipi per le pagine tooltip: rimandati finche' la popolazione non e' pura

- **Stato:** Accettato
- **Data:** 2026-08-19
- **Interessa:** `edge-agent/assets/templates/bper/` (nessuna modifica: e' il punto)
- **Misura:** `tools/measure_tooltip_prototypes.py`
- **Correlati:** [0008](0008-classificatore-locale-prototipi-reali-e-classi-di-scarto.md), [0006](0006-router-llm-come-predefinito.md)

## Contesto

Con i 17 screenshot mirati consegnati dall'operatrice, le pagine tooltip (3, 6, 7, 8)
hanno per la prima volta piu' di un'immagine ciascuna, nella stessa forma dei nove
riferimenti: finestra intera, cattura diretta. L'esperimento: usarli come prototipi
aggiuntivi di quelle classi, meta' dentro e meta' tenuti fuori come test.

## Misura

| verifica | esito |
|---|---|
| i 9 riferimenti restano riconosciuti | **5/9** -- falliscono esattamente 3, 6, 7, 8 |
| scatti tenuti fuori, mai visti | 5/8 |
| pagina 3 (lista + tooltip) | 2/2, margini **0.386 e 0.431** |
| errori (tutti confusione 6 contro 8) | margini **0.004-0.036** |
| negativi | ancora scartati dalle classi SCARTO |

## Lettura

**Il crollo dei riferimenti e' di popolazione, non di contenuto.** I prototipi delle
classi tooltip mescolano due geometrie (riferimenti ~848px, scatti ~1890px): la media
si sposta verso la seconda e il riferimento `screen 6` cade su `screen 5`. E' la
stessa causa del crollo 9/9 -> 1/9 dello [0008], in forma piu' mite. La regola che ne
esce: **una classe di prototipi non mescola mai popolazioni di inquadratura**.

**La confusione 6 contro 8 e' intrinseca a questo descrittore ed e' gia' gestita.**
Quelle pagine differiscono per quale cella ospita un popup minuscolo; gli errori
portano margini sotto 0.04, cioe' sotto la soglia 0.10 del `local-first`: finirebbero
comunque all'LLM, che legge il testo invece di confrontare pixel. La misura conferma
il progetto del ripiego a margine invece di smentirlo.

**Avvertenza sul 2/2 della pagina 3:** i suoi prototipi sono gli unici "da lista" nella
popolazione degli scatti, quindi il riconoscimento potrebbe appoggiarsi in parte alla
geometria oltre che al contenuto. Non e' separabile con il materiale attuale.

## Decisione

Non si cabla nulla: i template spediti restano nove riferimenti + tre classi di
scarto, e la baseline sui riferimenti non si tocca. Gli scatti restano nel corpus
(`tests/fixtures/frames/tooltips/`) come materiale di misura.

Il pezzo mancante e' piccolo e concreto: **scatti diretti delle pagine base (1, 2, 4,
5, 9) senza tooltip**, nella stessa forma. Con quelli si costruisce un set di
prototipi interamente nella popolazione live, per tutte e nove le classi, senza
mescolare nulla, e la misura si ripete con `tools/measure_tooltip_prototypes.py`.
