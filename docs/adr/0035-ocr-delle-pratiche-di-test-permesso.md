# 0035 — La lettura OCR delle pratiche di test è permessa

- Data: 2026-11-24
- Stato: Accettato. Supera in parte l'ADR 0027 per la lettura OCR delle pratiche di test.

## Contesto

L'ADR 0027 teneva sigillate le 13 pratiche di test: non si leggevano con l'OCR né si aprivano finché
non c'era un candidato congelato. L'ADR 0034 registrò come violazione la lettura di `51027430`.

Il 2026-11-24 il responsabile del progetto ha chiesto perché l'OCR fosse vietato e ha deciso che si
può fare OCR su qualsiasi pratica, con qualsiasi motore e in qualsiasi luogo, Modal compreso. Leggere
le schermate non rivela la verità: la prova cieca la protegge solo l'uso dei valori del test per
scegliere o regolare un modello.

## Decisione

- La lettura OCR delle schermate delle pratiche di test, e il loro caricamento su Modal o su un altro
  servizio per leggerle, sono permessi senza aspettare il candidato congelato.
- Non cambia, perché la decisione non lo tocca: i valori di verità del test non servono a scegliere o
  regolare un modello (ADR 0027, `data/README.md`). Il test resta l'unica prova cieca.
- `include_test` in `load_screens()` e in `read_archive()` resta un'opzione esplicita, non un
  divieto: evita solo che una pratica di test entri in una lettura per distrazione.
- Una lettura di test che ha guidato una scelta si annota nel registro di `data/README.md`.

## Conseguenze e verifica

Nessun comportamento del codice cambia, quindi nessun test nuovo: `test_training_dataset.py` continua
a coprire il rifiuto di una schermata di test senza `include_test`. Aggiornati `data/README.md`,
`src/training/README.md`, `CLAUDE.md`, `AGENTS.md` e lo stato dell'ADR 0027.
