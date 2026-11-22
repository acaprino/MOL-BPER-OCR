# 0025 — Righe dei soggetti centrate e testata letta dalla sua etichetta

- Data: 2026-11-07
- Stato: Accettato

## Contesto

Su alcune pratiche, 11 campi della tabella Soggetti si perdevano anche
ricostruendo dalle etichette revisionate: `FONDO DI GARANZIA PER LA PRIMA CASA` diventava
`CASA`, e la sua prima riga finiva nel soggetto sopra. `decode_fields()` faceva iniziare una
riga mezza altezza di parola sopra il suo NDG, ma l'NDG sta al centro verticale della riga:
su tutte le schermate revisionate le righe di una
cella a capo distano fino a 0,56 altezze da lui. Bastava che la scala della pagina portasse
quello scarto oltre 0,5 perché la prima riga passasse al soggetto precedente.

Il modello inoltre assegna all'NDG e alla denominazione di testata anche parole lette altrove,
e `decode_fields()` le univa: il numero di pratica (`52032077 32661219`), il proponente sulla
riga sopra (`SEBASTIANO ADRIANO`), la colonna della tabella Garanzie
(`BEN ROMDHANE NAJEH BEN ROMDHA BAONN`). Sulle schermate di dettaglio la testata è una riga
fissa con la sua etichetta: `NDG: numero - nome`.

## Decisione

Ogni riga di soggetto, anche la prima, inizia 0,75 altezze sopra il suo NDG
(`SUBJECT_CELL_REACH`): oltre lo scarto massimo misurato (0,56) e sotto la metà del passo
minimo fra due righe (1,47).

Se l'OCR legge l'etichetta `NDG:` e il trattino sulla stessa riga, l'NDG è ciò che sta fra i
due e la denominazione ciò che segue il trattino. Senza etichetta o senza trattino restano i
ruoli del modello.

## Conseguenze e verifica

Dalle etichette revisionate nessun campo si perde più: 0 su 574 in addestramento, 0 su 126 in
controllo, 0 su 287 in altre pratiche revisionate (erano 11). Le regole vengono dagli errori di
queste pratiche, non dal test. L'effetto sui modelli, insieme alla
lettura per colonna dei Fidi e al cambio di metrica, è nell'[ADR 0026](0026-celle-fidi-lette-per-colonna.md).

`test_training_evaluation.py` copre la prima riga di una cella a capo, le parole sopra la prima
riga, la testata letta dall'etichetta e la riga senza trattino.
