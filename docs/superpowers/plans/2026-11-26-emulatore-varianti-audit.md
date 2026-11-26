# Emulatore BPER: quattro correzioni dall'audit delle varianti — Piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allineare l'emulatore a quattro differenze provate dall'audit: l'intestazione «Fase di recupero/Inserimento», il suffisso di «Ultima validazione» in giorni, settimane e mesi, i valori della Scheda Privati per gli autonomi, le righe di «Uscite continuative».

**Architecture:** Ogni correzione sta dove il valore nasce. Elenco Soggetti si disegna in `bper-emulator/site/detail.js`. La Scheda sintetica si genera in `bper-emulator/bper_synthetic_db.py` (schema in `bper-emulator/bper_synthetic_schema.sql`); i profili scritti a mano sono in `bper-emulator/profiles/generated-set-01.json` e `tests/fixtures/bper_profiles_list_names.json` (`generated-set-02.json` ha tutte le schede `null` e non cambia). La pagina si rende con `bper-emulator/site/scheda/index.html`, `scheda.js` e `scheda.css`. Gli stati di cattura e la loro verità vengono da `bper-emulator/bper_simulator_truth.py`. I dati della Scheda sono un oggetto JSON di valori di testo, più il booleano `details.employerRegistered`; questo piano aggiunge la lista `details.outgoings`.

**Tech Stack:** Python 3.13 (pytest), SQLite, JavaScript del browser senza build, Chrome headless e Node 24 (WebSocket e fetch integrati) per le verifiche visive.

**Spec:** `D:\audit-varianti-pef\report\RIEPILOGO.md` (fuori dal repository perché cita registrazioni reali; non contiene dati di clienti). Riga 6 della tabella delle varianti, righe S2-S4 della sezione «Scheda Privati». Revisioni cieche del piano: `D:\audit-varianti-pef\report\revisione-piano\`.

## Global Constraints

- Niente si compila sul PC del proprietario; niente `npm install`. I test Python si eseguono in locale con `.venv/Scripts/python.exe -m pytest ... -p no:cacheprovider`. I test in `tests/browser/*.cjs` e `bper-emulator/audit_truth.cjs` richiedono Playwright, che qui non c'è, e il repository non ha CI: si scrivono ma **non si eseguono**, e il resoconto finale lo dice. Le verifiche visive usano Chrome headless (sezione «Verifiche nel browser»).
- Le pratiche di `test` (ADR 0027) non guidano modifiche: nessuna prova usata qui viene da una di loro (la pratica di riferimento 51350695 è di addestramento).
- I commit li firma solo lo sviluppatore umano, senza riferimenti all'AI (AGENTS.md). I «punti di commit» si eseguono solo se l'utente lo chiede, mettendo in stage solo le parti del compito (`git add -p` dove un file contiene altro lavoro).
- Un test esistente che fissa il comportamento vecchio si cambia solo con la decisione scritta nel messaggio di commit (AGENTS.md, Test-Suite Rules 3); ogni compito elenca le funzioni di test che cambia. Un test nuovo si vede fallire prima del codice che lo fa passare.
- Ogni modifica allo schema o al seed aumenta insieme `SCHEMA_VERSION` (`bper_synthetic_db.py:22`) e `PRAGMA user_version` (`bper_synthetic_schema.sql:3`), aggiunge la nuova versione alla storia (`bper_synthetic_db.py:18-21`) e aggiunge la versione lasciata a `OLDER_VERSIONS` e al commento sopra di esso in `tests/test_bper_synthetic_db.py:425-426` e `tests/test_bper_simulator_server.py:294-295` (le versioni 4 e 5 restano fuori come oggi).
- Testo dell'interfaccia in italiano, identificatori e commenti in inglese; percorsi relativi alla radice del repository. I file JSON sono in CRLF nella copia di lavoro: si conservano fine riga, rientro (`indent=1` per i profili, `indent=2` per `reference.json`), `ensure_ascii=False` e newline finale. La nuova chiave `outgoings` va in fondo a `details`.
- Ogni commento `shortcut:` nomina il limite e quando superarlo.
- Valori osservati (verbatim): «Fase di recupero/Inserimento»; «(un giorno fa)», «(5 giorni fa)», «(6 giorni fa)», «(una settimana fa)» a 8 giorni, «(2 settimane fa)» a 13, «(4 settimane fa)» a circa 27, «(un mese fa)» oltre 4 settimane; «LAVORATORE AUTONOMO»; «USCITA CONTINUATIVA 1», colonne «DESCRIZIONE», «IMPORTO ANNUO», «SCADENZA», «DEBITO RESIDUO»; descrizioni «AFFITTO», «PRESTITO AL CONSUMO», «CESSIONE DEL QUINTO»; importi annui delle uscite in migliaia esatte.

## Decisioni dedotte

- D1. Suffisso come il tempo relativo italiano di moment.js: sotto 7 giorni i giorni, poi le settimane (`round(giorni / 7)`) fino a 4, poi i mesi (`round(giorni / 30.44)`). Prove: V20 «(6 giorni fa)» e V22 «(una settimana fa)» per lo stesso timbro (soglia 7 o 8 giorni: si sceglie 7); «(4 settimane fa)» a circa 27 giorni; V21/00423 «(un mese fa)» oltre 4 settimane. Si contano giorni di calendario da `SCHEDA_TODAY`, mentre il programma reale conta il tempo trascorso esatto. Le ore (V14/00133 «(un'ora fa)», «(20 ore fa)») e gli anni restano fuori: `ValueError` sotto 1 giorno e da 11 mesi.
- D2. Autonomi: sempre 1 mensilità. Sulla pagina web un cliente autonomo (V20/V22, lo stesso) ne mostra 1; nella vista PDF dentro PEF (S1) V33 ne mostra 1 e V13 12, ma V13 è un socio d'impresa. I mestieri autonomi dell'emulatore (titolari) sono a loro volta sostituti: «sempre 1» è un `shortcut:` da rivedere quando un mestiere da socio entra in `JOBS`. «Retribuzione annua netta» resta il reddito annuo della nota.
- D3. «NON CENSITO» compare solo se il datore di lavoro ha un nome e non è un cliente censito. Prove: V22 (autonomo, riquadro vuoto, nessuna scritta), V21/00423 e V39/00214 (NDG 0, un nome, «NON CENSITO»), V14/00133 (datore censito, nessuna scritta). Per pensionati e non lavoratori non ci sono prove: si applica la stessa regola.
- D4. Le righe delle Uscite vengono dai fatti della pratica: casa in affitto (`renting`, canone `rent`, variabili locali di `_seed_scheda`) e rata CRIF (`other_installment`, parametro, scritta nella nota PEF). Ogni fatto dà la sua riga con probabilità 2/3: nei video le righe compaiono in 9 dei circa 16 che mostrano la pagina web (un limite inferiore), e il seed ne dà a 35 schede su 64. Estrazioni su `rows = Random(80261122 + i)`, sempre quattro e in quest'ordine, presenti o no i fatti: `rows.random() < 2 / 3` per l'affitto, `rows.random() < 2 / 3` per la rata, `rows.randrange(12, 61)` mesi di durata residua, `rows.random() < 1 / 2` per la cessione del quinto. La rata è CESSIONE DEL QUINTO se il richiedente è DIPENDENTE o PENSIONE e l'ultima estrazione lo dice, altrimenti PRESTITO AL CONSUMO: la nota PEF non nomina il tipo, e la cessione del quinto esiste solo per dipendenti e pensionati. AFFITTO: importo annuo = canone × 12 arrotondato alle migliaia, scadenza e debito residuo vuoti. Rata: importo annuo = rata × 12 arrotondato alle migliaia; scadenza = mese della validazione della Scheda più la durata residua; debito residuo = rata × durata residua, arrotondato alle migliaia (`shortcut:` V32 mostra un residuo circa il 15% più basso, il capitale; da sostituire con il capitale residuo se un valore di riga diventa un campo estratto). AFFITTO viene prima, come in V23 (nella realtà l'ordine varia: V21). Arrotondamento: `(euro + 500) // 1000 * 1000`. Gli importi annui (al massimo 11.000) non possono coincidere con `importo_totale_annuo_nucleo` (0 o almeno 12.000): nessun codice per evitarlo. Il debito residuo può arrivare a 12.000-13.000: il test lo controlla. Con il seed attuale `demo` riceve due righe: i suoi stati 02+ passano a scorrimento 842 e perdono i tre campi del datore.
- D5. Gli stati 02+ della Scheda sono la pagina scorsa fino in fondo: `SCHEDA_PAGE_SCROLL = 662` è la fine della pagina senza righe (somma delle altezze di `scheda.css`: 1608 px, scorrimento massimo 663). Con n righe lo scorrimento diventa `662 + n × OUTGOING_ROW_PX`, così «SITUAZIONE FAMILIARE» resta a 435 px nella viewport e la casella della nota finisce a 893 px, come oggi. Un campo del datore resta nella verità di quegli stati solo se il suo riquadro valore è tutto nella viewport. La pagina si dichiara pronta solo se lo scorrimento ottenuto è quello richiesto.

## Alternative scartate

- D1: soglia di 26 giorni come il default di moment.js. V22 la smentisce.
- D2: estrarre 1, 1 o 12 mensilità. Il caso con 12 è un socio d'impresa, assente fra i mestieri dell'emulatore.
- D3: un nuovo flag nei dati (`employerUnregistered`) o `employerRegistered: null` quando non c'è datore. `_SCHEDA` vuole un booleano stretto e ogni profilo lo porta: cambiarne il tipo tocca validatore, profili e archivio; la condizione doppia in `data-show` resta locale alla pagina.
- D4: righe solo quando la nota della Scheda cita il fatto (la presenza dipenderebbe da quali paragrafi sono stati estratti, `bper_synthetic_db.py:510-512`); scadenza e residuo contati da `created` (una rata potrebbe scadere prima della validazione stessa); righe MUTUO e più di due righe (il dossier non ha un fatto da cui ricavarle, e per chi non ha rate la nota PEF dice «Non risultano altre rate in corso», che una riga MUTUO smentirebbe).
- D5: scorrimento fisso a 662. Con due righe la casella della nota finirebbe 128 px sotto la viewport e la verità della nota sarebbe falsa.
- `details.outgoings` facoltativa. `_shape_problems` (`bper_profiles.py:85-106`) rifiuta allo stesso modo una chiave mancante e una sconosciuta: una chiave obbligatoria con `[]` dove non nota segue la forma esistente. Conseguenza: un file di profili esterno senza `outgoings` ora viene rifiutato (il formato resta `bper-emulator-profiles/1`); il README lo dice.

## Fuori ambito

S1 (la Scheda in PDF dentro Analisi Soggetti), S5 (impaginazione fluida), S6 (professioni e abitazioni fuori catalogo), S7 (professione secondaria), le varianti 3, 4 e 7 del riepilogo, i tooltip, i suffissi in ore e anni, le righe MUTUO e più di due righe (vedi «Alternative scartate»), la versione dello schema nei manifest delle catture e delle registrazioni (tocca gli script di cattura), la correzione dell'allineatore (Review Focus 8).

## Verifiche nel browser

- **Chrome:** ogni avvio usa `--headless=new --disable-gpu --force-device-scale-factor=1 --user-data-dir=<cartella temporanea nuova>`, come `measure_scheda.py` e `measure_fidelity.py`: senza un profilo separato l'avvio può finire nel Chrome aperto dell'utente, e Chrome recente rifiuta `--remote-debugging-port` sul profilo predefinito.
- **Elenco Soggetti (Task 1).** Una pagina HTML statica in `D:\claude-tmp\` carica, con percorsi `file:///` assoluti, `bper-emulator/site/detail.css`, `pef-extra.css`, `pef-extra.js` e `detail.js`; uno script in linea fa come `openAlone` (`tests/browser/bper_pef_pages.cjs:42-60`): `BperDetail.render`, `BperDetail.show(4)`, scrive i testi dei `th`, poi un clic su `[data-group="IST"]` e su `[data-nav="IST.soggetti"]` e riscrive i `th`, il tutto in un `<pre>`. Si legge con `chrome ... --allow-file-access-from-files --virtual-time-budget=3000 --dump-dom <file>`. Inoltre `.venv/Scripts/python.exe bper-emulator/measure_fidelity.py --out <cartella nuova> --steps 4`.
- **Scheda Privati (Task 3 e 4).** Server: `.venv/Scripts/python.exe bper-emulator/serve_bper_simulator.py --db D:/claude-tmp/<sessione>/verifica-<task>.sqlite3 --port <porta>`, con un database nuovo a ogni giro (così quello predefinito non viene toccato). Uno script Node usa e getta in `D:\claude-tmp\`, `cdp-eval.cjs <url> <espressione>`: avvia Chrome con `--remote-debugging-port=<porta>` e `--window-size=1920,945` (la finestra di cattura, audit e `measure_scheda.py`), trova la pagina in `/json/list`, la porta all'URL, aspetta `document.body.dataset.ready === "true"` (o, per la verifica del Task 4 Step 6, che compaia `scrollMismatch`), valuta l'espressione e stampa il risultato JSON. URL: `/schede/SchedaPrivati/?scroll=<px>&noteScroll=<px>#/schede/<ndg>/<schedaId>`, con NDG e id presi da `/api/practices.json`. Le posizioni si misurano rispetto al rettangolo di `.sp-main`. Le pratiche si scelgono così, nell'ordine di `/api/practices.json`: il primo autonomo (`tipo_contratto == "LAVORATORE AUTONOMO"`), il primo dipendente con `employerNdg == "0"`, la prima scheda con 0, con 1 e con 2 righe (con il seed attuale: sim-002, `demo`, sim-002, sim-003, `demo`).
- **Regressione della Scheda di riferimento.** `.venv/Scripts/python.exe bper-emulator/measure_scheda.py --out <cartella nuova>` al Task 0 e dopo i Task 3 e 4, ogni volta in una cartella nuova (una cartella riusata contiene un database della versione vecchia e il controllo si ferma): le cinque righe stampate restano identiche.
- **Non coperto da controlli eseguiti:** l'export offline, dove `bper-emulator/site/app.js:34-38` scrive la pagina della Scheda con `document.write` (ora con il `<template>`); lo esercitano `audit_truth.cjs` e `captureScheda` di `capture_bper_dataset.cjs`, entrambi con Playwright.

## Review Focus

1. Una scheda sintetica con una riga nelle Uscite: lo stato 02 non deve dire «visibile» un campo del datore uscito in alto. Test in Task 4 (`test_bottom_states_drop_the_employer_fields_the_rows_push_out`, con insiemi di campi scritti per n = 0, 1, 2).
2. Un'altezza di riga sbagliata o una riga non disegnata: il browser ferma lo scorrimento senza errore. La pagina non si dichiara pronta se lo scorrimento differisce da quello richiesto (Task 4 Step 6), così cattura e audit falliscono; test sul foglio di stile (`test_outgoing_row_geometry_matches_the_frozen_stylesheet`) e verifica del Task 4 Step 11.
3. Un profilo scritto a mano senza `outgoings`: il validatore lo rifiuta e `--profiles` non parte. Test in Task 4 (`test_profiles_without_outgoings_are_rejected`) e aggiornamento di `generated-set-01.json` e della fixture.
4. Un autonomo con 1 mensilità: l'annuo calcolato come rata × mensilità crollerebbe a un dodicesimo e smentirebbe la nota. Test in Task 3 (`test_self_employed_annual_income_is_the_note_income`), visto fallire a metà dello Step 3.
5. Un database locale di versione 6 o 7: va messo da parte e ricostruito. Test esistenti di aggiornamento, con 6 e 7 aggiunti a `OLDER_VERSIONS` (Task 3 e 4).
6. La verità della Scheda si controlla davvero solo con `audit_truth.cjs`, che qui non gira: le verifiche con Chrome headless di Task 4 sono l'unico controllo della geometria eseguito e fanno da criterio di accettazione.
7. Dati già prodotti dall'emulatore con la versione 6 o precedente (catture di `capture_bper_dataset.cjs`; le 10.403 righe dell'emulatore usate per il riconoscitore OCR del commit `7be7234`, `models/README.md:22`): ogni campione resta coerente con la propria verità, ma ha i formati vecchi e non si distingue dai nuovi. È uno scarto di distribuzione, non un'etichetta sbagliata (i dati LiLT vengono solo da `data/dataset`): rigenerarli prima del prossimo addestramento è consigliato, non obbligatorio; il resoconto finale lo dice.
8. L'allineatore di addestramento (`src/training/alignment.py:27-33, 330-334, 583-585`) cerca l'etichetta di `importo_totale_annuo_nucleo` come prima parola che inizia per «importo»: con le righe in vista viene prima «IMPORTO ANNUO» e il campo resterebbe non risolto. Oggi nessuno stato della Scheda dell'emulatore arriva all'allineatore (`live_simple.py:79-82`, LiLT solo sull'archivio); una futura Scheda reale con righe sì. Si segnala, la correzione è fuori ambito.

---

### Task 0: punto di partenza

- [ ] **Step 1:** `.venv/Scripts/python.exe -m pytest tests -m "not slow" -q -p no:cacheprovider`; si annotano passati e falliti come riferimento (la copia di lavoro contiene altro lavoro non committato). Riferimento parziale già misurato: i 297 casi di `test_bper_synthetic_db.py`, `test_bper_generated_profiles.py`, `test_bper_profiles.py`, `test_bper_simulator_truth.py`, `test_bper_archive.py`, `test_bper_simulator_export.py`, `test_bper_simulator_server.py`, `test_bper_capture_pack.py` passano.
- [ ] **Step 2:** `.venv/Scripts/python.exe bper-emulator/measure_scheda.py --out D:/claude-tmp/<sessione>/scheda-prima` e `.venv/Scripts/python.exe bper-emulator/measure_fidelity.py --out D:/claude-tmp/<sessione>/fedelta-prima --steps 4`; si salvano le righe stampate.
- [ ] **Step 3: Punto di commit, solo se l'utente vuole i commit** — un commit con le sole colonne CR già nella copia di lavoro (`bper-emulator/site/detail.js`, `tests/browser/bper_pef_pages.cjs`, la frase sulle colonne CR di `bper-emulator/README.md`), messaggio «Add the CR Obbligatoria and CR Presente columns to Elenco Soggetti opened from Istruttoria».

### Task 1: «Fase di recupero/Inserimento» con la I maiuscola

**Files:**
- Modify: `bper-emulator/site/detail.js:164` (array `headers` di `subjectsPanel`)
- Modify (test): `tests/browser/bper_pef_pages.cjs:264` (costante `EIGHT`; `TEN` ne deriva)

**Interfaces:**
- Consumes: nulla.
- Produces: l'intestazione `"Fase di recupero/Inserimento"` nelle varianti a 8 e a 10 colonne.

- [ ] **Step 1: Cambia l'atteso** — in `EIGHT`, `'Fase di recupero/inserimento'` diventa `'Fase di recupero/Inserimento'`.
- [ ] **Step 2: Verifica che fallisca** — test browser non eseguibile; la pagina di verifica stampa ancora `Fase di recupero/inserimento` in entrambe le varianti.
- [ ] **Step 3: Implementa** — in `detail.js` la stringa diventa `"Fase di recupero/Inserimento"`.
- [ ] **Step 4: Verifica** — la pagina stampa `Fase di recupero/Inserimento` nelle due varianti; `measure_fidelity.py --out <cartella nuova> --steps 4` dà per lo step 4 `blur|diff|` e `px>24` non più alti del Task 0; la corsa pytest del Task 0 dà lo stesso risultato.
- [ ] **Step 5: Punto di commit** — `bper-emulator/site/detail.js`, `tests/browser/bper_pef_pages.cjs`; «Write Inserimento with a capital I in the Elenco Soggetti header, as on every real screenshot».

### Task 2: suffisso di «Ultima validazione» in giorni, settimane e mesi

Il suffisso si calcola alla lettura (`_scheda`), non si salva: niente cambio di versione.

**Files:**
- Modify: `bper-emulator/bper_synthetic_db.py:137` (commento sopra `SCHEDA_TODAY`) e `:666-667` (`_scheda`)
- Modify: `bper-emulator/profiles/generated-set-01.json` (26 schede con 7 giorni o più), `tests/fixtures/bper_profiles_list_names.json` (2 schede a 18 giorni)
- Modify (test): `tests/test_bper_synthetic_db.py:14-17` (import), `:190`, `:252-256`; `tests/test_bper_generated_profiles.py:19-22` (import), `:48`, `:536-541`

**Interfaces:**
- Consumes: `SCHEDA_TODAY` (`bper_synthetic_db.py:138`).
- Produces: `validation_age(days: int) -> str` in `bper_synthetic_db.py`, pubblica. `ValueError` per `days < 1` o da 11 mesi (`round(days / 30.44) >= 11`).

- [ ] **Step 1: Scrivi il test che fallisce** — in `tests/test_bper_synthetic_db.py` (importa `validation_age`):

```python
def test_validation_age_counts_days_then_weeks_then_months() -> None:
    observed = {1: "un giorno fa", 5: "5 giorni fa", 6: "6 giorni fa", 8: "una settimana fa", 13: "2 settimane fa",
                27: "4 settimane fa"}
    inferred = {2: "2 giorni fa", 7: "una settimana fa", 10: "una settimana fa", 11: "2 settimane fa",
                25: "4 settimane fa", 31: "4 settimane fa", 32: "un mese fa", 61: "2 mesi fa"}
    assert {d: validation_age(d) for d in {**observed, **inferred}} == {**observed, **inferred}
    for days in (0, 335):
        with pytest.raises(ValueError):
            validation_age(days)
```

- [ ] **Step 2: Verifica che fallisca** — `.venv/Scripts/python.exe -m pytest tests/test_bper_synthetic_db.py::test_validation_age_counts_days_then_weeks_then_months -q -p no:cacheprovider` → ImportError su `validation_age`.
- [ ] **Step 3: Implementa** `validation_age(days: int) -> str` secondo D1 («un giorno fa», «N giorni fa», «una settimana fa», «N settimane fa», «un mese fa», «N mesi fa»), con il commento `shortcut: counts calendar days from SCHEDA_TODAY while the real page counts elapsed time, and has no hours or years; extend when a recording shows a stamp under a day or over ten months`. In `_scheda`: `days = (SCHEDA_TODAY - validated.date()).days` e `stamp = f"{validated:%d/%m/%Y %H:%M} ({validation_age(days)})"`. Il commento sopra `SCHEDA_TODAY` dice «the relative suffix of the validation stamp counts from it».
- [ ] **Step 4: Aggiorna i test che fissavano «N giorni fa»** (tre funzioni) —
  - `test_scheda_follows_the_structure_and_formats_of_the_reference_page`, riga `:190`: `re.fullmatch(r"(\d\d/\d\d/\d{4}) \d\d:\d\d \((.+ fa)\)", ...)`; il gruppo 2 vale `validation_age((SCHEDA_TODAY - day(gruppo 1)).days)`.
  - `test_scheda_dates_are_ordered_inside_the_practice_life`, righe `:252-256`: stessa regex; l'asserzione di `:256` diventa `2 <= (SCHEDA_TODAY - validated).days <= 25` e `suffisso == validation_age((SCHEDA_TODAY - validated).days)`.
  - `test_bper_generated_profiles.py:48`: `STAMP = re.compile(r"(\d\d/\d\d/\d{4}) (\d\d):(\d\d) \((.+ fa)\)")` (importa `validation_age`); `test_the_validation_stamp_counts_the_days_to_the_viewing_day` confronta il gruppo 4 con `validation_age((SCHEDA_TODAY - _day(gruppo 1)).days)`.
- [ ] **Step 5: Riscrivi i profili** — script usa e getta fuori dal repository: per ogni scheda ricalcola il suffisso di `fields.ultima_validazione_scheda` e `lastChange.when` con `validation_age` e la data del timbro, e riscrive il file secondo i vincoli globali. Atteso: 26 schede e 52 righe cambiate in `generated-set-01.json`, 2 schede e 4 righe nella fixture; `git diff --word-diff` mostra solo suffissi.
- [ ] **Step 6: Verifica** — il test nuovo e quelli riscritti passano; la corsa pytest del Task 0 dà lo stesso risultato.
- [ ] **Step 7: Punto di commit** — «Write the Scheda validation age in days, weeks and months as the real page does (recordings V20/V22, V21, V25, V39, V41). Three stamp tests now check the shared rule validation_age instead of the old "N giorni fa" form; the hand-written profiles are rewritten with it».

### Task 3: autonomi nella Scheda Privati

**Files:**
- Modify: `bper-emulator/bper_synthetic_schema.sql:3` (`user_version = 7`), `:109` (`payments`), `:129-130` (vincolo e commento)
- Modify: `bper-emulator/bper_synthetic_db.py:18-22` (storia: «7 the autonomous contract and one payment for the self-employed»; `SCHEMA_VERSION = 7`), `:146-159` (commenti di `JOBS` e del pensionato, `:159` dice ancora «NON CENSITO»), `:150-155` (`JOBS`: mensilità `(1,)` per AUTONOMO), `:433-436` (ramo AUTONOMO: contratto), `:517-518` (annuo e contratto nell'INSERT)
- Modify: `bper-emulator/site/scheda/index.html:69`, `bper-emulator/site/scheda/scheda.js` (`render` e commento in testa, `:4` e `:15`)
- Modify: `bper-emulator/profiles/generated-set-01.json` (autonomi gen-003, 008, 014, 020, 024, 030, 034), `tests/fixtures/bper_profiles_list_names.json` (fittizia-sotto, fittizia-sopra)
- Modify (test): `tests/test_bper_synthetic_db.py:196`, `:201-214`, `:266-293` (anche il commento `:273`), `:425-426`; `tests/test_bper_simulator_server.py:294-295`; `tests/test_bper_generated_profiles.py:444-466`
- Create: `tests/browser/bper_scheda.cjs` (oggi nessun test browser verifica come la Scheda si rende; stesso schema di `bper_pef_pages.cjs`: server a `BPER_TEST_URL`, Playwright da `PLAYWRIGHT_MODULE`)

**Interfaces:**
- Consumes: nulla.
- Produces: per AUTONOMO `fields.tipo_contratto == "LAVORATORE AUTONOMO"` e `fields.numero_mensilita == "1"`; `data-show` accetta più condizioni separate da spazio, tutte vere, ciascuna `path` o `!path`.

- [ ] **Step 1: Scrivi i test nuovi** — in `tests/test_bper_synthetic_db.py` (importa `JOBS`); qui una scheda sintetica è autonoma se `professione_principale` è in `{job[1] for job in JOBS if job[0] == "AUTONOMO"}`:
  - `test_self_employed_schede_carry_the_autonomous_contract_and_one_payment`: ogni scheda autonoma ha `tipo_contratto == "LAVORATORE AUTONOMO"` e `numero_mensilita == "1"`; ne esiste almeno una.
  - `test_self_employed_annual_income_is_the_note_income`: per le schede autonome la cui nota contiene `€ ([\d.]+) netti annui`, l'importo è uguale a `retribuzione_annua_netta`; almeno una nota lo contiene.
- [ ] **Step 2: Verifica** — il primo fallisce (`""`, `"12"`); il secondo passa ancora (lo si vede fallire allo Step 3b).
- [ ] **Step 3a: Implementa schema e mensilità** —
  - Schema: `payments INTEGER NOT NULL CHECK(payments BETWEEN 12 AND 14 OR (payments = 1 AND income_kind = 'AUTONOMO'))`; il vincolo a `:129-130` diventa `CHECK(income_kind != 'AUTONOMO' OR (employer_id IS NULL AND contract = 'LAVORATORE AUTONOMO'))` e `CHECK(income_kind != 'PENSIONE' OR (employer_id IS NULL AND contract = ''))`; gli altri tipi restano liberi (`test_bper_synthetic_db.py:349-353` sposta un pensionato su ALTRO). Il commento lo dice.
  - Generatore: AUTONOMO con mensilità `(1,)` (una sola estrazione, come oggi) e contratto `"LAVORATORE AUTONOMO"`, con la formula dell'annuo **ancora** `applicant * payments * 100`.
- [ ] **Step 3b: Verifica che la protezione fallisca** — `test_self_employed_annual_income_is_the_note_income` ora fallisce (l'annuo vale un mese).
- [ ] **Step 3c: Implementa l'annuo** — `net_annual_cents = applicant * (12 if income_kind == "AUTONOMO" else payments) * 100`; la protezione passa. Versione 7 secondo i vincoli globali; `OLDER_VERSIONS` diventa `(1, 2, 3, 6)` nei due file di test, e il commento sopra aggiunge «6: without the autonomous contract and the one-payment self-employed». Commenti che diventano falsi: `JOBS` e il pensionato (`:146-159`); `scheda.js:15`.
- [ ] **Step 4: Aggiorna i test esistenti** (cinque funzioni; la decisione di ciascuna va nel commit) —
  - `test_scheda_follows_the_structure_and_formats_of_the_reference_page`, riga `:196`: l'insieme ammesso è `{"12", "13", "14"}`, più `"1"` quando la professione è autonoma (predicato dello Step 1).
  - `test_scheda_income_matches_the_monthly_income_quoted_in_the_practice_note` (`:201-214`): `divisor = 12 if f["numero_mensilita"] == "1" else payments`, usato in **tutte** le asserzioni (`annual % divisor == 0`, ramo del richiedente e ramo dei cointestatari, dove sim-004 è un artigiano cointestato).
  - `test_employer_box_follows_the_employment_in_the_practice_note` (`:266-293`): per «attività» il trio atteso è `("", "", "LAVORATORE AUTONOMO")` e la mensilità `"1"`; per «pensionato» resta `("", "", "")` e `"13"`; il commento `:273` lo dice; l'insieme finale dei contratti guadagna `"LAVORATORE AUTONOMO"`.
  - `test_the_scheda_fields_agree_with_the_applicant_employment` (`test_bper_generated_profiles.py:444-462`, il predicato resta `_employment(p)[1]` con `SELF_EMPLOYED`, che comprende AGENTE DI COMMERCIO): `boxless` non chiede più il contratto vuoto; «lavoratore autonomo» chiede `tipo_contratto == "LAVORATORE AUTONOMO"` e `numero_mensilita == "1"`; «pensionato» e «senza datore di lavoro» chiedono il contratto vuoto.
  - `test_scheda_payments_are_twelve_to_fourteen` (`:465-466`) diventa `test_scheda_payments_are_one_for_the_self_employed_else_twelve_to_fourteen`: `"1"` se `_employment(p)[1] == "lavoratore autonomo"`, altrimenti 12-14.
- [ ] **Step 5: «NON CENSITO» solo con un nome** — in `bper_scheda.cjs`, `the NON CENSITO mark needs a named employer` (non eseguibile qui): per il primo autonomo `.sp-census` non è visibile, per il primo dipendente con NDG `"0"` lo è. In `scheda.js` `render` divide `data-show` per spazi e mostra il nodo solo se ogni condizione è vera; il commento in testa dice che «NON CENSITO» richiede un datore con nome e non censito, e che i valori sono testo più un booleano (e, dal Task 4, una lista). In `index.html:69`: `data-show="fields.datore_di_lavoro_anagrafica !details.employerRegistered"`. Verifica con `cdp-eval.cjs`: `getComputedStyle(document.querySelector('.sp-census')).display` è `none` per l'autonomo e non lo è per il dipendente.
- [ ] **Step 6: Aggiorna i profili** — nei 7 autonomi di `generated-set-01.json` e nei 2 della fixture: `tipo_contratto` «LAVORATORE AUTONOMO», `numero_mensilita` «1»; stessa formattazione del Task 2.
- [ ] **Step 7: Verifica** — corsa pytest del Task 0 con lo stesso risultato (più i test nuovi); `measure_scheda.py --out <cartella nuova>` con le cinque righe del Task 0.
- [ ] **Step 8: Punto di commit** — messaggio con D2, D3, le prove (V20/V22, V21/00423, V39/00214, V14/00133) e le cinque funzioni di test cambiate, ciascuna con il motivo.

### Task 4: righe di «Uscite continuative»

**Files:**
- Modify: `bper-emulator/bper_synthetic_schema.sql` (`user_version = 8`, tabella `scheda_outgoing`)
- Modify: `bper-emulator/bper_synthetic_db.py` (storia: «8 the outgoing rows of the Scheda»; `SCHEMA_VERSION = 8`, `_seed_scheda`, `_scheda`)
- Modify: `bper-emulator/bper_profiles.py:63-64` (forma), `bper-emulator/bper_archive.py:184-186` (`"outgoings": []`), `bper-emulator/site/scheda/reference.json` (`"outgoings": []`)
- Modify: `bper-emulator/profiles/generated-set-01.json` e `tests/fixtures/bper_profiles_list_names.json` (`"outgoings": []` in fondo a ogni `details`)
- Modify: `bper-emulator/site/scheda/index.html:87`, `bper-emulator/site/scheda/scheda.js`, `bper-emulator/site/scheda/scheda.css`
- Modify: `bper-emulator/bper_simulator_truth.py:29-36` (costanti), `_scheda_captures`, docstring di `scheda_states` (`:198-200`)
- Modify (test): `tests/test_bper_synthetic_db.py`, `tests/test_bper_profiles.py`, `tests/test_bper_simulator_truth.py` (anche `scheda_with()` a `:42-53`), `tests/test_bper_synthetic_db.py:425-426`, `tests/test_bper_simulator_server.py:294-295`, `tests/browser/bper_scheda.cjs`, `tests/browser/bper_truth_audit.cjs:43-47`

**Interfaces:**
- Consumes: `_money`, `_month`, `_iso_month`, `_month_index`, `EMPTY_MONTH` di `bper_synthetic_db.py`; in `_seed_scheda` il parametro `other_installment`, le locali `income_kind`, `renting`, `rent` e `validated` (`:472-479`).
- Produces: `details.outgoings: list[{"description": str, "annualAmount": str, "due": str, "residual": str}]` in ogni scheda (lista vuota dove non nota); in `bper_simulator_truth.py`, `OUTGOING_ROW_PX: int = 90` ed `EMPLOYER_TOP_PX: dict[str, int]` con le chiavi `datore_di_lavoro_anagrafica`, `rating_ufficiale`, `score_cgs`.

- [ ] **Step 1: Scrivi i test che falliscono (dati)** — in `tests/test_bper_synthetic_db.py` (importa `_money`; un aiuto `arrotonda(euro) = (euro + 500) // 1000 * 1000`), `test_outgoings_follow_the_rent_and_the_crif_instalment_of_the_practice`: per ogni scheda sintetica, con `anchor` il mese della data del timbro di validazione:
  - ogni riga AFFITTO ha `housing == "AFFITTO"`, `annualAmount` in migliaia esatte (`re.fullmatch(r"\d{1,3}(\.000)+", ...)`), `due == EMPTY_MONTH` e `residual == ""`; se la nota della Scheda cita il canone (`canone mensile (?:di )?€ (\d+)`), `annualAmount == _money(arrotonda(X * 12) * 100)`;
  - ogni riga di rata ha nella nota PEF «Altra rata in corso di X,00 € mensili», `annualAmount == _money(arrotonda(X * 12) * 100)`, `due` un mese fra 12 e 60 mesi dopo `anchor`, `residual == _money(arrotonda(X * mesi) * 100)` con `mesi` da `anchor` a `due`; la descrizione è PRESTITO AL CONSUMO, oppure CESSIONE DEL QUINTO solo se `tipo_contratto` non è «LAVORATORE AUTONOMO» (dipendente o pensionato);
  - AFFITTO viene prima; nessun'altra riga; né `annualAmount` né `residual` di una riga sono uguali a `importo_totale_annuo_nucleo` o a `retribuzione_annua_netta` della stessa scheda;
  - nel seed esistono almeno una scheda con due righe, una con una sola, un fatto senza riga, una riga AFFITTO con il canone citato, una PRESTITO AL CONSUMO e una CESSIONE DEL QUINTO.
  In `tests/test_bper_profiles.py`, `test_profiles_without_outgoings_are_rejected`: togliere `details.outgoings` da una scheda valida produce `scheda.details.outgoings: mancante`.
- [ ] **Step 2: Verifica che falliscano** — chiave assente.
- [ ] **Step 3: Implementa i dati** —
  - Tabella `scheda_outgoing(ndg TEXT NOT NULL REFERENCES scheda(ndg), n INTEGER NOT NULL CHECK(n BETWEEN 1 AND 2), description TEXT NOT NULL CHECK(description IN ('AFFITTO', 'PRESTITO AL CONSUMO', 'CESSIONE DEL QUINTO')), annual_cents INTEGER NOT NULL CHECK(annual_cents > 0 AND annual_cents % 100000 = 0), due TEXT CHECK(due IS NULL OR due GLOB '[12][0-9][0-9][0-9]-[01][0-9]'), residual_cents INTEGER CHECK(residual_cents IS NULL OR residual_cents % 100000 = 0), CHECK((description = 'AFFITTO') = (due IS NULL AND residual_cents IS NULL)), PRIMARY KEY (ndg, n))`.
  - In `_seed_scheda`, dopo l'INSERT della scheda, le righe secondo D4 (le quattro estrazioni di `Random(80261122 + i)` nell'ordine dato; le altre estrazioni non cambiano). Scadenza: `_iso_month(_month_index(validated) + durata)`.
  - `_scheda` legge le righe in ordine di `n`: `annualAmount = _money(annual_cents)`, `due = _month(due)` (`EMPTY_MONTH` se nullo), `residual = _money(residual_cents)` o `""`.
  - Forma in `bper_profiles._SCHEDA["details"]`; `[]` in `bper_archive.py`, `reference.json`, profili e fixture.
  - Versione 8 secondo i vincoli globali; `OLDER_VERSIONS` diventa `(1, 2, 3, 6, 7)`, il commento aggiunge «7: without the outgoing rows».
- [ ] **Step 4: Scrivi il test del foglio di stile** — in `tests/test_bper_simulator_truth.py`, `test_outgoing_row_geometry_matches_the_frozen_stylesheet`, sullo schema di `test_note_box_geometry_matches_the_frozen_stylesheet`: la regola trovata da `\.sp-outgoing \{([^}]*)\}` contiene `height: {OUTGOING_ROW_PX}px;`; in quella regola e in quella di `\.sp-outgoings \{([^}]*)\}` ogni dichiarazione `margin` o `padding` vale 0. Fallisce: regole assenti.
- [ ] **Step 5: Rendi le righe** —
  - `index.html`, dentro `#uscite` dopo l'`h2`: `<div class="sp-outgoings"></div>` e `<template id="sp-outgoing">` con `<div class="sp-outgoing"><h4></h4><div class="sp-grid">` e quattro `label.sp-field` (`span` + `input readonly`): DESCRIZIONE con la classe `sp-choice`, IMPORTO ANNUO, SCADENZA, DEBITO RESIDUO.
  - `scheda.css`: `.sp-outgoings { margin: 0; padding: 0; }`, `.sp-outgoing { box-sizing: border-box; height: 90px; overflow: hidden; }`, `.sp-outgoing > h4 { height: 26px; margin: 0; padding-top: 10px; color: #979797; font: bold 13.4px/16px "Segoe UI", sans-serif; }`, `.sp-outgoing > .sp-grid { grid-template-columns: 4fr 3fr 3fr 3fr; grid-auto-rows: 64px; }`, con il commento `shortcut: row pitch (89-92 px) and column proportions come from recordings of narrower, fluid windows; this changes fidelity only, the truth follows OUTGOING_ROW_PX; re-measure when a 1903 px screenshot shows rows`.
  - `scheda.js`, in `render` prima del ciclo `[data-bind]`: per ogni elemento di `details.outgoings` clona il template, scrive «USCITA CONTINUATIVA n» nell'`h4` e i quattro valori negli `input`, nell'ordine della lista; il commento in testa descrive `details.outgoings`.
  - In `bper_scheda.cjs`, `the outgoing rows render under USCITE CONTINUATIVE` (non eseguibile qui): la prima scheda con due righe mostra due titoli e otto valori; la prima senza righe nessun `.sp-outgoing`.
  - Il test dello Step 4 passa; verifica con `cdp-eval.cjs`: due `.sp-outgoing` alti 90 px nella scheda con due righe, nessuno in quella senza.
- [ ] **Step 6: Pronta solo con lo scorrimento giusto** — in `bper_scheda.cjs`, `a scroll the page cannot reach leaves the page not ready` (non eseguibile qui): con `?scroll=5000` `document.body.dataset.ready` resta assente e `scrollMismatch` vale `5000/<fine pagina>`. In `scheda.js`, dopo gli scorrimenti richiesti: `ready = "true"` solo se `.sp-main.scrollTop` e lo `scrollTop` della casella della nota distano al più 1 px da `?scroll=` e `?noteScroll=` (quando presenti); altrimenti `document.body.dataset.scrollMismatch = "<richiesto>/<ottenuto>"` e nessun `ready`. `capture_bper_dataset.cjs:65` e `audit_truth.cjs:256` aspettano `ready === 'true'`, quindi uno stato sbagliato fa fallire la cattura invece di etichettarla male. Verifica con `cdp-eval.cjs` su `?scroll=5000`. Se uno stato esistente non diventa pronto, ci si ferma e si segnala: è un errore di verità che c'era già.
- [ ] **Step 7: Misura e fissa `EMPLOYER_TOP_PX`** — con `cdp-eval.cjs` a scorrimento 662 sulla prima scheda senza righe: il bordo superiore di ciascuno dei tre `input` meno il bordo superiore di `.sp-main`, arrotondato all'intero. Atteso dalle altezze di `scheda.css`: ANAGRAFICA 18, RATING 150, CRIBIS 147, ±2 px; un valore diverso si ferma e si segnala. Un commento in `bper_simulator_truth.py` dice come è stato misurato.
- [ ] **Step 8: Scrivi il test che fallisce (stati)** — in `tests/test_bper_simulator_truth.py`, `scheda_with()` porta `details` con `outgoings` (vuota per default, un parametro `outgoings`); poi `test_bottom_states_drop_the_employer_fields_the_rows_push_out`: con 0, 1 e 2 righe gli stati 02+ hanno `scroll == 662`, `752` e `842`, e i campi del datore nella loro verità sono, scritti per esteso, `{datore_di_lavoro_anagrafica, rating_ufficiale, score_cgs}`, `{rating_ufficiale, score_cgs}` e nessuno; con 0 righe stati e verità sono quelli di oggi.
- [ ] **Step 9: Implementa gli stati** — `_scheda_captures` legge `scheda["details"]["outgoings"]`, sposta lo scorrimento di `n × OUTGOING_ROW_PX` e tiene un campo del datore solo se `EMPLOYER_TOP_PX[campo] - n × OUTGOING_ROW_PX >= 0`; la docstring di `scheda_states` lo dice.
- [ ] **Step 10: Audit della verità (in sospeso)** — in `tests/browser/bper_truth_audit.cjs:43-47` l'insieme controllato aggiunge, scelte per proprietà come il pensionato, la prima pratica con due righe (`outgoings.length === 2`) e il primo autonomo (`tipo_contratto === 'LAVORATORE AUTONOMO'`); con il seed attuale sono `demo`, già presente, e sim-002. `audit_truth.cjs --all` con 0 violazioni resta da eseguire: si potrà quando ci sarà Playwright, o un sostituto via `PLAYWRIGHT_MODULE` (`test_bper_capture_pack.py:89` ne usa uno finto).
- [ ] **Step 11: Verifica (criterio di accettazione del Task 4)** — corsa pytest del Task 0 con lo stesso risultato (più i test nuovi); `measure_scheda.py --out <cartella nuova>` con le cinque righe del Task 0. Con `cdp-eval.cjs`, sulle prime schede con 0, 1 e 2 righe allo scorrimento dello stato 02: la pagina è pronta; `.sp-main.scrollTop` è uguale al valore richiesto e dista al più 1 px da `scrollHeight - clientHeight`; «SITUAZIONE FAMILIARE» è a 435 px e la casella della nota finisce a 893 px nella viewport (±2 px); per ciascun campo del datore, essere interamente nella viewport coincide con l'essere nella verità dello stato.
- [ ] **Step 12: Punto di commit** — messaggio con D4, D5 e le prove (V17, V21, V23, V32; l'archivio per l'assenza di righe).

### Task 5: documentazione e verifica finale

**Files:**
- Modify: `bper-emulator/README.md` (riga 5: «(dipendenti e pensionati; lo schema accetta anche gli autonomi)» non è più vero; paragrafo della Scheda Privati e «Limiti noti»: righe delle Uscite, autonomi, suffisso, schema versione 8 al posto del vecchio «ora 4», `outgoings` obbligatoria nei file di profili)

- [ ] **Step 1:** aggiorna il testo, senza nomi né dati di pratiche reali.
- [ ] **Step 2: Verifica finale** — `.venv/Scripts/python.exe -m pytest tests -m "not slow" -q -p no:cacheprovider`; il risultato si riporta così com'è, confrontato con il Task 0. I casi esclusi da `-m "not slow"` sono quelli del classificatore DINOv2, che questo piano non tocca. I test browser, `audit_truth.cjs` e l'export offline restano dichiarati non verificati.
- [ ] **Step 3: Resoconto** — dice che `demo` ha ora due righe (stati 02+ a 842, senza campi del datore) e che rigenerare i dati già ricavati dall'emulatore (Review Focus 7) è consigliato prima del prossimo addestramento.
- [ ] **Step 4: Punto di commit** — `bper-emulator/README.md` (solo le parti di questo piano, `git add -p`); «Document the Scheda outgoing rows, the self-employed values and the validation age».
