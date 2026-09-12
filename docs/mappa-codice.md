# Mappa del codice

Percorsi di lettura della [documentazione ufficiale](INDEX.md) per orientarsi
tra architettura, funzionamento, dati e API.

## Architettura: tre ingressi, un motore di estrazione

[Architettura](04-architecture.md) presenta CLI, GUI Tkinter ed edge-agent,
i moduli condivisi e il diagramma dei componenti.
L'[anatomia del progetto](09-project-anatomy.md) aiuta a trovare i file.

## Ingressi utilizzabili

[Per iniziare](07-getting-started.md) raccoglie installazione, avvio delle tre
interfacce e distribuzione portable. La [guida alla configurazione](10-configuration-guide.md)
distingue le impostazioni del motore da quelle del router.

## Come scorre una singola estrazione

Il [workflow della pipeline](05-workflows.md#pipeline-di-estrazione-multi-pass)
descrive anchor, passaggio principale, retry, ritagli e post-processing,
con i limiti del budget di chiamate e la gestione degli errori.

## Cattura dal vivo: ordine ed esito sono due contratti diversi

Il [workflow dell'edge-agent](05-workflows.md#cattura-dal-vivo-delledge-agent-modalità-bper)
segue acquisizione, visita, accodamento, esito, nuovo tentativo e scatto manuale.
Il [modello dei dati](06-data-model.md#ordine-di-acquisizione-e-disponibilità-dei-risultati)
spiega come i risultati diventano disponibili in ordine di acquisizione.

## Dati che attraversano i confini

Il [modello dei dati](06-data-model.md) descrive il risultato dell'estrazione,
i metadati, i campi canonici, il consolidamento per NDG e il formato Excel.

## Riferimento delle API principali

Il capitolo [API Python](12-python-api.md) contiene firme e contratti delle
interfacce utilizzabili dal codice.

### Batch di file

Vedi [API batch](12-python-api.md#batch-di-file).

### Pipeline per una singola immagine

Vedi [API della pipeline](12-python-api.md#pipeline-per-una-singola-immagine).

### Client asincrono dell'edge-agent

Vedi [API del client asincrono](12-python-api.md#client-asincrono-delledge-agent).

### Consolidamento ed esportazione

Vedi [API di consolidamento ed export](12-python-api.md#consolidamento-ed-esportazione).

## Dove intervenire e cosa verificare

La [guida agli interventi](07-getting-started.md#dove-intervenire-e-cosa-verificare)
associa ogni modifica ai file e ai controlli pertinenti.
Le [decisioni architetturali](adr/README.md) spiegano i vincoli da conservare.
