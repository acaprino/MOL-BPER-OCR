# Struttura di `data/` (Dataset pratiche, dati locali e modelli)

Tutte le sottocartelle di `data/` sono visibili nel progetto; `.gitignore` esclude soltanto i pesi binari dei modelli (`*.safetensors`, ~1,1 GB) e i ritagli temporanei di debug (`data/reference/debug_crops/`).

## Sottocartelle

- **`data/pratiche/<id_pratica>/`** — **Dataset unificato di tutte le 23 pratiche BPER (156 schermate in perimetro + 22 off-topic = 178 screenshot PNG)**, con una cartella per ciascuna pratica e nomi pagina normalizzati (`Elenco.png`, `Elenco_dx.png`, `Elenco_tooltip*.png`, `Soggetti.png`, `GestioneFidi.png`, `GestioneFidi_Tooltip*.png`, `Note.png`, `Note_chiuso.png`, `Scheda_Privati_*.png`, più `offtopic/`):
  - **12 pratiche del riscontro 2026-10-07 (con ground truth revisionato v3.1):**
    `51185037`, `51531667`, `51659595`, `52060489`, `52062600`, `52067184`, `52068422`, `52080223`, `52102599`, `52126316`, `52130861`, `52135039` (113 schermate in perimetro + 18 off-topic).
  - **10 pratiche del lotto 2026-08-21 (con/senza tooltip):**
    `51772928`, `51788077`, `51792073`, `51798191`, `51800301`, `51859514`, `51997531`, `52013664`, `52022324`, `52032077` (34 schermate in perimetro + 4 off-topic).
  - **1 pratica di riferimento iniziale (`LUNARDI_26871394`):**
    9 schermate (`Elenco.png`, `Elenco_dx.png`, `Elenco_tooltip1.png`, `Soggetti.png`, `GestioneFidi.png`, `GestioneFidi_Tooltip1..3.png`, `Note.png`).
  - `manifest.json`: indice strutturato di tutte le 23 pratiche con lotto di origine, split e elenco schermate.
- **`data/revisione/`** — Workbook di revisione del ground truth delle 12 pratiche:
  - `revisione/Revisione_ground_truth_v3_1.xlsx`: workbook autorevole con i 1.008 valori revisionati e confermati.
  - `revisione/ritagli_2026-10-16/` e `revisione/schermate_riferimento.zip`: materiali di supporto alla revisione.
  - `revisione_versioni_superate/`: versioni storiche del workbook (`v1`, `v2`, `v3`).
  - `dati.csv`: fotogramma dei valori estratti sul corpus delle 12 pratiche (formato lungo, con colonna `Nota`).
- **`data/training/`** — Dataset sigillato e modelli addestrati dal pacchetto `src/training/`:
  - `ground-truth-v3.1/`: bundle supervisionato generato da `python -m training.dataset` (`examples.json`, `roles.json`, `coverage.json`, `manifest.json`, `ground_truth.csv`, `alignment_report.csv`).
  - `ocr-cache/rapid_v6_small_1x.json`: cache OCR delle 113 schermate (RapidOCR 3.9.2, PP-OCRv6 small, scala 1x) da cui è costruito `ground-truth-v3.1/`, SHA-256 `e261c05b…` come in `manifest.json`. Il manifest conserva il percorso originale, rimosso dal riordino del repository; il file è stato ripristinato qui dalla storia git senza modifiche.
  - `runs/lilt-v3.1-20261016/`: artefatti del run GPU Modal e pesi scaricati per inferenza CPU (`cpu_model/`). Addestrato su una versione precedente del bundle, con allineamento e codice di `src/training/` anteriori.
  - `runs/lilt-v3.1-20261018-current-bundle/`: stesso protocollo, addestrato sul bundle `ground-truth-v3.1/` corrente (`dataset_content_sha256` `469c26d1…`) con la selezione dell'epoca sull'accuratezza dei campi interi in validazione. Stessa struttura del run precedente; i pesi `model.safetensors` non sono versionati.
  - `runs/lilt-v3.1-20261018-A1-ocr/` e `runs/lilt-v3.1-20261018-A2-ocr/`: stesso protocollo e stesse revisioni, ma con le parole OCR delle configurazioni A1 e A2 dello Stadio A. Il dataset di ciascuno è quello derivato in `.codebase-xray/runs/2026-10-18-phase1-modal-ocr/medium/<config>/run/dataset/`, ricostruibile con `python -m training.ocr_runner report` dalla `cache.json` versionata accanto. I run con suffisso `-seedN` ripetono A0 (bundle corrente) e A1 con un altro seed.
- **`data/reference/`** — Directory predefinita del motore VLM (`INPUT_DIR=data/reference`), con i 9 screenshot tracciati `screen 1.png` .. `screen 9.png` e il relativo `dati.csv`.
- **`data/spike-ocr/`** — Script e dati storici del primo spike esplorativo RapidOCR + LiLT (superati da `src/training/`).
