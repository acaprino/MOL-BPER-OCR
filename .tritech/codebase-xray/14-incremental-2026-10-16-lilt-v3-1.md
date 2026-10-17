# Ground truth 3.1 per LiLT — addestramento e verifica

Aggiornamento mirato al pacchetto offline `training/`, ai suoi quattro file di test,
alle dipendenze, alla guida e all'ADR 0022. Revisione effettiva osservata:
`3be17a8ae7c15a4b33183044c70da9fe5591470f`, branch `develop`, più questi file non
committati. Non include né attribuisce a questa attività le modifiche applicative
concorrenti delle Fasi 3–4, gli incrementi 11–13 o la migrazione X-ray staged.
I run storici conservano il proprio snapshot e i propri risultati.

## Stato dell'esecuzione

Esperimento completato: un solo addestramento GPU, otto epoche, modello scaricato e
verificato su CPU. Test finale: **127/192 valori corretti (66,15%)**, contro 124/192
(64,58%) dei risultati storici LiLT v2, ricalcolati con la stessa metrica. Guadagno
netto di tre campi, +1,56 punti percentuali: **miglioramento insufficiente per
l'adozione**, nessuna integrazione o sostituzione del motore dell'edge-agent.
La separazione delle pratiche è rispettata; il confronto con v2 resta esplorativo
perché non conosciamo tutte le sue sovrapposizioni di addestramento.

L'utente ha confermato l'uso dei dati in risposta alla domanda specifica su Modal:
«Ma sono dati del cliente che ci paga per allenare il suo sistema». Il controllo
successivo ha autorizzato l'esecuzione. La cronologia conserva il primo rifiuto,
la conferma e gli errori recuperati:
[execution-status.json](checks/2026-10-16-lilt-v3-1/execution-status.json).
Esecuzione effettiva: [Modal](https://modal.com/apps/alfio-caprino/main/ap-F5mwZELp5C5XOBmo6GhZ5h).
Il payload comprende parole OCR, coordinate, etichette, valori revisionati e
manifest; PNG e workbook sono rimasti locali. Nessuna chiamata nuova a Gemini.

## Fonti e integrità

- Excel approvato: `mnt/riscontro-2026-10-07/revisione/Revisione_ground_truth_v3_1.xlsx`.
- SHA-256 Excel: `483e1ab4f48b47de757a13b564ab4a3c102e2c6f39675721b2698da8ce3b20d4`.
- Cache OCR: `baselines/2026-10-07-riscontro-12-pratiche/prove/ocr-locale-rapidocr/rapid_v6_small_1x.json`.
- Bundle: `mnt/training/ground-truth-v3.1/`, ignorato da Git.
- Impronta canonica di esempi e ordine classi: `11b88186d4f777e4b3175bb2b1e8a45037f5a0a7cd170e1c844bd2f68bc0ed93`.
- Audit indipendente: [dataset-audit.json](checks/2026-10-16-lilt-v3-1/dataset-audit.json).

Tutti i 1.008 valori effettivi coincidono tra Excel, JSON e CSV. L'originale del
revisore, la revisione 3.1, i 113 PNG e il cache OCR rimangono invariati. I 32.040
token OCR mantengono esattamente il testo sorgente. Nessuna formula nelle righe
revisionate. Gli script storici di generazione della revisione non sono modificati.

## Flusso e interfacce aggiornati

1. `training.schema.vocabulary()` legge i soli dati letterali dal proprietario
   canonico `extraction/fields.py`, senza importare il runtime VLM. I 45 campi
   diventano 36 ruoli semantici, più `O`; i ruoli dei soggetti sono condivisi e il
   decoder ripristina il numero di riga.
2. `training.dataset.read_reviewed_truth()` rifiuta bozze, formule, chiavi duplicate,
   campi sconosciuti e pratica incoerente. La colonna P è autorevole anche quando
   vuota; non torna al valore vecchio. `N/D` resta testo visibile.
3. `training.alignment.align_screen()` usa regioni di campo, inchiostro dell'immagine
   e testo del cache. Il matching permissivo serve soltanto a localizzare; la
   supervisione richiede testo esatto. Mantiene la punteggiatura OCR realmente
   presente tra parole abbinate. Non inserisce cifre o segni mancanti.
4. `apply_supervision()` produce etichette per campi esatti, oppure parole verificate
   nelle note e nella data di validazione. Gli altri token incerti sono `IGNORE`;
   conflitti tra ruoli non ricevono una classe arbitraria. I valori attesi completi
   rimangono disponibili anche quando esclusi dalla perdita.
5. `audit_splits()` controlla pratica, tutti gli NDG dei soggetti, hash dei file e
   hash dei pixel. `seal_dataset()` lega esempi, ordine delle classi e sorgenti al
   manifest. `validate_reviewed_dataset()` rifiuta corpus incompleti o alterati.
6. `training.model.encode_chunks()` normalizza i box sull'intera immagine, conserva
   tutte le parole e supervisiona solo il primo sottotoken. `train_model()` prepara
   copie aumentate solo del train, sceglie l'epoca con F1 di validazione e valuta
   il test dopo la scelta. Parte dal LiLT pubblico, senza i vecchi pesi BPER.
7. `training.modal_train` è l'unico accesso remoto di questo esperimento. Salva una
   versione nuova, scarica pesi/tokenizer ordinari e produce impronte dei file.
   `predict()` usa lo stesso percorso su CPU e GPU. La cattura e il motore VLM
   dell'edge-agent restano quelli esistenti.
8. `training.evaluation.decode_fields()` ricostruisce testo dalle parole predette,
   senza leggere i valori attesi o gli allineamenti. I marcatori numerici OCR nella
   colonna NDG conservano la posizione delle righe anche quando un NDG non viene
   predetto: non diventano un NDG emesso. I nomi su più righe restano nello stesso
   soggetto. `evaluate_predictions()` include tutti i campi revisionati della
   popolazione scelta e separa disponibilità OCR, F1 e accuratezza del valore.

La nuova guida è [training/README.md](../../training/README.md), richiamata da
`docs/INDEX.md`; la decisione è [ADR 0022](../../docs/adr/0022-addestramento-lilt-da-revisione-umana.md).
Le dipendenze del percorso offline sono nel solo `requirements.txt` di radice.
Non è introdotto un client remoto nel flusso BPER dell'edge-agent.

## Dati, copertura e limiti

| Insieme | Pratiche | Schermate | Valori revisionati |
|---|---:|---:|---:|
| Train | 8 | 75 | 670 |
| Validazione | 2 | 16 | 146 |
| Test | 2 | 22 | 192 |

Nessuna sovrapposizione per pratica, soggetto o immagine. Le due pratiche che
condividono il soggetto FONDO rimangono entrambe nel train. Tutte le 37 classi hanno
token di addestramento. Supervisione: 844 campi completi, 17 parziali; 55 differenze
OCR e 13 allineamenti incerti sono mascherati; 79 valori sono assenze. Audit:
zero differenze testuali nei campi completamente supervisionati e zero parole
parzialmente verificate assenti dal testo revisionato.

I tredici campi Scheda Privati compaiono in una sola pratica, collocata nel train;
anche i due tooltip CONSAP non hanno positivi nel test. Per questi quindici campi
non c'è una misura indipendente di generalizzazione. Alcune classi hanno un solo
token positivo: la presenza nella tabella classi non dimostra affidabilità.

## Riscontri e confronto sul test

Metrica `strict-v2-punctuation-spacing`: conserva cifre, suffissi, punteggiatura e
confini tra parole; normalizza solo rappresentazioni documentate. Nessuna tolleranza
6/8 o confronto approssimativo dà una risposta corretta. Gli spazi adiacenti a segni
di punteggiatura già presenti sono equivalenti. Non si inseriscono segni mancanti.

| Provenienza | Corretti, incluse assenze | Totale | Accuratezza |
|---|---:|---:|---:|
| LiLT v2, output storico ricalcolato | 124 | 192 | 64,58% |
| Nuovo LiLT 3.1, test dopo selezione su validazione | 127 | 192 | 66,15% |
| Gemini, output storico ricalcolato | 180 | 192 | 93,75% |
| Ruoli supervisionati esatti + decoder, controllo diagnostico | 179 | 192 | 93,23% |

Il risultato dei ruoli supervisionati è un controllo delle annotazioni e della ricostruzione, **non
il risultato di un modello addestrato**. Conserva tutti i 192 campi: 11 mancanti
(9 rapporti e 2 NDG letti male) e 2 note errate. Il testo esatto è disponibile per
170/183 valori non vuoti. Non è un limite matematico universale: descrive questo
OCR e questa supervisione. I nuovi pesi ottengono 119 valori corretti, 8 assenze corrette, 38 errati, 26 mancanti e 1 allucinato. Nessun campo è escluso dal denominatore.
La storia di addestramento di v2 non prova l'assenza di sovrapposizioni con queste
pratiche; il confronto storico è esplorativo. Nessuna nuova chiamata a provider.

Aggregati e impronte: [cached-baseline-summary.json](checks/2026-10-16-lilt-v3-1/cached-baseline-summary.json).
I dettagli con valori personali rimangono sotto `mnt/`, ignorato da Git.

## Verifiche e finding

TDD osservato per lettura revisione, separazione, parole/box, sequenze/tokenizer,
ciclo reale CPU con modello piccolo e ricostruzione. Le regressioni aggiuntive
hanno fallito prima dei fix: punteggiatura reale esclusa, falsi confronti esatti,
parole parziali errate e rinumerazione dei soggetti con NDG non predetti.
Evidenze: [alignment](checks/2026-10-16-lilt-v3-1/alignment-tdd-evidence.md),
[model](checks/2026-10-16-lilt-v3-1/model-tdd-evidence.md).
Risultato mirato finale: dataset 14, allineamento 10, modello 11, valutazione 36
test passati. Suite completa dopo la correzione del trasporto: **430 passed,
3 warnings in 78.68s**, exit 0, con thread numerici limitati a 1 e socket locali
Windows fuori sandbox. [Log finale](checks/2026-10-16-lilt-v3-1/pytest-native-boundary-final.txt)
e [cronologia verifiche](checks/2026-10-16-lilt-v3-1/verification.json).
I run precedenti, 429 passed in 117.19s e 429 passed in 76.93s, restano storici.
Il primo conteneva un traceback del worker `LocalExtractionClient` che emette dopo
la distruzione dell'oggetto Qt; non compare negli ultimi due run. Questo lavoro
non corregge né dichiara risolto quel problema applicativo di ciclo di vita.

- Risolto nel percorso offline: origine di verità non approvata o ambigua, immagini
  duplicate tra insiemi, pseudo-correzione 6/8 usata come verità, punteggiatura reale
  etichettata come sfondo, perdita di parole ai confini della sequenza, righe soggetti
  rinumerate quando un identificatore manca.
- Eseguiti: conferma del trasferimento, addestramento GPU reale e verifica dei pesi su CPU.
  Aperta e fuori perimetro: integrazione nel flusso live, da subordinare a qualità sufficiente.
- Aperto: tredici letture del test non esatte con il cache e la supervisione correnti,
  copertura indipendente mancante per quindici campi e dataset piccolo.
- Finding delle altre aree: rimangono gli esiti degli incrementi 11 e 13; questo
  lavoro non li chiude implicitamente.


## Modello, recupero e prova su CPU

- Modello pubblico iniziale: `nielsr/lilt-xlm-roberta-base`, revisione
  `39325597c4aa6698a50323f444013287bae52e67`; nuova testa di classificazione.
- Volume/versione: `bper-lilt-spike/model_v3_1_cbc98601c0262b11`; le versioni precedenti
  rimangono invariate. Artefatto locale: `mnt/training/runs/lilt-v3.1-20261016/cpu_model/`.
- Pesi SHA-256: `01d7ca87fd1b0cd7c78f770e59d08ade73c580a403a8ef8e4f93eacd8245e880`.
- Undici file, 1.151.848.890 byte, dimensioni e hash verificati due volte:
  [download-manifest.json](checks/2026-10-16-lilt-v3-1/download-manifest.json).
- Otto epoche, migliore epoca 8 scelta soltanto sulla validazione. Test generato
  una volta dopo la scelta. F1 parole: validazione 97,81%, test 88,89%; accuratezza
  dei campi: validazione 115/146 (78,77%), test 127/192 (66,15%). La F1 sulle parole
  non sostituisce il confronto del valore completo e maschera i token incerti.
- Fase registrata di training/valutazione: 325,42 secondi. Tempo esatto della
  funzione remota non persistito e perso nel ritorno; non viene ricostruito fittiziamente.
- CPU: due thread, primo fotogramma test da 137 parole, input limitato a parole e
  dimensioni immagine, senza valori attesi/etichette/allineamenti. Zero differenze
  di ruolo rispetto alla GPU; massima differenza di probabilità 0,000003. Caricamento
  modello/tokenizer 5,926s; prima inferenza 1,469s, escluso OCR. È una prova su un
  fotogramma, non una misura di tutte le acquisizioni live.
  [Verifica CPU](checks/2026-10-16-lilt-v3-1/cpu-verification.json).

Gli avvii precedenti alla funzione GPU si sono fermati per codifica Windows cp1252
poi per `scaledown_window=1`, inferiore al minimo remoto di 2 secondi. Nessun
training era iniziato. Il training effettivo ha poi completato e committato il volume;
il client locale senza Torch non ha potuto deserializzare `torch.__version__`,
che era un `TorchVersion`. Gli artefatti JSON salvati erano corretti. Recupero
in sola lettura dal volume, senza nuova GPU. Un tentativo CLI con destinazione non
esistente come directory ha mescolato i file sullo stesso percorso; quel file
invalido è stato rimosso, e lo scaricamento per singolo file ha completato il recupero.

Il ritorno ora usa stringhe native per le versioni delle dipendenze. Una regressione
con training CPU reale ha fallito sul tipo `TorchVersion`, poi è passata con tutti
gli 11 test del modello. La correzione riguarda il trasporto dei metadati, non il
calcolo dei pesi. Il manifest del run mantiene **gli hash sorgenti realmente eseguiti**;
lo snapshot corrente registra separatamente la correzione successiva. Nessuna
rilabelizzazione del vecchio snapshot e nessun nuovo addestramento.
[Provenienza eseguita](checks/2026-10-16-lilt-v3-1/executed-training-provenance.json),
[sorgenti correnti](checks/2026-10-16-lilt-v3-1/source-snapshot.json).

## Errori osservati e prossimo esperimento

La verifica indipendente conferma esattamente il risultato e gli hash:
[independent-trained-audit.json](checks/2026-10-16-lilt-v3-1/independent-trained-audit.json).
Rispetto a v2: 23 campi guadagnati e 20 regressioni, guadagno netto 3. Cinque campi
della tabella fidi concentrano 40/65 errori: rapporto 9, importo 8, scadenza 8,
tipo operazione 8, numero fido 7. Gli otto importi errati dipendono dalla
classificazione: quattro letti come scadenza, quattro come sfondo. Non emerge un
nuovo difetto chiaro del decoder; con i ruoli supervisionati la ricostruzione rimane
179/192. Non si modifica il decoder sul test per migliorarne il punteggio.

Le note costituiscono 412/699 parole positive del test; senza note la F1 parole
scende al 75,59%. Il valore aggregato 88,89% nasconde quindi errori importanti nelle
colonne di credito. Il prossimo esperimento deve analizzare queste confusioni su
**train e validazione**, curare gli esempi delle tabelle e i negativi dello sfondo,
e migliorare la lettura OCR dei rapporti. Servono anche altre pratiche per la
copertura dei quindici campi senza positivi nel test. Il test attuale resta congelato;
non è avviato un secondo training e non si dichiara raggiunta la qualità per l'uso.

### Correzione post-analisi del collo di bottiglia Fidi (preparazione al prossimo run)

L'analisi delle confusioni su `train` e `val` ha individuato e risolto nel pacchetto
`training/` quattro difetti strutturali che penalizzavano la tabella `FIDI`:

1. **Ordinamento locale per righe di cella in `training/alignment.py` (`_order_cell_indices` / `_field_result`):**
   le celle su due righe (`Rapporto`, `Tipo Op.`, `Ruolo`, `Denominazione`) venivano
   fuse nella stessa `row` globale della pagina e ordinate per `x0` crescente,
   anteponendo la seconda riga centrata (`05502254`, `Finanza`, `Di Pegno`) alle
   parole della prima riga (`0744`, `Nuova`, `Garante/nuovo`). Con l'ordinamento per
   righe visive interne alla cella, **19 campi su 55** precedentemente marcati
   `ignored_ocr_mismatch` risultano esatti al 100% senza toccare il testo OCR
   (recuperati 13 `rapporto` su 15 — inclusi 8 dei 9 del test dati per non disponibili —,
   3 `tipo_op`, 2 `ruolo` e 1 `denominazione_4`). La disponibilità esatta dell'oracle
   diagnostico sale da 179/192 (93,23%) a **187/192 (97,40%)** nel test e da 134/146
   (91,78%) a **137/146 (93,84%)** in validazione.
2. **Circoscrizione del riquadro d'incertezza (`fallback_area`) e supervisione parziale in `training/alignment.py` e `training/dataset.py`:**
   i campi non risolti conservano la `bbox` delle parole candidate libere nella
   propria regione anziché `bbox=None`. Le schermate con zero etichette `O` scendono
   da 7 a **0** nel train (+1.845 parole `O` supervisionate) e da 3 a **0** in
   validazione (parole `IGNORE` in validazione ridotte da 968 a 127). `Scadenza` e
   `Tipo Op.` supervisionano inoltre le parole esatte verificate (es. `"mesi"` in
   `"381 mesi"`). Nel bundle `mnt/training/ground-truth-v3.1/` rigenerato (impronta
   `469c26d1dd6e5464be3732ae0a06dc71751a779d8771aa39ab289e84fa8ae6e6`), i campi
   completamente supervisionati salgono da 844 a **863**, i parziali da 17 a **22**
   e gli `ignored_ocr_mismatch` scendono da 55 a **31**.
3. **Integrità del blocco tabella `FIDI` e augmentation in `training/model.py`:**
   `_word_groups()` non spezza più la sezione `FIDI` tra due finestre da 512
   sottotoken (azzerati i 13 campi `rapporto`/`tipo_op` divisi a metà tra chunk e i
   10 casi di riga `F1` separata dall'intestazione tabella). `_augment()` riduce il
   jitter a `±0,5%` di scala e `±0,3%` di traslazione (evitando la sovrapposizione
   tra `scadenza`, `importo_euro` e `tipo_op`) e sostituisce le sole cifre non-zero
   (`1..9`) su tutte le parole non-`IGNORE`, preservando gli zeri delle migliaia
   (`.000`). I pesi di classe usano `reference = max(median, 100)` per non schiacciare
   a `1.0` i campi scalari da una parola per schermata.
4. **Selezione del checkpoint in `training/model.py`:**
   `score_predictions()` espone `field_accuracy`, `credit_field_accuracy` e
   `non_note_f1`; `train_model()` seleziona il checkpoint su
   `(field_accuracy, non_note_f1, f1)` di validazione.
5. **Verifica suite:** 6 nuovi test TDD in `tests/test_training_alignment.py` e
   `tests/test_training_model.py` (falliti prima del fix e passati dopo); suite
   completa: **436 passed, 3 warnings in 119.43s**. Nessun nuovo addestramento GPU
   è stato ancora avviato con questi aggiornamenti.

## Risorse e costo

Una L4, 2 CPU richieste/4 limite, 12GiB richiesti, timeout 1.800s, un container,
nessun retry automatico. [Prezzi Modal](https://modal.com/pricing) e
[compatibilità CUDA](https://modal.com/docs/guide/cuda) verificati sulle fonti
primarie. La sola fase registrata di 325,42s corrisponde a circa $0,089–$0,098
ai prezzi pubblicati per quelle risorse. **Non è il totale fatturato**: sono esclusi
preparazione, caricamento, salvataggio, build, scaricamenti e spazio persistente;
le eventuali franchigie del piano non sono verificate. Il costo effettivo completo
non è disponibile dal riepilogo recuperato. Non si presenta una stima come fattura.
