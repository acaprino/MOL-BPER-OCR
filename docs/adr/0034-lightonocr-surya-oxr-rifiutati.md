# 0034 — Rifiutati LightOnOCR-3, Surya e OXR-1.0 per leggere e dividere le schermate

- Data: 2026-11-22
- Stato: Rifiutato

## Contesto

Il 2026-11-22 si sono guardati quattro modelli aperti come alternativa alla lettura RapidOCR (Stadio A di
`src/training`) o come aiuto di layout sulle schermate:

| Modello | Cosa fa | Licenza dei pesi |
|---|---|---|
| LightOnOCR-3-0.8B | VLM che legge una pagina in markdown, 0,85 miliardi di parametri | Apache-2.0 |
| surya_layout2 | solo layout (riquadri, etichette, ordine di lettura) | AI Pubs Open RAIL-M modificata |
| surya-ocr-2.5 | VLM da 0,69 miliardi per layout, OCR e tabelle; llama.cpp su CPU, GGUF da 629 MB più 207 MB di `mmproj` | stessa licenza di surya_layout2 |
| OXR-1.0-DFINE-layout | solo layout, D-FINE da 19,5 milioni di parametri, GGUF F32 da 78 MB, eseguibile solo con il runtime CrispEmbed | OXR: Apache-2.0 con condizioni aggiuntive |

Nessuno ha un export ONNX; la CPU del PC di sviluppo (Core Ultra 7 155H, 22 thread, 31,5 GB di RAM) non
ha GPU NVIDIA.

## Cosa si è misurato

Solo due modelli sono stati provati; gli altri due sono stati scartati senza prova (surya_layout2 e
surya-ocr-2.5).

- **LightOnOCR-3-0.8B su CPU** (transformers, float32, circa 4,2 GB di RAM), una schermata da 2.054 token
  in ingresso: caricamento con download dei pesi 68 s, poi oltre 9 minuti di generazione senza
  terminare; la prova è stata interrotta. Due kernel (`causal_conv1d`, `flash-linear-attention`) giravano
  nella versione di riserva lenta, quindi il tempo è pessimistico. Il risultato del testo non c'è.
- **OXR-1.0-DFINE-layout su Modal** (CPU 4 thread, CrispEmbed alla revisione
  `893293336fd51c2d4c2086bd93b986c8b8a45624`, build portabile AVX2, pesi con SHA-256 verificato), nove
  schermate da circa 1913x1077:
  - 16-17 s a pagina (codificatore circa 16 s, decodificatore circa 0,6 s), contro 1,4-2,3 s che la
    documentazione di CrispEmbed dichiara per lo stesso modello su 4 thread. La causa dello scarto non
    è verificata.
  - Nessun riquadro `Table` in nessuna delle 18 letture. Di solito un solo `Picture` a tutta pagina; in
    `soggetti-01` e `note-01`, le due viste a occhio, anche il pannello dell'applicazione come `Picture`,
    la riga della data come `Text`, schede del browser e barra delle applicazioni come intestazione e
    piè di pagina. La tabella Elenco Soggetti e il blocco «Nota della richiesta» non sono stati trovati.
  - La seconda lettura di ogni schermata, incollata su una tela 1920x1080, non vale: le schermate erano
    già grandi quanto la tela e sono state tagliate. Vale solo la lettura «com'è».

## Decisione

Nessuno dei quattro entra. Lo stack resta RapidOCR (Stadio A) e LiLT. Per la dipendenza dall'inquadratura
restano `frame_normalize` (ADR 0001) e le variazioni di inquadratura dell'addestramento (`_reframe()`).

- LightOnOCR: troppo lento su CPU per leggere le schermate qui, senza ONNX né tempi pubblicati.
- OXR: non trova le tabelle sulle schermate dell'applicazione (addestrato su documenti) ed è molto più
  lento di quanto dichiarato.
- Surya: non provato; le soglie della licenza (oltre 5 milioni di dollari di ricavi o di finanziamenti, o
  un prodotto che compete con quelli del licenziante, senza eccezione di ricerca per quest'ultimo caso)
  non sono state valutate per l'organizzazione che usa il progetto.
- OXR ha soglie proprie (uso commerciale libero solo sotto 2 milioni di dollari di ricavi e di
  finanziamenti, citazione obbligatoria in un servizio online): la licenza è stata riconosciuta dallo
  sviluppatore che ha chiesto la prova, per la sola prova, non per un uso.

Non si conclude che questi modelli siano scadenti in generale: non hanno dato un risultato utile qui, a
questo costo.

## Quando riaprire

Con una GPU a disposizione, con un export ONNX ufficiale o tempi su CPU pubblicati, o con la licenza
chiarita. Ogni nuova prova usa pratiche di addestramento o di controllo.

## Come è stata fatta la prova, e una violazione

La prova ha letto una pratica di test, `51027430`, contro l'ADR 0027 (le pratiche di test restano
sigillate: non si leggono con l'OCR né si aprono): LightOnOCR su `gestione-fidi-01`, OXR su tutte e nove le
schermate, caricate su Modal, e due immagini di risultato aperte. Nessun parametro di modello è stato
scelto su quella lettura, ma il suo esito ha pesato su questa decisione: chi legge la misura finale su
`51027430` deve saperlo. I file temporanei e la cache dei pesi sono stati cancellati; il caricamento su
Modal non è cancellabile dal progetto.

## Conseguenze e verifica

Nessun comportamento cambia, quindi nessun test. Il progetto non contiene codice di CrispEmbed, né
pesi, né dipendenze nuove.
