# 0039 – Recupero locale delle sessioni dell’operatore

**Accettata il 26 novembre 2026.** Sostituisce la scelta di conservare i dati soltanto in memoria nella [ADR 0033](0033-correzioni-dell-operatore-e-tema-proprio.md).

## Decisione

Il client desktop assegna a ogni cattura una coppia (sessione, progressivo). Prima di confermarla registra i pixel già preparati in PNG e i metadati necessari al replay. Un’estrazione riuscita sostituisce il record pendente con il risultato. In caso di arresto vengono rieseguite le sole letture ancora pendenti. La tabella, la guida e l’Excel consumano lo stesso prefisso contiguo di risultati. La GUI accoda la scrittura del testo fuori dal thread grafico e segnala quando è ancora pendente. Una correzione confermata e la rimozione della sua bozza sono una sola modifica.

SQLite effettua un’unica transazione su archivio, replica e marcatore di revisione tramite database collegati, journal di rollback e sincronia `EXTRA`. Un lock di sistema limita la scrittura a un processo per archivio. All’apertura l’agent confronta identità, revisione e checksum e controlla che il profilo possa decifrare i dati. I payload Windows usano DPAPI in ambito utente. Su POSIX il client usa AES-GCM con una chiave in un file privato. Le chiavi logiche sono nomi di servizio, sessioni e progressivi. Il successo della duplicazione dipende anche dalle garanzie di scrittura offerte dai dispositivi. [Transazioni fra database collegati in SQLite](https://www.sqlite.org/lang_attach.html) · [Protezione DPAPI per utente](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)

La destinazione predefinita della replica è `backup/` nella cartella dello script o dell’eseguibile. Il pacchetto ZIP include la cartella vuota. L’archivio primario resta nel profilo dell’operatore. Lo storico conserva tre versioni indipendenti nella destinazione della replica. Un worker crea e verifica la nuova copia prima della rotazione. Il recupero esplicito scrive in una nuova directory. L’Excel viene preparato in un file temporaneo nella stessa cartella, sincronizzato e pubblicato attraverso sostituzione atomica. Un arresto forzato durante l’export può lasciare il file temporaneo nella cartella scelta.

## Verifica

- [Archivio e arresto durante la transazione](../../tests/test_recovery_store.py)
- [Arresto del processo durante l’estrazione, ordine dei risultati e salvataggio della bozza](../../tests/test_session_recovery.py)
- [Storico, rotazione e ripristino](../../tests/test_recovery_history.py)
- [Esportazione senza modello, chiave o interfaccia grafica](../../tests/test_recovery_export.py)
- [Copertura e decisioni dopo il riavvio](../../tests/test_bper_capture_lifecycle.py)
- [Uso operativo e configurazione del secondo disco](../recupero-sessioni.md)

Il 26 novembre 2026, su Windows e Qt offscreen, la prova ha inviato 40 battiture a una cella con 12 nuove immagini sintetiche da 1000 × 700 pixel in elaborazione. Con scrittura sincrona la chiamata di salvataggio nel thread GUI arrivava a 327 ms al 95º percentile. Nella GUI modificata il gestore del tasto ha restituito il controllo in 1,21 ms al 95º percentile, con massimo 1,52 ms. Un timer da 40 ms ha avuto un intervallo massimo di 59 ms. Alla riapertura risultavano salvati tutti i 40 caratteri e i 13 fotogrammi, inclusa la cattura iniziale. Il tempo del gestore misura la reattività della finestra. L’avviso di salvataggio resta attivo durante la scrittura effettiva su disco.

Una prova distinta ha terminato un processo sintetico durante una chiamata all’estrattore. Alla riapertura è ripartita quella sola cattura e il risultato successivo già pronto è ricomparso al proprio posto. I test sull’archivio hanno interrotto il processo anche durante una transazione reale con journal di rollback presente. Su Windows è stato verificato anche il recupero fra i volumi C: e D: dopo l’uscita forzata del processo e la rimozione simulata del file primario. Le prove riguardano l’arresto del processo e la perdita o la corruzione simulata di un file. Il guasto fisico di una postazione resta un caso da verificare sulla configurazione di backup dell’installazione.

Suite completa da sorgente su Windows, con Python 3.11 nell’ambiente di prova: 1.417 test superati, 20 saltati e 9 falliti. Tutti e nove i fallimenti riguardano il simulatore HTTP e il rifiuto del socket di loopback `WinError 10013`. L’avvio Qt offscreen è riuscito sia dall’entry point desktop sia da `main.py --gui`. Il pacchetto distribuibile e la postazione bancaria restano da verificare.
