# Panoramica del progetto

MutuiOnline BPER estrae i dati che un operatore legge nelle schermate di Nuova PEF e della Scheda Privati. Il risultato finale nell’edge-agent è una riga Excel per NDG normalizzato nella sessione. Per una singola pratica si possono acquisire più volte la stessa pagina o lo stesso campo.

## Tre modi di lavorare

| Ingresso | Come arriva la schermata | Cosa si ottiene |
|---|---|---|
| CLI | Immagini in una cartella, con valori attesi | Risultati per schermata, accuratezza per campo e costo stimato delle chiamate |
| Desktop Tkinter | File selezionati dall’utente | Estrazione a video, esportazione e valutazione facoltativa |
| Edge-agent PyQt6 | Fotogrammi dal monitor | Riconoscimento della vista, guida per pratica, correzioni con salvataggio automatico e ripresa della sessione, Excel |

Il vocabolario comprende **45 campi**, distribuiti su **cinque pagine sorgenti** e **quattro gruppi Excel**. Le **nove viste** del router distinguono anche scorrimenti e tooltip di una stessa pagina PEF. La Scheda Privati è un’applicazione separata. [Flusso funzionale e campi per vista](flusso-data-entry.md)

## Motori e misure

Il motore usato dalle tre interfacce estrae i campi con un VLM. Legge prima gli identificativi, poi il contenuto, infine rilegge le aree poco affidabili entro il budget configurato. Nel batch la pratica predefinita trova i valori attesi nell’archivio revisionato del repository. [Workflow](05-workflows.md) · [Archivio](../data/README.md)

Il lavoro sui modelli locali mantiene in parallelo **RapidOCR + LiLT** e il percorso **OCRia-nano-1 + LiLT**. La versione Nano riaddestrata valutata sui campi usa il rilevatore RapidOCR. Per confrontare le catene servono le stesse schermate di controllo e, per ciascun OCR, il LiLT addestrato sulla sua lettura. Il riconoscimento della vista PEF ha una verifica separata, inclusi ritorni e salti. [Confronto dei modelli](ocr-lilt.md) · [Navigazione dell’edge-agent](navigazione-edge.md)
