# 0012 - Prototipi interamente nella popolazione live: la misura che lo 0011 aspettava

- **Stato:** Accettato
- **Data:** 2026-08-21
- **Interessa:** `tests/fixtures/frames/no-tooltip-rita/`, `tools/measure_tooltip_prototypes.py` (i template spediti restano invariati)
- **Misura:** `tools/measure_tooltip_prototypes.py`
- **Correlati:** [0011](0011-prototipi-tooltip-rimandati-purezza-di-popolazione.md), [0008](0008-classificatore-locale-prototipi-reali-e-classi-di-scarto.md), [0006](0006-router-llm-come-predefinito.md)

## Contesto

Lo [0011] aveva rimandato i prototipi delle pagine tooltip perche' mescolare
popolazioni di inquadratura dentro una classe (riferimenti ~848px, scatti ~1890px)
sposta la media verso nessuna delle due. Il pezzo mancante dichiarato: scatti diretti
delle pagine base senza tooltip, nella stessa forma.

Sono arrivati il 2026-08-21: 21 catture (`tests/fixtures/frames/no-tooltip-rita/`,
verbale nel manifest). Con i 17 del primo giro, tutte e nove le classi hanno per la
prima volta prototipi possibili **dentro una sola popolazione**: quella live, l'unica
che il classificatore serve (il percorso file non lo attraversa).

Due sorprese dalla verifica immagine per immagine:

1. Le coppie consegnate come "Note da richiesta 1b/1c" sono sulla tab **Note a
   Istruttoria**, che non e' tra le 9 classi: quattro negativi di processo veri,
   visivamente quasi identici alla pagina 9.
2. La pagina 9 si presenta con la sezione nota **compressa**; aperta cambia molto.
   La consegna contiene entrambe le viste.

## Misura

Prototipi solo da scatti diretti, meta' dentro e meta' tenuti fuori; i 9 riferimenti
declassati a informativi (altra popolazione, altro percorso).

| verifica | esito |
|---|---|
| scatti tenuti fuori, mai visti dai prototipi | **10/15** corretti |
| adozioni locali sbagliate (margine >= 0.10) | **1**: `1b -> 2`, margine 0.102 |
| errori sotto soglia (finirebbero all'LLM) | 4: `1d->2` 0.084; `2d->8` 0.019; `3c->6` 0.056; `4a->6` 0.036 |
| Note a Istruttoria adottate come pagina 9 | **0/2** con `SCARTO-fuori-processo-live`; era 3/4 senza, margini fino a 0.205 |
| pagina 9 aperta, con prototipo solo-chiusa | cadeva su **screen 5 con margine 0.220**; con chiusa+aperta nel prototipo l'errore sparisce |
| riferimenti (informativo) | 2/9: atteso, e' l'altra popolazione |
| negativi sintetici | ancora scartati (`SCARTO-vuoto`) |

## Lettura

**La purezza di popolazione funziona.** Stesse classi, stesso descrittore dello
[0011]: portando i prototipi dentro una sola popolazione, gli errori con margine
alto spariscono quasi tutti e il ripiego a margine contiene il resto. La confusione
6<->8 resta intrinseca (margini 0.019-0.056, tutti sotto soglia: all'LLM, come da
progetto [0006]).

**Le classi 1 e 2 convergono a risoluzione live.** La distinzione nasce dalla
finestra a 848px, dove entrano meta' colonne e lo scorrimento crea due viste
davvero diverse. A ~1890px la vista base mostra gia' quasi tutte le colonne: le due
classi condividono il contenuto e l'unica adozione sbagliata della misura e' proprio
`1 -> 2`, a un soffio dalla soglia (0.102). Con zoom ridotto e tutte le colonne
visibili (`rita-base-1e`) il margine crolla a 0.001. Non si decide qui: un'eventuale
fusione 1+2 e' una decisione di catalogo (spec dei campi comprese) e merita il suo
ADR quando il cablaggio del classificatore tornera' sul tavolo.

**Una pagina della stessa applicazione fuori dalle 9 classi e' il negativo piu'
pericoloso**: Note a Istruttoria somiglia alla 9 piu' di quanto la 6 somigli alla 8,
e senza contromisure viene adottata con margini pieni. La contromisura e' il
meccanismo gia' esistente dello [0008], le classi SCARTO, popolato **nella stessa
popolazione live** (`SCARTO-fuori-processo-live`, distinta da `SCARTO-fuori-processo`
che resta sui ritagli da registrazione: mescolarle ricreerebbe la malattia che
questa serie di ADR cura).

**Variante chiusa/aperta nella stessa classe, non in classi diverse.** Le due viste
della 9 sono la stessa pagina per il processo; separarle avrebbe raddoppiato le
classi per ogni sezione espandibile. Dentro la stessa classe il prototipo medio
regge, al costo di non poter testare la classe con il materiale attuale.

## Decisione

1. Il set di prototipi per un eventuale cablaggio local-first si costruisce
   **interamente nella popolazione live**: scatti diretti per le nove classi, piu'
   una classe di scarto live per le pagine BPER fuori processo. Mai mescolare
   popolazioni dentro una classe (regola dello [0011], ora con la controprova).
2. **Non si cabla ancora nulla**: i template spediti restano nove riferimenti + tre
   classi di scarto, `router = llm` resta il predefinito ([0006]). Il residuo
   dichiarato prima del cablaggio: classe 7 con un solo esemplare, classe 9 non
   testabile, confine 1/2 da decidere, e una sola pratica dietro ai negativi
   istruttoria.
3. Al prossimo giro di scatti servono: altre "Note da Richiesta" (per testare la 9),
   altri tooltip CONSAP DR BIS (pagina 7), e qualunque pagina BPER fuori processo
   (per irrobustire lo scarto live oltre le due pratiche di oggi).
