#### Prova dal vivo dell'edge-agent sull'emulatore

`bper-emulator/live_test.py` fa girare il **vero** percorso di cattura dell'edge-agent contro l'emulatore: il vero
`BPERCaptureWorker` (con `frame_normalize`, `preprocess_for_ocr`, dedup pHash e `StabilityTracker`), il vero
classificatore DINOv2 (router `ml`, nessun LLM) e il vero registro pagine, dentro una `QCoreApplication` senza
finestre. Un "operatore" scritto (`bper-emulator/live_driver.cjs`, Chrome DevTools Protocol, solo eventi di input
CDP: mouse e tastiera del sistema non vengono toccati) apre le pratiche dall'interfaccia vera (Home → Ricerca
Pratica → Elenco → menu a tre puntini → pratica), visita Soggetti, Fidi e Garanzie con i tooltip, la Nota, gli stati
della lista, cambia pratica e ridimensiona la finestra. Mentre lavora registra con data e ora che cosa mostra la
pagina (lo stato letto dal DOM): è la verità con cui si giudica ciò che l'agente ha adottato.

Tre modi:

| Modo | Che cosa cattura | Costo | Finestra visibile |
|---|---|---|---|
| `record` | Chrome senza interfaccia gioca lo scenario e salva la vista a ogni cambiamento | nessuno | no |
| `replay` | una registrazione incollata in un desktop 1920 × 1080, servita al worker a 3 fps su orologio virtuale (`--realtime`: all'orologio vero, con i ritardi reali del worker; `--desktop-image FILE`: quell'immagine affiancata dietro la finestra al posto di un desktop uniforme) | nessuno | no |
| `live` | il monitor vero con `mss`, mentre Chrome con interfaccia gioca lo scenario | nessuno (con `--extract` sì) | **sì, 1-2 minuti** |

```powershell
# registrazione e riproduzione (senza finestre, ripetibili)
python bper-emulator/live_test.py record --scenario bper-emulator/live_scenarios/matrix.json --geometry wide --out runs/matrix-wide --db D:/tmp/emulatore.sqlite3
python bper-emulator/live_test.py replay --recording runs/matrix-wide --out runs/matrix-wide-report

# dal vivo (Windows): prende il monitor principale
python bper-emulator/live_test.py live --scenario bper-emulator/live_scenarios/careful-wide.json --out runs/live-1 --db D:/tmp/emulatore.sqlite3
```

Ogni comando avvia **il proprio** server dell'emulatore su una porta libera (`--port 0`, mai la 8765 del simulatore
dell'utente), con il database indicato da `--db` (predefinito `.tritech/local/bper-live-test.sqlite3`), e lo ferma alla
fine. `--profiles FILE` aggiunge un file di profili; gli scenari che usano le pratiche `gen-*` lo dichiarano già.

**Geometrie** (`--geometry` sostituisce quella dello scenario): `reference` è la finestra degli screenshot di
riferimento, 1280 × 1025 a zoom 110% (poi ridotti a 848 × 679; vista CSS 1149 px); `wide` è quella che mostra la
maggior parte dell'archivio reale, 1912 × 1030 a zoom 90% (vista CSS 2106 px); `maximized` è una finestra
massimizzata a zoom 90%, solo dal vivo. Lo zoom è lo zoom del browser (preferenza del profilo nuovo, come Ctrl +/-):
le barre di Chrome restano al 100%, mentre `--force-device-scale-factor` rimpicciolirebbe anche quelle. In `replay`
la finestra riproduce quella misurata dal vivo su Windows 11 al 100%: bordi invisibili di 7 pixel a sinistra, a
destra e in basso (compresi nel rettangolo di `GetWindowRect`, quindi nel ritaglio), cornice di 1 pixel e 87 pixel di
barre di Chrome (una fascia neutra) sopra la pagina. Su un'altra macchina o con un'altra scala vanno rimisurati: le
note del report dal vivo riportano `GetWindowRect`, i limiti DWM e le dimensioni della vista.

**Scenari** in `bper-emulator/live_scenarios/`: `smoke-wide` (circa 25 s), `careful-reference` e `careful-wide`
(pensionato `sim-018` e due linee di credito `sim-006`, 3 s per pagina), `resize-fast` (nota lunga `sim-021`, un
operatore veloce a 1 s per stato, che non deve produrre catture, poi la finestra allargata a metà sessione),
`generated-wide` (due pratiche del set da 40), `matrix`, `generated-set` e `modes` (solo per `replay`; `modes` apre
una pratica in visualizzazione e una in lavorazione). Il formato è validato da `load_scenario()`: azioni `start`,
`search`, `open`, `next`, `tab`, `list`, `scroll-list`, `hover` (`evidence`, `tipo`: la descrizione del Tipo che
segue il puntatore, `fido`, `guarantee-1`, `guarantee-2`), `unhover`, `scroll-page` (scorre la pagina PEF 2.0 di una
vista alla volta fino in fondo, con una sosta a ogni posizione), `resize`, `wait`, ognuna con `dwell_ms`
facoltativo. In `practices` ogni pratica è una chiave o un oggetto `{"key": "sim-018", "mode": "visualizzazione"}`
(predefinito `lavorazione`). Nell'emulatore il modo vale per tutta la pagina (`?visualizzazione=1`), quindi
l'operatore ricarica la pagina quando la pratica successiva è nell'altro modo. In visualizzazione «Avvia Step Succ.»
è disattivato e Gestione Fidi si apre dal navigatore. Le posizioni di `scroll-list` (inizio, metà, fine) si leggono
dalla lista al momento, non da costanti, così reggono ai cambi della lista.

**Uscite** nella cartella `--out`: `report.md` (per pagina: soste, adozioni giuste, sbagliate, mancate, troppo brevi,
latenza da pagina pronta a cattura; per segmento: verità, esito, prototipo migliore e punteggio), `report.json` (tutto,
compreso il registro di ogni fotogramma: strategia di `frame_normalize`, visita, duplicato, instradamento, margine),
`driver.log`, `scenario.json` e, dal vivo, `frames/` con i soli fotogrammi **già ritagliati sulla finestra
dell'emulatore**, salvati quando cambiano. "Una riga per pratica" usa di norma un estrattore oracolo (la verità
dell'emulatore per lo stato a schermo): misura il raggruppamento a NDG perfetto, non la qualità dell'estrazione.
`python bper-emulator/live_test.py rescore --run CARTELLA` ricalcola il punteggio di una prova già fatta.

Come leggere il report: una sosta è un segmento in cui la pagina mostra lo stesso stato; `right` vuol dire che
l'agente ha adottato proprio quella schermata, `wrong` un'altra (la colonna "famiglia giusta" conta Elenco, Soggetti,
Fidi e Note). La lista fa eccezione: alla scala nativa le sue colonne non sono quelle degli stati di riferimento
(lo stato 1 parte dallo scorrimento 0, Creazione può finire sotto Evidenze), quindi conta solo che la pagina sia
riconosciuta (qualunque schermata 1-3) e non fissa attese sui campi; l'oracolo ne legge solo l'NDG. La verità dei
campi è quella per pratica (`/api/truth-practice/<chiave>.csv`), dopo il consolidamento. La distinzione fra le
schermate 1 e 2 viene dallo scorrimento della lista rispetto al suo intervallo, letto dal DOM. `missed` che la sosta bastava (2 s di stabilità più un fotogramma di conferma e uno di instradamento)
ma non è arrivata un'adozione (distinta in "nessuna etichetta accettata", un problema di riconoscimento, e "etichetta
accettata ma la sosta è finita prima della stabilità", un problema di tempi), `short` che era troppo breve per
pretenderla. Un'adozione durante un caricamento o su
una pagina fuori catalogo (Home, Ricerca, Note Delibere Precedenti) è `false-adoption`; una in una sosta più breve
della soglia di stabilità è una violazione. La latenza va da quando la pagina è pronta a quando il fotogramma adottato
è stato catturato. `lag-dropped` conta i fotogrammi persi perché il ciclo di cattura non regge i 3 fps.

**Avvertenza per il modo `live`.** Per 1-2 minuti una finestra di Chrome occupa il monitor principale e resta in primo
piano (sempre sopra): non coprirla e non muovere il mouse sopra di essa. Prima di aprirla il programma stampa un
conto alla rovescia di 10 secondi. Rifiuta di partire se è già aperta una finestra intitolata «BPER · Nuova PEF»
(chiudi il simulatore nel browser) e ogni prova dura al massimo 120 secondi.

**Riservatezza del desktop.** `mss` cattura tutto il monitor. Un fotogramma passa al riconoscimento, all'estrazione e
al disco solo se `frame_normalize` l'ha ritagliato con il rettangolo della finestra dell'emulatore (strategia
`window-rect`), quel rettangolo è proprio della finestra di Chrome avviata dalla prova e la finestra è davvero in primo
piano (controllo a griglia con `WindowFromPoint`). Un fotogramma `unchanged` (monitor intero), un ritaglio
`content-rect` sul desktop vero, un'altra finestra o una finestra coperta vengono scartati e contati; al terzo la prova
si ferma; se all'avvio la finestra non risulta in primo piano entro 5 secondi la prova non parte e il messaggio dice
quali programmi la coprono (solo il nome dell'eseguibile). Nei fotogrammi salvati sono coperte di grigio le parti che
il ritaglio di `GetWindowRect` prende fuori dalla finestra disegnata: i bordi invisibili e gli angoli arrotondati di
Windows 11 (il desktop dietro), e in una finestra massimizzata gli 8 pixel che sporgono sulla barra delle
applicazioni. Del desktop si registrano solo luminanza media e dispersione di quelle fasce (`strips` nel registro dei
fotogrammi), mai i pixel.

**`--extract` (a pagamento).** Al posto dell'oracolo usa la vera `ExtractionPipeline` con il provider configurato
(`LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` come per la CLI). Richiede `--accept-cost`; `--max-screens N` (predefinito
12, massimo 60) limita le schermate inviate al provider, le successive si chiudono senza chiamate. Prima di partire
stampa la stima (circa 3 chiamate da 8.000 token in ingresso e 1.500 in uscita per schermata, al massimo
`MAX_CALLS_PER_SCREEN`); rifiuta un modello assente da `PRICING_PER_1M`, perché il suo costo risulterebbe $0,00. Alla
fine stampa il costo reale, sommato dai `_meta` di ogni risultato. Poiché i fotogrammi lasciano la macchina, in questo
modo il worker riceve il ritaglio con le parti fuori dalla finestra disegnata (bordi invisibili, angoli, sporgenza
sulla barra delle applicazioni) già coperte di grigio: il riconoscimento lavora quindi su fasce neutre, a differenza
del modo senza `--extract`. Il collegamento di `--extract` al provider vero non è mai stato eseguito: è provato solo
con un provider finto. Usa solo pratiche con ruolo `sintetica` (letto da
`/api/practices.json`): mai pratiche dell'archivio o di test, e il server della prova non riceve mai
`--include-archive` né `--include-test`. Con `gemini-3.8-flash` e 12 schermate la stima è circa $0,42 (al massimo
$0,70). La chiave non viene mai stampata né scritta: la copia di `config.ini` nella cartella della prova ha `api_key`
vuoto.

**Test.** `tests/test_bper_live_harness.py`: scenario, timeline di verità, punteggio, confronto dei campi, guardie di
costo, ruolo e riservatezza (anche al punto in cui il worker riceve il fotogramma), e un test lento che fa passare le
nove schermate di riferimento dal vero worker e dal vero classificatore (`-m slow`): 9 giuste, 0 sbagliate, nessuna
cattura nelle soste di 1 secondo. Le inquadra dal desktop uniforme (`content-rect`), come `test_page_classifier.py`:
ritagliate con il rettangolo esatto della finestra (1-3 pixel di differenza) 4 schermate su 9 cambiano etichetta,
perché i margini tra le varianti di Gestione Fidi sono sotto 0,01. È un limite del classificatore, non della prova.
