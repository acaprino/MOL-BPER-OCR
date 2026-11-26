# Modelli riaddestrati

Qui stanno solo i file che il progetto ha riaddestrato, nella versione corrente. A ogni nuovo candidato si
sostituiscono i file e si aggiorna questa pagina. Lo storico delle corse e tutte le misure sono in
`outputs/ocria-nano-bench/PROVENIENZA.md` (cartella non versionata) e sui volumi Modal.

## `ocria-nano-rec/` — riconoscitore di testo

| File | Cos'è |
|---|---|
| `rec_latin.onnx` | il riconoscitore latino di OCRia-nano-1 riaddestrato sulle righe delle schermate BPER |
| `rec_latin.charset.json` | l'alfabeto del modello, non modificato: l'uscita `ids` vale posizione + 1, lo 0 è il vuoto |
| `meta.json` | corsa, seme, epoche, allargamento della riga e dati usati in addestramento |
| `LICENSE` | OCRia-nano-1 Model License, che accompagna ogni copia e ogni derivato |

- **Origine:** `llamaindex/OCRia-nano-1`, pacchetto `ocria-nano@1.0.0`, file `rec_latin.onnx`.
- **Modifiche (file cambiato rispetto all'originale):** pesi portati a 7 bit (interi dimezzati, scale
  raddoppiate) e poi riaddestrati; grafo e alfabeto invariati. A 7 bit il file legge uguale su ogni CPU, con o
  senza istruzioni VNNI.
- **Corsa corrente:** `g-x1.5-w1-s0` del volume Modal `ocria-nano-train`, 2026-11-26, SHA-256
  `c3ca3e7cc306e7667aef6c0261cfd711b42a01646e980402eb1547c65cc88096`. Addestrata su 2.857 ritagli delle
  pratiche di addestramento più 10.403 righe dell'emulatore BPER (pratiche sintetiche), 25 epoche.
- **Come si usa:** si ritaglia ogni riquadro del rilevatore di RapidOCR con 2 px di margine, lo si porta in grigio
  ad altezza 32 px con larghezza `larghezza × 32 / altezza × 1,5`, valori `x / 127,5 − 1`, riempimento bianco fino
  a un multiplo di 128 px. Il modello restituisce un simbolo ogni 4 px: si tolgono i vuoti e le ripetizioni.
  Il codice di riferimento è in `outputs/ocria-nano-bench/scripts/pair_modal.py` (`read`).
- **Licenza:** è un derivato e resta sotto la OCRia-nano-1 Model License, con le sue soglie d'uso.

## `lilt/` — assegnazione dei campi

Il modello LiLT addestrato sulla lettura «rilevatore di RapidOCR + `ocria-nano-rec`», corsa
`model_5094c21c60b5febe` del volume Modal `bper-lilt-spike` (`training.modal_train`, seme 7).

`model.safetensors` pesa 1,1 GB ed è versionato con Git LFS (`.gitattributes`: `models/**/*.safetensors`): dopo
un clone serve `git lfs install` una volta, poi `git lfs pull`. Ogni versione nuova occupa altri 1,1 GB della quota
LFS del repository remoto. La copia originale resta sul volume Modal:

```
python -m modal volume get bper-lilt-spike model_5094c21c60b5febe/model.safetensors models/lilt/model.safetensors
```

## Misure della versione corrente

Pratiche di controllo dell'archivio, 16 schermate, 146 campi; una corsa di LiLT per lettura.

| Catena | Campi giusti | Campi di credito | Lettura di una schermata, 4 core |
|---|---|---|---|
| RapidOCR A1 + LiLT | 95,2% | 90,0% | circa 7 s |
| RapidOCR A0 + LiLT | 93,2% | 86,7% | 2,0 s |
| Rilevatore RapidOCR + questo riconoscitore + questo LiLT | 93,8% | 100% | 0,52 s |

Il seme 0 entra qui per regola fissata prima delle misure, non per il punteggio. Gli altri due semi dello stesso
addestramento danno 96,6% e 93,2% (media dei tre 94,5%); la versione precedente (senza righe dell'emulatore) dava
94,5%, 93,8% e 88,4% (media 92,2%). Prima di LiLT la lettura contiene 138, 140 e 140 dei 146 valori rivisti
(RapidOCR A1 139, A0 137). Le pratiche di test non sono state misurate.
