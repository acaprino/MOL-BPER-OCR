# Piano: prove di OCR e LiLT in condizioni dinamiche, con il simulatore

- Data: 2026-11-23
- Stato: **bozza, nessuna prova eseguita.** Le soglie sono proposte, da confermare.

## Perché

Tutte le misure di OCR e LiLT fatte finora (126 valori su 133 nel testo letto, 139 campi su 146 in controllo) sono su
PNG già salvati, un fotogramma alla volta, a scala 1×. Nell'uso reale la schermata è dal vivo: la finestra del browser
cambia dimensione, la pagina scorre, si seleziona una riga, il cursore passa sopra i valori. Inoltre ogni fotogramma
passa da `preprocess_for_ocr()` (ingrandimento ×1,25 o ×1,5, maschera di nitidezza, contrasto) prima di essere letto.
Nulla di questo è misurato per OCR e LiLT. Oggi nell'app i campi li estrae l'LLM e RapidOCR/LiLT sono un percorso
offline, quindi è un rischio da chiudere prima di collegarli.

Il simulatore (`bper-emulator/`) produce schermate e valori giusti per costruzione e senza dati di clienti: è lo
strumento adatto. Non sostituisce le pratiche vere: le soglie di accuratezza "ufficiali" restano misurate su quelle.

## Cosa manca nel simulatore

Lo script `capture_bper_dataset.cjs` cattura oggi solo a 842×617 (le 9 schermate di ogni pratica) e a 1920×945
(Scheda Privati, con scorrimento via parametri `scroll` e `noteScroll`). Non ha opzioni per la dimensione della
finestra, la selezione di una riga, il testo evidenziato o il cursore. Va esteso prima di cominciare: è il lavoro
della sessione che sviluppa il simulatore.

## Fasi

1. **Controllo di fedeltà.** Leggere con A1 le 9 schermate vere della pratica di riferimento e quelle del simulatore.
   Soglie: numero di righe lette entro ±5%; valori giusti non più alti del reale di oltre 5 punti, perché un
   simulatore troppo facile "regala" risultati. È grossolano: su 77 valori l'errore statistico è circa ±2,5 punti.
2. **Base statica.** Circa 20 pratiche sintetiche (circa 1.500 valori), finestra nativa, nessuna interazione. Con quel
   numero l'errore è circa ±0,6 punti, quindi uno scarto di 2-3 punti si distingue dal rumore.
3. **Le cinque condizioni**, sulle stesse pratiche e ognuna confrontata con la base (tabella sotto).
4. **Percorso live reale, a mano.** L'emulatore in una vera finestra del browser, catturato con il vero lavoratore di
   cattura (`BPERCaptureWorker`, con `frame_normalize` e `preprocess_for_ocr`) e non con Playwright, una pratica per
   condizione. I PNG di Playwright vengono da Chrome senza testa e non coincidono con la resa della VDI.

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

- Le pratiche vere di test restano sigillate (ADR 0027). Le pratiche sintetiche di test si catturano solo con
  `--include-test`, che lo script già impone.
- Le pratiche con cui si addestra non si usano per misurare.
- Il simulatore non contiene dati di clienti, quindi inviarlo a Modal non è un problema di privacy; si chiede comunque
  il via prima di ogni invio.
- I pesi di LiLT sono sul volume Modal `bper-lilt-spike`: la misura dei campi va fatta lì, oppure scaricando i pesi
  (circa 1,1 GB).

## Da decidere

1. Le soglie della tabella.
2. Chi estende lo script di cattura (dimensione finestra, selezione, cursore) e quando.
3. Se il passo 4 si fa su una macchina con desktop interattivo, perché non è automatizzabile in una pipeline.
