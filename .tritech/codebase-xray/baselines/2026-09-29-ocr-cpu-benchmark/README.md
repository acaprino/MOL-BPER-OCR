# Benchmark software: OCR ed estrazione dei campi su CPU (2026-09-29)

## Scopo

Scegliere come leggere le schermate BPER **sul PC dell'operatore**: senza GPU, spesso su desktop
virtuale (gli scatti live mostrano la finestra "Pool01-VDI"), in locale e con licenza utilizzabile
commercialmente. Il termine di confronto è la pipeline attuale su Gemini
([baseline](../2026-09-29-gemini-3.8-flash-thinking-low/README.md)).

## Come è stato misurato

- **Immagini:** i 9 screenshot di riferimento `mnt/data/screen *.png` (848x679, pratica LUNARDI),
  a scala 1x e ingranditi 2x. Per l'estrazione dei campi anche i 38 scatti live di
  `tests/fixtures/frames/{no-tooltip-rita,tooltips-rita}` (~1890 px, circa 9 pratiche).
- **Metrica OCR ("valori letti"):** un valore del ground truth conta come letto se, senza spazi e in
  minuscolo, compare nel testo OCR della sua schermata; per la nota lunga si misura la quota di
  parole (3+ caratteri) ritrovate. Il ground truth è la bozza di 77 righe del 2026-09-29, **non
  ancora verificata da una persona**. La metrica penalizza le celle su più righe (lette bene ma non
  consecutive), quindi è prudenziale per tutti i motori allo stesso modo.
- **Metrica campi:** l'`Evaluator` del progetto (`extraction/evaluation.py`), lo stesso della baseline Gemini.
- **Profili CPU su Modal**, limite rigido e thread pari ai core:
  - `pc4` = `cpu=(4, 4)`, 8 GB, come un Core i5 da ufficio;
  - `vdi2` = `cpu=(2, 2)`, 8 GB, come un desktop virtuale minimo.
  Tempi per schermata dopo un giro di riscaldamento. Il modello di CPU non è visibile nel sandbox
  Modal: i tempi assoluti su un PC desktop possono differire, il confronto fra motori regge.
- **Tetto di tempo:** 1500 s di elaborazione per motore e profilo; i VLM più lenti sono stati quindi
  valutati su meno di 9 schermate (colonna "schermate").

## Risultati OCR (lettura del testo)

Valori letti su 72 (valori brevi del ground truth); tempi in secondi per schermata.

| Motore | Tipo | Scala | Schermate | Valori letti | pc4 media / max | vdi2 media / max | Licenza |
|---|---|---|---:|---:|---|---|---|
| **RapidOCR 3.9.2, PP-OCRv6 small (ONNX)** | classico | 1x | 9 | **64/72** | **1,86 / 2,41** | **2,48 / 3,13** | Apache 2.0 |
| RapidOCR 3.9.2, PP-OCRv6 small | classico | 2x | 9 | 61/72 | 2,22 / 2,79 | 3,01 / 3,75 | Apache 2.0 |
| PaddleOCR 3.x ufficiale, `lang=it`, oneDNN spento | classico | 1x | 9 | 61/72 | 41,9 / 54,1 | 58,6 / 77,5 | Apache 2.0 |
| Tesseract 5 (`ita+eng`, `--psm 11`) | classico | 1x | 9 | 12/72 | 3,25 / 4,38 | 3,92 / 5,56 | Apache 2.0 |
| Tesseract 5 | classico | 2x | 9 | 33/72 | 4,20 / 6,22 | 4,75 / 6,77 | Apache 2.0 |
| EasyOCR (`it`, `en`) | classico | 1x | 9 | 12/72 | 9,12 / 13,2 | 13,7 / 19,1 | Apache 2.0 |
| EasyOCR | classico | 2x | 9 | 20/72 | 14,7 / 19,9 | 23,2 / 33,6 | Apache 2.0 |
| MMOCR 1.0.1 (DBNet + SAR, torch 2.0.1) | classico | 1x | 9 / 8 | 27/72 | 66,6 / 118 | 214 / 321 | Apache 2.0 |
| LightOnOCR-2-1B Q8_0 (llama.cpp, AVX2) | VLM | 1x | 8 / 6 | 64/68 | 201 / 415 | 343 / 733 | Apache 2.0 |
| LightOnOCR-2-1B Q4_K_M | VLM | 1x | 7 / 5 | 54/57 | 216 / 356 | 367 / 757 | Apache 2.0 |
| PaddleOCR-VL-1.6 GGUF ufficiale, pagina intera | VLM | 1x | 9 | 26/72 | 85 / 177 | 172 / 271 | Apache 2.0 |
| Falcon-OCR 1.5 (transformers) | VLM | - | 0 | non esegue su CPU | - | - | Apache 2.0 |

Note sui singoli motori:

- **RapidOCR** legge anche tutti e 4 i tooltip esattamente. Errori veri a 1x: "BPI Mutu**l**" in 3
  intestazioni (testo rosso piccolo) e "Cointestazione" non rilevata una volta; a 2x spariscono, ma
  alcune parole perdono lo spazio ("GARANZIAPER"). Sui 38 scatti live a ~1890 px, su questa macchina
  (22 core, 4 thread, memoria quasi esaurita da altri programmi): 5,5 s di media, massimo 10,9 s.
- **PaddleOCR ufficiale** usa gli stessi modelli di famiglia PP-OCR in versione server; con oneDNN
  attivo (default) va in errore su PaddlePaddle 3.x CPU (`ConvertPirAttribute2RuntimeAttribute not
  support`), senza oneDNN è 20-25 volte più lento di RapidOCR.
- **Tesseract ed EasyOCR** leggono male il testo piccolo delle interfacce ("MDC: 76371194" per
  "NDG: 26871394"): non è la metrica, è verificato sul testo grezzo.
- **LightOnOCR** legge benissimo ma impiega minuti a schermata su CPU.
- **PaddleOCR-VL** è progettato per regioni, non per pagine intere (lo dice anche il card della
  versione ONNX); su pagina intera perde gran parte dei valori.
- **Falcon-OCR** impone `torch.compile` con FlexAttention, non supportata su CPU
  (`return_lse is not supported yet`); senza compilazione il codice del modello rifiuta di partire.

## Risultati estrazione dei campi (dal testo ai 45 campi)

Sulle 9 schermate LUNARDI, stessa metrica della baseline.

| Approccio | Campi corretti | Tempo per schermata | Costo per schermata | Dati fuori dal PC |
|---|---|---|---|---|
| Gemini 3.8-flash, `thinking_level=low` (pipeline attuale, file calibrati) | 72-73/77 (93,5-94,8%) | 14-18 s (somma delle chiamate) | ~$0,024 | sì |
| Regole ad ancore su RapidOCR, prima versione | 49% (1x) / 71% (2x) | ~0 oltre l'OCR | $0 | no |
| **RapidOCR + LiLT addestrato, prima prova** | **61%** | +0,45 s (pc4) / +0,81 s (vdi2) | $0 | no |

**LiLT** ([`nielsr/lilt-xlm-roberta-base`](https://huggingface.co/nielsr/lilt-xlm-roberta-base),
284M parametri, MIT): classificazione di ogni parola OCR in un ruolo di campo. Addestrato su 38
scatti live (etichette di Gemini, $0,90), 40 varianti sintetiche ciascuno, 6 epoche su GPU L4 in 11
minuti; valutato sulla pratica LUNARDI, mai vista. La loss arriva a 0,0005: il modello ha
memorizzato. Alcuni ruoli compaiono pochissimo nei dati (NDG del soggetto 6 volte, tooltip delle
evidenze 3). La versione int8 dinamica non è più veloce su 4 core e cambia le predizioni, quindi si
resta in fp32. Dettagli in [`lilt_spike_metrics.json`](lilt_spike_metrics.json).

### Iterazione 2 di LiLT (stesso giorno)

- **Dati:** ai 38 scatti live si aggiungono 158 frame delle registrazioni (`tests/fixtures/frames`,
  etichette di pagina del registro), ritagliati sull'area dello schermo condiviso rilevata
  automaticamente (le registrazioni Teams hanno a destra i riquadri video dei partecipanti, che
  restano fuori; il riquadro `app_rect` del registro taglia la finestra a sinistra e non è stato
  usato), deduplicati per classe di pagina. Scartati **14 frame della pratica LUNARDI** (sessione
  `20250909-consap80`): allenarsi su di essi avrebbe invalidato il test. Etichette Gemini: $3,95.
  Parole etichettate 5083 (erano 541); NDG del soggetto 47 (erano 6).
- **Addestramento:** GPU L4, 10 varianti per schermata, pesi maggiori ai ruoli rari, varianti di
  inquadratura, arresto anticipato su una pratica di validazione (NDG 32159666, 11 frame): scelta
  l'epoca 3 (F1 parole validazione 0,934; su LUNARDI 0,765, solo osservato).
- **Ricostruzione dei campi** con quattro regole generali (valore contiguo sulla riga, confini fra
  righe dei soggetti a metà fra gli NDG, ordine per righe visive, nota come blocco). Le prime due
  verificate anche sulla pratica di validazione (concordanza con Gemini dal 73,2% all'80,5%).

| LiLT su LUNARDI (mai vista) | Ricostruzione iniziale | Ricostruzione corretta |
|---|---:|---:|
| Prima prova (38 scatti) | 61,0% | 66,2% |
| **Iterazione 2 (196 schermate)** | 68,8% | **81,8% (63/77)** |

Tempo su CPU dopo l'OCR: 0,65 s (pc4), 1,15 s (vdi2). Dei 14 errori residui, circa metà dipende
dalla lettura OCR o dalla visibilità ("BPI Mutu**l**" in 3 intestazioni, "Cointestazione" letto
male, data tagliata, descrizione coperta dal tooltip); gli altri sono del modello (pagina lista,
evidenze, un tooltip, "In Lavoraz.", la nota).

**Incidente:** durante la prova la cartella temporanea della sessione è stata svuotata da una
pulizia per memoria esaurita: persi OCR, etichette Gemini e dataset. Il modello `model_v2` era nel
volume Modal; la valutazione su LUNARDI è stata rifatta rifacendo l'OCR (deterministico, 72/73
valori allineati come prima) e riottenendo le predizioni identiche (68,83% con la ricostruzione
iniziale, come prima). La misura di validazione della quarta regola non è stata ripetuta. Il lavoro
ora risiede in `mnt/spike-ocr/` (ignorata da git); per un'iterazione 3 le etichette vanno rifatte.

## Esclusi per licenza, anche se tecnicamente validi

| Componente | Licenza | Motivo |
|---|---|---|
| Chandra OCR 2 (pesi) | OpenRAIL-M modificata | gratuita solo sotto 2 milioni di dollari di fatturato |
| LayoutLMv3, LayoutXLM | CC BY-NC-SA 4.0 | non commerciale |
| OmniParser (rilevatore) | AGPL | copyleft forte per un prodotto distribuito |

## Conclusioni

1. Sui PC degli operatori l'unica lettura praticabile è **RapidOCR PP-OCRv6 small**: 64/72 valori in
   ~2 s su 4 core, ~2,5 s su 2 core, Apache 2.0.
2. I VLM di OCR leggono bene ma su CPU richiedono da 1,5 a 12 minuti per schermata.
3. Sopra RapidOCR, **LiLT** è abbastanza veloce (<1 s) ma nella prima prova si ferma al 61%: il
   limite sono i dati di addestramento, non la tecnologia. Direzione scelta: RapidOCR così com'è,
   addestramento di LiLT con più dati (frame delle registrazioni, revisione umana delle etichette).

## Limiti di questa misura

- Una sola pratica di test e ground truth non ancora verificato a mano.
- Tempi su CPU server Modal, non su un PC d'ufficio reale.
- Le etichette di addestramento di LiLT vengono da Gemini, non da una persona.
- Le schermate di riferimento (848 px) e gli scatti live (~1890 px) hanno inquadrature diverse: per
  LiLT è anche uno spostamento di distribuzione tra addestramento e test.

## File

- [`results.json`](results.json): numeri per motore, profilo e scala (nessun testo estratto).
- [`lilt_spike_metrics.json`](lilt_spike_metrics.json): addestramento e tempi di inferenza LiLT.
- [`scripts/`](scripts/): gli script usati, così come sono stati eseguiti (prove usa e getta, con
  percorsi assoluti della macchina di sviluppo). I testi OCR e le predizioni non sono salvati qui
  perché contengono i dati della pratica.

I modelli LiLT addestrati (`model`, `model_v2`) sono nel volume Modal `bper-lilt-spike`: contengono
pesi addestrati su dati BPER e vanno cancellati a fine prova. Gli script dell'iterazione 2 sono in
`scripts/` (ricostruiti dopo l'incidente, stessa logica di quelli eseguiti).
