# 0009 - Il ritaglio del contenuto si applica solo all'inquadratura calibrata

- **Stato:** Accettato
- **Data:** 2026-08-19
- **Interessa:** `extraction/config.py`, `extraction/imaging.py`, `extraction/pipeline.py`
- **Test:** `tests/test_content_crop.py`
- **Correlati:** [0001](0001-normalizzazione-inquadratura-frame.md) (l'inquadratura si normalizza alla cattura), [0008](0008-classificatore-locale-prototipi-reali-e-classi-di-scarto.md)

## Contesto

`CONTENT_CROP = (0.18, 0.12, 0.98, 0.98)` toglie navigatore e cromatura prima dei
passaggi VLM. Le frazioni sono calibrate sugli screenshot di finestra 848x679 di
`mnt/data`: lo 0.18 sinistro e' la quota di larghezza che il navigatore occupa in
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

## Cosa questa guardia NON copre

L'aspetto e' un indizio, non una prova. Una finestra con l'aspetto calibrato ma
resa piu' larga in pixel CSS ha comunque il navigatore piu' stretto in proporzione,
e dalla sola dimensione dell'immagine il caso non e' rilevabile. Non e' ancora stato
osservato in nessuna cattura; se compare, il punto dove aggiungere la rilevazione e'
`select_content_crop()`, non un nuovo consumatore ([0001] vieta di ri-derivare i
ritagli altrove).

## Conseguenze

- Sul percorso CLI (mnt/data, 848x679 normalizzati a 1800 mantenendo l'aspetto)
  il comportamento e' **identico bit a bit** a prima: il ritaglio si applica.
- Sul percorso edge-agent le finestre reali passano intere al VLM: nessuna colonna
  amputata, costo per chiamata leggermente maggiore.
- Un'eventuale ricalibrazione per una seconda famiglia di inquadrature aggiunge una
  voce di calibrazione, non un nuovo meccanismo.
