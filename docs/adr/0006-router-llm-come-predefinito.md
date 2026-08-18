# 0006 - Router LLM come predefinito, ML come ripiego

- **Stato:** Accettato
- **Data:** 2026-08-18
- **Supera:** [0005](0005-router-ml-invece-di-router-llm.md)
- **Interessa:** `edge-agent/config.ini`, `edge-agent/llm_router.py`
- **Correlati:** [0001](0001-normalizzazione-inquadratura-frame.md), [0002](0002-riconoscimento-pagina-roi-e-coseno-centrato.md)

## Contesto

L'ADR [0005](0005-router-ml-invece-di-router-llm.md), scritto il giorno precedente,
scelse `router = ml` su tre argomenti: DINOv2 separa tutte e 9 le pagine, il confronto
è locale e gratuito, e una chiamata di rete per frame aggiunge latenza e dipendenza a un
percorso che l'operatore percepisce come interattivo.

Il primo argomento poggiava su una premessa non dichiarata: **che l'inquadratura del
frame sia normalizzabile**. Un embedding globale è per costruzione una funzione
dell'intera immagine, quindi è una funzione dell'inquadratura; l'ADR
[0001](0001-normalizzazione-inquadratura-frame.md) esiste proprio per ricondurre il
frame alla forma dei prototipi.

Quella premessa è caduta. Il contesto reale di esercizio, chiarito dall'operatore dopo
la scrittura di 0005:

- Il browser può stare **in locale** oppure dentro una **sessione remota** (mstsc,
  Citrix), in qualsiasi dimensione e posizione sullo schermo.
- I due casi possono **coesistere nello stesso lavoro**: una parte del processo in
  Chrome locale, una parte dentro la sessione remota. L'inquadratura quindi cambia fra
  una pagina e l'altra della stessa acquisizione.
- Non esiste e non esisterà accesso a una postazione reale su cui misurare, quindi
  nessuna strategia di normalizzazione può essere validata prima del rilascio.

Una misura sulle sette inquadrature realistiche costruite in laboratorio aveva già
mostrato che `detect_app_rect()` ne gestisce **1 su 7**, e la peer review incrociata
(`.peer-review/2026-08-17-2114-.../04-verdict.md`, finding F01, accettato e certificato)
ha stabilito che quelle sette non sono comunque un criterio di decisione, non essendo
un campione della distribuzione di produzione.

Sommando: non si può normalizzare in modo affidabile un'inquadratura che varia in modi
che non possiamo osservare, e senza normalizzazione il classificatore a prototipi non
può funzionare. Non è un problema di taratura di ROI, soglia o centratura: è la
categoria di metodo che non soddisfa il requisito.

## Decisione

`router = llm` diventa l'impostazione spedita in `edge-agent/config.ini`.

Il router LLM riconosce la pagina **dal testo che vede**, non dalla disposizione
globale dei pixel. Il testo è invariante a dimensione, posizione, annidamento, scala e
al livello di finestra in cui l'applicativo si trova: è la proprietà che il requisito
richiedeva e che nessuna variante del confronto per prototipi può avere.

`DEFAULT_ROUTER_MODE` nel codice resta `"ml"`. La divergenza col file spedito è
**voluta**, non una deriva: `AgentConfig` usa i default quando `config.ini` non esiste,
e in quel caso partire facendo chiamate di rete con una chiave che potrebbe non essere
configurata è peggio che partire con un riconoscitore locale. Il file spedito esprime la
scelta; il default nel codice esprime il comportamento sicuro in assenza di scelta.

## Misure

Riconoscimento sulle 9 pagine di riferimento, confrontando il router generico con il
classificatore a prototipi sulle stesse immagini:

| inquadratura | router LLM | classificatore a prototipi |
|---|---|---|
| finestra nuda | **9/9** | 9/9 |
| annidata su desktop 1920x1080, scala 1.0 | **8/9** | 4/9 |
| annidata, scala 0.7 | **8/9** | non misurato (è il caso che lo rompe) |

Latenza media per chiamata: 4.0 s sulla finestra nuda, 4.6-4.7 s sulle annidate.

L'unico errore è ricorrente e prevedibile: `screen 1` viene letta come `screen 2`
("Risultato ricerca" contro "Risultato ricerca - Colonne estese"). Le due pagine
differiscono solo per quali colonne sono visibili. Sulla finestra nuda le distingue,
annidata no.

## Alternative valutate

**Restare su ML correggendo ancora la normalizzazione.** È la strada percorsa per un
giorno intero, e ha prodotto miglioramenti reali (ROI sul contenuto, coseno centrato,
chiave di cache) che restano validi. Scartata perché ogni variante richiede un'ipotesi
sull'ambiente che l'operatore non può garantire: titolo di finestra, processo, sfondo
uniforme, margini, livello di annidamento.

**Ancoraggio sul contenuto per individuare il rettangolo dell'applicativo.** Sarebbe
indipendente dalle finestre, ma resta un riconoscimento di pixel che deve poi essere
seguito dal confronto per prototipi, quindi eredita la fragilità alla compressione
Citrix e alla scala. E l'ancora andrebbe puntata sul bordo del browser, non sulla
testata BPER, perché i prototipi includono la cromatura del browser.

**Riconoscimento per template multi-scala.** Usa i 9 PNG come template da cercare nel
frame, restituendo insieme etichetta e rettangolo. Interessante e non misurato: resta
il candidato se la latenza del router LLM si rivelasse insostenibile in esercizio.

**OCR locale più regole sulle parole chiave.** Ha la stessa invarianza del router LLM
senza costo per frame né dipendenza di rete, ed è deterministico e ispezionabile.
Scartato **per ora** solo perché richiede una dipendenza nuova e del lavoro, mentre il
router LLM era già implementato e configurato. È la destinazione naturale se il costo o
la latenza diventano un problema.

## Conseguenze

Ogni frame instradato costa una chiamata VLM. Il throttling `route_retry_seconds` limita
i tentativi sui frame duplicati, ma su schermate diverse il costo è per frame.

**La latenza è il prezzo vero.** `route()` è sincrona dentro `_capture_once()`, quindi il
worker si blocca 4-5 secondi per ogni frame non duplicato. Col gate di stabilità che
richiede due riconoscimenti concordi, una pagina si acquisisce in circa dieci secondi
invece di due. Per un flusso guidato di 9 schermate è sostenibile, ma l'operatore
aspetta, e questo è il primo candidato a diventare inaccettabile se il numero di pagine
cresce.

Il router richiede una chiave per il provider configurato. Il `config.ini` spedito usa
`gemini` con `api_key` vuota, quindi la chiave arriva dall'ambiente
(`GEMINI_API_KEY` → `GOOGLE_API_KEY` → `LLM_API_KEY`). Senza chiave il router non
riconosce nulla e lo dice solo nella tab Debug LLM: un fallimento silenzioso già
documentato nella guida alla configurazione.

`torch`/`torchvision` restano necessari solo per il ripiego ML. Diventano candidati a
dipendenza opzionale, cosa che 0005 aveva escluso e che ora torna sul tavolo.

La confusione fra `screen 1` e `screen 2` va tenuta d'occhio: sono due pagine distinte
nella sequenza di acquisizione, e un'etichetta sbagliata consuma lo slot dell'altra. Il
recupero esiste ed è manuale (`force_capture()` non controlla l'appartenenza a
`captured_page_types`), quindi l'errore è correggibile dall'operatore ma non
automaticamente.
