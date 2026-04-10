# Data Model

This project has no database. Every piece of data lives in one of four places: Pydantic models that constrain what the VLM is allowed to return, Python dictionaries that carry the result of an extraction through the pipeline, a CSV file that holds the ground truth for accuracy evaluation, and JSON files on disk that persist the batch output. The domain itself is narrow -- a single BPER credit-management "practice" made of one anagraphic header, up to four subjects, a list of credit lines, a list of guarantees, and a long free-text note. Everything else is metadata about how that data was obtained.

## Entity Relationship Diagram

```mermaid
erDiagram
    GROUND_TRUTH_CSV ||--o{ GT_CELL : "contains rows"
    GT_CELL }o--|| FIELD_KEY : "csv label maps to"
    FIELD_KEY }o--|| CANONICAL_FIELD : "schema key defines"
    CANONICAL_FIELD }o--|| CANONICAL_PAGE : "belongs to"

    EXTRACTION_RESPONSE ||--|| FIELDS_MODEL : "fields"
    EXTRACTION_RESPONSE ||--o{ SOGGETTO : "soggetti"
    EXTRACTION_RESPONSE ||--o{ FIDO : "fidi"
    EXTRACTION_RESPONSE ||--o{ GARANZIA : "garanzie"
    FIELDS_MODEL ||--o{ FIELD_RESULT : "one per FIELD_KEY"

    ANCHOR_RESPONSE ||--|| ANCHOR_FIELDS : "fields"
    ANCHOR_FIELDS ||--o| FIELD_RESULT : "ndg"
    ANCHOR_FIELDS ||--o| FIELD_RESULT : "denominazione"

    PIPELINE_OUTPUT ||--|| FIELDS_MODEL : "fields (merged)"
    PIPELINE_OUTPUT ||--o{ SOGGETTO : "soggetti"
    PIPELINE_OUTPUT ||--o{ FIDO : "fidi"
    PIPELINE_OUTPUT ||--o{ GARANZIA : "garanzie"
    PIPELINE_OUTPUT ||--o{ CANONICAL_ENTRY : "canonical_fields"
    PIPELINE_OUTPUT ||--|| META_AGG : "_meta_agg"
    PIPELINE_OUTPUT ||--o{ ATTEMPT_META : "_attempts"
    PIPELINE_OUTPUT ||--o{ FIELD_SOURCE : "_field_sources"

    CANONICAL_ENTRY }o--|| CANONICAL_FIELD : "references"
    CANONICAL_ENTRY }o--|| CANONICAL_PAGE : "references"

    POC_OUTPUTS_JSON ||--o{ PIPELINE_OUTPUT : "screen_id to result"
    POC_DEBUG_CSV ||--o{ DEBUG_ROW : "per screen per field"
    DEBUG_ROW }o--|| PIPELINE_OUTPUT : "joins on screen_id"
    DEBUG_ROW }o--|| GT_CELL : "joins on screen+key"

    FIELD_RESULT {
        string value
        float confidence
        string evidence_text
        string section
    }
    SOGGETTO {
        string ndg
        string denominazione
        string ruolo
        float confidence
        string evidence_text
    }
    FIDO {
        string n_fido
        string rapporto
        string descrizione
        string scadenza
        string importo_euro
        string tipo_op
        float confidence
    }
    GARANZIA {
        string n_gar
        string descrizione
        string fido
        string ndg
        string denominazione
        string importo_percentuale
        string tipo_op
        float confidence
    }
    CANONICAL_FIELD {
        string schema_key PK
        string display_name
        string page_key FK
    }
    CANONICAL_PAGE {
        string page_key PK
        string display_name
    }
    CANONICAL_ENTRY {
        string schema_key FK
        string display_name
        string page_key FK
        string page_name
        string value
        float confidence
        string evidence_text
        string section
    }
    META_AGG {
        string model_main
        string model_anchor
        int calls
        int total_tokens
        float estimated_cost_usd
        int latency_ms
    }
```

Read this diagram as three layers. The top layer (`GROUND_TRUTH_CSV`, `GT_CELL`, `FIELD_KEY`, `CANONICAL_FIELD`, `CANONICAL_PAGE`) is static reference data, baked into code and CSV. The middle layer (`EXTRACTION_RESPONSE`, `ANCHOR_RESPONSE`, `FIELD_RESULT`, `SOGGETTO`, `FIDO`, `GARANZIA`) is the Pydantic contract between the pipeline and the LLM. The bottom layer (`PIPELINE_OUTPUT`, `CANONICAL_ENTRY`, `META_AGG`, `POC_OUTPUTS_JSON`, `POC_DEBUG_CSV`) is the runtime result shape that gets persisted and evaluated.

## FieldResult

The atomic unit of extraction. Every single value the VLM returns is wrapped in one of these. It holds the raw string the model read plus three pieces of introspection that the evaluation and retry logic rely on.

Defined in `extraction/schemas.py` lines 9-13:

- `value: Optional[str]` -- the extracted text, or `None` when the field is absent on screen
- `confidence: float` -- the model's self-reported confidence from 0.0 to 1.0
- `evidence_text: Optional[str]` -- a short quote from the image used to justify the value (helpful for debug CSV rows)
- `section: Optional[str]` -- the UI section name where the value was found (e.g. `soggetti_table`)

The confidence score drives two decisions. First, `ExtractionPipeline.extract_anchors()` (`extraction/pipeline.py` lines 91-96) zeroes out the NDG and Denominazione anchors if their confidence is below `ANCHOR_CONF_MIN` (default 0.95, `extraction/config.py` line 52). Second, `ExtractionPipeline._retry_areas()` (`extraction/pipeline.py` lines 254-257) triggers a retry pass for any field with confidence below 0.60.

## FieldsModel

A single flat container that holds one `Optional[FieldResult]` per schema key. It isn't written by hand -- it is built dynamically at import time by `create_model()` from Pydantic, using the contents of `FIELD_KEYS` as the source of truth (`extraction/schemas.py` lines 46-49). Add a new entry to `FIELD_KEYS` in `extraction/fields.py` and the Pydantic model gains that field automatically.

`FIELD_KEYS` currently has 45 entries (count them in `extraction/fields.py` lines 12-54) covering:

- **Header fields** of the Risultato Ricerca page: `ndg`, `denominazione`, `tipo`, `stato`, `fase`, `creazione`, `evidenze`, `filiale_relazione`
- **Fidi row fields**: `n_fido`, `rapporto`, `descrizione`, `scadenza`, `importo_euro`, `tipo_op`
- **Free text**: `note_della_richiesta`
- **Tooltip fields** that exist only on hover: `tooltip_descrizione_bmb`, `tooltip_evidenze_b`, `tooltip_descrizione_m_consap`, `tooltip_descrizione_consap_dr_bis`, `tooltip_descrizione_ipoteca`
- **Flattened Soggetti** for CSV compatibility: `ndg_1..4`, `denominazione_1..4`, `ruolo_1..4`
- **Private-customer fields** from screens 4 and 5: `dal`, `datore_di_lavoro_anagrafica`, `di_cui_percepiscono_reddito`, `importo_totale_annuo_nucleo`, `note_scheda_privati`, `nr_altri_componenti_nucleo`, `numero_mensilita`, `professione_principale`, `rating_ufficiale`, `retribuzione_annua_netta`, `score_cgs`, `tipo_contratto`, `ultima_validazione_scheda`

The flattened Soggetti are a workaround. The VLM returns subjects as a structured list (see `Soggetto` below), but the ground truth CSV has them as separate columns. After the main pass, `ExtractionPipeline.extract_from_image()` copies the first four soggetti into these flat keys (`extraction/pipeline.py` lines 160-166) so the evaluator can compare them column-by-column.

## Soggetto, Fido, Garanzia

The three table entities represented as Pydantic `BaseModel` classes in `extraction/schemas.py` lines 15-41. Unlike the flat fields above, these live as ordered `List[...]` inside `ExtractionResponse` and can grow to arbitrary length.

**Soggetto** (lines 15-20) is a person or legal entity tied to the credit practice. The domain fields are `ndg`, `denominazione`, and `ruolo`. Typical roles are "TITOLARE", "COOBBLIGATO", "GARANTE". One screen can list several subjects in a table.

**Fido** (lines 22-30) is a credit line: `n_fido` (the credit line number), `rapporto` (the underlying account), `descrizione` (human-readable product description), `scadenza` (expiry date), `importo_euro` (amount), and `tipo_op` (operation type, e.g. BMB). All string-typed because the VLM returns raw OCR text -- numeric validation happens later in `classify_field()` via `norm_number_str()` (`extraction/normalization.py`).

**Garanzia** (lines 32-41) is a collateral record: `n_gar` (guarantee number), `descrizione`, `fido` (the credit line it backs), `ndg`/`denominazione` (the subject providing it), `importo_percentuale`, and `tipo_op`. Note that a Garanzia contains its own `ndg` and `denominazione` -- these are denormalized joins, not foreign keys, because the VLM extracts them directly from the on-screen table rather than looking them up.

All three share the common `confidence: float` and `evidence_text: Optional[str]` trailing fields.

## ExtractionResponse and AnchorResponse

The top-level Pydantic models that LangChain's `.with_structured_output()` validates against. Two exist because the pipeline makes two different kinds of VLM calls with two different prompts.

**`ExtractionResponse`** (`extraction/schemas.py` lines 54-58) is the full schema sent on the main pass and the retry passes. It has:

- `fields: FieldsModel` -- all 45 scalar fields
- `soggetti: List[Soggetto]`
- `fidi: List[Fido]`
- `garanzie: List[Garanzia]`

**`AnchorResponse`** (`extraction/schemas.py` lines 60-65) is a deliberately narrow schema for the first pass. It wraps an `AnchorFields` model that holds only `ndg` and `denominazione`, both `Optional[FieldResult]`. A narrow schema forces the model to focus on just the two identity fields from the header strip, reduces token count, and lets the pipeline enforce a high confidence gate before anything else runs. See the anchor pass discussion in [Workflows](05-workflows.md).

Both classes have the backward-compatible aliases `RESPONSE_SCHEMA` and `ANCHOR_SCHEMA` at the bottom of the file (`extraction/schemas.py` lines 70-71).

## Canonical Field Metadata

`CANONICAL_FIELD_DEFINITIONS` in `extraction/field_definitions.py` lines 5-186 is the bridge between the compact snake_case schema keys used in code and the human-facing labels the client cares about. Every entry in `FIELD_KEYS` should have a matching entry here; if one is missing the display name falls back to the schema key itself (`extraction/fields.py` lines 118-121).

Each entry is shaped like this:

```python
"n_fido": {
    "display_name": "n° FIDO",
    "page_key": "gestione_fidi_e_garanzie",
},
```

The `display_name` is the exact Italian label the BPER banking application shows on screen. The `page_key` is a foreign key into the canonical page table (see next section), and it determines which of four sheets a field ends up on when the edge-agent exports to Excel via `DataTableTab`.

Beside the definitions, the same file carries `FIELD_LABEL_ALIASES` (lines 188-235), a reverse lookup from normalized lowercase labels back to schema keys. `normalize_field_label()` (lines 238-240) trims, lowercases, and collapses whitespace so a CSV column like `"n° FIDO"` resolves to `"n_fido"` regardless of spacing or case. Two public helpers use this: `resolve_schema_key()` (lines 243-246) for going from label to key, and `resolve_display_name()` / `resolve_field_page_key()` (lines 249-262) for the reverse lookup.

## Canonical Pages

The four pages of the BPER credit-management workflow that this project extracts from. Defined in `extraction/page_definitions.py` lines 5-10:

| page_key | display_name |
|----------|--------------|
| `risultato_ricerca` | Risultato ricerca |
| `elenco_soggetti` | Elenco Soggetti |
| `gestione_fidi_e_garanzie` | Gestione Fidi e Garanzie |
| `note_da_richiesta` | Note da Richiesta |

`PAGE_NAME_ALIASES` (lines 12-21) maps common label variants back to the canonical key, and `normalize_page_label()` (lines 31-33) does the same case/spacing cleanup as its field-level counterpart. `PAGE_SHEET_ORDER` (lines 23-28) freezes the ordering used when `build_canonical_field_entries()` sorts its output, which is how the Excel export keeps its sheets in a consistent order.

Note: the brief and code both speak of "nine" BPER screens (the prototype images in `edge-agent/assets/templates/bper/` and `mnt/data/screen 1-9.png`). The page model has only four canonical pages because several raw screens map to the same canonical page -- e.g. two Fidi screens both feed `gestione_fidi_e_garanzie`. The edge-agent uses a separate 5-page definition in `edge-agent/assets/templates/bper/prompts.json` for its LLM router, which is unrelated to the canonical page model used by the extraction pipeline.

## CanonicalEntry and the canonical_fields List

After the pipeline finishes, `ExtractionPipeline.extract_from_image()` calls `build_canonical_field_entries()` from `extraction/canonical_mapping.py` (lines 20-42). This walks the extracted `fields` dict, looks up each schema key via `get_canonical_field_metadata()` (`extraction/fields.py` lines 128-138), and produces a flat list of entries:

```python
{
    "schema_key": "n_fido",
    "display_name": "n° FIDO",
    "page_key": "gestione_fidi_e_garanzie",
    "page_name": "Gestione Fidi e Garanzie",
    "value": "123456",
    "confidence": 0.95,
    "evidence_text": "n° FIDO 123456",
    "section": "fidi_table",
}
```

The list is sorted by a composite key `(page_index, display_name, schema_key)` from `_canonical_entry_sort_key()` (lines 8-18). The result lives under `output["canonical_fields"]` and is what the edge-agent UI renders in `ExtractionResultsTab` and exports via `DataTableTab`.

## Pipeline Output Dict

The runtime dictionary that `ExtractionPipeline.extract_from_image()` (`extraction/pipeline.py` lines 104-180) returns. It starts life as a `model_dump()` of an `ExtractionResponse` and gets decorated in place with pipeline metadata. Shape:

| Key | Type | Source |
|-----|------|--------|
| `fields` | dict of schema_key to FieldResult-shaped dict | from the main pass, merged with anchor and retry results |
| `soggetti` | list of Soggetto-shaped dicts | from the main pass, possibly overwritten by BODY retry |
| `fidi` | list of Fido-shaped dicts | same |
| `garanzie` | list of Garanzia-shaped dicts | same |
| `canonical_fields` | list of CanonicalEntry dicts | built after all passes via `build_canonical_field_entries()` |
| `_attempts` | list of per-call `_meta` dicts | appended by every `call_vlm_with_retry()` invocation |
| `_meta_agg` | aggregated cost and latency | built by `ExtractionPipeline._aggregate_meta()` lines 330-340 |
| `_field_sources` | dict of schema_key to attempt name | tracks which pass won each field (CONTENT_MAIN, ANCHOR_HEADER, RETRY_HEADER, RETRY_BODY, RETRY_FOOTER) |
| `_status` | `"OK"` or `"ANCHOR_UNCERTAIN"` | set at the end based on whether NDG and Denominazione are both present |
| `screen_id` | string | the basename of the screenshot without extension |

The underscore-prefixed keys are a deliberate convention: they are extraction metadata, not extracted data, and they get filtered out of the Excel export but kept in the JSON output for debugging.

Each `_attempts[i]` entry is a dict built by `call_vlm_with_retry()` in `extraction/vlm_client.py`. Its shape (lines 107-116, 167-176, and 214-223 -- there are three code paths for OpenAI structured, Gemini legacy, and Gemini free-form):

```python
{
    "model": "gpt-4o",
    "screen_id": "screen 1",
    "attempt": "CONTENT_MAIN",
    "latency_ms": 2800,
    "prompt_tokens": 1234,
    "completion_tokens": 456,
    "total_tokens": 1690,
    "estimated_cost_usd": 0.0078,
}
```

`_meta_agg` then sums `calls`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `estimated_cost_usd`, and `latency_ms` across all attempts, while carrying through `model_main` and `model_anchor` as flat strings for the cost report (`extraction/evaluation.py` lines 244-258).

## Ground Truth CSV

The evaluation reference file. The path is `mnt/data/dati.csv` by default, resolved from `GROUND_TRUTH_CSV` in `extraction/config.py` line 9. The file is gitignored and has to be supplied manually at run time.

`load_ground_truth()` in `extraction/evaluation.py` lines 33-69 reads it into a nested dict shaped `{ screen_name: { csv_column_label: value, ... }, ... }`. The loader is tolerant: it searches for the screen column among `["Screenshot", "Fotogramma", "Screen", "screen"]`, the value column among `["Valore rilevato", "Valore rilevato ", "Valore", "Value"]`, and the key column among `["Denominazione da attribuire", "Denominazione", "Campo", "Field"]` (lines 38-52). The helper `_find_column()` (lines 26-31) raises `ValueError` if none match, listing the columns it actually found so you can fix the CSV.

Each row of the CSV becomes one `GT_CELL` -- a triple of (screen_name, csv_column_label, value). The loader skips rows whose key is blank or the string `"nan"`, and normalizes missing values to the empty string. Screens and keys are kept as-is (lowercased only in the evaluator), so ordering and duplicate handling follow pandas defaults.

The bridge from CSV columns to schema keys lives in `CSV_TO_SCHEMA` in `extraction/fields.py` lines 56-100. It's a plain Python dict: keys are Italian BPER column labels (including stray-space variants like `"Evidenze "` and `"Valore rilevato "`), values are schema keys. When `eval_outputs()` iterates ground truth, it only considers rows whose CSV key is present in this mapping (`extraction/evaluation.py` lines 87-90) -- unmapped columns are silently ignored, which lets you add extra diagnostic columns to the CSV without breaking evaluation.

## JSON Output File

`mnt/data/poc_outputs_improved.json` is the single persistence artefact of a CLI batch run. It is written as a dict keyed by `screen_id`, where every value is a full Pipeline Output dict:

```json
{
    "screen 1": {
        "fields": {
            "ndg": {"value": "12345678", "confidence": 0.98, "evidence_text": "...", "section": "header"},
            "denominazione": {"value": "ROSSI MARIO", "confidence": 0.97, ...},
            ...
        },
        "soggetti": [...],
        "fidi": [...],
        "garanzie": [...],
        "canonical_fields": [...],
        "_meta_agg": {...},
        "_attempts": [...],
        "_field_sources": {...},
        "_status": "OK"
    },
    "screen 2": {...}
}
```

The write happens in `cli.main()` (`extraction/cli.py` lines 337-340) using `json.dump(..., ensure_ascii=False, indent=2)`. The file replaces the previous run on every execution -- there is no run history or versioning. The accompanying debug CSV `mnt/data/poc_debug_improved.csv` is a flat semicolon-delimited file, one row per (screen, GT key) pair, written by `build_debug_report()` in `extraction/evaluation.py` lines 125-177. Its columns include the predicted value, the GT value, the classification status, the retry source for that field, and the per-screen cost aggregate.

## Data Flow Patterns

### Create
Data only enters the system in two ways. From the **ground truth CSV**, loaded once at the start of a batch run by `load_ground_truth()`. From **PIL Image objects**, either read from disk via `Image.open(path).convert("RGB")` in `ExtractionPipeline.extract_from_screen()` (`extraction/pipeline.py` lines 182-187) or received in memory from the edge-agent capture worker via `LocalExtractionClient.ingest_frame()`. There is no direct user input into the data model itself.

### Read
The ground truth dict is read by `eval_outputs()`, `build_debug_report()`, and the accuracy summary printer. The JSON output file is read by the Tkinter GUI and the edge-agent UI when the user opens a previous run. The `canonical_fields` list is read by the edge-agent UI tabs to populate the pages tree, the fields table, and the spreadsheet view.

### Update
The only mutable data is the Pipeline Output dict during a single extraction. Five mutation points, all in `extraction/pipeline.py`:

1. `_merge_anchors()` (lines 211-216) overwrites `fields["ndg"]` and `fields["denominazione"]` with the anchor-pass result when the anchor has a non-null value.
2. `_postprocess_tipo()` (lines 219-223) rewrites `fields["tipo"]["value"]` through `normalize_tipo()` from `extraction/normalization.py`.
3. `_retry_areas()` (lines 243-309) iterates unconfident fields and calls `merge_field_sources()` from `extraction/normalization.py` line 96 to swap in better values. The helper uses `pick_best()` to pick between current and candidate based on null-ness and confidence, and updates `field_sources` when the candidate wins.
4. `_merge_tables()` (lines 225-241) replaces `soggetti`, `fidi`, or `garanzie` wholesale if the BODY retry returns more rows or higher-average confidence.
5. `_coherence_check()` (lines 311-328) cross-wires tooltip fields back into their target fields -- if `tooltip_evidenze_b` is populated but `evidenze` is null or a bare number, it overwrites `evidenze` with `"B"`.

Once `extract_from_image()` returns, the dict is effectively frozen -- the only downstream "mutation" is the flat Soggetti copy done inside the same function at lines 160-166.

### Delete
None. There is no deletion. The CLI overwrites `poc_outputs_improved.json` on each run, the edge-agent keeps results in memory until the user closes the window, and the ground truth CSV is never touched by code. The commented-out `_deduplicate_same_page_outputs()` in `extraction/cli.py` lines 92-152 could drop duplicate-page outputs from a batch, but it is currently disabled via a commented call at lines 268-274.

## Validation

Validation is layered and almost entirely runtime. There are no schema migrations, no SQL constraints, no form validators.

**Pydantic structured output** is the first and strictest layer. When the pipeline calls LangChain with `.with_structured_output(ExtractionResponse)`, the LLM response has to deserialize into the full nested Pydantic tree or a `ValidationError` is raised inside `call_vlm_with_retry()`. For newer Gemini models that reject complex `response_schema`, `_call_vlm_gemini_freeform()` in `extraction/vlm_client.py` lines 47-119 takes the free-form JSON back, strips Markdown fences via `_extract_json_str()`, and runs `schema.model_validate_json()` manually. Either way, every field in every returned record is a typed `FieldResult`.

**Confidence gating** is the second layer. The anchor pass zeroes out low-confidence NDG and Denominazione below `ANCHOR_CONF_MIN = 0.95` (`extraction/pipeline.py` lines 91-96). The retry logic flags any field below 0.60 for a second look (`extraction/pipeline.py` line 255). If `STOP_ON_ANCHOR_UNCERTAIN` is set and both anchors are null, the pipeline short-circuits and returns `_status = "ANCHOR_UNCERTAIN"` without running the main pass (`extraction/pipeline.py` lines 112-124).

**Ground-truth-time validation** happens during evaluation. `classify_field()` in `extraction/normalization.py` lines 113-148 emits one of five statuses -- `OK`, `OK_NULL`, `MISSING`, `HALLUCINATED`, `WRONG` -- for every (predicted, expected) pair. Numeric fields (`importo_euro`, `ndg`, `n_fido`) go through `norm_number_str()` for type-tolerant comparison. Long text fields (>20 characters) use `difflib.SequenceMatcher` with a 0.85 ratio threshold for fuzzy matching. `dataset_mismatch_guard()` lines 174-189 is a sanity check that flags entire screens where the NDG or Denominazione differs heavily between GT and prediction, suggesting the operator aligned the CSV to the wrong screenshot. Those screens still appear in the RAW accuracy number but are excluded from the FILTERED number that gets printed as the headline metric.

**Dataset mismatch** is a sixth status that only `build_debug_report()` uses (`extraction/evaluation.py` line 149). It rewrites the per-cell status to `"DATASET_MISMATCH"` when the whole screen trips the guard, so when you read the debug CSV you can tell "this row was wrong" from "this whole screen was comparing against the wrong GT row".

There is no validation on the edge-agent side beyond what the pipeline itself enforces. `RouterResult` (`edge-agent/llm_router.py` lines 27-34) is a `dataclass`, not a Pydantic model, and its `fields: Dict[str, Any]` is passed through untyped.

## Cross-References

- [Architecture](04-architecture.md) -- how the data layer sits between the VLM client and the evaluation/export layers
- [Features](02-features.md) -- the user-facing behaviours that consume these structures
- [Workflows](05-workflows.md) -- the end-to-end flow that creates and reads this data, including the multi-pass pipeline mutations described here
- [Getting Started](07-getting-started.md) -- how to supply the ground truth CSV and inspect the JSON output
