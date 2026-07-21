# Glossario

Definizioni in parole semplici di ogni termine ricorrente in questa documentazione. I termini di dominio vengono dal contesto bancario italiano dell'applicativo di gestione del credito BPER; nel codice compaiono letterali come chiavi di campo, prompt e stringhe UI, e lì non vengono mai tradotti. I termini tecnici coprono la pipeline di estrazione e gli strumenti attorno.

Se sei nuovo del progetto, leggi prima la [Sintesi per tutti](00-executive-summary.md) e tieni questa pagina aperta accanto a tutto il resto. Per dove ogni struttura vive nel codice, vedi [Data Model](06-data-model.md); per cosa il sistema ne fa, vedi [Funzionalità](02-features.md).

## Termini bancari / di dominio

| Termine | Significato |
|---|---|
| **BPER** | Il gruppo bancario italiano il cui applicativo interno di gestione del credito (pagine "BStore Pratiche" / PEF) è ciò che questo progetto legge. |
| **pratica** | Il fascicolo di credito: il dossier che la banca tiene per una richiesta di credito -- cliente, linee di credito, garanzie, dati reddituali. |
| **NDG** / `ndg` | Il numero identificativo univoco del cliente nel sistema della banca. Insieme a `denominazione` identifica di chi è la pratica mostrata in una schermata. |
| **denominazione** | Il nome del cliente (persona o azienda) come registrato dalla banca. |
| **anchor (àncore: NDG + denominazione)** | I due campi di identità estratti per primi, in un passaggio dedicato -- ogni altro valore ha senso solo una volta bloccata l'identità del cliente. Se uno dei due non concorda con il foglio delle risposte, l'intera schermata viene esclusa dall'accuratezza FILTERED. |
| **fido** (plurale **fidi**) | Una linea di credito: un affidamento che la banca concede al cliente. `n_fido` è il suo numero. |
| **garanzia** (plurale **garanzie**) | Una garanzia (reale o personale) a copertura di una linea di credito. |
| **soggetti** | Le parti (cointestatari, garanti) collegate a una pratica. I primi quattro vengono appiattiti in `ndg_1..4` / `denominazione_1..4` / `ruolo_1..4`. |
| **ruolo** | La parte che un soggetto ricopre nella pratica (intestatario, cointestatario, garante, ...). |
| **tipo / stato / fase** | Tipo, stato e fase della pratica come mostrati nell'intestazione della schermata. |
| **evidenze** | Un campo di segnalazione/alert sulla pratica; il valore "B" può essere riparato dal suo tooltip dal controllo di coerenza. |
| **BMB / BPI Mutui** | Etichette di tipo pratica come mostrate nella UI BPER. Le varianti di scrittura del tipo mutuo (`mutui spesa`, `mutuo spesa`, `bpi mutui`) vengono canonicalizzate in "BPI Mutui". |
| **scheda privati** | La scheda dati "clienti privati": 13 campi su lavoro e reddito, come `professione_principale` e `retribuzione_annua_netta`. |
| **filiale_relazione** | La filiale che detiene la relazione con il cliente. |
| **rapporto** | Il conto/rapporto a cui una linea di credito è agganciata. |
| **scadenza** | Data di scadenza. |
| **importo_euro** | Importo in euro. |
| **tipo_op** | Tipo operazione di una riga fido o garanzia. |
| **rating ufficiale / score CGS** | Valutazioni creditizie del cliente secondo la banca (campi della scheda privati). |
| **campi tooltip** (`tooltip_*`) | Testo che nella UI BPER appare solo al passaggio del mouse; cinque campi lo catturano, e due di essi alimentano le regole di riparazione per coerenza di `evidenze` e `tipo`. |
| **Fotogramma** | La colonna del CSV di ground truth che indica a quale screenshot appartiene un valore. |
| **pagine canoniche** | Il raggruppamento fisso in quattro pagine usato per l'export e la visualizzazione client-facing: `risultato_ricerca`, `elenco_soggetti`, `gestione_fidi_e_garanzie`, `note_da_richiesta`. |
| **"Altro / Non riconosciuto"** | La definizione di pagina catch-all "altro / non riconosciuto"; l'edge-agent non la cattura mai. |
| **ground truth** / `dati.csv` | Il foglio delle risposte con i valori attesi verificati da una persona, usato per dare un voto all'estrazione. Il codice non lo modifica mai (e il file non è nel repository). |

## Termini tecnici

| Termine | Significato |
|---|---|
| **VLM** (Vision Language Model) | Un modello AI che guarda un'immagine e risponde a domande su di essa -- il motore di lettura del progetto. Scritto anche "Vision-LLM". |
| **LLM** | Large language model; l'AI testo-e-immagini dietro sia l'estrazione sia il riconoscimento pagina. |
| **prompt** | Le istruzioni scritte inviate al modello insieme a ogni immagine. Qui in italiano, per scelta. |
| **anchor pass / main pass / retry pass** | I tre passaggi di lettura: prima l'identità del cliente, poi tutto il contenuto della pagina, infine una rilettura mirata delle zone deboli. |
| **confidenza** | La certezza auto-dichiarata dal modello (0-1) per ogni valore. Guida i retry (sotto 0.60) e gli spareggi, ma non è verificata in modo indipendente. La soglia 0.95 per le àncore (`ANCHOR_CONF_MIN`) è dichiarata nel codice ma oggi di fatto non filtra nulla (vedi [Flussi di lavoro](05-workflows.md)). |
| **output strutturato** | Obbligare il modello a rispondere in una forma JSON fissa e verificabile a macchina invece che in testo libero; le risposte non valide falliscono rumorosamente. |
| **Pydantic** | La libreria Python che definisce e valida quelle forme di output (gli "schemi"). |
| **LangChain / ChatModel** | Lo strato di astrazione che rende OpenAI e Google Gemini intercambiabili dietro un'unica funzione factory. |
| **provider** | Quale servizio AI esegue l'estrazione -- OpenAI (default) o Google Gemini -- selezionato dall'impostazione `LLM_PROVIDER`. |
| **token** | L'unità con cui i servizi AI fatturano; i conteggi per chiamata alimentano il report dei costi. |
| **crop / ritaglio** | Una fetta rettangolare fissa dello screenshot inviata al modello (striscia di intestazione, area contenuti, aree di retry). |
| **result dict** | L'unica struttura di output per schermata -- valori, tabelle, provenienza, costi -- che tutto ciò che sta a valle consuma. |
| **provenienza dei campi** / `_field_sources` | Il registro di quale passaggio ha prodotto il valore finale di ogni campo. |
| **coherence check (controllo di coerenza)** | Le regole di post-processing che riparano `evidenze` e `tipo` a partire dai tooltip, dopo tutti i passaggi. |
| **RAW vs FILTERED** | Accuratezza contata su tutte le schermate vs solo sulle schermate le cui àncore di identità coincidevano con la ground truth. |
| **DATASET_MISMATCH** | Un flag sull'intera schermata: NDG/denominazione estratti non concordano con la riga di ground truth, quindi la schermata è esclusa dalle metriche FILTERED. |
| **OK / WRONG / MISSING / HALLUCINATED / OK_NULL** | I voti per campo: corretto; sbagliato; atteso un valore ma non estratto; prodotto un valore dove non ce n'era; correttamente vuoto. |
| **allucinazione** | Quando l'AI inventa un valore che in realtà non è a schermo. Il report di accuratezza lo segnala come HALLUCINATED. |
| **edge-agent** | L'app desktop PyQt6 che osserva un monitor ed esegue l'estrazione dal vivo mentre un operatore naviga BPER. |
| **pHash dedup** | Hashing percettivo: frame consecutivi quasi identici hanno impronte quasi identiche e vengono saltati invece di essere rielaborati. |
| **distanza di Hamming** | Quanti bit differiscono tra due hash; una distanza piccola significa frame quasi duplicati. |
| **cancello di stabilità** | Il requisito di "stare fermi" 2 secondi prima che una pagina riconosciuta venga catturata -- evita di estrarre a metà scroll. |
| **page routing / router** | Decidere quale pagina BPER è a schermo prima di estrarre; modalità `llm` (OpenAI Vision), `ml` (classificatore locale), `hybrid` (prima LLM, fallback ML). |
| **classificatore a prototipi** (DINOv2) | Il router ML locale: trasforma l'intestazione della pagina in un embedding di 384 numeri e lo confronta per similarità del coseno con prototipi per pagina in cache. |
| **embedding** | Un'impronta numerica di un'immagine che rende misurabile la somiglianza visiva. |
| **similarità del coseno** | La matematica usata per misurare quanto due embedding sono simili. |
| **hallucination guard** | Il rifiuto delle risposte del router che nominano una pagina non presente nel file delle definizioni di pagina. |
| **QThread / segnale Qt** | Thread in background e messaggistica thread-safe nella UI PyQt6; il segnale `result_ready` porta ogni risultato all'interfaccia. |
| **CLI** | Interfaccia a riga di comando: `python main.py`, il front-end batch-e-valutazione. |
| **Tkinter / PyQt6** | I due toolkit UI desktop: quello integrato in Python (la GUI semplice) e quello più ricco (l'edge-agent). |
| **mss** | La libreria usata per la cattura veloce dell'intero monitor. |
| **FPS** | Frame al secondo -- quanto spesso l'edge-agent guarda il monitor. |
| **thread pool** | Eseguire in parallelo le estrazioni di più schermate per accorciare i batch. |
| **env var / `.env`** | Configurazione tramite variabili d'ambiente, caricate da un file `.env` locale (mai committato). |
| **OCR** | "Optical Character Recognition", la tecnologia classica di lettura del testo dalle immagini. Qui il lavoro lo fa il VLM in cloud; il nome sopravvive solo in `preprocess_for_ocr()`, che è un ritocco dell'immagine, non un lettore. |
| **POC** (proof of concept) | Software costruito per dimostrare e misurare un approccio, non per essere consegnato a utenti finali. |

---

Vedi anche: [Data Model](06-data-model.md) per la forma esatta che ogni termine assume nel codice, [Domande aperte](08-open-questions.md) per i termini la cui semantica non è ancora confermata (regole di coerenza, sinonimi di `tipo`, binding delle pagine canoniche).
