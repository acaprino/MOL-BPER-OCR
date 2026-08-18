# 0002 - Riconoscimento pagina: ROI sul contenuto e coseno centrato

- **Stato:** Accettato
- **Data:** 2026-08-17
- **Interessa:** `edge-agent/page_classifier.py`
- **Test:** `tests/test_page_classifier.py`
- **Dipende da:** [0001](0001-normalizzazione-inquadratura-frame.md)

## Contesto

`BPERPagePrototypeClassifier` riconosce quale delle 9 pagine BPER è a schermo confrontando
l'embedding DINOv2 ViT-S/14 del frame con 9 prototipi, uno per pagina, via similarità coseno.

Tre difetti sovrapposti lo rendevano inutilizzabile.

### La ROI inquadrava il browser, non l'applicativo

`crop_roi = (0.0, 0.12, 1.0, 0.30)` è la striscia orizzontale fra il 12% e il 30% dell'altezza: sui
riferimenti è la barra delle tab del browser. Da sola costava 4 pagine su 9.

### Il CenterCrop scartava l'85% della striscia

La transform era `Resize(224) + CenterCrop(224)`. `T.Resize` con un intero scala il lato **corto**:
un ritaglio 847x122 diventa 1555x224, e il `CenterCrop` successivo tiene i 224 px centrali, cioè il
**14.4% della larghezza**. Al modello arrivava un quadrato contenente la coda della parola
"...atiche" e una X di chiusura tab. Nessun contenuto di pagina.

### Il coseno grezzo rendeva la soglia inesprimibile

Nove pagine dello stesso applicativo condividono quasi tutti i pixel. La componente comune domina il
coseno, e la parte che distingue una pagina dall'altra è residuale. Misurato sui prototipi stessi:

| grandezza | valore |
|---|---|
| similarità fra pagine **diverse** | 0.91 - 0.9997 |
| margine fra prima e seconda classificata | 0.0001 - 0.0112 |
| `similarity_threshold` in vigore | 0.70 |

La soglia non rifiutava mai nulla, perché nulla scendeva sotto 0.91. E con margini dell'ordine di
0.003 qualunque perturbazione dell'inquadratura ribaltava l'ordine: l'etichetta era rumore.

## Decisione

Tre modifiche, misurate una alla volta.

**ROI sull'area applicativa:** `DEFAULT_CROP_ROI = (0.0, 0.20, 1.0, 0.98)`. Esclude la cromatura del
browser, che varia con le tab aperte dell'operatore e non porta informazione sulla pagina.

**Resize schiacciato, senza CenterCrop:** `Resize((EMBED_SIDE, EMBED_SIDE))` con `EMBED_SIDE = 224`,
multiplo di 14 (patch size di ViT-S/14). Comprimere l'intera ROI nel quadrato conserva tutto il
contenuto; le 9 pagine differiscono per la disposizione del contenuto, non per le proporzioni.

**Punteggio su coseno centrato:** `_refresh_proto_matrix()` calcola il centroide dei prototipi e lo
sottrae sia ai prototipi sia alla query prima del confronto. Resta solo ciò che distingue una pagina
dalle altre. Con un solo prototipo la differenza è il vettore nullo, quindi si resta sul coseno
grezzo. Soglia ricalibrata: `DEFAULT_SIMILARITY_THRESHOLD = 0.35`.

## Misure

Il fatto centrale, controintuitivo: **la centratura non cambia quale pagina vince.** Cambia di trenta
volte il margine con cui vince, ed è quello che rende la soglia esprimibile.

Accuratezza sui 9 riferimenti, per configurazione e per inquadratura di ingresso:

| ROI + transform | ingresso | corrette | margine medio |
|---|---|---|---|
| tab strip + CenterCrop (precedente) | finestra | 5/9 | 0.0023 |
| tab strip + CenterCrop (precedente) | monitor intero | **1/9** | 0.0059 |
| contenuto + squash | finestra | **9/9** | 0.0036 |
| contenuto + squash | monitor intero | 4/9 | 0.0027 |
| contenuto + squash + centratura | finestra | **9/9** | **0.1165** |

Robustezza della configurazione adottata, con l'inquadratura normalizzata secondo
[0001](0001-normalizzazione-inquadratura-frame.md):

| variazione | corrette |
|---|---|
| scala finestra 0.8x / 1.0x / 1.4x / 1.8x / 2.4x | 9/9 |
| scala finestra 0.6x | 8/9 |
| proporzioni alterate x1.0/y1.4, x1.4/y1.0, x1.0/y0.8 | 9/9 |

Separazione fra match e non-match, che giustifica la soglia 0.35:

| ingresso | punteggio centrato |
|---|---|
| match corretti (9 pagine x 3 scale) | 0.664 - 0.982 |
| desktop uniforme | 0.096 |
| grigio medio pieno | 0.200 |

## Alternative valutate

**Tenere il coseno grezzo alzando la soglia.** Impossibile: le pagine diverse stanno fra 0.91 e
0.9997, non esiste un valore che accetti la prima e rifiuti la seconda.

**Token di patch DINOv2 con matching spaziale, o una testa addestrata.** Avrebbe più capacità
discriminante, in particolare fra le pagine che differiscono solo per un tooltip aperto (5, 6, 7, 8).
Scartata perché non serviva: la configurazione scelta è a 9/9 con margine di 0.11 **sulle
inquadrature che la normalizzazione gestisce** (vedi la precisazione in coda), e un
addestramento richiederebbe un dataset di catture reali che non abbiamo.

**Solo la correzione geometrica, senza centratura.** Porta a 9/9 sulle finestre, quindi i test di
riconoscimento passerebbero. Scartata perché lascia i margini a 0.0036: il classificatore sarebbe
corretto e allo stesso tempo incapace di rifiutare una schermata che non è una pagina BPER, che è
esattamente il difetto che ha bloccato la sessione descritta in
[0001](0001-normalizzazione-inquadratura-frame.md).

## Conseguenze

La cache dei prototipi esistente diventa inservibile: è stata costruita con la geometria precedente.
Non se ne accorgerebbe da sola, ed è la ragione di
[0003](0003-chiave-cache-prototipi-con-geometria.md).

Il primo avvio dopo questa modifica ricostruisce i 9 prototipi, con un ritardo di alcuni secondi.

La soglia 0.35 è calibrata su due soli negativi sintetici, perché non abbiamo schermate reali
non-BPER. È conservativa rispetto al margine misurato (il match corretto più debole è a 0.664, quasi
il doppio della soglia), ma va rivista se si dovessero osservare falsi positivi su schermate reali
diverse dalle 9 previste.

`EMBED_SIDE` è esportato invece di essere murato nella transform: fa parte della chiave di cache di
[0003](0003-chiave-cache-prototipi-con-geometria.md) e cambiarlo deve invalidare i prototipi.

## Precisazione (2026-08-18)

Due misure di questo ADR sono state contestate dalla peer review incrociata e le
contestazioni sono state accettate:

- **Il 9/9 non è prova di comportamento sul campo** (finding F11). Il test costruisce
  il frame incollando la finestra centrata su una tela, che è l'unica delle sette
  inquadrature realistiche che `detect_app_rect()` gestisce. Misura il caso favorevole.
- **Il 4/9 su monitor intero non descrive il classificatore spedito** (finding F07). La
  riga della tabella è `contenuto + squash` **senza** centratura, e non è mai stato
  verificato se quei quattro superino la soglia 0.35.

Le decisioni prese qui (ROI sul contenuto, squash, coseno centrato, chiave di cache)
restano valide e sono miglioramenti reali. Ciò che non regge è l'uso di questi numeri
come prova che il riconoscimento per prototipi basti in esercizio:
[0006](0006-router-llm-come-predefinito.md) lo sostituisce come predefinito.
