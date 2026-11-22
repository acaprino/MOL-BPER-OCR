# 0028 — Tabelle Elenco e Soggetti lette per colonna

- Data: 2026-11-07
- Stato: Accettato

## Contesto

Dopo l'[ADR 0026](0026-celle-fidi-lette-per-colonna.md), su 9 pratiche revisionate
misurate da modelli che non le hanno viste restavano 18 errori su 360: 12 letture dell'OCR e 6
del modello. I 6 erano parole messe nella colonna sbagliata, o lasciate fuori:

- `BPM-SI` in Tipo su due schermate, sotto la colonna Area, con la colonna Tipo fatta scorrere via;
- `IB`, sotto la testata Denom., unito alla Fase: `IB IST`;
- una `B` della barra delle schede del browser unita alle Evidenze: `B BC`;
- `DANIELE`, dal pannello di sinistra, unito alla denominazione di un soggetto;
- `Cointestato` non assegnato a nessun soggetto.

Come per i Fidi, la posizione dice già cosa è ogni parola.

## Decisione

**Soggetti.** `_subject_cells()` legge per colonna: il modello dice che la pagina ha i soggetti,
la testata della tabella dice cosa è ogni parola. Le righe sono i numeri sotto `NDG`, allineati a
destra. Denominazione e Ruolo sono allineati a sinistra: una colonna parte dal bordo sinistro
della sua testata e finisce a quello della successiva. Se la testata non si legge intera, restano
i ruoli del modello.

**Elenco.** `_list_columns()` si applica alla tabella con `ABI` e `Denom.` in testata, ed è un
filtro: qui una cella può contenere icone che l'OCR legge come parole, quindi le parole restano
quelle scelte dal modello. Una parola con il ruolo Tipo, Stato, Fase, Creazione o Evidenze deve
stare entro un'altezza di parola dalla sua testata (le celle revisionate stanno entro 0,6). Senza
la testata del ruolo non si può distinguere una colonna fatta scorrere via da una testata letta
male: il ruolo perde solo le parole entro due altezze da un'altra testata nota. La colonna
Evidenze resta sempre a destra, quindi senza la sua testata conserva le sue parole.

La somiglianza per riconoscere una testata sale da 0,75 a 0,8: a 0,75 `Importo` valeva `Tipo`.

La metrica passa a `strict-v6-table-columns`: le stesse predizioni danno valori diversi, quindi i
rapporti precedenti non si confrontano con i nuovi senza ricalcolo.

## Conseguenze e verifica

Dalle etichette revisionate nessun campo supervisionato si perde: 0 su 638 in addestramento, 0 su 126 in
controllo, 0 su 287 in altre pratiche revisionate. Letti soltanto per colonna, senza i ruoli del
modello, i Soggetti sbagliano solo dove sbaglia l'OCR: `KOLAALTIN`, `LA MORGIAANDREA`, `Coinstine`,
`LANDOGNAANTONINO`; nelle altre pratiche revisionate nessun errore.

Con le stesse predizioni, sulle 9 pratiche misurate da modelli che non le hanno viste si passa da 342 a 348 campi esatti
su 360, con Soggetti 51/51: tutti i 12 errori rimasti sono letture dell'OCR. In controllo
resta 139/146.

Le regole vengono dagli errori di quelle pratiche, quindi lì la stima è ottimistica: il test
non è stato usato per ricavarle e la prova cieca resta il test sigillato. Se
l'applicazione cambiasse le testate, i Soggetti tornerebbero ai ruoli del modello e il filtro
dell'Elenco smetterebbe di togliere parole, invece di sbagliare colonna.

`test_training_evaluation.py` copre cella letta sotto la testata, parola nella colonna sbagliata,
parola fuori tabella, cella su due righe, NDG non predetto, pulsante sotto la tabella, pagina senza
soggetti e testata incompleta; per l'Elenco la colonna sbagliata, la colonna fatta scorrere via, la
testata letta male, `Importo` non preso per `Tipo`, la colonna Evidenze e le pagine senza quella
tabella.
