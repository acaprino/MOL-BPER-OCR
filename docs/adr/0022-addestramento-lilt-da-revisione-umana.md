# 0022 — Addestrare LiLT da valori revisionati e pratiche separate

- Data: 2026-10-16
- Stato: Accettato

## Contesto

La revisione umana fornisce valori corretti per screenshot BPER. Per usarli nel
riconoscitore locale RapidOCR + LiLT servono etichette sulle parole e coordinate
relative all'immagine completa. Il testo OCR può contenere errori, e schermate della
stessa pratica non sono esempi indipendenti. I precedenti pesi BPER non hanno una
storia sufficiente a escludere sovrapposizioni con un nuovo test.

## Decisione

Il pacchetto offline `training/` legge soltanto valori e stati approvati nella
revisione completata. Conserva testo OCR e valori attesi separatamente. Supervisiona
parole individuate con testo esatto e geometria verificata (ordinando le celle
multi-riga secondo le righe visive della cella); maschera conflitti e osservazioni
incerte circoscrivendo il riquadro di incertezza alla regione del campo. Nelle note,
nella data di validazione, nella scadenza e nel tipo operazione può utilizzare le
parole esatte in ordine, mascherando quelle lette male. Le assenze non ricevono un
riquadro sintetico. Il valore letterale `N/D` non diventa un'assenza.

Gli insiemi vengono separati per pratica prima dell'addestramento. Il controllo
rifiuta anche NDG di soggetti o immagini identiche che attraversano il confine.
Il manifest lega il corpus e l'ordine delle classi a un'impronta del contenuto.

Il modello parte dal LiLT pubblico preaddestrato, con una nuova testa per i ruoli
BPER. Ogni parola mantiene i propri sottotoken; nessuna parola viene troncata dal
limite della sequenza e il blocco tabella `FIDI` non viene spezzato dalla sua
intestazione tra finestre diverse. Varianti numeriche (che preservano gli zeri
delle migliaia) e geometriche contenute riguardano solo copie di addestramento.
La validazione sceglie l'epoca in base all'accuratezza sui campi completi (con
spareggio su F1 delle parole non-nota e F1 complessiva); il test viene misurato
dopo la scelta.

Un'esecuzione GPU esplicitamente avviata è limitata e produce una nuova versione;
il modello scaricato è caricabile su CPU. Il motore dell'edge-agent non cambia.
Le metriche dei campi includono tutti i valori revisionati della popolazione
valutata, anche quelli esclusi dalla perdita per errori OCR. Disponibilità OCR,
F1 delle parole e accuratezza dei campi rimangono misure distinte.

## Conseguenze e verifica

I valori corretti possono alimentare l'addestramento senza trasformare errori OCR
in risposte corrette fittizie. Non si dichiara validato un campo senza esempi nelle
pratiche di prova. Servono ulteriori pratiche per misurare i campi presenti in una
sola pratica e ulteriori miglioramenti dell'OCR per recuperare cifre lette male.

`test_training_dataset.py` copre archivio, assenze, supervisione e separazione;
`test_training_alignment.py` copre geometria e parole verificate;
`test_training_model.py` copre sottotoken, split e ciclo reale di salvataggio e
ricaricamento; `test_training_evaluation.py` copre ricostruzione e confronto rigoroso.
