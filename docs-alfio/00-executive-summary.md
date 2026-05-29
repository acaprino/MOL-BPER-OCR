# Sintesi per tutti

**poc-data-extraction legge per te le schermate dell'applicativo bancario e le trasforma, in automatico, in una tabella di dati pulita e verificabile.**

Questa pagina è per chiunque: non serve essere sviluppatori. Se un termine non è chiaro, il [Glossario](11-glossary.md) lo spiega in parole semplici.

## In una frase

Guarda gli screenshot dell'applicazione bancaria BPER e trascrive le informazioni presenti (codici cliente, nomi, fidi, garanzie, redditi) in una forma strutturata, così nessuno deve ricopiarle a mano.

## Il problema che risolve

Gli operatori che usano l'applicativo di gestione del credito di BPER leggono sempre le stesse schermate e ridigitano i valori in altri sistemi. È lento e si sbaglia facilmente. Questo progetto fa la lettura al posto loro.

## Come funziona, in parole semplici

Immaginalo come un assistente velocissimo che:

1. Guarda una schermata e capisce prima di tutto **di chi** è la pratica (codice e nome del cliente), così non si confonde nulla.
2. Legge tutta la schermata e annota ogni valore che trova.
3. Torna indietro e rilegge solo le parti su cui era incerto, ingrandendole.
4. Per ogni valore dice quanto è sicuro, e tiene il conto di quanto è costata la lettura.

La "lettura" la fa un'intelligenza artificiale capace di interpretare le immagini (chiamata Vision Language Model). Il progetto può usare l'AI di OpenAI oppure quella di Google.

## Cosa ottieni

- Un file strutturato con ogni campo letto, ciascuno con un punteggio di confidenza da 0 a 1.
- Un **report di accuratezza**: se fornisci le risposte corrette (un file di "ground truth"), il sistema si auto-valuta campo per campo.
- Un **report dei costi**: quante chiamate all'AI sono state fatte e il prezzo stimato.

## A chi serve

- **Personale operativo della banca** che deve estrarre i dati da queste schermate senza ridigitarli.
- **Sviluppatori** che costruiscono strumenti simili "da screenshot a dati" e cercano un esempio concreto.
- **Decisori** che valutano se la lettura automatica via AI è abbastanza accurata ed economica da adottare.

## Tre modi di usarlo

- **A lotti (batch):** gli indichi una cartella di screenshot salvati e li elabora tutti insieme.
- **App desktop:** scegli i file a mano da una finestra semplice.
- **Agente dal vivo:** osserva il tuo schermo mentre lavori in BPER e cattura ogni pagina in automatico quando la riconosce.

## Lo stato, onestamente

È un **proof of concept**, non un prodotto finito. Funziona e produce risultati utili, ma non ha test automatici, non ha un installer e per girare richiede una chiave dell'AI e dei dati di esempio. I limiti e i dubbi aperti sono elencati in [Domande Aperte](08-open-questions.md).

## Dove andare adesso

- **Non sei tecnico?** Ti bastano questa pagina e il [Glossario](11-glossary.md).
- **Vuoi capire come funziona senza leggere codice:** [Come funziona, sotto il cofano](12-come-funziona-sotto-il-cofano.md).
- **Vuoi il giro delle funzionalità:** [Funzionalità](02-features.md).
- **Vuoi eseguirlo:** [Getting Started](07-getting-started.md).
- **Vuoi il quadro tecnico:** [Architettura](04-architecture.md).
