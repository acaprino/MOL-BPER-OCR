# Edge-Agent: consolidamento per pratica ed export Excel — Design

Date: 2026-08-17
Status: approved in chat

## Problem

L'edge-agent è il prodotto che vede l'utente finale, ma oggi espone tre superfici dati
diverse, tutte con taglio tecnico, e nessuna produce un file consegnabile.

**1. Tre export CSV, nessuno pensato per l'utente finale.**

| Sito | Contenuto |
|---|---|
| `ui/capture_tab.py:340` | `LocalExtractionClient.export_csv()` — wide tecnico |
| `ui/extraction_results_tab.py:218` | lo stesso `export_csv()` |
| `ui/data_table_tab.py:327` | CSV piatto con le label canoniche |

`export_csv()` (`local_extraction_client.py:153-185`) emette `screen_id`, `_page_type`,
`_status`, poi `<campo>_value` per tutti i campi e poi `<campo>_conf` per tutti i campi,
con le chiavi schema grezze (`professione_principale`). È un artefatto di diagnostica
esposto due volte all'utente finale come se fosse il dato.

**2. L'export Excel esistente è inutilizzabile.** `data_table_tab.py:354-400` crea un
foglio per `page_name` ma scrive **tutte** le righe in **ogni** foglio (`for result in
self._results` dentro il ciclo sulle pagine, righe 388-394): ogni foglio ripete l'intero
dataset con solo le colonne della propria pagina valorizzate. Nessuna formattazione: è
un `df.to_excel()` grezzo.

**3. Una riga per frame produce una tabella quasi vuota.** Il router riconosce 9
schermate (`assets/templates/bper/prompts.json`), ma il contratto canonico ha 4 pagine
(`PAGE_SHEET_ORDER`, `extraction/page_definitions.py:23`). Le altre 5 sono varianti
della stessa pagina (tabella scrollata, tooltip aperto) e portano 1-6 campi utili
ciascuna: "Risultato ricerca - Colonne estese" porta solo `Creazione`. Catturando una
sola pratica l'utente vede 9 righe per lo stesso soggetto, in gran parte vuote.

Corollario: `resolve_page_key()` (`page_definitions.py:36`) riconosce solo i 4 nomi
canonici esatti; le 5 varianti restituiscono `None` e finiscono nel foglio "Altro"
dell'export attuale.

**4. Manca la neutralizzazione delle formule dove serve.** `export_csv()` applica
`escape_csv_formula()` (`local_extraction_client.py:183`), ma il CSV di *Dati Estratti*
no (`data_table_tab.py:349`): un valore OCR che inizia con `=` viene valutato da Excel
(CWE-1236).

## Decision

L'edge-agent mostra **tutti e soli** i dati con taglio per l'utente finale, in una sola
vista, con un solo export. Tutto il resto va nei log.

1. **Una riga = una pratica.** I frame catturati vengono consolidati per NDG e fusi
   campo per campo. I 9 frame di una pratica diventano un record con i 45 campi
   canonici.
2. **Identità della pratica: NDG, con fallback di sessione.** L'NDG normalizzato è la
   chiave. Un frame con NDG nullish si attacca all'ultima pratica vista; se arriva
   prima di qualsiasi NDG leggibile resta in un buffer e confluisce nella prima pratica
   identificata.
3. **Fusione con `pick_best()`.** Si riusa `extraction/normalization.py:104` invece di
   scrivere una seconda semantica di merge: non-nullo batte nullo, a parità vince la
   confidenza più alta. È già la regola con cui la pipeline fonde i retry.
4. **Una sola vista dati.** Il tab "Risultati" viene rimosso. Confidenza, stato, costo,
   token, latenza e JSON grezzo finiscono in `edge-agent.log`.
5. **Un solo export, Excel formattato.** Tutti e tre i pulsanti CSV spariscono. Resta
   "Esporta Excel", raggiungibile sia da Cattura sia da Dati Estratti, con un'unica
   implementazione condivisa.
6. **Logica pura fuori dalla UI.** Consolidamento ed export vivono in due moduli senza
   Qt sotto `edge-agent/`, come `stability.py` e `page_registry.py`, e hanno i loro test.

### Perché non dentro `extraction/`

`import extraction.normalization` esegue `extraction/__init__.py`, che a riga 68 importa
`llm_factory` e quindi LangChain. È lo stesso vincolo per cui `prompt_store.py` vive
alla radice del repo e non dentro `extraction/` (CLAUDE.md, vincolo 13). Moduli nuovi
dentro `extraction/` trascinerebbero LangChain nei test dell'edge-agent.

### Perché non dentro `LocalExtractionClient` o nella tab

Nel client la logica pura si mescolerebbe a Qt e al threading, e i test diventerebbero
test di Qt. Nella tab sarebbe logica di business dentro la view, non testabile, e
l'export dovrebbe duplicare la logica di costruzione della tabella.

## Design

### 1. `edge-agent/practice_consolidation.py` (nuovo, puro)

Input: la lista di risultati che `LocalExtractionClient` già tiene per job
(`get_results(job_id)`). Output: lista ordinata di record di pratica.

```python
@dataclass(frozen=True)
class PracticeRecord:
    ndg: Optional[str]              # NDG normalizzato, None se mai rilevato
    denominazione: Optional[str]
    fields: Dict[str, Dict[str, Any]]   # schema_key -> {value, confidence, ...}
    source_pages: Tuple[str, ...]       # _page_type dei frame confluiti, in ordine
    frame_count: int

def consolidate(results: Sequence[Dict[str, Any]]) -> List[PracticeRecord]: ...
```

**Raggruppamento.** Per ogni risultato in ordine di arrivo si legge
`fields["ndg"]["value"]` e lo si normalizza con `norm_number_str()`
(`normalization.py:40`), la stessa funzione che `dataset_mismatch_guard()` usa per
confrontare gli NDG. Se non nullish (`is_nullish()`, `normalization.py:28`) è la chiave
di gruppo e diventa "ultima pratica vista". Se nullish, il frame va all'ultima pratica
vista; se non ne esiste ancora nessuna finisce in un buffer di attesa.

**Buffer iniziale.** Il buffer confluisce nella prima pratica identificata. Se la
sessione finisce senza mai un NDG leggibile, il buffer diventa un unico record con
`ndg=None`, reso in UI come "NDG non rilevato".

**Fusione.** Per ogni chiave di `FIELD_KEYS` (45), riduzione con `pick_best()` su tutti i
frame del gruppo, partendo da `safe_field()` così che un campo assente valga come nullo
con confidenza 0. `denominazione` esce dalla fusione come tutti gli altri campi.

**Ordinamento.** Pratiche per ordine di prima comparsa. Deterministico e stabile: la
riga non salta mentre l'operatore cattura.

**Nota sul limite accettato.** `pick_best` sceglie sulla confidenza dichiarata dal
modello, non sulla pagina che possiede il campo. Se un frame legge `creazione` con
confidenza alta ma sbagliata, e il frame "Colonne estese" (dove `creazione` è davvero
visibile) la legge con confidenza più bassa, vince il primo. Una regola basata sul
possesso del campo richiederebbe la lista `fields` di `prompts.json`, che usa label
libere ("NDG (riga 1)") non mappate in `FIELD_LABEL_ALIASES`: troppo fragile per
guadagnarci. Limite noto, non risolto qui.

### 2. `edge-agent/excel_export.py` (nuovo, puro)

`openpyxl` diretto, niente pandas: servono celle unite e formattazione per cella.

```python
def write_workbook(
    records: Sequence[PracticeRecord],
    columns: Sequence[ColumnSpec],   # schema_key, label, page_key, page_name
    path: str,
) -> None: ...
```

Struttura del foglio unico "Dati Estratti":

| Riga | Contenuto |
|---|---|
| 1 | nome della pagina canonica su celle unite, centrato, sfondo per pagina |
| 2 | nome del campo: label rinominata dall'utente, altrimenti `display_name` |
| 3+ | una riga per pratica |

**Ordine colonne.** `NDG` e `DENOMINAZIONE` fissate in posizione 1 e 2, poi i restanti
43 campi ordinati con la chiave di `_canonical_entry_sort_key` (`canonical_mapping.py:8`):
`PAGE_SHEET_ORDER`, poi `display_name`, poi `schema_key`.

Le due colonne vanno ancorate esplicitamente perché l'ordine canonico puro non le mette
in testa: ordina i display name per codepoint, quindi dentro `risultato_ricerca` la
sequenza è `Creazione, DENOMINAZIONE, Evidenze, Fase, Filiale relazione, NDG, Stato,
Tipo, tooltip...` — NDG cadrebbe in sesta colonna e i riquadri bloccati su `C3` non
ancorerebbero l'identità della pratica. L'ordinamento canonico resta la regola per tutto
il resto, così le colonne continuano a raggrupparsi per pagina senza buchi.

**Formattazione.**
- Intestazioni in grassetto, sfondo per pagina, testo bianco.
- Riquadri bloccati su `C3`: restano visibili le prime due colonne e le due righe di
  intestazione durante lo scorrimento.
- Autofiltro sulla riga 2, esteso all'ultima riga di dati.
- Larghezza colonna calcolata sul contenuto, con tetto (le note lunghe non devono
  produrre una colonna larga uno schermo).
- A capo automatico e allineamento in alto sulle colonne di testo lungo
  (`note_della_richiesta`, `note_scheda_privati`, i 5 `tooltip_*`).
- Bordi sottili, righe alternate.

**Valori.** Tutti scritti come testo, come deciso escludendo i tipi nativi: i valori OCR
non sono garantiti parsabili e una data mal interpretata è peggio di una data come
stringa. `escape_csv_formula()` applicato a ogni valore, colmando la lacuna di
`data_table_tab.py:349`. Un campo non rilevato lascia la cella vuota.

### 3. `ui/data_table_tab.py` (riscritto)

- Righe = `PracticeRecord`. Colonne = i 45 campi canonici nell'ordine sopra.
- Via la colonna fissa "Schermata": con una riga per pratica non ha più significato.
  `_FIXED_COLUMNS` sparisce e con essa l'aritmetica di offset (`_on_header_clicked`,
  `_on_rename_column`), che diventa un indice diretto su `_field_meta`.
- Fascia di raggruppamento per pagina resa con `QTableWidget.setSpan()` sulla riga 0:
  QTableWidget non ha intestazioni a due livelli native. Le celle della fascia non sono
  selezionabili.
- Resta la rinomina colonne, che continua a scrivere in `self._column_labels` e a
  propagarsi all'export.
- Un solo pulsante: "⬇️ Esporta Excel".

Le colonne restano i 45 campi canonici anche quando la sessione ne ha valorizzati pochi:
l'utente deve vedere *tutti* i campi previsti, non solo quelli riusciti. Le celle vuote
sono informazione.

### 4. Rimozione del tab "Risultati" e diagnostica nei log

- `ui/extraction_results_tab.py` eliminato; `ui/__init__.py:3,8` e
  `ui/main_window.py:14,62-65,74,88-89` aggiornati. Restano Cattura e Dati Estratti,
  quindi `_on_tab_changed` confronta `index == 1` per `data_tab` (oggi è 2).
- `LocalExtractionClient.export_csv()` eliminato insieme agli import `csv` e `io`; la
  docstring di classe (riga 46) perde `export_csv()` dalla superficie dichiarata.
- `ui/capture_tab.py`: `export_button` diventa "⬇️ Esporta Excel" e `_on_export_csv`
  diventa `_on_export_excel`, che chiama la stessa funzione condivisa usata da Dati
  Estratti. Il pulsante resta in Cattura perché è lì che l'operatore finisce la
  sessione: costringerlo a cambiare tab per salvare sarebbe un peggioramento.
- `LocalExtractionClient._process_frame()` scrive una riga di log per frame su stdout
  (che nel bundle windowed è `edge-agent.log`, `edge_agent.py:15-25`): schermata,
  pagina rilevata, stato, costo, token e latenza da `_meta_agg`, e per ogni campo
  valorizzato il valore, la confidenza e il pass di provenienza da `_field_sources`
  (`pipeline.py:167`). È l'unico posto dove questi dati restano leggibili dopo la
  rimozione del tab.

### 5. Test

`tests/test_practice_consolidation.py` (puro, nessuna dipendenza Qt):
- frame con lo stesso NDG confluiscono in un record
- NDG diversi producono record distinti, nell'ordine di prima comparsa
- frame con NDG nullish si attacca all'ultima pratica vista
- frame nullish prima di qualsiasi NDG confluisce nella prima pratica identificata
- sessione senza alcun NDG leggibile produce un solo record con `ndg=None`
- conflitto di valori risolto per confidenza; non-nullo batte nullo ad alta confidenza
- NDG scritti in formati diversi ("12345" e "12.345") si uniscono, coerentemente con
  `norm_number_str()`

`tests/test_excel_export.py` (rilegge il workbook con openpyxl):
- riga 1 contiene i 4 nomi di pagina su celle unite, nell'ordine `PAGE_SHEET_ORDER`
- riga 2 contiene i 45 display name; una label rinominata sostituisce il display name
- riquadri bloccati su `C3` e autofiltro presente
- un valore che inizia con `=` è scritto come testo e non come formula
- una pratica per riga a partire dalla riga 3

Verifica: `.venv/Scripts/python.exe -m pytest tests -q` (oggi 60 test verdi; il Python
di sistema non ha PyQt6 né LangChain).

## Out of scope

- `gui_app.py` e il batch CLI: `export_to_csv()` resta com'è. La richiesta riguarda
  l'edge-agent.
- Tipi di dato nativi in Excel (importi come valuta, date come data): escluso in fase di
  design.
- `_deduplicate_same_page_outputs()` in `extraction/cli.py:268-273`, ancora commentato:
  il consolidamento qui vive nell'edge-agent e non lo tocca.
- Persistenza delle pratiche tra sessioni: il consolidamento è per job, in memoria.
