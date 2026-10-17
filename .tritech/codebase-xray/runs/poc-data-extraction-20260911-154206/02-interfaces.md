# Phase 2: Interface Analysis

## Public APIs (by partition)

### Partition: root

Le firme seguenti sono **[verified]**: estratte con il parser del plugin e verificate nel sorgente, senza importare moduli applicativi. Sono conservati i tipi effettivamente annotati e i separatori keyword-only; dove manca un'annotazione non si deduce una promessa di tipo dal corpo. `self` è omesso dalla presentazione. Le forme dei dizionari, i segnali e le condizioni semantiche sono descritti in `Contracts`; la disponibilità delle API non certifica gli esiti dei provider o del sistema grafico.

**[verified]** La facade `extraction` espone configurazione, factory, vocabolario, schema, normalizzazione, imaging, pipeline e batch mediante `__all__` e import eager (`extraction/__init__.py:11`, `__all__`; `extraction/__init__.py:47`). I moduli di dati/configurazione sono descritti nei contratti: `extraction/config.py:16`, `LLM_PROVIDER`; `extraction/prompts.py:6`; `extraction/schemas.py:68`, `FieldsModel`. I package desktop contengono marker/re-export (`edge-agent/__init__.py:1`; `edge-agent/ui/__init__.py:1`; `edge-agent/workers/__init__.py:3`; `edge-agent/workers/capture/__init__.py:3`).

**[verified]** Gli ingressi sono `main.py:7` (CLI o `--gui`), `gui_app.py:16` (`App`) ed `edge-agent/edge_agent.py:38` (`main`). Lo shim non dichiara una funzione propria: il main CLI è `extraction/cli.py:318`, `main`. Questi ingressi non definiscono un server HTTP.


#### Catalogo e front-end

##### `prompt_store.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `load_prompts(directory: Path) -> Dict[str, Prompt]` | **[verified]** `prompt_store.py:239`, `load_prompts` |
| `catalog_source() -> Path` | **[verified]** `prompt_store.py:287`, `catalog_source` |
| `get_prompt(prompt_id: str) -> Prompt` | **[verified]** `prompt_store.py:292`, `get_prompt` |
| `get_text(prompt_id: str) -> str` | **[verified]** `prompt_store.py:302`, `get_text` |
| `get_part(prompt_id: str, part: str) -> str` | **[verified]** `prompt_store.py:310`, `get_part` |

##### `gui_app.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `App.__init__()` | **[verified]** `gui_app.py:17`, `App.__init__` |
| `App.run_process()` | **[verified]** `gui_app.py:228`, `App.run_process` |
| `App.display_results(outputs, metrics=None)` | **[verified]** `gui_app.py:287`, `App.display_results` |

##### `edge-agent/edge_agent.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `main() -> int` | **[verified]** `edge-agent/edge_agent.py:38`, `main` |

#### Core: vocabolario, immagini e normalizzazione

##### `extraction/field_definitions.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `normalize_field_label(label: str) -> str` | **[verified]** `extraction/field_definitions.py:238`, `normalize_field_label` |
| `resolve_schema_key(label: str) -> Optional[str]` | **[verified]** `extraction/field_definitions.py:243`, `resolve_schema_key` |
| `resolve_display_name(schema_key: str) -> Optional[str]` | **[verified]** `extraction/field_definitions.py:249`, `resolve_display_name` |
| `resolve_field_page_key(schema_key: str) -> Optional[str]` | **[verified]** `extraction/field_definitions.py:257`, `resolve_field_page_key` |

##### `extraction/page_definitions.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `normalize_page_label(label: str) -> str` | **[verified]** `extraction/page_definitions.py:31`, `normalize_page_label` |
| `resolve_page_key(label: str) -> Optional[str]` | **[verified]** `extraction/page_definitions.py:36`, `resolve_page_key` |
| `resolve_page_name(label: str) -> Optional[str]` | **[verified]** `extraction/page_definitions.py:42`, `resolve_page_name` |
| `get_canonical_page_name(page_key: str) -> Optional[str]` | **[verified]** `extraction/page_definitions.py:49`, `get_canonical_page_name` |

##### `extraction/fields.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `get_canonical_field_display_name(schema_key: str) -> str` | **[verified]** `extraction/fields.py:102`, `get_canonical_field_display_name` |
| `get_canonical_field_page_key(schema_key: str) -> Optional[str]` | **[verified]** `extraction/fields.py:108`, `get_canonical_field_page_key` |
| `get_canonical_field_metadata(schema_key: str) -> Dict[str, Optional[str]]` | **[verified]** `extraction/fields.py:112`, `get_canonical_field_metadata` |

##### `extraction/canonical_mapping.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `build_canonical_field_entries(fields: Dict[str, Any]) -> List[Dict[str, Any]]` | **[verified]** `extraction/canonical_mapping.py:20`, `build_canonical_field_entries` |

##### `extraction/imaging.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `normalize_image(img: Image.Image, long_side: int = 1800) -> Image.Image` | **[verified]** `extraction/imaging.py:19`, `normalize_image` |
| `screen_id_from_path(path: str) -> str` | **[verified]** `extraction/imaging.py:29`, `screen_id_from_path` |
| `clamp_long_side(img: Image.Image, max_side: int) -> Image.Image` | **[verified]** `extraction/imaging.py:38`, `clamp_long_side` |
| `select_content_crop(size: Tuple[int, int]) -> Optional[Tuple[float, float, float, float]]` | **[verified]** `extraction/imaging.py:52`, `select_content_crop` |
| `crop_relative(img: Image.Image, box: Tuple[float, float, float, float]) -> Image.Image` | **[verified]** `extraction/imaging.py:78`, `crop_relative` |
| `img_to_png_bytes(img: Image.Image) -> bytes` | **[verified]** `extraction/imaging.py:87`, `img_to_png_bytes` |
| `save_debug_crop(img: Image.Image, screen_id: str, name: str) -> None` | **[verified]** `extraction/imaging.py:93`, `save_debug_crop` |

##### `extraction/normalization.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `normalize_tipo(val: Any) -> Any` | **[verified]** `extraction/normalization.py:16`, `normalize_tipo` |
| `is_nullish(v: Any) -> bool` | **[verified]** `extraction/normalization.py:28`, `is_nullish` |
| `norm_text(x: Any) -> str` | **[verified]** `extraction/normalization.py:34`, `norm_text` |
| `norm_number_str(x: Any) -> str` | **[verified]** `extraction/normalization.py:40`, `norm_number_str` |
| `escape_csv_formula(value: Any) -> Any` | **[verified]** `extraction/normalization.py:62`, `escape_csv_formula` |
| `safe_field(fields: Dict[str, Any], key: str) -> Dict[str, Any]` | **[verified]** `extraction/normalization.py:77`, `safe_field` |
| `safe_set_field(fields: Dict[str, Any], key: str, *, value=None, confidence=None, evidence_text=None, section=None) -> None` | **[verified]** `extraction/normalization.py:88`, `safe_set_field` |
| `pick_best(f1: Dict[str, Any], f2: Dict[str, Any]) -> Dict[str, Any]` | **[verified]** `extraction/normalization.py:104`, `pick_best` |
| `merge_field_sources( field_sources: Dict[str, str], field_key: str, current: Dict[str, Any], candidate: Dict[str, Any], candidate_source: str, ) -> Dict[str, Any]` | **[verified]** `extraction/normalization.py:115`, `merge_field_sources` |
| `classify_field(gt_val: Any, pred_val: Any, field_key: Optional[str] = None) -> Tuple[str, str]` | **[verified]** `extraction/normalization.py:134`, `classify_field` |
| `get_pred_value_for_gt_key(pred: Dict[str, Any], gt_key: str) -> Tuple[Optional[str], Any, float, Optional[str], Optional[str]]` | **[verified]** `extraction/normalization.py:171`, `get_pred_value_for_gt_key` |
| `dataset_mismatch_guard(gt_kv: Dict[str, Any], pred: Dict[str, Any]) -> bool` | **[verified]** `extraction/normalization.py:195`, `dataset_mismatch_guard` |

#### Core: provider, pipeline e batch

##### `extraction/llm_factory.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `create_chat_model( provider_name: str, *, model: str, api_key: Optional[str] = None, ) -> BaseChatModel` | **[verified]** `extraction/llm_factory.py:18`, `create_chat_model` |

##### `extraction/vlm_client.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float` | **[verified]** `extraction/vlm_client.py:26`, `estimate_cost_usd` |
| `call_vlm( chat_model: BaseChatModel, image_bytes: bytes, prompt: str, screen_id: str, attempt: str, model: str, schema: Type[BaseModel], ) -> Dict[str, Any]` | **[verified]** `extraction/vlm_client.py:123`, `call_vlm` |
| `call_vlm_with_retry( chat_model: BaseChatModel, image_bytes: bytes, prompt: str, screen_id: str, attempt: str, model: str, schema: Type[BaseModel], max_retries: int = 3, ) -> Dict[str, Any]` | **[verified]** `extraction/vlm_client.py:230`, `call_vlm_with_retry` |

##### `extraction/pipeline.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `extract_anchors( anchor_model: BaseChatModel, anchor_model_name: str, content_img: Image.Image, screen_id: str, ) -> Dict[str, Any]` | **[verified]** `extraction/pipeline.py:400`, `extract_anchors` |
| `extract_from_screen( main_model: BaseChatModel, anchor_model: BaseChatModel, main_model_name: str, anchor_model_name: str, path: str, ) -> Dict[str, Any]` | **[verified]** `extraction/pipeline.py:410`, `extract_from_screen` |
| `ExtractionPipeline.__init__(main_model: BaseChatModel, anchor_model: BaseChatModel, main_model_name: str, anchor_model_name: str, ) -> None` | **[verified]** `extraction/pipeline.py:62`, `ExtractionPipeline.__init__` |
| `ExtractionPipeline.extract_anchors(content_img: Image.Image, screen_id: str, *, calibrated: bool = True ) -> Dict[str, Any]` | **[verified]** `extraction/pipeline.py:78`, `ExtractionPipeline.extract_anchors` |
| `ExtractionPipeline.extract_from_image(img: Image.Image, screen_id: str, *, allow_content_crop: bool = False ) -> Dict[str, Any]` | **[verified]** `extraction/pipeline.py:122`, `ExtractionPipeline.extract_from_image` |
| `ExtractionPipeline.extract_from_screen(path: str) -> Dict[str, Any]` | **[verified]** `extraction/pipeline.py:223`, `ExtractionPipeline.extract_from_screen` |

##### `extraction/cli.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `run_extraction_batch( paths: List[str], *, api_key: Optional[str] = None, provider_name: Optional[str] = None, model_main: Optional[str] = None, model_anchor: Optional[str] = None, parallel: bool = True, max_workers: int = 4, on_complete: Optional[Callable[[str, Dict[str, Any]], None]] = None, on_error: Optional[Callable[[str, Exception], None]] = None, ) -> Dict[str, Dict[str, Any]]` | **[verified]** `extraction/cli.py:285`, `run_extraction_batch` |
| `main() -> None` | **[verified]** `extraction/cli.py:318`, `main` |
| `BatchRunner.__init__(*, api_key: Optional[str] = None, provider_name: Optional[str] = None, model_main: Optional[str] = None, model_anchor: Optional[str] = None, parallel: bool = True, max_workers: int = 4, ) -> None` | **[verified]** `extraction/cli.py:164`, `BatchRunner.__init__` |
| `BatchRunner.run(paths: List[str], on_complete: Optional[Callable[[str, Dict[str, Any]], None]] = None, on_error: Optional[Callable[[str, Exception], None]] = None, ) -> Dict[str, Dict[str, Any]]` | **[verified]** `extraction/cli.py:210`, `BatchRunner.run` |

##### `extraction/evaluation.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `load_ground_truth(csv_path: str) -> Dict[str, Dict[str, Any]]` | **[verified]** `extraction/evaluation.py:47`, `load_ground_truth` |
| `eval_outputs(outputs: Dict[str, Dict[str, Any]], gt: Dict[str, Dict[str, Any]]) -> Dict[str, Any]` | **[verified]** `extraction/evaluation.py:88`, `eval_outputs` |
| `build_debug_report( outputs: Dict[str, Dict[str, Any]], gt: Dict[str, Dict[str, Any]], out_csv_path: str, ) -> None` | **[verified]** `extraction/evaluation.py:139`, `build_debug_report` |
| `export_to_csv(outputs: Dict[str, Dict[str, Any]], out_csv_path: str) -> None` | **[verified]** `extraction/evaluation.py:191`, `export_to_csv` |
| `print_cost_summary(outputs: Dict[str, Dict[str, Any]]) -> None` | **[verified]** `extraction/evaluation.py:248`, `print_cost_summary` |
| `Evaluator.__init__(gt: Dict[str, Dict[str, Any]]) -> None` | **[verified]** `extraction/evaluation.py:272`, `Evaluator.__init__` |
| `Evaluator.eval(outputs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]` | **[verified]** `extraction/evaluation.py:275`, `Evaluator.eval` |
| `Evaluator.build_debug_report(outputs: Dict[str, Dict[str, Any]], out_csv_path: str) -> None` | **[verified]** `extraction/evaluation.py:279`, `Evaluator.build_debug_report` |
| `Evaluator.print_cost_summary(outputs: Dict[str, Dict[str, Any]]) -> None` | **[verified]** `extraction/evaluation.py:284`, `Evaluator.print_cost_summary` |

#### Desktop: percorsi, configurazione e avvio

##### `edge-agent/app_paths.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `is_frozen() -> bool` | **[verified]** `edge-agent/app_paths.py:9`, `is_frozen` |
| `app_dir() -> Path` | **[verified]** `edge-agent/app_paths.py:14`, `app_dir` |
| `project_root() -> Path` | **[verified]** `edge-agent/app_paths.py:26`, `project_root` |
| `config_ini() -> Path` | **[verified]** `edge-agent/app_paths.py:33`, `config_ini` |
| `env_file() -> Path` | **[verified]** `edge-agent/app_paths.py:38`, `env_file` |
| `templates_dir() -> Path` | **[verified]** `edge-agent/app_paths.py:43`, `templates_dir` |
| `torch_cache_dir() -> Path` | **[verified]** `edge-agent/app_paths.py:48`, `torch_cache_dir` |
| `bundled_defaults_dir() -> Path` | **[verified]** `edge-agent/app_paths.py:53`, `bundled_defaults_dir` |
| `prompts_dir() -> Path` | **[verified]** `edge-agent/app_paths.py:60`, `prompts_dir` |
| `bundled_prompts_dir() -> Path` | **[verified]** `edge-agent/app_paths.py:65`, `bundled_prompts_dir` |
| `bundled_assets_dir() -> Path` | **[verified]** `edge-agent/app_paths.py:72`, `bundled_assets_dir` |

##### `edge-agent/config.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `AgentConfig.__init__(config_path: Optional[Path] = None)` | **[verified]** `edge-agent/config.py:58`, `AgentConfig.__init__` |
| `AgentConfig.resolve_llm_settings() -> Tuple[str, str, str]` | **[verified]** `edge-agent/config.py:292`, `AgentConfig.resolve_llm_settings` |
| `AgentConfig.update_from_ui(fps: int, window_filter: str) -> None` | **[verified]** `edge-agent/config.py:323`, `AgentConfig.update_from_ui` |
| `AgentConfig.save() -> None` | **[verified]** `edge-agent/config.py:339`, `AgentConfig.save` |

##### `edge-agent/bootstrap.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `run_preflight(parent: Optional[QtWidgets.QWidget] = None) -> Optional[AgentConfig]` | **[verified]** `edge-agent/bootstrap.py:489`, `run_preflight` |

#### Desktop: cattura, classificazione e consegna

##### `edge-agent/frame_normalize.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `crop_to_rect(img: Image.Image, monitor: Dict[str, int], window_rect: Optional[Rect]) -> Image.Image` | **[verified]** `edge-agent/frame_normalize.py:49`, `crop_to_rect` |
| `detect_app_rect(img: Image.Image, *, tolerance: int = _COLOR_TOLERANCE) -> Optional[Rect]` | **[verified]** `edge-agent/frame_normalize.py:72`, `detect_app_rect` |
| `select_window_rect( title_substring: str, windows: Iterable[Dict[str, Any]], own_pid: int, ) -> Optional[Rect]` | **[verified]** `edge-agent/frame_normalize.py:113`, `select_window_rect` |
| `find_window_rect(title_substring: str) -> Optional[Rect]` | **[verified]** `edge-agent/frame_normalize.py:194`, `find_window_rect` |
| `normalize_frame( img: Image.Image, monitor: Dict[str, int], window_rect_provider: Callable[[], Optional[Rect]], ) -> Tuple[Image.Image, str]` | **[verified]** `edge-agent/frame_normalize.py:209`, `normalize_frame` |

##### `edge-agent/image_ops.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `preprocess_for_ocr( img: Image.Image, *, scale: Optional[float] = None, unsharp_amount: float = 0.8, unsharp_radius: float = 1.2, unsharp_threshold: int = 2, contrast_stretch: bool = True, ) -> Image.Image` | **[verified]** `edge-agent/image_ops.py:21`, `preprocess_for_ocr` |
| `to_png8(img: Image.Image) -> bytes` | **[verified]** `edge-agent/image_ops.py:58`, `to_png8` |
| `to_webp_lossless(img: Image.Image) -> bytes` | **[verified]** `edge-agent/image_ops.py:67`, `to_webp_lossless` |

##### `edge-agent/page_registry.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `slugify(name: str) -> str` | **[verified]** `edge-agent/page_registry.py:12`, `slugify` |
| `PageRegistry.__init__(pages: List[PageDef], catchall_name: Optional[str]) -> None` | **[verified]** `edge-agent/page_registry.py:30`, `PageRegistry.__init__` |
| `PageRegistry.load(cls, prompts_path: Path) -> "PageRegistry"` | **[verified]** `edge-agent/page_registry.py:40`, `PageRegistry.load` |
| `PageRegistry.empty(cls) -> "PageRegistry"` | **[verified]** `edge-agent/page_registry.py:63`, `PageRegistry.empty` |
| `PageRegistry.resolve(label: Optional[str]) -> Optional[PageDef]` | **[verified]** `edge-agent/page_registry.py:69`, `PageRegistry.resolve` |
| `PageRegistry.acquirable(router_mode: str) -> List[PageDef]` | **[verified]** `edge-agent/page_registry.py:83`, `PageRegistry.acquirable` |
| `PageRegistry.names(router_mode: str = "llm") -> List[str]` | **[verified]** `edge-agent/page_registry.py:89`, `PageRegistry.names` |

##### `edge-agent/stability.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `StabilityTracker.__init__(config: Optional[StabilityConfig] = None) -> None` | **[verified]** `edge-agent/stability.py:29`, `StabilityTracker.__init__` |
| `StabilityTracker.reset() -> None` | **[verified]** `edge-agent/stability.py:38`, `StabilityTracker.reset` |
| `StabilityTracker.observe(page: Optional[str], now: float) -> Optional[str]` | **[verified]** `edge-agent/stability.py:46`, `StabilityTracker.observe` |
| `StabilityTracker.confirm(now: float) -> Optional[str]` | **[verified]** `edge-agent/stability.py:76`, `StabilityTracker.confirm` |

##### `edge-agent/llm_router.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `PageRouter.route(image: Image.Image) -> RouterResult` | **[verified]** `edge-agent/llm_router.py:39`, `PageRouter.route` |
| `MLPageRouter.__init__(templates_dir: Path, classifier: Optional[Any] = None) -> None` | **[verified]** `edge-agent/llm_router.py:46`, `MLPageRouter.__init__` |
| `MLPageRouter.route(image: Image.Image) -> RouterResult` | **[verified]** `edge-agent/llm_router.py:61`, `MLPageRouter.route` |
| `LLMPageRouter.__init__(prompts_path: Path, *, provider: str = "openai", base_url: str = "https://api.openai.com/v1", model: str = "gpt-4o-mini", api_key: str = "", timeout: int = 60, ) -> None` | **[verified]** `edge-agent/llm_router.py:73`, `LLMPageRouter.__init__` |
| `LLMPageRouter.set_expected_page(name: Optional[str]) -> None` | **[verified]** `edge-agent/llm_router.py:158`, `LLMPageRouter.set_expected_page` |
| `LLMPageRouter.get_page_hints(name: str) -> Optional[str]` | **[verified]** `edge-agent/llm_router.py:162`, `LLMPageRouter.get_page_hints` |
| `LLMPageRouter.route(image: Image.Image) -> RouterResult` | **[verified]** `edge-agent/llm_router.py:172`, `LLMPageRouter.route` |
| `LLMPageRouter.get_last_debug() -> Dict[str, Any]` | **[verified]** `edge-agent/llm_router.py:288`, `LLMPageRouter.get_last_debug` |

##### `edge-agent/page_classifier.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `embedding_geometry(crop_roi: Optional[Tuple[float, float, float, float]] = None, reject_classes: int = 0) -> str` | **[verified]** `edge-agent/page_classifier.py:140`, `embedding_geometry` |
| `cache_is_valid(templates_dir: Path, cache_path: Optional[Path] = None) -> bool` | **[verified]** `edge-agent/page_classifier.py:166`, `cache_is_valid` |
| `BPERPagePrototypeClassifier.__init__(templates_dir: Path, *, cache_path: Optional[Path] = None, crop_roi: Optional[Tuple[float, float, float, float]] = None, similarity_threshold: float = 0.75, device: str = "cpu", ) -> None` | **[verified]** `edge-agent/page_classifier.py:234`, `BPERPagePrototypeClassifier.__init__` |
| `BPERPagePrototypeClassifier.classify_detailed(image) -> "Classification"` | **[verified]** `edge-agent/page_classifier.py:660`, `BPERPagePrototypeClassifier.classify_detailed` |
| `BPERPagePrototypeClassifier.classify(image) -> Tuple[Optional[str], float]` | **[verified]** `edge-agent/page_classifier.py:696`, `BPERPagePrototypeClassifier.classify` |
| `BPERPagePrototypeClassifier.info() -> Dict` | **[verified]** `edge-agent/page_classifier.py:711`, `BPERPagePrototypeClassifier.info` |

##### `edge-agent/extraction_pool.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `DaemonThreadPool.__init__(max_workers: int, name_prefix: str = "extract") -> None` | **[verified]** `edge-agent/extraction_pool.py:23`, `DaemonThreadPool.__init__` |
| `DaemonThreadPool.submit(fn: Callable[..., Any], *args: Any) -> bool` | **[verified]** `edge-agent/extraction_pool.py:33`, `DaemonThreadPool.submit` |
| `DaemonThreadPool.pending() -> int` | **[verified]** `edge-agent/extraction_pool.py:40`, `DaemonThreadPool.pending` |
| `DaemonThreadPool.stop() -> None` | **[verified]** `edge-agent/extraction_pool.py:44`, `DaemonThreadPool.stop` |

##### `edge-agent/local_extraction_client.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `LocalExtractionClient.__init__(parent: Optional[QtCore.QObject] = None, pipeline: Optional[ExtractionPipeline] = None, ) -> None` | **[verified]** `edge-agent/local_extraction_client.py:90`, `LocalExtractionClient.__init__` |
| `LocalExtractionClient.start_job() -> str` | **[verified]** `edge-agent/local_extraction_client.py:121`, `LocalExtractionClient.start_job` |
| `LocalExtractionClient.ingest_frame(job_id: str, img: Image.Image, page_no: int = 0, page_type: str = "", confidence: float = 0.0, fields_json: str = "{}", ) -> None` | **[verified]** `edge-agent/local_extraction_client.py:125`, `LocalExtractionClient.ingest_frame` |
| `LocalExtractionClient.requeue_job(job_id: str) -> bool` | **[verified]** `edge-agent/local_extraction_client.py:180`, `LocalExtractionClient.requeue_job` |
| `LocalExtractionClient.pending_extractions() -> int` | **[verified]** `edge-agent/local_extraction_client.py:184`, `LocalExtractionClient.pending_extractions` |
| `LocalExtractionClient.shutdown() -> None` | **[verified]** `edge-agent/local_extraction_client.py:188`, `LocalExtractionClient.shutdown` |
| `LocalExtractionClient.get_results(job_id: str) -> List[Dict[str, Any]]` | **[verified]** `edge-agent/local_extraction_client.py:195`, `LocalExtractionClient.get_results` |
| `LocalExtractionClient.get_all_job_ids() -> List[str]` | **[verified]** `edge-agent/local_extraction_client.py:199`, `LocalExtractionClient.get_all_job_ids` |

##### `edge-agent/workers/capture/base_capture_worker.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `BaseCaptureWorker.__init__(config, job_id_getter: Callable[[], Optional[str]], parent=None, ) -> None` | **[verified]** `edge-agent/workers/capture/base_capture_worker.py:22`, `BaseCaptureWorker.__init__` |
| `BaseCaptureWorker.run() -> None` | **[verified]** `edge-agent/workers/capture/base_capture_worker.py:41`, `BaseCaptureWorker.run` |
| `BaseCaptureWorker.start_capture()` | **[verified]** `edge-agent/workers/capture/base_capture_worker.py:69`, `BaseCaptureWorker.start_capture` |
| `BaseCaptureWorker.stop()` | **[verified]** `edge-agent/workers/capture/base_capture_worker.py:73`, `BaseCaptureWorker.stop` |
| `BaseCaptureWorker.on_error(exc: Exception) -> None` | **[verified]** `edge-agent/workers/capture/base_capture_worker.py:94`, `BaseCaptureWorker.on_error` |

##### `edge-agent/workers/capture/bper_capture_worker.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `BPERCaptureWorker.__init__(config, job_id_getter, api_client: Optional[Any] = None, parent: Optional[QtCore.QObject] = None, ) -> None` | **[verified]** `edge-agent/workers/capture/bper_capture_worker.py:44`, `BPERCaptureWorker.__init__` |
| `BPERCaptureWorker.run() -> None` | **[verified]** `edge-agent/workers/capture/bper_capture_worker.py:201`, `BPERCaptureWorker.run` |
| `BPERCaptureWorker.stop() -> None` | **[verified]** `edge-agent/workers/capture/bper_capture_worker.py:210`, `BPERCaptureWorker.stop` |
| `BPERCaptureWorker.force_capture(page_name: str) -> None` | **[verified]** `edge-agent/workers/capture/bper_capture_worker.py:643`, `BPERCaptureWorker.force_capture` |

##### `edge-agent/workers/capture/default_capture_worker.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `DefaultCaptureWorker.__init__(config, job_id_getter, parent: Optional[QtCore.QObject] = None)` | **[verified]** `edge-agent/workers/capture/default_capture_worker.py:29`, `DefaultCaptureWorker.__init__` |

#### Desktop: dati, workbook e UI

##### `edge-agent/practice_consolidation.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `normalize_ndg(value: Any) -> Optional[str]` | **[verified]** `edge-agent/practice_consolidation.py:46`, `normalize_ndg` |
| `consolidate(results: Sequence[Dict[str, Any]]) -> List[PracticeRecord]` | **[verified]** `edge-agent/practice_consolidation.py:105`, `consolidate` |

##### `edge-agent/excel_export.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `build_columns(labels: Optional[Mapping[str, str]] = None) -> List[ColumnSpec]` | **[verified]** `edge-agent/excel_export.py:92`, `build_columns` |
| `write_workbook( records: Sequence[PracticeRecord], columns: Sequence[ColumnSpec], path: str, ) -> None` | **[verified]** `edge-agent/excel_export.py:177`, `write_workbook` |
| `export_results( results: Sequence[Dict[str, Any]], path: str, labels: Optional[Mapping[str, str]] = None, ) -> int` | **[verified]** `edge-agent/excel_export.py:217`, `export_results` |

##### `edge-agent/ui/main_window.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `MainWindow.__init__(config: AgentConfig, show_debug: bool = False, parent: Optional[QtWidgets.QWidget] = None)` | **[verified]** `edge-agent/ui/main_window.py:31`, `MainWindow.__init__` |
| `MainWindow.closeEvent(event) -> None` | **[verified]** `edge-agent/ui/main_window.py:85`, `MainWindow.closeEvent` |

##### `edge-agent/ui/capture_tab.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `CaptureTab.__init__(config: AgentConfig, api_client: Any, parent: Optional[QtWidgets.QWidget] = None, debug_tab: Optional[QtWidgets.QWidget] = None, ) -> None` | **[verified]** `edge-agent/ui/capture_tab.py:47`, `CaptureTab.__init__` |
| `CaptureTab.get_current_job_id() -> Optional[str]` | **[verified]** `edge-agent/ui/capture_tab.py:398`, `CaptureTab.get_current_job_id` |
| `CaptureTab.stop_capture() -> None` | **[verified]** `edge-agent/ui/capture_tab.py:401`, `CaptureTab.stop_capture` |

##### `edge-agent/ui/data_table_tab.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `DataTableTab.__init__(extraction_client: Any, parent: Optional[QWidget] = None, ) -> None` | **[verified]** `edge-agent/ui/data_table_tab.py:59`, `DataTableTab.__init__` |
| `DataTableTab.set_job_id(job_id: Optional[str]) -> None` | **[verified]** `edge-agent/ui/data_table_tab.py:285`, `DataTableTab.set_job_id` |

##### `edge-agent/ui/debug_tab.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `DebugTab.__init__(parent: Optional[QtWidgets.QWidget] = None) -> None` | **[verified]** `edge-agent/ui/debug_tab.py:14`, `DebugTab.__init__` |
| `DebugTab.append_json(json_str: str) -> None` | **[verified]** `edge-agent/ui/debug_tab.py:25`, `DebugTab.append_json` |
| `DebugTab.append_log(msg: str) -> None` | **[verified]** `edge-agent/ui/debug_tab.py:35`, `DebugTab.append_log` |

##### `edge-agent/ui/overlay.py`

| Firma dichiarata | Evidenza / stato |
|---|---|
| `CaptureBorderOverlay.__init__(geometry: QtCore.QRect, parent: QtWidgets.QWidget \| None = None) -> None` | **[verified]** `edge-agent/ui/overlay.py:12`, `CaptureBorderOverlay.__init__` |
| `CaptureBorderOverlay.set_screen_geometry(geometry: QtCore.QRect) -> None` | **[verified]** `edge-agent/ui/overlay.py:25`, `CaptureBorderOverlay.set_screen_geometry` |
| `CaptureBorderOverlay.paintEvent(event: QtGui.QPaintEvent) -> None` | **[verified]** `edge-agent/ui/overlay.py:30`, `CaptureBorderOverlay.paintEvent` |

#### Strumenti offline e superficie dei test

| Modulo / ingresso | Parametri e output significativi, con stato |
|---|---|
| `tools/extract_frames.py:69`, `extract`; `tools/extract_frames.py:108`, `main` | **[verified]** `extract(video: Path, out: Path, mode: str, seconds: int, fps: float, scene: float, tag: str) -> List[Path]`. CLI: `--video` ripetibile e `--out` obbligatori, `--mode` fixed/scene, durata, fps/soglia e manifest opzionale. Invoca ffmpeg e produce PNG; la deduplicazione riduce la lista selezionata senza eliminare i file (`tools/extract_frames.py:86`). |
| `tools/label_frames.py:61`, `build_prompt`; `tools/label_frames.py:121`, `localize`; `tools/label_frames.py:156`, `main` | **[verified]** Prompt costruito dal processo e localizzazione score/rettangolo; CLI frames/out obbligatori, processo/template/worker/batch/restart/limit opzionali. Scrive crop, checkpoint JSON e `prompt.txt`, invoca direttamente il provider e termina con codice 10 se rimane lavoro (`tools/label_frames.py:178`; `tools/label_frames.py:227`; `tools/label_frames.py:281`). |
| `tools/build_frame_registry.py:74`, `main` | **[verified]** Labels ripetibile obbligatorio, review/curated/output: unisce proposte, revisione e manifest in record con frame, video, cluster, processo, step, rettangolo e score (`tools/build_frame_registry.py:113`). I conteggi iniziali precedono l'estensione curated (`tools/build_frame_registry.py:129`; `tools/build_frame_registry.py:148`). |
| `tools/build_prototypes.py:85`, `main` | **[verified]** Out/per-class/seed/dry-run e pages opt-in; seleziona frame dal registro e dalle rettifiche, ricrea le directory delle classi pianificate e scrive PNG (`tools/build_prototypes.py:148`). Il default costruisce rifiuti; le classi pagina richiedono l'opzione (`tools/build_prototypes.py:115`). |
| `tools/make_contact_sheets.py:32`, `main` | **[verified]** Labels/crops/out obbligatori, raggruppamento per label/origine e dimensioni/titolo; produce tavole immagine e indice (`tools/make_contact_sheets.py:93`; `tools/make_contact_sheets.py:97`). |
| `tools/make_framing_corpus.py:91`, `compose`; `tools/make_framing_corpus.py:121`, `main` | **[verified]** Compone una pagina in uno schermo con scala/sfondo/nesting; CLI pages/out/per-page/seed. Manifest con file, label, rect, screen, scale, background e nesting (`tools/make_framing_corpus.py:149`). |
| `tools/relocalize.py:31`, `load_localizer`; `tools/relocalize.py:38`, `main` | **[verified]** Carica dinamicamente il localizzatore di `label_frames`, salta risultati esistenti e salva ogni 25 frame (`tools/relocalize.py:55`; `tools/relocalize.py:87`). |
| `tools/measure_classifier.py:60`, `main` | **[verified]** Registry/frames-dir/holdout: confronta embedding con separazione per registrazione e stampa metriche (`tools/measure_classifier.py:77`). La validità statistica della separazione rimane **[unverified]**. |
| `tools/benchmark_backbones.py:53`, `HFBackbone`; `tools/benchmark_backbones.py:139`, `main` | **[verified]** Corpus richiesto; pages/backbones/limit/report opzionali. Supporta torch hub e `hf:` via transformers e riporta IoU/tempi (`tools/benchmark_backbones.py:70`, `load_backbone`; `tools/benchmark_backbones.py:182`). |
| `tools/measure_reject_prototypes.py:29`; `tools/measure_tooltip_prototypes.py:82` | **[verified]** Esperimenti con lavoro nel corpo di modulo, senza guardia main: possono caricare modelli, copiare immagini e lasciare directory temporanee (`tools/measure_tooltip_prototypes.py:144`). |
| `tests/conftest.py:19`, `install_fake_vlm`; `tests/test_prompt_store.py:33`; `tests/test_page_classifier.py:50` | **[verified]** Test e fixture sono superficie di verifica, non API produttive. Il worker ha letto tutti i 15 file di test senza eseguirli; le asserzioni dimostrano copertura intenzionale, non esito. L'esecuzione della suite è gestita dal coordinatore. |

## Cross-Partition Exports

| Exporting Partition | Symbol | Consumers (list of partitions) |
|---|---|---|

Nessuna: root comprende l'intera repository e non ha partizioni sorelle. I consumer sono sottosistemi interni: `gui_app.py:238` → `extraction.cli.run_extraction_batch`, `edge-agent/local_extraction_client.py:159` → `ExtractionPipeline.extract_from_image`, `edge-agent/excel_export.py:227` → `practice_consolidation.consolidate`. Tali collegamenti sono **[verified]** e non richiedono riconciliazione cross-partition.

Gli outgoing reference di struttura e la [mappa di interconnessione](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260911-154206/08-interconnect-map.md) concordano: nessuna esportazione fra partizioni.

## Contracts (by partition)

### Partition: root

#### Campi, righe e output di estrazione

| Oggetto | Forma, invarianti e limiti |
|---|---|
| Vocabolario | **[verified]** `FIELD_KEYS` contiene 45 chiavi italiane: identificatori, metadati pratica, credito, note/tooltip, quattro triplette soggetto e dati privati. `CSV_TO_SCHEMA` risolve gli alias della ground truth; i metadati collegano schema key, nome visualizzato e pagina (`extraction/fields.py:12`, `FIELD_KEYS`; `extraction/fields.py:56`, `CSV_TO_SCHEMA`; `extraction/fields.py:112`, `get_canonical_field_metadata`). |
| Pagine canoniche | **[verified]** `PAGE_SHEET_ORDER` ordina quattro gruppi di output, distinti dalle nove classi del router (`extraction/page_definitions.py:23`, `PAGE_SHEET_ORDER`; `edge-agent/assets/templates/bper/prompts.json:2`, `pages`). Alias normalizzati per spazi/case risolvono chiave/nome o `None` (`extraction/page_definitions.py:31`; `extraction/field_definitions.py:243`, `resolve_schema_key`). |
| `FieldResult` | **[verified]** `value: Optional[str]`, `confidence: float = 0.0`, `evidence_text: Optional[str]`, `section: Optional[str]`. Il validatore confidence opera dopo la conversione Pydantic del float e tratta numeri non finiti/fuori intervallo; non garantisce accettazione di ogni input testuale invalido (`extraction/schemas.py:21`, `_ConfidenceModel._clamp_confidence`; `extraction/schemas.py:31`, `FieldResult`). |
| `FieldsModel`, `ExtractionResponse` | **[verified]** Modello generato con 45 proprietà opzionali FieldResult; risposta con fields e liste soggetti/fidi/garanzie di default vuote. AnchorResponse limita fields a NDG/denominazione; gli alias legacy puntano alle classi (`extraction/schemas.py:68`, `FieldsModel`; `extraction/schemas.py:76`, `ExtractionResponse`; `extraction/schemas.py:82`, `AnchorFields`; `extraction/schemas.py:86`, `AnchorResponse`; `extraction/schemas.py:92`, `RESPONSE_SCHEMA`). |
| Righe tabellari | **[verified]** `Soggetto`: ndg, denominazione, ruolo, confidence, evidence_text. `Fido`: n_fido, rapporto, descrizione, scadenza, importo_euro, tipo_op e confidence/evidence. `Garanzia`: n_gar, descrizione, fido, ndg, denominazione, importo_percentuale, tipo_op e confidence/evidence (`extraction/schemas.py:37`, `Soggetto`; `extraction/schemas.py:44`, `Fido`; `extraction/schemas.py:54`, `Garanzia`). Le quantità sono stringhe opzionali, non Decimal validati. |
| Dizionario pipeline | **[verified]** La risposta completa aggiunge screen_id, attempt, `_meta`, `_attempts`, `_meta_agg`, `_field_sources`, `_status`, `_content_crop` e canonical_fields. `_content_crop` vale calibrated/full-frame. L'uscita anticipata per anchor nulle restituisce fields/liste vuote, `_status`, `_content_crop`, `_attempts`, `_meta_agg` e `_field_sources`, ma non `_meta`, attempt o canonical_fields; i consumer devono tollerare tale forma ridotta (`extraction/pipeline.py:152`, `ExtractionPipeline.extract_from_image`; `extraction/pipeline.py:209`; `extraction/pipeline.py:216`; `extraction/vlm_client.py:215`, `call_vlm`). |
| Voci canoniche | **[verified]** Lista con chiave schema, nome visualizzato, pagina e dati del campo, ordinata per pagina/nome (`extraction/canonical_mapping.py:20`, `build_canonical_field_entries`; `extraction/canonical_mapping.py:8`, `_canonical_entry_sort_key`). |
| Stato | **[verified]** Il percorso completo restituisce OK se NDG e denominazione finali hanno valore, altrimenti ANCHOR_UNCERTAIN: non misura l'accuratezza di tutti i campi (`extraction/pipeline.py:216`, `ExtractionPipeline.extract_from_image`). Il client converte eccezioni in ERROR con fields vuoti e `_error` string (`edge-agent/local_extraction_client.py:160`, `LocalExtractionClient._process_frame`). |

**[verified] Selezione e post-processing.** Le anchor sotto ANCHOR_CONF_MIN perdono il valore prima del merge; quelle rimanenti sovrascrivono gli omologhi del main (`extraction/pipeline.py:111`, `ExtractionPipeline.extract_anchors`; `extraction/pipeline.py:244`, `ExtractionPipeline._merge_anchors`). Seguono normalizzazione tipo, retry, coerenza, flatten dei primi quattro soggetti, canonicalizzazione e stato (`extraction/pipeline.py:188`, `ExtractionPipeline.extract_from_image`; `extraction/pipeline.py:202`). `pick_best` preferisce il non nullo, poi confidence maggiore, conserva il primo a parità e restituisce l'oggetto originale (`extraction/normalization.py:104`, `pick_best`), senza copia immutabile.

**[verified] Provenienza parziale.** Il merge scalare aggiorna `_field_sources` tramite identità dell'oggetto scelto (`extraction/normalization.py:115`, `merge_field_sources`). La coerenza può sintetizzare B/BMB e il flatten può sovrascrivere triplette senza aggiornare la provenienza (`extraction/pipeline.py:365`, `ExtractionPipeline._coherence_check`; `extraction/pipeline.py:202`). La mappa non dimostra quindi ogni origine del valore finale.

#### Geometria, retry e chiamate LLM

| Contratto | Comportamento e limite |
|---|---|
| Immagini/file | **[verified]** Il file viene aperto RGB e normalizzato con downscale iniziale 1800 e filtri contrasto/sharpen. Il core applica anche MAX_IMAGE_LONG_SIDE, default 2000; un valore non positivo disabilita quel clamp (`extraction/pipeline.py:223`, `ExtractionPipeline.extract_from_screen`; `extraction/imaging.py:19`, `normalize_image`; `extraction/config.py:65`; `extraction/imaging.py:38`, `clamp_long_side`). |
| Crop | **[verified]** CONTENT_CROP=(.18,.12,.98,.98) vale solo con lato lungo 800–900 e rapporto entro 5% di 848/679, con opt-in del percorso file/immagine. Senza calibrazione l'anchor legge l'immagine intera; crop_relative converte frazioni in interi senza propria validazione geometrica (`extraction/config.py:76`; `extraction/imaging.py:52`, `select_content_crop`; `extraction/imaging.py:78`, `crop_relative`; `extraction/pipeline.py:139`, `ExtractionPipeline.extract_from_image`; `extraction/pipeline.py:91`, `ExtractionPipeline.extract_anchors`). |
| Aree retry | **[verified]** HEADER/BODY/FOOTER usano bande 0–.35, .25–.75, .65–1 e soglia RETRY_CONF_MIN=.60. Un campo assente/debole rende candidata l'area; il budget riserva due passaggi e seleziona le aree in ordine prima di eseguirle in parallelo (`extraction/config.py:59`; `extraction/config.py:92`, `RETRY_AREAS`; `extraction/config.py:101`, `AREA_TO_FIELDS`; `extraction/pipeline.py:295`, `ExtractionPipeline._retry_areas`; `extraction/pipeline.py:305`; `extraction/pipeline.py:337`). Creazione e i cinque tooltip non appartengono ad aree retry (confronto `extraction/fields.py:12` / `extraction/config.py:101`). |
| Merge retry | **[verified]** Ogni retry aggiorna solo i suoi scalari; BODY considera le tre tabelle. Fuori calibrazione le tabelle riempiono solo liste vuote; in calibrazione prevale il numero di righe, poi confidence media a parità. Errori di un'area sono stampati e saltati (`extraction/pipeline.py:258`, `ExtractionPipeline._merge_tables`; `extraction/pipeline.py:354`, `ExtractionPipeline._retry_areas`; `extraction/pipeline.py:342`). |
| Factory core | **[verified]** Chiave esplicita → LLM_API_KEY → variabile legacy provider; assenza chiave/provider/modello incongruo solleva ValueError. I wrapper LangChain sono importati lazy (`extraction/llm_factory.py:18`, `create_chat_model`; `extraction/llm_factory.py:32`; `extraction/llm_factory.py:44`). Il core Gemini non include GOOGLE_API_KEY come il router (`extraction/llm_factory.py:34`; `edge-agent/config.py:303`, `AgentConfig.resolve_llm_settings`). |
| Provider | **[verified]** OpenAI e Gemini 1.5 usano structured output; i Gemini successivi usano JSON libero e validazione Pydantic (`extraction/vlm_client.py:135`, `call_vlm`; `extraction/vlm_client.py:148`; `extraction/vlm_client.py:194`; `extraction/vlm_client.py:94`). Conformità e precisione reali rimangono **[unverified]** senza risposte effettive. |
| Retry di chiamata | **[disputed]** Il wrapper è descritto come retry transitorio, ma esenta solo ValueError, KeyError, IndexError e ritenta le altre Exception con attesa esponenziale. max_retries=3 significa tre tentativi totali (`extraction/vlm_client.py:230`, `call_vlm_with_retry`; `extraction/vlm_client.py:242`; `extraction/vlm_client.py:253`). |
| Costi/latenza | **[verified]** `_meta` contiene modello, screen/attempt, latency_ms, token prompt/completion/total e costo stimato. Usage assente e modello fuori listino producono zeri; `_meta_agg.latency_ms` somma latenze riuscite anche se parallele. Non è tempo di parete né fatturazione (`extraction/vlm_client.py:26`, `estimate_cost_usd`; `extraction/vlm_client.py:215`, `call_vlm`; `extraction/pipeline.py:383`, `ExtractionPipeline._aggregate_meta`). Il budget schermata conta passaggi logici, non tutti i tentativi interni/falliti (`extraction/pipeline.py:305`; `extraction/vlm_client.py:242`). |

#### Batch, ground truth e CSV

**[verified]** BatchRunner costruisce una volta i modelli e li condivide; le callback sono invocate nel ciclo chiamante dopo il completamento dei future. `run` salta file mancanti e usa lo stem come chiave: omonimi in directory diverse collidono. In seriale senza on_error l'errore si propaga; in parallelo viene stampato e l'output fallito omesso. La deduplicazione pagina è definita ma la chiamata è commentata (`extraction/cli.py:164`, `BatchRunner.__init__`; `extraction/cli.py:210`, `BatchRunner.run`; `extraction/cli.py:245`; `extraction/cli.py:254`; `extraction/cli.py:269`; `extraction/cli.py:271`; `extraction/imaging.py:29`, `screen_id_from_path`). La sicurezza concorrente effettiva delle librerie provider rimane **[unverified]** pur essendo assunta dal codice (`extraction/llm_factory.py:27`).

**[verified]** La ground truth è letta provando UTF-8 BOM/cp1252/latin1, con colonne alternative per schermata/campo/valore; l'ultimo duplicato sovrascrive il precedente. La CLI richiede dati.csv, Tkinter valuta facoltativamente (`extraction/evaluation.py:32`, `_read_gt_csv`; `extraction/evaluation.py:47`, `load_ground_truth`; `extraction/evaluation.py:82`; `extraction/cli.py:318`, `main`; `gui_app.py:263`, `App.run_process`).

**[verified]** `classify_field` restituisce stato/motivo con OK, WRONG, MISSING, HALLUCINATED, OK_NULL; usa normalizzazione delle quantità e similarità per testi lunghi. `dataset_mismatch_guard` considera NDG/denominazione, con fallback soggetti e normalizzazione numerica anche per NDG. False significa nessuna differenza rilevata, non identità provata (`extraction/normalization.py:134`, `classify_field`; `extraction/normalization.py:183`, `_resolve_anchor_value`; `extraction/normalization.py:195`, `dataset_mismatch_guard`).

**[verified]** `eval_outputs` itera la ground truth e ignora schermate senza output e campi non mappati; restituisce acc_raw, acc_filt, per_field_filt. Un output del tutto assente non viene contato come insieme di campi mancanti (`extraction/evaluation.py:88`, `eval_outputs`; `extraction/evaluation.py:95`; `extraction/evaluation.py:103`; `extraction/evaluation.py:130`). Debug e CSV includono mismatch/campi/tabelle e centralizzano escaping formule e scrittura (`extraction/evaluation.py:139`, `build_debug_report`; `extraction/evaluation.py:191`, `export_to_csv`; `extraction/evaluation.py:15`, `_write_csv`; `extraction/normalization.py:62`, `escape_csv_formula`).

#### Prompt, configurazione e cataloghi pagina

| Contratto | Forma e conseguenze |
|---|---|
| Prompt JSON | **[verified]** Il file deve avere id coerente col nome, testo stringa/lista di righe e parts oggetto. CATALOG dichiara dieci ID, parti richieste e placeholder ammessi; si verificano parti e placeholder sconosciuti, senza imporre l'uso di ogni placeholder ammesso. Prompt aggiuntivi non catalogati sono accettati se strutturalmente validi (`prompt_store.py:62`, `CATALOG`; `prompt_store.py:139`, `_validate_against_spec`; `prompt_store.py:176`, `_load_file`; `prompt_store.py:239`, `load_prompts`). |
| Registro | **[verified]** Prompt/PromptSpec sono dataclass frozen e le parti caricate sono rese non modificabili. get_text fallisce per prompt di sole parti, get_part per parte inesistente (`prompt_store.py:47`, `PromptSpec`; `prompt_store.py:92`, `Prompt`; `prompt_store.py:209`, `_load_file`; `prompt_store.py:302`, `get_text`; `prompt_store.py:310`, `get_part`). |
| Ricerca/lifecycle | **[verified]** PROMPTS_DIR esplicito è esclusivo, senza fallback. Frozen prova la directory accanto all'exe e il bundle; source usa il catalogo root. Vince la prima directory caricabile; il registro globale viene creato una volta. load_prompts separato non sostituisce il registro (`prompt_store.py:220`, `catalog_candidates`; `prompt_store.py:262`, `_load_first_usable`; `prompt_store.py:284`, assegnazione globale). |
| Configurazione | **[verified]** Il core fotografa l'ambiente all'import; AgentConfig legge INI e risolve chiave/base URL/modello secondo provider. Chiave non vuota INI precede l'ambiente; REDACTED* è ignorato. save serializza anche il campo chiave nell'INI (`extraction/config.py:16`; `edge-agent/config.py:58`, `AgentConfig.__init__`; `edge-agent/config.py:241`; `edge-agent/config.py:292`, `AgentConfig.resolve_llm_settings`; `edge-agent/config.py:339`, `AgentConfig.save`). Nessun contenuto di ambiente/credenziale è stato letto nell'analisi. |
| Percorsi/preflight | **[verified]** app_paths distingue source/frozen e centralizza config, template/cache e prompt. run_preflight prepara file, carica config/ambiente e richiede chiave; solo ml/hybrid attivano controllo/warmup ML. Il flag smoke salta le operazioni successive alla configurazione. La presenza locale della chiave non autentica presso il provider (`edge-agent/app_paths.py:14`, `app_dir`; `edge-agent/app_paths.py:26`, `project_root`; `edge-agent/bootstrap.py:489`, `run_preflight`; `edge-agent/bootstrap.py:503`; `edge-agent/bootstrap.py:99`, `_has_api_key`). |
| Pagine | **[verified]** PageRegistry.load consuma pages con name, ordine positivo, template opzionale, slug derivato e catchall; controlla unicità e scarta catchall. Il registro vuoto è permissivo e sintetizza una pagina per label sconosciuta; in ml sono acquisibili solo pagine con template (`edge-agent/page_registry.py:18`, `PageDef`; `edge-agent/page_registry.py:40`, `PageRegistry.load`; `edge-agent/page_registry.py:63`, `PageRegistry.empty`; `edge-agent/page_registry.py:69`, `PageRegistry.resolve`; `edge-agent/page_registry.py:83`, `PageRegistry.acquirable`). |
| Errori dei cataloghi | **[verified]** Il catalogo prompt fallisce con PromptStoreError; il caricamento delle specifiche pagina nel router degrada a spec vuota. Un registro permissivo non è un rifiuto di ogni frame (`prompt_store.py:87`, `PromptStoreError`; `edge-agent/llm_router.py:102`, `LLMPageRouter.__init__`). |
| Processo e runtime | **[disputed]** Il processo descrive navigazione libera/rivisite ed è letto dal tool di etichettatura; il runtime usa un catalogo separato e l'insieme già acquisito (`processes/bper-p1.json:282`, `navigation`; `processes/bper-p1.json:368`, `capture_policy`; `tools/label_frames.py:174`, `main`; `edge-agent/workers/capture/bper_capture_worker.py:308`, `BPERCaptureWorker._capture_once`). Pagina 9 esclude checklist nel processo ma le ammette ancora nel catalogo runtime (`processes/bper-p1.json:259`; `edge-agent/assets/templates/bper/prompts.json:104`). |

#### Router, classificatore e stabilità

**[verified]** RouterResult contiene page_type opzionale, confidence, fields e reason/expected opzionali. PageRouter.route solleva NotImplementedError, senza il vincolo di istanziazione di una abstract base class. MLPageRouter converte la coppia del classificatore; LLMPageRouter invia due immagini (frame ridotto e header), richiede JSON via SDK OpenAI compatibile e limita a due tentativi. Valida il nome pagina, ma non limita confidence a [0,1]; fields restituito è vuoto. set_expected_page esiste ma il worker non lo usa per imporre l'ordine (`edge-agent/llm_router.py:29`, `RouterResult`; `edge-agent/llm_router.py:39`, `PageRouter.route`; `edge-agent/llm_router.py:61`, `MLPageRouter.route`; `edge-agent/llm_router.py:158`, `LLMPageRouter.set_expected_page`; `edge-agent/llm_router.py:194`, `LLMPageRouter.route`; `edge-agent/llm_router.py:219`; `edge-agent/llm_router.py:251`; `edge-agent/llm_router.py:273`).

**[verified]** Classification contiene label, score, margin, runner_up, rejected_by. BPERPagePrototypeClassifier usa DINOv2 ViT-S/14 con riferimento hub fissato, trasformazione 224×224 e confronto con prototipi centrati. Un vincitore SCARTO* è rifiutato prima della soglia. Score è similarità, non probabilità, e può essere negativo: il range [0,1] descritto dal metodo legacy è **[disputed]** (`edge-agent/page_classifier.py:33`, costanti hub; `edge-agent/page_classifier.py:73`, `Classification`; `edge-agent/page_classifier.py:379`, trasformazione; `edge-agent/page_classifier.py:673`, `BPERPagePrototypeClassifier.classify_detailed`; `edge-agent/page_classifier.py:688`; `edge-agent/page_classifier.py:703`, docstring di `BPERPagePrototypeClassifier.classify`). La precisione reale è **[unverified]**.

**[verified]** Il costruttore pubblico ha default threshold .75 e crop None, mentre i caller runtime passano soglia/ROI configurati (.35 e `(0,.20,1,.98)` nelle costanti condivise). Il cache contiene hash dei file e geometria e viene ricostruito quando cambiano. embedding_geometry rappresenta crop None come ROI predefinita, mentre l'elaborazione con None usa l'immagine intera: tali casi possono condividere la chiave geometrica (`edge-agent/page_classifier.py:44`, `DEFAULT_CROP_ROI`; `edge-agent/page_classifier.py:51`, `DEFAULT_SIMILARITY_THRESHOLD`; `edge-agent/page_classifier.py:140`, `embedding_geometry`; `edge-agent/page_classifier.py:234`, `BPERPagePrototypeClassifier.__init__`; `edge-agent/page_classifier.py:435`; `edge-agent/page_classifier.py:607`, `BPERPagePrototypeClassifier._apply_roi`). Gli errori di salvataggio cache vengono assorbiti (`edge-agent/page_classifier.py:571`).

**[verified]** StabilityConfig imposta min_matches=2, min_seconds=2, max_misses=1. Il tracker riceve timestamp dal chiamante; observe stabilizza una candidata, confirm può avanzare su un frame identico, miss oltre tolleranza resettano/adottano la candidata pendente. Cambiare candidata non significa acquisirla nello stesso ramo (`edge-agent/stability.py:10`, `StabilityConfig`; `edge-agent/stability.py:46`, `StabilityTracker.observe`; `edge-agent/stability.py:76`, `StabilityTracker.confirm`; `edge-agent/stability.py:105`, `StabilityTracker._register_miss`).

#### Cattura, concorrenza e segnali Qt

| Confine | Contratto effettivo |
|---|---|
| Normalizzazione monitor | **[verified]** Rect=(left,top,right,bottom) in pixel. MSS usa coordinate virtuali anche negative; crop_to_rect converte/limita con minimo 16 px. normalize_frame prova rettangolo finestra, euristica contenuto e infine immagine invariata, restituendo strategia. Titolo/area/spigoli sono euristiche, non prova d'identità applicativa (`edge-agent/frame_normalize.py:27`, `Rect`; `edge-agent/frame_normalize.py:49`, `crop_to_rect`; `edge-agent/frame_normalize.py:209`, `normalize_frame`; `edge-agent/frame_normalize.py:72`, `detect_app_rect`; `edge-agent/frame_normalize.py:113`, `select_window_rect`). |
| Worker base | **[verified]** QThread con tick(str), error(Exception), llm_debug(str); loop a cadenza configurata, latch stop e gestione errori per iterazione. La sottoclasse implementa _capture_once; start/stop controllano flag (`edge-agent/workers/capture/base_capture_worker.py:9`, `BaseCaptureWorker`; `edge-agent/workers/capture/base_capture_worker.py:41`, `BaseCaptureWorker.run`; `edge-agent/workers/capture/base_capture_worker.py:69`, `BaseCaptureWorker.start_capture`; `edge-agent/workers/capture/base_capture_worker.py:81`, `BaseCaptureWorker._capture_once`). |
| BPER | **[verified]** Il router viene inizializzato in run. Cattura MSS, normalizzazione, pHash/throttle, preprocessing/routing, registro/stabilità e consegna client formano il ciclo. La pagina entra in captured_page_types dopo _upload_page senza conferma del successo dell'estrazione. force_capture bypassa stabilità e precedente acquisizione (`edge-agent/workers/capture/bper_capture_worker.py:201`, `BPERCaptureWorker.run`; `edge-agent/workers/capture/bper_capture_worker.py:255`, `BPERCaptureWorker._capture_once`; `edge-agent/workers/capture/bper_capture_worker.py:339`; `edge-agent/workers/capture/bper_capture_worker.py:392`, `BPERCaptureWorker._grab_raw`; `edge-agent/workers/capture/bper_capture_worker.py:643`, `BPERCaptureWorker.force_capture`). |
| Modalità | **[verified]** llm crea LLM; hybrid crea LLM più classificatore fallback; gli altri valori creano ML. Il gate local-first può usare score/margine locale ma il fallback inizializzato resta ML; il preflight scalda solo ml/hybrid (`edge-agent/workers/capture/bper_capture_worker.py:108`, `BPERCaptureWorker._init_router`; `edge-agent/workers/capture/bper_capture_worker.py:491`, `BPERCaptureWorker._try_local_first`; `edge-agent/bootstrap.py:511`, `run_preflight`). Il nome local-first non prova un fallback LLM. |
| Pool | **[verified]** DaemonThreadPool ha coda senza limite, worker daemon, submit booleano e pending pari alla sola coda. stop scarta task non iniziati e invia sentinelle senza join, senza cancellare chiamate attive. Check stop/inserimento non sono un'unica sezione critica (`edge-agent/extraction_pool.py:23`, `DaemonThreadPool.__init__`; `edge-agent/extraction_pool.py:33`, `DaemonThreadPool.submit`; `edge-agent/extraction_pool.py:40`, `DaemonThreadPool.pending`; `edge-agent/extraction_pool.py:44`, `DaemonThreadPool.stop`). L'uscita immediata dell'interprete con executor interni dei retry resta **[unverified]** (`extraction/pipeline.py:337`). |
| Client locale | **[verified]** start_job restituisce UUID. ingest_frame emette frame_queued(job_id,page_type) prima dell'inserimento, ignora il booleano submit e non usa fields_json nell'estrazione. Al completamento aggiunge `_page_type`, `_page_no`, `_page_confidence`, conserva il risultato ed emette result_ready(job_id,dict) (`edge-agent/local_extraction_client.py:87`, segnali; `edge-agent/local_extraction_client.py:121`, `LocalExtractionClient.start_job`; `edge-agent/local_extraction_client.py:125`, `LocalExtractionClient.ingest_frame`; `edge-agent/local_extraction_client.py:168`, `LocalExtractionClient._process_frame`). |
| Risultati/shutdown | **[verified]** get_results copia superficialmente la lista: i dict rimangono condivisi. requeue_job è uno stub True; pending_extractions non conta task attivi; shutdown chiude il pool senza attendere (`edge-agent/local_extraction_client.py:180`, `LocalExtractionClient.requeue_job`; `edge-agent/local_extraction_client.py:184`, `LocalExtractionClient.pending_extractions`; `edge-agent/local_extraction_client.py:188`, `LocalExtractionClient.shutdown`; `edge-agent/local_extraction_client.py:195`, `LocalExtractionClient.get_results`). |
| UI | **[verified]** MainWindow possiede client/tab e ferma cattura/client su close. CaptureTab aspetta il worker fino a 5 s, senza dimostrare il termine di una chiamata più lunga; l'acquisizione manuale chiama direttamente il worker dalla UI. DataTableTab consolida prima del rendering (`edge-agent/ui/main_window.py:85`, `MainWindow.closeEvent`; `edge-agent/ui/capture_tab.py:299`, `CaptureTab._on_stop_capture`; `edge-agent/ui/capture_tab.py:417`, `CaptureTab._on_force_capture`; `edge-agent/ui/data_table_tab.py:194`, `DataTableTab._load_table`). |

#### Pratica consolidata e workbook

**[verified]** PracticeRecord è frozen ma contiene fields mutabile, ndg, denominazione, source_pages e frame_count. normalize_ndg conserva alfanumerici maiuscoli senza punteggiatura e rimuove zeri iniziali solo se interamente numerico. consolidate mantiene l'ordine del primo incontro, mette in attesa frame senza NDG prima del primo identificatore e associa quelli successivi all'ultimo NDG incontrato. I campi passano per pick_best senza soglia globale (`edge-agent/practice_consolidation.py:30`, `PracticeRecord`; `edge-agent/practice_consolidation.py:46`, `normalize_ndg`; `edge-agent/practice_consolidation.py:85`, `_Group.absorb`; `edge-agent/practice_consolidation.py:105`, `consolidate`). Il client conserva in ordine di completamento, quindi l'ordine visuale di cattura non è garantito (`edge-agent/local_extraction_client.py:175`, `LocalExtractionClient._process_frame`); la correttezza dell'associazione di frame senza NDG in sequenze mescolate è **[unverified]**.

**[verified]** ColumnSpec contiene schema_key, label, page_key, page_name. Le 45 colonne fissano NDG/denominazione davanti e ordinano il resto per pagina/nome; rinomine cambiano solo etichette. write_workbook produce Dati Estratti, due righe di intestazione, dati dalla terza, filtro e freeze C3. I valori estratti sono celle esplicitamente testuali, preservando formule apparenti e importi negativi; le etichette personalizzate hanno un percorso distinto senza la stessa forzatura del tipo. export_results restituisce il numero di pratiche scritte (`edge-agent/excel_export.py:74`, `ColumnSpec`; `edge-agent/excel_export.py:92`, `build_columns`; `edge-agent/excel_export.py:124`, `_set_text`; `edge-agent/excel_export.py:160`, `_write_labels`; `edge-agent/excel_export.py:177`, `write_workbook`; `edge-agent/excel_export.py:212`; `edge-agent/excel_export.py:217`, `export_results`).

**[verified]** La tabella mostra campi scalari consolidati e conserva rinomine nella sessione. Il suo export passa le etichette, quello Capture non passa override; le liste complete fidi/garanzie non diventano righe aggiuntive del workbook, poiché il consolidamento considera i campi scalari (`edge-agent/ui/data_table_tab.py:161`, `DataTableTab._on_rename_column`; `edge-agent/ui/data_table_tab.py:210`; `edge-agent/ui/data_table_tab.py:270`, `DataTableTab._on_export_excel`; `edge-agent/ui/capture_tab.py:361`, `CaptureTab._on_export_excel`; `edge-agent/practice_consolidation.py:85`, `_Group.absorb`).

## External Dependencies

Le righe sono **[verified]** per import/uso/dichiarazioni osservati. Versioni effettivamente installate, compatibilità futura e comportamento dei servizi sono **[unverified]** in questa analisi statica. Le librerie standard sono esterne alla partizione ma non pacchetti di terze parti.

| Dipendenza / confine | Utilizzo ed evidenza |
|---|---|
| LangChain core + OpenAI/Google | Factory, messaggi e structured output del core (`extraction/llm_factory.py:49`, `create_chat_model`; `extraction/llm_factory.py:59`; `extraction/vlm_client.py:123`, `call_vlm`; `requirements.txt:1`). |
| Pydantic | Schema dinamico e validazione risposte (`extraction/schemas.py:1`; `extraction/schemas.py:68`, `FieldsModel`). Non ha una riga propria nel manifesto, quindi la disponibilità dipende dalla catena transitiva (`requirements.txt:1`). |
| OpenAI SDK | Router con endpoint configurabile ed etichettatore; secondo confine provider rispetto al core LangChain (`edge-agent/llm_router.py:98`, `LLMPageRouter.__init__`; `edge-agent/llm_router.py:228`, `LLMPageRouter.route`; `tools/label_frames.py:196`, `main`; `requirements.txt:15`). |
| Pillow / imagehash | Resize, crop, codifica e pHash (`extraction/imaging.py:19`, `normalize_image`; `edge-agent/image_ops.py:21`, `preprocess_for_ocr`; `edge-agent/workers/capture/bper_capture_worker.py:464`, `BPERCaptureWorker._is_duplicate_frame`; `requirements.txt:10`; `requirements.txt:11`). |
| pandas / openpyxl | CSV/valutazione e workbook diretto openpyxl (`extraction/evaluation.py:32`, `_read_gt_csv`; `edge-agent/excel_export.py:177`, `write_workbook`; `requirements.txt:4`; `requirements.txt:16`). |
| PyQt6 / qt-material / Tkinter | UI, QThread, segnali, tema e GUI batch separata; Tkinter è stdlib ed esclusa dal bundle edge (`edge-agent/edge_agent.py:48`, `main`; `edge-agent/edge_agent.py:53`; `gui_app.py:16`, `App`; `requirements.txt:6`; `requirements.txt:7`; `edge_agent.spec:37`). |
| mss / pyscreenshot | Cattura monitor/fallback; pyscreenshot ha marker Linux (`edge-agent/workers/capture/bper_capture_worker.py:369`, `BPERCaptureWorker._grab_raw`; `edge-agent/workers/capture/default_capture_worker.py:75`, `DefaultCaptureWorker._capture_screenshot`; `requirements.txt:8`; `requirements.txt:9`). L'ambiente grafico effettivo è **[unverified]**. |
| torch / torchvision / torch hub | DINOv2, trasformazioni e prototipi; bootstrap può scaricare pesi con hash atteso e sostituzione atomica (`edge-agent/page_classifier.py:313`, `BPERPagePrototypeClassifier._lazy_init_torch`; `edge-agent/page_classifier.py:363`; `edge-agent/page_classifier.py:379`; `edge-agent/bootstrap.py:304`, `_WeightsDownloadWorker.run`; `edge-agent/bootstrap.py:320`; `requirements.txt:13`; `requirements.txt:14`). |
| transformers / ffmpeg | Benchmark Hugging Face opzionale e binario per estrazione video (`tools/benchmark_backbones.py:56`, `HFBackbone.__init__`; `tools/extract_frames.py:77`, `extract`). Non sono righe del manifesto (`requirements.txt:1`); presenza effettiva **[unverified]**. |
| requests | POST della sola modalità generica; il contratto remoto è costruito dal worker, senza server negli ingressi inventariati (`edge-agent/workers/capture/default_capture_worker.py:34`, `DefaultCaptureWorker._capture_once`; `requirements.txt:12`). |
| python-dotenv | Caricamento ambiente dove previsto dall'ingresso (`main.py:4`; `edge-agent/edge_agent.py:31`; `edge-agent/local_extraction_client.py:24`; `requirements.txt:5`). Nessun file di ambiente è stato letto qui. |
| PyInstaller / pytest | Build e suite sviluppo (`edge_agent.spec:27`, `Analysis`; `build_exe.bat:75`; `requirements.txt:17`; `requirements-dev.txt:1`). |
| stdlib / API sistema | threading/queue/futures, JSON/pathlib, ctypes Win32 e subprocess (`edge-agent/extraction_pool.py:23`, `DaemonThreadPool.__init__`; `extraction/pipeline.py:337`; `prompt_store.py:176`, `_load_file`; `edge-agent/frame_normalize.py:161`, `_enumerate_windows`; `tools/extract_frames.py:82`, `extract`). |

## How to Add a New Module (per partition)

### Partition: root

I passi sono proposte **[unverified]** fino all'implementazione; i contratti e i precedenti citati sono **[verified]**.

1. Creare `extraction/<responsabilita>.py` per trasformazioni condivise o `edge-agent/<responsabilita>.py` per integrazione desktop; mantenere i cataloghi indipendenti dal core quando devono precederne l'import eager (`extraction/canonical_mapping.py:20`, `build_canonical_field_entries`; `prompt_store.py:30`, import stdlib; `edge-agent/edge_agent.py:74`, import UI ritardato).
2. Dichiarare input/output/errori. Un campo richiede vocabolario/alias, metadati, schema indiretto, area retry pertinente e prompt; un testo nuovo richiede JSON più CATALOG (`extraction/fields.py:12`, `FIELD_KEYS`; `extraction/fields.py:56`, `CSV_TO_SCHEMA`; `extraction/config.py:101`, `AREA_TO_FIELDS`; `extraction/schemas.py:68`, `FieldsModel`; `prompt_store.py:62`, `CATALOG`).
3. Integrare nel punto di composizione esistente: pipeline/batch, CaptureTab per modalità, registro/asset per pagine, __all__ per API pubbliche. Preservare il ritorno rapido di ingest_frame e il merge comune della pratica (`extraction/pipeline.py:122`, `ExtractionPipeline.extract_from_image`; `edge-agent/ui/capture_tab.py:224`, `CaptureTab._on_start_capture`; `edge-agent/page_registry.py:40`, `PageRegistry.load`; `extraction/__init__.py:11`, `__all__`; `edge-agent/practice_consolidation.py:90`, `_Group.absorb`).
4. Aggiungere test del comportamento in `tests/test_<modulo>.py`, usando i confini di rete isolati e fixture geometriche rappresentative. Un router iniettato non verifica il cablaggio produttivo (`tests/conftest.py:19`, `install_fake_vlm`; `tests/test_content_crop.py:79`; `tests/test_page_classifier.py:50`; `tests/test_excel_export.py:14`; `tests/test_bper_capture_framing.py:212`).
