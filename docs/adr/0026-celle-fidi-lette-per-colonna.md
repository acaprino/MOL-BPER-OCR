# 0026 — Celle Fidi lette per colonna sotto la testata della tabella

- Data: 2026-11-07
- Stato: Accettato

## Contesto

Sulle pratiche nuove LiLT trova la riga del fido ma confonde le sue celle, soprattutto quelle
a capo. In `M.F. PF FONDO` su due righe, `PF` finisce in Tipo Op. e `FONDO` nello sfondo; la
data finisce in Importo; `NO` di `M.I.PF NO FOND` finisce in Tipo Op. e `FOND` in Rapporto. Sono
errori di colonna su parole lette bene, e la posizione dice già cosa sono: ogni cella sta sotto
la sua testata. La tabella ha una struttura fissa, due tabelle affiancate con le stesse colonne:
a sinistra i fidi proposti, che sono i valori revisionati.

## Decisione

Il modello trova la riga, la testata dice cosa è ogni parola. `_fidi_cells()` parte dal numero
di fido predetto più in alto (la riga di [ADR 0023](0023-campi-fidi-dalla-prima-riga-della-tabella.md))
e legge i cinque campi per colonna, anche le parole che il modello ha dato ad altri ruoli o allo
sfondo:

- una colonna finisce a metà strada verso la testata successiva, perché le celle sono centrate;
- la prima parte dal numero di fido, perché un rapporto su una riga è più largo della sua testata;
- l'ultima finisce prima della colonna numero della tabella di destra, che ne resta fuori;
- una parola appartiene alla cella se il suo centro sta nella colonna, entro 0,9 altezze dal
  numero (`FIDI_CELL_REACH`) e prima della riga successiva. Le parole delle celle stanno entro
  0,61 altezze, tooltip e riga successiva iniziano da 1,18.

Una cella senza parole resta vuota. La testata tollera le letture sbagliate dell'OCR
(`Deacrizione`, `Típo`, `Tip`). Se non si legge intera, o se il numero non sta a sinistra di
Rapporto (un numero della tabella Garanzie), restano i ruoli del modello: oggi succede su 2
schermate, `51788077__GestioneFidi` e `51788077__GestioneFidi_Tooltip2`.

La metrica passa a `strict-v5-fidi-columns`: le stesse predizioni danno valori diversi, quindi i
rapporti precedenti non si confrontano con i nuovi senza ricalcolo.

## Conseguenze e verifica

Dalle etichette revisionate nessun campo si perde: 0 su 574 in addestramento, 0 su 126 in controllo,
0 su 287 in altre pratiche revisionate, e nessuna parola etichettata cade fuori dalla sua colonna.

Su 9 pratiche revisionate, misurate da modelli che non le hanno viste, con le regole di questo ADR e
dell'[ADR 0025](0025-righe-dei-soggetti-centrate-e-testata-sulla-riga-ndg.md) due modelli passano da
275/360 a 312/360 e da 307/360 a 340/360 campi esatti, con Fidi non vuoti 88/106 e 104/106.

In validazione entrambi restano a 139/146: i 7 errori sono tutti letture dell'OCR, e G5 Fidi resta
a 22/25 contro le 23/25 richieste.

La regola è ricavata dagli errori di quelle pratiche, quindi lì non è più una stima
indipendente: la prova è il test, sigillato fino al congelamento, e non è stato eseguito. Se l'applicazione cambiasse la testata della tabella, la lettura tornerebbe ai ruoli
del modello invece di sbagliare colonna.

`test_training_evaluation.py` copre la parola nella colonna giusta, la cella a capo, la tabella di
destra, la cella vuota, tooltip e riga successiva, il rapporto largo, la testata letta male o
incompleta e il numero della tabella Garanzie.
