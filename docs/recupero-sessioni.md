# Riprendere il lavoro dopo un arresto

Una cattura diventa recuperabile quando l’agent ne conferma l’ingresso in coda. Da quel momento puoi passare alla pagina successiva anche se l’estrazione è ancora in corso. Se il processo cade prima della conferma, torna alla schermata in banca e acquisiscila di nuovo.

Il salvataggio comprende il contesto di ogni scatto e il numero pratica già verificato in quel momento. Se il computer si arresta mentre leggi la 42 e rimane una cattura della 31 da elaborare, al riavvio quella cattura riparte nel contesto della 31. Un esito con una testata incompatibile rimane nell’archivio e viene escluso dal fascicolo e dall’Excel.

## Se si interrompe il processo di estrazione

Ogni screenshot accettato ha già una copia cifrata con pagina e progressivo. Se il processo che legge le immagini termina inaspettatamente, lo smistatore ritenta una volta ogni lettura interrotta nella posizione originale. La finestra resta utilizzabile. Se fallisce anche il secondo tentativo, la tabella Cattura segnala l’errore e l’archivio conserva i pixel per il riavvio. Gli esiti già salvati mantengono la loro posizione. La lettura dal vivo usa il VLM configurato. Le misure offline di RapidOCR e OCRia-nano con LiLT sono descritte nella [guida ai due percorsi](ocr-lilt.md).

## Alla riapertura

1. Apri l’agent con lo stesso account Windows. In **Dati estratti** seleziona la sessione interrotta e verifica la riga dell’NDG. Mantieni disponibile il provider per le letture rimaste in sospeso.
2. Se avevi una cella aperta, scegli **Riprendi modifica** e premi **Invio** per confermare il testo. **Scarta bozza** lo elimina. L’Excel contiene i valori confermati. Durante la digitazione **Salvataggio…** indica che la scrittura è in corso. Un arresto forzato in quell’istante può perdere gli ultimi caratteri. Il testo già confermato su disco è recuperabile. Se la scrittura fallisce, controlla l’ultimo testo salvato prima di reinserire la modifica.
3. In **Cattura**, seleziona la sessione precedente e avvia la cattura. Apri la pratica nell’applicativo BPER. La guida ritrova le viste acquisite, escluse e riaperte per quell’NDG. Il riconoscimento della pagina sul monitor riparte dall’immagine attuale.
4. Controlla le viste mancanti e i dati. Attendi gli ultimi risultati prima dell’export definitivo. Durante la scrittura dell’Excel puoi continuare a lavorare. I dati arrivati dopo l’inizio del salvataggio restano disponibili per un nuovo export. La chiusura normale attende la fine della scrittura. Se Excel tiene aperto il file precedente, chiudilo e ripeti l’esportazione, oppure scegli un altro nome.

| Interruzione | Cosa recuperi |
|---|---|
| Il processo termina mentre il provider elabora la pagina | L’immagine già confermata viene riletta al riavvio con lo stesso progressivo. Una richiesta già ricevuta dal provider può comportare una seconda chiamata. |
| Un risultato successivo arriva prima di uno precedente | Il risultato completato resta registrato. Appena si risolve la cattura precedente, entrambi tornano disponibili in ordine. |
| La sessione contiene correzioni o una bozza | I valori confermati prevalgono sulle letture successive. La bozza conserva anche il testo ancora da confermare. |
| La copia principale è illeggibile | Se la replica supera le verifiche e corrisponde alla revisione confermata, l’agent recupera e avvisa. In presenza di copie incompatibili conserva i file e interrompe l’apertura. |
| Manca spazio o la replica diventa inaccessibile | La cattura si ferma. Lascia aperta la finestra ed esporta su un percorso funzionante i risultati già disponibili. Ripristina l’accesso al disco e riapri l’agent. |
| Fallisce soltanto una copia storica | La GUI segnala il problema. Controlla lo spazio nella cartella di backup. La replica in tempo reale continua a proteggere le operazioni che l’agent conferma. |

## Dove si trovano le copie

| Impostazione | Utilizzo |
|---|---|
| `EDGE_AGENT_RECOVERY_DIR` | Cartella primaria. Il default Windows è `%LOCALAPPDATA%\MutuiOnline\BPER-EdgeAgent\recovery`, nel profilo dell’operatore. |
| `EDGE_AGENT_BACKUP_DIR` | Il default è la sottocartella `backup` accanto a `EdgeAgent.exe`. Da sorgente è `src/edge-agent/backup/`. Un percorso relativo parte dalla cartella dell’agent anche quando viene avviato da un collegamento. Per una replica su un secondo disco si può impostare un percorso assoluto. |
| `EDGE_AGENT_PRIORITY=above_normal` | Facoltativo su Windows. Richiede priorità CPU superiore alla normale per il processo. La ripresa dei dati funziona anche con la priorità predefinita. |

Nel pacchetto portable trovi `EdgeAgent\backup\` già vuota. L’agent scrive la replica in `backup/sessions-backup.sqlite3` e le copie storiche in `backup/history/`. Se aggiorni un’installazione che aveva la replica accanto all’archivio primario, l’agent la verifica e può usarla per ricostruire i file. Le copie storiche precedenti restano recuperabili dalla loro cartella `history` originale.

L’archivio conserva i dati delle sessioni anche dopo l’export. Per impostazione predefinita non c’è una scadenza delle sessioni. La postazione deve avere spazio sufficiente e le cartelle di lavoro devono seguire i tempi di conservazione stabiliti per le pratiche. Con la configurazione Windows i dati sono cifrati con DPAPI nel profilo dell’utente. Per il recupero ordinario occorrono lo stesso account e la stessa postazione. Se si guasta il disco che contiene anche il profilo Windows, per leggere la replica serve poter recuperare le chiavi DPAPI di quel profilo. L’IT deve verificare questa possibilità prima di considerare coperta la perdita della postazione. [Requisiti di decrittazione Windows](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata) L’Excel esportato contiene dati leggibili e va salvato nella destinazione aziendale prevista.

## Esportazione di emergenza senza provider

Con l’agent chiuso, da PowerShell nella cartella del progetto, indica una cartella di destinazione nuova. Il comando esporta il prefisso già leggibile di ogni sessione e produce un riepilogo delle catture ancora pendenti e delle bozze. Al rilancio normale si possono completare le letture interrotte.

```powershell
python src/edge-agent/edge_agent.py --recovery-export "D:\Lavoro\Export-recuperato"
```

## Recuperare una versione precedente

La replica viene scritta a ogni modifica confermata. La cartella `history` conserva inoltre le ultime tre copie storiche verificate. Durante il lavoro l’agent le aggiorna in background a intervalli di almeno 15 minuti quando ci sono modifiche. La data nel nome della copia è in UTC. Una versione storica può precedere le ultime acquisizioni.

Per creare subito una copia e poi ripristinare una versione precisa, usa una cartella di destinazione ancora inesistente. Sostituisci il percorso di esempio con quello della copia effettiva.

```powershell
python src/edge-agent/edge_agent.py --recovery-snapshot
python src/edge-agent/edge_agent.py --recovery-restore "E:\BPER\backup\history\snapshot-..." "D:\Lavoro\BPER-ripristinato"
```

Chiudi l’agent prima di cambiare archivio. In una nuova finestra PowerShell seleziona il percorso ripristinato e una **nuova cartella di replica** sul disco di backup. I percorsi delle copie originali restano disponibili per tornare all’ultima versione.

```powershell
$env:EDGE_AGENT_RECOVERY_DIR = 'D:\Lavoro\BPER-ripristinato'
$env:EDGE_AGENT_BACKUP_DIR = 'E:\BPER\backup-ripristinato'
python src/edge-agent/edge_agent.py
```

Per il pacchetto Windows gli stessi argomenti si passano a `EdgeAgent.exe`. Per una prova periodica usa un archivio sintetico e verifica, dopo il ripristino, una cella corretta, una vista esclusa e una cattura rimasta in lavorazione. [Decisione tecnica e test](adr/0039-recupero-sessioni.md)
