# Come l’edge-agent segue la pratica

La scheda **Cattura → Guida alla pratica** risponde a tre domande. Quale vista è sul monitor? Quale gesto conviene fare adesso? Quali viste mancano a questo fascicolo? La guida segue l’operatore anche quando passa direttamente alle note o riapre una pratica precedente. Per i gesti nel gestionale e i valori da copiare vedi la [guida al data entry](flusso-data-entry.md).

## Vista sul monitor e copertura della pratica

| Situazione | Cosa mostra la guida | Effetto sulle viste mancanti |
|---|---|---|
| Cambiano i pixel | Riconoscimento in corso. Il vecchio NDG può figurare accanto all’elenco come **ultimo NDG**. | L’elenco resta consultabile con la propria identità. |
| Il router riconosce una vista | Nome della vista e attesa di stabilità. | La sola presenza a video lascia la vista da acquisire. |
| Il fotogramma stabile entra nella coda | Estrazione in corso. L’operatore può proseguire. | La visita rimane pendente. |
| L’estrazione termina e sono disponibili i risultati precedenti | Vista acquisita, identità e prossima azione. | La vista passa tra le acquisite dopo l’associazione al numero pratica. |
| La pagina è estranea, illeggibile o l’estrazione fallisce | Richiesta di mostrare PEF o di riprovare. | La copertura già confermata resta disponibile. |
| Si apre un secondo fascicolo e poi si torna al primo | Copertura del numero pratica nella testata del dettaglio. | Ciascuna pratica conserva le proprie viste acquisite e non applicabili nella sessione. |

## Quando cambia la pratica

Se passi direttamente da una finestra PEF a un’altra, controlla il **numero pratica** nella guida. Quando il numero corrisponde a un fascicolo già aperto, la guida indica **Pratica ripresa** e suggerisce la prima vista utile tra quelle ancora da acquisire. Le elaborazioni avviate nell’altra finestra proseguono con il loro progressivo originale.

Su Windows il worker controlla la finestra sul monitor scelto prima e dopo lo scatto. Un cambio di finestra o del titolo della sessione VDI, un’interruzione della cattura o una pausa di almeno un minuto richiedono una nuova verifica. Uno scatto durante il passaggio viene ripetuto. Il titolo rimane in memoria. Se la VDI cambia contenuto dentro la stessa finestra, l’identificazione si basa sulla testata PEF leggibile. Quando il numero già salvato compare con un NDG diverso, la guida chiede di verificare entrambi e i dati in conflitto rimangono fuori dall’Excel.

| Cosa fa l’operatore | Cosa succede ai dati |
|---|---|
| Torna in ricerca, scorre i risultati o apre un tooltip dell’elenco | Il fascicolo precedente resta disponibile. Una riga di elenco con numero pratica leggibile può contribuire a quel fascicolo quando il suo dettaglio viene aperto. |
| Seleziona una riga e apre il dettaglio PEF | La guida attende il numero pratica della testata. Un numero nuovo apre una nuova riga e una checklist propria, anche per lo stesso NDG. Riaprire un numero già lavorato recupera la sua checklist. |
| Acquisisce le Note mentre il numero pratica è illeggibile | La lettura resta salvata. In **Coda** compare **Letta · pratica da associare**. Mostrare di nuovo la testata prima di cambiare pratica permette di associare le note alla visita. |
| Si passa a un altro risultato prima di identificare la visita | La nota incerta rimane nell’archivio della sessione e fuori dall’Excel. Riaprire il fascicolo corretto e riacquisire la nota. |

**Esempio.** La pratica 31 e la 42 hanno entrambe NDG 100. Accodi le Note della 31 e passi alla 42. In **Coda → Pratica** le Note conservano il numero 31. Anche se la 42 termina prima, il risultato verificato delle Note aggiorna la 31. Riaprendo la 31 ritrovi le sue viste mancanti. In **Dati estratti** il suggerimento sulla cella NDG mostra il numero pratica. In Excel lo trovi nel commento della stessa cella.

Per ogni scatto l’agent salva subito la sessione, il progressivo e il contesto di acquisizione. Se conosce già il numero pratica lo salva insieme ai pixel. Al primo scatto di una nuova selezione la coda mostra **Da verificare · contesto N**. La prima testata valida identifica il fascicolo per quel contesto. Se una testata successiva indica un altro numero dentro la stessa VDI, l’esito compare come **Esclusa · pratica diversa allo scatto**. Lascia visibile la nuova pagina perché venga riacquisita nel proprio contesto. Le letture anonime rimaste nel vecchio contesto non seguono la nuova pratica. Il recupero dopo un arresto applica le stesse regole.

L’agent osserva le schermate. Il passaggio dall’elenco al dettaglio segnala l’apertura di un risultato. Se l’elenco passa troppo velocemente, due numeri pratica diversi nelle testate permettono comunque di distinguere i fascicoli. Una lettura senza numero interposta tra due fascicoli diversi rimane da associare. Nell’elenco con più righe, apri quella corretta e mostra il dettaglio. Le sessioni storiche che registravano soltanto l’NDG conservano il raggruppamento originario.

## Come sceglie il passo successivo

Il catalogo PEF distingue le viste base **1, 2, 4, 5, 9** e quattro viste condizionali con tooltip **3, 6, 7, 8**. Il registro fornisce nomi e ordine. Per ciascuna vista aperta, la guida privilegia le operazioni che si raggiungono con meno cambi di contesto.

| Distanza dalla vista corrente | Esempio |
|---|---|
| Stessa pagina e stessa scheda interna | Da Fidi al tooltip della descrizione |
| Stesso passo del Navigatore, altra scheda interna | Da Note da Richiesta alla scheda Fidi |
| Stessa scheda applicativa, altro passo del Navigatore | Da Elenco Soggetti a Gestione Fidi e Garanzie |
| Altra scheda applicativa | Dal dettaglio a Elenco Pratiche per recuperare Creazione |

A parità di distanza, una vista base precede un tooltip. L’ordine di catalogo risolve l’ulteriore parità. **Non applicabile** esclude un tooltip per il solo fascicolo selezionato. **Ripristina** lo rende nuovamente disponibile. Riaprire davvero quel tooltip e acquisirlo ne conferma la presenza anche dopo un’esclusione. Il suggerimento è un aiuto per l’operatore. La classificazione del frame usa ciò che è visibile. [Registro del processo](../processes/README.md)

## Risposte tardive, arresto e tabella

- Se una pagina figura acquisita per errore, selezionala e premi **Da riacquisire**. La guida riapre la vista per quella pratica fino alla prima cattura successiva confermata. I risultati già in coda al momento della scelta lasciano la vista aperta. Le celle estratte si verificano e correggono in **Dati estratti**.
- Il worker associa ogni invio a sessione, numero progressivo e visita. Una risposta tardiva aggiorna la copertura nella sequenza originale. Solo la risposta della visita attuale può cambiarne lo stato sul monitor. [Ordine di acquisizione](adr/0013-risultati-nell-ordine-di-acquisizione.md) · [Esito per visita](adr/0014-acquisizione-per-visita-con-esito.md)
- **Ferma** disabilita i comandi di cattura mentre la finestra continua a rispondere. Una chiamata al router già iniziata può durare fino alla risposta o al timeout. Alla fine del worker la GUI riabilita **Avvia** e conserva la lista delle viste aggiornata fino all'arresto. Le estrazioni già accodate possono ancora aggiornare **Dati estratti**. Alla chiusura l'operatore decide cosa fare delle sessioni da esportare.
- La tabella riceve i risultati pubblicati in ordine. Se è nascosta, prepara l’aggiornamento per quando viene aperta. Se è visibile, riunisce i risultati arrivati insieme e aggiorna le righe cambiate. Un editor di cella aperto mantiene la precedenza sul ridisegno.
- Con **Acquisisci ora** sullo stesso monitor, l'agent si riduce a icona e attende tre secondi. Porta PEF in primo piano, mostra la vista scelta e mantienila visibile fino allo scatto. Puoi riaprire l'agent dalla barra delle applicazioni. Il **Registro attività** conserva le ultime 1.000 righe nella GUI.

La Scheda Privati contribuisce ai 45 campi ma ha un proprio applicativo e resta fuori dalle nove viste del router. Alla riapertura la guida recupera le visite e le decisioni per fascicolo. Attende una nuova immagine per identificare la pagina attualmente sul monitor. [Ripresa della sessione](recupero-sessioni.md) Il riconoscimento su video e desktop reali si misura separatamente dal comportamento della guida. [Prove di cattura e replay](../bper-emulator/live_test_README.md)

## Ripetere il cambio di pratica

Lo [scenario ritorno-pratica](../bper-emulator/live_scenarios/ritorno-pratica.json) passa dalle Note ai Fidi, apre i tooltip, cambia NDG e rientra nella prima pratica. Per generare una registrazione nuova su una postazione con il simulatore, eseguire dalla radice:

```powershell
python bper-emulator/live_test.py record --scenario bper-emulator/live_scenarios/ritorno-pratica.json --out outputs/ritorno-pratica --db outputs/ritorno-pratica.sqlite3
python bper-emulator/live_test.py replay --recording outputs/ritorno-pratica --out outputs/ritorno-pratica-report
```

In `report.md` confrontare per ogni sosta la vista attesa, la classe adottata e le viste mancate. Il punteggio del replay accorpa le tre varianti di Elenco Pratiche. Per verificare proprio lo scorrimento e il tooltip occorre controllare anche la colonna **Adopted as**. I valori iniettati dal simulatore verificano il raggruppamento per NDG.

### Riscontro del 26 novembre 2026

Su una registrazione ricomposta da due pratiche sintetiche nella finestra 1912 × 1030 al 90%, il worker ha ricevuto 204 fotogrammi a 3 fps. Il confronto usa le stesse 16 soste in PEF, di quattro secondi ciascuna, con un ritorno da Note a Fidi e il passaggio dalla prima pratica alla seconda e di nuovo alla prima. Una sosta aggiuntiva sulla Home è rimasta fuori dal catalogo in entrambe le prove. Per isolare la navigazione, il simulatore ha fornito i valori estratti.

| Esito del classificatore locale | Prima | Dopo |
|---|---:|---:|
| Variante della schermata esatta | 4 | 4 |
| Elenco Pratiche corretto, variante di scorrimento o tooltip errata | 4 | 4 |
| Vista Fidi o Garanzie classificata come Note | 4 | 0 |
| Vista rimasta da riconoscere | 4 | 8 |

La correzione evita di segnare Note come acquisita sulla base di una tabella finanziaria. Il riconoscimento automatico di Soggetti, Fidi e delle singole varianti di elenco su finestra larga richiede ancora lavoro. Sulle nove immagini di dettaglio delle due pratiche reali di controllo, la correzione ha tenuto entrambe le vere Note e ha portato da sette a zero le altre pagine classificate come Note. [Decisione e limiti](adr/0038-evidenze-del-router.md)

In una prova separata con finestra Qt, worker e classificatore reali, la sorgente video riproduceva le viste di riferimento e l'estrattore forniva due NDG sintetici. La sequenza **Note A → Fidi A → Soggetti B → Note A** ha ripristinato le due viste della pratica A e ha prodotto due righe nell'Excel esportato. Questa prova verifica l'identità e la navigazione della GUI. La lettura dei valori bancari ha un proprio [protocollo di valutazione](ocr-lilt.md).

Una prova aggiuntiva sul formato largo ha usato un ritaglio guidato dalle intestazioni. Ha recuperato tre soste sintetiche su Soggetti, ma nessuna delle due schermate Soggetti reali di controllo ha raggiunto il margine di accettazione di 0,10. Per la stessa vista Fidi senza popup, due ritagli hanno indicato due tooltip diversi. Il classificatore mantiene quindi la possibilità di lasciare la vista da riconoscere. L’operatore può indicarla con **Acquisisci ora**.
