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
