# Frame di riferimento estratti dalle registrazioni

505 fotogrammi distinti presi da tre registrazioni di sessioni reali. Servono come
riferimento fisso per test, non-regressione e confronto fra versioni: sono l'unica
prova di **come l'applicativo appare davvero su una postazione**, e non sono
riproducibili se le registrazioni si perdono.

## Perché esistono

Fino al 2026-08-18 ogni misura sul riconoscimento pagina e sull'inquadratura era
fatta su materiale costruito in laboratorio: i 9 screenshot di riferimento in
`mnt/data`, oppure composizioni sintetiche. La peer review incrociata
(`.peer-review/2026-08-17-2114-.../04-verdict.md`, finding F01, accettato e
certificato) ha stabilito che quel materiale non è un campione della distribuzione
di produzione, quindi non può sostenere una decisione.

Questi frame lo sono.

## Provenienza

| cartella | registrazione | durata | frame |
|---|---|---|---|
| `20250919-parte02/` | `Bper-20250919_Parte 02 - Registrazione per N.mp4` | 71 min | 211 |
| `bpimutui-surroga/` | `Lavorazione Pratica BPIMutui - Surroga.mp4` | 46 min | 212 |
| `20250925-controllo-schermo/` | `Bper-20250925_Pratica fatta da Denis prendendo il controllo dello schermo di Radu.mp4` | 50 min | 82 |

Tutte e tre sono condivisioni schermo di riunioni: i riquadri dei partecipanti sono
visibili sulla destra, e la finestra condivisa cambia dimensione e posizione fra una
registrazione e l'altra. È esattamente la variabilità che il sistema deve tollerare.

## Come sono stati prodotti

```bash
ffmpeg -i "<registrazione>.mp4" -vf "select='gt(scene,0.10)'" -fps_mode vfr out/%04d.png
```

Poi deduplicazione pHash (distanza di Hamming > 3 su un ridimensionamento 256x256) e
conversione in JPEG qualità 88. Da 1288 fotogrammi selezionati da ffmpeg a 505 distinti.

**Avvertenza sulla deduplicazione:** il pHash è calcolato sul fotogramma **intero**,
quindi è dominato dalle parti statiche (sfondo, riquadri dei partecipanti). Pagine BPER
genuinamente diverse possono avere hash vicini, e una soglia più larga le collassa: un
primo tentativo a distanza 6 aveva ridotto 53 fotogrammi a 12, buttando distinzioni
reali. La soglia stretta usata qui conserva più materiale al prezzo di qualche
quasi-duplicato. La deduplicazione corretta andrebbe fatta **dopo** aver ritagliato
l'area applicativa, non prima.

## Cosa contengono, e cosa non contengono

Non sono soltanto le 9 pagine bersaglio. Le registrazioni percorrono un'intera pratica,
quindi ci sono pagine BPER fuori catalogo, altre applicazioni, transizioni, menu e
schermate quasi nere. **Quei fotogrammi sono materiale prezioso, non scarto:** sono i
negativi reali con cui calibrare la soglia di rifiuto, che fino ad oggi era tarata su
due negativi sintetici (un desktop uniforme e un grigio pieno). Era il finding F09 della
stessa peer review.

## Dati reali

Contengono nominativi, NDG e importi di clienti veri, come i 9 screenshot in `mnt/data`.
Il repository è privato. Non renderlo pubblico senza averli rimossi dalla cronologia,
non solo dal working tree: questo repository ha già dovuto riscrivere la propria storia
una volta, il 2026-07-21, per una chiave API committata.

## Il registro: `registry.json`

`registry.json` è l'indice su questi fotogrammi, e ha vita più lunga di qualsiasi singolo
esperimento: serve **a tutte le riesecuzioni**. Un metodo nuovo, un backbone nuovo, un
prompt nuovo si misurano contro questo file, e i risultati diventano confrontabili nel tempo
perché il riferimento non cambia sotto i piedi.

Si rigenera con `python tools/build_frame_registry.py --labels <...> --review <...>`.

Per ogni fotogramma:

| campo | contenuto |
|---|---|
| `frame` | percorso relativo dentro `tests/fixtures/frames/` |
| `cluster` | il gruppo: `1`..`9` per una pagina del processo, oppure un negativo |
| `process`, `step`, `step_name` | quando è una pagina: il processo e il passo esatto, esplicitati invece che lasciati dedurre dal numero |
| `proposals.gemini`, `proposals.claude` | le due proposte indipendenti, conservate entrambe |
| `reviewed` | se la revisione indipendente ha già coperto questo fotogramma |
| `app_rect`, `localization_score` | dove è stata trovata l'area applicativa, e con quale punteggio |

`app_rect` è il motivo per cui i **ritagli non sono committati**: da fotogramma più rettangolo
il ritaglio si riproduce identico, e il repository non porta due copie della stessa immagine.

### I negativi sono tre gruppi, non uno

| cluster | cos'è | difficoltà |
|---|---|---|
| `altro-bper` | BPER Gestione Pratiche fuori dal processo P1, tipicamente Gestione Documentale | **difficile**: stesso applicativo, stesso stile, va rifiutato lo stesso |
| `altro-app` | un altro applicativo (istruttoria qtask, iSpace, il browser) | facile |
| `altro-nulla` | nero, transizione, popup | banale |
| `altro` | negativo proposto dal batch e non ancora suddiviso | da rivedere |

La distinzione non è cosmetica. La soglia di rifiuto era stata tarata su due negativi
sintetici, un desktop uniforme e un grigio pieno: entrambi `altro-nulla`. Una soglia che
supera quella prova può fallire completamente su `altro-bper`, che è il caso che conta.

### Nessuna etichetta è verità umana

`gemini` è la passata batch, `claude` è una revisione indipendente di un'altra famiglia di
modelli. Sono conservate **entrambe**, non fuse in un verdetto, perché il loro accordo è
l'unica cosa che dà fiducia in assenza di validazione umana.

L'accordo si misura a due granularità, e la distinzione è necessaria: dove il batch dice
`altro` e la revisione dice `altro-bper`, è lo **stesso giudizio a grana più fine**, non un
disaccordo. Confrontare le stringhe direttamente lo conta come errore e sottostima
gravemente l'accordo: sul primo foglio, 23 corrispondenze su 24 si leggevano come 4 su 24.
Per questo il registro riporta `agreement_page_vs_altro` accanto ad `agreement_exact_string`.

## Due estrazioni, e perché servono entrambe

I fotogrammi vengono da due passate con criteri opposti, e la differenza non è
accademica: hanno prodotto materiale complementare.

| | modo | copertura | fotogrammi | pagine bersaglio |
|---|---|---|---|---|
| radice | cambio-scena | tutta la durata | 505 + 984 | 6% |
| `fixed-1fps/` | passo fisso 1 fps | primi 10 minuti | 609 | **14%** |

**Il campionamento a passo fisso è l'unico che ha catturato le pagine con tooltip.**
Su 1489 fotogrammi selezionati per cambio-scena, le pagine 3, 6, 7 e 8 comparivano
**zero** volte. Con il passo fisso sono comparse 3, 6 e 7. La ragione è nel
docstring di `tools/extract_frames.py`: un tooltip copre lo 0,05% dello schermo e
dura un paio di secondi, quindi il rilevamento scena non scatta e la
deduplicazione percettiva rifonde ciò che resta nella pagina base.

Il cambio-scena resta prezioso per l'altro scopo: i negativi difficili (`altro-bper`,
BPER fuori processo) vengono quasi tutti da lì, perché spazzando la coda lunga delle
registrazioni intercetta le lunghe sessioni di gestione documentale.

## Copertura attuale, e cosa manca

| pagina | esempi | |
|---|---|---|
| 9 Note da Richiesta | 118 | sufficienti |
| 5 Gestione Fidi e Garanzie | 43 | sufficienti |
| 4 Elenco Soggetti | 34 | sufficienti |
| 1 Risultato ricerca | 13 | sufficienti |
| 2 Colonne estese | 8 | al limite |
| 3 Tooltip Evidenze | 2 | **insufficienti** |
| 7 Tooltip Garanzie riga 1 | 2 | **insufficienti** |
| 6 Tooltip Fidi | 1 | **insufficienti** |
| 8 Tooltip Garanzie riga 2 | 0 | **assente** |

Le quattro pagine scarse sono le quattro con tooltip, e la scarsità non dipende da
come sono state cercate. Un tooltip esiste solo mentre il cursore ci resta sopra, e
un operatore non ci passa: conosce già quei codici. Chi ha prodotto i nove
screenshot di riferimento in `mnt/data` ci è passato **apposta**, per documentarli.

Altre estrazioni hanno quindi rendimento marginale su quelle quattro. La strada è
chiedere screenshot mirati a chi usa l'applicativo.

## Attenzione all'accordo riportato nel registro

`review_status.agreement_*` misura **solo la prima passata**, quella con il prompt
scritto a mano, perché è quella i cui fotogrammi sono stati rivisti a mano
(83/95 corretti, 12 errori, quasi tutti "un altro applicativo scambiato per BPER").

Le passate successive girano su estrazioni diverse e non condividono fotogrammi con
la revisione, quindi **non hanno un accordo misurato**. Il numero nel registro non è
un giudizio sul catalogo di processo, e il campo `agreement_caveat` lo ripete lì.

## Screenshot mirati (2026-08-19)

`tooltips-rita/` contiene 17 catture dirette, a finestra intera, consegnate su
richiesta da chi usa l'applicativo: pratiche diverse fra loro, ognuna con un
tooltip aperto. Sono esattamente il materiale che le registrazioni non potevano
dare (un tooltip vive solo finche' il mouse ci sta fermo sopra, e un operatore
non ci passa: quei codici li conosce gia').

Le etichette dei nomi file sono state verificate immagine per immagine, e tre
sono state corrette (`manifest.json` ne tiene il verbale): 3a, 3c e 3d mostrano
il tooltip dell'ipoteca, quindi pagina 8. La 3a e' anche una lezione di modello:
in quella pratica esiste una sola garanzia e l'ipoteca sta in riga 1, quindi
l'identita' delle pagine 7/8 e' il **contenuto** del tooltip (CONSAP DR BIS vs
IPOTECA), non il numero di riga da cui il nome delle pagine deriva.

Con queste, ogni pagina del processo ha esempi reali.

## Screenshot mirati, secondo giro (2026-08-21)

`no-tooltip-rita/` contiene 21 catture dirette delle **pagine base senza
tooltip**, richieste per costruire un set di prototipi interamente dentro la
popolazione live (l'ADR 0011 documenta perche' mescolare popolazioni dentro una
classe distrugge i prototipi). Stessa operatrice, stessa forma dei 17 scatti
precedenti: finestra intera ~1890x1015.

Verificate immagine per immagine; due avvertenze dal verbale
(`no-tooltip-rita/manifest.json`):

- le coppie consegnate come "Note da richiesta 1b/1c" sono in realta' sulla tab
  **Note a Istruttoria**, che non e' tra le 9 classi: etichettate `altro-bper` e
  usate come negativi di processo nella misura dei prototipi;
- in alcune schermate lo zoom del browser e' ridotto per far entrare l'intera
  pagina (segnalato dall'operatrice): la finestra resta ~1890px ma il contenuto
  e' reso piu' piccolo. E' variabilita' reale della popolazione live.

La coppia chiuso/aperto di "Note da Richiesta" documenta che la pagina si
presenta con la sezione nota compressa: l'operatore clicca per espanderla, e le
due viste sono abbastanza diverse da servire entrambe al prototipo di classe 9.

Copertura per pagina dopo i due giri (scatti diretti + registrazioni):

| pagina | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| esempi | 19 | 13 | 7 | 38 | 47 | 7 | **4** | 8 | 121 |

La pagina 7 resta la piu' scarsa (un solo esemplare mirato). I manifesti curati
(`tooltips-rita/manifest.json`, `no-tooltip-rita/manifest.json`,
`reference-screens.json`, che verbalizza anche i nove riferimenti di mnt/data)
vengono fusi nel registro a ogni rebuild da `tools/build_frame_registry.py`,
cosi' rieseguire gli strumenti non li perde.
