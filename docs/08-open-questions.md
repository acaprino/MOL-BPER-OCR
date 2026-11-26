# Questioni aperte

## Operatore e navigazione

| Questione | Perché serve una conferma |
|---|---|
| Da quale comando BPER si apre la Scheda Privati, e come si torna alla pratica corretta? | Le catture la mostrano già aperta. Per estendere la guida occorrono il passaggio reale e un riscontro sull’identità del titolare. |
| Come riconoscere tutte le viste su finestre molto larghe? | Nel replay locale restano quattro errori fra varianti di Elenco Pratiche e otto astensioni su Soggetti, Fidi e tooltip. Le colonne fisse nell'elenco e il testo piccolo rendono difficile distinguere le varianti. [Misure per tipo di errore](navigazione-edge.md#riscontro-del-26-novembre-2026) |
| Quando due fascicoli dello stesso NDG devono dare righe distinte? | L’edge-agent conserva una riga per NDG e sessione. Per distinguere i fascicoli servirebbe un identificativo di pratica affidabile in cattura. |

Il percorso osservato, le varianti opzionali e l’esito di ogni acquisizione sono descritti nella [guida al data entry](flusso-data-entry.md) e nella [navigazione dell’edge-agent](navigazione-edge.md).

## Modelli e accuratezza

- Confermare con l’operatore le diciture dei tooltip e i sinonimi di Tipo da aggiungere, in particolare quando un’abbreviazione consente di ricostruire un valore.
- Consolidare gli script del lettore Nano sperimentale in un percorso riproducibile da un nuovo clone. Verificare qualità e latenza end-to-end di entrambe le catene sui frame reali prima dell’adozione nell’edge-agent. [Stato dei modelli](ocr-lilt.md)
- Concordare la soglia di accettazione del provider VLM su più pratiche. La baseline storica del settembre 2026 è riferita a una sola pratica e a un determinato modello. [Come confrontare le estrazioni](07-getting-started.md)
- Verificare i modelli del catalogo con le revisioni effettive degli SDK e mantenere il listino dei costi. Una voce senza prezzo produce una stima nulla.
- Misurare quanto il pretrattamento dell’edge-agent cambia la lettura rispetto al percorso da file. [Architettura](04-architecture.md)

## Sviluppo e distribuzione

- Restano da definire ambienti dell’operatore supportati, aggiornamento delle installazioni portable, approvazione delle release, visibilità dei risultati dei test e responsabilità sul contratto esterno dei campi.
- Valutare il futuro della cattura generica, del formato dei risultati in errore e del dispatch degli aggiornamenti Tkinter al thread UI.
- L’incidente del luglio 2026 ha comportato la riscrittura della cronologia. Restano da confermare revoca della vecchia chiave e aggiornamento dei cloni precedenti. Il pacchetto e i file di configurazione richiedono una gestione esplicita delle credenziali. [Chiavi API e cronologia Git](../README.md#chiavi-api-e-cronologia-git)

Le decisioni già prese su dataset, merge, pagine sorgenti, routing e packaging si consultano nell’[indice degli ADR](adr/README.md).
