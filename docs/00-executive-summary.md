# Sintesi per tutti

**poc-data-extraction** è un prototipo funzionante che legge gli screenshot di un applicativo bancario interno e trasforma ciò che vede sullo schermo in dati organizzati e verificabili, e poi si dà il voto da solo, dicendo anche quanto è costata la lettura.

Questa pagina è per chiunque: non serve essere sviluppatori. Se un termine non è chiaro, il [Glossario](11-glossary.md) lo spiega in parole semplici.

## Il problema che risolve

In BPER, gruppo bancario italiano, i dettagli di una pratica di credito (codici e nomi dei clienti, importi dei fidi, garanzie, dati su reddito e lavoro) vivono sulle schermate di un applicativo interno. Oggi, portare quelle informazioni altrove significa che una persona legge lo schermo e ridigita tutto a mano. È lento, noioso e facile da sbagliare.

## Come funziona, in parole semplici

Dai al software uno screenshot di una di quelle schermate, oppure lo lasci osservare in silenzio il monitor mentre un operatore sfoglia l'applicativo. Il software invia l'immagine a un servizio di intelligenza artificiale capace di guardare le immagini e rispondere a domande su di esse: la stessa tecnologia dietro i moderni assistenti conversazionali. Le domande arrivano in tre passi accurati: prima *"di chi è questa pratica?"*, per agganciare il cliente giusto; poi *"leggi tutto quello che c'è su questa pagina"*; infine *"riguarda solo le parti su cui non eri sicuro"*. Ogni risposta torna come una voce etichettata, con allegato un livello di confidenza.

Immaginalo come un impiegato diligente affiancato da un supervisore severo. L'impiegato trascrive ogni schermata in un modulo. Il supervisore poi confronta ogni voce con un foglio delle risposte corrette, la marca come giusta, sbagliata, mancante o inventata, e tiene il conto esatto di quanto è costata la lettura di ogni pagina: perché i servizi di AI dietro le quinte si pagano a consumo.

## Cosa ottieni

- Per ogni schermata: un record di dati strutturato, circa 45 campi, ciascuno con il proprio punteggio di confidenza.
- Per ogni esecuzione: un **report di accuratezza** (quali campi l'AI ha letto bene, campo per campo e in totale) e un **report dei costi** (quanto è costato elaborare ogni schermata).

Insieme, questi due report rispondono alla domanda per cui il progetto esiste: **l'AI può sostituire in modo affidabile la ridigitazione manuale di queste schermate bancarie, e a quale prezzo?**

## A chi serve

Agli ingegneri di Tri-tech solutions che costruiscono e valutano il sistema. È inclusa anche un'applicazione desktop che un operatore di banca potrebbe usare direttamente: osserva lo schermo, riconosce quale pagina è aperta, cattura i dati in automatico e suggerisce quale pagina aprire dopo.

## Lo stato, onestamente

È un proof of concept in sviluppo attivo, non un prodotto finito. Non ci sono test automatici, non c'è un installer, e i risultati si verificano a mano rispetto a un foglio di riferimento. Dimostra e misura un approccio; non è pronto da consegnare così com'è agli utenti finali.

## Dove andare adesso

- **Non sei tecnico?** Ti bastano questa pagina e il [Glossario](11-glossary.md).
- **Vuoi capire come funziona senza leggere codice:** [Panoramica](01-overview.md).
- **Sei uno sviluppatore:** parti dalla [Panoramica](01-overview.md), poi [Architettura](04-architecture.md) per come si incastrano i pezzi e [Getting Started](07-getting-started.md) per eseguirlo tu stesso.
