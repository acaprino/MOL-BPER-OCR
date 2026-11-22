# Edge-agent UI professionale e correzione dei valori — Piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dare all'edge-agent PyQt6 un aspetto e una UX da prodotto (tema proprio, navigazione, barra di stato) e permettere agli operatori di correggere i valori della tabella senza perderli.

**Architecture:** Le correzioni sono un livello di precedenza applicato dopo il merge dei frame (`consolidate(results, corrections)`), tenuto in `LocalExtractionClient` e usato da un unico percorso di export. Il tema è un modulo top-level (`theme.py`) con token e QSS propri al posto di `qt-material`; la UI si riordina in navigazione laterale + barra di stato + due tab ridisegnate.

**Tech Stack:** Python, PyQt6 6.11 (QtSvg incluso), openpyxl, pytest (`.venv`, `QT_QPA_PLATFORM=offscreen`).

**Spec:** `docs/superpowers/specs/2026-11-22-edge-agent-ui-redesign-design.md`

## Global Constraints

- `ui.main_window` si importa **dopo** `bootstrap.run_preflight()` (Costante 3). `ui/__init__.py` importa `capture_tab` e `main_window`: quindi **`theme.py` sta in `src/edge-agent/` (top-level), mai dentro `ui/`**, e non importa `extraction`.
- Nessuna confidenza, stato, costo o provenienza nelle tab (Costante 14). `consolidate()` resta l'unico punto di merge dei frame; la correzione è una precedenza applicata dopo.
- xlsx: formule neutralizzate con `cell.data_type = "s"` (`_set_text()`), mai `escape_csv_formula()`.
- Stringhe UI in italiano; codice, identificatori, commenti in inglese; annotazioni complete su ogni funzione; marcatori `# ============================================================`.
- Percorsi sempre via `app_paths`. Asset (icone) in `src/edge-agent/assets/`, copiati da `build_exe.bat` e da `edge_agent.spec`.
- Nessun salvataggio su disco di risultati o correzioni. NDG e righe senza NDG non modificabili. Nessun `pywinstyles`, nessun acrylic.
- Contrasto testo >= 4.5:1, componenti e testo grande >= 3:1; focus visibile; stati mai solo a colore; corpo 10-11 pt; layout verificato a scala 125% e 150%.
- Scorciatoie (le mostrano i tooltip): Avvia/Ferma `F9`, Esporta Excel `Ctrl+E`, cerca `Ctrl+F`, modifica cella `F2`.
- Test prima del codice (suite rules di CLAUDE.md): scrivere, vedere fallire per il motivo giusto, poi implementare. Mai indebolire un test. `python -m pytest tests` verde prima di dichiarare finito.
- Commit: solo con il via dell'utente; `git add` dei soli file del task (mai `git add -A`: il working tree ha modifiche non correlate); messaggio **senza** `Co-Authored-By` né menzioni di AI (CLAUDE.md prevale).
- Test Qt: un solo `QApplication` creato in `tests/conftest.py` (Task 3); gli helper `_app()` esistenti lo riusano via `instance()`.

## Review Focus

1. Correzione che inizia con `=`, `+`, `-`, `@`: nell'Excel resta testo inerte e il valore è quello digitato (Task 2).
2. Testo incollato con caratteri di controllo o lunghissimo: l'export non deve fallire; il testo viene ripulito e limitato a 32767 caratteri (Task 2).
3. Un frame arriva mentre l'editor di una cella è aperto: il testo in corso non si perde e la tabella non crolla (Task 9).
4. NDG scritto in modo diverso tra frame (`012.345` vs `12345`): la correzione si applica comunque (Task 1).
5. Chiusura con frame ancora in elaborazione o con la stessa pratica in due sessioni: il dialogo lo dice e elenca entrambe le sessioni (Task 2 e 5).

---

### Task 1: Correzioni nel consolidamento

**Files:**
- Modify: `src/edge-agent/practice_consolidation.py`
- Test: `tests/test_practice_consolidation.py` (riusa l'helper `_frame`)

**Interfaces:**
- Produces: `Corrections = Mapping[str, Mapping[str, Optional[str]]]` (`{ndg normalizzato: {schema_key: valore | None}}`); `consolidate(results, corrections: Optional[Corrections] = None) -> List[PracticeRecord]`; `is_correctable(record: PracticeRecord, schema_key: str) -> bool`. Un campo corretto ha `fields[key] == {..., "value": <corretto>, "original_value": <estratto o None>, "corrected": True}`; gli altri non hanno la chiave `"corrected"`.

- [ ] **Step 1: scrivere i test (devono fallire)**

```python
def test_correction_replaces_the_extracted_value_and_keeps_the_original() -> None:
    records = consolidate([_frame("12345", tipo=("BPI Mutui", 0.9))], {"12345": {"tipo": "Mutuo"}})
    field = records[0].fields["tipo"]
    assert (field["value"], field["original_value"], field["corrected"]) == ("Mutuo", "BPI Mutui", True)
    assert "corrected" not in records[0].fields["stato"]

def test_correction_survives_a_later_frame_with_another_value() -> None:
    records = consolidate(
        [_frame("12345", tipo=("A", 0.5)), _frame("12345", tipo=("B", 0.9))], {"12345": {"tipo": "Mutuo"}})
    assert records[0].fields["tipo"]["value"] == "Mutuo"
    assert records[0].fields["tipo"]["original_value"] == "B"

def test_correction_applies_when_the_frame_writes_the_ndg_differently() -> None:  # Review Focus 4
    records = consolidate([_frame("012.345", tipo=("A", 0.9))], {"12345": {"tipo": "Mutuo"}})
    assert records[0].fields["tipo"]["value"] == "Mutuo"

def test_clearing_a_field_is_a_valid_correction() -> None:
    field = consolidate([_frame("1", tipo=("A", 0.9))], {"1": {"tipo": None}})[0].fields["tipo"]
    assert (field["value"], field["corrected"]) == (None, True)

def test_ndg_and_unknown_keys_cannot_be_corrected_and_other_practices_are_untouched() -> None:
    records = consolidate([_frame("1", tipo=("A", 0.9)), _frame("2", tipo=("B", 0.9))],
                          {"1": {"ndg": "999", "boh": "x"}, "2": {}})
    assert [r.ndg for r in records] == ["1", "2"]
    assert "corrected" not in records[0].fields["ndg"] and records[1].fields["tipo"]["value"] == "B"

def test_is_correctable_excludes_ndg_and_records_without_ndg() -> None:
    with_ndg = consolidate([_frame("1", tipo=("A", 0.9))])[0]
    anonymous = consolidate([_frame(None, tipo=("A", 0.9))])[0]
    assert is_correctable(with_ndg, "tipo") and not is_correctable(with_ndg, "ndg")
    assert not is_correctable(anonymous, "tipo")
```

- [ ] **Step 2:** `python -m pytest tests/test_practice_consolidation.py -v` — atteso FAIL (`is_correctable`/parametro `corrections` mancanti).
- [ ] **Step 3:** Implementare le firme sopra in `practice_consolidation.py`. `_Group.to_record(corrections_for_ndg)` applica l'overlay copiando i dict dei campi (nessun alias con `_Group.fields`); chiavi fuori da `FIELD_KEYS` o `ndg` ignorate; record con `ndg=None` ignorano le correzioni.
- [ ] **Step 4:** stesso comando — atteso PASS, insieme ai test già esistenti del file.
- [ ] **Step 5: Commit** `git add tests/test_practice_consolidation.py src/edge-agent/practice_consolidation.py`

### Task 2: Stato del client e unico percorso di export

**Files:**
- Modify: `src/edge-agent/excel_export.py` (`export_results(..., corrections=None)`), `src/edge-agent/local_extraction_client.py`
- Test: `tests/test_excel_export.py`, `tests/test_local_extraction_client.py`

**Interfaces:**
- Consumes: `consolidate(results, corrections)` e `normalize_ndg()` (Task 1 / `extraction.normalization`).
- Produces su `LocalExtractionClient`: `session_label(job_id: str) -> str` (`"Sessione 2 · 10:42"`, numerata in ordine di `start_job()`); `set_correction(job_id, ndg: str, schema_key: str, value: Optional[str]) -> None` (`ValueError` per `ndg`, chiavi non canoniche o NDG illeggibile; pulisce il testo: `strip()`, rimuove `ILLEGAL_CHARACTERS_RE` di openpyxl, limite 32767 caratteri, vuoto → `None`); `clear_correction(job_id, ndg, schema_key) -> None`; `get_corrections(job_id) -> Dict[str, Dict[str, Optional[str]]]` (copia); `get_column_labels() -> Dict[str, str]` (copia); `set_column_label(schema_key: str, label: str) -> None`; `export_workbook(job_id: str, path: str) -> int`; `unexported_jobs() -> List[str]`.
- `export_results(results, path, labels=None, corrections=None) -> int`.

- [ ] **Step 1: scrivere i test (devono fallire).** In `test_excel_export.py`: `test_export_results_applies_corrections` (cella pratica 1 colonna `tipo` == `"Mutuo"`). In `test_local_extraction_client.py` aggiungere una `SequencePipeline` che restituisce campi scriptati e questi test, ognuno con `ingest_frame` + `_wait_for`:
  - `test_set_correction_cleans_the_text`: `"  Mutuo\x0b "` → `"Mutuo"`; `""` → `None`; 40000 caratteri → lunghezza 32767 (Review Focus 2).
  - `test_set_correction_refuses_ndg_and_unknown_fields`: `pytest.raises(ValueError)` per `"ndg"` e `"boh"`.
  - `test_corrections_are_per_session_and_returned_as_copies`.
  - `test_export_workbook_writes_corrections_and_shared_labels`: dopo `set_column_label("tipo", "Tipo pratica")` l'intestazione riga 2 vale `"Tipo pratica"` e la cella riga 3 `"Mutuo"`.
  - `test_formula_like_corrections_are_exported_as_inert_text`: per `"=1+1"`, `"+5"`, `"-300,50"`, `"@x"` → `cell.data_type == "s"` e `cell.value ==` testo digitato (Review Focus 1).
  - `test_correction_with_control_characters_exports_without_error`.
  - `test_job_is_unexported_until_exported_and_again_after_a_change`: dati → in `unexported_jobs()`; dopo `export_workbook` no; dopo un nuovo risultato con valore nuovo o una correzione sì.
  - `test_error_only_job_is_never_unexported` (risultato `_status: ERROR`, `fields: {}`).
  - `test_reverting_a_correction_restores_the_exported_state`.
  - `test_session_labels_number_sessions_in_start_order`: regex `^Sessione 1 · \d\d:\d\d$` poi `Sessione 2`.
- [ ] **Step 2:** `python -m pytest tests/test_excel_export.py tests/test_local_extraction_client.py -v` — atteso FAIL.
- [ ] **Step 3:** Implementare. Stato nuovo sotto lo stesso `self._lock` di `_results`. `export_workbook` fa **uno snapshot** (risultati, correzioni, etichette) sotto lock, esporta dallo snapshot con `export_results` e registra l'impronta *dello snapshot* (non ricalcolata dopo). Impronta = hash del contenuto consolidato (NDG + valori dei campi canonici), `None` se nessun record ha un valore non nullo; `unexported_jobs()` restituisce i job con impronta non `None` diversa da quella dell'ultimo export.
- [ ] **Step 4:** stesso comando più `python -m pytest tests/test_practice_consolidation.py` — atteso PASS.
- [ ] **Step 5: Commit** dei quattro file.

### Task 3: Tema, avvio e fixture Qt

**Files:**
- Create: `src/edge-agent/theme.py`, `tests/test_theme.py`
- Modify: `src/edge-agent/edge_agent.py` (righe 52-59), `tests/conftest.py`

**Interfaces:**
- Produces: `Tokens` (dataclass frozen: `name, background, surface, surface_alt, border, text, text_muted, primary, on_primary, danger, corrected_bg, corrected_icon`), `LIGHT`, `DARK`; `contrast_ratio(foreground: str, background: str) -> float` (WCAG); `build_stylesheet(tokens: Tokens) -> str`; `apply_theme(app: QApplication) -> Tokens` (sceglie da `app.styleHints().colorScheme()`, `Unknown` → chiaro; font `Segoe UI` 10 pt; si riapplica su `colorSchemeChanged`); `current_tokens() -> Tokens`. `conftest.py` espone `qapp` e crea all'import un `QApplication` con `QT_QPA_PLATFORM=offscreen` (protetto da `ImportError`).

- [ ] **Step 1: test (falliscono)** in `tests/test_theme.py`:
  - `test_text_pairs_meet_aa_contrast_in_both_themes`: per `LIGHT` e `DARK`, `contrast_ratio` >= 4.5 per `(text, background)`, `(text, surface)`, `(text_muted, surface)`, `(on_primary, primary)`, `(danger, surface)`; >= 3.0 per `(corrected_icon, surface)`.
  - `test_stylesheet_styles_focus_for_every_input_widget`: la QSS contiene `QPushButton:focus`, `QLineEdit:focus`, `QComboBox:focus`, `QTableView:focus`.
  - `test_apply_theme_follows_the_system_scheme` (offscreen): `apply_theme(qapp)` restituisce `LIGHT` o `DARK` coerenti con `qapp.styleHints().colorScheme()` e imposta `qapp.styleSheet()` non vuoto.
- [ ] **Step 2:** `python -m pytest tests/test_theme.py -v` — atteso FAIL (modulo mancante).
- [ ] **Step 3:** Creare `theme.py`. Valori di partenza (da **verificare** col test e correggere se non passano): chiaro `background #F8FAFC, surface #FFFFFF, surface_alt #E9EEF6, text #0F172A, text_muted #475569, primary #1E40AF, on_primary #FFFFFF, danger #DC2626, corrected_bg #FEF3C7, corrected_icon #D97706`; scuro `background #0F172A, surface #1E293B, text #F8FAFC, text_muted #94A3B8, primary #60A5FA, on_primary #0F172A`. La QSS copre `QMainWindow, QWidget, QFrame#card, QPushButton` (primario `[primary="true"]`, secondario, disabilitato), `QLineEdit, QComboBox, QSpinBox, QTextEdit, QTableView` (intestazioni, righe alternate, selezione), `QToolTip`, `QScrollBar`, `QMessageBox`, stati `:hover/:focus/:disabled` con bordo di focus 2 px.
- [ ] **Step 4:** In `edge_agent.py` sostituire il blocco `qt_material` con `import theme; theme.apply_theme(app)` (prima di `run_preflight`, così lo stile vale anche per il dialogo del primo avvio; nessun `try/except ImportError`).
- [ ] **Step 5:** `python -m pytest tests/test_theme.py tests/test_local_extraction_client.py -v` (verifica che `conftest` non rompa i test esistenti) poi `EDGE_AGENT_SMOKE=1 python src/edge-agent/edge_agent.py` — atteso: parte e si chiude da solo dopo ~5 s (con il tema ancora vecchio nelle tab, già senza `qt_material`).
- [ ] **Step 6: Commit** `theme.py`, `edge_agent.py`, `conftest.py`, `test_theme.py`.

### Task 4: Icone SVG

**Files:**
- Create: `src/edge-agent/ui/icons.py`, `src/edge-agent/assets/icons/*.svg`, `src/edge-agent/assets/icons/LICENSE-lucide.txt`, `tests/test_icons.py`

**Interfaces:**
- Produces: `ICON_NAMES: Tuple[str, ...]` = `("play", "square", "download", "camera", "search", "refresh-cw", "pencil", "undo-2", "chevron-down", "chevron-right", "table", "scan", "bug", "check", "triangle-alert")`; `icon(name: str, color: str, size: int = 20) -> QIcon` (rende l'SVG sostituendo `currentColor`, con device pixel ratio; `KeyError` per nome ignoto).

- [ ] **Step 1: test (falliscono):** `test_every_icon_name_has_an_svg_file`; `test_icon_renders_pixels_in_the_requested_color` (render 20 px, almeno un pixel non trasparente con il colore chiesto); `test_unknown_icon_name_raises_key_error`.
- [ ] **Step 2:** `python -m pytest tests/test_icons.py -v` — atteso FAIL.
- [ ] **Step 3:** Scaricare gli SVG Lucide dal repository `lucide-icons/lucide` (licenza ISC: ricontrollarla e salvarne il testo in `LICENSE-lucide.txt`; i nomi file possono differire da `ICON_NAMES` se Lucide li ha rinominati: tenere `ICON_NAMES` coerente coi file). Implementare `icons.py` con `QSvgRenderer`; cartella da `app_paths.bundled_assets_dir() / "icons"`.
- [ ] **Step 4:** stesso comando — atteso PASS.
- [ ] **Step 5: Commit.**

### Task 5: Guscio — navigazione, barra di stato, dialogo di chiusura

**Files:**
- Create: `src/edge-agent/ui/shell.py`, `tests/test_main_window.py`
- Modify: `src/edge-agent/ui/main_window.py`, `src/edge-agent/ui/capture_tab.py`

**Interfaces:**
- Consumes: `LocalExtractionClient.unexported_jobs()`, `.session_label()`, `.pending_extractions()` (Task 2); `icons.icon` (Task 4); `theme.current_tokens()` (Task 3).
- Produces: `NavRail(QWidget)` con `page_selected = pyqtSignal(int)`, `add_page(label: str, icon_name: str) -> int`, `set_current(index: int) -> None`; `StatusHeader(QWidget)` con `toggle_requested = pyqtSignal()`, `set_running(running: bool) -> None` (pulsante primario "Avvia"/"Ferma", etichetta "● Cattura in corso" / "○ Cattura ferma"), `set_counters(queued: int, done: int, practices: int) -> None` (testo `"{done} elaborati su {queued} · {practices} pratiche"`); `MainWindow.__init__(config, show_debug=False, parent=None, extraction_client: Optional[LocalExtractionClient] = None)`; `leave_message(labels: Sequence[str], pending: int) -> str` (funzione di modulo in `main_window.py`); `MainWindow._ask_leave_unexported(labels: List[str], pending: int) -> bool` (`QMessageBox` con "Torna all'app" predefinito e "Esci senza esportare"); `CaptureTab.running_changed = pyqtSignal(bool)`, `counters_changed = pyqtSignal(int, int)`, `start_capture() -> None`, `is_running() -> bool`.

- [ ] **Step 1: test (falliscono)** in `tests/test_main_window.py`, con `MainWindow(config, extraction_client=<client con pipeline finta>)`:
  - `test_status_header_labels_follow_state`: `set_running(True)` → testo pulsante `"Ferma"`; `set_counters(12, 12, 3)` → `"12 elaborati su 12 · 3 pratiche"`.
  - `test_leave_message_mentions_frames_still_processing`: per `pending=2` contiene `"2 frame ancora in elaborazione"`; per `0` no; elenca ogni etichetta di sessione (Review Focus 5, due sessioni).
  - `test_close_without_unexported_data_accepts_without_asking`.
  - `test_close_with_unexported_data_and_back_keeps_the_window_open` (`_ask_leave_unexported` sostituita da un registratore che ritorna `False`; `event.isAccepted()` falso; chiamata una volta con le etichette giuste).
  - `test_exit_without_exporting_stops_capture_and_shuts_the_client_down` (ritorna `True`; evento accettato; dopo, `client.ingest_frame(...)` solleva `RuntimeError`).
  - `test_start_stop_shortcut_toggles_capture`: il pulsante del header chiama `CaptureTab.start_capture/stop_capture` (worker sostituito da un doppio che registra le chiamate: confine reale della cattura).
- [ ] **Step 2:** `python -m pytest tests/test_main_window.py -v` — atteso FAIL.
- [ ] **Step 3:** Implementare `shell.py`. In `MainWindow`: `NavRail` + `QStackedWidget` al posto di `QTabWidget` (pagine Cattura, Dati estratti, Debug LLM solo con `--debug`; `_on_tab_changed` mantiene la logica attuale, indice 1 = Dati), `StatusHeader` in alto collegato ai segnali di `CaptureTab` (pratiche = `len(consolidate(client.get_results(job)))` a ogni `result_ready`), `F9` sul pulsante. `closeEvent`: `unexported = client.unexported_jobs()`; se non vuota e `_ask_leave_unexported(...)` ritorna `False` → `event.ignore(); return` **prima** di `stop_capture()`/`shutdown()`. `EDGE_AGENT_SMOKE` continua a chiudere via `app.quit()` senza dialoghi.
- [ ] **Step 4:** In `capture_tab.py` rimuovere `start_button`/`stop_button`, esporre i segnali e i metodi pubblici sopra (`_on_start_capture` → `start_capture`), emettere `running_changed` in avvio/arresto e `counters_changed` nei due handler di conteggio.
- [ ] **Step 5:** stesso comando più la suite `tests/test_theme.py` — atteso PASS.
- [ ] **Step 6: Commit.**

### Task 6: Strumento di revisione visiva

**Files:**
- Create: `tools/ui_screenshots.py`, `tests/test_ui_screenshots.py`

**Interfaces:**
- Produces: `main(argv: Optional[Sequence[str]] = None) -> int` con `--out <dir>` (default `outputs/ui-review`) e `--scale <float>` (default 1.0); scrive `{light,dark}-{capture,data,data-empty}.png` con `QWidget.grab()`, finestra offscreen 1280x800, dati **inventati** (nessun dato reale di clienti), `LLM_API_KEY` fittizia via `os.environ.setdefault` prima degli import.

- [ ] **Step 1: test (fallisce):** `test_ui_screenshots_writes_the_six_pngs(tmp_path)` → `main(["--out", str(tmp_path)]) == 0` e i sei file esistono e non sono vuoti.
- [ ] **Step 2:** `python -m pytest tests/test_ui_screenshots.py -v` — atteso FAIL.
- [ ] **Step 3:** Implementare lo script (popola il client con `ingest_frame` e una pipeline finta con tre pratiche; forza lo schema colori chiaro/scuro; scala via `QT_SCALE_FACTOR`).
- [ ] **Step 4:** test PASS; poi `python tools/ui_screenshots.py` e **guardare i PNG** (Read). Da qui in poi, dopo ogni task di UI rilanciarlo e controllare a occhio, anche con `--scale 1.5`.
- [ ] **Step 5: Commit.**

### Task 7: Tab Cattura

**Files:**
- Create: `src/edge-agent/ui/widgets.py` (`Card(QFrame)` con `objectName "card"`; `CollapsiblePanel(QWidget)` con titolo, `set_summary(text: str)`, `set_expanded(expanded: bool)`, chiuso di default)
- Modify: `src/edge-agent/ui/capture_tab.py`
- Test: `tests/test_capture_tab.py`

**Interfaces:**
- Consumes: `LocalExtractionClient.export_workbook(job_id, path)` (Task 2), `icons.icon`, `Card` e `CollapsiblePanel`.
- Produces: `CaptureTab.log_error_count() -> int`.

- [ ] **Step 1: test (falliscono):** `test_log_panel_is_collapsed_by_default_and_summarises_the_last_line`; `test_error_lines_are_counted_in_the_panel_summary` (una riga `[ERROR] ...` → `log_error_count() == 1`, sommario "1 errore"); `test_settings_are_locked_while_capturing` (con `running_changed(True)` i campi impostazioni sono disabilitati, tornano abilitati a `False`).
- [ ] **Step 2:** `python -m pytest tests/test_capture_tab.py -v` — atteso FAIL.
- [ ] **Step 3:** Ridisegnare: impostazioni in una `Card`; azioni secondarie con icona e tooltip con scorciatoia ("Acquisisci ora", "Esporta Excel" `Ctrl+E`); registro dentro `CollapsiblePanel`; l'export usa `client.export_workbook()` (niente più `export_results` diretto). Testi per l'operatore: sessione non avviabile → "Non riesco ad avviare la sessione. Chiudi e riapri l'app; se succede ancora, contatta l'assistenza."; niente da esportare → "Non c'è ancora niente da esportare. Avvia la cattura e attendi almeno un'estrazione."; export riuscito → "{n} pratiche salvate in:\n{percorso}"; errore del worker → riga di stato "Cattura interrotta da un errore. Dettagli nel registro." Il log mantiene il testo tecnico.
- [ ] **Step 4:** stesso comando PASS; `python tools/ui_screenshots.py` e controllo visivo.
- [ ] **Step 5: Commit.**

### Task 8: Tab Dati — base

**Files:**
- Modify: `src/edge-agent/ui/data_table_tab.py`
- Test: `tests/test_data_table_tab.py`

**Interfaces:**
- Consumes: `session_label`, `get_column_labels`, `set_column_label`, `export_workbook` (Task 2).
- Produces: `DataTableTab._apply_column_label(schema_key: str, label: str) -> None`; `DataTableTab.search_box: QLineEdit`; `DataTableTab.empty_state: QWidget`.

- [ ] **Step 1: test (falliscono):** `test_empty_state_is_shown_until_a_practice_exists`; `test_session_picker_shows_labels_and_keeps_job_ids_as_data` (`itemText == "Sessione 1 · hh:mm"`, `itemData == job_id`); `test_search_hides_rows_that_do_not_match_ndg_or_denominazione` (case-insensitive, riga di fascia sempre visibile); `test_renaming_a_column_updates_the_shared_labels_for_every_export` (`client.get_column_labels()`).
- [ ] **Step 2:** `python -m pytest tests/test_data_table_tab.py -v` — atteso FAIL.
- [ ] **Step 3:** Toolbar ordinata con icone (`Ctrl+E` esporta, `Ctrl+F` cerca), `QStackedLayout` stato vuoto ("Nessuna pratica ancora. Avvia la cattura dalla scheda Cattura.") / tabella; rinomina colonna con doppio click sull'intestazione (via `sectionDoubleClicked` + `QInputDialog`, che chiama `_apply_column_label`); `_column_labels` rimosso dalla tab (stato nel client); export via `client.export_workbook()`.
- [ ] **Step 4:** PASS e controllo visivo con `tools/ui_screenshots.py`.
- [ ] **Step 5: Commit.**

### Task 9: Tab Dati — correzione dei valori

**Files:**
- Modify: `src/edge-agent/ui/data_table_tab.py`
- Test: `tests/test_data_table_tab.py`

**Interfaces:**
- Consumes: `is_correctable`, `consolidate(...)`, `set_correction`, `clear_correction`, `get_corrections` (Task 1-2); `icons.icon("pencil", ...)`.
- Produces: `CORRECTED_ROLE = Qt.ItemDataRole.UserRole + 1` (`True` sulle celle corrette); azione di contesto "Ripristina originale".

- [ ] **Step 1: test (falliscono):**
  - `test_editing_a_cell_stores_a_correction_and_marks_it` (imposta il testo, `client.get_corrections(job) == {ndg: {key: testo}}`, cella con `CORRECTED_ROLE` vero e tooltip "Valore originale: …").
  - `test_ndg_band_row_and_anonymous_rows_are_not_editable`.
  - `test_typing_the_extracted_value_does_not_create_a_correction`; con una correzione esistente, digitare l'originale la rimuove.
  - `test_clearing_the_text_stores_an_empty_correction`.
  - `test_correction_survives_a_new_result_for_the_same_practice` (nuovo `ingest_frame` stessa pratica → valore ancora corretto, originale aggiornato).
  - `test_restore_original_removes_the_correction`.
  - `test_result_arriving_while_an_editor_is_open_keeps_the_editor` (Review Focus 3: `table.editItem(item)`, poi un risultato nuovo + `processEvents`; `table.state() == EditingState`; confermando il testo la correzione viene salvata).
- [ ] **Step 2:** `python -m pytest tests/test_data_table_tab.py -v` — atteso FAIL.
- [ ] **Step 3:** `_set_cell` rende editabili solo le celle con `is_correctable(record, key)`. `itemChanged` (con guardia durante il popolamento) normalizza il testo (stessa pulizia del client), poi `set_correction` o `clear_correction`; il rebuild segue con `QTimer.singleShot(0, ...)`. Se `table.state() == EditingState`, `_load_table` viene **rimandato** fino alla chiusura dell'editor. Celle corrette: sfondo `corrected_bg`, icona matita, `CORRECTED_ROLE`, tooltip dell'originale. Colonne e righe di fascia non editabili.
- [ ] **Step 4:** PASS; `python -m pytest tests` per intero; controllo visivo.
- [ ] **Step 5: Commit.**

### Task 10: Colonne NDG e denominazione fisse (staccabile)

**Files:**
- Create: `src/edge-agent/ui/frozen_table.py`, `tests/test_frozen_table.py`
- Modify: `src/edge-agent/ui/data_table_tab.py`

**Interfaces:**
- Produces: `FrozenColumnsTable(QTableWidget)` con `frozen_count: int = 2`; una seconda `QTableView` sullo stesso modello mostra solo le prime colonne, con scroll verticale e selezione sincronizzati (tecnica standard "frozen column").

- [ ] **Step 1: test (falliscono):** `test_frozen_view_shows_only_the_first_two_columns`; `test_vertical_scroll_and_selection_stay_in_sync`; i test di Task 9 restano verdi (la denominazione è modificabile anche nella vista fissa).
- [ ] **Step 2:** `python -m pytest tests/test_frozen_table.py -v` — atteso FAIL.
- [ ] **Step 3:** Implementare e usare nella tab Dati.
- [ ] **Step 4:** `python -m pytest tests/test_frozen_table.py tests/test_data_table_tab.py -v` — atteso PASS. **Se la selezione o la modifica regrediscono e non si risolve entro una prova ragionevole, annullare questo task**, annotare "colonne fisse: fuori scopo" nello spec e proseguire.
- [ ] **Step 5: Commit.**

### Task 11: Pacchetto, documentazione, ADR

**Files:**
- Modify: `requirements.txt` (togliere `qt-material`), `edge_agent.spec` (togliere `collect_data_files("qt_material")`, aggiungere `hiddenimports += ["PyQt6.QtSvg"]`), `CLAUDE.md` e `AGENTS.md` (righe che citano `qt-material`: UI e dipendenze), `docs/01-overview.md`, `docs/03-tech-stack.md`, `docs/09-project-anatomy.md`, `docs/10-configuration-guide.md`, `docs/adr/README.md`
- Create: `docs/adr/0033-correzioni-dell-operatore-e-tema-proprio.md` (italiano: la correzione dell'operatore vince sul consolidato, solo in memoria e perché; NDG e righe senza NDG non modificabili; tema proprio al posto di `qt-material`; Mica come extra; niente `pywinstyles`)

- [ ] **Step 1:** Applicare le modifiche sopra; nell'ADR indicare i test che lo tengono vero (`test_practice_consolidation.py`, `test_local_extraction_client.py`, `test_data_table_tab.py`).
- [ ] **Step 2:** `python -m pytest tests` — atteso tutto verde (riportare l'output reale).
- [ ] **Step 3:** Costruire con `build_exe.bat` (chiede la chiave di pacchetto o `EDGE_AGENT_PACKAGE_KEY`) e avviare `dist\EdgeAgent\EdgeAgent.exe` con `EDGE_AGENT_SMOKE=1`: atteso finestra con icone visibili e uscita dopo ~5 s. Se la macchina non regge la build, dichiararlo come **non verificato** e lasciarlo all'utente.
- [ ] **Step 4: Commit.**

### Task 12: Mica e barra del titolo (opzionale, ultimo)

**Files:**
- Create: `src/edge-agent/ui/win_effects.py`, `tests/test_win_effects.py`
- Modify: `src/edge-agent/ui/main_window.py`

**Interfaces:**
- Produces: `apply_window_effects(window: QWidget, dark: bool) -> bool` (`True` solo se ha applicato qualcosa; `ctypes` + `DwmSetWindowAttribute`: `DWMWA_SYSTEMBACKDROP_TYPE = 38` con valore Mica `2` da Windows 11 build >= 22621; `DWMWA_USE_IMMERSIVE_DARK_MODE = 20` da build >= 19041; nessuna eccezione verso l'alto).

- [ ] **Step 1: test (falliscono):** `test_effects_are_a_noop_off_windows` (`sys.platform` simulato → `False`); `test_effects_are_a_noop_on_old_windows_builds` (versione simulata); `test_constants_match_the_dwm_values`.
- [ ] **Step 2:** `python -m pytest tests/test_win_effects.py -v` — atteso FAIL.
- [ ] **Step 3:** Implementare; chiamarla da `MainWindow.showEvent` (una volta) e al cambio schema colori.
- [ ] **Step 4:** PASS. **Prima di tenerlo**, l'utente verifica con una cattura reale che i frame non cambiano; se c'è il minimo dubbio o un problema grafico, rimuovere il task senza toccare il resto.
- [ ] **Step 5: Commit.**

---

## Auto-revisione

- **Copertura spec:** obiettivi 1-2 → Task 3-4; 3 → Task 5; 4 → Task 7; 5 → Task 8 e 10; 6 → Task 1, 2, 9; 7 → contrasto/focus Task 3, scala 125-150% Task 6; 8 → Task 2 e 5. ADR e pacchetto → Task 11; extra Windows → Task 12; criteri di accettazione 1 → Task 3/5/11, 6 → Task 6.
- **Coerenza dei nomi:** `consolidate(results, corrections)`, `is_correctable`, `set_correction/clear_correction/get_corrections`, `export_workbook`, `unexported_jobs`, `session_label`, `get_column_labels/set_column_label`, `CORRECTED_ROLE` sono usati con la stessa firma in tutti i task.
- **Rischi dichiarati:** QtSvg e plugin nel pacchetto PyInstaller (Task 11 verifica); colonne fisse staccabili (Task 10); Mica staccabile (Task 12); valori dei token verificati dal test di contrasto, non assunti.
