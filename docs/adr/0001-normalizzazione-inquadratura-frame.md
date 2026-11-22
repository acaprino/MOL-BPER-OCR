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

Tutte sono tarate sugli screenshot di riferimento in `data/dataset/pratiche/51350695`, che sono
**finestre di browser 846x677 a 850x680** (verificato file per file: la cifra "848x679" che questo ADR
riportava era generalizzata da un solo file). Dagli stessi file sono costruiti i prototipi del
classificatore (`edge-agent/assets/templates/bper/bper_page_prototypes.json`,
[0030](0030-prototipi-delle-pagine-distribuiti-con-l-app.md)).

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
di un'altra.

**Correzione (2026-08-18, peer review finding F02/F05).** Questo ADR diceva
"nessun modo per l'operatore di recuperarla": e' falso. `force_capture()` non
controlla l'appartenenza a `captured_page_types` (`bper_capture_worker.py`), i risultati si
accodano per job (`ingest_frame()` in `local_extraction_client.py`) e si consolidano per NDG
tramite `pick_best` (`consolidate()` in `practice_consolidation.py`). Il recupero e' **manuale e parziale**, non
assente: l'operatore puo' riacquisire la pagina con "Acquisisci ora". Resta vero che
la sequenza guidata non si sblocca da sola.

## Decisione

Riportare l'inquadratura sulla finestra applicativa **al momento della cattura**, dentro
`_grab_raw()`, prima di deduplicazione, routing ed estrazione.

`frame_normalize.normalize_frame()` prova due strategie in ordine di affidabilità:

1. **Rettangolo della finestra dal sistema operativo.** `find_window_rect()` enumera le finestre
   visibili con `user32` via `ctypes` e `select_window_rect()` sceglie fra quelle il cui titolo
   contiene la sottostringa configurata. La sottostringa è `window_title_contains` in `config.ini`,
   che era già presente, già esposta nella UI in `capture_tab.py:101` e **non usata da nessuna
   parte**: questo la collega.

   *Aggiornato il 2026-08-18.* La prima stesura prendeva la **prima** finestra corrispondente, senza
   verificarla. Siccome l'agent intitola la propria finestra "BPER Edge Agent" e `config.ini` cerca
   "BPER", l'agent trovava se stesso, e un ritaglio riuscito ferma la funzione prima del ripiego:
   a router ed estrazione arrivava uno screenshot dell'agent. Ora le finestre del nostro processo
   sono escluse per PID e fra le restanti vince l'area maggiore. Resta un arbitraggio, non una
   validazione.
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

*Portata di quel 9/9, precisata il 2026-08-18 (peer review finding F11).* Il test costruisce il
frame "dal vivo" incollando la finestra centrata su una tela, cioè **l'unica inquadratura che
`detect_app_rect()` sa gestire fra le sette realistiche misurate**. Il 9/9 dimostra che geometria e
punteggio sono corretti; non dimostra niente sulle sei inquadrature che la normalizzazione non
gestisce, e niente sul campo. Questa è parte della ragione per cui
[0006](0006-router-llm-come-predefinito.md) supera l'impianto.

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
