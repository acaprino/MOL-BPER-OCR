# Domande aperte

Quello che segue è un catalogo onesto delle cose che il codice da solo non può dirti. Ogni domanda nasce da qualcosa di concreto nel repo -- una funzione lasciata a stub, una configurazione che contraddice la documentazione, un commento che sottintende una decisione che nessuno ha messo per iscritto. Porta questa lista alla tua prima conversazione con il team; ogni risposta che raccogli renderà il prossimo file che toccherai un po' meno confuso. Le domande sono raggruppate per categoria e ordinate, all'interno di ciascun gruppo, in base a quanto la risposta cambierà il tuo lavoro quotidiano.

## Architettura

**Dove è finito `app.py`, e Streamlit è ancora in scope?**
`CLAUDE.md` righe 11-12 e 89 descrivono `app.py` come entry point della web UI Streamlit, ed `extraction/cli.py` riga 296 riporta un docstring che dice che `run_extraction_batch()` è "Shared by CLI (main) and Streamlit (app.py)." Ma nessun `app.py` esiste nel working tree, e `streamlit` è ancora pinnato in `requirements.txt` riga 6. Questo file è stato rimosso di recente su questo branch, mantenuto su un altro branch, o non è mai stato committato? Se Streamlit è sparito definitivamente, la dipendenza e i riferimenti nel docstring andrebbero rimossi? Questo conta perché un nuovo sviluppatore che legge `CLAUDE.md` perderà un'ora a cercare un file che non c'è.

**Quale modalità di routing è quella intesa come default per l'edge-agent: `llm`, `ml` o `hybrid`?**
`edge-agent/config.ini` riga 4 imposta `router = llm`, ma `edge-agent/llm_router.py` (righe 42-50) ed `edge-agent/page_classifier.py` implementano un `MLPageRouter` completo basato su DINOv2 e il repo include embedding di prototipo in cache in `edge-agent/assets/templates/bper/bper_page_prototypes.json`. Il brief di contesto menziona anche un'opzione hybrid. Il classificatore ML è l'obiettivo strategico (più economico, offline) con il router LLM come fallback, oppure è il router LLM quello che funziona davvero bene e il percorso ML è un esperimento iniziale? La risposta cambia su quale file dovresti investire tempo per capirlo per primo.

**Perché la pipeline mantiene sia un passaggio anchor che un passaggio principale invece di estrarre NDG/Denominazione in un'unica chiamata?**
`extraction/pipeline.py` righe 70-90 esegue un passaggio anchor dedicato sul solo ritaglio dell'header (`HEADER_IN_CONTENT = (0.00, 0.00, 1.00, 0.22)` in `extraction/config.py` riga 56) con il proprio modello (`LLM_MODEL_ANCHOR`) e il proprio prompt (`ANCHOR_PROMPT` in `extraction/prompts.py` riga 25). Il passaggio principale poi ri-estrae gli stessi campi sull'intero ritaglio del contenuto. Questa separazione è stata introdotta perché la versione a passaggio singolo allucinava gli anchor, perché permetteva di usare un modello più economico per l'anchor, o per qualche altro motivo legato all'accuratezza? Questa è la decisione architetturale più costosa della pipeline -- conoscere il razionale è essenziale prima di metterci mano.

**`extraction/canonical_mapping.py` è il ponte previsto a lungo termine verso uno schema di backend, o uno shim temporaneo?**
`extraction/canonical_mapping.py` e i quattro nomi di pagina canonici in `extraction/page_definitions.py` (`risultato_ricerca`, `elenco_soggetti`, `gestione_fidi_e_garanzie`, `note_da_richiesta`) appiattiscono l'output grezzo a 9 schermate in un modello canonico più piccolo. Questo meccanismo convive con la lista piatta originale `FIELD_KEYS` in `extraction/fields.py`. Quale rappresentazione usa effettivamente il consumo a valle, e quale è quella destinata a sopravvivere in produzione? Correlato: `extraction/cli.py` righe 268-273 lasciano `_deduplicate_same_page_outputs()` commentato con una nota `TEMP TEST: keep all outputs until page_key mapping is validated` -- chi è responsabile di validare quella mappatura, e cosa significa "validated" in termini concreti?

**Perché `gui_app.py` è un'app Tkinter mentre `edge-agent/` è PyQt6?**
Due UI desktop nello stesso repo usano due toolkit diversi. `gui_app.py` è Tkinter autonomo; l'edge-agent sotto `edge-agent/ui/` è PyQt6 + qt-material. La versione Tkinter doveva essere sostituita, è un fallback più semplice per gli utenti che non possono installare Qt, oppure le due servono persone diverse (una rivolta agli operatori, una rivolta agli sviluppatori)? Se quella Tkinter è deprecata, il nuovo lavoro probabilmente non dovrebbe estenderla.

## Logica di business

**Com'è fatta esattamente la ground truth `mnt/data/dati.csv`, e chi la mantiene?**
`extraction/evaluation.py` riga 33 ed `extraction/config.py` riga 9 puntano entrambi a `mnt/data/dati.csv`, ma `/mnt` è gitignored (la riga per `/mnt` in `.gitignore`) e il file non è nel working tree. Il loader in `load_ground_truth()` (`extraction/evaluation.py` righe 33-56) accetta diversi nomi di colonna alternativi (`Screenshot`/`Fotogramma`/`Screen`, `Valore rilevato`/`Valore`, `Denominazione da attribuire`/`Campo`), il che suggerisce che lo schema sia andato alla deriva. Chi possiede la versione canonica di quel CSV, dove è archiviato, e quale variante dei nomi di colonna è autorevole in questo momento?

**Qual è il significato esatto delle 9 schermate BPER, e corrispondono 1:1 con le 4 pagine canoniche?**
Il repo fa riferimento alle schermate da "screen 1" a "screen 9" (es. `mnt/data/screen 1.png`, prototipi in `edge-agent/assets/templates/bper/`), mentre `extraction/page_definitions.py` definisce solo 4 pagine canoniche ed `edge-agent/assets/templates/bper/prompts.json` definisce 5 tipi di pagina per il router. Più schermate vengono fuse in un'unica pagina canonica (cosa che implica la logica di deduplica commentata in `extraction/cli.py`), e se sì, qual è la mappatura esatta? Chi valida l'output di estrazione su dati reali ha bisogno di questa tabella di traduzione messa per iscritto.

**Cosa dovrebbe fare l'operatore quando la pipeline restituisce `_status: ANCHOR_UNCERTAIN`?**
`extraction/pipeline.py` emette questo stato quando entrambi i valori anchor sono nulli e `STOP_ON_ANCHOR_UNCERTAIN=1`. È un errore bloccante che richiede intervento manuale, un avviso soft per riprovare con uno screenshot diverso, o un segnale che la schermata non è affatto una pagina BPER valida? Il default è 0 (non fermarsi) secondo `extraction/config.py` riga 51, ma il commento di `.env.example` riga 30 suggerisce che questa sia una manopola deliberata. Qual è l'impostazione di produzione prevista?

**Perché `normalize_tipo()` hard-coda "mutui spesa" -> "BPI Mutui"?**
`extraction/normalization.py` righe 10-23 contiene una singola tabella `TIPO_MAPPING` a tre voci che riscrive "mutui spesa"/"mutuo spesa"/"bpi mutui" nel canonico "BPI Mutui". È un fix temporaneo per una stranezza del modello, la prima voce di quella che dovrebbe diventare una tabella di sinonimi generale, o una regola a livello di prodotto arrivata da uno stakeholder? Un nuovo sviluppatore non saprà se aggiungere altre voci qui o contestare il concetto.

**Cosa fa il controllo di coerenza basato sui tooltip nella pipeline, e quando dovrebbe scattare?**
`extraction/fields.py` righe 28-32 e 74-78 definiscono cinque campi `tooltip_*` (es. `tooltip_descrizione_bmb`, `tooltip_evidenze_b`), e il brief di contesto menziona uno step 7 "Controllo di coerenza: correzioni basate sui tooltip" nella pipeline. Quale regola di business stabilisce che un tooltip debba sovrascrivere il valore di un campo, e questi tooltip sono specifici per pagina o globali? Se un tooltip è in disaccordo con il valore principale estratto, quale dei due vince e perché?

**I ritagli delle aree di retry (HEADER/BODY/FOOTER) sono tarati su uno specifico layout di pagina BPER, o sono abbastanza generici per tutte le 9 schermate?**
`extraction/config.py` righe 59-78 fissa tre regioni di retry con coordinate relative hard-coded (`HEADER = (0.00, 0.00, 1.00, 0.35)`, `BODY = (0.00, 0.25, 1.00, 0.75)`, `FOOTER = (0.00, 0.65, 1.00, 1.00)`) e una mappa statica `AREA_TO_FIELDS`. Queste si sovrappongono nelle bande 0.25-0.35 e 0.65-0.75. Sono state tarate su una schermata e funzionano per le altre, o ogni regione è stata validata su ogni pagina? Se cambi uno di quei numeri, quale test dovresti eseguire?

## Infrastruttura

**La chiave API OpenAI committata in `edge-agent/config.ini` riga 23 -- è attiva, già ruotata, o un'esca?**
`edge-agent/config.ini` riga 23 contiene `api_key = REDACTED_OPENAI_API_KEY`, e il file è tracciato in git. Questa dovrebbe essere la prima cosa che il team conferma: la chiave è stata revocata, e qual è il piano per spostare i segreti dell'edge-agent fuori da `config.ini` (per esempio delegando a `.env` allo stesso modo del pacchetto extraction)? Finché non c'è risposta, nessuno dovrebbe dare per scontato che la chiave sia al sicuro.

**Qual è il target di deployment per l'edge-agent, e chi esegue la CLI di estrazione?**
Non c'è alcun Dockerfile, nessuna unit systemd, nessun wrapper di servizio Windows. `README.md` documenta una ricetta PyInstaller per `gui_app.py` ma non per l'edge-agent. L'edge-agent è pensato per essere distribuito come eseguibile bundle, come sorgente Python depositato sulle macchine degli operatori, o è solo uno strumento per sviluppatori? E per la CLI, il runner previsto è il laptop di uno sviluppatore, un job schedulato, o una macchina ops con accesso a `mnt/data/`?

**Cosa sono `localhost:8081` e `localhost:9000` referenziati in `edge-agent/config.ini`?**
`edge-agent/config.ini` riga 10 punta `[api] base_url` a `http://localhost:8081` e le righe 13-16 configurano un'intera sezione MinIO (`http://localhost:9000`, bucket `edge-agent-frames`). Ma `bper_capture_worker.py` riga 713 ha `_maybe_upload_dataset()` stubbed con un `return`, e nessun codice attualmente fa POST verso la porta 8081. C'era un backend SaaS con cui questi parlavano e che è stato rimosso (commento riga 710: "Rimossa logica di upload remoto (SaaS/Sauron) per consolidamento locale"), e se sì, il piano è di reintrodurlo o di eliminare la config morta?

**Come viene scaricato il modello DINOv2 in un ambiente sandboxato o offline?**
`edge-agent/page_classifier.py` usa `torch.hub.load` per scaricare `dinov2_vits14` al primo avvio. L'ambiente di produzione o del cliente ha accesso in uscita alla CDN torch hub di Facebook, o ci si aspetta che il modello sia pre-cachato? Se pre-cachato, dove lo ospita il team, e qual è la dimensione/posizione attesa su disco?

**Qual è l'artefatto di rilascio?**
Il `.gitignore` esclude `build/` e `dist/` ma nessuna pipeline di artefatti è committata. Il team produce bundle `.exe` da `gui_app.py` manualmente, ci sono release binarie ospitate da qualche parte (GitHub Releases, S3, condivisione file interna), e chi è responsabile di ricostruirle quando il codice cambia?

## Processo

**Su quale branch atterrano le nuove funzionalità: `develop` o `master`?**
`git status` mostra il working tree su `develop`. I commit recenti includono un merge da `bug-fix/improove_accuracy` in `develop`. `master` è un branch di rilascio protetto che resta indietro rispetto a `develop`, o è di fatto morto? Un nuovo sviluppatore dovrebbe creare un branch da `develop` per ogni modifica, e qual è il processo di code review / merge?

**Come testa il team le modifiche senza una suite di test?**
`CLAUDE.md` afferma esplicitamente che non esistono test, e non ci sono file `tests/` o `test_*.py`. Il valutatore di accuratezza (`extraction/evaluation.py`) usa `mnt/data/dati.csv` come ground truth, ma quel CSV non è committato. Il flusso attuale è "esegui `python main.py` su un set noto di schermate e guarda a occhio i numeri di accuratezza", e se sì, chi tiene le schermate di riferimento e gli output attesi? Più importante ancora, qual è lo smoke test che un nuovo sviluppatore dovrebbe eseguire dopo la sua prima modifica per dimostrare di non aver rotto nulla?

**Ci sono convenzioni di codice oltre a quelle presenti nel codice stesso?**
Non c'è `.editorconfig`, nessun `pyproject.toml` con `[tool.black]`, nessun `ruff.toml`, nessun pre-commit hook. Il repo mescola inglese e italiano in docstring, commenti e persino nei nomi di variabile (`extraction/prompts.py` è in italiano, i commenti di `bper_capture_worker.py` sono in italiano, le keyword/identificatori Python sono in inglese). La convenzione è "italiano per le stringhe rivolte all'utente e di dominio, inglese per il codice", o è semplicemente incoerente? Un nuovo arrivato dovrà scegliere da che parte stare quando aggiunge il suo primo file.

**Chi revisiona le modifiche, e cosa conta come "fatto"?**
La recente PR mergiata (`#2` da `bug-fix/improove_accuracy`) mostra che il team usa le PR di GitHub, ma non c'è `CODEOWNERS`, nessun template di PR, e nessuna CI. Cosa cerca un revisore? Ci si aspettano metriche di accuratezza manuali nella descrizione della PR?

## Debito tecnico

**Il blocco di deduplica commentato in `extraction/cli.py` righe 268-273: dovrebbe tornare, e quando?**
Il codice viene rilasciato con `# TEMP TEST: keep all outputs until page_key mapping is validated` seguito dalle tre righe commentate che chiamerebbero `_deduplicate_same_page_outputs()`. L'helper stesso è completamente implementato (righe 92-152) con messaggi di log e quattro diverse strategie di fallback. Chi è responsabile di riattivarlo, e quale lavoro lo blocca? C'è un ticket?

**`boto3` e `keyboard` in `requirements.txt` senza utilizzo attuale -- è sicuro rimuoverli?**
`requirements.txt` righe 15-16 pinnano `boto3>=1.35.0` e `keyboard==0.13.5`. Un grep sull'intero codebase (a parte lo stub no-op `_maybe_upload_dataset()` in `edge-agent/workers/capture/bper_capture_worker.py` riga 713) non trova alcuna chiamata. `boto3` è presumibilmente per il percorso MinIO che è stato rimosso; `keyboard` è pinnato a una versione vecchia ed esatta senza alcun chiamante. Si possono eliminare, o c'è qualcosa in programma che ne ha bisogno?

**Il default di `PARALLEL_WORKERS` dice 12 nel codice ma 4 nella documentazione -- quale è corretto?**
`extraction/config.py` riga 11 legge `int(os.getenv("PARALLEL_WORKERS", "12"))` ma `.env.example` riga 20 scrive `PARALLEL_WORKERS=4` e anche `CLAUDE.md` dice 4. Il default nel codice è stato aumentato senza aggiornare la documentazione, o qualcuno ha cambiato il default del codice per sbaglio? Questo conta perché 12 chiamate VLM concorrenti bruceranno il rate limit di OpenAI su un account piccolo più velocemente di quanto un nuovo arrivato si aspetti.

**`LLM_THINKING_LEVEL` ha un default `medium` morto in `extraction/config.py` -- la costante andrebbe rimossa?**
`extraction/config.py` riga 20 legge `os.getenv("LLM_THINKING_LEVEL", "medium")` in una costante di modulo, ma nulla importa o usa quella costante. Il gate effettivo vive in `extraction/llm_factory.py` riga 72, che legge `os.getenv("LLM_THINKING_LEVEL", "")` con default vuoto e applica il valore solo quando il nome del modello contiene "thinking". Quindi funzionalmente il comportamento corrisponde a `.env.example` ("commentato -> off"), ma la riga morta in `config.py` è confusa e dovrebbe probabilmente essere eliminata o ricollegata. Qual è il contratto previsto: "default medium quando non impostato" (attualmente documentato) o "off quando non impostato" (attualmente implementato)?

**`prompts_immagini.txt` è ancora contenuto attivo, o un artefatto residuo?**
`prompts_immagini.txt` si trova alla radice del repo. Il brief di contesto lo marca come "Solo riferimento: prompt di generazione immagini (non usati)." Dovrebbe essere spostato sotto `docs/`, eliminato, o è effettivamente referenziato da uno script che un grep ha mancato? Lasciarlo al livello superiore suggerisce che abbia importanza.

**`edge-agent/workers/capture/bper_capture_worker.py` si aspetta un `Guida pagine ITA .xlsx` che non è committato.**
Le righe 253-284 di quel file caricano l'ordinamento delle pagine da un workbook Excel in `edge-agent/assets/templates/bper/Guida pagine ITA .xlsx`, con fallback a `prompts.json` quando il file manca. L'Excel non è nel repo. Questo file dovrebbe vivere nel repo (ed è stato solo dimenticato), viene distribuito separatamente agli operatori, o il percorso Excel è codice morto che andrebbe eliminato a favore del solo `prompts.json`?

**Il marcatore `# TEMP TEST` è l'unico indizio di una campagna di validazione del page_key. Quale altro lavoro in corso c'è?**
Quando trovi `TEMP TEST`, `FIXME`, `TODO` o `# noqa: BLE001` sparsi qua e là (`bper_capture_worker.py` usa `noqa: BLE001` in più punti per silenziare gli avvisi "blind except", per esempio), vale la pena chiedere al team quali di questi sono intenzioni a breve termine e quali stanno marinando da mesi. C'è da qualche parte, fuori dal codice, una lista di voci di lavoro per il passaggio da POC a produzione?

## Riferimenti incrociati

- [Architettura](04-architecture.md) per il diagramma a layer attorno a cui ruotano queste domande
- [Stack tecnologico](03-tech-stack.md) per i dettagli sulle dipendenze (in particolare `boto3`, `keyboard`, `streamlit`)
- [Workflow](05-workflows.md) per le sequenze del batch, dell'edge-agent e della pipeline multi-passaggio
- [Per iniziare](07-getting-started.md) per i passi di setup che danno per risolte molte di queste domande
