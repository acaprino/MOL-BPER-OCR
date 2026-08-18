# Catalogo dei processi

Un **processo** è una sequenza di schermate che un operatore percorre per portare a termine
un compito dentro un applicativo. Ogni processo sta in un file JSON, e i processi si
accodano in sequenza: `bper-p1` è il primo, e altri potranno seguirlo.

| file | id | applicativo | pagine |
|---|---|---|---|
| `bper-p1.json` | `bper-p1` | BPER Gestione Pratiche (PEF) | 9 |

## Perché esiste

Fino al 2026-08-18 il processo non era scritto da nessuna parte. Le sole descrizioni erano
i campi `hints` dentro `edge-agent/assets/templates/bper/prompts.json`, che descrivono le
singole pagine ma non dicono a quale **applicativo** appartengano, non prevedono che di
processi ce ne possa essere più d'uno, e non distinguono ciò che una pagina è da ciò che
una pagina *non* è.

Quel vuoto ha avuto un costo misurato. Etichettando 505 fotogrammi estratti da registrazioni
reali, il modello ha classificato come pagine BPER decine di schermate di un **secondo
gestionale** presente nelle stesse registrazioni (istruttoria mutui su
`qtaskbper.istruttore.it`), perché contiene campi chiamati "Nota ..." che somigliano a quelli
di BPER. Nessuna descrizione diceva che quell'applicativo non fa parte del processo.

## Struttura di un file di processo

- **`id`, `name`, `title`, `description`** — identità del processo.
- **`sequence`, `next`** — posizione nella catena. `next` è l'id del processo che segue, o
  `null` per l'ultimo.
- **`application`** — a quale applicativo appartiene il processo:
  - `url_contains`, `identifying_marks`: come si riconosce.
  - **`not_this_application`**: cosa può essere confuso con esso e non lo è. È il campo che
    mancava, ed è quello che paga di più: senza, un riconoscitore che deve scegliere fra
    N pagine sceglierà comunque la più somigliante anche quando l'applicativo è un altro.
- **`layout_families`** — gruppi di pagine che condividono il layout e differiscono per
  poco (le tre viste della lista, le quattro viste della pagina fidi). Esplicitarlo serve
  a chi tara un classificatore: sono le distinzioni difficili, e sono note in anticipo.
- **`pages[]`** — per ogni pagina: `order`, `name`, `slug`, `template`, `signature` (cosa
  la caratterizza), **`excludes`** (cosa la esclude), `fields` (i campi che vivono lì).
- **`catchall`** — la categoria di scarto, con la nota che un falso positivo consuma lo slot
  di una pagina per l'intero job.

## Navigazione: un grafo, non una lista

Un processo **non** è una sequenza da percorrere una volta sola. L'operatore si sposta
liberamente: torna a una pagina già vista, la riapre per leggere un tooltip diverso, salta a
un altro passo e rientra. `sequence` e `order` descrivono il percorso *suggerito*, non
quello percorso.

`navigation` descrive come ci si muove davvero, su **tre livelli**, e il fatto decisivo è
che tutti e tre sono **leggibili dallo schermo**: la fase corrente non va inferita da un
modello di transizioni, sta scritta nell'interfaccia.

| livello | cosa contiene | dove si legge |
|---|---|---|
| `app-tabs` | Ricerca Pratica, Elenco Pratiche, PEF 2.0 - Pratica N | barra schede in alto |
| `navigator` | Verifica Preliminare, **Istruttoria**, Proposta, Parere, Delibera, e i passi della fase aperta | colonna "Navigatore" a sinistra |
| `content-tabs` | Gestione Fidi e Garanzie, Note a Istruttoria, Note da Richiesta, Dettaglio BPI | riga di schede sopra il contenuto |

Il navigatore porta anche lo **stato** di ogni voce: spunta verde per i passi conclusi,
pallino arancione sulla voce corrente, matita su quelli da fare. Leggere quello stato dice
a che punto del processo ci si trova, senza doverlo ricostruire.

Ogni pagina dichiara la propria posizione nei tre livelli in `location`, più
`within_page_state` per ciò che distingue varianti della stessa posizione (lo scorrimento
della tabella, quale tooltip è aperto). Si vede subito che le pagine 5, 6, 7 e 8 hanno
`location` **identica** e differiscono solo per `within_page_state`: sono la stessa
schermata con un popup diverso, ed è per questo che sono le più difficili da distinguere.

### Conseguenza sulla cattura

`capture_policy.revisiting_allowed` è `true`, e non è un dettaglio: le pagine 6, 7 e 8 si
raggiungono **solo** tornando sulla 5 e aprendo un tooltip diverso. Un sistema che rifiuta
di riacquisire una pagina già vista non può raccoglierle.

Il codice oggi non rispetta questo modello, e il file lo dichiara in
`capture_policy.implementation_gap` invece di lasciarlo scoprire: `captured_page_types` è a
sola aggiunta, e la guida procede in ordine lineare. Allinearlo è una modifica di
comportamento e merita la sua decisione.

## Rapporto con `prompts.json`

Questo catalogo è la **formalizzazione**, non ancora il file che il programma legge a runtime:
l'edge-agent continua a leggere `edge-agent/assets/templates/bper/prompts.json`. I due
divergono di proposito su un punto, documentato nel campo `note` della pagina 9.

Collegare il runtime a questo catalogo è una modifica di comportamento e merita una
decisione a sé, con il suo ADR: finché non avviene, chi modifica una descrizione deve
sapere che sta toccando due file.

## Aggiungere un processo

1. Nuovo file `<id>.json` con la stessa struttura.
2. Impostare `sequence`, e aggiornare `next` del processo che lo precede.
3. Aggiungere la riga alla tabella qui sopra.

Il candidato naturale è il gestionale di istruttoria mutui che compare nelle registrazioni:
oggi è materiale da respingere, e diventerebbe un processo a sé con le proprie pagine.
