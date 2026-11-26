# Cosa fa il progetto

Il data entrista legge le schermate della pratica di credito BPER. L’edge-agent riconosce la vista aperta, acquisisce i dati e li raggruppa in una riga per NDG. L’operatore può controllare e correggere i valori nella scheda **Dati estratti** prima di esportarli in Excel.

**Esempio.** Una pratica ha due garanzie. L’operatore può leggere la prima descrizione, passare alle note e tornare sulla seconda garanzia. La navigazione deve conservare quanto raccolto per quella pratica e rendere visibile la vista ancora da acquisire. La [guida al data entry](flusso-data-entry.md) descrive le azioni e i campi di ogni schermata.

## Come si legge una schermata

L’applicazione in uso legge i campi con un servizio VLM. Il riconoscimento della pagina serve a decidere quando acquisire una vista. Il batch confronta i valori con la verità revisionata nell’archivio e riporta accuratezza per campo, tempi e costi. [Flussi di elaborazione](05-workflows.md)

In parallelo il progetto mantiene due percorsi per la lettura su CPU, **RapidOCR + LiLT** e **OCRia-nano-1 di LlamaIndex + LiLT**. L’OCR localizza e trascrive il testo. LiLT usa testo e posizione per attribuire ogni parola a un campo. I risultati sul controllo e le parti ancora sperimentali sono nella [guida ai due percorsi](ocr-lilt.md).

## Dove proseguire

- [Passi dell’operatore e albero di navigazione](flusso-data-entry.md)
- [Avvio dell’applicazione](07-getting-started.md)
- [Archivio delle pratiche e valori corretti](../data/README.md)
