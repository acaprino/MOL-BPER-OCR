# 0027 — Ogni pratica ha un ruolo: addestramento, controllo o test

- Data: 2026-11-07
- Stato: Accettato

## Contesto

Le pratiche revisionate sono poche e costano lavoro manuale. Una pratica che non serve né a
misurare né a insegnare è lavoro sprecato, e una pratica dimenticata fuori dal dataset non si
nota. Il responsabile del progetto ha fissato la regola il 2026-11-07: tutte le pratiche devono
contribuire al test, al controllo o all'addestramento, e nessuna resta esclusa.

## Decisione

| Ruolo | Pratiche | A cosa serve |
|---|---:|---|
| Addestramento | 18 | insegna al modello; include la pratica di riferimento `51350695`, su cui il motore VLM è stato sviluppato e misurato e che quindi non può essere una prova cieca |
| Controllo | 2 | `51659595`, `52126316`: scelta dell'epoca |
| Test | 13 | l'unica prova cieca |

Il ruolo sta nella colonna `Ruolo` di `pratiche.csv` e dà lo split delle schermate della pratica.
`read_archive()` rifiuta un ruolo sconosciuto e le schermate di una pratica senza ruolo: una
pratica dimenticata ferma la costruzione invece di restare fuori in silenzio.

Le pratiche di test restano sigillate: non si leggono con l'OCR né si aprono finché non c'è un
candidato congelato (`include_test`). Una volta eseguita la verifica finale possono entrare anche
nell'addestramento del modello da distribuire.

## Conseguenze e verifica

La stima del modello viene dal controllo e, una sola volta, dal test. Le regole di lettura degli
ADR 0025, 0026 e 0028 vengono dagli errori di pratiche già viste: la prova cieca resta il test.

`test_training_dataset.py` copre il ruolo sconosciuto, la pratica senza ruolo, la lettura del test
solo con `include_test` e il rifiuto di una lettura OCR di una schermata di test senza.
