# 0001 - Normalizzare l'inquadratura del frame sulla finestra applicativa

- **Stato:** Accettato
- **Data:** 2026-08-17
- **Interessa:** `edge-agent/frame_normalize.py`, `edge-agent/workers/capture/bper_capture_worker.py`
- **Test:** `tests/test_frame_normalize.py`, `tests/test_bper_capture_framing.py`

## Contesto

Ogni ritaglio del sistema è espresso in **coordinate relative**:

| Costante | Valore | Dove |
|---|---|---|
| `DEFAULT_CROP_ROI` | ROI del classificatore pagina | `edge-agent/page_classifier.py` |
| `CONTENT_CROP` | `(0.18, 0.12, 0.98, 0.98)` | `extraction/config.py` |
| `HEADER_IN_CONTENT` | `(0.00, 0.00, 1.00, 0.22)` | `extraction/config.py` |
| `RETRY_AREAS` | HEADER / BODY / FOOTER | `extraction/config.py` |

Tutte sono tarate sugli screenshot di riferimento in `mnt/data`, che sono **finestre di browser
848x679**. Gli stessi file sono anche i prototipi del classificatore
(`edge-agent/assets/templates/bper/screen N.png`).

`BPERCaptureWorker._grab_raw()` però cattura il **monitor intero** via `mss`. Su un frame
1920x1080 la frazione 0.12-0.30 non cade sulla stessa parte dell'interfaccia su cui era stata
tarata: cade dove capita, in funzione di dove si trova la finestra e di quanto è grande.

Il difetto si è manifestato in esercizio come riconoscimento pagina sempre sbagliato. Riproducendo la
condizione reale (finestra di riferimento incollata su un desktop 1920x1080) il classificatore ha
etichettato **8 pagine su 9 come `screen 9`**, con punteggi 0.885-0.907. Nel log della sessione reale
si leggeva «Note da Richiesta» a 0.840-0.921 su ogni singolo frame, per tutta la durata della
cattura: la stessa firma numerica.

La conseguenza a valle era peggiore dell'etichetta sbagliata. Una pagina etichettata male entra in
`captured_page_types`, e da quel momento ogni frame successivo finisce nell'uscita anticipata "già
acquisita" di `_capture_once()`. La sessione si blocca: una pagina acquisita su nove, sotto il nome
di un'altra, e nessun modo per l'operatore di recuperarla.

## Decisione

Riportare l'inquadratura sulla finestra applicativa **al momento della cattura**, dentro
`_grab_raw()`, prima di deduplicazione, routing ed estrazione.

`frame_normalize.normalize_frame()` prova due strategie in ordine di affidabilità:

1. **Rettangolo della finestra dal sistema operativo.** `find_window_rect()` enumera le finestre
   visibili con `user32` via `ctypes` e prende la prima il cui titolo contiene la sottostringa
   configurata. La sottostringa è `window_title_contains` in `config.ini`, che era già presente,
   già esposta nella UI in `capture_tab.py:100` e **non usata da nessuna parte**: questo la collega.
2. **Rettangolo dedotto dal contenuto.** `detect_app_rect()` confronta i quattro angoli del frame:
   se concordano, li assume come sfondo del desktop e prende il bounding box di ciò che ne differisce.
   Rinuncia quando gli angoli non concordano o quando il contenuto tocca un bordo, perché in quei
   casi non c'è sfondo su cui basarsi e la finestra probabilmente riempie il monitor.

Se nessuna delle due conclude, il frame passa **invariato**. Peggiorare l'inquadratura con un
ritaglio indovinato è peggio che lasciarla come è.

## Alternative valutate

**Ricostruire i prototipi da catture reali a schermo intero.** Sarebbe la soluzione più diretta:
adattare il classificatore alla realtà invece del contrario. Scartata perché non disponiamo di altre
immagini oltre alle 9 di riferimento, e perché legherebbe i prototipi a una risoluzione e a un
layout di finestra specifici, rendendoli fragili al primo cambio di postazione.

**Correggere solo le costanti di ritaglio per il caso a schermo intero.** Sposta il problema: ogni
risoluzione e ogni posizione della finestra vorrebbe costanti diverse.

**Ritaglio finestra con `pywin32`.** Equivalente in funzione, ma aggiunge una dipendenza a
`requirements.txt` per ottenere ciò che `ctypes` già dà con la libreria standard.

## Conseguenze

Il ritaglio corregge **sia** il riconoscimento pagina **sia** l'estrazione: `CONTENT_CROP` è tarato
sulle stesse finestre, quindi anche la pipeline riceveva un ritaglio spostato. Il test di
riconoscimento passa da 1/9 a 9/9, e regge scale della finestra da 0.8x a 2.4x e variazioni di
proporzioni del ±40% (vedi [0002](0002-riconoscimento-pagina-roi-e-coseno-centrato.md)).

La deduplicazione pHash ora confronta frame già ritagliati: cambiamenti sul desktop **fuori** dalla
finestra non contano più come frame nuovo. È un miglioramento, ma è un cambio di comportamento da
tenere presente se la deduplicazione dovesse sembrare troppo aggressiva.

`find_window_rect()` è specifico per Windows e restituisce `None` altrove, dove resta attivo il solo
rilevamento da contenuto. L'edge-agent è già di fatto solo Windows (`run_edge_agent.bat`, `mss` sul
monitor), quindi non introduce un vincolo nuovo, ma il ripiego evita che il modulo sia inimportabile.

`GetWindowRect` include i bordi invisibili di ridimensionamento introdotti da DWM, circa 8 px per
lato. Non è stato compensato con `DWMWA_EXTENDED_FRAME_BOUNDS` perché il riconoscimento regge
variazioni di proporzioni molto più grandi: 8 px sono irrilevanti e la compensazione costerebbe
un'altra chiamata di sistema per frame.

Il rilevamento da contenuto assume un desktop di colore uniforme attorno alla finestra. Con altre
finestre visibili agli angoli gli angoli non concordano e la funzione rinuncia, ricadendo sul frame
intero: torna il difetto originale, ma in modo silenzioso. È il limite noto di questa decisione, e la
ragione per cui la strategia basata sul titolo della finestra viene tentata **prima**.
