# Piano per la Prossima Versione dell'Estrazione Locale (`next-ver-plan.md`)

**Data:** 2026-10-17 — aggiornato il 2026-10-18  
**Ambito:** Evoluzione della pipeline locale CPU (`OCR + Estrazione dei 45 campi BPER`) rispetto alla baseline `data/training/runs/lilt-v3.1-20261016` e ad `ADR 0022`.

---

## 1. Contesto e Diagnosi Empirica della Baseline Attuale

L'obiettivo della pipeline locale è leggere le schermate dell'applicativo BPER **"Nuova PEF 3.0"** direttamente sul PC dell'operatore o su desktop virtuale (`Pool01-VDI`), **senza GPU**, **senza invio di dati a servizi cloud**, con **latenza compatibile con l'operatività (< 6–10 s per schermata su 2–4 core CPU, <= 1,5 GB RAM)** e **licenze compatibili con uso bancario/commerciale (Apache-2.0, MIT, BSD)**.

**Requisito prioritario e bloccante: il processo deve essere resiliente e stabile.**
Un errore su una schermata deve restare circoscritto e consentire il recupero entro
un tempo massimo definito. Blocchi permanenti, crescita incontrollata delle risorse,
perdita silenziosa di lavoro accettato o attribuzione dei dati alla pratica sbagliata
impediscono la promozione del candidato, anche quando accuratezza e velocità
raggiungono gli altri obiettivi. Questo requisito comprende l'intero percorso locale:
acquisizione, OCR, assegnazione dei campi, consolidamento ed esportazione.

Secondo il contratto fissato in [`docs/adr/0022-addestramento-lilt-da-revisione-umana.md`](adr/0022-addestramento-lilt-da-revisione-umana.md), la pipeline è divisa in due stadi distinti:
1. **Stadio A — Lettura OCR (`Immagine -> Box + Testo`)**: legge i caratteri visibili senza inventare testo non presente nei pixel.
2. **Stadio B — Assegnazione dei ruoli e ricostruzione (`Box + Testo -> 45 campi BPER`)**: assegna i token OCR ai 36 ruoli semantici (`+ O`) e ricostruisce i 45 campi canonici.

### 1.1 Baseline Storica e Provenienza (`ground-truth-v3.1` e `lilt-v3.1-20261016`)

Dall'analisi riga per riga di `data/training/ground-truth-v3.1/alignment_report.csv` (`1.008` righe su `113` schermate di `12` pratiche revisionate in `data/revisione/revisione/Revisione_ground_truth_v3_1.xlsx`) e di `data/training/runs/lilt-v3.1-20261016/test_field_metrics.json` (`22` schermate di test, pratiche `51531667` e `52060489`, `192` valori valutati con metrica `strict-v2-punctuation-spacing`):

| Indicatore | Valore misurato | Dettaglio |
|---|---:|---|
| **Supervisione sul dataset intero (`1.008` righe)** | `863` supervisionate (`92,9%` dei non-vuoti) | `79 empty`, `31 ignored_ocr_mismatch`, `22 partial_supervision`, `13 ignored_alignment` |
| **`content_availability` OCR sul test set (`192` campi)** | **`93,23%` (`179/192`)** | Sui campi non-null: **`92,90%` (`170/183`)**, con **`13` valori `unavailable`** |
| **F1 a livello parola di `LiLT v3.1` (Validazione vs Test)** | Val: **`0,9781`** -> Test: **`0,8889`** | Precision test: `0,8308`, Recall test: `0,9557` (`6.709` parole valutate) |
| **Accuratezza strict a campo intero sul test set** | **`66,15%` (`127/192`)** | `119 correct`, `8 correct_null`, **`38 wrong`**, **`26 missing`**, `1 hallucinated` |

Il report storico `validation_field_metrics.json` misura **115/146 = 78,77%** di
accuratezza globale e **121/133 = 90,98%** di disponibilità OCR sui valori non-null.
Le righe revisionate si distribuiscono in **670 train, 146 val, 192 test**.

**I report del run e gli artefatti correnti del dataset non sono intercambiabili.**
La riconciliazione della Fase 0 ne ha stabilito la causa: il modello del run è
stato addestrato su una versione precedente del bundle, con la stessa cache OCR
(`e261c05b…`) ma allineamento, workbook e codice di `src/training/` precedenti
(844 supervisioni complete e 55 mismatch OCR, contro 863 e 31). Rivalutando le
predizioni salvate sugli esempi correnti con l'evaluatore corrente, valori attesi,
predetti ed esiti coincidono su tutte le 338 osservazioni: l'accuratezza strict
resta **115/146** e **127/192**. Cambia solo la disponibilità OCR, che dipende
dall'allineamento: sui valori non-null è **124/133** in validazione e **178/183**
nel test, contro i 121/133 e 170/183 del run. Le disponibilità della tabella sopra
sono quindi superate. La Fase 0 ha poi riprodotto A0 (113/113 schermate identiche
alla cache) e riaddestrato LiLT sul bundle corrente con lo stesso protocollo e la
selezione dell'epoca sull'accuratezza dei campi interi in validazione: è il B0 dei
gate G4/G5. Le due versioni differiscono sia nell'allineamento di addestramento
sia nel criterio di selezione, quindi il guadagno non è attribuibile al solo
allineamento. I report storici restano immutati; riconciliazione, provenienza,
impronte e nuove esecuzioni appartengono alla X-ray. Anche un confronto
cloud richiede identica popolazione e identici comparatori; i numeri cloud non
verificati su questa popolazione non partecipano ai gate.

### 1.2 Scomposizione dei due colli di bottiglia

1. **Collo di bottiglia Stadio A (5 valori non-null illeggibili nel test sul corpus corrente; 13 nel report storico):**
   - **Il report storico conta 13 valori `unavailable`, di cui 9 `rapporto`, ma 8 di quei 9 dipendevano dall'allineamento precedente, non dall'OCR.** Sei sono `034 0744 0017 05502254` su `51531667__GestioneFidi_Tooltip1..6`: RapidOCR li legge esattamente e LiLT li sbaglia tutti, unendo al valore la seconda riga Fidi (errore di Stadio B). Due sono schermate di `52060489` che LiLT predice già correttamente. La pratica `52060489` ha 4 schermate `GestioneFidi*`, e il `6` letto come `8` (`05666385`) riguarda soltanto `52060489__GestioneFidi`.
   - Con la stessa cache OCR restano illeggibili, oltre a quel `rapporto`, `ndg_1` (`36248986` -> `36248988`) e `ndg_2` (`20515962` -> `20515982`) in `52060489__Soggetti`, sempre un `6` letto come `8` nel font alto **7 pixel** delle tabelle di dettaglio, e le due `note_della_richiesta` (`51531667__Note` e `52060489__Note`): il match strict sull'intero blocco dà `0/2`. La F1 delle parole classificabili (`0,9988`, `tp=411, fp=0, fn=1`) non dimostra la correttezza del valore completo e non permette di attribuire automaticamente l'errore allo scroll.
   - **Distribuzione corrente dei `6` letti come `8`:** i 13 valori sopra vengono dal report storico del run. Nel `alignment_report.csv` corrente, confrontando le sole cifre, le letture 6→8 sono **10 nel train** (4 pratiche, 8 valori distinti: 5 NDG soggetti, 1 `rapporto` e `scadenza` `361 mesi` letta `381 mesi` su due schermate ciascuna di `52068422` e `52135039`), **1 in validazione** (`52126316__GestioneFidi_Tooltip1`, `importo_euro` `160.000` letto `180,000`, con anche il punto letto come virgola) e **3 nel test storico** (un solo `rapporto`, 11/12, più i due NDG). Sul `rapporto` del test il CSV corrente dà 1 errore contro i 9 del run, per la causa riconciliata in §1.1: nel test, 3 dei 5 valori non-null illeggibili sono letture 6→8.
   - **In validazione mancano 9 valori non-null** (124/133, contro i 131 richiesti da G1) e solo uno è una lettura 6→8 (`180,000`). Gli altri sono `scadenza` `301 mesi`, che il detector non rileva su due tooltip di `51659595`, `Nuova Fnanza`, `21 - STELFRANCO`, un `-` iniziale davanti a `LANDOGNA CORRADO`, `tipo` `BMB` escluso dall'allineamento e le due note. Il guadagno atteso da A5 è quindi limitato; le varianti di detector (A2, A3) e il recognizer latino (A4) restano rilevanti per G1.
   - **OCR storico:** `modal_ocr_bench.py` e `modal_ocr_ref.py` configurano la famiglia v6 senza specificare le taglie. Il nuovo runner deve fissare esplicitamente taglia, lingua, classificatore di orientamento, preprocessing, soglie, backend e impronte dei pesi. La variante medium è predisposta in `data/spike-ocr/scripts/ocr_probe_rapid.py`; la sua qualità sul corpus deve essere misurata.
   - **Controllo pixel storico:** recuperabile da `fd043e8:.codebase-xray/baselines/2026-10-07-riscontro-12-pratiche/scripts/pixel_six_eight.py`, verifica testo e coordinate forniti sul font da 7 pixel. Il risultato documentato è **89 valori verificati su 99**, contenenti 149 cifre, senza discordanza con la trascrizione; **10 valori non verificabili**. Non è ancora un correttore OCR automatico e non garantisce copertura completa.

2. **Collo di bottiglia Stadio B (il calo dal `97,40%` di disponibilità OCR corrente, `187/192`, al `66,15%` di `LiLT v3.1`; `93,23%` nel report storico):**
   - Nel report storico di test la disponibilità OCR è **12/12** per ciascuno di `importo_euro`, `n_fido`, `scadenza`, `tipo_op`, `descrizione`, e **2/2** per ciascuno di `denominazione_1..2`, `ruolo_1..3`.
   - Eppure `LiLT v3.1` ottiene:
     - `importo_euro`: **`33,3%` (`4/12`)** (`8 missing`)
     - `n_fido`: **`41,7%` (`5/12`)** (`6 wrong`, `1 missing`)
     - `scadenza`: **`33,3%` (`4/12`)** (`7 wrong`, `1 missing`)
     - `tipo_op`: **`33,3%` (`4/12`)** (`3 wrong`, `5 missing`)
     - `denominazione_1` e `denominazione_2`: **`50,0%` (`1/2`)** ciascuno; `ruolo_1`: **`0/2`**, `ruolo_2`: **`1/2`**.
     - `rapporto`: **`25,0%` (`3/12`)**; metriche di parola `tp=8`, `fp=37`, `fn=4`, precisione **`0,1778`**. Con disponibilità corrente 11/12, 8 dei 9 errori sono di Stadio B, tutti su `51531667`: in 7 schermate LiLT unisce due righe Fidi, in `51531667__GestioneFidi_down` non restituisce il valore.
   - **Ipotesi da verificare su train/val:** overfitting lessicale e insufficienza dei vincoli di riga/colonna. Le differenze di formato tra pratiche e i falsi positivi motivano confronti controllati; non dimostrano da soli la causa del calo. Anche il contributo di detector e recognizer al tempo CPU va misurato.

### 1.3 Copertura dei 45 Campi

Validazione e test storici coprono soltanto **30 campi con esempi positivi**.
Mancano tutti i 13 campi Scheda Privati e i due tooltip
`tooltip_descrizione_m_consap` e `tooltip_descrizione_consap_dr_bis`.
I risultati sul corpus esistente qualificano solo l'ambito effettivamente coperto.
L'adozione dei 45 campi richiede nuove pratiche e il gate G8.

---

## 2. Vincoli di Licenza e Perimetro Tecnologico

### 2.1 Componenti Candidati e Verifica degli Artefatti

Per ogni componente, il manifest registra versione, revisione, origine, SHA-256,
licenza del codice, licenza dei pesi e avvisi da distribuire. La verifica riguarda
gli artefatti effettivamente inclusi e va chiusa prima del packaging.

- **RapidOCR:** codice e modelli ufficiali derivati da PaddleOCR dichiarati Apache-2.0; verificare i file ONNX e il runtime scelti. Fonti: [RapidOCR](https://github.com/RapidAI/RapidOCR#-license), [avviso sui modelli](https://rapidai.github.io/RapidOCRDocs/main/en/model_licenses/).
- **Controllo pixel e parser:** codice interno; il parser esistente usa la libreria standard, il controllo pixel usa Pillow. Includere gli avvisi delle dipendenze.
- **LightGBM / scikit-learn / python-crfsuite:** candidati con licenze permissive dei rispettivi progetti; verificare versioni e dipendenze native. B2 resta condizionale.
- **LiLT:** implementazione [MIT](https://github.com/jpWang/LiLT/blob/main/LICENSE); le model card [SCUT](https://huggingface.co/SCUT-DLVCLab/lilt-infoxlm-base) e [nielsr](https://huggingface.co/nielsr/lilt-xlm-roberta-base) dichiarano MIT nei metadati. Conservare provenienza e termini dell'esatta revisione dei pesi e del tokenizer; l'assenza di un file LICENSE separato non equivale ad assenza di una dichiarazione di licenza.

### 2.2 Componenti esclusi dal piano
| Tecnologia | Motivo di esclusione |
|---|---|
| `LayoutLMv2`, `LayoutXLM`, `LayoutLMv3` | I checkpoint Microsoft [v2](https://huggingface.co/microsoft/layoutlmv2-base-uncased), [XLM](https://huggingface.co/microsoft/layoutxlm-base), [v3](https://huggingface.co/microsoft/layoutlmv3-base) dichiarano termini non commerciali; esclusi dalla baseline permissiva. |
| `Surya OCR` / `Marker` / `Chandra` | Codice e pesi hanno termini distinti. Le licenze dei pesi prevedono condizioni commerciali specifiche: [Surya](https://github.com/datalab-to/surya#commercial-usage), [Marker](https://github.com/datalab-to/marker#commercial-usage), [Chandra](https://github.com/datalab-to/chandra#commercial-usage). Fuori dalla baseline permissiva. |
| `EasyOCR` / `CRAFT` | Codice [EasyOCR](https://github.com/JaidedAI/EasyOCR/blob/master/LICENSE) Apache-2.0 e repository [CRAFT](https://github.com/clovaai/CRAFT-pytorch/blob/master/LICENSE) MIT: non si assume un divieto commerciale generale dei pesi CRAFT. Fuori dalla matrice principale; un'eventuale prova richiede inventario dei pesi e confronto riproducibile. |
| `Nougat` | [Codice MIT e pesi non commerciali](https://github.com/facebookresearch/nougat#license); escluso dalla baseline permissiva. |
| `OmniParser` | Il [README Microsoft](https://github.com/microsoft/OmniParser#model-weights-license) distingue detector precedenti AGPL, nuovo detector basato su YOLOv9 MIT e caption model MIT; il repository ha termini propri. Fuori dalla baseline, con eventuale verifica della versione e dei componenti completi. |
| `BROS-base` e VLM locali generativi | Fuori dalla matrice principale; riconsiderarli soltanto con evidenze di qualità, latenza CPU e risorse sugli stessi profili. Non generalizzare tempi di altri hardware alla VDI. |
| `winocr` come motore primario | Richiede verifica dei language pack effettivamente disponibili sull'immagine Windows Server/LTSC della VDI. |

---

## 3. Matrice delle Combinazioni da Testare

### 3.1 Stadio A — Configurazioni Motore OCR (6 combinazioni)

Il detector localizza il testo e il recognizer legge i ritagli. Il
[catalogo ufficiale](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml)
supporta le taglie v6 `tiny`, `small`, `medium` e il recognizer v5 latino `mobile`.
Fissare versioni e impronte nella Fase 0; misurare separatamente tempi e dimensioni
reali dei componenti, senza assumere quale domini il costo CPU.

| ID | Nome Configurazione | `Det` (Riquadri) | `Rec` (Lettura) | Post-processing Cifre 7px | Ipotesi da verificare |
|---|---|---|---|---|---|
| **A0** | **Baseline `v6_small`** | `PP-OCRv6 SMALL` | `PP-OCRv6 SMALL` | Nessuno | Riprodurre una baseline coerente prima dei confronti. |
| **A1** | **Hybrid `det_small_rec_medium`** | `PP-OCRv6 SMALL` | **`PP-OCRv6 MEDIUM`** | Nessuno | Misurare qualità e costo del recognizer più grande. |
| **A2** | **Full `v6_medium`** | **`PP-OCRv6 MEDIUM`** | **`PP-OCRv6 MEDIUM`** | Nessuno | Misurare recupero delle celle e costo del detector. |
| **A3** | **Fast `det_tiny_rec_medium`** | **`PP-OCRv6 TINY`** | **`PP-OCRv6 MEDIUM`** | Nessuno | Misurare il compromesso tra localizzazione e tempo. |
| **A4** | **Latin `det_v6_small_rec_v5_latin`** | `PP-OCRv6 SMALL` | **`PP-OCRv5 LATIN MOBILE`** | Nessuno | Misurare lettura di italiano, cifre e punteggiatura. |
| **A5** | **Controllo pixel sul migliore A0–A4 scelto nella Fase 1** | Come il candidato | Come il candidato | Correzione verificabile con astensione | Confrontare con il motore senza correzioni secondo il protocollo sotto la tabella; misurare copertura, correzioni giuste e sbagliate, regressioni e overhead. |

A5 deve ricavare box e abbinamenti dei caratteri senza il valore atteso, operare
sui pixel alla risoluzione supportata e conservare testo originale, correzione,
evidenza e motivo di astensione. L'obiettivo di 20 ms riguarda il solo controllo
pixel; un eventuale re-OCR dei box a 3× è una variante distinta, con tempo totale
misurato. Nessuna promessa di zero errori precede la verifica.

A5 si sviluppa sul train e si misura per pratica. Il report riporta separatamente
ciascuno dei 10 casi 6→8 del train (8 valori distinti in 4 pratiche, §1.2); se A5
ha soglie regolabili, il guadagno si stima lasciando fuori una pratica alla volta.
La validazione contiene un solo caso positivo, quindi non misura il guadagno ma le
regressioni: sulle cifre `6` e `8` già lette correttamente nei valori di Fidi e
negli NDG dei soggetti di validazione (oggi 15 e 12, contando le schermate
ripetute) si contano correzioni sbagliate e astensioni, e l'unico caso positivo si
riporta a parte. A5 è promuovibile solo con **zero correzioni sbagliate** in
validazione. La generalizzazione resta da dimostrare sulla conferma indipendente
di G8: le sue pratiche devono includere NDG dei soggetti e rapporti con cifre `6`,
scelti sulla verità revisionata prima delle prove e non sugli errori OCR.
Sul corpus corrente il guadagno osservabile di A5 sui valori held-out è piccolo
(1 caso in validazione, 3 nel test): A5 da sola non porta G1 a 131/133.

---

### 3.2 Stadio B — Assegnazione e Ricostruzione dei Campi

| ID | Architettura | Contratto e verifica |
|---|---|---|
| **B0** | LiLT v3.1 addestrato sul bundle corrente (`lilt-v3.1-20261018-current-bundle`) | Inferenza del checkpoint `cpu_model` sui nuovi box, senza riaddestramento; un ruolo e una probabilità per parola, poi `decode_fields()`. |
| **B1** | Parser di ancore, colonne e righe | Estendere `data/spike-ocr/scripts/anchor_rules.py` su train. Identificare intestazioni e sotto-tabelle, scegliere la riga pertinente, ricostruire celle multilinea, note e tooltip. Se mancano ancore o geometrie affidabili, astenersi. Output: valori per campo con evidenza delle parole/regioni selezionate. |
| **B2** | Classificatore leggero di layout | Feature geometriche relative ad ancore e colonne, indice di riga, altezza e flag tipologici. Escludere nomi propri e valori identificativi dalle feature; verificare comunque overfitting di layout, tempo di training e dimensione effettiva. |
| **B3** | Ibrido B1 + B0, eventualmente B2 | Routing determinato su train/val. Definire condizioni di competenza, conflitto e astensione per campo; conservare evidenza e origine interna. Non scegliere la risposta usando il ground truth. |

I vantaggi attesi delle regole geometriche vanno misurati anche con scroll,
intestazioni incomplete, DPI e dimensioni differenti. L'assenza di pesi neurali
non garantisce invariabilità del layout. Le scelte di riga e di fusione del parser
devono sopravvivere al percorso di valutazione e al consolidamento del risultato.
Latenza sotto 10 ms per B1 e training sotto 10 s / pesi sotto 5 MB per B2 restano
obiettivi sperimentali, da includere nella misura complessiva G6.

## 4. Gate di Selezione e di Adozione

Le soglie percentuali si applicano ai conteggi esatti, senza arrotondare per
superare un gate: per `N` osservazioni servono almeno `ceil(soglia × N)` successi.
I conteggi di validazione sotto indicati riguardano il corpus attuale; dopo
l'estensione della copertura si ricalcolano i minimi con la stessa formula e con
popolazioni congelate prima delle misure.

| Gate | Popolazione e baseline | Criterio |
|---|---|---|
| **G1 — Disponibilità OCR** | Valori non-null: validazione storica 121/133; test storico 170/183. Sul corpus corrente, riconciliati: 124/133 e 178/183. | **>=98,4%** in validazione: almeno **131/133** sul corpus attuale. Sul denominatore storico di 183 corrisponde a **181/183**, non 180. Stessa soglia sulla conferma indipendente. |
| **G2 — Supervisione** | Intero corpus di 1.008 righe: 863 supervisioni complete, 31 mismatch OCR, 22 parziali, 13 esclusioni di allineamento. | Audit del candidato congelato: **<=6 mismatch OCR** e, come obiettivo distinto, **>=890 supervisioni complete su 929 non-vuote**. Recuperare 25 mismatch porta a 888; le altre due righe richiedono miglioramenti ulteriori. Nessuna selezione basata sulle righe di test o sul totale che le contiene. |
| **G3 — Identificativi OCR** | Nel CSV di allineamento corrente: NDG soggetti **26/33**, rapporto **39/41**; in validazione **5/5 e 5/5**. Sono conteggi su occorrenze non-null, distinti dalla disponibilità dei report storici del run. | In validazione **100% degli NDG soggetti** e **>=97,5% dei rapporti**: attualmente 5/5 e 5/5. Dopo il congelamento, audit storico su **33/33** NDG e **>=40/41** rapporti. Stesse percentuali sulla conferma indipendente, con tutte le occorrenze incluse. In validazione G3 è già saturo e non distingue i motori: vale come controllo di non regressione, mentre il confronto tra A0–A4 usa train e validazione (Fase 1). |
| **G4 — Campi completi** | Accuratezza strict, incluse assenze corrette. B0 sul bundle corrente: validazione **124/146** (per pratica 52/72 in `51659595` e 72/74 in `52126316`); test storico 144/192. Run del 2026-10-16: 115/146 e 127/192. | Minimo sperimentale **>=88%**: 129/146 in validazione. Target di adozione **>=92%**: 135/146 in validazione e stessa soglia sulla conferma indipendente. Riportare anche il risultato non-null. Sul vecchio test le equivalenze sono 169/192 e 177/192. |
| **G5 — Tabelle critiche** | Accuratezza micro **non-null**. B0 sul bundle corrente: Fidi val **19/25** (5 dei 10 valori unici), test 25/60; Soggetti val **15/15**, test 19/21. Run del 2026-10-16: Fidi 13/25 e 20/60, Soggetti 10/15 e 10/21. | Fidi **>=90%**, Soggetti **>=92%**, in validazione e conferma indipendente: attualmente almeno **23/25** e **14/15** in validazione. Pubblicare separatamente assenze corrette e allucinazioni. |
| **G6 — Latenza e risorse** | Misura dell'intero processo integrato, con modelli, immagini, coda e risultati residenti. La somma storica 7,69 s OCR + 0,65 s LiLT non è una misura end-to-end certificata. | `pc4`: media **<=6 s**, massimo **<=10 s**; `vdi2`: massimo **<=10 s**. **RAM totale di picco <=1,5 GB** su entrambi i profili, anche nel carico concorrente dichiarato. |
| **G7 — Resilienza e integrità** | Motore reale integrato nell'edge-agent e pacchetto distribuito, su `pc4` e `vdi2`. | **Zero crash non gestiti, blocchi permanenti, duplicazioni di risultati e contaminazioni tra pratiche**; ogni lavoro accettato ha un esito tracciabile; tutte le prove della sezione 5.3 superate. **Bloccante**. |
| **G8 — Copertura e conferma indipendente** | Il corpus esistente non qualifica tutti i 45 campi. | Raccogliere pratiche aggiuntive separate tra validazione estesa e conferma, con controllo di NDG e immagini. Ogni campo richiede esempi positivi in validazione estesa e in almeno **due pratiche di conferma**. Pubblicare supporto e metriche per campo; i campi senza copertura restano non validati. Nessuna adozione dichiarata sui 45 campi senza G8. |

Per G5, **Fidi** comprende `n_fido`, `importo_euro`, `scadenza`, `tipo_op`,
`rapporto`; **Soggetti** comprende tutti i dodici `ndg_1..4`,
`denominazione_1..4`, `ruolo_1..4`. L'unità è l'osservazione di campo per
schermata, senza deduplicare ripetizioni per migliorare il risultato.
Il report conserva anche metriche per pratica: schermate ripetute della stessa
pratica non sono evidenze indipendenti di generalizzazione.

Per G4 e G5 il report affianca al conteggio per schermata quello per valore unico
e per pratica. In validazione i 25 Fidi non-null sono 10 valori unici: `51659595`
ripete 5 valori su 2 schermate, `52126316` 5 valori su 3. Un solo valore sbagliato
porta quindi G5 Fidi a 22/25 se cade in `52126316` e a 23/25 se cade in
`51659595`. Se due candidati superano entrambi un gate, una differenza che dipende
da un solo valore ripetuto non decide la scelta; a parità si sceglie il candidato
più semplice o meno costoso.

La selezione usa soltanto train/val. G2 e l'audit storico complessivo di G3 si
calcolano dopo il congelamento come controlli di regressione. I gate sulla nuova
conferma sono verifiche finali di adozione, senza scegliere tra candidati sul loro
risultato. La copertura minima di G8 non costituisce una garanzia statistica;
l'ADR deve dichiarare il numero di pratiche e i limiti osservati per ogni campo.

## 5. Protocollo Sperimentale

### 5.1 Separazione dei Dati e Congelamento

Preservare gli split del manifest v3.1:

| Split | Pratiche | Schermate | Righe revisionate | Uso |
|---|---|---:|---:|---|
| train | 51185037, 52062600, 52067184, 52068422, 52080223, 52102599, 52130861, 52135039 | 75 | **670** | Sviluppo delle regole e fitting dei modelli; insieme alla validazione, confronto dei motori OCR A0–A4 sulle sole metriche OCR (Fase 1). |
| val | 51659595, 52126316 | 16 | **146** | Scelta OCR, estrattore, soglie e routing; decisioni sulle fasi successive. |
| test storico | 51531667, 52060489 | 22 | **192** | Regressione dopo il congelamento. Già analizzato, quindi non è una nuova prova cieca. |

Il test storico non viene rinominato o spostato in train/val. Non introdurre
eccezioni, coordinate o stringhe ricavate dai suoi errori. L'esecuzione OCR sulle
sue immagini è ammessa per creare cache complete; le metriche e le osservazioni
di test non partecipano alla selezione.

Le nuove pratiche di G8 sono assegnate a validazione estesa o conferma prima
delle prove, con separazione di pratica, NDG dei soggetti e immagini anche rispetto
al corpus originario. La conferma resta sigillata fino al congelamento di codice,
pesi, configurazione, popolazioni e comparatori di un unico candidato. Se fallisce,
non si rilancia una sequenza di candidati sullo stesso insieme dichiarandola cieca:
ogni successiva conferma indipendente richiede un insieme non usato nelle scelte.

### 5.2 Contratti, Riproducibilità e Misure

**Cache OCR.** Ogni configurazione salva tutte le 113 schermate del corpus corrente
con il formato richiesto da `build_dataset()`: identificativo -> `seconds` e
`items` come triple testo, confidenza, quadrilatero. Esempio strutturale con dati
sintetici, non una misura eseguita:

```json
{
  "pratica_demo__Pagina": {
    "seconds": 4.12,
    "items": [["Testo letto", 0.994, [[10, 20], [80, 20], [80, 30], [10, 30]]]]
  }
}
```

`build_dataset()` richiede oggi tutte le schermate del workbook e le 12 pratiche
previste: **non passargli una cache parziale da 38 schermate**. Il piano usa cache
complete e filtra i report per split. Salvare ogni configurazione in una nuova
directory, senza mescolare OCR di motori differenti. Eventuali corpus aggiuntivi
richiedono un contratto esplicito di preparazione, non la rimozione dei controlli
del dataset revisionato.

**Valutazione comune.** `evaluate_predictions()` riceve un ruolo per parola e
ricostruisce i campi con `decode_fields()`. Restituisce `overall.accuracy`,
`overall.counts`, `by_field`, `by_split`, `records`, `missing_predictions` e metriche
di parola; i singoli split hanno `counts` e `by_field`. Non accetta direttamente
il dizionario di campi prodotto da B1. Entrambi i percorsi riportano ora anche
`complete`, falso quando manca l'esito di almeno una schermata, e il numero di
astensioni per riepilogo e per campo.

Prima del benchmark B1/B3, aggiungere al modulo `src/training/evaluation.py` un
ingresso di valutazione per valori di campo. Esso deve condividere comparatori,
record e riepiloghi con il percorso a ruoli, senza duplicare la semantica strict,
preservando le scelte di riga e fusione del parser. Output e astensioni devono
avere uno schema verificato; ogni schermata prevista richiede un esito esplicito.
Un insieme di predizioni incompleto rende la prova incompleta e impedisce la
promozione, anche se l'evaluatore attuale può rappresentarlo come tutti `O`.
F1 delle parole non applicabile a un parser di soli campi va dichiarata tale.

Questo ingresso esiste: `evaluate_field_values()` riceve per ogni schermata
`{"fields": {campo: testo o None}, "abstained": [campi]}`. Usa gli stessi record,
comparatori e riepiloghi del percorso a ruoli; tratta i campi astenuti o assenti
come valori assenti; rifiuta schermate sconosciute, chiavi impreviste, campi
estranei al vocabolario dei 45, valori vuoti o non testuali e campi insieme
predetti e astenuti. Le metriche di parola sono riportate come `None`. Sulle
predizioni B0 trasformate in valori di campo dà gli stessi esiti record per record
del percorso a ruoli.

La disponibilità OCR si calcola con gli stessi esempi e allineamenti del candidato,
indipendentemente dai campi predetti. `build_dataset()` produce allineamenti e
manifest; è il percorso di valutazione a calcolare `content_availability`.
Le correzioni A5 devono dichiarare nel manifest il testo riscritto e conservarne
l'originale: i valori attuali hardcoded `scale=1x` e `words_rewritten=False` vanno
adeguati e verificati prima di generare quel pacchetto.

**CPU e tempi.** Fissare un backend per il confronto principale, inizialmente
ONNX Runtime CPU. `pc4` usa 4 thread intra-op e 1 inter-op; `vdi2` ne usa 2 e 1.
Applicare i limiti anche a PyTorch quando B0/B3 lo utilizzano. Il numero di
estrazioni concorrenti e i thread di ciascun motore devono rispettare il budget
CPU complessivo dichiarato. Verificare la condivisione dei modelli sul motore reale.

Eseguire un warm-up dedicato prima di misurare tutte le schermate della popolazione;
registrare separatamente avvio a freddo e caricamento. Per ciascuna configurazione
registrare media, mediana, p95, massimo, RAM di picco, hardware, sistema operativo,
versioni e numero di ripetizioni. Un errore non è un campione veloce da includere
nella media: resta un esito fallito, con durata e recupero riportati separatamente.
Latenza di servizio OCR+estrazione, attesa in coda e tempo acquisizione->risultato
sono misure distinte; G6 sull'applicazione include il tempo fino al risultato.
Ripetere la verifica sul PC e sulla VDI reali prima dell'adozione.

### 5.3 Verifica Obbligatoria di Resilienza e Stabilità (G7)

Prima delle prove, fissare nel manifest del candidato i tempi massimi di esecuzione,
recupero e arresto, il numero massimo di tentativi per lavoro, la capacità della coda,
la concorrenza e i limiti di conservazione dei risultati e dei log. Questi limiti devono
essere finiti e misurabili. Ogni prova verifica il rispetto dei limiti dichiarati;
il superamento di un limite è un fallimento del gate. Il timeout di guasto è distinto
dall'obiettivo di latenza ordinaria G6 e non lo sostituisce.

| Prova | Comportamento richiesto e criterio di superamento |
|---|---|
| **Errore isolato e input non supportato** | Iniettare immagini vuote, danneggiate, troppo grandi, schermate fuori dominio e geometrie non supportate. Il lavoro termina con un esito esplicito; la schermata valida successiva viene elaborata. Il parser e il controllo pixel si astengono fuori dal proprio dominio verificato, senza inventare valori o correggere cifre senza evidenza sufficiente. |
| **Timeout, blocco e crash del motore** | Iniettare eccezioni, un'inferenza che non termina e la terminazione del worker. Verificare il recupero effettivo della capacità di elaborazione entro il limite dichiarato, anche con un solo worker. Un semplice timeout dell'attesa non basta se il calcolo rimane attivo; i tentativi sono limitati e nessun lavoro blocca per sempre quelli successivi. |
| **Sovraccarico e memoria** | Alimentare l'acquisizione più velocemente dell'estrazione e riempire la coda. Verificare capacità e concorrenza limitate, politica esplicita di rifiuto o accorpamento e tracciamento di ogni lavoro accettato, inclusi quelli annullati. La deduplicazione non elimina schermate che portano nuovi dati. RAM dell'intero processo entro G6, incluse immagini in attesa e modelli residenti; conservazione di risultati e log limitata. |
| **Ordine, identità e recupero** | Alternare pratiche, frame senza NDG e completamenti fuori ordine; ripetere il caso con errore, timeout e nuovo tentativo interposti. Preservare l'ordine di acquisizione, le regole di `normalize_ndg()` e la semantica di consolidamento con `pick_best()`. Zero risultati duplicati e zero attribuzioni alla pratica sbagliata; un risultato tardivo non deve riaprire un lavoro già concluso o annullato. |
| **Avvio e funzionamento senza rete** | Eseguire il pacchetto su una macchina senza cache con la rete disabilitata. I modelli necessari sono inclusi e verificati; non sono consentiti download impliciti o ripieghi verso servizi cloud. Un modello mancante, corrotto o incompatibile produce un errore operativo chiaro prima di accettare lavoro; la disponibilità della UI non deve mascherare l'indisponibilità del motore. |
| **Arresto, riavvio ed esportazione** | Eseguire almeno 100 cicli di avvio/arresto della cattura, includendo coda piena e inferenze in corso, e chiudere/riaprire l'applicazione. Nessun worker orfano o risultato di una sessione precedente pubblicato nella nuova; ogni lavoro accettato termina o viene annullato esplicitamente. Simulare anche errori di scrittura dell'export: i dati già validi restano integri e il nuovo file non viene dichiarato salvato se incompleto. |
| **Funzionamento prolungato** | Per ciascun profilo eseguire almeno 8 ore consecutive e 1.000 frame ammessi, riproducendo sequenze congelate prima della prova e includendo cambi pratica, scroll, tooltip e guasti precedenti. Zero crash non gestiti, blocchi permanenti e violazioni d'integrità. Misurare RAM, thread, handle, coda e tempi di recupero: nessun accumulo non recuperato a parità di carico dopo lo svuotamento della coda e l'applicazione dei limiti di conservazione. |

Le prove di affidabilità riutilizzano dati di train/val e input sintetici, senza usare
il test per tarare regole, soglie o politiche di recupero. Devono esercitare il motore
locale reale e il pacchetto distribuito; i test unitari da soli non certificano G7.
L'ADR deve risolvere esplicitamente il caso di cambio pratica con NDG illeggibile:
la sola vicinanza temporale non dimostra l'identità. Ogni eventuale modifica alle
regole attuali di associazione richiede una decisione e una regressione dedicata.
La UI resta reattiva e presenta messaggi operativi in italiano; dettagli tecnici ed
esiti diagnostici rimangono nei log. Il rapporto conserva versione e impronte di
codice, modelli e configurazione, hardware, limiti dichiarati, carico, guasti iniettati
e risultati effettivi. Un criterio non misurato resta **non verificato** e impedisce
la promozione: la presenza di thread daemon non dimostra il recupero da un blocco.

---

## 6. Roadmap e Decisioni Stop/Go

### Fase 0 — Prerequisiti e Baseline Coerente

1. Recuperare gli strumenti storici necessari senza sovrascrivere le prove originali. Preparare un ambiente Python 3.12/3.13 con versioni riproducibili, dipendenze OCR/CPU, test e misurazione risorse. Congelare modelli e licenze; nessun download implicito nel runtime distribuito.
2. Riconciliare il run LiLT storico con dataset, allineamenti e impronte. Ricostruire A0 e la valutazione delle predizioni compatibili in una nuova directory; registrare le differenze nella X-ray. Non confrontare candidati con baseline composte da snapshot diversi.
3. Preparare il runner per cache complete e report separati per split, gli ingressi comuni di valutazione e i metadati delle correzioni. Scrivere prima i test comportamentali dei nuovi contratti e verificarne il fallimento atteso prima dell'implementazione.
4. Preparare il piano delle nuove pratiche di G8 e congelare soglie, popolazioni e politiche di selezione. Le API e i controlli v3.1 restano operativi per il corpus storico.

**Stop/Go:** avviare i confronti soltanto con baseline, provenienza, licenze e
contratti verificati. Questo piano non rappresenta codice già implementato.

### Fase 1 — Scelta dello Stadio A

1. Eseguire A0–A4 con cache complete delle 113 schermate nei due profili CPU. Generare dataset derivati separati e rendere disponibili alla selezione soltanto i risultati di train e validazione; il test storico resta escluso.
2. Classificare A0–A4 su G1, G3 e sul numero di letture 6→8 per pratica, calcolati su train più validazione (10 pratiche), e sul costo CPU/RAM misurato. Il train è ammesso perché nessun motore OCR è addestrato o regolato su quelle pratiche. L'ammissione vale solo per le metriche OCR, non per G4/G5 misurati con B0, che è LiLT addestrato sull'output di A0 nel train. G1 e G3 di validazione restano gate di non regressione. Confrontare poi A5 con il motore scelto secondo il protocollo di §3.1, includendo astensioni e regressioni.
3. Congelare A* soltanto se supera G1/G3 di validazione e lascia un budget realistico per Stadio B entro G6. Il tempo OCR da solo non certifica G6. Se nessuna configurazione è idonea, interrompere la promozione e documentare l'esito.

### Fase 2 — Estrattori senza Riaddestramento

1. Eseguire A*+B0 per misurare il solo effetto dell'OCR. Sviluppare B1 sul train e selezionare le sue soglie sulla validazione.
2. Confrontare B0, B1 e B3 sulla validazione con la stessa valutazione strict, riportando G4/G5, supporto e astensioni. Scegliere il candidato usando questi risultati; la decisione di passare alla Fase 3 usa soltanto train/val.
3. Un candidato con G4 target e G5 superati può passare all'integrazione sperimentale. L'adozione richiede G6 sull'intero processo, G7 e G8; non basta il benchmark offline. Se manca copertura, la sperimentazione resta limitata ai campi effettivamente verificati.

### Fase 3 — B2 o LiLT Successivo, Solo se Necessari

1. Se train/val mostrano limiti delle regole o dell'ibrido, addestrare B2 sulle feature ammesse e confrontarlo sulla validazione, senza consultare il test per scegliere feature o soglie.
2. Riaddestrare LiLT soltanto se train/val dimostrano un contributo utile ai campi variabili e un problema di distribuzione dei nuovi box. Prima di creare `ground-truth-v3.2`, aggiornare esplicitamente il builder e il contratto di `validate_reviewed_dataset()`: oggi scrivono/accettano soltanto v3.1. Preservare controlli di revisione, split, classi, impronte e rifiuto delle versioni sconosciute, con regressioni per v3.1 e v3.2. Una directory rinominata non è una nuova versione del dataset.
3. Un eventuale training Modal è un esperimento separato dall'esecuzione operativa offline, con perimetro e dati trasferiti dichiarati secondo ADR 0022. Selezionare l'epoca sulla validazione; l'automatismo di valutazione del test nel training va adeguato prima di confrontare nuovi candidati, per rispettare il congelamento previsto qui.

### Verifica Finale del Candidato Congelato

Congelare un unico candidato dopo le scelte su train/val. Calcolare G2 e i report
di regressione sul corpus storico, poi eseguire la conferma indipendente di G8
senza adattare il candidato ai risultati. Ripetere G6/G7 sul pacchetto destinato
al PC e alla VDI reali. Qualsiasi gate fallito o non misurato impedisce l'adozione;
un errore d'identità o un blocco permanente impediscono la promozione anche con
accuratezza globale elevata. L'ADR registra combinazione, limiti verificati e
ambito dei campi qualificati.

## 7. Artefatti Attesi

1. Runner riproducibile A0–A5 / B0–B3, configurazioni, manifest e impronte; risultati di ogni prova in una nuova directory della X-ray, con possibilità di riconoscere output parziali e riprendere un run senza considerarli completi.
2. Report separati per train, validazione, regressione storica e conferma indipendente: disponibilità OCR, conteggi `correct`, `correct_null`, `wrong`, `missing`, `hallucinated`, accuratezza globale e non-null, per campo, gruppo e pratica. Per ogni campo dei 45 indicare anche supporto nullo o insufficiente.
3. Report G6/G7 su entrambi i profili, dimensioni degli artefatti per PyInstaller, guasti iniettati, capacità della coda, astensioni, recuperi e limiti effettivamente verificati. Conservare risultati precedenti distinti dalle nuove esecuzioni.
4. ADR di adozione soltanto dopo il superamento dei gate applicabili, con provenienza e licenze della combinazione distribuita, qualificazione dei campi e gestione dei casi d'identità incerta. Le cronache delle esecuzioni restano nella X-ray.
