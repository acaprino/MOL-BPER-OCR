# Catalogo dei processi

Un **processo** è una sequenza di schermate che un operatore percorre per portare a termine
un compito dentro un applicativo. Ogni processo sta in un file JSON, e i processi si
accodano in sequenza: `bper-p1` è il primo, e altri potranno seguirlo.

| file | id | applicativo | viste di riferimento |
|---|---|---|---|
| `bper-p1.json` | `bper-p1` | BPER Gestione Pratiche (PEF) | 9 |

Per seguire una pratica, dalla ricerca fino alla verifica delle 45 colonne, consulta il
[percorso dell’operatore](../docs/flusso-data-entry.md). I nove template PEF rappresentano
quattro pagine sorgenti con diverse posizioni di scorrimento e tooltip. La quinta sorgente,
Scheda Privati, fornisce 13 campi da un applicativo separato.

`bper-p1/transizioni/` conserva le schermate di navigazione fra le pagine (Scheda Privati, Scheda Immobile,
Gestione GEP, FICS) che documentano il processo; il codice non le legge. Fino al 2026-11-22 stavano fra gli
asset dell'edge-agent.

## Perché esiste

Fino al 2026-08-18 il processo non era scritto da nessuna parte. Le sole descrizioni erano
i campi `hints` dentro `src/edge-agent/assets/templates/bper/prompts.json`, che descrivono le
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
- **`catchall`** - la categoria di scarto per una vista ambigua o esterna al processo.

## Navigazione fra le viste

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

Il Navigatore mostra la **voce aperta** e l’**avanzamento della lavorazione**. La spunta
verde indica un passo concluso, il pallino arancione il passo in corso e la matita quelli
da fare. Per individuare la vista consultata, guarda la voce selezionata e il titolo del
contenuto. Un operatore può tornare su un passo concluso.

Ogni pagina dichiara la propria posizione nei tre livelli in `location`, più
`within_page_state` per ciò che distingue varianti della stessa posizione (lo scorrimento
della tabella, quale tooltip è aperto). Si vede subito che le pagine 5, 6, 7 e 8 hanno
`location` **identica** e differiscono solo per `within_page_state`: sono la stessa
schermata con un popup diverso, ed è per questo che sono le più difficili da distinguere.

### Conseguenza sulla cattura

`capture_policy.revisiting_allowed` è `true`. Sulla scheda Fidi l’operatore può mostrare
la tabella di base, aprire un tooltip, richiuderlo e puntare un’altra riga. Una nuova visita
può riattivare la cattura anche quando porta lo stesso nome di una vista già elaborata.
Un tooltip può mancare se la pratica non contiene la riga o il relativo testo. Un esito
di elaborazione richiede comunque la verifica dei valori da parte dell’operatore.
Le regole di acquisizione e della guida sono descritte nella
[navigazione dell’edge-agent](../docs/navigazione-edge.md) e nell’[ADR 0014](../docs/adr/0014-acquisizione-per-visita-con-esito.md).

## Rapporto con `prompts.json`

Gli strumenti di etichettatura offline usano `bper-p1.json` per descrivere l’applicativo e
distinguere le viste. Il registro dei template dell’edge-agent legge
[`prompts.json`](../src/edge-agent/assets/templates/bper/prompts.json). I due cataloghi
identificano la pagina 9 dalla scheda attiva e dal riquadro **Nota della richiesta**, anche
quando è chiuso. Il campo `note` registra il motivo per cui la descrizione precedente
confondeva documenti e note. I campi citati nelle descrizioni delle viste aiutano a
riconoscerle. I campi e le colonne dell’export si verificano nelle
[definizioni canoniche](../src/extraction/field_definitions.py).

## Aggiungere un processo

1. Nuovo file `<id>.json` con la stessa struttura.
2. Impostare `sequence`, e aggiornare `next` del processo che lo precede.
3. Aggiungere la riga alla tabella qui sopra.

Il candidato naturale è il gestionale di istruttoria mutui che compare nelle registrazioni:
oggi è materiale da respingere, e diventerebbe un processo a sé con le proprie pagine.
