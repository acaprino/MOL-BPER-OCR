# Baseline 2026-09-29 - gemini-3.8-flash

Prima baseline di accuratezza e costo con un provider reale. Serve a fissare il punto di partenza
della beta e a riconoscere una regressione, non a dimostrare l'accuratezza sul traffico reale: copre
**una sola pratica** in 9 schermate.

## Come è stata prodotta

- **Codice:** commit `4b5cac6` (`develop`) più le modifiche non committate del 2026-09-29
  ([aggiornamento incrementale](../../09-incremental-2026-09-29.md)); la pipeline non è cambiata.
- **Comando:** `python main.py` dalla radice, `LLM_PROVIDER=gemini`,
  `LLM_MODEL=LLM_MODEL_ANCHOR=gemini-3.8-flash`, `MAX_CALLS_PER_SCREEN=5`, `PARALLEL_WORKERS=4`,
  prompt da `prompts/`. Tre esecuzioni identiche per misurare la variabilità del modello.
- **Livello di ragionamento: `high` di fatto.** Il `.env` locale conteneva `LLM_THINKING_LEVEL=low`,
  ma il codice di allora lo inviava solo ai modelli con `thinking` nel nome: a `gemini-3.8-flash`
  non arrivava nulla e vale il default del modello, `high`. Il confronto con `low`, misurato dopo
  l'[ADR 0016](../../../docs/adr/0016-adapter-per-famiglia-di-modelli.md), è in
  [2026-09-29-gemini-3.8-flash-thinking-low](../2026-09-29-gemini-3.8-flash-thinking-low/README.md).
- **Immagini:** i 9 screenshot tracciati in `mnt/data/screen *.png` (848x679, "Nuova PEF 3.0",
  pratica NDG 26871394).
- **Ground truth:** [`dati.csv`](dati.csv), copia di `mnt/data/dati.csv`. 77 righe trascritte a vista
  il 2026-09-29, **non ancora verificate da una persona**. Il `dati.csv` nella storia git
  (`e8c677c`) descrive altri screenshot e non è stato usato.

### Scelte del ground truth da confermare

| Schermata | Campo | Scelta | Perché conta |
|---|---|---|---|
| 1 | Tipo | vuoto | La colonna è fuori vista: un valore del modello conta come invenzione. |
| 2 | Creazione | `09/09/2025` | La cella è tagliata a sinistra (`…/09/2025`); il modello legge `9/09/2025` in 3 run su 3. |
| 4 | NDG/Denominazione/Ruolo 4 | vuoti | La tabella soggetti ha 3 righe. |
| 5-8 | Rapporto, Descrizione | righe unite da uno spazio | A schermo vanno a capo; sotto i 20 caratteri il confronto è esatto. |
| 4-9 | NDG, Denominazione, Tipo, Filiale relazione | ripetuti su ogni schermata di dettaglio | Visibili in ogni intestazione: pesano 24 righe su 77. |

Nessuna delle 9 schermate è una scheda privati: i 13 campi di quella pagina non sono misurati.

## Risultati

| Run | Campi corretti | Accuratezza | Token prompt / completion | Costo | Costo per schermata |
|---|---:|---:|---:|---:|---:|
| 1 | 72/77 | 93,5% | 195.445 / 51.689 | $0,340 | $0,038 |
| 2 | 73/77 | 94,8% | 195.445 / 57.876 | $0,364 | $0,040 |
| 3 | 73/77 | 94,8% | 195.445 / 49.507 | $0,332 | $0,037 |

RAW e FILTERED coincidono (nessuna schermata esclusa dalla guardia NDG). 45 chiamate per run, 5 per
schermata: il budget di retry è sempre consumato per intero. Costi al listino introduttivo
($0,75 / $3,75 per 1M token fino al 2026-12-31); dal 2027-01-01 il listino raddoppia, circa
$0,08 per schermata. La schermata 3 chiude sempre in `ANCHOR_UNCERTAIN`: NDG e denominazione
non sono visibili, è atteso.

**Sempre corretti in 3 run su 3:** NDG e denominazione di testata, i 3 soggetti con ruoli (e i null
del quarto), stato, fase, evidenze, tipo, i 4 tooltip, i campi della tabella fidi tranne la
descrizione, la nota della richiesta.

**Errori (13 su 231 valutazioni):**

| Campo | Frequenza | Valore letto | Natura |
|---|---|---|---|
| `filiale_relazione` | schermata 8 in 3/3 run, schermate 5 e 6 in 1/3 | `3749` invece di `3749 - GRUGLIASCO` | Errore vero. Il valore finale viene dal retry HEADER; `_attempts` non conserva i valori per passaggio, quindi non si vede se il passaggio principale avesse letto giusto. |
| `descrizione` | schermata 5 in 3/3, schermata 6 in 2/3 | `M. CONSAP >=80%` / `M. CONSAP >= 80%` | Spazi in più: il contenuto è giusto, il confronto esatto lo boccia. |
| `creazione` | schermata 2 in 3/3 | `9/09/2025` | Cella tagliata: dipende dalla convenzione del ground truth. |

Dati completi per run in `runN.debug.csv`, `runN.outputs.json` e `runN.log`; aggregati in
[`summary.json`](summary.json).

## Soglia di accettazione proposta

Da confermare. Vale su questo ground truth e questi 9 screenshot; va rifissata quando il ground
truth cambia.

1. **Identità al 100%, bloccante:** NDG e denominazione (testata e soggetti) sempre corretti. Un NDG
   sbagliato fonde o spezza le pratiche nel consolidamento dell'edge-agent.
2. **Accuratezza complessiva almeno 71/77 (92%)** su ciascun run. Il migliore osservato è 73/77:
   la soglia tollera la variabilità vista (un campo) più un campo di margine.
3. **Run completo:** 77 campi valutati e nessuna schermata in `ERROR`. Oggi un run in cui falliscono
   tutte le chiamate stampa `0/0` ed esce con codice 0 (XQ-R12): va controllato a mano.
4. **Costo al massimo $0,05 per schermata** al listino attuale ($0,10 dal 2027).
