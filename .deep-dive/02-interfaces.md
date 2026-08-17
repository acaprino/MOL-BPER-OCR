# Phase 2: Interface Analysis

Signatures below are copied verbatim from the code (with real type annotations),
cited by `file:line`. This documents what the code actually exposes and returns,
not what the docs describe.

## Public APIs

### `pipeline.py` — the extraction engine

```python
class ExtractionPipeline:                                            # pipeline.py:47
    def __init__(self, main_model: BaseChatModel, anchor_model: BaseChatModel,
                 main_model_name: str, anchor_model_name: str) -> None            # :54
    def extract_anchors(self, content_img: Image.Image, screen_id: str) -> Dict[str, Any]  # :70
    def extract_from_image(self, img: Image.Image, screen_id: str) -> Dict[str, Any]        # :104
    def extract_from_screen(self, path: str) -> Dict[str, Any]                    # :182
    # private: _prepare_content_image, _build_anchor_hint_prompt, _merge_anchors,
    #          _postprocess_tipo, _merge_tables, _retry_areas, _coherence_check,
    #          _aggregate_meta

# Backward-compatible module-level wrappers (build a throwaway pipeline):
def extract_anchors(anchor_model: BaseChatModel, anchor_model_name: str,
                    content_img: Image.Image, screen_id: str) -> Dict[str, Any]   # :347
def extract_from_screen(main_model: BaseChatModel, anchor_model: BaseChatModel,
                        main_model_name: str, anchor_model_name: str,
                        path: str) -> Dict[str, Any]                              # :357
```

Behavioral contract of `extract_from_image` (`pipeline.py:104-180`): runs anchor →
main → conditional retry, then (in this fixed order) merge anchors → normalize `tipo`
→ retry areas → coherence check → aggregate meta → flatten `soggetti[:4]` into
`ndg_1..4`/`denominazione_1..4`/`ruolo_1..4` → build `canonical_fields` → set
`_status`. Early-exit shape when `STOP_ON_ANCHOR_UNCERTAIN=1` and both anchors null
(`pipeline.py:113-124`) omits `canonical_fields` and the top-level `_meta`.

### `cli.py` — orchestration

```python
class BatchRunner:                                                   # cli.py:158
    def __init__(self, *, api_key: Optional[str] = None,
                 provider_name: Optional[str] = None,
                 model_main: Optional[str] = None,
                 model_anchor: Optional[str] = None,
                 parallel: bool = True, max_workers: int = 4) -> None            # :165
    def run(self, paths: List[str],
            on_complete: Optional[Callable[[str, Dict[str, Any]], None]] = None,
            on_error: Optional[Callable[[str, Exception], None]] = None,
            ) -> Dict[str, Dict[str, Any]]                                       # :207

def run_extraction_batch(paths: List[str], *, api_key: Optional[str] = None,
                         provider_name: Optional[str] = None,
                         model_main: Optional[str] = None,
                         model_anchor: Optional[str] = None,
                         parallel: bool = True, max_workers: int = 4,
                         on_complete: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                         on_error: Optional[Callable[[str, Exception], None]] = None,
                         ) -> Dict[str, Dict[str, Any]]              # cli.py:282
def main() -> None                                                   # cli.py:314
```

### `evaluation.py` — ground truth, metrics, reporting

```python
def load_ground_truth(csv_path: str) -> Dict[str, Dict[str, Any]]                # :33
def eval_outputs(outputs: Dict[str, Dict[str, Any]],
                 gt: Dict[str, Dict[str, Any]]) -> Dict[str, Any]                # :74
def build_debug_report(outputs: Dict[str, Dict[str, Any]],
                       gt: Dict[str, Dict[str, Any]], out_csv_path: str) -> None # :125
def export_to_csv(outputs: Dict[str, Dict[str, Any]], out_csv_path: str) -> None # :182
def print_cost_summary(outputs: Dict[str, Dict[str, Any]]) -> None               # :244
def infer_screenshots_from_gt(gt: Dict[str, Dict[str, Any]], base_dir: str = ".") -> List[str]  # :19

class Evaluator:                                                     # evaluation.py:265
    def __init__(self, gt: Dict[str, Dict[str, Any]]) -> None                    # :268
    def eval(self, outputs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]         # :271
    def build_debug_report(self, outputs: Dict[str, Dict[str, Any]], out_csv_path: str) -> None  # :275
    @staticmethod
    def print_cost_summary(outputs: Dict[str, Dict[str, Any]]) -> None           # :279
```

`eval_outputs` returns `{"acc_raw": float, "acc_filt": float, "per_field_filt":
Dict[str, [correct, total]]}` (`evaluation.py:116-120`) and prints RAW + FILTERED
accuracy as a side effect.

### `vlm_client.py` — VLM calls (LangChain structured output)

```python
def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float  # :21
def call_vlm(chat_model: BaseChatModel, image_bytes: bytes, prompt: str,
             screen_id: str, attempt: str, model: str,
             schema: Type[BaseModel]) -> Dict[str, Any]              # vlm_client.py:122
def call_vlm_with_retry(chat_model: BaseChatModel, image_bytes: bytes, prompt: str,
                        screen_id: str, attempt: str, model: str,
                        schema: Type[BaseModel], max_retries: int = 3) -> Dict[str, Any]  # :229
```

`call_vlm` returns `schema.model_dump()` plus a top-level `_meta` dict (see Contracts),
`screen_id`, `attempt`. `call_vlm_with_retry` retries only transient errors;
`ValueError` (parse/validation) is re-raised immediately (`vlm_client.py:252-253`).

### `llm_factory.py`

```python
def create_chat_model(provider_name: str, *, model: str,
                      api_key: Optional[str] = None) -> BaseChatModel  # llm_factory.py:16
```

Raises `ValueError` for unknown provider, missing key, or provider/model mismatch
(e.g. a `gemini-*` model under `openai`). Lazy-imports `langchain_openai` /
`langchain_google_genai`.

### `normalization.py`

```python
def normalize_tipo(val: Any) -> Any                                              # :16
def is_nullish(v: Any) -> bool                                                   # :28
def norm_text(x: Any) -> str                                                     # :34
def norm_number_str(x: Any) -> str                                               # :40
def safe_field(fields: Dict[str, Any], key: str) -> Dict[str, Any]              # :60
def safe_set_field(fields: Dict[str, Any], key: str, *, value=None,
                   confidence=None, evidence_text=None, section=None) -> None    # :71
def pick_best(f1: Dict[str, Any], f2: Dict[str, Any]) -> Dict[str, Any]         # :87
def merge_field_sources(field_sources: Dict[str, str], field_key: str,
                        current: Dict[str, Any], candidate: Dict[str, Any],
                        candidate_source: str) -> Dict[str, Any]                 # :98
def classify_field(gt_val: Any, pred_val: Any,
                   field_key: Optional[str] = None) -> Tuple[str, str]           # :113
def get_pred_value_for_gt_key(pred: Dict[str, Any], gt_key: str
        ) -> Tuple[Optional[str], Any, float, Optional[str], Optional[str]]      # :150
def dataset_mismatch_guard(gt_kv: Dict[str, Any], pred: Dict[str, Any]) -> bool  # :174
```

`classify_field` status ∈ `{"OK", "WRONG", "MISSING", "HALLUCINATED", "OK_NULL"}`.
`pick_best`: non-null beats null; on equal nullness, higher confidence wins, ties
keep `f1` (`normalization.py:90-96`).

### `imaging.py`

```python
def normalize_image(img: Image.Image, long_side: int = 1800) -> Image.Image      # :12
def crop_relative(img: Image.Image,
                  box: Tuple[float, float, float, float]) -> Image.Image          # :22
def img_to_png_bytes(img: Image.Image) -> bytes                                   # :31
def save_debug_crop(img: Image.Image, screen_id: str, name: str) -> None          # :37
```

### `canonical_mapping.py`, `fields.py`, `field_definitions.py`, `page_definitions.py`

```python
def build_canonical_field_entries(fields: Dict[str, Any]) -> List[Dict[str, Any]]  # canonical_mapping.py:20

def get_canonical_field_display_name(schema_key: str) -> str                       # fields.py:118
def get_canonical_field_page_key(schema_key: str) -> Optional[str]                 # fields.py:124
def get_canonical_field_metadata(schema_key: str) -> Dict[str, Optional[str]]      # fields.py:128

def normalize_field_label(label: str) -> str                                       # field_definitions.py:238
def resolve_schema_key(label: str) -> Optional[str]                                # field_definitions.py:243
def resolve_display_name(schema_key: str) -> Optional[str]                         # field_definitions.py:249
def resolve_field_page_key(schema_key: str) -> Optional[str]                       # field_definitions.py:257

def normalize_page_label(label: str) -> str                                        # page_definitions.py:31
def resolve_page_key(label: str) -> Optional[str]                                  # page_definitions.py:36
def resolve_page_name(label: str) -> Optional[str]                                 # page_definitions.py:42
def get_canonical_page_name(page_key: str) -> Optional[str]                        # page_definitions.py:49
```

`build_canonical_field_entries` returns a list of
`{schema_key, display_name, page_key, page_name, value, confidence, evidence_text,
section}` sorted by `PAGE_SHEET_ORDER` then display name (`canonical_mapping.py:8-18,
29-42`).

### `config.py`

```python
def get_screenshot_paths(gt: Dict[str, Any], base_dir: str = ".") -> List[str]    # config.py:99
```
(Exported/aliased but no live caller — `main()` scans `INPUT_DIR` directly.)

## Contracts

### Pydantic models (`schemas.py`)

```python
class FieldResult(BaseModel):                       # schemas.py:9
    value: Optional[str] = None
    confidence: float = 0.0
    evidence_text: Optional[str] = None
    section: Optional[str] = None

class Soggetto(BaseModel):                           # :15
    ndg: Optional[str]; denominazione: Optional[str]; ruolo: Optional[str]
    confidence: float = 0.0; evidence_text: Optional[str] = None

class Fido(BaseModel):                               # :22
    n_fido, rapporto, descrizione, scadenza, importo_euro, tipo_op: Optional[str]
    confidence: float = 0.0; evidence_text: Optional[str] = None

class Garanzia(BaseModel):                           # :32
    n_gar, descrizione, fido, ndg, denominazione, importo_percentuale, tipo_op: Optional[str]
    confidence: float = 0.0; evidence_text: Optional[str] = None

# Dynamic — one Optional[FieldResult] per key in FIELD_KEYS (single source of truth):
FieldsModel = create_model("FieldsModel",
    **{k: (Optional[FieldResult], None) for k in FIELD_KEYS})   # :46-49

class ExtractionResponse(BaseModel):                 # :54
    fields: FieldsModel = Field(default_factory=FieldsModel)
    soggetti: List[Soggetto]  = Field(default_factory=list)
    fidi:     List[Fido]      = Field(default_factory=list)
    garanzie: List[Garanzia]  = Field(default_factory=list)

class AnchorFields(BaseModel):                       # :60
    ndg: Optional[FieldResult] = None
    denominazione: Optional[FieldResult] = None
class AnchorResponse(BaseModel):                     # :64
    fields: AnchorFields = Field(default_factory=AnchorFields)

RESPONSE_SCHEMA = ExtractionResponse   # legacy aliases   :70
ANCHOR_SCHEMA   = AnchorResponse                          #  :71
```

### Result-dict shape (produced by `ExtractionPipeline.extract_from_image`)

The pipeline returns a plain `dict` (the `model_dump()` of `ExtractionResponse`
mutated in place). Normal (non-early-exit) shape:

```python
{
  "fields": { <field_key>: {"value","confidence","evidence_text","section"} | None, ... },  # one per FIELD_KEYS
  "soggetti": [ {ndg, denominazione, ruolo, confidence, evidence_text}, ... ],
  "fidi":     [ {n_fido, rapporto, descrizione, scadenza, importo_euro, tipo_op, confidence, evidence_text}, ... ],
  "garanzie": [ {n_gar, descrizione, fido, ndg, denominazione, importo_percentuale, tipo_op, confidence, evidence_text}, ... ],
  "screen_id": str,                       # from main pass
  "attempt": "CONTENT_MAIN",              # from main pass
  "_meta": { ... main-pass meta ... },    # top-level, single call (see below)
  "_attempts": [ {…anchor meta…}, {…main meta…}, {…retry meta…}? ],
  "_meta_agg": {                          # pipeline.py:330-340
      "model_main", "model_anchor", "calls",
      "prompt_tokens", "completion_tokens", "total_tokens",
      "estimated_cost_usd", "latency_ms"
  },
  "_field_sources": { <field_key>: "ANCHOR_HEADER"|"CONTENT_MAIN"|"RETRY_HEADER"|"RETRY_BODY"|"RETRY_FOOTER" },
  "canonical_fields": [ {schema_key, display_name, page_key, page_name, value,
                         confidence, evidence_text, section}, ... ],   # page-ordered
  "_status": "OK" | "ANCHOR_UNCERTAIN"
}
```

Per-call `_meta` (from `call_vlm`, `vlm_client.py:107-116 / 167-176 / 214-223`):
`{model, screen_id, attempt, latency_ms, prompt_tokens, completion_tokens,
total_tokens, estimated_cost_usd}`.

Caveats that are part of the contract:
- `fields[ndg_1..4 / denominazione_1..4 / ruolo_1..4]` are **unconditionally
  overwritten** from `soggetti[:4]` (even with `None`), and this flatten does **not**
  update `_field_sources` (`pipeline.py:161-166`).
- Early-exit shape (`STOP_ON_ANCHOR_UNCERTAIN`, `pipeline.py:114-124`):
  `{screen_id, fields:{}, soggetti:[], fidi:[], garanzie:[], _status:"ANCHOR_UNCERTAIN",
  _attempts:[anchor_meta], _meta_agg, _field_sources:{}}` — no `canonical_fields`, no
  top-level `_meta`.

### Config-constants contract (`config.py`, `fields.py`)

- `FIELD_KEYS: List[str]` — **45** schema keys, single source of truth for
  `FieldsModel`, retry loops, evaluation (`fields.py:12-54`).
- `CSV_TO_SCHEMA: Dict[str, str]` — CSV header → schema key (`fields.py:56-100`);
  drives `eval_outputs` and `get_pred_value_for_gt_key`.
- `AREA_TO_FIELDS: Dict[str, List[str]]` — `{"HEADER":[8], "BODY":[29], "FOOTER":[2]}`
  (`config.py:69-82`). **Does not cover** `creazione` + 5 `tooltip_*` (6 of 45 keys
  never retried).
- `FIELD_RETRY_MAP: Dict[str, str]` — inverted `AREA_TO_FIELDS` (`config.py:85-88`).
- `RETRY_AREAS: Dict[str, tuple]` — per-area relative crop boxes (`config.py:63-67`).
- `CONTENT_CROP = (0.18,0.12,0.98,0.98)`, `HEADER_IN_CONTENT = (0.00,0.00,1.00,0.22)`.
- `PRICING_PER_1M: Dict[str, {"input","output"}]` — cost table; **missing model → $0.0**
  (`config.py:36-49`, `vlm_client.py:23-25`).
- `PROVIDER_MODELS: Dict[str, List[str]]` — provider → allowed model IDs
  (`config.py:22-33`); consumed by `gui_app.py` dropdown.
- `_SOGGETTI_KEY_MAP`, `_GARANZIE_KEY_MAP` (`fields.py:102-116`) — table column → key.

### Ground-truth CSV contract (`evaluation.load_ground_truth`)

Three columns, auto-detected by candidate names (`evaluation.py:38-52`):
- **screen** ∈ `{"Screenshot","Fotogramma","Screen","screen"}`
- **key** ∈ `{"Denominazione da attribuire","Denominazione","Campo","Field"}`
- **value** ∈ `{"Valore rilevato","Valore rilevato ","Valore","Value"}`

Missing any → `ValueError` (`evaluation.py:26-31`). Output:
`{ screen_id: { csv_key: value } }`; blank/`nan` keys skipped, `nan` values → `""`
(`evaluation.py:58-69`). The file is **not in the repo** (`/mnt` gitignored); `main()`
raises `FileNotFoundError` without it (`cli.py:315-316`).

## External Dependencies

| Library | Where / how used |
|---|---|
| **langchain-core** (`BaseChatModel`, `SystemMessage`, `HumanMessage`) | Type of the shared chat models (`pipeline.py:7`, `cli.py`, `llm_factory.py:7`); message construction in `vlm_client.py:9-10, 69-74, 141-146, 186-192`. |
| **langchain-openai** (`ChatOpenAI`) | Lazy-imported OpenAI branch of `create_chat_model` (`llm_factory.py:47-54`). |
| **langchain-google-genai** (`ChatGoogleGenerativeAI`) | Lazy-imported Gemini branch, with `safety_settings` + optional `thinking_level` (`llm_factory.py:57-75`). |
| **pydantic** (`BaseModel`, `Field`, `create_model`) | All structured-output schemas (`schemas.py:3`); manual `model_validate_json` / `model_json_schema` in the Gemini free-form path (`vlm_client.py:11, 63, 93`). LangChain's `.with_structured_output(schema, include_raw=True)` binds these (`vlm_client.py:147, 193`). |
| **Pillow / PIL** (`Image`, `ImageEnhance`, `ImageFilter`) | `imaging.py:7` (normalize/crop/encode); per-area contrast+sharpness boosts in `pipeline._retry_areas` (`pipeline.py:6, 268-272`); `Image.open(...).convert("RGB")` in `extract_from_screen` (`pipeline.py:184`). |
| **pandas** (`pd`) | Only in `evaluation.py:5` — `read_csv` for ground truth (`:35`) and `DataFrame(...).to_csv(...)` for debug + export (`:172-177, 234-239`). |
| **stdlib** | `base64` (image → data URI, `vlm_client.py:132`), `json` (JSON extraction/dumps, `vlm_client.py`, `cli.py`), `re` (`_extract_json_str`, `normalize`, coherence regex), `time` (retry backoff + latency, `vlm_client.py:256-257`), `concurrent.futures.ThreadPoolExecutor` (batch runner `cli.py:5` + per-area retry `pipeline.py:5, 284`), `os` (paths/env), `io` (PNG buffer), `difflib.SequenceMatcher` (fuzzy match, `normalization.py:3, 143`), `warnings` (`__init__.py:8-9`, `llm_factory.py:36`). |

Not imported anywhere in this package: `openai`, `torch`, `mss`, `PyQt6` — those
belong to the edge-agent, which reuses only `create_chat_model`, `ExtractionPipeline`,
and the three `LLM_*` config constants.

## How to Add a New Module

Follow the existing layered pattern (see `01-structure.md`). Concrete steps, using
`imaging.py`/`normalization.py` as reference templates:

1. **Create `extraction/<name>.py`.** Start with a one-line module docstring. Add the
   full-width section markers
   `# ============================================================` between logical
   blocks.
2. **Respect the dependency direction.** Import only from lower layers (leaves →
   primitives → engines). Read env/config through `extraction.config`, never
   `os.getenv` directly (mirrors `imaging.py:9`, `vlm_client.py:13`). Keep provider
   SDK imports lazy and centralized in `llm_factory.py` — do not add a second place
   that constructs chat models (Architectural Constraint #5).
3. **Match the interface style.** Fully annotate every parameter and the return type.
   Use `snake_case` functions, `_leading_underscore` for private helpers, and
   `PascalCase` for any Pydantic model (with an `UPPER_SNAKE_CASE` legacy alias only
   if a caller needs it).
4. **If it touches fields/pages**, resolve through the canonical helpers
   (`fields.get_canonical_field_metadata`, `page_definitions.get_canonical_page_name`)
   rather than hardcoding display names.
5. **Register in the facade** (`extraction/__init__.py`): add each public symbol to
   `__all__` (`__init__.py:11-45`) **and** to a `from extraction.<name> import ...`
   block (`__init__.py:47-126`). Both are required — `__all__` alone does not import.
6. **Wire consumers deliberately.** For a new engine, expose it via
   `run_extraction_batch`/`ExtractionPipeline` rather than a parallel path. For a new
   output format, add an `export_*`/`build_*_report` function in `evaluation.py`
   alongside the existing ones and re-export it.
7. **Update field-config in lockstep** if the module adds fields: `FIELD_KEYS`,
   `CSV_TO_SCHEMA`, `AREA_TO_FIELDS`, `field_definitions.CANONICAL_FIELD_DEFINITIONS`,
   and the relevant prompt. Nothing validates these against each other — a missing
   `AREA_TO_FIELDS` entry silently disables retry for that field.
8. **Verify** by importing `extraction` (import-time config must not raise) and running
   `python main.py` against a local `mnt/data/dati.csv`, or an edge-agent smoke test if
   the module is on the `extract_from_image` path.
