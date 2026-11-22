# 0029 — La pratica di riferimento è una pratica dell'archivio come le altre

- Data: 2026-11-22
- Stato: Accettato. Superato in parte dall'ADR 0032 per la disposizione dei dati.

## Contesto

La pratica su cui è stato sviluppato il motore VLM aveva più copie delle stesse 9 schermate: una
cartella di input della CLI con il suo `dati.csv`, una cartella dell'archivio delle pratiche, e i
template della pagina distribuiti con l'edge-agent. Era anche l'unica cartella dell'archivio con
cognome e NDG nel nome: le altre portano il numero di pratica. Il responsabile del progetto ha
chiesto il 2026-11-22 che non ci siano doppie copie e che sia una pratica come tutte le altre.

Il numero si legge sull'intestazione della scheda Soggetti: `PEF 2.0 - Pratica: 51350695`, la
stessa etichetta che dà il nome alle altre cartelle (verificato su `51185037`).

## Decisione

- La pratica si chiama col suo numero, `51350695`, come tutte le altre, e ha una sola copia delle
  schermate nell'archivio delle pratiche.
- La CLI legge per default quella cartella. I valori attesi di una cartella vengono da un suo
  `dati.csv` se c'è, altrimenti dalla verità dell'archivio (`resolve_ground_truth()`, ADR 0032).
  Un `dati.csv` nella cartella vince ancora: lo usano le catture del simulatore.
- I risultati della CLI e i ritagli di debug vanno in `OUTPUT_DIR`, per default
  `outputs/<cartella di INPUT_DIR>`, fuori dall'archivio.
- Restano i template `screen N.png` dell'edge-agent. Sono un asset dell'applicazione, distribuito
  nel pacchetto, e il classificatore li legge da lì.

## Conseguenze e verifica

- Per `51350695` la CLI carica le stesse 77 terne (schermata, campo, valore) del `dati.csv`
  consegnato, con le schermate chiamate per pagina invece che `screen 1..9`. Un rapporto di
  accuratezza registrato prima, con le chiavi `screen N`, non si allinea più riga per riga; i
  numeri restano confrontabili.
- I test `tests/test_practice_truth.py` fissano da dove la CLI prende la verità.
