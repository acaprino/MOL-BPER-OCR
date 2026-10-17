# poc-data-extraction: documentazione ufficiale

Il progetto estrae campi strutturati dalle schermate bancarie BPER. Lo stesso motore
serve il batch da file, la GUI Tkinter e l'edge-agent PyQt6 per la cattura dal vivo.
L'edge-agent riunisce le informazioni in una riga per pratica ed esporta in Excel;
la valutazione di accuratezza richiede un CSV di riferimento separato.

## Scegli il percorso di lettura

- **Capire il progetto:** [Sintesi per tutti](00-executive-summary.md) →
  [Panoramica](01-overview.md) → [Funzionalità](02-features.md).
- **Installare e avviare:** [Avvio e sviluppo](07-getting-started.md) →
  [Guida alla configurazione](10-configuration-guide.md).
- **Modificare il codice:** [Architettura](04-architecture.md) →
  [Workflow](05-workflows.md) → [Modello dei dati](06-data-model.md),
  con la tabella dei punti d'intervento in [Avvio e sviluppo](07-getting-started.md).
- **Integrare il motore in Python:** [API Python](12-python-api.md) →
  [Modello dei dati](06-data-model.md) → [Decisioni architetturali](adr/README.md).

## Capitoli

| # | Documento | Contenuto |
|---|---|---|
| 0 | [Sintesi per tutti](00-executive-summary.md) | Scopo, uso e limiti in parole semplici. |
| 1 | [Panoramica](01-overview.md) | Contesto del progetto, utenti e confini. |
| 2 | [Funzionalità](02-features.md) | Estrazione, cattura, valutazione ed esportazione. |
| 3 | [Tech Stack](03-tech-stack.md) | Librerie e responsabilità, dipendenze applicative e di sviluppo. |
| 4 | [Architettura](04-architecture.md) | Componenti, dipendenze, configurazione e confini tra thread. |
| 5 | [Workflow](05-workflows.md) | Pipeline, routing, visite, conferme, ordine ed errori. |
| 6 | [Modello dei dati](06-data-model.md) | Schemi, metadati, raggruppamento per NDG e formato Excel. |
| 7 | [Avvio e sviluppo](07-getting-started.md) | Prerequisiti, comandi, build, test e punti d'intervento. |
| 8 | [Domande aperte](08-open-questions.md) | Limiti e decisioni ancora da chiarire. |
| 9 | [Anatomia del progetto](09-project-anatomy.md) | Directory, file di configurazione e script. |
| 10 | [Guida alla configurazione](10-configuration-guide.md) | Impostazioni, operazioni e risoluzione dei problemi. |
| 11 | [Glossario](11-glossary.md) | Termini bancari e tecnici usati nella guida. |
| 12 | [API Python](12-python-api.md) | Firme e contratti di batch, pipeline, client locale, consolidamento ed export. |
| — | [Decisioni architetturali](adr/README.md) | Contesto, alternative e conseguenze delle decisioni accettate. |
| — | [How It Works](how-it-works.md) | Riferimento dei meccanismi interni in inglese. |
| — | [Addestramento locale LiLT](../src/training/README.md) | Preparazione da revisione umana, separazione delle pratiche e modello caricabile su CPU. |
