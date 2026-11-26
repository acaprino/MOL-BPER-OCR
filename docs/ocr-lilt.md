# Lettura locale delle schermate con RapidOCR, OCRia-nano e LiLT

Manteniamo due percorsi offline per estrarre i campi BPER. Il primo usa RapidOCR per trovare e leggere le righe. Il secondo usa il rilevatore di RapidOCR e il riconoscitore latino di **LlamaIndex OCRia-nano-1**, riaddestrato sulle righe BPER. Ciascun percorso alimenta un LiLT addestrato sulla propria lettura. La scelta del candidato da distribuire è ancora aperta. [Comandi di preparazione e addestramento](../src/training/README.md)

## Che cosa riconosce ogni modello

| Operazione | Ingresso → uscita | Componente |
|---|---|---|
| Riconoscere la pagina BPER | Fotogramma inquadrato → variante di pagina o nessuna corrispondenza | Router dell'edge-agent, con DINOv2 in modalità `ml`. Nella cattura corrente l'estrazione dei campi passa al VLM. |
| Trovare e leggere il testo | Immagine → righe con testo, confidenza e quattro vertici in pixel | RapidOCR A1 o A0, oppure rilevatore PP-OCRv6 small + lettore latino Nano riaddestrato. Il Nano originale completo via LiteParse è un confronto OCR separato. |
| Attribuire il testo ai campi | Parole e posizioni → ruolo per parola → valori dei 45 campi canonici | LiLT assegna i ruoli. `training.evaluation` ricostruisce i valori dalle parole osservate, anche per riga e colonna nelle tabelle. |

## Risultati sul controllo

L’obiettivo per entrambe le coppie OCR + LiLT comprende due prove sullo stesso percorso operatore. Per il **riconoscimento della vista**, registrare la vista effettiva, quella attribuita e i casi di astensione su avanzamenti, ritorni e pagine esterne. Per la **lettura**, confrontare i 45 campi con le trascrizioni della medesima pratica. Oggi i risultati delle coppie qui sotto misurano la lettura. Il router operativo riconosce le pagine separatamente. Per attribuire una capacità di riconoscimento della pagina a una coppia OCR + LiLT serve un classificatore o un criterio di pagina basato sul suo output e una valutazione dedicata. [Protocollo di prova dinamica](piano-prove-dinamiche-simulatore.md)

Al 26 novembre 2026, il confronto usa le stesse **16 schermate di due pratiche di controllo**. Le 133 schermate delle 18 pratiche di addestramento hanno alimentato i modelli. Le 13 pratiche di test restano disponibili per la prova cieca finale. [Archivio e split](../data/README.md)

| Lettura | Valori presenti nel testo OCR, su 104 | Campi interi corretti con il proprio LiLT, su 146 |
|---|---:|---:|
| RapidOCR A1, rilevatore small e lettore medium | 96 | 139 (95,2%) |
| RapidOCR A0, rilevatore small e lettore small | 96 | 136 (93,2%) |
| Rilevatore RapidOCR + lettore Nano, seme 0 | 97 | 138 (94,5%) |
| Stessa ricetta Nano, semi 1 e 2 | 92 e 94 | 129 e 137 (88,4% e 93,8%) |
| OCRia-nano-1 originale via LiteParse, fotogramma intero | 83 con VNNI, 68 senza | Non misurati |

La prima colonna cerca una sottostringa identica per ciascun valore canonico `TRASCRITTO` lungo almeno quattro caratteri, a spazi normalizzati. La seconda valuta l'intero campo, assenze comprese, con `strict-v6-table-columns`. Ogni lettura ha avuto una sola corsa LiLT con seme 7 ed epoca scelta sul controllo. Il seme 0 del riconoscitore identifica la copia di lavoro. L'intervallo dei tre semi mostra l'incertezza del confronto. [Definizione del metro OCR](adr/0036-screenvlm-rifiutato.md)

**Tempo del solo OCR.** Nello stesso pannello CPU senza VNNI, la mediana a 4 core sulle 149 schermate è 0,52 s per l'ibrido seme 0, 2,01 s per A0 e 0,53 s per Nano originale. A 2 core sulle 22 schermate campionate è rispettivamente 0,79, 3,61 e 0,66 s. Per A1 il pannello separato su 22 schermate misura 7,15 s a 4 core e 12,92 s a 2. La latenza di LiLT, cattura e consolidamento va misurata sulla macchina di destinazione.

## Modelli e provenienza

Le tre associazioni di riferimento si recuperano dal volume Modal `bper-lilt-spike`. Ogni `result.json` locale riporta `remote_model_dir` e il manifest di addestramento. `dataset_sha256` deve coincidere con `dataset_content_sha256` del dataset derivato dalla cache OCR corrispondente.

| Lettura riproducibile | Cache locale, relativa a `outputs/` | Directory LiLT sul volume |
|---|---|---|
| RapidOCR A1, prima cache 3.9.2, profilo `pc4` | `ocr-A1-archivio/cache.json` | `model_b47465bd4a400d65` |
| RapidOCR A0, versione 3.10.0 | `ocr-A0-A3-149/A0/run/cache.json` | `model_aa1d0d52a9061f9b` |
| PP-OCRv6 small + Nano `f-x1.5-s0` | `ocria-nano-bench/pair-f/cache-f-x1.5-s0.json` | `model_9042c85d680c6e41` |

Il modello originario è `llamaindex/OCRia-nano-1`, pacchetto `ocria-nano@1.0.0`, misurato con LiteParse 2.21.2. Per il derivato si è riaddestrato il solo `rec_latin.onnx`, partendo dai pesi a 7 bit, per 25 epoche. I ritagli delle righe A1 hanno margine di 2 px, grigio ad altezza 32 px e larghezza moltiplicata per 1,5. Molte etichette provengono da letture di A1, mentre le trascrizioni umane verificano solo una parte delle righe. Sul volume `ocria-nano-train` la directory è `f-x1.5-s0`. Il lettore ha SHA-256 `1891c1b890ae79e0005b91447003ed3f2dad028870d43b34c5689891009c56f2`. Il derivato conserva la licenza specifica di LlamaIndex. [Scheda e licenza dell'originale](https://huggingface.co/llamaindex/OCRia-nano-1)

Il repository conserva in `models/ocria-nano-rec/` il lettore ONNX, l'alfabeto, i metadati e la licenza. In `models/lilt/` conserva anche il LiLT abbinato al seme 0 con tokenizer, configurazione, etichette, metriche e manifest. I pesi `model.safetensors` da circa 1,1 GB sono versionati tramite Git LFS. Dopo il clone eseguire `git lfs install` e `git lfs pull`. Una copia della stessa corsa è sul volume Modal. [Inventario dei modelli e recupero dei pesi](../models/README.md)

Per i risultati dettagliati servono `outputs/ocria-nano-bench/PROVENIENZA.md`, i manifest e i report LiLT in `outputs/run-archivio-seed7/`, `outputs/ocria-nano-bench/lilt-A0/` e `outputs/ocria-nano-bench/pair-f/lilt-s{0,1,2}/`. Questi percorsi identificano i materiali locali della corsa, fuori da Git.

## Aggiornare e consegnare i due percorsi

| Cosa cambia | Lavoro sui due percorsi |
|---|---|
| Nuove pratiche revisionate o trascrizioni corrette | Aggiornare lo split per pratica. Leggere le nuove schermate con entrambi gli OCR, rigenerare gli esempi con le correzioni e riaddestrare ciascun LiLT sul proprio dataset. |
| Cambia il rilevatore, il riconoscitore di testo o il preprocessing di un percorso | Rigenerare la cache e il LiLT interessati. Se cambia un rilevatore condiviso aggiornare entrambe le coppie. Ripetere il confronto con le stesse schermate di controllo. |
| Cambiano le pagine del gestionale, il Navigatore o il contenuto di un tooltip | Rivedere catalogo e guida operativa. Nel replay misurare gli errori di pagina e le astensioni. Se cambiano anche testo o campi, aggiornare le etichette e ripetere la prova di lettura per entrambi i percorsi. |

1. **Fissare il confronto.** Usare gli stessi CSV e PNG di `data/dataset`, ruoli per pratica e versione del valutatore. Registrare commit, SHA-256 dei CSV e dei pesi, profilo CPU e istruzioni VNNI. Dichiarare prima della prova i semi e il criterio con cui si adotterà un candidato. Le schermate di test possono passare dall'OCR con `--include-test`. I valori del test servono una volta sola, a candidato congelato. [ADR 0035](adr/0035-ocr-delle-pratiche-di-test-permesso.md)
2. **Preparare una cache per lettura.** Per RapidOCR eseguire `training.ocr_runner` con A1 di riferimento e, per il confronto di latenza, A0. Il runner usa i pesi pubblicati da RapidOCR. Un aggiornamento del pacchetto, del rilevatore o del lettore richiede una nuova cache. Per l'ibrido, `scripts/pair_modal.py::caches` legge le schermate con il rilevatore small e il Nano salvato. Per riaddestrarlo, `scripts/lines_table.py` prepara i ritagli con la provenienza dell'etichetta e `scripts/rec_train_modal.py::sweep` addestra il lettore. Questi script stanno sotto `outputs/ocria-nano-bench/` e dipendono da percorsi locali e dalle chiavi della cache A1 storica. Per ripetere l'ibrido da un clone pulito occorre recuperare gli script dell'esperimento e la cache di riferimento. Un nuovo archivio richiede di aggiornare l'elenco di schermate e verificarne la copertura.
3. **Addestrare LiLT sulla rispettiva cache.** Costruire un dataset distinto con `training.dataset`, salvare `manifest.json` e `alignment_report.csv`, poi invocare `training.modal_train` per ogni dataset con le stesse impostazioni. Conservare separatamente cache, tokenizer, ordine delle classi, pesi LiLT e `download_manifest.json`. Il passaggio da un lettore all'altro con gli stessi pesi LiLT resta da verificare. [Comandi PowerShell](../src/training/README.md)
4. **Confrontare e passare la consegna.** Riportare per entrambi lettura esatta, campi strict e conteggi per gruppo, errori su identificativi, cifre e note, mediane per profilo sullo stesso host e risultati per seme. Annotare cosa cambia rispetto alla coppia precedente, indicare come recuperare i due modelli e mantenere l'identità della versione precedente. Restano da verificare la stabilità fra ulteriori semi LiLT, la resa dopo il preprocessing di cattura e il tempo end-to-end su PC/VDI. [Prove dinamiche con il simulatore](piano-prove-dinamiche-simulatore.md)
