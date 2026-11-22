# 0009 - Il ritaglio del contenuto si applica solo all'inquadratura calibrata

- **Stato:** Superato da [0010](0010-ritaglio-autorizzato-dal-percorso-e-dalla-famiglia.md)
- **Data:** 2026-08-19
- **Interessa:** `extraction/config.py`, `extraction/imaging.py`, `extraction/pipeline.py`
- **Test:** `tests/test_content_crop.py`
- **Correlati:** [0001](0001-normalizzazione-inquadratura-frame.md) (l'inquadratura si normalizza alla cattura), [0008](0008-classificatore-locale-prototipi-reali-e-classi-di-scarto.md)

## Contesto

`CONTENT_CROP = (0.18, 0.12, 0.98, 0.98)` toglie navigatore e cromatura prima dei
passaggi VLM. Le frazioni sono calibrate sugli screenshot di finestra 848x679 di
`data/dataset/pratiche/51350695`: lo 0.18 sinistro e' la quota di larghezza che il navigatore occupa in
**quella** finestra.

Il navigatore pero' e' impaginato in pixel CSS, non in proporzione: su una finestra
piu' larga la sua quota scende, e lo 0.18 taglia dentro le colonne della tabella.

**Misurato su una cattura reale 1536x1032** (aspetto 1.488 contro l'1.249 della
calibrazione): il bordo sinistro del ritaglio cade a x=276, oltre le colonne NDG,
Denom., Tipo e Importo. L'NDG `32084406` e' stato estratto come `06`. Nella stessa
misura, l'estrazione **senza alcun ritaglio** ha battuto quella con `CONTENT_CROP`
su tutti e tre gli screenshot reali disponibili.

Il percorso edge-agent rende il caso comune: `normalize_frame()` riporta il frame
alla finestra dell'operatore ([0001](0001-normalizzazione-inquadratura-frame.md)),
e quella finestra ha l'aspetto che l'operatore le ha dato, quasi mai 1.249.

## Decisione

`select_content_crop(size)` in `extraction/imaging.py` restituisce `CONTENT_CROP`
solo se l'aspetto dell'immagine devia meno del 5% da 848/679; altrimenti `None`, e
la pipeline manda l'immagine intera. Header e aree di retry continuano a misurarsi
dentro `content_img`, qualunque esso sia.

La tolleranza e' stretta di proposito. Tutte le inquadrature validate condividono un
solo aspetto, e i due modi di sbagliare non sono simmetrici: ritagliare
un'inquadratura non calibrata distrugge campi in silenzio, non ritagliarne una
calibrata costa solo qualche token di immagine in piu'.

## Rifinitura nello stesso giorno: la decisione appartiene al percorso

La prima versione applicava la guardia di aspetto a ogni immagine, ovunque entrasse.
L'osservazione che l'ha corretta e' dell'utente: **nessuna finestra reale potra' mai
essere il riferimento renderizzato a 848px** -- ogni operatore ha una risoluzione
diversa. Ne segue che sul percorso live un match di aspetto e' *sempre* un falso
positivo: una finestra che capita per coincidenza a proporzione 1.249 ha comunque il
navigatore piu' stretto del 18% calibrato, perche' quello e' impaginato in pixel CSS,
e il ritaglio la amputerebbe come qualunque altra.

Quindi il ritaglio non e' autorizzato da una proprieta' dell'immagine ma dal punto
di ingresso: `extract_from_image()` (percorso live, edge-agent) **non ritaglia mai**;
`extract_from_screen()` (file su disco: i riferimenti di `data/dataset/pratiche/51350695`, la CLI, la GUI)
fa opt-in, e anche li' la guardia di aspetto deve comunque essere d'accordo, cosi'
un file fuori famiglia messo in `INPUT_DIR` non viene amputato.

Il punto cieco della prima versione (aspetto calibrato ma resa CSS piu' larga) resta
teoricamente aperto solo sul percorso da file, dove pero' la famiglia e' chiusa e
nota. Sul percorso live non esiste piu' per costruzione.

## Conseguenze

- Sul percorso CLI (`data/dataset/pratiche/51350695`, 848x679 normalizzati a 1800 mantenendo l'aspetto)
  il comportamento e' **identico bit a bit** a prima: il ritaglio si applica.
- Sul percorso edge-agent le finestre reali passano intere al VLM: nessuna colonna
  amputata, costo per chiamata leggermente maggiore.
- Un'eventuale ricalibrazione per una seconda famiglia di inquadrature aggiunge una
  voce di calibrazione, non un nuovo meccanismo.
