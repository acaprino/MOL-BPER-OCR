# 0017 - Identità NDG condivisa tra valutazione e consolidamento

- **Stato:** Accettato
- **Data:** 2026-10-16
- **Interessa:** `extraction/normalization.py`, `edge-agent/practice_consolidation.py`
- **Test:** `tests/test_normalization.py`, `tests/test_practice_consolidation.py`

## Contesto

Il consolidamento live trattava già l'NDG come identificatore con
`normalize_ndg()`. La classificazione dei campi e la guardia di mismatch della
valutazione usavano invece `norm_number_str()`, che interpreta quantità e
arrotonda a due decimali. La stessa pratica poteva così essere raggruppata
correttamente dal vivo e confrontata con un'identità diversa nel report.

Gli esempi distinguono i due contratti: `12.345` e `12345` identificano lo
stesso NDG, ma il normalizzatore numerico rende il primo `12.35`.
`12345/A` e `12345/B` devono restare distinti; eliminare il suffisso li rende
entrambi `12345.00`. Anche un NDG lungo deve essere confrontato esattamente,
senza passare dalla similarità prevista per il testo libero.

## Decisione

`normalize_ndg()` vive in `extraction/normalization.py`. Il consolidamento la
importa da lì, conservandola disponibile anche attraverso l'import storico da
`practice_consolidation`. La usano sia `classify_field()` per le cinque chiavi
`ndg`, `ndg_1`, `ndg_2`, `ndg_3`, `ndg_4`, sia `dataset_mismatch_guard()`.

La funzione restituisce `None` per un valore non letto, conserva soltanto
lettere ASCII e cifre, uniforma le lettere in maiuscolo e rimuove gli zeri
iniziali solo quando l'identificatore risultante è interamente numerico.
Perciò `0012345` equivale a `12345`, mentre `0012345/A` conserva gli zeri.
Gli NDG normalizzati vengono confrontati per uguaglianza, senza fuzzy matching.

Restano le regole di nullità e i relativi stati della classificazione. La
guardia mantiene il fallback ai soggetti quando manca l'NDG di testata e il
confronto della denominazione tramite `norm_text()`. Un identificativo non
letto non costituisce da solo un mismatch. `importo_euro` e `n_fido`
mantengono il confronto con `norm_number_str()`.

## Alternative valutate

- **Correggere il normalizzatore delle quantità.** Renderebbe ambigui importi
  e identificatori e cambierebbe i confronti numerici estranei al problema.
- **Copiare la regola nel valutatore.** Risolverebbe gli esempi correnti ma
  lascerebbe due implementazioni dell'identità NDG da mantenere coerenti.
- **Applicare fuzzy matching agli identificativi lunghi.** Una sola cifra o
  un suffisso diverso può identificare un soggetto diverso, anche con
  similarità elevata.

## Conseguenze e verifica

RAW, FILTERED e consolidamento condividono ora la stessa identità NDG.
Questo corregge il confronto delle letture, senza cambiare il testo estratto
o garantire che un NDG riconosciuto corrisponda ai pixel della schermata.
L'euristica che raggruppa le pratiche per NDG resta invariata.

`test_ndg_classification_accepts_equivalent_identifiers` e
`test_ndg_classification_rejects_distinct_identifiers` proteggono separatori,
zeri, suffissi e identificativi lunghi su tutte le cinque chiavi. I test
`test_dataset_guard_accepts_equivalent_ndg_identifiers`,
`test_dataset_guard_rejects_distinct_ndg_identifiers` e
`test_dataset_guard_uses_subject_ndg_when_header_ndg_is_unread` coprono la
guardia. Gli altri casi di `test_normalization.py` preservano nullità,
denominazione e confronto delle quantità; `test_practice_consolidation.py`
protegge il raggruppamento live.
