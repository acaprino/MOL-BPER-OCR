# 0020 - Separare la pagina sorgente dal gruppo di esportazione

- **Stato:** Accettato
- **Data:** 2026-10-16
- **Interessa:** `extraction/field_definitions.py`, `extraction/page_definitions.py`, `extraction/canonical_mapping.py`, `edge-agent/excel_export.py`
- **Test:** `tests/test_page_metadata.py`, `tests/test_excel_export.py`
- **Correlati:** [0004](0004-budget-retry-derivato-dalle-aree.md)

## Contesto

I tredici campi della Scheda Privati erano associati a `note_da_richiesta`, pur
appartenendo a una schermata diversa. Lo stesso `page_key` guidava sia il
metadato canonico sia il gruppo delle colonne Excel e della tabella live.
Correggerlo senza distinguere i due significati avrebbe cambiato il layout
esistente a quattro gruppi.

## Decisione

`CANONICAL_FIELD_DEFINITIONS.page_key` indica la pagina sorgente. I tredici campi
privati usano `scheda_privati`, con nome e alias in `page_definitions.py`.
Le voci canoniche emettono quindi `page_key="scheda_privati"` e
`page_name="Scheda Privati"` senza aggiungere nuove chiavi al payload.

Per quei campi `export_group_key="note_da_richiesta"` conserva il gruppo
precedente. `resolve_field_export_group_key()` è l'unico risolutore del gruppo,
con fallback al `page_key` per le altre definizioni. Excel e ordinamento canonico
lo usano per mantenere l'ordine esistente. `ColumnSpec.page_key` e `page_name`
restano i nomi del gruppo visualizzato, non la pagina sorgente del campo.

`CANONICAL_PAGE_NAMES` descrive cinque pagine sorgenti; `PAGE_SHEET_ORDER` resta
l'ordine dei quattro gruppi di export. Le 45 colonne, le bande unite e i campi
NDG/denominazione iniziali restano quelli precedenti. Questa modifica non
aggiunge template o pagine al catalogo del router e non filtra i retry per pagina.

## Alternative valutate

- **Aggiungere un quinto gruppo Excel.** Correggerebbe anche l'etichetta visiva,
  ma cambierebbe un contratto esistente senza necessità per correggere i metadati.
- **Conservare `page_key` errato e aggiungere un secondo metadato sorgente.**
  Lascerebbe ambigua la funzione già usata per risolvere la pagina di un campo.
- **Duplicare la corrispondenza nell'export.** Creerebbe un elenco parallelo dei
  tredici campi, con possibilità di divergenza dalle definizioni canoniche.

## Conseguenze e verifica

I consumatori dei metadati canonici ricevono ora la pagina corretta per quei
tredici campi. Chi dipendeva dall'etichetta errata deve usare il risolutore del
gruppo per ricostruire il layout precedente. L'ordine delle voci resta compatibile
con tale layout, quindi non è un raggruppamento ordinato per pagina sorgente.

I test verificano ciascun campo privati e gli alias della pagina. L'export è
protetto da aspettative esplicite per tutte le 45 posizioni delle colonne e per
nomi e intervalli delle quattro bande Excel, senza derivare l'atteso dai mapping
modificati. La pagina delle note conserva la propria identità.
