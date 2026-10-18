# 0023 — Ricostruire i campi Fidi dalla prima riga della tabella

- Data: 2026-10-18
- Stato: Accettato

## Contesto

I campi `n_fido`, `rapporto`, `descrizione`, `scadenza`, `importo_euro` e `tipo_op`
hanno un solo valore per schermata, ma la tabella `FIDI` può avere più righe (F1, F2).
Il valore revisionato è sempre quello della riga più in alto tra quelle visibili:
nelle pratiche di addestramento lo mostra 52102599, l'unica con due righe; nella
schermata di test con la tabella fatta scorrere la prima riga visibile è F2, e il
valore è F2. LiLT assegna il ruolo alle parole di ogni riga che riconosce come fido,
comprese a volte le righe della tabella
`GARANZIE`, e `decode_fields()` univa tutte le parole dello stesso ruolo: `n_fido`
diventava `F1 F2 F1 F2` e `rapporto` conteneva i numeri di più righe. Nessuna
pratica di validazione ha una tabella con più righe, quindi la scelta dell'epoca non
vedeva questo errore; lo mostrava la pratica di test 51531667.

## Decisione

`decode_fields()` prende come riga di riferimento la parola più in alto predetta come
`n_fido`. La riga termina a metà strada verso la prima parola successiva allineata
nella stessa colonna, predetta o no (di solito il numero del fido seguente). Le
parole dei sei ruoli Fidi oltre quel limite non entrano nei valori ricostruiti. Le
celle su più righe visive restano intere, perché il limite è a metà tra due righe
della tabella. Senza un `n_fido` predetto, o senza una parola successiva nella
colonna, la ricostruzione resta quella precedente. È lo stesso principio già usato
per le righe dei soggetti: i marcatori di riga vengono dalla geometria OCR e non
diventano predizioni.

La versione della metrica passa a `strict-v3-fidi-first-row`: le stesse predizioni
danno valori ricostruiti diversi, quindi i rapporti precedenti non sono
confrontabili con i nuovi senza ricalcolo.

## Conseguenze e verifica

Ricostruendo con le etichette revisionate al posto delle predizioni, nessuno dei
sei campi cambia su nessuna delle 113 schermate, sia con l'OCR del bundle sia con
quello A1: la regola non taglia valori approvati. Sulle predizioni salvate dei sei
modelli addestrati il 2026-10-18 la validazione non perde alcun campo (ne guadagna
uno su un modello), mentre il test migliora da 2 a 18 campi. Il test era già stato
consultato, e la regola è stata individuata guardando i suoi errori: per questa
regola non è più una stima indipendente.

Restano fuori dalla regola gli errori di riconoscimento del ruolo: una prima riga
non etichettata, o un `tipo_op` mai predetto. Servono più esempi di tabelle con più
righe nell'addestramento.

`test_training_evaluation.py` copre la prima riga, la cella su più righe visive e la
riga chiusa da un numero di fido non predetto.
