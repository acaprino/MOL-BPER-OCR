# `data/dataset`: l'archivio delle pratiche

Tutto ciò che serve per addestrare da zero, e niente altro: schermate, valori corretti e ruolo di ogni pratica. OCR, modelli e run non ci sono: si rigenerano da qui.

```
data/dataset/
  pratiche/<id>/<pagina>-<NN>.png     240 schermate di 33 pratiche
  pratiche.csv                        una riga per pratica: Pratica;Ruolo;Schermate;Valori
  schermate.csv                       una riga per schermata
  valori.csv                          la verità: una riga per valore
```

## Nomi

- **Pratica:** il numero di pratica (`51350695`), come sta sull'intestazione della scheda Soggetti.
- **Schermata:** `<pagina>-<NN>`, con `NN` a due cifre e la schermata base della pagina per prima. Pagine: `elenco`, `soggetti`, `gestione-fidi`, `note`, `scheda-privati`. L'id in `schermate.csv` e `valori.csv` è `<pratica>/<pagina>-<NN>` (`51350695/elenco-01`); il nome del file senza estensione è lo stesso `<pagina>-<NN>`.
- **Variante** (`schermate.csv`): `destra`, `basso`, `chiuso`, `tooltip`, oppure **vuota**. Vuota vuol dire schermata base o variante non descritta: alcune schermate sono state consegnate solo numerate e non si sono aperte per classificarle.

## Tabelle (separatore `;`, UTF-8 con BOM)

| File | Colonne |
|---|---|
| `pratiche.csv` | `Pratica`, `Ruolo`, `Schermate`, `Valori` |
| `schermate.csv` | `Schermata`, `Pratica`, `Pagina`, `Numero`, `Variante`, `File`, `SHA256`, `Larghezza`, `Altezza` |
| `valori.csv` | `Schermata`, `Campo`, `Chiave`, `Valore`, `Esito` |

`Campo` è il nome della colonna come lo scrive la revisione (`NDG`, `Tipo`, ...). `Chiave` è il campo canonico tra i 45 di `FIELD_KEYS`; è **vuota** per i 156 valori fuori vocabolario (tabella Garanzie, Agente proponente), che restano nella verità senza essere un bersaglio.

## Esito

| Esito | Significato |
|---|---|
| `TRASCRITTO` | valore letto sullo schermo |
| `VUOTO` | il campo c'è ed è vuoto |
| `NON VISIBILE` | il campo è fuori dallo schermo |
| `DERIVATO` | ricavato dalle altre pagine (intestazioni delle schermate di dettaglio): serve solo per le etichette |
| `PARZIALE`, `NON LEGGIBILE` | restano nella verità, non sono un bersaglio |

## Ruoli

`Ruolo` in `pratiche.csv`: **addestramento** 18, **controllo** 2, **test** 13 (ADR 0027). Le pratiche di test non si usano per scegliere o regolare nulla e non si leggono con l'OCR né si aprono finché non c'è la misura finale: si leggono una volta, a fine sviluppo.

Sei pratiche di test (`51027430`, `51886329`, `52102964`, `52136040`, `52186431`, `52196577`) hanno i valori di ogni pagina tutti sulla sua prima schermata (`<pagina>-01`): la suddivisione per schermata si farà quando si potranno guardare.

## Regole

1. **Le immagini non si modificano.** `SHA256` in `schermate.csv` dice com'erano.
2. **Il nome di una schermata è la sua chiave** in `valori.csv` e in qualsiasi OCR o modello costruito da qui. Cambiarlo è una nuova versione dell'archivio.
3. **I risultati della CLI non vanno qui:** stanno in `outputs/<cartella>/`.

## Registro: le pratiche di test lette prima della misura finale

Chi legge la misura finale deve sapere cosa è già stato visto. Nessuna delle voci ha scelto un parametro di un modello.

- **2026-11-22, confronto del classificatore di pagine (DINOv2 e DINOv3):** sono stati calcolati gli embedding delle 240
  schermate, comprese quelle delle 13 pratiche di test, e un'accuratezza aggregata che le includeva. Nessuna immagine è stata
  guardata; il risultato è stato scartato e rifatto sulle sole 20 pratiche di addestramento e controllo. Lo stesso giorno
  `frame_normalize` è stato fatto girare su tutte le 240 per vedere se riconosceva la finestra.
- **2026-11-22, prova di OXR-1.0 e LightOnOCR-3** (altra sessione, ADR 0034): lettura di `51027430`.

## Come è stato costruito

`tools/build_dataset_archive.py` ha letto la verità corrente e le schermate del vecchio albero (lotti, versioni `v3.x`, OCR e run) e le ha riscritte con questi nomi, verificando che ogni immagine avesse la stessa impronta. Il vecchio albero è stato tolto il 2026-11-22 (ADR 0032) e resta nella storia git al commit `b2d4b80`: `git show b2d4b80:data/README.md` ne spiega la disposizione. `src/training` costruisce il dataset da qui (`python -m training.dataset --archive data/dataset ...`, vedi `src/training/README.md`).
