# Baseline 2026-10-07 - 12 pratiche a schermo intero (gemini-3.8-flash, thinking low)

Prima misura su più pratiche e sull'inquadratura che l'operatore usa davvero. Il materiale è il
riscontro di Rita Macis alla mail del 30/09: 131 screenshot di 12 pratiche "Nuova PEF 3.0", presi il
6 e 7 ottobre 2026 dall'ambiente di test (dati non reali), finestra `Pool01-VDI` massimizzata a circa
1915x1010. Copre i due limiti dichiarati nella
[baseline del 29/09](../2026-09-29-gemini-3.8-flash/README.md): una sola pratica e scheda privati mai
misurata.

## Come è stata prodotta

- **Codice:** commit `a4f4cda` (`develop`) più le modifiche non committate dell'ADR 0016. Nessun file
  sorgente, test o configurazione è stato modificato per questa misura.
- **Comando:** `INPUT_DIR=mnt/riscontro-2026-10-07 python main.py`, con il `.env` locale:
  `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-3.8-flash`, `LLM_THINKING_LEVEL=low`,
  `MAX_CALLS_PER_SCREEN=5`, `PARALLEL_WORKERS=4`. **Un solo run**: la variabilità non è misurata.
- **Librerie:** quelle del `.venv` al 2026-10-07 (`langchain-core` 1.4.0, `langchain-google-genai`
  4.2.4, `google-genai` 2.7.0).
- **Immagini:** 113 schermate in perimetro, copiate come `<pratica>__<nome>.png` in
  `mnt/riscontro-2026-10-07/` (ignorata da git). Le 18 `OffTopic*` stanno in `offtopic/` e non sono
  state estratte.
- **Inquadratura:** tutte e 113 fuori calibrazione (`_content_crop: full-frame`, ADR 0010).
- **Ground truth:** [`dati.csv`](dati.csv), 1008 righe, **non verificato da una persona**. Deriva
  dalle trascrizioni in [`trascrizioni/`](trascrizioni/) (una per pratica, lette da Claude Opus su
  ritagli ingranditi) assemblate da [`scripts/assemble_gt.py`](scripts/assemble_gt.py), che contiene
  tutte le convenzioni in un solo punto.

### Controlli fatti sul ground truth

| Controllo | Esito |
|---|---|
| Stesso valore su tutte le schermate di una pratica (testata, riga Elenco, primo fido) | 0 discordanze su 12 pratiche |
| NDG dei soggetti contro i pixel, senza modello ([`scripts/verify_small_digits.py`](scripts/verify_small_digits.py)) | 277 cifre: 34 sei e 13 otto, 0 discordanze |
| Rapporto contro il numero FICS scritto nelle note in carattere più grande | coincide nelle 7 pratiche che lo riportano |
| Scadenze contestate dal modello, lette sulla griglia dei pixel ([`scripts/ascii_region.py`](scripts/ascii_region.py)) | 7 schermate controllate, ground truth confermato in tutte |

Le incertezze dichiarate da chi ha trascritto (160 note, quasi tutte su colonne tagliate che lo schema
non legge) sono in [`controlli.json`](controlli.json).

### Scelte del ground truth da confermare

| Campo | Scelta | Peso |
|---|---|---|
| Evidenze | Tutte le icone a lettera della cella, separate da spazio (`B P`, `B V`, `BC`) | 36 righe; 16 errori dipendono solo dal contare o no la `P` nel cerchio rosa |
| Denominazione in Elenco | Se l'applicativo la tronca: testo visibile più `...` | 3 errori di sola forma |
| Tipo | In Elenco la sigla a schermo (`BMB`, `BMM`, `BMS`); nel dettaglio `BPI Mutui` | 100 righe |
| Tooltip | Valutati solo quelli che cadono su uno dei 5 campi `tooltip_*` dello schema | 26 tooltip su 52 restano fuori |
| Fidi | Solo la prima riga visibile | 2 pratiche hanno 2 fidi |
| Soggetti | Solo i primi 4 | 2 pratiche ne hanno 5 |
| Note della richiesta | Il testo visibile in quella schermata, righe unite da spazio | 15 righe, confronto approssimato |
| Ultima validazione scheda | Come a schermo, compreso `(4 giorni fa)` | 1 riga |
| DAL (scheda privati) | Quello accanto a Professione principale, non quello del datore di lavoro | 1 riga |

## Risultati

| | Corretti | |
|---|---:|---:|
| **Tutti i campi (RAW)** | 947/1008 | 93,9% |
| FILTERED (3 schermate escluse dalla guardia NDG/denominazione) | 931/985 | 94,5% |
| Identità: NDG e denominazione, testata e soggetti | 289/300 | 96,3% |

| Tipo di pagina | Schermate | Corretti | |
|---|---:|---:|---:|
| Elenco con tooltip | 20 | 131/150 | 87,3% |
| Elenco (base e scorso a destra) | 16 | 102/112 | 91,1% |
| Scheda Privati (una sola pratica) | 5 | 36/38 | 94,7% |
| Fidi con tooltip | 33 | 318/334 | 95,2% |
| Soggetti | 12 | 184/192 | 95,8% |
| Fidi (base e scorso in basso) | 12 | 112/116 | 96,6% |
| Note | 15 | 64/66 | 97,0% |

565 chiamate, 5 per schermata; 2.469.878 token di prompt e 255.387 di completion; **$2,81, cioè
$0,025 per schermata**; 28,8 s per schermata come somma delle chiamate. Nessuna schermata in errore.
11 schermate in `ANCHOR_UNCERTAIN`: sono quelle scorse in cui la testata non è a schermo, è atteso.

Il `run1.log` riporta `475/511`: è il punteggio stampato dal comando contro il ground truth
parziale (6 pratiche) disponibile al lancio. I numeri di questa pagina sono ricalcolati sugli stessi
output con il ground truth completo ([`scripts/report_run.py`](scripts/report_run.py), che usa
`classify_field()` come `eval_outputs()`), e sono in [`summary.json`](summary.json).

### I 61 errori

| Natura | Errori | Dettaglio |
|---|---:|---|
| **Un 6 letto come 8** | 23 | `scadenza` 15 (`361 mesi` → `381 mesi`, `15/10/2036` → `2038`), NDG dei soggetti 8 |
| Evidenze con più icone | 21 | Il modello restituisce solo `B`, o niente se c'è solo `P`. In 5 casi perde la `V` (Prodotto Voucher) |
| `tipo` sostituito dal testo del tooltip | 4 | Con `BMM` o `BMS` il tooltip non ha un campo suo e finisce in `tipo` |
| Denominazione troncata | 3 | `KOLA AL..` contro `KOLA AL...`: sola forma |
| Retry che peggiora la lettura | 5 | HEADER tronca `filiale_relazione` al codice (2); FOOTER sostituisce la nota intera con un pezzo (2); BODY mette `NON CENSITO` nel datore di lavoro (1) |
| Tooltip non estratto | 3 | Un popover aperto, campo lasciato vuoto |
| Altri | 2 | `M CONSAP` senza punto; data di validazione senza `(4 giorni fa)` |

### Il 6 letto come 8

È l'unico errore di lettura sistematico e colpisce solo le tabelle del dettaglio pratica, dove le
cifre sono alte 7 pixel ([`scripts/digit_confusions.py`](scripts/digit_confusions.py)):

| | |
|---|---:|
| Sei letti male | 36 su 115 (31%), 35 volte come otto |
| Altre cifre lette male | 1 su 1420 |
| NDG di cointestatari e garanti (righe 2-4) corretti | 13 su 21 |
| Scadenze che contengono un 6 corrette | 17 su 32 |
| Rapporti corretti cifra per cifra | 30 su 41 |

Ingrandendo lo screenshot quei 6 sembrano 8 anche a una persona: la differenza sta in uno o due
pixel e si vede solo sulla griglia dei pixel. Per questo il ground truth di questi campi è stato
controllato senza modello.

**Gli 11 rapporti sbagliati non compaiono fra i 61 errori.** `classify_field()` accetta al 0,85 di
somiglianza ogni testo oltre i 20 caratteri, e un rapporto ne ha 22: una cifra sbagliata su un
identificativo conta come corretta ([`scripts/exact_identifiers.py`](scripts/exact_identifiers.py)).
Contandoli, i corretti scendono a 936/1008 (92,9%). Lo stesso vale per la baseline del 29/09, dove
`rapporto` risulta sempre corretto.

## Prove collegate

Due prove fatte per capire se il 6 letto 8 si corregge senza cambiare motore di lettura. Nessuna
delle due lo corregge. File in [`prove/`](prove/).

| Prova | Schermate | Sei letti male | NDG di soggetti (righe 2-4) corretti | Costo per schermata | Tempo per schermata |
|---|---:|---:|---:|---:|---:|
| `thinking_level=low` (dal run principale) | 23 | 14 su 54 | 13 su 21 | $0,026 | 30 s |
| `thinking_level=high`, stesse schermate | 22 | 16 su 47 | 11 su 19 | **$0,18** | **327 s** |
| Schermo intero, pratica 52062600 | 6 | 5 su 19 | 0 su 3 | $0,024 (media del pilota, 14 schermate) | 27 s (idem) |
| Ritaglio sul pannello del dettaglio, stessa pratica | 6 | 4 su 19 | 0 su 3 | $0,026 | 29 s |

- **Ragionamento alto** (Soggetti e Gestione Fidi base di tutte le pratiche): stessi errori, sette
  volte il costo e undici volte il tempo. 974.305 token di completion contro 58.471; **$4,01 per 22
  schermate in 29 minuti**. Una schermata è fallita per JSON non valido (`52135039__Soggetti`), che
  per scelta non viene ritentato.
- **Ritaglio sul pannello** ([`scripts/make_panel_variant.py`](scripts/make_panel_variant.py)): la
  pipeline porta comunque il lato lungo a 1800 pixel, quindi il ritaglio ingrandisce il testo di
  circa 1,9 volte. Le scadenze tornano giuste (3 su 3 contro 1 su 3), ma un rapporto si rompe e i 3
  NDG restano sbagliati su un'altra cifra (`38214602` invece di `36214802`): l'errore si sposta,
  non sparisce. Ingrandire non aggiunge informazione a cifre alte 7 pixel.

Spesa complessiva verso il provider per questa misura: $7,31 ($2,81 il run principale, $4,01 la
prova a ragionamento alto, $0,48 il pilota e il ritaglio).

## Lettura con OCR locale (RapidOCR)

La direzione del progetto è leggere in locale, non con un modello remoto a runtime
([benchmark del 29/09](../2026-09-29-ocr-cpu-benchmark/README.md)). Stesso motore di allora, provato
sulle stesse 113 schermate, tutto sul PC e senza costo: RapidOCR 3.9.2, PP-OCRv6 small ONNX,
`onnxruntime` 1.30.0, 4 thread, scala 1x
([`scripts/ocr_local_rapid.py`](scripts/ocr_local_rapid.py), risultati in
[`prove/ocr-locale-rapidocr/`](prove/ocr-locale-rapidocr/)).

**Valori letti: 874/920 (95,0%)**; parole delle note ritrovate 2874/3021 (95,1%); 7,7 s di media per
schermata, 12,2 s al massimo, su questa macchina con altri lavori in corso.

La metrica è quella del 29/09: un valore conta se compare nel testo OCR della sua schermata. Misura
la **lettura**, non l'assegnazione ai campi, quindi non va confrontata con il 93,9% di Gemini: è il
tetto di ciò che un estrattore locale può ottenere sopra questo OCR. Due distorsioni note: penalizza
le celle su due righe (`Tipo Op.` 25/41, `Rapporto` 32/41) e premia un valore ripetuto altrove nella
schermata (l'NDG di testata copre una cella letta `38237200`).

Sui numeri piccoli, valori letti esattamente:

| | RapidOCR 1x | Gemini 3.8-flash low |
|---|---:|---:|
| NDG di cointestatari e garanti | 17 su 21 | 13 su 21 |
| Scadenze che contengono un 6 | 24 su 32 | 17 su 32 |
| Rapporti | 39 su 41 | 30 su 41 |

RapidOCR sbaglia meno di Gemini ma nello stesso modo (`381 mesi`, `38306834`, `20515982`), e in 6
schermate non restituisce la cella della scadenza. A scala 2x, provata sulle 23 schermate di
Soggetti e Gestione Fidi base, il risultato è misto: NDG 19 su 21 (erano 17), scadenze con un 6
3 su 8 (erano 5), rapporti 8 su 10 (erano 9).

Conseguenze per la strada locale:

- **Né un modello remoto né l'OCR da soli bastano su queste cifre.** La regola geometrica usata per
  verificare il ground truth (barra sulla terza riga per il 6, strozzatura sulla quarta per l'8)
  separa senza errori i 34 sei e i 13 otto degli NDG dei soggetti: è il candidato naturale per un
  controllo locale a valle dell'OCR. Non è stato costruito né provato come correttore.
- **Etichette di addestramento.** Le etichette di LiLT prodotte da Gemini portano lo stesso errore
  sui campi a carattere piccolo. Vanno verificate sui pixel prima di una nuova iterazione.
- **Insieme di test.** Queste 12 pratiche, mai usate per addestrare, sostituiscono la sola pratica
  LUNARDI come banco di prova, con ground truth controllato sui numeri piccoli.

## Estrazione dei campi in locale (RapidOCR + LiLT `model_v2`)

È il numero confrontabile con quello di Gemini: stesso ground truth, stesso `classify_field()`.
Modello del 29/09 (iterazione 2, addestrato su 196 schermate con etichette Gemini), mai riaddestrato.
Le parole vengono dall'OCR locale qui sopra; le predizioni sono state calcolate su Modal (volume
`bper-lilt-spike`, 4 CPU, 96 s in tutto, costo non misurato) con `modal_predict_v2.py` non
modificato; i campi sono ricostruiti con le funzioni di `mnt/spike-ocr/scripts/ft_eval.py`, caricate
senza modifiche da [`scripts/lilt_to_outputs.py`](scripts/lilt_to_outputs.py). Lo stesso percorso
rifatto sulle 9 schermate LUNARDI restituisce 63/77 (81,8%), come il 29/09.

| | Corretti | |
|---|---:|---:|
| **RapidOCR + LiLT, ricostruzione corretta** | 677/1008 | **67,2%** |
| Solo i campi per cui il modello ha un ruolo (niente scheda privati né tooltip sul Tipo) | 663/965 | 68,7% |
| Ricostruzione iniziale | 580/1008 | 57,5% |
| Gemini 3.8-flash low, per confronto | 947/1008 | 93,9% |

| Tipo di pagina | LiLT | Gemini |
|---|---:|---:|
| Elenco | 84,8% | 91,1% |
| Soggetti | 78,1% | 95,8% |
| Elenco con tooltip | 74,0% | 87,3% |
| Fidi con tooltip | 60,2% | 95,2% |
| Note | 59,1% | 97,0% |
| Fidi | 57,8% | 96,6% |
| Scheda Privati (campi non previsti dal modello) | 36,8% | 94,7% |

Per pratica va dal 49,5% (51531667, due fidi e quattro garanzie) all'83,5%.

I 331 errori sono soprattutto di **assegnazione**, non di lettura: il valore giusto è nel testo OCR
ma il campo prende parole in più o la riga sbagliata. Esempi: NDG `51185037 32015734` (numero pratica
più NDG), `n_fido` = `F1 201.000 Sostituzione FE1 F2`, importo preso da `Totale accordato`, `tipo_op`
= `in`, denominazione di testata con nomi presi da altre righe. I campi più deboli:
`tipo_op` 10/45, `denominazione` 47/102, `importo_euro` 21/45, `scadenza` 25/45, `rapporto` 29/45.

Non verificato: se qualcuna di queste 12 pratiche fosse già fra le schermate usate per addestrare
`model_v2`.

## Revisione manuale del ground truth

Il ground truth resta una bozza finché una persona non lo controlla. Per farlo c'è un file Excel,
`mnt/riscontro-2026-10-07/revisione/revisione_ground_truth_v3.xlsx` (11 MB, ignorato da git), generato da
[`scripts/make_review_workbook.py`](scripts/make_review_workbook.py): una riga per ciascuno dei 1008
valori, con il ritaglio dello screenshot, un riquadro sul valore, il valore trascritto e tre celle
gialle da compilare (Esito, Valore corretto, Note).

- **Posizione dei valori:** dalle righe dell'OCR locale. L'OCR dà una casella per riga, non per
  parola: le parole sono collocate sulle macchie d'inchiostro della riga, e ogni valore è cercato
  solo nella regione del suo campo (la testata, la riga della tabella, la metà dei fidi proposti).
  Una nota è incorniciata come blocco di righe.
- **Colore del riquadro:** rosso su 924 valori, il riquadro è sul testo. Arancione su 14: il valore è
  a schermo ma l'OCR non ha letto la cella (icone a lettera, celle coperte in parte da un tooltip, la
  testata di una schermata), e il riquadro segna la zona dove cercarlo. Azzurro su 70: il valore
  atteso è vuoto, il riquadro segna solo ciò che deve restare bianco e sopra l'immagine c'è scritto.
- **Priorità:** 85 righe sono marcate `ALTA` (Gemini o l'OCR leggono altro, posizione stimata,
  cifre piccole non verificate in automatico).
- **Cifre piccole:** anche un disegno pixel per pixel inganna l'occhio, quindi ogni 6 e 8 delle
  tabelle di dettaglio è controllato da [`scripts/pixel_six_eight.py`](scripts/pixel_six_eight.py),
  che non conosce i modelli. Su 99 valori con un 6 o un 8 ne verifica 89 (149 cifre: 106 sei e 43
  otto): **nessuna discordanza con la trascrizione**, punteggi da +154 a +232 per i 6 e da -184 a
  -104 per gli 8. Degli altri 10, 6 non sono abbinabili carattere per carattere e 4 non hanno una
  posizione esatta.
- **Ritorno:** [`scripts/apply_review.py`](scripts/apply_review.py) rilegge il file compilato e scrive
  `dati_revisionato.csv` con le correzioni, l'esito e il valore precedente; elenca le righe marcate
  ERRATO senza valore corretto. Provato su una copia del file con 4 esiti di prova.
- **Schermate intere:** nella stessa cartella c'è `schermate_riferimento.zip` (16 MB, ignorato da
  git) per chi revisiona, quando il ritaglio non basta. Contiene i 113 PNG di
  `mnt/riscontro-2026-10-07/`, identici byte per byte e con lo stesso nome, cioè il valore della
  colonna `ID schermata` più `.png`.

### La prima versione aveva riquadri sbagliati

Il primo file (ora in `mnt/riscontro-2026-10-07/revisione_versioni_superate/`, con la seconda versione) è stato scartato alla prima apertura:
diversi riquadri non erano sul valore. Le cause, tutte nello script e non nel ground truth:

| Causa | Effetto |
|---|---|
| Le parole dentro una riga dell'OCR erano collocate in proporzione al numero di caratteri | Riquadri spostati o che tagliavano il testo (NDG e denominazione di testata, filiale relazione) |
| `align_value` di `ft_data.py` limita alla regione del campo solo la prima parola del valore | Nella pratica 51531667, che ha anche i fidi in essere, l'ultimo gruppo del rapporto finiva sulla copia nella tabella accanto (riquadro largo 466 pixel); descrizione e importo sul fido in essere |
| Una cella su due righe letta come una riga sola, con la seconda prima della prima | Riquadro sulla prima riga soltanto: 8 rapporti, 1 denominazione |
| Testata non letta dall'OCR (1 schermata) | NDG e denominazione di testata incorniciati sulla prima riga della tabella dei soggetti |
| `align_note` di `ft_data.py` usa `difflib` con `autojunk` attivo, che oltre i 200 caratteri ignora le lettere frequenti | Tutte le 18 note: riquadro esteso al menu di sinistra e più corto del testo. Su 292 righe di nota leggibili il criterio ne riconosceva 133 |
| Un'icona accanto a una sigla contata come testo | Riquadro sulla graffetta invece che su `BC`; `ABB` allargato al fumetto |

`align_note` è anche la funzione che il 29/09 ha etichettato le note per l'addestramento di LiLT: la
stessa perdita è probabile in quelle etichette, e va verificata prima del prossimo addestramento.

### La seconda versione usava l'arancione per due cose

Alla prima apertura della seconda versione il revisore ha segnalato riquadri arancioni su un'area
vuota (righe 195, 202, 210: la cella `Fase` di una pratica che non ha una fase). Erano corretti, ma
non si capiva: l'arancione valeva sia per "valore non trovato" sia per "qui non deve esserci nulla",
e il ritaglio non mostrava il titolo della colonna. Nella terza versione i 70 valori attesi vuoti
hanno il riquadro azzurro, una scritta sopra l'immagine e il titolo della colonna o l'etichetta nel
ritaglio. Il riquadro è stato anche ristretto a ciò che deve essere bianco: per le righe di soggetti
che non esistono segnava l'intera tabella, righe piene comprese, e per le evidenze vuote includeva il
numero di filiale della colonna accanto. I 924 riquadri rossi sono identici a quelli della seconda
versione.

### Come sono stati controllati i riquadri

- **A vista, tutti.** I 1008 riquadri sono stati guardati uno per uno su tavole di ritagli raggruppate
  per campo, non a campione. Trovato e corretto 1 riquadro sbagliato (la graffetta) e alcuni bordi larghi.
  Dopo la terza versione sono stati riguardati tutti gli 84 riquadri azzurri e arancioni, sulle
  immagini contenute nel file.
- **In automatico.** [`scripts/check_review_frames.py`](scripts/check_review_frames.py) confronta il
  valore con quello che l'OCR legge dentro il riquadro, contando 6 e 8 come la stessa cifra. Sui 906
  riquadri rossi fuori dalle note: 896 contengono esattamente il valore, 4 differiscono per uno o due
  caratteri letti male dall'OCR, 6 contengono qualcosa in più (un'icona fra due sigle in 5 casi,
  l'etichetta `NDG:` in 1). **Nessuno lascia fuori parte del valore.** Esito in
  [`prove/revisione-riquadri/controllo_riquadri.txt`](prove/revisione-riquadri/controllo_riquadri.txt).
  Lo stesso script elenca i riquadri lontani dalla posizione che il campo ha sulle altre pratiche:
  75, tutti spiegati dall'impaginazione (pagina scorsa, colonne più larghe, righe di tabella più basse).
- **Il file.** [`scripts/check_review_workbook.py`](scripts/check_review_workbook.py) lo rilegge: 1008
  righe uguali a `dati.csv`, 1165 immagini ancorate ciascuna alla propria cella, nessuna formula,
  elenco a discesa sull'esito.

Limite: il controllo automatico usa lo stesso OCR che ha collocato i riquadri, quindi non è una
seconda lettura indipendente. Quella tentata (rileggere ogni ritaglio con l'OCR) è caduta a metà per
memoria esaurita sulla macchina e non è stata ripetuta.

## Rispetto alla soglia proposta il 29/09

| Criterio | Esito |
|---|---|
| Identità al 100%, bloccante | **Non rispettato**: 8 NDG di soggetti sbagliati su 33, tutti per un 6 letto 8. NDG di testata 102/102 |
| Accuratezza complessiva almeno 92% | Rispettato (93,9%; 92,9% contando i rapporti) |
| Run completo, nessuna schermata in errore | Rispettato |
| Costo al massimo $0,05 per schermata | Rispettato ($0,025) |

## Cosa questa misura non dice

- **Riconoscimento delle pagine.** Il router e il classificatore non sono stati provati su queste
  schermate, né sulle 18 `OffTopic`.
- **Percorso live.** Il comando usa il percorso file (`extract_from_screen()`); l'edge-agent passa da
  `extract_from_image()` dopo `preprocess_for_ocr()`.
- **Variabilità.** Un solo run; nella baseline del 29/09 oscillava di un campo su 77.
- **Scheda privati.** Una sola pratica, 5 schermate dello stesso soggetto.
- **I 9 screenshot del 29/09.** Lì le cifre delle tabelle sono alte 5 pixel e non si possono
  verificare sui pixel: gli NDG dei soggetti 2 e 3 di quel ground truth poggiano sulla stessa lettura
  a vista che qui sbaglia.

File: `run1.outputs.json`, `run1.debug.csv` (rigenerato con il ground truth completo), `run1.log`,
`summary.json`, `controlli.json`.
