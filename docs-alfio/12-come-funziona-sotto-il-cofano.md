# Come funziona, sotto il cofano (spiegato semplice)

> Questo documento risponde alla domanda **"sì, ma *come* fa?"**. Gli altri file dicono *cosa* fa il progetto e *com'è* costruito; qui ti spiego i meccanismi interni con parole semplici, analogie e qualche disegno. Niente codice da leggere: solo le idee.
>
> È pensato per essere letto dopo l'[Executive Summary](00-executive-summary.md) e l'[Overview](01-overview.md). Se incontri un termine strano, tienilo aperto accanto al [Glossario](11-glossary.md).

---

## La domanda da cui parte tutto: è OCR o è AI?

La prima cosa da chiarire, perché è la più fraintesa: **non c'è nessun OCR locale.** Non c'è Tesseract, non c'è EasyOCR, non c'è nessun "motore che legge il testo" installato sul computer.

Tutta la lettura la fa un **modello di intelligenza artificiale che capisce le immagini** (un *Vision Language Model*, o VLM — di base GPT-4o di OpenAI o Gemini di Google). In pratica: si manda l'immagine al modello insieme a una domanda scritta ("estrai questi campi"), e il modello *guarda* lo screenshot e risponde con i dati già organizzati.

> ⚠️ **Trappola del nome.** Nel codice c'è una funzione che si chiama `preprocess_for_ocr()`. Il nome inganna: **non legge testo.** Fa solo un ritocco dell'immagine (la ingrandisce, la rende più nitida, alza il contrasto) per farla "vedere" meglio al modello. È un truccatore prima della foto, non un lettore.

**In una frase:** l'intelligenza di lettura sta nel modello in cloud; sul computer gira solo la regia (cattura, ritaglio, ritocco, controlli).

---

## Il viaggio di uno screenshot

Prima la mappa, poi i dettagli. Uno screenshot, dal momento in cui esiste a quando diventa dati strutturati, attraversa questo percorso:

```
                 ┌─────────────────────────────────────────────┐
   SOLO          │  FASE 0 — solo nell'Edge Agent (cattura live)│
   EDGE          │                                             │
   AGENT         │  cattura schermo  →  è un doppione? (pHash)  │
                 │        ↓ no                                  │
                 │  che pagina è? (router)  →  è stabile? (2s)  │
                 │        ↓ sì                                  │
                 │  ritocco immagine                           │
                 └───────────────────┬─────────────────────────┘
                                     │
                 ┌───────────────────▼─────────────────────────┐
   TUTTE         │  LA PIPELINE A 3 PASSAGGI (il cuore)        │
   E TRE         │                                             │
   LE MODALITÀ   │  1) ANCHOR  → chi è il cliente? (testata)    │
                 │  2) MAIN    → leggi tutto lo schermo         │
                 │  3) RETRY   → rileggi solo ciò di cui        │
                 │               non eri sicuro (zoom mirato)   │
                 └───────────────────┬─────────────────────────┘
                                     │
                 ┌───────────────────▼─────────────────────────┐
                 │  scelta del valore migliore + controlli     │
                 │  di coerenza  →  JSON finale + costi         │
                 └─────────────────────────────────────────────┘
```

La **Fase 0** esiste solo nell'Edge Agent (la modalità che "guarda" il monitor dal vivo). Nelle modalità CLI e GUI tu gli dai già l'immagine pronta, quindi si parte direttamente dalla pipeline a 3 passaggi.

Vediamo i due blocchi.

---

## Fase 0 — Dalla cattura allo screenshot "buono" (solo Edge Agent)

L'Edge Agent fa una cosa apparentemente banale ma piena di insidie: guarda lo schermo che cambia in continuazione e deve capire **quando** vale la pena leggere una schermata. Lo fa con quattro filtri in cascata.

### 1. Cattura continua

Fa screenshot ripetuti del monitor a una certa **frequenza** (gli FPS, impostabili in `config.ini`). Pensa a una telecamera che scatta foto a raffica.

### 2. "È un doppione?" — il dedup con pHash

Se stai fermo sulla stessa schermata, la telecamera scatta decine di foto identiche. Sarebbe uno spreco mandarle tutte al modello (ogni chiamata costa).

Per evitarlo si usa il **pHash** (*perceptual hash*): una specie di "impronta digitale" dell'immagine, un codice corto che riassume com'è fatta la foto. Due immagini quasi identiche hanno impronte quasi identiche. Il programma confronta l'impronta del nuovo scatto con quella del precedente:

- se la differenza (*distanza di Hamming*) è **≤ 3** → "è praticamente la stessa schermata", scarta e va avanti.
- se è più grande → "qualcosa è cambiato", procedi.

> Analogia: è come riconoscere una canzone dai primi due secondi senza ascoltarla tutta.

### 3. "Che pagina è?" — il riconoscimento pagina (router)

Prima di leggere, il programma capisce **quale delle schermate BPER** sta guardando. Questo è fondamentale (vedi più avanti la sezione sui campi omonimi). Ci sono tre modi, scelti in `config.ini` con `router=`:

| Modalità | Come funziona | Dove gira |
|---|---|---|
| `llm` | Manda l'immagine a un modello di visione **insieme a una descrizione scritta di ogni pagina** (i suoi tratti distintivi: "ha la sidebar blu?", "c'è un tooltip aperto?"). Il modello sceglie. | Cloud |
| `ml` | Trasforma l'immagine in un vettore numerico ("impronta visiva") con un modello chiamato **DINOv2** e lo confronta con dei campioni di riferimento. Vince la pagina più somigliante. | Locale, senza internet |
| `hybrid` | Prova prima `llm`, se fallisce ripiega su `ml`. | Misto |

Se la pagina riconosciuta è un catch-all tipo *"Altro / Non riconosciuto"* (login, errori, popup…), viene **ignorata**: non c'è niente da estrarre.

> Nota: la modalità `ml` usa **DINOv2**, non MobileNet come dice qualche vecchia descrizione. È un dettaglio, ma è bene saperlo.

### 4. "È ferma?" — il controllo di stabilità

Mentre navighi, una schermata può essere ancora "in movimento" (tabelle che si caricano, popup che appaiono). Leggere in quel momento darebbe dati incompleti.

Quindi il programma aspetta che la stessa pagina resti stabile per **2 secondi** prima di procedere. È come aspettare che il soggetto stia fermo prima di scattare la foto buona.

### 5. Ritocco finale

Superati i filtri, l'immagine viene ritoccata (`preprocess_for_ocr`: ingrandimento, nitidezza, contrasto) e passata alla pipeline.

**In una frase:** la Fase 0 serve a non sprecare chiamate — legge solo schermate **nuove, riconosciute e ferme**.

---

## I ritagli (crop): la chiave di tutto

Prima di spiegare i 3 passaggi serve capire i **ritagli**, perché li usano tutti.

Un **ritaglio** è esattamente come ritagliare un rettangolo da una foto con le forbici. Invece di mandare al modello *tutta* la schermata, gli si manda solo la **fetta** che interessa.

Le coordinate non sono in pixel ma in **percentuali da 0 a 1** (così funzionano con qualsiasi risoluzione). Il formato è sempre `(sinistra, alto, destra, basso)`. Esempio: `(0.00, 0.00, 1.00, 0.22)` = "tutta la larghezza, dall'alto fino al 22% dell'altezza" = **la striscia della testata**.

```
┌─────────────────────────────────┐  0%
│   TESTATA  (0 → 0.22)           │  ← il ritaglio (0, 0, 1, 0.22)
├─────────────────────────────────┤  22%
│                                 │
│   resto della schermata          │
│   (escluso da questo ritaglio)   │
│                                 │
└─────────────────────────────────┘  100%
```

**Perché ritagliare?** Per due motivi:

1. **Precisione.** Se al modello mostri *solo* la testata e gli dici "qui c'è l'NDG del cliente", non può confonderlo con gli NDG che stanno nelle tabelle più in basso: in quel ritaglio quei numeri **non esistono proprio**. Hai eliminato fisicamente l'errore.
2. **Risparmio.** Immagine più piccola = meno costo per chiamata.

I ritagli principali usati dal progetto:

```
┌─────────────────────────────────┐  0%
│  TESTATA → NDG, Denominazione,  │  usata dal pass ANCHOR
│            Tipo, Stato, Fase     │  e dai retry "HEADER"
│ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │ ~25-35%
│  CORPO  → tabelle Fidi,         │  retry "BODY"
│           Garanzie, Soggetti     │
│ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │ ~65%
│  PIEDE  → Note della richiesta  │  retry "FOOTER"
└─────────────────────────────────┘ 100%
```

> Dettaglio furbo: le fasce **si sovrappongono** apposta (il CORPO inizia mentre la TESTATA non è ancora finita). Così un campo a cavallo di un confine non viene tagliato a metà in nessuno dei due ritagli.

**In una frase:** un ritaglio mostra al modello *solo la zona giusta* per quello che sta cercando — meno confusione, meno costo.

---

## Il cuore: la pipeline a 3 passaggi

Ora il pezzo centrale. Ogni schermata viene letta in **tre passaggi successivi**, ognuno con un ritaglio diverso e una "domanda" diversa scritta al modello. L'idea di fondo è quella di un bravo impiegato: *prima capisco di chi è la pratica, poi leggo tutto, poi torno indietro solo sui punti dubbi.*

### Passaggio 1 — ANCHOR: "di chi è questa pratica?"

Si ritaglia **solo la testata** e si chiede al modello soltanto due cose: **NDG** (il codice cliente) e **Denominazione** (il nome).

Questi due valori sono le "àncore" (anchor): identificano la pratica e fanno da guida ai passaggi successivi. Proprio perché sono critici, c'è un **cancello di sicurezza**: il valore viene accettato solo se il modello dichiara una confidenza **≥ 0.95** (95%). Sotto questa soglia, il valore viene buttato (messo a "nullo") — meglio nessun dato che un dato sbagliato sull'identità del cliente.

> Perché solo la testata? Per la disambiguazione: l'NDG "del cliente" sta nell'intestazione, gli altri NDG (dei soggetti, delle garanzie) stanno nelle tabelle. Ritagliando la testata li si tiene fisicamente separati.

### Passaggio 2 — MAIN: "adesso leggi tutto"

Si ritaglia l'**area dei contenuti** (tutto tranne la sidebar e le barre inutili) e si chiede al modello di estrarre **tutti i campi** in una volta: metadati, importi, tabelle soggetti/fidi/garanzie, note, tooltip.

Trucco importante: al modello si passa anche un **suggerimento** ricavato dal passaggio 1, del tipo *"NDG atteso: 12345"*. È come dire al lettore "guarda che il cliente è questo": lo aiuta a non sbagliare e a restare coerente.

### Passaggio 3 — RETRY: "rileggi solo i punti dubbi"

Dopo il passaggio 2 il programma controlla i risultati e si chiede: *quali campi sono venuti male?* Un campo è "da rifare" se:

- è **vuoto/nullo**, oppure
- ha **confidenza sotto 0.60** (il modello stesso non era convinto).

Solo per le **zone** che contengono campi dubbi si fa un nuovo tentativo, mandando il **ritaglio mirato** di quella zona (TESTATA, CORPO o PIEDE) con un prompt specializzato (es. per il PIEDE: *"copia il testo delle note parola per parola"*). Su questi ritagli si applica anche un ritocco più aggressivo di contrasto/nitidezza.

C'è un **tetto** ai tentativi: massimo `MAX_CALLS_PER_SCREEN` chiamate per schermata (di default 4, di cui 2 già spese da anchor + main). Serve a non far esplodere costi e tempi.

```
        ANCHOR (testata)
           │  NDG + Denominazione, con cancello ≥ 0.95
           ▼
        MAIN (contenuti)  ◄── suggerimento "NDG atteso: ..."
           │  tutti i campi in una volta
           ▼
     qualche campo vuoto o con confidenza < 0.60?
           │ sì                          │ no
           ▼                             ▼
        RETRY (ritaglio mirato       (si salta il retry)
        per zona, prompt dedicato)
           │  max ~2 tentativi extra
           ▼
        risultati uniti
```

**In una frase:** anchor inquadra il cliente, main legge tutto, retry fa lo zoom solo dove serviva — spendendo chiamate extra solo quando ne vale la pena.

---

## Come sceglie il valore "definitivo"

Lo stesso campo può essere stato letto più volte (nel main e in un retry). Quale valore tiene? La regola (`pick_best`) è semplice e in quest'ordine:

1. **Un valore pieno batte sempre un valore vuoto.** Se il main aveva lasciato vuoto e il retry ha trovato qualcosa, vince il retry.
2. **A parità (entrambi pieni), vince la confidenza più alta.** Tiene la lettura di cui il modello era più sicuro.

In più il programma tiene un registro (`_field_sources`) che annota, per ogni campo, **da quale passaggio** è arrivato il valore finale (testata? main? quale retry?). Utile per il debug: sai sempre "chi ha detto cosa".

---

## La disambiguazione dei campi omonimi

Questo è il punto più sottile, e merita una sezione sua. A schermo, lo stesso nome **"NDG"** compare in almeno **tre posti diversi** con tre significati diversi:

- l'NDG **della testata** → il cliente principale
- gli NDG **nelle righe della tabella Soggetti** → le altre persone coinvolte
- gli NDG **nelle righe della tabella Garanzie** → altri soggetti ancora

Come fa il programma a non fare confusione? Con **tre meccanismi sovrapposti** — e nessuno dei tre, da solo, basterebbe:

**1. Il contesto della pagina.** Il riconoscimento pagina (Fase 0, oppure dedotto dai contenuti) dice *in quale schermata siamo*. E ogni campo, nel progetto, è **legato a una sola pagina**: l'NDG "principale" appartiene alla pagina "Risultato ricerca", gli NDG dei soggetti alla pagina "Elenco Soggetti", e così via. Quindi lo stesso nome "NDG" si traduce in caselle diverse a seconda di dove ci si trova.

**2. La struttura imposta dallo schema.** Al modello non si chiede una lista piatta di "NDG". Gli si chiede di riempire una **struttura precisa**: l'NDG principale è un campo a sé; gli NDG dei soggetti vanno *dentro* oggetti-soggetto `[NDG, Denominazione, Ruolo]`; quelli delle garanzie *dentro* oggetti-garanzia. Sono caselle diverse anche se il testo a video è identico.

**3. La separazione fisica con i ritagli.** Il pass anchor cerca l'NDG del cliente **solo nella testata**, lontano dalle tabelle. Quindi anche geograficamente i tre "NDG" vivono in ritagli diversi.

```
   stesso testo a schermo: "NDG"
              │
   ┌──────────┼───────────────────────┐
   ▼          ▼                       ▼
 TESTATA   tabella SOGGETTI        tabella GARANZIE
   │          │                       │
 campo      dentro oggetto-          dentro oggetto-
 "ndg"      soggetto (ndg_1,         garanzia
            ndg_2, ...)
   │          │                       │
   └──── pagina + schema + ritaglio diverso ────┘
        → tre caselle distinte, zero collisioni
```

**In una frase:** la pagina dice *in che contesto siamo*, lo schema dice *in quale casella mettere ogni valore*, il ritaglio *separa fisicamente* le zone. Insieme risolvono l'omonimia.

---

## I controlli di coerenza

Dopo aver unito tutto, il programma fa un paio di **controlli di buon senso** sui dati banking, sfruttando i tooltip (i testi nei popover "i"). Esempi reali:

- se c'è il tooltip che spiega il valore "B" del campo *Evidenze*, ma *Evidenze* è venuto vuoto o solo numerico → lo corregge a **"B"**.
- se c'è il tooltip che descrive un tipo "BMB", ma il campo *Tipo* è vuoto → lo riempie con **"BMB"**.

È la rete di sicurezza: usa un'informazione presente altrove nella schermata per turare i buchi in modo coerente.

---

## Confidenza e costi: il "conto della spesa"

Due cose viaggiano insieme a ogni dato estratto:

- **Confidenza (0–1):** per ogni campo, quanto il modello era sicuro. È quella che fa scattare il retry (< 0.60) e il cancello degli anchor (≥ 0.95).
- **Costo:** *ogni singola chiamata* al modello registra quanti token ha usato, quanto è costata in dollari e quanto ci ha messo. Alla fine questi numeri vengono **sommati** per schermata, così sai esattamente quanto ti è costato leggere una pagina.

Questo permette i due report finali: l'**accuratezza** (confrontando con i dati corretti, la *ground truth*) e il **costo**.

---

## Il quadro completo, in dieci righe

1. Niente OCR locale: a leggere è un modello AI che capisce le immagini.
2. L'Edge Agent cattura lo schermo in continuo, ma legge solo schermate **nuove** (dedup pHash), **riconosciute** (router) e **ferme** (stabilità 2s).
3. Tutto ruota attorno ai **ritagli**: mostrare al modello solo la fetta giusta.
4. La lettura avviene in **3 passaggi**: anchor (chi è il cliente) → main (leggi tutto) → retry (zoom sui dubbi).
5. Gli anchor passano solo con confidenza **≥ 0.95**; i retry scattano sotto **0.60**.
6. Il valore finale si sceglie con `pick_best`: pieno batte vuoto, poi vince la confidenza più alta.
7. L'**omonimia** dei campi si risolve con pagina + schema + ritaglio.
8. Controlli di **coerenza** sui tooltip turano i buchi.
9. Ogni chiamata traccia **token, costo e tempo**, sommati per schermata.
10. Output: JSON strutturato + report di **accuratezza** e **costo**.

---

### Dove approfondire

- I passaggi con diagrammi tecnici di sequenza → [Workflows](05-workflows.md)
- Le caselle esatte dei dati (gli schemi) → [Data Model](06-data-model.md)
- Come i pezzi stanno insieme → [Architecture](04-architecture.md)
- I termini banking (NDG, fido, garanzia…) → [Glossario](11-glossary.md)

*Documento concettuale in linguaggio semplice — complementare alla guida tecnica.*
