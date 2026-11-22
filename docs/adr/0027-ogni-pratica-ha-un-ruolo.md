# 0027 — Ogni pratica ha un ruolo: addestramento, controllo o test

- Data: 2026-11-07
- Stato: Accettato

## Contesto

Le pratiche revisionate sono poche e costano lavoro manuale. La validazione estesa del piano le
usava solo per misurare: 9 pratiche, 4 del lotto 2026-11-05 e 5 del lotto 2026-08-21, non
insegnavano nulla al modello, che continuava ad addestrarsi sulle stesse 8. E una pratica,
`LUNARDI_26871394`, non aveva nessun ruolo: ha 9 schermate in `data/pratiche` e una verità in
`data/reference/dati.csv`, ma non era mai entrata nel dataset. Il responsabile del progetto ha
fissato la regola il 2026-11-07: tutte le pratiche devono contribuire al test, al controllo o
all'addestramento, e nessuna resta esclusa.

## Decisione

| Ruolo | Pratiche | Quali |
|---|---:|---|
| Addestramento | 18 | le 8 del train, `LUNARDI_26871394`, le 9 di validazione estesa |
| Controllo | 2 | `51659595`, `52126316`: scelta dell'epoca |
| Test | 13 | le 2 del test storico, le 11 sigillate di conferma |

`LUNARDI_26871394` addestra perché su di lei il motore VLM è stato sviluppato e misurato: non può
essere una prova cieca. I suoi 77 valori sono stati confrontati con le 9 schermate una per una,
senza correzioni; vive nel lotto `riferimento-lunardi` e il dataset passa a `ground-truth-v3.4`.

Le 9 di validazione estesa addestrano il modello finale con `--also-train`. Per continuare a
misurarle, altri tre addestramenti ne tengono fuori un terzo ciascuno, assegnate per numero
crescente a rotazione: `51788077`, `51859514`, `52080736`; `51798191`, `52013664`, `52125946`;
`51849993`, `52032077`, `52137073`. Ogni pratica è misurata da un modello che non l'ha vista
(`validazione-estesa/confronta.py`).

Le 11 di conferma restano sigillate: sono il test, l'unica prova cieca. Una volta eseguita la
verifica finale possono entrare anche nell'addestramento del modello da distribuire.

`practices.csv` ha la colonna `Ruolo`. `build_dataset()` sulla versione più recente rifiuta una
cartella di `data/pratiche` senza ruolo: una pratica dimenticata ferma la costruzione invece di
restare fuori in silenzio.

## Conseguenze e verifica

La validazione estesa non misura più il modello finale: la sua stima viene dai tre addestramenti a
rotazione, che usano una pratica in meno su tre rispetto a lui. Il gate G8 chiede ancora esempi
positivi in validazione estesa e in due pratiche di conferma: lo stesso conteggio resta valido
perché quelle pratiche sono misurate da modelli che non le hanno viste.

Prima misura, OCR A1, seed 7, `ground-truth-v3.4`, metrica `strict-v6-table-columns`. Il modello
finale `lilt-v3.4-20261107-T18-seed7`, sulle 18 pratiche, fa 139/146 in controllo e 178/192 sul test
storico. A rotazione, ogni pratica misurata da un modello che non l'ha vista, le 9 di validazione
estesa fanno 348/360: 136/144 quelle di agosto, 212/216 quelle nuove, Fidi non vuoti 104/106,
Soggetti non vuoti 51/51 (`rotazione.json` nel run T18). I 12 errori rimasti sono letture dell'OCR.
La stima è ottimistica, perché le regole di lettura degli ADR 0025, 0026 e 0028 vengono dagli errori
di queste stesse pratiche, e il test storico era già stato analizzato. La prova cieca resta la
conferma.

`test_training_dataset.py` copre il lotto di riferimento, la cartella senza ruolo e la colonna
`Ruolo`; `test_training_model.py` copre `also_train` e il contratto di v3.4.
