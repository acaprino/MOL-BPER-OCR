# Glossario

Definizioni in parole semplici dei termini usati in questa guida e nel codice. Due gruppi: **termini di dominio bancario** (in gran parte italiani, dall'applicativo BPER) e **termini tecnici** (lato software e AI). Dopo questa pagina, un lettore di entrambi i mondi dovrebbe riuscire a seguire il resto della documentazione.

## Termini di dominio bancario

Vengono dall'applicativo di gestione del credito di BPER e dal mondo bancario italiano. Nel codice le chiavi dei campi mantengono volutamente i nomi italiani, perché devono corrispondere alle etichette usate dalla banca.

| Termine | Significato |
|---|---|
| **BPER** | La banca italiana di cui questo progetto legge le schermate dell'applicativo di gestione del credito. |
| **Pratica** | Il "fascicolo" di credito: la richiesta di un cliente e tutti i dati collegati. |
| **NDG** | "Numero di Gestione": l'identificativo univoco del cliente nel sistema della banca. Il progetto lo usa come àncora per stabilire a chi appartengono i dati di una schermata. |
| **Denominazione** | Il nome della persona o azienda a cui si riferisce la pratica. |
| **Soggetto** | Una persona o entità collegata alla pratica di credito. Una pratica può elencarne più di uno. |
| **Ruolo** | La parte che un soggetto ricopre, per esempio intestatario, cointestatario o garante. |
| **Tipo (pratica)** | Il tipo di prodotto di credito, per esempio "BPI Mutui". |
| **Fido** | Una linea di credito concessa al cliente: numero, rapporto collegato, importo, scadenza e tipo. |
| **Garanzia** | La garanzia che copre una linea di credito: descrizione, fido garantito, soggetto che la presta e importo coperto. |
| **Evidenze** | Marcatori associati alla pratica (il codice può ricavarli da un tooltip). |
| **Filiale di relazione** | La filiale che gestisce il rapporto con il cliente. |
| **Rating ufficiale** | La valutazione creditizia ufficiale del cliente secondo la banca. |
| **Score CGS** | Un punteggio di credito usato dalla banca. |
| **Scheda privati** | I campi su lavoro e nucleo familiare: retribuzione annua netta, professione principale, tipo contratto, numero mensilità, datore di lavoro, componenti del nucleo. |
| **Ground truth** | Il file con le risposte corrette (`dati.csv`) usato per misurare l'accuratezza. Lo fornisce una persona; il codice non lo modifica mai. |

## Termini tecnici

| Termine | Significato |
|---|---|
| **VLM (Vision Language Model)** | Un'AI che guarda un'immagine e risponde a domande su di essa in testo. È il motore che legge davvero ogni screenshot. |
| **LLM (Large Language Model)** | La famiglia più ampia di modelli AI testuali a cui i VLM appartengono. |
| **OpenAI / GPT-4o** | Uno dei due fornitori AI utilizzabili. GPT-4o è il modello predefinito. |
| **Google Gemini** | L'altro fornitore AI, selezionabile al posto di OpenAI. |
| **LangChain** | La libreria che permette di parlare sia con OpenAI sia con Gemini tramite un'unica interfaccia comune. |
| **Pydantic / output strutturato** | Un modo per obbligare l'AI a rispondere in una forma rigida e predefinita, così il risultato è sempre un record pulito e non testo libero. |
| **Anchor pass (passaggio àncora)** | La prima lettura: guarda solo l'intestazione per catturare codice e nome del cliente con alta confidenza, prima di leggere il resto. |
| **Main pass (passaggio principale)** | La seconda lettura: legge l'intera schermata ed estrae tutti i campi in una volta. |
| **Retry pass (passaggio di ripasso)** | Una terza lettura mirata: solo i campi tornati vuoti o incerti vengono riletti da un ritaglio ingrandito. |
| **Confidenza** | Un numero da 0 a 1 che l'AI riporta per ogni valore, per dire quanto è sicura. Sotto 0.60 fa scattare un ripasso; le àncore dell'intestazione sotto 0.95 vengono scartate. |
| **Crop (ritaglio)** | Un taglio rettangolare dell'immagine. Il progetto ritaglia via la barra laterale e ingrandisce regioni specifiche per leggerle meglio. |
| **Normalizzazione** | La pulizia di testo o numeri prima di confrontarli, per esempio togliendo i simboli di valuta o uniformando varianti di scrittura. |
| **Coherence check (controllo di coerenza)** | Una pulizia finale che usa i campi tooltip per correggere alcuni campi principali quando sono in disaccordo. |
| **Pagina / campo canonico** | Un nome ordinato e standard su cui il progetto mappa schermate e campi grezzi. Le nove schermate grezze confluiscono in quattro pagine canoniche. |
| **pHash (perceptual hash)** | Un'impronta dell'immagine. L'agente dal vivo la usa per saltare una schermata che non è cambiata, risparmiando chiamate inutili all'AI. |
| **DINOv2 (ViT-S/14)** | Un modello visivo pre-addestrato che l'agente dal vivo può usare per riconoscere quale pagina BPER è a schermo, confrontando impronte di immagini. |
| **Cosine similarity (similarità del coseno)** | La matematica usata per misurare quanto sono simili due impronte di immagini. |
| **Page routing (instradamento pagina)** | Decidere quale pagina BPER è la schermata corrente, con il modello DINOv2 o chiedendo direttamente all'AI. |
| **Edge agent (agente locale)** | L'applicazione desktop che osserva il monitor dal vivo ed estrae i dati mentre navighi, invece di lavorare da file salvati. |
| **OCR** | "Optical Character Recognition", la tecnologia classica per leggere il testo dalle immagini. Qui il lavoro lo fa l'AI, ma il pre-trattamento dell'immagine è comunque ottimizzato per rendere il testo leggibile. |
| **Worker paralleli** | Il progetto legge più screenshot contemporaneamente per andare più veloce. Il numero di letture simultanee è configurabile. |
| **Token** | L'unità con cui i fornitori AI fatturano. I report dei costi contano i token usati per schermata. |
| **API key (chiave API)** | La credenziale segreta che permette al progetto di usare OpenAI o Gemini. Necessaria per l'esecuzione. |
| **Allucinazione** | Quando l'AI inventa un valore che in realtà non è a schermo. Il report di accuratezza la segnala come "HALLUCINATED". |

## Vedi anche

- [Sintesi per tutti](00-executive-summary.md) per la panoramica in parole semplici.
- [Come funziona, sotto il cofano](12-come-funziona-sotto-il-cofano.md) per il funzionamento spiegato senza codice.
- [Data Model](06-data-model.md) per i campi e gli schemi esatti dietro questi termini.
