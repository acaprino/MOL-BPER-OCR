# 0004 - Budget di retry derivato dal numero di aree

- **Stato:** Accettato
- **Data:** 2026-08-17
- **Interessa:** `extraction/config.py`, `.env`, `.env.example`
- **Test:** `tests/test_pipeline_retry.py`

## Contesto

La terza passata della pipeline ritenta le aree deboli. Un'area è debole se **almeno uno** dei suoi
campi è nullo o sotto confidenza 0.60. Le aree sono tre, dichiarate in `AREA_TO_FIELDS`:

| area | contiene |
|---|---|
| HEADER | ndg, denominazione, tipo, stato, fase, evidenze, filiale_relazione, ultima_validazione_scheda |
| BODY | fidi, garanzie, soggetti, campi della scheda privati |
| FOOTER | note_della_richiesta, note_scheda_privati |

Il budget era `allowed_retries = max(0, MAX_CALLS_PER_SCREEN - 2)`, con `MAX_CALLS_PER_SCREEN`
letterale a `4`: **due** retry per tre aree. La selezione avviene nell'ordine di dichiarazione, con un
commento nel codice che spiega perché HEADER deve restare primo.

Ne segue che l'ultima area della lista è **strutturalmente irraggiungibile** ogni volta che le due
precedenti sono deboli. E su una pagina che mostra una sola sezione questo succede sempre: i campi
delle altre aree non sono su quella pagina, quindi risultano nulli, quindi le loro aree risultano
deboli e consumano tutto il budget.

Il caso concreto è la pagina "Note da Richiesta". Contiene un solo campo che conta,
`note_della_richiesta`, che appartiene a FOOTER. HEADER è parzialmente letto e BODY è
completamente vuoto, quindi entrambi chiedono un retry e se lo prendono. FOOTER, l'unica area con il
contenuto della pagina, non viene mai riletta.

## Decisione

Derivare il default dal numero di aree invece di scriverlo:

```python
MAX_CALLS_PER_SCREEN = int(
    os.getenv("MAX_CALLS_PER_SCREEN", str(2 + len(AREA_TO_FIELDS)))
)
```

Il `2` sono la passata anchor e la passata principale, già consumate quando si arriva ai retry. La
definizione è stata spostata dopo `AREA_TO_FIELDS` nel file, perché il default ora dipende da essa.

`.env` e `.env.example` avevano `MAX_CALLS_PER_SCREEN=4` esplicito, che avrebbe annullato il fix:
aggiornati a `5` con la spiegazione del vincolo.

## Alternative valutate

**Ordinare le aree per densità di campi deboli.** Un'area con letture parziali è più probabilmente
recuperabile di un'area interamente nulla, che di solito significa "non è su questa pagina".
Scartata perché non risolve il caso: su "Note da Richiesta" FOOTER è interamente nulla esattamente
come BODY, quindi resterebbe in coda e continuerebbe a perdere il retry.

**Scopare le aree in base alla pagina riconosciuta.** La pipeline riceve il tipo di pagina come
`screen_id`, ed esiste `resolve_field_page_key()` in `extraction/field_definitions.py`. Sarebbe la
soluzione di principio: su una pagina di note non si ritenterebbe nemmeno HEADER. Scartata **per ora**
perché quella mappa è inaffidabile per questo scopo: `dal`, `professione_principale`,
`rating_ufficiale` e gli altri campi della scheda privati sono marcati `note_da_richiesta` mentre
stanno sulle schermate 4 e 5. Costruirci sopra la logica di retry introdurrebbe una nuova fonte di
errore al posto di quella rimossa. Va ripreso dopo aver corretto la mappa.

**Lasciare il letterale e alzarlo a 5.** Fa passare i test di oggi e riproduce il difetto domani:
aggiungendo una quarta area di retry, il letterale la affama in silenzio. È la stessa classe di
fragilità che `CLAUDE.md` documenta al vincolo *No startup guards*, dove una chiave assente da
`AREA_TO_FIELDS` non viene mai ritentata e nessuno se ne accorge.

## Conseguenze

Il costo peggiore per schermata sale da 4 a 5 chiamate VLM, cioè +25%. Solo nel caso peggiore: un'area
viene ritentata unicamente se è debole, quindi una schermata letta bene continua a costare 2 chiamate.

Chi ha bisogno di contenere il costo può ancora abbassare `MAX_CALLS_PER_SCREEN` via ambiente, ma ora
sa che cosa sta sacrificando: le aree in coda a `AREA_TO_FIELDS`.

Aggiungere una quarta area di retry alza il default da sé, senza che nessuno debba ricordarselo.

Resta aperto un difetto vicino ma distinto, che questa decisione **non** risolve: `_merge_tables()`
accetta le tabelle del retry BODY quando ha più righe di quelle correnti, quindi un retry BODY su una
pagina priva di tabelle può aggiungere righe inventate, che poi l'appiattimento dei soggetti riversa
in `ndg_1..ruolo_4`. Questa decisione non ne cambia la frequenza: BODY era già secondo nell'ordine,
quindi veniva ritentato anche col budget precedente. L'area aggiunta è FOOTER, e `_merge_tables()`
esce subito per ogni area diversa da BODY, quindi il retry in più non porta rischio sulle tabelle. Il
difetto va affrontato a parte.
