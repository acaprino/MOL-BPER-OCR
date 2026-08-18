# 0008 - Classificatore locale: prototipi da ritagli reali e classi di scarto

- **Stato:** Accettato (cablato il 2026-08-18; `router = local-first` non ancora attivato in `config.ini`)
- **Data:** 2026-08-18
- **Interessa:** `edge-agent/page_classifier.py`, `tools/label_frames.py`
- **Misure:** `tests/fixtures/frames/registry.json`, `tools/measure_classifier.py`
- **Correlati:** [0002](0002-riconoscimento-pagina-roi-e-coseno-centrato.md), [0006](0006-router-llm-come-predefinito.md)

## Contesto

L'ADR [0006](0006-router-llm-come-predefinito.md) ha reso il router LLM il predefinito
perche' il confronto per prototipi non reggeva le inquadrature reali. Quella decisione
resta valida, ma poggiava su prototipi costruiti da **nove screenshot di finestra**, uno
per pagina.

Nel frattempo sono stati raccolti 2098 fotogrammi da sei registrazioni di sessioni reali,
etichettati e registrati in `tests/fixtures/frames/registry.json`. La domanda che questo
ADR misura: con prototipi costruiti da ritagli **reali**, il riconoscimento puo' tornare
in locale, togliendo la chiamata di rete dal percorso comune?

## Le tre correzioni misurate

### 1. Vincolo di area minima sulla localizzazione

Su 2098 fotogrammi, il **36% dei rettangoli** era sotto 0.6 Mpx contro una mediana di
1.10, il peggiore 249x203 su uno schermo 1920x1080. La ricerca scorre le larghezze dalla
piu' piccola e il punteggio e' normalizzato per finestra, quindi una zona uniforme piccola
puo' battere la finestra vera senza contenere **nessuno** degli elementi che identificano
l'applicativo: barra indirizzi, logo BPER, navigatore.

`MIN_AREA_FRACTION = 0.20` scarta i candidati sotto un quinto del frame. Ricalcolati 319
rettangoli: il piu' piccolo passa dal 5% al 22% del frame, mediana 53%.

Guadagno misurato: da 24/29 a 26/29 pagine corrette. Reale ma modesto, e **non** risolve
i falsi positivi.

### 2. I nove screenshot di riferimento come prototipi

Erano stati esclusi per una ragione metodologica: sono screenshot di *finestra*, mentre i
fotogrammi delle registrazioni sono finestre dentro desktop condivisi, e mescolare
distribuzioni diverse falsa la misura.

**L'obiezione era sbagliata nel merito.** Le registrazioni sono condivisioni schermo di
riunioni Teams, con i riquadri dei partecipanti e la finestra ristretta: e' la situazione
da lezione. Un operatore che lavora apre il browser a schermo intero, e quello che il
sistema vede e' **esattamente** l'inquadratura dei nove PNG. Il caso che stavo trattando
come artificiale e' probabilmente quello prevalente in esercizio.

| | solo fotogrammi | con i nove riferimenti |
|---|---|---|
| classi con prototipo | 5 | **9** |
| pagine corrette | 26/31 (84%) | 27/31 (87%) |
| falsi positivi | 52/116 | 53/116 |

Le classi coperte passano da cinque a nove a costo zero. Le quattro pagine con tooltip
(3, 6, 7, 8) senza i riferimenti non avrebbero **nessun** prototipo: nelle registrazioni
compaiono al massimo due volte ciascuna.

### 3. Classi di scarto separate per tipo

Senza una classe di scarto il classificatore **deve** scegliere fra le pagine: il 100% dei
negativi veniva assegnato a una pagina, non per errore ma per costruzione.

| strategia | prototipi | pagine | falsi positivi |
|---|---|---|---|
| nessuna | 0 | 90% | 100% |
| uno solo, mediato | 1 | 87% | 44% |
| **per tipo** | **3** | **87%** | **20%** |
| k-means 4 | 4 | 77% | 16% |
| k-means 8 | 8 | 77% | 14% |
| k-means 16 | 16 | 42% | 9% |
| k-means 24 | 24 | 35% | 9% |

I tre tipi sono `altro-bper` (BPER fuori processo, tipicamente Gestione Documentale),
`altro-app` (altro applicativo) e `altro-nulla` (nero, transizioni). Non sono un
raggruppamento statistico: sono le categorie distinte **guardando le immagini** durante
la revisione, e averle separate nell'etichettatura invece di collassarle in un unico
"altro" e' cio' che le rende utilizzabili adesso.

Il k-means abbassa ancora i falsi positivi ma li paga in accuratezza, e il meccanismo e'
chiaro: piu' prototipi di scarto esistono, piu' e' probabile che uno somigli casualmente
a una pagina vera. A 16 gruppi il classificatore e' rotto.

## Decisione

Adottare la configurazione **prototipi reali + i nove riferimenti + tre classi di scarto
per tipo**, che sulla registrazione tenuta fuori misura 87% sulle pagine e 20% di falsi
positivi, contro 83% e 100% del punto di partenza.

### Cablaggio (2026-08-18)

- `page_classifier.py` riconosce le cartelle di prototipi che iniziano per `SCARTO`:
  restano normali prototipi, cambia solo come `classify()` riporta una loro vittoria.
- `classify_detailed()` espone `margin`, `runner_up` e `rejected_by` accanto a label e
  score, senza toccare il contratto `(label, score)` usato da cinque chiamanti.
- `embedding_geometry()` include il numero di classi di scarto: aggiungerne una cambia il
  *comportamento*, non solo i dati, e una cache costruita prima non deve essere servita
  dopo.
- `router = local-first` nel worker: il classificatore decide quando il margine supera
  `local_margin_min` (default 0.10) o quando il frame perde contro uno scarto; altrimenti
  passa al router LLM. E' l'inversa di `hybrid`, dove la rete si paga comunque.

### Cosa e' stato effettivamente spedito, e la sorpresa (2026-08-18)

Costruendo i prototipi e provandoli, la parte sulle **pagine** non ha retto:

| configurazione dei prototipi | riferimenti riconosciuti |
|---|---|
| solo i nove riferimenti | **9/9** |
| riferimenti + tre classi di scarto | **9/9** |
| riferimenti + scarto + ritagli reali nelle pagine | **1/9** |

Aggiungere ritagli reali alle classi *pagina* fa crollare il riconoscimento: tutto finisce
su `screen 8`, l'unica classe rimasta con il solo riferimento. La misura sul corpus
(87% con prototipi reali) era fatta costruendo **tutti** i prototipi dai ritagli, una
popolazione sola; mescolarli con i riferimenti produce prototipi mediati fra due
popolazioni e lontani da entrambe. Il meccanismo esatto non e' stato dimostrato, il fatto
misurato si'.

Lungo la strada e' emerso anche un difetto del builder: salvare i prototipi gia' ritagliati
sull'area applicativa fa applicare `DEFAULT_CROP_ROI` una seconda volta, togliendo un altro
20% di contenuto vero. Corretto allargando il rettangolo verso l'alto, ma non e' bastato a
salvare la configurazione mista.

**Spedito quindi:** pagine dai nove riferimenti (come prima), piu' le **tre classi di
scarto** dai ritagli reali. E' la meta' che regge: 9/9 sulle pagine e negativi rifiutati con
la categoria giusta. `tools/build_prototypes.py` costruisce gli scarti per default e mette
le pagine dietro `--pages`, con il numero in aiuto.

Il `config.ini` spedito resta su `router = llm`. `local-first` e' cablato e provabile, ma
attivarlo di default richiede una misura sul campo che questa non sostituisce.

## Cosa questa misura NON dice

**Il campione e' piccolo.** 31 pagine e 116 negativi di **una sola** registrazione. La
differenza fra 83% e 87% e' un fotogramma.

**Le etichette non sono verita' umana.** Sono proposte da un modello e riviste da un
altro. Guardando cinque presunti falsi positivi uno per uno, **due avevano l'etichetta
sbagliata**: il classificatore aveva ragione. Una misura contro etichette non validate
misura l'accordo, non l'accuratezza, ed e' un limite che nessun numero qui supera.

**La pagina 3 resta 0/2** anche avendo il prototipo. Differisce dalla 2 per un tooltip che
copre lo 0,05% dei pixel: un prototipo costruito su un solo esempio non basta.

**Le quattro pagine con tooltip hanno un prototipo fragile**, costruito su una o due
immagini. Sono state richieste catture mirate a chi usa l'applicativo; finche' non
arrivano, quelle classi vanno considerate coperte solo formalmente.

## Conseguenze

Se cablata, la configurazione permette al classificatore locale di decidere il caso comune
e di **rifiutare** quattro negativi su cinque, cosa che prima era impossibile. Il router
LLM resta per i casi a margine basso e per le pagine con tooltip.

La cache dei prototipi cambia forma, quindi `embedding_geometry()`
([0003](0003-chiave-cache-prototipi-con-geometria.md)) va esteso a coprire anche la
composizione dei prototipi, altrimenti una cache costruita con la vecchia configurazione
verrebbe servita in silenzio.
