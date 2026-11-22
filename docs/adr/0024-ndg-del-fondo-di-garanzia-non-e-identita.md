# 0024 — L'NDG del Fondo di garanzia non è un'identità

- Data: 2026-11-07
- Stato: Accettato

## Contesto

La separazione fra gli insiemi di addestramento, controllo e test confronta pratica, immagini e
NDG dei soggetti: due pratiche con lo stesso NDG di solito riguardano lo stesso cliente, e
metterle in insiemi diversi toglierebbe indipendenza alla prova. La regola trattava tutti gli NDG
allo stesso modo.

`11153238` è il Fondo di garanzia per la prima casa. Non è un cliente: è il garante dei mutui
prima casa, ed è un soggetto in una larga parte delle pratiche. Trovarlo in due pratiche non dice
nulla su di loro. Applicata anche al Fondo, la regola produce un falso allarme ogni volta che
arriva una pratica con il Fondo, e costringerebbe a escludere o spostare pratiche già revisionate.

## Decisione

`INSTITUTIONAL_NDGS` in `src/training/dataset.py` elenca gli NDG degli enti: oggi soltanto
`11153238`. Non sono identità in nessun controllo: non contano in `audit_splits()` e non sono
registrati come sovrapposizioni. Il manifest del bundle li nomina in `institutional_ndgs`.

L'NDG di un cliente in comune fra due insiemi resta rifiutato. Un altro ente trovato in più
pratiche si aggiunge all'elenco, senza spostare né escludere pratiche.

## Conseguenze e verifica

Le righe del Fondo nell'insieme di test non sono una prova cieca, come non lo erano già: il Fondo è
anche nell'addestramento.

`test_training_dataset.py` copre il Fondo in comune fra due insiemi, che è accettato, e il cliente
in comune, che è rifiutato.
