# 0036 — Rifiutato ScreenVLM per leggere le schermate

- Data: 2026-11-24
- Stato: Rifiutato

## Contesto

Il 2026-11-24 si è provato ScreenVLM (`docling-project/ScreenVLM`, Apache-2.0, 316 milioni di parametri,
Idefics3 con SigLIP2 a 512 px e Granite 165M) come alternativa a RapidOCR (Stadio A di `src/training`) e,
in prospettiva, a LiLT. Legge il testo dai pixel e restituisce ScreenTag: elementi con tipo, riquadro e
testo. La domanda della prova era una sola: quanti valori della verità trascrive identici.

## Cosa si è misurato

Revisione `78df0cc8498bbea1a03eb2816056fc0a76d2f63d` (`main`, checkpoint ScreenParse v2), zero-shot, fotogramma
intero, prompt e parametri della scheda del modello (`max_tokens` 6192, decodifica greedy), su Modal con
vLLM 0.34.0. Schermate: le 149 delle 20 pratiche di addestramento e di controllo; nessuna pratica di test.
Confronto: le letture RapidOCR A1 delle stesse schermate (`outputs/ocr-A1-archivio`, RapidOCR 3.9.2).

Metro: il valore rivisto (`TRASCRITTO`, con chiave canonica, almeno 4 caratteri, spazi normalizzati) compare
identico nel testo letto dalla schermata. Non usa l'allineatore.

| Tipo di valore | RapidOCR A1 | ScreenVLM v2 |
|---|---|---|
| ID (NDG, n. fido, rapporto) | 192/210 (91,4%) | 16/210 (7,6%) |
| Importi | 64/64 (100%) | 0/64 (0%) |
| Date | 99/106 (93,4%) | 23/106 (21,7%) |
| Nomi e ruoli | 241/276 (87,3%) | 11/276 (4,0%) |
| Note e tooltip | 86/115 (74,8%) | 0/115 (0%) |
| Altri | 88/120 (73,3%) | 0/120 (0%) |
| Tutti | 770/891 (86,4%) | 50/891 (5,6%) |

- Con l'allineatore del progetto (`build_dataset`, `exact_text`) RapidOCR A1 dà 1052/1119 (94,0%). Lo stesso
  punteggio per ScreenVLM è stato interrotto prima della fine.
- 51 schermate su 149 non terminano la generazione e arrivano al limite di 6192 token.
- Il testo viene anche inventato: su `51185037/note-01` importi inesistenti ripetuti («Fase 5: 1.000€ -
  1.000€ - 1.000€») al posto della nota; su `51350695/soggetti-01` 5 elementi («Previous Next», «Lista de
  desejos: 0») contro i 103 di RapidOCR.
- Le 9 schermate da 846x677 della pratica `51350695`, dove il pannello riempie il fotogramma, danno 0/64
  contro 56/64 di RapidOCR.
- Tempi: con vLLM 50 schermate in 70-85 s su una L4; con `transformers` circa 25 s a schermata, perché
  `generation_config.json` del modello ha `use_cache: false`. L'attesa di un container GPU è stata di 11-16
  minuti a lancio.

Dal paper (arXiv 2602.14276): ScreenParse è fatto di pagine web renderizzate, le metriche sono tutte di
localizzazione (PageIoU, Recall@50, mAP@50) e la trascrizione del testo non è misurata; su ScreenSpot il
Recall@50 scende da 0,557 (web) a 0,222 (PC).

## Decisione

ScreenVLM non entra. Lo stack resta RapidOCR (Stadio A) e LiLT, per decisione del responsabile del progetto.

## Limiti della prova

- **Il controllo positivo non c'è.** Quattro pagine di ScreenParse lette con lo stesso percorso vLLM erano
  state lanciate per verificare il setup e sono state interrotte prima del risultato. Il 5,6% misura questa
  condizione (zero-shot, fotogramma intero, ricetta della scheda con vLLM 0.34.0 e `transformers` 5.24.0,
  mentre il checkpoint è stato scritto con la 4.55.2); non esclude un errore di setup e non è il tetto del
  modello.
- **Non provati:** il ritaglio sul solo pannello dell'applicazione (i ritagli sono pronti, non letti), la
  lettura a riquadri, il checkpoint `v1`, l'addestramento sulle nostre schermate.
- `transformers` e vLLM hanno dato output diversi sulla stessa schermata con decodifica greedy
  (`51185037/soggetti-01`: 843 token con fine-testo contro 6192 al limite).

## Quando riaprire

Con il controllo positivo eseguito e superato, e con la prova sul pannello ritagliato che si stacca da
zero. Ogni nuova prova sceglie sul solo addestramento e controllo (ADR 0027, ADR 0035).

## Conseguenze e verifica

Nessun comportamento cambia, quindi nessun test. Il progetto non contiene codice, pesi o dipendenze di
ScreenVLM. Output grezzi, cache convertita e i quattro script della prova sono in
`outputs/screenvlm-bench/`, fuori da git. Le schermate delle 20 pratiche sono state caricate su Modal.
