# 0030 — I prototipi delle pagine sono distribuiti con l'app, non calcolati all'avvio

- Data: 2026-11-22
- Stato: Accettato

## Contesto

L'edge-agent riconosce la pagina BPER confrontando ogni fotogramma con un prototipo DINOv2 per
pagina e per tipo di scarto. Fino a oggi l'app conteneva le immagini da cui ricavarli: le 9
schermate di riferimento `screen 1..9.png` e 75 ritagli nelle cartelle `SCARTO-*`, 31 MB in tutto.
Al primo avvio ne calcolava i prototipi e li salvava in una cache non versionata
(`bper_page_prototypes.json`); li ricalcolava ogni volta che le immagini cambiavano.

Il responsabile del progetto ha osservato il 2026-11-22 che l'agent deve sapere a priori come
sono fatte le pagine: quello che sa va calcolato una volta, salvato e distribuito con
l'applicazione. Le 9 schermate erano anche una copia di quelle della pratica `51350695`
(ADR 0029, che le lasciava fra gli asset: questa decisione la supera su quel punto).

## Decisione

- `bper_page_prototypes.json` è un file versionato e distribuito con l'app: 9 prototipi di pagina e
  3 di scarto, da 384 valori ciascuno. È il file costruito il 2026-08-18, invariato: il
  riconoscimento non cambia.
- L'app carica i prototipi e non legge immagini. Li rifiuta, prima di caricare il modello, se
  mancano o se la loro `embedding_geometry()` non coincide con quella del codice (ADR 0003): un
  cambio di ROI, resize, modello o regola di punteggio ferma l'avvio invece di servire vettori
  incompatibili.
- I prototipi si costruiscono solo fuori dall'app, con `tools/build_prototypes.py`: le 9 pagine
  dalle schermate di `data/pratiche/51350695` (`tools/reference_screens.py` dice quale pagina è
  ogni `screen N`), gli scarti da ritagli del registro dei fotogrammi di test, tagliati in una
  cartella temporanea.
- Le immagini escono dall'app: le 9 schermate restano solo nella pratica, i ritagli si rigenerano
  dal registro, le schermate di navigazione `transitions/`, che il codice non leggeva, vanno in
  `processes/bper-p1/transizioni/`.

## Conseguenze e verifica

- Ricostruiti oggi, i 9 prototipi di pagina coincidono con quelli distribuiti (coseno 1,0); quelli
  di scarto no (coseno 0,986-0,999), perché il registro è cresciuto il 2026-08-21 e lo stesso
  campionamento sceglie altri ritagli (16 su 75 identici). Una ricostruzione è quindi un cambio di
  comportamento: si fa per cambiare i prototipi e si verifica con i test lenti di
  `tests/test_page_classifier.py`.
- Restano scaricati al primo avvio i pesi di DINOv2, il modello generico che produce gli
  embedding: i prototipi sono la parte specifica di BPER, e quella arriva già pronta.
- `tests/test_page_classifier.py` verifica che l'app non contenga immagini, che i prototipi
  distribuiti siano pronti senza immagini e che prototipi di un'altra geometria siano rifiutati;
  il riconoscimento da fotogrammi a schermo intero resta 9 pagine su 9.
