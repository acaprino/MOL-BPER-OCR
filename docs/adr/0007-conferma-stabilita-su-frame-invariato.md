# 0007 - Confermare la stabilità con un frame invariato, non con una seconda risposta del router

- **Stato:** Accettato
- **Data:** 2026-08-18
- **Interessa:** `edge-agent/stability.py`, `edge-agent/workers/capture/bper_capture_worker.py`
- **Test:** `tests/test_stability.py`, `tests/test_bper_capture_framing.py`
- **Nasce da:** [0006](0006-router-llm-come-predefinito.md)

## Contesto

`StabilityTracker` dichiara stabile una pagina dopo **due osservazioni concordi**
(`min_matches = 2`) e almeno 2 secondi di permanenza (`min_seconds = 2.0`). Le soglie
sono state scritte per un classificatore locale che risponde in millisecondi: a 3 FPS,
"due osservazioni" significa tenere ferma la schermata per 2 secondi, che è quanto
`min_seconds` chiede comunque.

[0006](0006-router-llm-come-predefinito.md) ha sostituito quel classificatore con un
router che costa una chiamata VLM per risposta. `route()` è sincrona dentro
`_capture_once()`, quindi il ciclo si blocca per tutta la durata della chiamata, e le
stesse due soglie hanno cambiato significato: **due osservazioni concordi ora
significano due round-trip di rete.**

Misurato su una sessione reale (job `25ea903f`, 08:32:50-08:33:17), gli intervalli fra
risposte consecutive del router sono stati **12s, 5s, 5s**. Nessuna pagina è stata
acquisita in 25 secondi di cattura, e l'export è fallito con "nessun risultato". Il
tracker si era comportato esattamente come progettato: adotta un candidato, tollera uno
scarto, alla seconda pagina diversa resetta e adotta la nuova. Nessuna pagina è mai
stata vista due volte di fila, perché fra un'osservazione e la successiva passavano
5-12 secondi e l'operatore nel frattempo si spostava.

Il router funzionava: quattro risposte, tutte plausibili, incluso un rifiuto corretto
("Altro / Non riconosciuto" a 1.000) su un frame non normalizzato. È la conferma a non
arrivare mai.

## Decisione

Un **frame identico al precedente** conta come osservazione ulteriore del candidato
corrente. `StabilityTracker.confirm(now)` fa questo, ed è un no-op quando non c'è
candidato: un frame invariato non dice nulla su una pagina che nessuno ha ancora
identificato.

Nel ciclo di cattura, un frame duplicato con un candidato in corso non interroga più il
router: chiama `confirm()`, e se la pagina diventa stabile la acquisisce riusando
l'esito dell'ultimo routing. La coda di acquisizione è stata estratta in `_acquire()`,
condivisa fra le due strade che possono dichiarare stabile una pagina.

Il pHash di deduplicazione esisteva già, gira a ogni frame e misura letteralmente "la
schermata non è cambiata". Era già lì la prova che la seconda chiamata al router stava
surrogando.

## Il compromesso, esplicito

La conferma è **prova più forte che lo schermo sia fermo** e **prova più debole che
l'etichetta sia giusta**, perché a sostenerla resta una sola risposta del router.

È accettato perché ciò che le due osservazioni proteggevano è la cattura a metà
scorrimento, e quella la protegge `min_seconds`, che continua ad applicarsi: `confirm()`
non scavalca il ritardo anti-scorrimento. Quel che si perde è la ridondanza sul
contenuto dell'etichetta, che il router LLM copre per conto suo con una confidenza
esplicita e con la categoria di rifiuto "Altro / Non riconosciuto".

## Alternative valutate

**Abbassare `min_matches` a 1.** Non basta e non è nemmeno equivalente: `min_seconds` si
misura dalla prima osservazione, quindi con una sola osservazione il tempo non
maturerebbe mai senza un secondo giro. E toglierebbe la protezione anti-scorrimento
invece di spostarla su una prova migliore.

**Rendere `route()` asincrona.** Il ciclo continuerebbe a campionare a 3 FPS mentre una
chiamata è in volo. Risolve la latenza percepita, ma apre la porta a molte chiamate VLM
concorrenti sullo stesso schermo, cioè sostituisce un problema di attesa con uno di
costo. Resta valida se la latenza dovesse dare fastidio anche dopo questa modifica.

**Alzare `route_retry_seconds`.** Agisce solo sul throttling dei duplicati, che non è
ciò che bloccava l'acquisizione.

## Conseguenze

Una pagina si acquisisce con **una** chiamata al router invece di due, circa 5 secondi
dopo che compare invece di 10-24. Il costo per pagina si dimezza.

Dopo l'acquisizione `_last_routed_page` viene azzerato insieme al tracker, così un frame
ancora duplicato non riacquisisce la stessa pagina: ricade sul percorso normale e
incontra il ramo "già acquisita".

Un'etichetta sbagliata ora consuma uno slot con una sola conferma invece di due. Il
recupero resta manuale via "Acquisisci ora", che non controlla l'appartenenza a
`captured_page_types` (vedi la correzione in coda a
[0001](0001-normalizzazione-inquadratura-frame.md)).
