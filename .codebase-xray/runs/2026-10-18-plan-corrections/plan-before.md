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

### 1.1 Cosa dicono i numeri reali (`ground-truth-v3.1` e `lilt-v3.1-20261016`)

Dall'analisi riga per riga di `data/training/ground-truth-v3.1/alignment_report.csv` (`1.008` righe su `113` schermate di `12` pratiche revisionate in `data/revisione/revisione/Revisione_ground_truth_v3_1.xlsx`) e di `data/training/runs/lilt-v3.1-20261016/test_field_metrics.json` (`22` schermate di test, pratiche `51531667` e `52060489`, `192` valori valutati con metrica `strict-v2-punctuation-spacing`):

| Indicatore | Valore misurato | Dettaglio |
|---|---:|---|
| **Supervisione sul dataset intero (`1.008` righe)** | `863` supervisionate (`92,9%` dei non-vuoti) | `79 empty`, `31 ignored_ocr_mismatch`, `22 partial_supervision`, `13 ignored_alignment` |
| **`content_availability` OCR sul test set (`192` campi)** | **`93,23%` (`179/192`)** | Sui campi non-null: **`92,90%` (`170/183`)**, con **`13` valori `unavailable`** |
| **F1 a livello parola di `LiLT v3.1` (Validazione vs Test)** | Val: **`0,9781`** -> Test: **`0,8889`** | Precision test: `0,8308`, Recall test: `0,9557` (`6.709` parole valutate) |
| **Accuratezza strict a campo intero sul test set** | **`66,15%` (`127/192`)** | `119 correct`, `8 correct_null`, **`38 wrong`**, **`26 missing`**, `1 hallucinated` |

### 1.2 Scomposizione dei due colli di bottiglia

1. **Collo di bottiglia Stadio A (i 13 valori `unavailable` dell'OCR nel test set):**
   - **9 su 13** sono lo stesso campo `rapporto` (`034 3217 0017 05666365`) ripetuto sulle 9 schermate `GestioneFidi*` della pratica `52060489`, dove `RapidOCR PP-OCRv6 small @1x` legge un `6` come `8` (`05666385`).
   - **2 su 13** sono `ndg_1` (`36248986` -> `36248988`) e `ndg_2` (`20515962` -> `20515982`) in `52060489__Soggetti`: sempre un `6` letto come `8` nel font alto **7 pixel** delle tabelle di dettaglio.
   - **2 su 13** sono `note_della_richiesta` (`51531667__Note` e `52060489__Note`): la nota è parzialmente tagliata dallo scroll o differisce per una parola, quindi il match strict sull'intero blocco dà `0/2` anche se `LiLT` classifica le parole della nota con `F1 = 0,9988` (`tp=411, fp=0, fn=1`).
   - **Perché oggi si usa `RapidOCR small`:** negli script `data/spike-ocr/scripts/modal_ocr_bench.py`, `modal_ocr_ref.py` e `ocr_local_rapid.py`, `RapidOCR` è stato inizializzato con `OCRVersion.PPOCRV6` senza specificare `Det.model_type` / `Rec.model_type`, selezionando così il default **`ModelType.SMALL`** (~31 MB). La variante **`ModelType.MEDIUM`** (~138 MB, 34.5M parametri) era stata predisposta in `data/spike-ocr/scripts/ocr_probe_rapid.py`, ma non è mai stata eseguita sulle 113 schermate. Inoltre, per verificare il ground truth sul font da 7 pixel esiste già nella storia git (`commit fd043e8`, `.codebase-xray/baselines/2026-10-07-riscontro-12-pratiche/scripts/pixel_six_eight.py`) una regola geometrica pura sui pixel che distingue il `6` (barra orizzontale sulla 3ª riga `top+2`) dall'`8` (strozzatura sulla 4ª riga `top+3`) con **149/149 corretti (0 errori)**.

2. **Collo di bottiglia Stadio B (il calo dal `93,23%` di disponibilità OCR al `66,15%` di `LiLT v3.1`):**
   - Sui campi tabellari di `Gestione Fidi` e `Soggetti`, la `content_availability` di `RapidOCR` nel test set è del **100% (`12/12`)** per `importo_euro`, `n_fido`, `scadenza`, `tipo_op`, `descrizione`, `denominazione_1..2`, `ruolo_1..3`.
   - Eppure `LiLT v3.1` ottiene:
     - `importo_euro`: **`33,3%` (`4/12`)** (`8 wrong`)
     - `n_fido`: **`41,7%` (`5/12`)** (`7 missing`)
     - `scadenza`: **`33,3%` (`4/12`)** (`1 wrong`, `7 missing`)
     - `tipo_op`: **`33,3%` (`4/12`)** (`8 missing`)
     - `denominazione_1`, `denominazione_2`, `ruolo_1`: **`50,0%` (`1/2`)** (`ruolo_2`: `0/2`)
     - `rapporto`: **`16,7%` (`2/12`)** (con `37` falsi positivi a livello parola: precision `0,575`)
   - **Cause radice nello Stadio B:**
     - **Overfitting lessicale su 8 pratiche di train:** in `train` `scadenza` ha formato `NNN mesi`, mentre nel test (`52060489`) è una data (`15/09/2056`); in `train` `tipo_op` è `Nuova Finanza` / `Sostituzione`, mentre nel test è `In Lavoraz.`. Il backbone XLM-RoBERTa da 284M parametri memorizza i pattern lessicali delle 8 pratiche invece di affidarsi alla colonna della tabella.
     - **Assenza di vincoli strutturali di riga/tabella:** quando una schermata contiene più righe di fido (`F1`, `F2`, fidi in essere, garanzie), la token classification etichetta token sparsi su righe diverse (`37 FP` su `rapporto`, `15 FP` su `denominazione`, `13 FP` su `ndg` e `scadenza`).

---

## 2. Vincoli di Licenza e Perimetro Tecnologico

### 2.1 Componenti ammessi (Licenza Commerciale Permissiva + Esecuzione CPU)
- **`RapidOCR` (`PP-OCRv6` `tiny` / `small` / `medium`, `PP-OCRv5` `latin` / `server`)**: Apache-2.0, runtime `ONNXRuntime` / `OpenVINO` su CPU.
- **Disambiguatore geometrico pixel (`pixel_six_eight.py`)**: codice interno deterministico su `Pillow` (MIT/HPND).
- **Parser geometrico ad ancore e colonne (`anchor_rules.py` v2)**: codice interno deterministico, zero dipendenze esterne.
- **Classificatori tabellari/sequenziali su feature di layout (`LightGBM`, `scikit-learn`, `python-crfsuite`)**: MIT / BSD-3-Clause.
- **`LiLT` (`src/training/model.py`)**: codice MIT (nota: il checkpoint `nielsr/lilt-xlm-roberta-base` eredita i pesi layout da `SCUT-DLVCLab/lilt-infoxlm-base` senza file `LICENSE` esplicito nella model card; un estrattore geometrico o `LightGBM` elimina anche questa zona grigia legale).

### 2.2 Componenti esclusi dal piano
| Tecnologia | Motivo di esclusione |
|---|---|
| `LayoutLMv2`, `LayoutXLM`, `LayoutLMv3` | Licenza pesi **`CC-BY-NC-SA-4.0` / `CC-BY-NC-4.0`** (vietato uso commerciale). |
| `Surya OCR` / `Marker` / `Chandra` | Pesi sotto **`AI Pubs Open RAIL-M`** (gratuiti solo sotto soglia di fatturato/funding aziendale). |
| `EasyOCR` (detector `CRAFT`) / `Nougat` | Pesi `CRAFT` non-commercial; `Nougat` `CC-BY-NC-4.0`; inoltre `EasyOCR` legge solo `12/72` valori BPER. |
| `OmniParser` | Licenza **AGPL-3.0** (copyleft incompatibile con distribuzione `.exe` proprietaria). |
| `BROS-base` (`naver-clova-ocr/bros-base-uncased`) | Tokenizer solo inglese (`bert-base-uncased`) e stesso limite di token classification su 8 pratiche. |
| VLM locali su CPU (`LightOnOCR-2-1B`, `Florence-2`, `Pix2Struct`, `Donut`, `PaddleOCR-VL`) | Latenza su CPU incompatibile (`85–360 s` per schermata nei test Modal) o rischio di allucinazione cifre nei modelli generativi seq2seq. |
| `winocr` (Windows.Media.Ocr) come motore primario | Dipendenza dal language pack `it-IT` preinstallato sull'immagine VDI Windows Server/LTSC dell'operatore. |

---

## 3. Matrice delle Combinazioni da Testare

### 3.1 Stadio A — Configurazioni Motore OCR (6 combinazioni)

In `RapidOCR` il **Detector (`Det`)** scandisce l'intera immagine `1915×1010` (dominando il tempo CPU), mentre il **Recognizer (`Rec`)** legge solo i ritagli delle singole righe. Testiamo quindi l'accoppiamento asimmetrico `Det` × `Rec` e il controllo pixel sui numeri a 7 px:

| ID | Nome Configurazione | `Det` (Riquadri) | `Rec` (Lettura) | Post-processing Cifre 7px | Ipotesi da verificare |
|---|---|---|---|---|---|
| **A0** | **Baseline `v6_small`** | `PP-OCRv6 SMALL` | `PP-OCRv6 SMALL` | Nessuno | Riferimento attuale (`93,23%` disp. test, `7,69 s` medi su `1915×1010`). |
| **A1** | **Hybrid `det_small_rec_medium`** | `PP-OCRv6 SMALL` | **`PP-OCRv6 MEDIUM`** | Nessuno | Il recognizer `MEDIUM` (34.5M param, ~108 MB) riduce gli errori sui caratteri piccoli mantenendo quasi invariato il tempo CPU di `A0`. |
| **A2** | **Full `v6_medium`** | **`PP-OCRv6 MEDIUM`** | **`PP-OCRv6 MEDIUM`** | Nessuno | Verifica se il detector `MEDIUM` recupera anche le celle saltate da `Det SMALL` (es. 6 `scadenza` sulle 113 schermate) e misura il sovraccosto CPU. |
| **A3** | **Fast `det_tiny_rec_medium`** | **`PP-OCRv6 TINY`** | **`PP-OCRv6 MEDIUM`** | Nessuno | Verifica se `Det TINY` (~6 MB) localizza comunque tutte le celle della UI BPER dimezzando il tempo di scansione dell'immagine `1915×1010`. |
| **A4** | **Latin `det_v6_small_rec_v5_latin`** | `PP-OCRv6 SMALL` | **`PP-OCRv5 LATIN`** | Nessuno | Verifica se il recognizer con dizionario solo latino (senza CJK) migliora la lettura di testo e punteggiatura italiana. |
| **A5** | **`A*` + Pixel Guard `6/8`** | *Migliore tra A0–A3* | *Migliore tra A0–A3* | **`pixel_six_eight.py` + eventuale re-OCR 3× LANCZOS sui soli box numerici** | Azzera in modo deterministico gli errori `6↔8` sui campi identificativi e numerici (`ndg_1..4`, `rapporto`, `scadenza`) con overhead `< 20 ms`. |

---

### 3.2 Stadio B — Architetture di Estrazione dei 45 Campi (4 combinazioni sopra l'OCR vincitore `A*`)

| ID | Architettura Estrattore | Funzionamento tecnico | Licenza | Vantaggio atteso |
|---|---|---|---|---|
| **B0** | **`LiLT v3.1` esistente** (`src/training/model.py`) | Inferenza con il checkpoint `data/training/runs/lilt-v3.1-20261016/cpu_model` e `decode_fields()` (`src/training/evaluation.py`) direttamente sui box di `A*`. | MIT *(pesi SCUT)* | Misura il guadagno immediato del solo miglioramento OCR (`A*`) senza alcun ri-addestramento. |
| **B1** | **Geometric Anchor + Table Parser (`anchor_rules.py` v2)** | Estensione strutturata di `data/spike-ocr/scripts/anchor_rules.py`:<br>1. **Header & Scheda Privati:** ricerca dell'etichetta ancora (`NDG:`, `Filiale relazione`, `Professione principale`, ecc.) e lettura del box a destra/sotto entro finestra geometrica.<br>2. **Tabelle (`Elenco`, `Soggetti`, `Gestione Fidi`):** localizzazione della riga di intestazione colonne, partizione del foglio nelle fasce verticali `[x0, x1]` di ciascuna colonna, separazione tra sotto-tabelle (`Fidi proposti` vs `Fidi in essere` vs `Garanzie`) tramite le rispettive barre di titolo, e raggruppamento delle righe per coordinata `y`.<br>3. **Note e Tooltip:** estrazione del blocco multi-riga nel pannello `Note della richiesta` e dei popover `tooltip_*` ancorati alla cella sottostante. | Codice interno (Apache-2.0 / MIT) | **Invariante al contenuto testuale:** legge `15/09/2056` o `360 mesi`, `In Lavoraz.` o `Nuova Finanza` con la stessa precisione perché decide in base alla colonna `[x0, x1]` e alla riga `y`. Latenza `< 10 ms`, 0 MB di pesi neurali. |
| **B2** | **Classificatore Leggero su Feature di Layout (`LightGBM` / `CRF`)** | Classifica ogni box candidato usando un vettore di ~25 feature puramente geometriche e tipologiche: offset `(dx, dy)` normalizzato rispetto alle 10 ancore principali della pagina, appartenenza alla fascia verticale `[x0, x1]` di ciascun header di colonna, indice di riga relativo sotto l'header tabella, altezza in pixel del font, e 6 flag regex (`is_date`, `is_currency`, `is_integer_8_digits`, `is_account_rapporto`, `is_fido_code`, `is_uppercase_name`). | MIT / BSD-3 | Non può memorizzare i nomi propri o i valori delle 8 pratiche di train; si addestra su CPU in `< 10 s` e pesa `< 5 MB`. |
| **B3** | **Ibrido `Anchor Table Parser (B1) + LiLT / LightGBM`** | **Routing per gruppo di campi:**<br>- **Tabelle rigide (`Elenco`, `Soggetti` righe 1–4, `Gestione Fidi` riga 1) + `Header`:** assegnate dal parser geometrico di colonna (`B1`) quando le intestazioni di tabella sono visibili.<br>- **Campi a layout variabile (`tooltip_*`, `note_della_richiesta`, `Scheda Privati` o schermate scrollate senza intestazione):** assegnati da `LiLT` (`B0`) o `LightGBM` (`B2`). | Apache-2.0 + MIT | Unisce l'accuratezza deterministica sulle tabelle (dove `LiLT` perde 30 punti) con la capacità del modello di recuperare i campi quando la pagina è scrollata o aperta su un tooltip. |

---

## 4. Obiettivi Specifici e Gate Quantitativi di Accettazione

Tutti i test sono valutati contro il ground truth umano revisionato (`data/revisione/revisione/Revisione_ground_truth_v3_1.xlsx`, `1.008` righe su `113` schermate) con gli stessi comparatori del progetto (`src/training/dataset.py` e `src/training/evaluation.py`):

| # | Obiettivo | Metrica di verifica | Baseline Attuale (`A0 + B0`) | Baseline Cloud (`Gemini 3.8-flash low`) | Target Gate (Criterio di Successo) |
|---|---|---|---|---|---|
| **G1** | **Disponibilità del testo OCR (Stadio A)** | `content_availability` sui campi non-null del test set (`183` valori su `22` schermate) | **`92,90%`** (`170/183`, `13` persi) | N/A | **`>= 98,4%`** (`>= 180/183`; ammessi solo i 2–3 casi di testo fisicamente tagliato dallo scroll) |
| **G2** | **Allineamento sull'intero dataset (Stadio A)** | Riduzione di `ignored_ocr_mismatch` su tutte le `113` schermate (`1.008` righe) | **`31`** mismatch OCR (`863` supervisionate) | N/A | **`<= 6` mismatch OCR** (`>= 890` righe supervisionate su `929` non-vuote, **`>= 95,8%`**) |
| **G3** | **Zero errori `6↔8` sugli NDG (Stadio A)** | Match esatto cifra-per-cifra sui `21` NDG di cointestatari/garanti (`ndg_1..4`) e sui `41` `rapporto` nelle 12 pratiche | `ndg` sogg.: `17/21` (`81,0%`)<br>`rapporto`: `39/41` (`95,1%`) | `ndg` sogg.: `13/21` (`61,9%`)<br>`rapporto`: `30/41` (`73,2%`) | **`100%` (`21/21`) su `ndg_1..4`** (requisito bloccante)<br>**`>= 97,5%` (`>= 40/41`) su `rapporto`** |
| **G4** | **Accuratezza Globale Campi (Stadio B)** | `strict whole-field accuracy` (`strict-v2-punctuation-spacing`) sulle `22` schermate del test set (`192` campi) | **`66,15%`** (`127/192`) | **`93,9%`** (`92,9%` con `rapporto` esatto) | **Gate Minimo: `>= 88,0%`** (`>= 169/192`)<br>**Gate Target: `>= 92,0%`** (`>= 177/192`) |
| **G5** | **Accuratezza Tabelle Critiche (Stadio B)** | Accuratezza sul test set per `Gestione Fidi` (`n_fido`, `importo_euro`, `scadenza`, `tipo_op`, `rapporto`) e `Soggetti` (`ndg_1..4`, `denominazione_1..4`, `ruolo_1..4`) | Fidi: **`33%–42%`**<br>Soggetti: **`50%–69%`** | Fidi: **`95,2%–96,6%`**<br>Soggetti: **`95,8%`** | **Fidi: `>= 90,0%`**<br>**Soggetti: `>= 92,0%`** |
| **G6** | **Latenza e Risorse CPU** | Tempo totale (`OCR + Estrazione`) per schermata `1915×1010` su 4 thread (`pc4`) e 2 thread (`vdi2`), più RAM di picco | `7,69 s` OCR + `0,65 s` LiLT = **`8,34 s`** (`pc4`) | `28,8 s` (somma chiamate API) | **Media `<= 6,0 s`, Max `<= 10,0 s`** su 4 thread<br>**RAM di picco `<= 1,5 GB`** |
| **G7** | **Resilienza, stabilità e integrità del processo** | Prove di guasto e durata della sezione 5.3 sull'intera combinazione candidata integrata nell'edge-agent, nei profili `pc4` e `vdi2` | Da verificare sul candidato integrato | N/A | **Zero crash non gestiti, blocchi permanenti, duplicazioni di risultati e contaminazioni tra pratiche**; ogni lavoro accettato ha un esito tracciabile; recupero entro i limiti dichiarati; superamento di tutte le prove della sezione 5.3. **Gate bloccante**. |

---

## 5. Modalità di Benchmarking e Protocollo Sperimentale

### 5.1 Prevenzione del Data Leakage (Isolamento Rigoroso degli Split)
Tutte le prove rispettano la partizione per pratica definita in `data/training/ground-truth-v3.1/manifest.json` (nessuna pratica né alcun NDG di soggetto è condiviso tra split):
- **`train` (8 pratiche, 75 schermate, 650 righe):** `51185037`, `52062600`, `52067184`, `52068422`, `52080223`, `52102599`, `52130861`, `52135039`.
  - *Consentito:* taratura delle finestre geometriche e delle etichette in `B1` (`anchor_rules.py` v2), fitting di `B2` (`LightGBM`/`CRF`), eventuale training di `LiLT`.
- **`val` (2 pratiche, 16 schermate, 166 righe):** `51659595`, `52126316`.
  - *Consentito:* selezione tra le varianti `A0..A5` e `B0..B3`, tuning delle soglie di confidenza e verifica delle regole di disambiguazione.
- **`test` (2 pratiche, 22 schermate, 192 righe):** `51531667`, `52060489`.
  - *Consentito:* **esclusivamente il calcolo finale delle metriche** tramite `evaluate_predictions()`. È vietato inserire eccezioni, coordinate o stringhe derivate dall'ispezione di `51531667` o `52060489`.

### 5.2 Standardizzazione delle Misure Tecniche
1. **Formato dell'output OCR (Stadio A):**
   - Ogni run `A0..A5` salva un file JSON compatibile con `src/training/dataset.py`:
     ```json
     {
       "52060489__GestioneFidi": {
         "seconds": 4.12,
         "items": [
           ["Testo letto", 0.994, [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]]
         ]
       }
     }
     ```
2. **Misura dei tempi CPU e della RAM:**
   - La **prima schermata** di ogni run viene sempre esclusa dalle medie (`warm-up` di inizializzazione sessione ONNX / PyTorch).
   - I test vengono eseguiti fissando esplicitamente `intra_op_num_threads=4, inter_op_num_threads=1` (profilo `pc4`) e `intra_op_num_threads=2, inter_op_num_threads=1` (profilo `vdi2`).
   - Per ogni configurazione si registrano: `sec_mean`, `sec_median`, `sec_p95`, `sec_max` e `rss_peak_mb`.
3. **Valutazione Automatica e Riproducibile:**
   - **Stadio A:** invocazione di `build_dataset()` (`src/training/dataset.py`) con il JSON OCR in esame e `data/revisione/revisione/Revisione_ground_truth_v3_1.xlsx`, producendo `alignment_report.csv` e `manifest.json` per il confronto diretto dei conteggi `supervised` / `ignored_ocr_mismatch` e `content_availability`.
   - **Stadio B:** invocazione di `evaluate_predictions(examples, predictions)` (`src/training/evaluation.py`), producendo il JSON completo con `accuracy`, `status_counts` (`correct`, `correct_null`, `wrong`, `missing`, `hallucinated`) e `per_field` identico a `test_field_metrics.json`.

---

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

## 6. Roadmap di Esecuzione in 3 Fasi (con Gate Stop/Go)

### Fase 1 — Benchmark Stadio A (`A0..A5`: Taglie `RapidOCR` + `pixel_six_eight`)
1. **Step 1.1 (Sottoinsieme veloce `val + test`, 38 schermate):**
   - Eseguire `A0`, `A1`, `A2`, `A3`, `A4` sulle 38 schermate di `val` (16) e `test` (22) da `data/pratiche/`.
   - Applicare il post-processing `pixel_six_eight.py` (`A5`) sui box numerici (`ndg_1..4`, `rapporto`, `scadenza`) del miglior motore.
2. **Step 1.2 (Misura e selezione):**
   - Calcolare `content_availability`, errori `6↔8` e tempi CPU (`pc4` / `vdi2`).
3. **Gate Stop/Go Fase 1:**
   - Promuovere la configurazione `A*` che raggiunge **G1 (`>= 98,4%` availability)**, **G3 (`100%` NDG soggetti)** e **G6 (`<= 6 s` medi)**, ed estendere l'estrazione OCR anche alle **75 schermate di `train`** (totale 113 schermate).

### Fase 2 — Benchmark Stadio B Zero-Training (`B0` LiLT attuale, `B1` Ancore v2, `B3` Ibrido)
1. **Step 2.1 (`A* + B0`):**
   - Eseguire `LiLT v3.1` esistente sui nuovi box `A*` per quantificare il miglioramento ottenuto dal solo OCR corretto (senza ri-addestrare).
2. **Step 2.2 (`A* + B1` — Sviluppo `anchor_rules.py` v2 su `train` + `val`):**
   - Completare il parser geometrico su tutte le tipologie di pagina (`Elenco`, `Soggetti`, `Gestione Fidi`, `Note`, `Scheda Privati` e `Tooltip`), verificando i risultati su `train` (75 screen) e `val` (16 screen).
   - Eseguire la valutazione cieca sul `test` set (22 screen) con `src/training/evaluation.py`.
3. **Step 2.3 (`A* + B3` — Combinazione Ibrida `B1 + B0`):**
   - Combinare l'output tabellare/header di `B1` con l'output di `LiLT v3.1` per i campi testuali/tooltip o per le pagine scrollate prive di ancore, e valutare su `val` e `test`.
4. **Gate Stop/Go Fase 2:**
   - Se `A* + B1` o `A* + B3` raggiunge **G4 (`>= 92,0%` sul test set)** e **G5 (`>= 90%` su Fidi e `>= 92%` su Soggetti)**, il candidato può passare all'integrazione sperimentale in `LocalExtractionClient` senza necessità di ri-addestramento neurale. La promozione per l'uso operativo richiede anche **G6 sull'intero processo integrato** e **G7 su entrambi i profili CPU**: il solo benchmark offline non è sufficiente. Lo stesso vincolo si applica agli eventuali candidati della Fase 3.

### Fase 3 — Classificatore Leggero (`B2` LightGBM/CRF) o Ri-addestramento `LiLT v3.2` (Condizionale)
1. **Step 3.1 (`A* + B2`):**
   - Se nella Fase 2 emergono casi di layout parzialmente visibile (scroll intermedio) in cui le regole pure (`B1`) sono troppo rigide e `LiLT` (`B0`) è troppo lento o impreciso, addestrare il classificatore `LightGBM` sulle feature geometriche relative alle ancore delle 75 schermate di `train` e valutarlo su `val` e `test`.
2. **Step 3.2 (Ri-addestramento `LiLT v3.2` su Modal):**
   - Solo se l'ibrido `B3` mostra che `LiLT` resta indispensabile sui blocchi testuali ma soffre il cambio di distribuzione dei box tra `A0` e `A*`, generare il pacchetto sigillato `data/training/ground-truth-v3.2/` con i box di `A*` e lanciare un singolo training `modal_train.py`.

---

## 7. Artefatti Attesi al Termine del Benchmark

1. **Script di benchmark riproducibile** per le configurazioni OCR `A0..A5` e gli estrattori `B0..B3`.
2. **Tabella comparativa completa** (`val` e `test`) con:
   - `content_availability` e dettaglio degli eventuali valori non letti;
   - accuratezza per ciascuno dei 45 campi (`correct`, `wrong`, `missing`, `hallucinated`, `correct_null`);
   - accuratezza separata sui campi bloccanti di identità (`ndg`, `denominazione`, `ndg_1..4`, `denominazione_1..4`);
   - latenza media/p95/max (`pc4` e `vdi2`) e occupazione RAM/disco per il packaging PyInstaller (`build_exe.bat`).
3. **Decisione architetturale documentata (ADR)** con la scelta definitiva della combinazione `Stadio A + Stadio B` da integrare nell'edge-agent.
4. **Rapporto di resilienza e stabilità G7** conservato nella X-ray, con esito di ogni prova della sezione 5.3, misure sull'intero processo e limiti operativi verificati. L'ADR di adozione riporta tali limiti; un candidato con prove fallite o non eseguite non è approvato per l'uso operativo.
