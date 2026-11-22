# 0033 — Correzioni dell'operatore e tema proprio

- Data: 2026-11-22
- Stato: Accettato

## Contesto

L'UI dell'edge-agent sembrava un prototipo: tema Material generico sempre scuro (il ternario di
`edge_agent.py` aveva lo stesso valore nei due rami), emoji al posto delle icone, quattro pulsanti
dello stesso peso, un log grezzo che occupava la tab e una tabella in sola lettura. Deve essere
usata da utenti di banca e data entry, in sessioni lunghe, e gli operatori devono anche correggere i
valori estratti.

Correggere nella tabella non basta, per due motivi che stanno nel codice:

- la tabella si ricostruisce da zero a ogni frame (`consolidate()` sui risultati grezzi): una
  modifica sparirebbe al frame successivo;
- l'export rilegge i risultati grezzi, non la tabella: la modifica non arriverebbe nell'Excel.

## Decisione

- **Le correzioni sono un livello di precedenza applicato dopo il merge dei frame.**
  `consolidate(results, corrections)` accetta `{NDG normalizzato: {campo: valore}}`; l'operatore
  vince, anche su un frame arrivato dopo, e il valore estratto resta in `original_value` per il
  tooltip. Non è una seconda semantica di merge dei frame: `pick_best()` resta l'unica.
- **Lo stato sta in `LocalExtractionClient`**: correzioni, etichette di colonna rinominate e, per
  sessione, l'impronta del contenuto all'ultimo export. `export_workbook()` è l'unico percorso di
  export, usato da entrambe le tab. Le formule restano neutralizzate (`data_type = "s"`); il testo
  digitato è ripulito dai caratteri che Excel rifiuta e limitato a 32767 caratteri.
- **NDG e righe senza NDG non sono correggibili.** L'NDG è l'identità della pratica; un record
  senza NDG viene assorbito nella prima pratica identificata, e una correzione fatta prima
  resterebbe orfana.
- **Solo in memoria, nessun salvataggio su disco**: sarebbero dati personali di clienti della banca.
  Alla chiusura con sessioni non esportate (impronta diversa da quella dell'ultimo export) un
  dialogo avvisa, prima di fermare la cattura, e avvisa anche se ci sono frame ancora in
  elaborazione (`frames_in_progress()`, che include quelli già presi da un worker: `shutdown()` li
  scarta); non esporta da solo, perché ogni Avvia crea una sessione e un export ne scrive una sola.
- **Tema proprio** in `src/edge-agent/theme.py`: token di colore, stylesheet, chiaro di default che
  segue Windows, scuro disponibile. Sostituisce `qt-material`. Il modulo è top-level e non importa
  `extraction`, perché si applica prima del preflight e `ui/__init__.py` importa `main_window`
  (vincolo d'ordine degli import, Costante 3 di CLAUDE.md). Il contrasto WCAG delle due palette è un
  test.
- **Niente `pywinstyles`, niente acrylic.** Libreria ferma a luglio 2024, bug aperti proprio
  sull'acrylic, esempi PyQt5. L'acrylic sfoca ciò che sta dietro la finestra e l'agent cattura
  l'intero monitor: potrebbe sporcare i frame. Un eventuale Mica sulla finestra principale è un
  extra opzionale e separato, non parte di questa decisione.

## Alternative scartate

- Riscrittura in QML/Qt Quick: massima resa grafica, ma si rifà tutta la UI e il ponte dei segnali.
- Libreria Fluent (`qfluentwidgets`): look generico, licenza da verificare, dipendenza in più da
  impacchettare.
- Salvataggio automatico della sessione su disco: protegge dalla chiusura accidentale ma scrive dati
  di clienti fuori dal controllo dell'operatore.

## Conseguenze e verifica

- Una correzione sopravvive ai frame successivi, compare in entrambi gli export, si ripristina; un
  risultato che arriva mentre un editor è aperto aspetta la chiusura dell'editor.
- Un errore in uno slot Qt non chiude l'app: `error_report.install_excepthook()` lo registra in
  `edge-agent.log` e lo mostra (PyQt6 altrimenti termina il processo, e le sessioni, solo in
  memoria, andrebbero perse). Test: `test_error_report.py`.
- Nessuna evidenza visiva delle celle incerte (lo vieta il vincolo "l'edge-agent mostra solo dati di
  business") e nessuna validazione di date e importi: restano fuori.
- Test che tengono vera la decisione: `test_practice_consolidation.py` (precedenza, NDG scritto in
  modo diverso, NDG non correggibile), `test_local_extraction_client.py` (testo ripulito, formule
  inerti, export con etichette, sessioni non esportate), `test_data_table_tab.py` (modifica,
  ripristino, editor aperto, colonne fisse), `test_main_window.py` (avviso alla chiusura) e
  `test_theme.py` (contrasto).
