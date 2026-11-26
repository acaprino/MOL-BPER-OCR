# 0037 — Conservare per pratica le viste acquisite e suggerire il passo successivo

**Stato** Accettato il 26 novembre 2026.

## Contesto

Il worker riarmava già la cattura quando cambiavano i pixel. La guida, invece, segnava i nomi di pagina in un insieme valido per tutta la sessione e proponeva la prima voce ancora assente dal catalogo. Se un operatore apriva Elenco Soggetti della seconda pratica, la guida poteva considerarlo già acquisito nella prima. Tornando dalle note a un tooltip, proponeva comunque di ricominciare dall’elenco.

## Decisione

La visita corrente segue il riconoscimento, la stabilità e l’esito dell’estrazione. La copertura delle viste usa il prefisso di risultati che il client ha già pubblicato in ordine di cattura, con le stesse identità NDG del consolidamento. La GUI riceve dal worker l’intero stato da mostrare. Durante una transizione può consultare la copertura dell’ultimo NDG identificato con un’etichetta esplicita.

La prossima vista dipende dalle visite ancora utili e dalla posizione su tre livelli (scheda applicativa, passo del Navigatore, scheda interna). Un tooltip può essere dichiarato non applicabile e poi ripristinato per un solo NDG. Ogni vista rimane rivisitabile anche dopo il completamento. Il registro distribuito con l’eseguibile mantiene la titolarità dei nomi e dell’ordine delle pagine. [Regole e casi operativi](../navigazione-edge.md)

## Conseguenze e verifica

L’operatore può iniziare a metà percorso, saltare avanti o indietro e recuperare una pratica nello stesso job. Un nuovo job riparte senza copertura. Se il frame corrente ha un NDG illeggibile, si applica la convenzione già usata per i dati: la pratica precedente nell’ordine di acquisizione, oppure una copertura provvisoria in attesa del primo NDG. Un errore di riconoscimento resta possibile e una visita acquisita può contenere campi da correggere.

I [test del ciclo di cattura](../../tests/test_bper_capture_lifecycle.py) esercitano cambi di pratica, salti, risposte invertite, errore e ripresa, esclusione e ritorno di un tooltip. I [test della guida Qt](../../tests/test_capture_navigation_ui.py) coprono le azioni e l’identità mostrate all’operatore. I [test della finestra](../../tests/test_main_window.py) verificano arresto e chiusura con risultati in transito.
