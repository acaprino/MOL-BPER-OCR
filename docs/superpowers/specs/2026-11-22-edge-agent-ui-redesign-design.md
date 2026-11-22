# Edge-agent: UI professionale e correzione dei valori (design)

Stato: bozza in attesa di approvazione. Data: 2026-11-22.
Cosa è detto dall'utente e cosa è una scelta mia è marcato: **[utente]** / **[mia scelta]**.

## Intento e perché

- **[utente]** L'UI PyQt6 dell'edge-agent oggi "sembra un PoC", è "grezza, brutta". Il team vuole un
  prodotto "professionale ed elegante", con una UX migliore, che possano usare **utenti di banca e
  data entry**, in sessioni lunghe.
- **[utente]** Gli operatori devono poter **correggere i valori** nella tabella, oltre ad avviare la
  cattura ed esportare l'Excel.
- **[utente]** L'idea di partenza era un effetto acrylic con `py-window-styles` (`pywinstyles`).
  Vedi "Approcci": è ridimensionata a un extra opzionale, senza quella libreria.

## Stato attuale (letto nel codice)

- `edge_agent.py` applica `qt-material` `dark_cyan` sempre: il ternario alla riga 56 ha lo stesso
  valore nei due rami. Il tema è applicato prima di `bootstrap.run_preflight()`, quindi stila anche
  il dialogo del primo avvio.
- `ui/main_window.py`: `QTabWidget` con "Cattura", "Dati Estratti", "Debug LLM" (solo `--debug`).
- `ui/capture_tab.py`: `QGroupBox` impostazioni, quattro pulsanti con emoji come icone
  (`▶ ■ ⬇️ 📷`) tutti dello stesso peso, un `QTextEdit` di log che occupa la tab, etichetta
  "Sessione: –" con l'ID grezzo. Conta già `_n_results` e `_n_queued`.
- `ui/data_table_tab.py`: toolbar con emoji, `QTableWidget` in sola lettura (`NoEditTriggers`),
  45 colonne, riga 0 come fascia di pagina con `setSpan()`. Rinominare una colonna richiede click
  sull'intestazione e poi un pulsante. Ogni risultato nuovo richiama `_load_table()`, che rifà
  `consolidate(client.get_results(job_id))` da zero.
- `excel_export.export_results(results, path, labels)` è **l'unico punto di export**, condiviso dalle
  due tab; riconsolida i risultati grezzi, non legge la tabella. `_set_text()` neutralizza le
  formule con `cell.data_type = "s"`.
- `LocalExtractionClient._results` tiene i risultati **solo in memoria**. `MainWindow.closeEvent`
  non avvisa se ci sono dati non esportati.

## Obiettivi

1. Un aspetto sobrio e coerente: tema proprio al posto di `qt-material`, icone SVG di un solo stile,
   nessuna emoji come icona, spaziature e gerarchia tipografica uniformi.
2. Tema **chiaro di default**, che segue il tema di Windows (`QStyleHints.colorScheme()`), con
   variante scura. **[mia scelta]** Motivo: uffici e sessioni lunghe; il chiaro è più sicuro.
3. Navigazione laterale (Cattura, Dati estratti, Debug LLM solo con `--debug`) e **barra di stato**
   sempre visibile: stato cattura ("In corso" / "Ferma"), frame in coda, pratiche, e **un solo
   pulsante primario** Avvia/Ferma. **[mia scelta]**
4. Tab Cattura: impostazioni in una card, azioni secondarie (Acquisisci ora, Esporta) distinte dalla
   primaria, log in un pannello richiudibile (chiuso di default, con l'ultima riga e il numero di
   errori visibili). Messaggi per l'operatore in italiano semplice che dicono cosa fare; il log
   conserva il testo tecnico.
5. Tab Dati: toolbar ordinata, ricerca su NDG e denominazione, stato vuoto con istruzione, nomi di
   sessione leggibili (es. "Sessione 1 · 10:42") invece dell'ID grezzo, rinomina colonna con doppio
   click sull'intestazione, colonne NDG e denominazione sempre visibili durante lo scroll
   orizzontale (come `freeze_panes = "C3"` dell'Excel). Se le colonne fisse mettono a rischio
   selezione o modifica, si lasciano fuori e lo si dichiara.
6. **Correzione dei valori** (sezione dedicata sotto).
7. Accessibilità per sessioni lunghe: contrasto testo >= 4.5:1 (componenti e testo grande >= 3:1),
   focus da tastiera sempre visibile, navigazione completa da tastiera con scorciatoie mostrate nei
   tooltip, nessuno stato affidato solo al colore (icona + testo), corpo del testo di 10-11 pt,
   layout verificato a scala 125% e 150%.
8. Avviso alla chiusura se ci sono dati non esportati. **[utente: opzione A]** Il dialogo elenca le
   sessioni non esportate e ha due azioni, "Torna all'app" (predefinita) ed "Esci senza esportare";
   non esporta da solo. **[mia scelta]** Motivo: ogni Avvia crea una sessione e un export scrive una
   sola sessione; esportare alla chiusura imporrebbe una regola per più sessioni.

## Correzione dei valori

- **Archivio** nel `LocalExtractionClient` (stesso lock di `_results`), per `job_id`, NDG
  normalizzato (`normalize_ndg()`) e `schema_key`. Ogni voce tiene valore corretto e valore
  originale. API indicativa: `set_correction`, `clear_correction`, `get_corrections`.
- **Applicazione**: `consolidate(results, corrections=None)` applica le correzioni **dopo** il merge
  con `pick_best()`; il merge dei frame non cambia. La correzione vince sempre, anche se un frame
  successivo porta un altro valore estratto (il valore originale mostrato nel tooltip è quello
  estratto più recente). Questa è una regola di precedenza deliberata ("l'operatore vince"), non una
  seconda semantica di merge: va scritta in un ADR.
- **Export**: `export_results(results, path, labels=None, corrections=None)`. Entrambe le tab passano
  le correzioni dell'archivio. I valori passano da `_set_text()`: una correzione che inizia con `=`
  resta testo inerte.
- **Etichette delle colonne** rinominate: oggi valgono solo per l'export dalla tab Dati (la tab
  Cattura esporta senza). Passano nello stesso stato condiviso del client e valgono per ogni export:
  la docstring di `export_results()` dice che i due pulsanti non devono divergere. **[mia scelta]**
- **Interazione**: doppio click, F2 o digitazione su una cella; Invio conferma, Esc annulla. Cella
  corretta marcata (tinta + icona, non solo colore) con tooltip del valore originale e azione
  "Ripristina originale". Svuotare la cella è una correzione valida (campo allucinato). Nessuna
  validazione di tipo (date, importi): solo `strip()`.
- **NDG non modificabile** (è l'identità della pratica, chiave di `consolidate()`), né la riga di
  fascia. Non sono modificabili nemmeno le righe senza NDG (sessione che non l'ha ancora letto):
  quando l'NDG arriva quel record viene assorbito nella prima pratica e una correzione fatta prima
  resterebbe orfana. **[mia scelta]**
- Le correzioni vivono quanto i risultati: **solo in memoria**, nessun salvataggio su disco, perché
  sarebbero dati personali di clienti della banca. **[utente: opzione A]** Va scritto nell'ADR.
- **Avviso di chiusura**: il client tiene per sessione un'impronta dell'output consolidato (con le
  correzioni) all'ultimo export riuscito; la sessione è "modificata" quando l'impronta attuale
  differisce. Un risultato di errore con `fields: {}` non cambia l'output e non la rende modificata.
  **[mia scelta]** `MainWindow.closeEvent` mostra il dialogo **prima** di `stop_capture()` e
  `shutdown()`, solo se almeno una sessione è modificata; se ci sono frame ancora in elaborazione
  (`pending_extractions()` > 0) il testo lo dice, e "Torna all'app" lascia finire il lavoro.
  L'hook `EDGE_AGENT_SMOKE=1` (`app.quit()`) deve continuare a chiudere senza dialoghi.

## Fuori scopo

- Evidenziare le celle a bassa confidenza: lo vieta il vincolo "l'edge-agent mostra solo dati di
  business" (confidenza e provenienza vanno in `edge-agent.log`).
- Validazione di date e importi, modifica dell'NDG, unione di righe, foglio di audit delle
  correzioni, marcatura delle celle corrette nell'Excel, salvataggio automatico su disco.
- Modifiche a cattura, estrazione, classificatore, router, semantica di `pick_best()`/`consolidate()`
  per i frame, o comportamento dei worker. Nessuna riscrittura in QML, nessuna libreria Fluent.

## Anti-obiettivi (sarebbe un fallimento anche se "funziona")

- Un look da demo: vetro, neon, gradienti, emoji, animazioni gratuite.
- Qualunque cambio che alteri i frame catturati o il comportamento della cattura.
- Una correzione persa in silenzio (per un frame nuovo, un ricarica, un export).
- Dati di clienti scritti su disco oltre all'Excel che l'operatore esporta e al log già esistente.

## Vincoli (dal progetto)

- Costante 3: `ui.main_window` si importa **dopo** `run_preflight()`; il tema va applicato prima del
  preflight (il dialogo del primo avvio deve avere lo stesso stile) e il modulo del tema non deve
  importare `extraction`.
- Costante 14: nessuna confidenza, stato o costo nelle tab. `consolidate()` resta l'unico punto di
  merge dei frame.
- xlsx: formule neutralizzate con `cell.data_type = "s"`, mai `escape_csv_formula()`.
- Stringhe UI in italiano; codice, identificatori e commenti in inglese; annotazioni complete;
  marcatori di sezione `# ====...`.
- Percorsi sempre via `app_paths` (sorgente e bundle PyInstaller). Font, icone e plugin SVG devono
  stare nel pacchetto: `build_exe.bat` deve continuare a produrre un pacchetto funzionante.
- Test: prima il test che fallisce, poi il codice (regole della suite). Estendere
  `test_practice_consolidation.py`, `test_excel_export.py`, `test_local_extraction_client.py`; test
  Qt con `QT_QPA_PLATFORM=offscreen`. Lanciare `python -m pytest tests` prima di dichiarare finito.
  Decisione che cambia comportamento = ADR in `docs/adr/` + test.
- I commit sono dell'autore umano: nessun "Co-Authored-By" né menzione di AI.

## Approcci considerati

1. **Tema proprio + UX riordinata, stessa architettura. Scelto** (tempo stimato: circa 1 giorno di
   lavoro con correzioni e avviso di chiusura). Tocca `edge_agent.py`, `ui/*`, un modulo di tema e
   le icone, `excel_export.py`, `practice_consolidation.py`, `local_extraction_client.py`.
2. Libreria Fluent (`qfluentwidgets`): risultato rapido ma look generico, licenza da verificare
   (credo GPL o commerciale) e dipendenza da impacchettare. Scartato.
3. Riscrittura in QML/Qt Quick: massima resa ma si rifà tutta la UI e il ponte dei segnali. Scartato
   per ora.

**Acrylic e `pywinstyles`. [mia scelta]** Niente `pywinstyles`: ultimo push luglio 2024, bug aperti
sull'acrylic (#37, #38, #39), README con esempi PyQt5. Niente acrylic sulla finestra principale: la
regola dei materiali Windows (analogo WinUI, non specifico PyQt) assegna Mica alle finestre
principali e Acrylic alle superfici transitorie; inoltre l'acrylic sfoca ciò che sta dietro e,
poiché l'agent cattura l'intero monitor, potrebbe sporcare i frame se la finestra sta sul monitor
catturato. Extra opzionale e **ultimo**: Mica via `ctypes` (`DwmSetWindowAttribute`,
`DWMWA_SYSTEMBACKDROP_TYPE`, Windows 11 22H2 o successivo) solo su barra del titolo e navigazione, più
la barra del titolo scura coerente con il tema (`DWMWA_USE_IMMERSIVE_DARK_MODE`). Senza effetto sugli
altri sistemi. Non blocca l'accettazione e si toglie senza impatto sul resto. Prima di tenerlo,
verificare con una cattura reale che i frame non cambiano.

## Scelte mie da controllare

Dialogo di chiusura senza export automatico; righe senza NDG non modificabili; etichette rinominate
valide in ogni export; indicatore "modificato" basato sul confronto con l'ultimo export; tema chiaro
di default; font di sistema Segoe UI (nessun file da impacchettare; IBM Plex Sans solo se
vuoi un tratto più "bancario"); icone SVG Lucide (licenza ISC, da riverificare); palette di partenza
(Marionette, "Data-Dense Dashboard"): primario `#1E40AF`, sfondo `#F8FAFC`, scheda `#FFFFFF`, secondario
tenue `#E9EEF6`, testo tenue `#475569`, errore `#DC2626`, evidenza `#D97706`; variante scura su scala
slate (`#0F172A`, `#1E293B`, testo `#F8FAFC`). I colori stanno in un solo file di token: se arrivano
colori aziendali si cambiano in un punto. I valori vanno **verificati per contrasto** prima dell'uso.

## Lasciato al costruttore

Struttura di moduli e file del tema e delle icone; valori finali dei token dopo la verifica di
contrasto; tasti delle scorciatoie; come condividere lo stato Avvia/Ferma tra barra di stato e tab
Cattura (una sola fonte di verità per il worker); implementazione delle colonne fisse; formato dei
nomi di sessione; numero e testo dell'ADR; se Mica entra o no.

## Criteri di accettazione

1. `python src/edge-agent/edge_agent.py` parte; con `EDGE_AGENT_SMOKE=1` esce da solo; il dialogo del
   primo avvio ha lo stesso stile.
2. Tema chiaro e scuro seguono Windows; report di contrasto >= 4.5:1 sui testi.
3. Una correzione sopravvive ai frame successivi, compare in entrambi gli export, si ripristina; l'NDG
   non è modificabile.
4. Chiusura con dati non esportati chiede conferma; senza dati si chiude subito.
5. `python -m pytest tests` verde; pacchetto `build_exe.bat` con icone e font funzionante.
6. Screenshot di entrambe le tab, nei due temi, con dati e a vuoto, consegnati all'utente per la
   revisione visiva ("elegante" lo decide l'occhio: sono previsti giri di correzione).
