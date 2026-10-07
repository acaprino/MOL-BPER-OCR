# Aggiornamento incrementale 2026-10-07

Aggiornamento mirato sopra il run `poc-data-extraction-20260912-175144`, non una nuova analisi
completa. Copre il commit `a4f4cda` (branch `develop`) con il working tree non committato già descritto
nel [documento del 29/09](09-incremental-2026-09-29.md). **Solo misure:** nessun file sorgente, test,
configurazione o documentazione ufficiale è stato modificato oggi.

Quel working tree (gli adapter per famiglia di modelli, ADR 0016) è stato committato a fine giornata in
`acb0cc0`, identico a come è stato misurato: `python -m pytest tests` subito prima del commit ha dato
190 passed in 33.78s.

## Cosa è stato aggiunto

| Percorso | Contenuto |
|---|---|
| `baselines/2026-10-07-riscontro-12-pratiche/` | Prima misura su 12 pratiche a schermo intero: ground truth bozza (1008 righe), un run, script, riepilogo. Rapporto in [README](baselines/2026-10-07-riscontro-12-pratiche/README.md). |
| `mnt/riscontro-2026-10-07/` (ignorata da git) | Le 113 schermate in perimetro rinominate `<pratica>__<nome>.png`, `dati.csv`, gli output del run; le 18 `OffTopic` in `offtopic/`. Dati dell'ambiente di test, non reali. |

## Verifiche eseguite oggi

| Verifica | Esito |
|---|---|
| `python -m pytest tests -p no:cacheprovider` (`.venv`, Python 3.13.14) | **190 passed, 3 warnings in 82.97s**, exit 0. Esecuzione nuova. |
| Stessa suite in un ambiente usa e getta con tutte le dipendenze all'ultima versione (`langchain-core` 1.6.7, `langchain-google-genai` 4.4.0, `google-genai` 2.28.0, `openai` 3.26.0, `torch` 2.14.1, `Pillow` 12.3.0) | **190 passed, 3 warnings in 72.35s**, exit 0. Il `.venv` del progetto non è stato aggiornato. |
| Chiamata reale di prova a `gemini-3.8-flash`, solo testo, sui due percorsi (LangChain, SDK `openai` con `json_object`), versioni attuali e aggiornate | Riuscita in tutti e quattro i casi. |
| `pip-audit` sulle versioni installate nel `.venv` | 11 pacchetti con vulnerabilità note; 8 sono nella chiusura di `requirements.txt` (`Pillow` 12.2.0, `cryptography` 48.0.0, `urllib3`, `anyio`, `torch`, `pyasn1`, `fsspec`, `langsmith`), 3 sono residui non richiesti (`gitpython`, `starlette`, `python-multipart`). Un'installazione pulita li risolve tutti. `build_exe.bat` impacchetta il `.venv` esistente. Build PyInstaller con le versioni nuove **non** eseguita. |
| `python main.py` su 113 schermate, `gemini-3.8-flash`, `thinking_level` low, un run | **947/1008 (93,9%)**, $2,81, nessuna schermata in errore, 113/113 fuori calibrazione. |
| Stesso comando con `LLM_THINKING_LEVEL=high` su 23 schermate (Soggetti e Gestione Fidi base) | 22 schermate estratte, 1 fallita per JSON non valido. Sei letti male 16 su 47 contro 14 su 54 a `low`: nessun miglioramento. **$4,01 e 29 minuti**: $0,18 e 327 s per schermata, contro $0,026 e 30 s. |
| Stesso comando sulle 6 schermate di dettaglio della pratica 52062600 ritagliate sul pannello | Sei letti male 4 su 19 contro 5 su 19 a schermo intero; i 3 NDG dei soggetti restano sbagliati, su un'altra cifra. |
| RapidOCR 3.9.2 (PP-OCRv6 small ONNX, 4 thread, 1x) in locale sulle 113 schermate, in un ambiente usa e getta | **874/920 valori letti (95,0%)**, 7,7 s di media per schermata. NDG di cointestatari e garanti esatti 17 su 21 (Gemini 13), scadenze con un 6 esatte 24 su 32 (Gemini 17), rapporti esatti 39 su 41 (Gemini 30). Misura la lettura, non l'assegnazione ai campi. A 2x, su 23 schermate, esito misto. |
| LiLT `model_v2` del 29/09 sulle parole di quell'OCR, predizioni su Modal (`modal_predict_v2.py` non modificato, 96 s), campi ricostruiti con le funzioni di `ft_eval.py`, stesso ground truth e stesso `classify_field` | **677/1008 (67,2%)** con la ricostruzione corretta, 57,5% con quella iniziale; Gemini 93,9%. Errori soprattutto di assegnazione. Il percorso di calcolo rifatto su LUNARDI restituisce 63/77 come il 29/09. |

Per la verifica umana del ground truth è stato generato un file Excel di revisione (1008 righe con
ritaglio e riquadro sul valore) e uno script che ne riapplica le correzioni; il controllo automatico
dei 6 e degli 8 sui pixel conferma 149 cifre su 149 verificabili. La prima versione del file aveva
riquadri sbagliati ed è stata rifatta: i 1008 riquadri della seconda sono stati guardati uno per uno,
e su 906 riquadri rossi fuori dalle note l'OCR legge dentro il riquadro il valore atteso in 896, con
nessun riquadro che lascia fuori parte del valore. Cause e controlli nel README della baseline.

## Stato dei finding

| ID | Stato | Nota |
|---|---|---|
| XQ-R13 · alta · **nuovo** · `verified` | aperto | Nelle tabelle del dettaglio pratica catturate a schermo intero le cifre sono alte 7 pixel e il modello legge un 6 come 8 in 35 casi su 115; le altre cifre sbagliano 1 volta su 1420. Ne risultano sbagliati 8 NDG di cointestatari o garanti su 21, 15 scadenze su 45 e 11 rapporti su 41. Niente nella pipeline lo intercetta: il valore esce con stato `OK`. L'NDG di testata, che è la chiave del consolidamento per pratica, è invece corretto 102 volte su 102 (carattere più grande). Ground truth di questi campi verificato sui pixel senza modello. |
| XQ-R14 · media · **nuovo** · `verified` | aperto | `classify_field` (`extraction/normalization.py:163`) accetta al 0,85 di somiglianza ogni testo oltre i 20 caratteri; solo i campi il cui nome contiene `importo_euro`, `ndg` o `n_fido` hanno il confronto esatto (`extraction/normalization.py:148`). `rapporto` ha 22 caratteri: gli 11 valori con una cifra sbagliata sono contati corretti (41/41 per il valutatore, 30/41 cifra per cifra). L'accuratezza dichiarata è sovrastimata di 11 campi qui, e `rapporto` "sempre corretto" nelle baseline del 29/09 non è una prova. |
| XQ-D06 · media · **nuovo** · `verified` | aperto | Lo schema è modellato su una pratica. I 5 campi `tooltip_*` portano nel nome il valore su cui il tooltip compariva nella pratica LUNARDI (`extraction/fields.py:28`): su 52 tooltip reali 26 non hanno un campo (`M.FOND.PRIVATI`, `BMS`, `BMM`, `V`, `BC`, `BM`, garanzie diverse dall'ipoteca), e in 4 casi il testo del tooltip finisce in `tipo`. `evidenze` è un valore solo, ma la cella porta fino a 3 icone a lettera. I campi scalari dei fidi leggono solo la prima riga (2 pratiche su 12 hanno 2 fidi) e i soggetti sono 4 (2 pratiche ne hanno 5). |

Osservazioni dalla misura, non promosse a finding:

- Il 6 letto 8 non è un difetto del solo Gemini: RapidOCR lo fa più di rado ma nello stesso modo, e
  chi ha trascritto il ground truth lo ha fatto a sua volta leggendo i ritagli ingranditi, prima di
  controllare i pixel. Le etichette Gemini usate per addestrare LiLT il 29/09 vanno quindi
  considerate sospette sui campi a carattere piccolo.
- I retry decidono il valore in 7 errori su 61: HEADER tronca `filiale_relazione` al codice (2, già
  visto il 29/09), FOOTER sostituisce la nota intera con una sua parte (2), BODY scrive `NON CENSITO`
  nel datore di lavoro (1) e rilegge `381 mesi` (2).
- Il budget di retry è consumato per intero su tutte le 113 schermate (565 chiamate).
- `align_note` in `baselines/2026-09-29-ocr-cpu-benchmark/scripts/ft_data.py`, che il 29/09 ha
  etichettato le note per l'addestramento di LiLT, confronta le righe con `difflib` lasciando
  `autojunk` attivo: oltre i 200 caratteri le lettere frequenti sono ignorate. Sulle note di oggi il
  suo criterio riconosce 133 righe su 292 che ne fanno parte. Misurato sulle righe dell'OCR di queste
  schermate, non sui dati di addestramento del 29/09: lì la perdita è probabile ma non verificata.
- Fuori calibrazione l'accuratezza complessiva non crolla: 93,9% contro 93,5-94,8% della baseline
  calibrata, con ground truth e convenzioni diversi, quindi il confronto è solo indicativo.
- La scheda privati è misurata per la prima volta: 36/38 su 5 schermate di un solo soggetto.
- `normalize_image` (`extraction/imaging.py:19`) riduce queste immagini da circa 1915 a 1800 pixel
  prima dell'invio. Se inviarle a dimensione nativa cambi la lettura dei 6 non è stato verificato.
- Lo strumento di cattura dell'operatore lavora dentro una finestra `Pool01-VDI`; né quel titolo né
  la scheda `Nuova PEF 3.0` contengono `BPER`, la stringa cercata da `window_title_contains`. Dedotto
  dai titoli visibili negli screenshot, non verificato sull'edge-agent.

## Non coperto

Riconoscimento delle pagine (router e classificatore) su queste schermate e rifiuto delle 18
`OffTopic`; percorso live `extract_from_image()`; variabilità fra run; verifica umana del ground truth.
