# 0029 — La pratica di riferimento è una pratica dell'archivio come le altre

- Data: 2026-11-22
- Stato: Accettato

## Contesto

La pratica su cui è stato sviluppato il motore VLM aveva tre copie delle stesse 9 schermate:
`data/reference/screen 1..9.png`, input predefinito della CLI con il suo `dati.csv`;
`data/pratiche/LUNARDI_26871394/`, nell'archivio delle pratiche; e i template della pagina
`src/edge-agent/assets/templates/bper/screen 1..9.png`, distribuiti con l'edge-agent. Era anche
l'unica cartella dell'archivio con cognome e NDG nel nome: le altre 32 portano il numero di
pratica. Il responsabile del progetto ha chiesto il 2026-11-22 che non ci siano doppie copie e
che sia una pratica come tutte le altre.

Il numero si legge sull'intestazione della scheda Soggetti: `PEF 2.0 - Pratica: 51350695`, la
stessa etichetta che dà il nome alle altre cartelle (verificato su `51185037`).

## Decisione

- La cartella diventa `data/pratiche/51350695`. Il lotto `riferimento-lunardi` diventa
  `riferimento-2025-09-09`, la data della cattura stampata sulla schermata, e porta con sé il
  `dati.csv` consegnato, invariato, con l'assegnazione chiamata `g8_assegnazione.json` come negli
  altri lotti.
- L'identificativo delle schermate cambia, quindi la verità si ricostruisce: `ground-truth-v3.5`
  è la v3.4 con il nuovo nome. La v3.4 resta com'è, perché i run T18 e fold vi fanno riferimento.
- `data/reference` sparisce. La CLI legge per default `data/pratiche/51350695`; i valori attesi
  di una cartella vengono da un suo `dati.csv`, altrimenti dal suo foglio di
  `data/pratiche/pratiche.xlsx` (`resolve_ground_truth()`). Un `dati.csv` nella cartella vince
  ancora: lo usano le catture del simulatore.
- I risultati della CLI e i ritagli di debug vanno in `OUTPUT_DIR`, per default
  `outputs/<cartella di INPUT_DIR>`, fuori dall'archivio.
- Restano i template `screen N.png` dell'edge-agent. Sono un asset dell'applicazione, distribuito
  nel pacchetto, e il classificatore li legge da lì; strumenti, simulatore e test che leggevano
  `data/reference` leggono loro.

## Conseguenze e verifica

- La nuova lettura OCR A1 delle 9 schermate coincide con la precedente in parole, riquadri e
  confidenze. La v3.5 coincide con la v3.4, a parte il nome, in valori, conteggi, ruoli, schermate
  ed esempi.
- Per `51350695` la CLI carica le stesse 77 terne (schermata, campo, valore) del `dati.csv`
  consegnato, con le schermate chiamate per pagina (`Elenco`, `Elenco_dx`, ...) invece che
  `screen 1..9`. Un rapporto di accuratezza registrato prima, con le chiavi `screen N`, non si
  allinea più riga per riga; i numeri restano confrontabili.
- I test `tests/test_practice_truth.py` fissano da dove la CLI prende la verità; il test del
  lotto di riferimento in `tests/test_training_dataset.py` fissa che produce la v3.5.
