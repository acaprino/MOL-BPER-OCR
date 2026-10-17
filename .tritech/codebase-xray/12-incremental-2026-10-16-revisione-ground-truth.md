# Revisione ground truth 3.1 — 16 ottobre 2026

Aggiornamento circoscritto alla revisione manuale del dataset delle 12 pratiche.
Base Git effettiva: `7826bdb9469133c7a3d3b20197a69c519711c98a`, working tree dirty.
Le modifiche applicative e documentali non committate descritte nell'incremento 11,
lo spostamento staged nella cartella `.tritech/` e gli altri lavori preesistenti
sono preservati e non fanno parte di questo intervento. Nessun file applicativo,
prompt, test o generatore storico è stato modificato da questa revisione.

## Fonte e artefatto

- Fonte restituita da Rita: `C:/Users/alfio/Desktop/Revisione_ground_truth_v3_02.xlsx`.
- SHA-256 fonte: `5ad66a8c2a0beb79c6a7e07d7fc12ab8169c1b5af3d9362238ec1b049bee6c3f`.
- Output: `mnt/riscontro-2026-10-07/revisione/Revisione_ground_truth_v3_1.xlsx`.
- SHA-256 output finale: `483e1ab4f48b47de757a13b564ab4a3c102e2c6f39675721b2698da8ce3b20d4`.
- La copia proposta prima della conferma, SHA-256
  `927db3a0f7402ae0c0a93a801b80b9f8a329b2769098948d0a644d9934afd378`,
  è conservata in `.tritech/local/ground-truth-v3-1/awaiting-confirmation.xlsx`.
- L'output è locale e ignorato da Git, come gli screenshot sorgenti. L'originale
  di Rita e la versione 3 non sono stati sovrascritti.

## Riscontri e flusso aggiornato

Tutte le 1.008 chiavi `(ID schermata, Campo)` e tutti i valori iniziali del file
restituito coincidono con il CSV storico delle 113 schermate. Non ci sono formule
nel materiale restituito. Gli esiti sono 989 `OK` e 19 `ERRATO`.

Le 16 correzioni esplicite di Rita riguardano `Evidenze`: 9 `P` diventano vuoti
e 7 `B P` diventano `B`. I nove testi letterali `"vuoto"` sono convertiti in celle
effettivamente vuote nella nuova colonna dei valori; il testo originale di Rita
resta conservato. La P cerchiata del segmento Privati è distinta dalla P verde
non cerchiata, che non viene eliminata con una regola indiscriminata.

Il file 3.1 conserva le colonne A–O, compresi esiti e note originali di Rita,
salvo il ripristino di B645 a `52080223`, verificato nella versione originale e
nelle colonne C/O. Le nuove colonne sono P `Valore aggiornato v3.1`, Q `Stato v3.1`,
R `Nota v3.1`; il filtro è esteso ad A:R. Istruzioni e note spiegano la lettura
delle nuove colonne. I 989 valori confermati e le 16 correzioni sono recepiti.

**Conferma dell'utente ricevuta il 16/10/2026:** righe 293–295, pratica 52060489,
`NDG 4`, `DENOMINAZIONE 4`, `RUOLO 4`. Rita ha contestato la posizione del
riquadro senza fornire un valore. Nell'immagine reale ci sono tre righe:
l'ultima contiene `21310900`, `ZHENG LINA`,
`Nuovo Garante/nuovo Datore Di Pegno`, già presenti come soggetto 3 alle righe
290–292. L'utente ha risposto «Sì» alla domanda esplicita di mantenere questi
dati nel soggetto 3 e lasciare vuoto il soggetto 4. La versione finale 3.1
registra questa decisione: P293:P295 restano vuoti, Q indica
`Confermato dall'utente`, le note e le didascalie non indicano più una conferma
pendente. Nessuna duplicazione del soggetto 3. Il totale finale è 989 conferme
di Rita, 16 correzioni di Rita e 3 conferme dell'utente: **1.008 righe revisionate**.

L'importatore storico `baselines/2026-10-07-riscontro-12-pratiche/scripts/apply_review.py`
continua a leggere G/H/I/J, non le nuove colonne P:R. Non è stato modificato né
eseguito sul file 3.1, e nessun CSV operativo o risultato di benchmark è stato
sovrascritto o ricalcolato. Per un successivo import va usato esplicitamente il
valore aggiornato di P, includendo la conferma dei tre casi.

## Correzione delle immagini

Il generatore storico `make_review_workbook.py:668` collocava artificialmente il
riquadro sotto l'ultima riga quando il soggetto atteso non esisteva. La verifica
visiva e la contestazione dell'utente hanno confermato che quel riquadro non è
un riferimento utilizzabile a un campo reale. Il generatore storico resta
immutato come parte del baseline; la versione 3.1 corregge il prodotto generato.

Sono aggiornate 63 immagini: 45 casi di soggetti assenti (inclusi 9 casi analoghi
non annotati da Rita), 2 riferimenti alla tabella Soggetti della pratica 52068422,
16 casi Evidenze. Il contesto mostra la tabella reale; per i tre casi confermati
i riquadri sono sui valori dell'ultima riga visibile, con la relativa spiegazione.
I soggetti assenti non vengono riempiti sulla base dello spostamento di un riquadro.

I 23 ritagli sorgenti sono copie esatte, pixel per pixel, delle regioni dei PNG
originali: nessun carattere o importo è stato generato o ricostruito. I riquadri
sono elementi vettoriali nativi di Excel. Sono preservati tutti i 929 media
originali, le 1.103 immagini non interessate e l'illustrazione aggiunta da Rita
in J91. I PNG sorgenti completi restano anche nel pacchetto per la provenienza.

## Verifiche nuove e limiti

- Validazione indipendente delle 1.008 righe, 16 correzioni, 989 conferme di Rita e
  3 conferme dell'utente; valori e stili originali preservati salvo B645.
- Verifica esatta dei pixel di tutti i 23 ritagli; 63 immagini aggiornate e
  54 riquadri contenuti nell'immagine e allineati entro un pixel.
- XML del pacchetto rileggibile, collegamenti alle immagini e identificativi
  coerenti; convalide e blocco dei riquadri preservati.
- Importazione e anteprime del workbook tramite Artifact Tool. Ispezionate
  visivamente le righe 293, 294, 295, 191, 8 e 548. Il ritaglio nativo OOXML non
  veniva rappresentato dal renderer: sostituito con il ritaglio esatto dei pixel
  originali, mantenendo i riquadri vettoriali. La verifica finale usa questa versione.
- Il runtime Node ha restituito exit code 1 dopo avere completato e stampato
  export/anteprime, senza una diagnostica successiva. Non è riportato come exit 0:
  il pacchetto prodotto è stato riaperto e verificato indipendentemente con Python
  e da un secondo agente. Microsoft Excel non è stato aperto durante la verifica.
- Due tentativi iniziali dei test nel sandbox sono stati interrotti, senza
  considerarli superati: il primo ha mostrato errori di fixture temporanee;
  il secondo si è fermato al 23% nelle condizioni restrittive dell'ambiente.
- Nuova esecuzione completa fuori sandbox, con directory temporanea nel progetto
  e thread numerici limitati a 1: **303 passed, 3 warnings in 38.60s**, exit 0.
  Le tre segnalazioni riguardano xFormers assente. Nessuna chiamata reale a provider.
- Dopo la conferma esplicita dell'utente, nuova verifica completa sullo stesso
  working tree: **303 passed, 3 warnings in 51.21s**, exit 0, registrata separatamente
  in `pytest-final.txt`. Nuova validazione delle 1.008 righe e ispezione visiva
  delle didascalie finali: nessun caso pendente. Le verifiche antecedenti alla
  conferma restano conservate e non vengono presentate come controlli finali.

Evidenze in `checks/2026-10-16-ground-truth-v3-1/`. Gli strumenti temporanei e le
anteprime sono in `.tritech/local/ground-truth-v3-1/`, ignorata da Git. Questa
revisione non sostituisce l'analisi applicativa dell'incremento 11 e non modifica
né promuove a risultati correnti i benchmark storici.
