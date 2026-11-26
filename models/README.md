# Modelli riaddestrati

Qui stanno solo i file che il progetto ha riaddestrato, nella versione corrente. A ogni nuovo candidato si
sostituiscono i file e si aggiorna questa pagina. Lo storico delle corse e tutte le misure sono in
`outputs/ocria-nano-bench/PROVENIENZA.md` (cartella non versionata) e sui volumi Modal.

## `ocria-nano-rec/` — riconoscitore di testo

| File | Cos'è |
|---|---|
| `rec_latin.onnx` | il riconoscitore latino di OCRia-nano-1 riaddestrato sulle righe delle schermate BPER |
| `rec_latin.charset.json` | l'alfabeto del modello, non modificato: l'uscita `ids` vale posizione + 1, lo 0 è il vuoto |
| `meta.json` | corsa, seme, epoche e allargamento della riga usati in addestramento |
| `LICENSE` | OCRia-nano-1 Model License, che accompagna ogni copia e ogni derivato |

- **Origine:** `llamaindex/OCRia-nano-1`, pacchetto `ocria-nano@1.0.0`, file `rec_latin.onnx`.
- **Modifiche (file cambiato rispetto all'originale):** pesi portati a 7 bit (interi dimezzati, scale
  raddoppiate) e poi riaddestrati; grafo e alfabeto invariati.
- **Corsa corrente:** `f-x1.5-s0` del volume Modal `ocria-nano-train`, 2026-11-26, SHA-256
  `1891c1b890ae79e0005b91447003ed3f2dad028870d43b34c5689891009c56f2`.
- **Come si usa:** si ritaglia ogni riquadro del rilevatore di RapidOCR con 2 px di margine, lo si porta in grigio
  ad altezza 32 px con larghezza `larghezza × 32 / altezza × 1,5`, valori `x / 127,5 − 1`, riempimento bianco fino
  a un multiplo di 128 px. Il modello restituisce un simbolo ogni 4 px: si tolgono i vuoti e le ripetizioni.
  Il codice di riferimento è in `outputs/ocria-nano-bench/scripts/pair_modal.py` (`read`).
- **Licenza:** è un derivato e resta sotto la OCRia-nano-1 Model License, con le sue soglie d'uso.

## `lilt/` — assegnazione dei campi

Il modello LiLT addestrato sulla lettura «rilevatore di RapidOCR + `ocria-nano-rec`», corsa
`model_9042c85d680c6e41` del volume Modal `bper-lilt-spike` (`training.modal_train`, seme 7).

`model.safetensors` pesa 1,1 GB: sta nella cartella ma git lo ignora (`*.safetensors` in `.gitignore`, GitHub
rifiuta i file oltre 100 MB). Per riaverlo:

```
python -m modal volume get bper-lilt-spike model_9042c85d680c6e41/model.safetensors models/lilt/model.safetensors
```

## Misure della versione corrente

Pratiche di controllo dell'archivio, 16 schermate, 146 campi; una corsa di LiLT.

| Catena | Campi giusti | Lettura di una schermata, 4 core |
|---|---|---|
| RapidOCR A1 + LiLT | 95,2% | circa 7 s |
| RapidOCR A0 + LiLT | 93,2% | 2,0 s |
| Rilevatore RapidOCR + questo riconoscitore + questo LiLT | 94,5% | 0,52 s |

Altri due semi dello stesso riconoscitore hanno dato 93,8% e 88,4%: il seme 0 è quello predefinito, non è stato
scelto per il punteggio. Le pratiche di test non sono state misurate.
