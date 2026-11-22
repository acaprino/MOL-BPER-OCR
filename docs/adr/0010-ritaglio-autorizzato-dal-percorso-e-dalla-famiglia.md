# 0010 - Il ritaglio calibrato: autorizzato dal percorso, limitato alla famiglia

- **Stato:** Accettato
- **Data:** 2026-08-19
- **Supera:** [0009](0009-ritaglio-contenuto-solo-su-inquadratura-calibrata.md)
- **Interessa:** `extraction/config.py`, `extraction/imaging.py`, `extraction/pipeline.py`
- **Test:** `tests/test_content_crop.py`
- **Correlati:** [0001](0001-normalizzazione-inquadratura-frame.md)

## Perche' un ADR nuovo

Lo [0009](0009-ritaglio-contenuto-solo-su-inquadratura-calibrata.md) era stato accettato
e poi corretto in giornata riscrivendolo, contro la regola di immutabilita' di questa
cartella. Questo ADR lo supera e contiene la decisione completa; lo 0009 resta come
storia di come ci si e' arrivati, errori compresi.

## Contesto

`CONTENT_CROP = (0.18, 0.12, 0.98, 0.98)` toglie navigatore e cromatura prima dei
passaggi VLM. Le frazioni sono calibrate sugli screenshot di finestra di `data/dataset/pratiche/51350695`
(846x677-850x680; "848x679" e' la cifra nominale, [0001]). Il navigatore e' impaginato
in **pixel CSS**, non in proporzione: su qualunque finestra non resa a quella larghezza
la sua quota cambia e le stesse frazioni tagliano dentro le colonne.

Misure che fondano la decisione:

1. **Cattura reale 1536x1032:** bordo sinistro del ritaglio a x=276, oltre le colonne
   NDG, Denom., Tipo e Importo; NDG `32084406` estratto come `06`. Sugli stessi tre
   screenshot reali, l'estrazione senza alcun ritaglio ha battuto quella con il crop.
2. **1280x1024 (5:4, risoluzione storica da terminale):** dista lo **0.09%**
   dall'aspetto calibrato 848/679. Nessuna tolleranza sull'aspetto puo' respingerla.
3. **Finestra operatore reale 1296x1027:** la banda alta del 22% (`HEADER_IN_CONTENT`)
   contiene solo cromatura del browser, logo e barra schede; al 35% la barra NDG appare
   tagliata a meta' sul bordo. Nessuna banda fissa contiene gli identificativi su una
   finestra arbitraria.

## Decisione

**1. Il ritaglio e' autorizzato dal punto di ingresso, non dall'immagine.**
`extract_from_image()` (percorso live: edge-agent) non ritaglia mai: nessuna finestra
operatore e' il riferimento reso a 848px, ogni operatore ha una risoluzione diversa,
quindi li' un match e' sempre una coincidenza, e una coincidenza viene amputata come
qualunque altra inquadratura. `extract_from_screen()` (file su disco: CLI, GUI) fa
opt-in.

**2. Anche sul percorso da file, il ritaglio richiede l'appartenenza alla famiglia:
aspetto E dimensione.** `select_content_crop()` approva solo aspetto entro il 5% da
848/679 **e** lato lungo in 800-900px. La sola tolleranza d'aspetto approverebbe i
1280x1024 caricati dalla GUI o messi in `INPUT_DIR` (misura 2). I riferimenti sono
larghi 846-850px e `normalize_image()` **non ingrandisce mai** (ridimensiona solo verso
il basso), quindi nulla di sostanzialmente piu' grande o piu' piccolo puo' essere uno
di loro.

**3. Fuori taratura, il passaggio anchor legge l'immagine intera.** Dare in pasto
all'anchor una banda fissa di un'immagine non calibrata e' l'amputazione del crop un
livello piu' in basso (misura 3): gli identificativi possono cadere fuori da qualunque
frazione fissa. Il costo e' un payload maggiore su quella chiamata.

**4. Fuori taratura, un retry piu' lungo puo' riempire una tabella vuota, mai
sostituirne una letta.** Le bande `RETRY_AREAS` sul percorso live sono fasce della
finestra grezza e includono la colonna del navigatore: una riga spuria letta dal testo
dei menu, adottata perche' "piu' righe vinceva", diventerebbe un `ndg_N` fabbricato
nella pratica consolidata. Sul percorso calibrato la regola di adozione resta quella
storica.

**5. La decisione e' osservabile.** Il risultato porta `_content_crop:
"calibrated"|"full-frame"`; i salvataggi di debug usano nomi distinti (`CONTENT` vs
`CONTENT_FULL`, `HEADER_IN_CONTENT` vs `HEADER_FULL`), cosi' un frame intero non e'
scambiabile per un ritaglio genuino durante una ricalibrazione.

## Cosa resta scoperto, dichiarato

- **Le bande `RETRY_AREAS` fuori taratura restano frazioni non calibrate** della
  finestra grezza: la mitigazione del punto 4 limita il danno delle tabelle, ma i retry
  scalari leggono comunque bande spostate (il merge scalare e' gia' conservativo:
  riempie campi deboli, non sovrascrive valori letti).
- **Un file estraneo che capita nella famiglia per aspetto E dimensione** (es. un
  850x680 qualunque) verrebbe ritagliato. Dalla sola geometria non e' distinguibile:
  oltre servono i pixel.
- Il percorso CLI sui riferimenti e' **identico bit a bit** a prima della serie
  0009/0010: la baseline di accuratezza non si muove (test dedicato).

## Conseguenze

Al giro di cattura live: frame interi al VLM, anchor sull'immagine intera, tabelle non
sostituibili da retry fuori banda. Una seconda famiglia di riferimenti aggiunge una
voce di calibrazione in `select_content_crop()`, non un nuovo meccanismo ne' un nuovo
consumatore ([0001] vieta di ri-derivare i ritagli altrove).
