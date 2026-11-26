# Piano: prove di OCR e LiLT in condizioni dinamiche, con il simulatore

- Proposta del 23 novembre 2026, aggiornata il 26 novembre.
- **Confronto dinamico dei due percorsi OCR + LiLT da eseguire.** Le soglie sotto sono proposte.

## Perché

Le misure sui campi interi di RapidOCR e del lettore OCRia-nano riaddestrato, ciascuno con il proprio LiLT, vengono
da PNG salvati. Nella cattura dal vivo la finestra cambia dimensione, la pagina scorre, la selezione o il cursore
coprono i valori e il frame adottato passa da `preprocess_for_ocr()`. Occorre misurare entrambi i percorsi su
queste immagini prima di collegarli all'edge-agent, che oggi estrae i campi con il VLM. [Misure su PNG](ocr-lilt.md#risultati-sul-controllo)

Il simulatore (`bper-emulator/`) produce schermate e valori giusti per costruzione e senza dati di clienti: è lo
strumento adatto. Non sostituisce le pratiche vere: le soglie di accuratezza "ufficiali" restano misurate su quelle.

## Cosa offre il simulatore

`bper-emulator/live_test.py` registra e riproduce scenari di scorrimento, hover e ridimensionamento con il worker e
il classificatore di pagina reali. Per impostazione predefinita il test usa i valori dell'emulatore per misurare il
consolidamento. Per misurare i campi OCR occorre leggere gli stessi frame adottati con i due percorsi e confrontarne
i risultati con i valori visibili. Il pilota sulle singole righe sintetiche ha verificato la somiglianza dei
riquadri; resta da misurare la catena OCR + LiLT nelle condizioni sotto. [Scenari e modalità disponibili](../bper-emulator/live_test_README.md)

## Fasi

1. **Controllo di fedeltà.** Leggere con A1 le 9 schermate vere della pratica di riferimento e quelle del simulatore.
   Soglie: numero di righe lette entro ±5%; valori giusti non più alti del reale di oltre 5 punti, perché un
   simulatore troppo facile "regala" risultati. È grossolano: su 77 valori l'errore statistico è circa ±2,5 punti.
2. **Base statica.** Circa 20 pratiche sintetiche (circa 1.500 valori), finestra nativa, nessuna interazione. Con quel
   numero l'errore è circa ±0,6 punti, quindi uno scarto di 2-3 punti si distingue dal rumore.
3. **Le cinque condizioni**, sulle stesse pratiche e ognuna confrontata con la base (tabella sotto).
4. **Percorso dal vivo.** Usare `live_test.py live` su una macchina con desktop interattivo, una pratica per
   condizione. Conservare l'inquadratura e le impostazioni di preprocessing effettive per confrontare replay e VDI.

## Condizioni e soglie proposte

| Condizione | Cosa si cattura | Cala al massimo di |
|---|---|---|
| Finestra | 842×617, 1280×720, 1600×900, 1920×945 | 2 punti |
| Scorrimento | lista all'inizio, a metà, alla fine; tabella scorsa | 3 punti, solo sui campi visibili |
| Riga selezionata, testo evidenziato | sfondo colorato sul valore | 5 punti |
| Cursore o hover sul valore | cursore sopra i caratteri | 5 punti |
| Ridimensionamento a metà sequenza | finestra stretta e poi larga | 3 punti |

Una condizione che cala di oltre 10 punti è un blocco. Il calo si calcola rispetto alla base, sulle stesse pratiche.

## Misure, per ogni condizione

- Valori giusti nel testo letto (come `ocr_selection_metrics`).
- Accuratezza dei campi di LiLT (`evaluate_predictions`, metrica `strict-v6-table-columns`).
- Riconoscimento della pagina: **zero adozioni sbagliate** con margine ≥ 0,10 (soglia dell'ADR 0012).
- Consolidamento: una riga per pratica, sempre.

## Regole

- Le pratiche vere di test si possono leggere con l'OCR. I loro valori si usano una volta sola sul candidato congelato
  (ADR 0027 e 0035). Il registratore dinamico usa le pratiche sintetiche ammesse dal proprio scenario.
- Le pratiche con cui si addestra non si usano per misurare.
- Il simulatore non contiene dati di clienti, quindi inviarlo a Modal non è un problema di privacy; si chiede comunque
  il via prima di ogni invio.
- Associare a ogni lettura i suoi pesi LiLT dal volume `bper-lilt-spike` (circa 1,1 GB per modello).
  [Identificativi dei modelli](ocr-lilt.md#modelli-e-provenienza)

## Da decidere

1. Le soglie della tabella.
2. Quali condizioni richiedono nuovi scenari, in particolare selezione del testo e cursore sui caratteri.
3. Su quale PC o VDI eseguire il passo 4.
