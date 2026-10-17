# Baseline 2026-09-29 - gemini-3.8-flash, thinking_level low

Seconda misura del 2026-09-29, fatta dopo il passaggio agli adapter per famiglia
([ADR 0016](../../../docs/adr/0016-adapter-per-famiglia-di-modelli.md)), che per la prima volta fa
arrivare `LLM_THINKING_LEVEL` a un modello Gemini 3. Stesse immagini, stesso ground truth e stesso
comando della [prima baseline](../2026-09-29-gemini-3.8-flash/README.md), con
`LLM_THINKING_LEVEL=low`. La prima baseline è di fatto a `high`: il livello non veniva inviato e
LangChain lascia a Gemini 3 il suo default, `high`.

## Confronto (3 run per livello, 77 campi per run)

| | high (prima baseline) | low |
|---|---|---|
| Campi corretti per run | 72, 73, 73 | 72, 73, 73 |
| Corretti su 231 valutazioni | 218 | 218 |
| NDG e denominazioni | sempre corretti | sempre corretti |
| Token di output (9 schermate) | 49.507-57.876 | 17.108-20.111 |
| Costo 9 schermate | $0,332-0,364 | $0,211-0,222 |
| Costo per schermata (media) | $0,039 | $0,024 |
| Latenza media per schermata (somma delle chiamate) | 29-38 s | 14-18 s |

I token di input non cambiano (195.445): cambia solo il ragionamento, che il listino fattura come
output.

## Dove cambiano gli errori

| Errore | high | low |
|---|---:|---:|
| `filiale_relazione` troncata a `3749` | 5 su 18 | 9 su 18 |
| `descrizione` con spazi in più (`M. CONSAP`) | 5 su 12 | 1 su 12 |
| `creazione` tagliata (`9/09/2025`) | 3 su 3 | 3 su 3 |

Il totale è identico, ma con `low` aumenta l'unico errore di contenuto (la filiale ridotta al solo
codice, sempre dal retry HEADER) e diminuisce quello di sola forma. Con 3 run per lato la
differenza sulla filiale può essere rumore: non è stata verificata con più ripetizioni.

## Lettura

`low` rispetta la soglia proposta nella prima baseline (almeno 71/77, identità al 100%, al massimo
$0,05 per schermata) con il 37% di costo in meno e la latenza dimezzata. La decisione di spedirlo
come default nel pacchetto resta aperta: il rischio da pesare è la filiale.

File: `runN.debug.csv`, `runN.outputs.json`, `runN.log` e il confronto in
[`compare_high_low.json`](compare_high_low.json).
