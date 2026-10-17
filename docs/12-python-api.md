# API Python

Riferimento delle interfacce usate dal batch e dall'edge-agent. Il repository espone
funzioni Python e segnali Qt; non implementa un server HTTP per l'estrazione BPER.
I metodi che avviano la pipeline chiamano i provider configurati e richiedono rete
oltre alle credenziali. Le firme qui riportate sono riferimenti, non script eseguibili.
<!-- Source: src/extraction/__init__.py:11; src/extraction/llm_factory.py:18; src/edge-agent/local_extraction_client.py:90 -->

Prima di importare `extraction`, prepara l'ambiente: `src/extraction/config.py` legge
le impostazioni all'importazione. Per integrare i moduli dell'edge-agent segui
l'avvio dell'applicazione e la sua risoluzione dei percorsi, descritti in
[Avvio e sviluppo](07-getting-started.md) e [Architettura](04-architecture.md).
<!-- Source: src/extraction/config.py:7; src/edge-agent/edge_agent.py:63; src/edge-agent/local_extraction_client.py:19 -->

Le firme seguenti sono trascritte dal codice; descrivono i punti di integrazione,
non un inventario di tutti gli helper esportati per compatibilità da `extraction`.

## Batch di file

```python
def run_extraction_batch(
    paths: List[str],
    *,
    api_key: Optional[str] = None,
    provider_name: Optional[str] = None,
    model_main: Optional[str] = None,
    model_anchor: Optional[str] = None,
    parallel: bool = True,
    max_workers: int = 4,
    on_complete: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    on_error: Optional[Callable[[str, Exception], None]] = None,
) -> Dict[str, Dict[str, Any]]:
```

**Source:** [extraction/cli.py](../extraction/cli.py), righe 285–312.
Restituisce `{screen_id: risultato}`; salta i percorsi inesistenti con un avviso.
Le callback sono eseguite dal thread che chiama il batch. In parallelo un errore viene
segnalato a `on_error` oppure stampato; in sequenziale, senza `on_error`, viene rilanciato.
Se `model_main` è esplicito e manca `model_anchor`, entrambi usano il modello scelto.
<!-- Source: src/extraction/cli.py::BatchRunner.__init__; src/extraction/cli.py::BatchRunner.run -->

## Pipeline per una singola immagine

```python
def __init__(
    self,
    main_model: BaseChatModel,
    anchor_model: BaseChatModel,
    main_model_name: str,
    anchor_model_name: str,
) -> None:

def extract_anchors(
    self, content_img: Image.Image, screen_id: str, *, calibrated: bool = True
) -> Dict[str, Any]:

def extract_from_image(
    self, img: Image.Image, screen_id: str, *, allow_content_crop: bool = False
) -> Dict[str, Any]:

def extract_from_screen(self, path: str) -> Dict[str, Any]:
```

**Source:** [extraction/pipeline.py](../extraction/pipeline.py), righe 62, 78, 122 e 223.
Il costruttore riceve modelli già creati. `extract_anchors()` restituisce i due campi
e `_meta`; gli altri metodi restituiscono il risultato completo o l'uscita anticipata
descritta nei [flussi di estrazione](05-workflows.md). Errori di apertura immagine e delle letture iniziali possono propagarsi.

## Client asincrono dell'edge-agent

```python
result_ready = QtCore.pyqtSignal(str, dict)   # (job_id, result)
frame_queued = QtCore.pyqtSignal(str, str)    # (job_id, page_type)

def __init__(
    self,
    parent: Optional[QtCore.QObject] = None,
    pipeline: Optional[ExtractionPipeline] = None,
) -> None:

def start_job(self) -> str:

def ingest_frame(
    self,
    job_id: str,
    img: Image.Image,
    page_no: int = 0,
    page_type: str = "",
    confidence: float = 0.0,
    fields_json: str = "{}",
) -> int:

def get_results(self, job_id: str) -> List[Dict[str, Any]]:

def pending_extractions(self) -> int:

def shutdown(self) -> None:
```

**Source:** [edge-agent/local_extraction_client.py](../edge-agent/local_extraction_client.py),
righe 87–127 e 210–225. `start_job()` genera un UUID; `ingest_frame()` restituisce una
sequenza da zero per job e solleva `RuntimeError` se il pool è chiuso, senza emettere
`frame_queued`. `fields_json` è accettato per compatibilità ma non guida la pipeline.
`pending_extractions()` conta approssimativamente i lavori ancora in coda, escludendo
quelli già iniziati. `get_results()` copia la lista, non i dizionari annidati: i consumatori
non devono modificarli. `requeue_job()` è uno stub che restituisce `True`, non un retry.
<!-- Source: src/edge-agent/local_extraction_client.py:123; src/edge-agent/local_extraction_client.py:145; src/edge-agent/local_extraction_client.py:157; src/edge-agent/local_extraction_client.py:206; src/edge-agent/local_extraction_client.py:222; src/edge-agent/extraction_pool.py:41 -->

## Consolidamento ed esportazione

`resolve_field_page_key(schema_key)` restituisce la pagina sorgente, inclusa `scheda_privati`.
`resolve_field_export_group_key(schema_key)` restituisce il gruppo di presentazione e usa
`page_key` come fallback. I tredici campi privati condividono il gruppo `note_da_richiesta`.
`ColumnSpec.page_key/page_name` descrivono tale gruppo, mentre le voci canoniche emettono la
pagina sorgente; l’ordine e le 45 colonne restano compatibili
([ADR 0020](adr/0020-pagina-sorgente-separata-dal-gruppo-export.md)).

```python
def consolidate(results: Sequence[Dict[str, Any]]) -> List[PracticeRecord]:

def export_results(
    results: Sequence[Dict[str, Any]],
    path: str,
    labels: Optional[Mapping[str, str]] = None,
) -> int:
```

**Source:** [practice_consolidation.py](../edge-agent/practice_consolidation.py), riga 105;
[excel_export.py](../edge-agent/excel_export.py), riga 217.
L'input deve rispettare l'ordine di cattura. `consolidate()` non scrive su disco;
`export_results()` consolida, scrive il workbook e restituisce il numero di pratiche.
`labels` sostituisce le etichette visualizzate per chiave di schema. Gli errori del
salvataggio non sono intercettati dall'API di esportazione.
<!-- Source: src/edge-agent/practice_consolidation.py:105; src/edge-agent/excel_export.py:92; src/edge-agent/excel_export.py:214; tests/test_excel_export.py:123 -->

## Contratti da conservare

- Il batch richiama `on_complete` e `on_error` nel thread del chiamante. L'ordine
  dei completamenti paralleli non costituisce l'ordine di acquisizione dell'edge-agent.
- Il client assegna `_capture_sequence` solo ai frame accettati. `result_ready`
  notifica ogni completamento e può precedere il ritorno di `ingest_frame()`;
  `get_results()` espone invece il prefisso contiguo completato, errori compresi.
- Tabella ed export leggono quel prefisso prima di consolidare. Un risultato lento
  può ritardare i successivi; gli errori diagnostici non devono lasciare buchi.
- `shutdown()` scarta i lavori ancora in coda e non attende quelli già partiti.
  I thread daemon possono proseguire finché il processo resta attivo; chiudere
  l'applicazione non garantisce di completare tutti i risultati prima dell'export.

<!-- Source: src/extraction/cli.py::BatchRunner.run; src/edge-agent/local_extraction_client.py:127; src/edge-agent/local_extraction_client.py:157; src/edge-agent/local_extraction_client.py:214; src/edge-agent/local_extraction_client.py:222; src/edge-agent/extraction_pool.py:45 -->

I diagrammi e i percorsi di errore sono nel capitolo [Workflow](05-workflows.md).
Le strutture restituite e la regola una riga per pratica sono nel [Modello dei dati](06-data-model.md).
Per scegliere dove intervenire, consulta [Avvio e sviluppo](07-getting-started.md).
I test di riferimento sono [test_local_extraction_client.py](../tests/test_local_extraction_client.py),
[test_practice_consolidation.py](../tests/test_practice_consolidation.py) e
[test_excel_export.py](../tests/test_excel_export.py).
