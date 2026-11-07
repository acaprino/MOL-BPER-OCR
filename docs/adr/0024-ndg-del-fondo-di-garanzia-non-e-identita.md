# 0024 — L'NDG del Fondo di garanzia non è un'identità

- Data: 2026-11-07
- Stato: Accettato

## Contesto

La separazione fra validazione estesa e conferma (`docs/next-ver-plan.md` §5.4, regola 3)
confronta pratica, immagini e NDG dei soggetti: due pratiche con lo stesso NDG di solito
riguardano lo stesso cliente, e metterle in gruppi diversi toglierebbe indipendenza alla
conferma. La regola trattava tutti gli NDG allo stesso modo.

`11153238` è il Fondo di garanzia per la prima casa. Non è un cliente: è il garante dei
mutui prima casa, ed è un soggetto in una larga parte delle pratiche (5 su 10 nel lotto
2026-11-05). Trovarlo in due pratiche non dice nulla su di loro. Applicata anche al Fondo,
la regola ha prodotto due volte un falso allarme: con il lotto 2026-08-21 ha portato a
proporre l'esclusione di 52032077, respinta il 2026-10-28 perché nessuna pratica si
esclude; con il lotto 2026-11-05 avrebbe mandato in validazione estesa tutte le pratiche
con il Fondo, ora e in futuro, lasciando la conferma senza quel prodotto.

## Decisione

`INSTITUTIONAL_NDGS` in `src/training/g8_assignment.py` elenca gli NDG degli enti: oggi
soltanto `11153238`. Non sono identità in nessun controllo: non legano le pratiche
nell'assegnazione (`assign_lot()`), non contano in `audit_splits()` e non sono registrati
come sovrapposizioni. I manifest li nominano: `ndg_istituzionali` nell'assegnazione, con le
pratiche che li contengono, e `institutional_ndgs` nel bundle.

L'NDG di un cliente in comune fra validazione estesa e conferma resta rifiutato. Una pratica
con l'identità di un cliente già in un gruppo segue quel gruppo. Un altro ente trovato in più
pratiche si aggiunge all'elenco, senza spostare né escludere pratiche e senza farne una
domanda per ogni lotto.

## Conseguenze e verifica

Il lotto 2026-11-05 va per regola in validazione estesa con 51849993, 52080736, 52125946,
52137073 e in conferma con 51027430, 51886329, 52102964, 52136040, 52186431, 52196577. I
tooltip M-CONSAP e CONSAP DR BIS sono coperti in entrambi i gruppi; restano scoperti i 13
campi Scheda Privati.

Le righe del Fondo in conferma non sono una prova cieca, come non lo erano già: il Fondo è
anche nel train. Il rapporto finale di conferma le conta anche a parte.

`test_training_g8_assignment.py` e `test_training_dataset.py` coprono il Fondo in comune
fra i gruppi, che è accettato e non registrato, e il cliente in comune, che è rifiutato.
