# Phase 2: Interface Analysis

> Stato: `verified`, firme estratte dal codice della revisione `f8f57e6124e008aa47ff6d8320aa508e9ef7976c` e working tree descritto in `01-structure.md`. Il parser del plugin individua simboli e linee; le dichiarazioni vengono riportate integralmente dal sorgente, preservando annotazioni, default e parametri keyword-only. Quando il sorgente non annota un parametro o il ritorno, il rapporto mantiene tale assenza: non è una garanzia di tipo. `self` e `cls` conservano la forma originale. Nessuna importazione applicativa, chiamata provider o esecuzione della suite è stata necessaria.

## Public APIs (by partition)

### Partition: root

Sono inclusi costruttori, metodi pubblici, proprietà e funzioni top-level pubbliche; gli helper privati essenziali al protocollo di cattura sono documentati separatamente. I test sono un’interfaccia pytest, non una API applicativa.

### edge-agent/__init__.py

Nessun callable pubblico definito direttamente; il modulo contiene import, costanti, dichiarazioni di schema o codice al livello modulo.

### edge-agent/app_paths.py

- `edge-agent/app_paths.py:9`: `def is_frozen() -> bool:`
- `edge-agent/app_paths.py:14`: `def app_dir() -> Path:`
- `edge-agent/app_paths.py:26`: `def project_root() -> Path:`
- `edge-agent/app_paths.py:33`: `def config_ini() -> Path:`
- `edge-agent/app_paths.py:38`: `def env_file() -> Path:`
- `edge-agent/app_paths.py:43`: `def templates_dir() -> Path:`
- `edge-agent/app_paths.py:48`: `def torch_cache_dir() -> Path:`
- `edge-agent/app_paths.py:53`: `def bundled_defaults_dir() -> Path:`
- `edge-agent/app_paths.py:60`: `def prompts_dir() -> Path:`
- `edge-agent/app_paths.py:65`: `def bundled_prompts_dir() -> Path:`
- `edge-agent/app_paths.py:72`: `def bundled_assets_dir() -> Path:`

### edge-agent/bootstrap.py

- `edge-agent/bootstrap.py:489`: `def run_preflight(parent: Optional[QtWidgets.QWidget] = None) -> Optional[AgentConfig]:`

Costanti dichiarate: `ENV_TEMPLATE`, `_KEY_ENV_VARS`.

### edge-agent/config.py

- Classe `AgentConfig`; basi: nessuna; dichiarata in `edge-agent/config.py:9`.
  - `AgentConfig.__init__`: `def __init__(self, config_path: Optional[Path] = None):` — `edge-agent/config.py:58`.
  - `AgentConfig.resolve_llm_settings`: `def resolve_llm_settings(self) -> Tuple[str, str, str]:` — `edge-agent/config.py:292`.
  - `AgentConfig.update_from_ui`: `def update_from_ui(self, fps: int, window_filter: str) -> None:` — `edge-agent/config.py:323`.
  - `AgentConfig.save`: `def save(self) -> None:` — `edge-agent/config.py:339`.
  - `AgentConfig.__repr__`: `def __repr__(self) -> str:` — `edge-agent/config.py:400`.

### edge-agent/edge_agent.py

- `edge-agent/edge_agent.py:38`: `def main() -> int:`

### edge-agent/excel_export.py

- `edge-agent/excel_export.py:92`: `def build_columns(labels: Optional[Mapping[str, str]] = None) -> List[ColumnSpec]:`
- `edge-agent/excel_export.py:177`: `def write_workbook( records: Sequence[PracticeRecord], columns: Sequence[ColumnSpec], path: str, ) -> None:`
- `edge-agent/excel_export.py:217`: `def export_results( results: Sequence[Dict[str, Any]], path: str, labels: Optional[Mapping[str, str]] = None, ) -> int:`
- Classe `ColumnSpec`; basi: nessuna; dichiarata in `edge-agent/excel_export.py:74`.

Costanti dichiarate: `_PROJECT_ROOT`, `SHEET_TITLE`, `PINNED_KEYS`, `PAGE_BAND_COLORS`, `LABEL_FILL`, `ZEBRA_FILL`, `WRAP_KEYS`, `MIN_WIDTH`, `MAX_WIDTH`, `HEADER_ROWS`, `_THIN`, `_BORDER`.

### edge-agent/extraction_pool.py

- Classe `DaemonThreadPool`; basi: nessuna; dichiarata in `edge-agent/extraction_pool.py:13`.
  - `DaemonThreadPool.__init__`: `def __init__(self, max_workers: int, name_prefix: str = "extract") -> None:` — `edge-agent/extraction_pool.py:23`.
  - `DaemonThreadPool.submit`: `def submit(self, fn: Callable[..., Any], *args: Any) -> bool:` — `edge-agent/extraction_pool.py:33`.
  - `DaemonThreadPool.pending`: `def pending(self) -> int:` — `edge-agent/extraction_pool.py:40`.
  - `DaemonThreadPool.stop`: `def stop(self) -> None:` — `edge-agent/extraction_pool.py:44`.

Costanti dichiarate: `_SENTINEL`.

### edge-agent/frame_normalize.py

- `edge-agent/frame_normalize.py:49`: `def crop_to_rect(img: Image.Image, monitor: Dict[str, int], window_rect: Optional[Rect]) -> Image.Image:`
- `edge-agent/frame_normalize.py:72`: `def detect_app_rect(img: Image.Image, *, tolerance: int = _COLOR_TOLERANCE) -> Optional[Rect]:`
- `edge-agent/frame_normalize.py:113`: `def select_window_rect( title_substring: str, windows: Iterable[Dict[str, Any]], own_pid: int, ) -> Optional[Rect]:`
- `edge-agent/frame_normalize.py:194`: `def find_window_rect(title_substring: str) -> Optional[Rect]:`
- `edge-agent/frame_normalize.py:209`: `def normalize_frame( img: Image.Image, monitor: Dict[str, int], window_rect_provider: Callable[[], Optional[Rect]], ) -> Tuple[Image.Image, str]:`

Costanti dichiarate: `WINDOW_RECT`, `CONTENT_RECT`, `UNCHANGED`, `_COLOR_TOLERANCE`, `_MIN_CROP_SIDE`, `_MIN_DESKTOP_MARGIN`.

### edge-agent/image_ops.py

- `edge-agent/image_ops.py:21`: `def preprocess_for_ocr( img: Image.Image, *, scale: Optional[float] = None, unsharp_amount: float = 0.8, unsharp_radius: float = 1.2, unsharp_threshold: int = 2, contrast_stretch: bool = True, ) -> Image.Image:`
- `edge-agent/image_ops.py:58`: `def to_png8(img: Image.Image) -> bytes:`
- `edge-agent/image_ops.py:67`: `def to_webp_lossless(img: Image.Image) -> bytes:`

### edge-agent/llm_router.py

- Classe `RouterResult`; basi: nessuna; dichiarata in `edge-agent/llm_router.py:29`.
- Classe `PageRouter`; basi: nessuna; dichiarata in `edge-agent/llm_router.py:38`.
  - `PageRouter.route`: `def route(self, image: Image.Image) -> RouterResult:` — `edge-agent/llm_router.py:39`.
- Classe `MLPageRouter`; basi: `PageRouter`; dichiarata in `edge-agent/llm_router.py:43`.
  - `MLPageRouter.__init__`: `def __init__(self, templates_dir: Path, classifier: Optional[Any] = None) -> None:` — `edge-agent/llm_router.py:46`.
  - `MLPageRouter.route`: `def route(self, image: Image.Image) -> RouterResult:` — `edge-agent/llm_router.py:61`.
- Classe `LLMPageRouter`; basi: `PageRouter`; dichiarata in `edge-agent/llm_router.py:66`.
  - `LLMPageRouter.__init__`: `def __init__( self, prompts_path: Path, *, provider: str = "openai", base_url: str = "https://api.openai.com/v1", model: str = "gpt-4o-mini", api_key: str = "", timeout: int = 60, ) -> None:` — `edge-agent/llm_router.py:73`.
  - `LLMPageRouter.set_expected_page`: `def set_expected_page(self, name: Optional[str]) -> None:` — `edge-agent/llm_router.py:158`.
  - `LLMPageRouter.get_page_hints`: `def get_page_hints(self, name: str) -> Optional[str]:` — `edge-agent/llm_router.py:162`.
  - `LLMPageRouter.route`: `def route(self, image: Image.Image) -> RouterResult:` — `edge-agent/llm_router.py:172`.
  - `LLMPageRouter.get_last_debug`: `def get_last_debug(self) -> Dict[str, Any]:` — `edge-agent/llm_router.py:288`.

### edge-agent/local_extraction_client.py

- Classe `LocalExtractionClient`; basi: `QtCore.QObject`; dichiarata in `edge-agent/local_extraction_client.py:76`.
  - `LocalExtractionClient.__init__`: `def __init__( self, parent: Optional[QtCore.QObject] = None, pipeline: Optional[ExtractionPipeline] = None, ) -> None:` — `edge-agent/local_extraction_client.py:90`.
  - `LocalExtractionClient.start_job`: `def start_job(self) -> str:` — `edge-agent/local_extraction_client.py:123`.
  - `LocalExtractionClient.ingest_frame`: `def ingest_frame( self, job_id: str, img: Image.Image, page_no: int = 0, page_type: str = "", confidence: float = 0.0, fields_json: str = "{}", ) -> int:` — `edge-agent/local_extraction_client.py:127`.
  - `LocalExtractionClient.requeue_job`: `def requeue_job(self, job_id: str) -> bool:` — `edge-agent/local_extraction_client.py:206`.
  - `LocalExtractionClient.pending_extractions`: `def pending_extractions(self) -> int:` — `edge-agent/local_extraction_client.py:210`.
  - `LocalExtractionClient.shutdown`: `def shutdown(self) -> None:` — `edge-agent/local_extraction_client.py:214`.
  - `LocalExtractionClient.get_results`: `def get_results(self, job_id: str) -> List[Dict[str, Any]]:` — `edge-agent/local_extraction_client.py:222`.
  - `LocalExtractionClient.get_all_job_ids`: `def get_all_job_ids(self) -> List[str]:` — `edge-agent/local_extraction_client.py:227`.

Costanti dichiarate: `_PROJECT_ROOT`.

### edge-agent/page_classifier.py

- `edge-agent/page_classifier.py:140`: `def embedding_geometry(crop_roi: Optional[Tuple[float, float, float, float]] = None, reject_classes: int = 0) -> str:`
- `edge-agent/page_classifier.py:166`: `def cache_is_valid(templates_dir: Path, cache_path: Optional[Path] = None) -> bool:`
- Classe `Classification`; basi: nessuna; dichiarata in `edge-agent/page_classifier.py:73`.
- Classe `Prototype`; basi: nessuna; dichiarata in `edge-agent/page_classifier.py:188`.
- Classe `BPERPagePrototypeClassifier`; basi: nessuna; dichiarata in `edge-agent/page_classifier.py:202`.
  - `BPERPagePrototypeClassifier.__init__`: `def __init__( self, templates_dir: Path, *, cache_path: Optional[Path] = None, crop_roi: Optional[Tuple[float, float, float, float]] = None, similarity_threshold: float = 0.75, device: str = "cpu", ) -> None:` — `edge-agent/page_classifier.py:234`.
  - `BPERPagePrototypeClassifier.classify_detailed`: `def classify_detailed(self, image) -> "Classification":` — `edge-agent/page_classifier.py:660`.
  - `BPERPagePrototypeClassifier.classify`: `def classify(self, image) -> Tuple[Optional[str], float]:` — `edge-agent/page_classifier.py:696`.
  - `BPERPagePrototypeClassifier.info`: `def info(self) -> Dict:` — `edge-agent/page_classifier.py:711`.

Costanti dichiarate: `DINOV2_HUB_REPO`, `DINOV2_MODEL_NAME`, `DINOV2_WEIGHTS_URL`, `DINOV2_WEIGHTS_FILENAME`, `DINOV2_WEIGHTS_SHA256`, `DEFAULT_CROP_ROI`, `DEFAULT_SIMILARITY_THRESHOLD`, `EMBED_SIDE`, `_EXCLUDED_SUBDIRS`, `REJECT_PREFIX`.

### edge-agent/page_registry.py

- `edge-agent/page_registry.py:12`: `def slugify(name: str) -> str:`
- Classe `PageDef`; basi: nessuna; dichiarata in `edge-agent/page_registry.py:18`.
- Classe `PageRegistry`; basi: nessuna; dichiarata in `edge-agent/page_registry.py:27`.
  - `PageRegistry.__init__`: `def __init__(self, pages: List[PageDef], catchall_name: Optional[str]) -> None:` — `edge-agent/page_registry.py:30`.
  - `PageRegistry.load` [classmethod]: `def load(cls, prompts_path: Path) -> "PageRegistry":` — `edge-agent/page_registry.py:40`.
  - `PageRegistry.empty` [classmethod]: `def empty(cls) -> "PageRegistry":` — `edge-agent/page_registry.py:63`.
  - `PageRegistry.resolve`: `def resolve(self, label: Optional[str]) -> Optional[PageDef]:` — `edge-agent/page_registry.py:69`.
  - `PageRegistry.acquirable`: `def acquirable(self, router_mode: str) -> List[PageDef]:` — `edge-agent/page_registry.py:83`.
  - `PageRegistry.names`: `def names(self, router_mode: str = "llm") -> List[str]:` — `edge-agent/page_registry.py:89`.

### edge-agent/practice_consolidation.py

- `edge-agent/practice_consolidation.py:46`: `def normalize_ndg(value: Any) -> Optional[str]:`
- `edge-agent/practice_consolidation.py:105`: `def consolidate(results: Sequence[Dict[str, Any]]) -> List[PracticeRecord]:`
- Classe `PracticeRecord`; basi: nessuna; dichiarata in `edge-agent/practice_consolidation.py:31`.

Costanti dichiarate: `_PROJECT_ROOT`.

### edge-agent/stability.py

- Classe `StabilityConfig`; basi: nessuna; dichiarata in `edge-agent/stability.py:10`.
- Classe `StabilityTracker`; basi: nessuna; dichiarata in `edge-agent/stability.py:18`.
  - `StabilityTracker.__init__`: `def __init__(self, config: Optional[StabilityConfig] = None) -> None:` — `edge-agent/stability.py:29`.
  - `StabilityTracker.reset`: `def reset(self) -> None:` — `edge-agent/stability.py:38`.
  - `StabilityTracker.observe`: `def observe(self, page: Optional[str], now: float) -> Optional[str]:` — `edge-agent/stability.py:46`.
  - `StabilityTracker.confirm`: `def confirm(self, now: float) -> Optional[str]:` — `edge-agent/stability.py:76`.

### edge-agent/ui/__init__.py

Nessun callable pubblico definito direttamente; il modulo contiene import, costanti, dichiarazioni di schema o codice al livello modulo.

### edge-agent/ui/capture_tab.py

- Classe `CaptureTab`; basi: `QWidget`; dichiarata in `edge-agent/ui/capture_tab.py:35`.
  - `CaptureTab.__init__`: `def __init__( self, config: AgentConfig, api_client: Any, parent: Optional[QtWidgets.QWidget] = None, debug_tab: Optional[QtWidgets.QWidget] = None, ) -> None:` — `edge-agent/ui/capture_tab.py:47`.
  - `CaptureTab.get_current_job_id`: `def get_current_job_id(self) -> Optional[str]:` — `edge-agent/ui/capture_tab.py:398`.
  - `CaptureTab.stop_capture`: `def stop_capture(self) -> None:` — `edge-agent/ui/capture_tab.py:401`.

### edge-agent/ui/data_table_tab.py

- Classe `DataTableTab`; basi: `QWidget`; dichiarata in `edge-agent/ui/data_table_tab.py:50`.
  - `DataTableTab.__init__`: `def __init__( self, extraction_client: Any, parent: Optional[QWidget] = None, ) -> None:` — `edge-agent/ui/data_table_tab.py:59`.
  - `DataTableTab.set_job_id`: `def set_job_id(self, job_id: Optional[str]) -> None:` — `edge-agent/ui/data_table_tab.py:285`.

Costanti dichiarate: `_EXTRACTION_ROOT`, `_BAND_ROW`, `_FIRST_DATA_ROW`.

### edge-agent/ui/debug_tab.py

- Classe `DebugTab`; basi: `QtWidgets.QWidget`; dichiarata in `edge-agent/ui/debug_tab.py:13`.
  - `DebugTab.__init__`: `def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:` — `edge-agent/ui/debug_tab.py:14`.
  - `DebugTab.append_json`: `def append_json(self, json_str: str) -> None:` — `edge-agent/ui/debug_tab.py:25`.
  - `DebugTab.append_log`: `def append_log(self, msg: str) -> None:` — `edge-agent/ui/debug_tab.py:35`.

### edge-agent/ui/main_window.py

- Classe `MainWindow`; basi: `QtWidgets.QMainWindow`; dichiarata in `edge-agent/ui/main_window.py:16`.
  - `MainWindow.__init__`: `def __init__(self, config: AgentConfig, show_debug: bool = False, parent: Optional[QtWidgets.QWidget] = None):` — `edge-agent/ui/main_window.py:31`.
  - `MainWindow.closeEvent`: `def closeEvent(self, event) -> None:  # type: ignore[override] try:` — `edge-agent/ui/main_window.py:85`.

### edge-agent/ui/overlay.py

- Classe `CaptureBorderOverlay`; basi: `QtWidgets.QWidget`; dichiarata in `edge-agent/ui/overlay.py:6`.
  - `CaptureBorderOverlay.__init__`: `def __init__(self, geometry: QtCore.QRect, parent: QtWidgets.QWidget | None = None) -> None:` — `edge-agent/ui/overlay.py:12`.
  - `CaptureBorderOverlay.set_screen_geometry`: `def set_screen_geometry(self, geometry: QtCore.QRect) -> None:` — `edge-agent/ui/overlay.py:25`.
  - `CaptureBorderOverlay.paintEvent`: `def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802 painter = QtGui.QPainter(self) painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True) pen = QtGui.QPen(QtGui.QColor(255, 0, 0)) pen.setWidth(6) painter.setPen(pen) # Rettangolo leggermente inset per non essere tagliato dai bordi schermo rect = self.rect().adjusted(3, 3, -3, -3) painter.drawRect(rect) painter.end()` — `edge-agent/ui/overlay.py:30`.

### edge-agent/workers/__init__.py

Nessun callable pubblico definito direttamente; il modulo contiene import, costanti, dichiarazioni di schema o codice al livello modulo.

### edge-agent/workers/capture/__init__.py

Nessun callable pubblico definito direttamente; il modulo contiene import, costanti, dichiarazioni di schema o codice al livello modulo.

### edge-agent/workers/capture/base_capture_worker.py

- Classe `BaseCaptureWorker`; basi: `QtCore.QThread`; dichiarata in `edge-agent/workers/capture/base_capture_worker.py:9`.
  - `BaseCaptureWorker.__init__`: `def __init__( self, config, job_id_getter: Callable[[], Optional[str]], parent=None, ) -> None:` — `edge-agent/workers/capture/base_capture_worker.py:22`.
  - `BaseCaptureWorker.run`: `def run(self) -> None:` — `edge-agent/workers/capture/base_capture_worker.py:41`.
  - `BaseCaptureWorker.start_capture`: `def start_capture(self):` — `edge-agent/workers/capture/base_capture_worker.py:69`.
  - `BaseCaptureWorker.stop`: `def stop(self):` — `edge-agent/workers/capture/base_capture_worker.py:73`.
  - `BaseCaptureWorker.on_error`: `def on_error(self, exc: Exception) -> None:` — `edge-agent/workers/capture/base_capture_worker.py:94`.

### edge-agent/workers/capture/bper_capture_worker.py

- Classe `BPERCaptureWorker`; basi: `BaseCaptureWorker`; dichiarata in `edge-agent/workers/capture/bper_capture_worker.py:30`.
  - `BPERCaptureWorker.__init__`: `def __init__( self, config: Any, job_id_getter: Callable[[], Optional[str]], api_client: Optional[Any] = None, parent: Optional[QtCore.QObject] = None, ) -> None:` — `edge-agent/workers/capture/bper_capture_worker.py:46`.
  - `BPERCaptureWorker.run`: `def run(self) -> None:` — `edge-agent/workers/capture/bper_capture_worker.py:216`.
  - `BPERCaptureWorker.force_capture`: `def force_capture(self, page_name: str) -> None:` — `edge-agent/workers/capture/bper_capture_worker.py:722`.

### edge-agent/workers/capture/default_capture_worker.py

- Classe `DefaultCaptureWorker`; basi: `BaseCaptureWorker`; dichiarata in `edge-agent/workers/capture/default_capture_worker.py:16`.
  - `DefaultCaptureWorker.__init__`: `def __init__(self, config, job_id_getter, parent: Optional[QtCore.QObject] = None):` — `edge-agent/workers/capture/default_capture_worker.py:29`.

### extraction/__init__.py

Nessun callable pubblico definito direttamente; il modulo contiene import, costanti, dichiarazioni di schema o codice al livello modulo.

### extraction/canonical_mapping.py

- `extraction/canonical_mapping.py:20`: `def build_canonical_field_entries(fields: Dict[str, Any]) -> List[Dict[str, Any]]:`

### extraction/cli.py

- `extraction/cli.py:285`: `def run_extraction_batch( paths: List[str], *, api_key: Optional[str] = None, provider_name: Optional[str] = None, model_main: Optional[str] = None, model_anchor: Optional[str] = None, parallel: bool = True, max_workers: int = 4, on_complete: Optional[Callable[[str, Dict[str, Any]], None]] = None, on_error: Optional[Callable[[str, Exception], None]] = None, ) -> Dict[str, Dict[str, Any]]:`
- `extraction/cli.py:318`: `def main() -> None:`
- Classe `BatchRunner`; basi: nessuna; dichiarata in `extraction/cli.py:157`.
  - `BatchRunner.__init__`: `def __init__( self, *, api_key: Optional[str] = None, provider_name: Optional[str] = None, model_main: Optional[str] = None, model_anchor: Optional[str] = None, parallel: bool = True, max_workers: int = 4, ) -> None:` — `extraction/cli.py:164`.
  - `BatchRunner.run`: `def run( self, paths: List[str], on_complete: Optional[Callable[[str, Dict[str, Any]], None]] = None, on_error: Optional[Callable[[str, Exception], None]] = None, ) -> Dict[str, Dict[str, Any]]:` — `extraction/cli.py:210`.

### extraction/config.py

Nessun callable pubblico definito direttamente; il modulo contiene import, costanti, dichiarazioni di schema o codice al livello modulo.

Costanti dichiarate: `INPUT_DIR`, `GROUND_TRUTH_CSV`, `PARALLEL_WORKERS`, `PARALLEL_ENABLED`, `LLM_PROVIDER`, `LLM_MODEL`, `LLM_MODEL_ANCHOR`, `LLM_THINKING_LEVEL`, `PROVIDER_MODELS`, `PRICING_PER_1M`, `STOP_ON_ANCHOR_UNCERTAIN`, `ANCHOR_CONF_MIN`, `RETRY_CONF_MIN`, `MAX_IMAGE_LONG_SIDE`, `CONTENT_CROP`, `CONTENT_CROP_CALIBRATED_ASPECT`, `CONTENT_CROP_ASPECT_TOLERANCE`, `CONTENT_CROP_LONG_SIDE_RANGE`, `HEADER_IN_CONTENT`, `RETRY_AREAS`, `AREA_TO_FIELDS`, `MAX_CALLS_PER_SCREEN`, `DEBUG_MODE`, `DEBUG_SAVE_CROPS`, `DEBUG_CROP_DIR`.

### extraction/evaluation.py

- `extraction/evaluation.py:47`: `def load_ground_truth(csv_path: str) -> Dict[str, Dict[str, Any]]:`
- `extraction/evaluation.py:88`: `def eval_outputs(outputs: Dict[str, Dict[str, Any]], gt: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:`
- `extraction/evaluation.py:139`: `def build_debug_report( outputs: Dict[str, Dict[str, Any]], gt: Dict[str, Dict[str, Any]], out_csv_path: str, ) -> None:`
- `extraction/evaluation.py:191`: `def export_to_csv(outputs: Dict[str, Dict[str, Any]], out_csv_path: str) -> None:`
- `extraction/evaluation.py:248`: `def print_cost_summary(outputs: Dict[str, Dict[str, Any]]) -> None:`
- Classe `Evaluator`; basi: nessuna; dichiarata in `extraction/evaluation.py:269`.
  - `Evaluator.__init__`: `def __init__(self, gt: Dict[str, Dict[str, Any]]) -> None:` — `extraction/evaluation.py:272`.
  - `Evaluator.eval`: `def eval(self, outputs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:` — `extraction/evaluation.py:275`.
  - `Evaluator.build_debug_report`: `def build_debug_report(self, outputs: Dict[str, Dict[str, Any]], out_csv_path: str) -> None:` — `extraction/evaluation.py:279`.
  - `Evaluator.print_cost_summary` [staticmethod]: `def print_cost_summary(outputs: Dict[str, Dict[str, Any]]) -> None:` — `extraction/evaluation.py:284`.

### extraction/field_definitions.py

- `extraction/field_definitions.py:238`: `def normalize_field_label(label: str) -> str:`
- `extraction/field_definitions.py:243`: `def resolve_schema_key(label: str) -> Optional[str]:`
- `extraction/field_definitions.py:249`: `def resolve_display_name(schema_key: str) -> Optional[str]:`
- `extraction/field_definitions.py:257`: `def resolve_field_page_key(schema_key: str) -> Optional[str]:`

Costanti dichiarate: `CANONICAL_FIELD_DEFINITIONS`, `FIELD_LABEL_ALIASES`.

### extraction/fields.py

- `extraction/fields.py:102`: `def get_canonical_field_display_name(schema_key: str) -> str:`
- `extraction/fields.py:108`: `def get_canonical_field_page_key(schema_key: str) -> Optional[str]:`
- `extraction/fields.py:112`: `def get_canonical_field_metadata(schema_key: str) -> Dict[str, Optional[str]]:`

Costanti dichiarate: `FIELD_KEYS`, `CSV_TO_SCHEMA`.

### extraction/imaging.py

- `extraction/imaging.py:19`: `def normalize_image(img: Image.Image, long_side: int = 1800) -> Image.Image:`
- `extraction/imaging.py:29`: `def screen_id_from_path(path: str) -> str:`
- `extraction/imaging.py:38`: `def clamp_long_side(img: Image.Image, max_side: int) -> Image.Image:`
- `extraction/imaging.py:52`: `def select_content_crop(size: Tuple[int, int]) -> Optional[Tuple[float, float, float, float]]:`
- `extraction/imaging.py:78`: `def crop_relative(img: Image.Image, box: Tuple[float, float, float, float]) -> Image.Image:`
- `extraction/imaging.py:87`: `def img_to_png_bytes(img: Image.Image) -> bytes:`
- `extraction/imaging.py:93`: `def save_debug_crop(img: Image.Image, screen_id: str, name: str) -> None:`

### extraction/llm_factory.py

- `extraction/llm_factory.py:18`: `def create_chat_model( provider_name: str, *, model: str, api_key: Optional[str] = None, ) -> BaseChatModel:`

Costanti dichiarate: `_LEGACY_KEY_VARS`.

### extraction/normalization.py

- `extraction/normalization.py:16`: `def normalize_tipo(val: Any) -> Any:`
- `extraction/normalization.py:28`: `def is_nullish(v: Any) -> bool:`
- `extraction/normalization.py:34`: `def norm_text(x: Any) -> str:`
- `extraction/normalization.py:40`: `def norm_number_str(x: Any) -> str:`
- `extraction/normalization.py:62`: `def escape_csv_formula(value: Any) -> Any:`
- `extraction/normalization.py:77`: `def safe_field(fields: Dict[str, Any], key: str) -> Dict[str, Any]:`
- `extraction/normalization.py:88`: `def safe_set_field(fields: Dict[str, Any], key: str, *, value=None, confidence=None, evidence_text=None, section=None) -> None:`
- `extraction/normalization.py:104`: `def pick_best(f1: Dict[str, Any], f2: Dict[str, Any]) -> Dict[str, Any]:`
- `extraction/normalization.py:115`: `def merge_field_sources( field_sources: Dict[str, str], field_key: str, current: Dict[str, Any], candidate: Dict[str, Any], candidate_source: str, ) -> Dict[str, Any]:`
- `extraction/normalization.py:134`: `def classify_field(gt_val: Any, pred_val: Any, field_key: Optional[str] = None) -> Tuple[str, str]:`
- `extraction/normalization.py:171`: `def get_pred_value_for_gt_key(pred: Dict[str, Any], gt_key: str) -> Tuple[Optional[str], Any, float, Optional[str], Optional[str]]:`
- `extraction/normalization.py:195`: `def dataset_mismatch_guard(gt_kv: Dict[str, Any], pred: Dict[str, Any]) -> bool:`

Costanti dichiarate: `TIPO_MAPPING`.

### extraction/page_definitions.py

- `extraction/page_definitions.py:31`: `def normalize_page_label(label: str) -> str:`
- `extraction/page_definitions.py:36`: `def resolve_page_key(label: str) -> Optional[str]:`
- `extraction/page_definitions.py:42`: `def resolve_page_name(label: str) -> Optional[str]:`
- `extraction/page_definitions.py:49`: `def get_canonical_page_name(page_key: str) -> Optional[str]:`

Costanti dichiarate: `CANONICAL_PAGE_NAMES`, `PAGE_NAME_ALIASES`, `PAGE_SHEET_ORDER`.

### extraction/pipeline.py

- `extraction/pipeline.py:400`: `def extract_anchors( anchor_model: BaseChatModel, anchor_model_name: str, content_img: Image.Image, screen_id: str, ) -> Dict[str, Any]:`
- `extraction/pipeline.py:410`: `def extract_from_screen( main_model: BaseChatModel, anchor_model: BaseChatModel, main_model_name: str, anchor_model_name: str, path: str, ) -> Dict[str, Any]:`
- Classe `ExtractionPipeline`; basi: nessuna; dichiarata in `extraction/pipeline.py:55`.
  - `ExtractionPipeline.__init__`: `def __init__( self, main_model: BaseChatModel, anchor_model: BaseChatModel, main_model_name: str, anchor_model_name: str, ) -> None:` — `extraction/pipeline.py:62`.
  - `ExtractionPipeline.extract_anchors`: `def extract_anchors( self, content_img: Image.Image, screen_id: str, *, calibrated: bool = True ) -> Dict[str, Any]:` — `extraction/pipeline.py:78`.
  - `ExtractionPipeline.extract_from_image`: `def extract_from_image( self, img: Image.Image, screen_id: str, *, allow_content_crop: bool = False ) -> Dict[str, Any]:` — `extraction/pipeline.py:122`.
  - `ExtractionPipeline.extract_from_screen`: `def extract_from_screen(self, path: str) -> Dict[str, Any]:` — `extraction/pipeline.py:223`.

Costanti dichiarate: `ANCHOR_HINT_NDG`, `ANCHOR_HINT_DENOMINAZIONE`.

### extraction/prompts.py

Nessun callable pubblico definito direttamente; il modulo contiene import, costanti, dichiarazioni di schema o codice al livello modulo.

Costanti dichiarate: `PROMPT`, `ANCHOR_PROMPT`, `RETRY_PROMPT_HEADER`, `RETRY_PROMPT_BODY`, `RETRY_PROMPT_FOOTER`, `FIELD_RETRY_PROMPTS`.

### extraction/schemas.py

- Classe `FieldResult`; basi: `_ConfidenceModel`; dichiarata in `extraction/schemas.py:31`.
- Classe `Soggetto`; basi: `_ConfidenceModel`; dichiarata in `extraction/schemas.py:37`.
- Classe `Fido`; basi: `_ConfidenceModel`; dichiarata in `extraction/schemas.py:44`.
- Classe `Garanzia`; basi: `_ConfidenceModel`; dichiarata in `extraction/schemas.py:54`.
- Classe `ExtractionResponse`; basi: `BaseModel`; dichiarata in `extraction/schemas.py:76`.
- Classe `AnchorFields`; basi: `BaseModel`; dichiarata in `extraction/schemas.py:82`.
- Classe `AnchorResponse`; basi: `BaseModel`; dichiarata in `extraction/schemas.py:86`.

Costanti dichiarate: `RESPONSE_SCHEMA`, `ANCHOR_SCHEMA`.

### extraction/vlm_client.py

- `extraction/vlm_client.py:26`: `def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:`
- `extraction/vlm_client.py:123`: `def call_vlm( chat_model: BaseChatModel, image_bytes: bytes, prompt: str, screen_id: str, attempt: str, model: str, schema: Type[BaseModel], ) -> Dict[str, Any]:`
- `extraction/vlm_client.py:230`: `def call_vlm_with_retry( chat_model: BaseChatModel, image_bytes: bytes, prompt: str, screen_id: str, attempt: str, model: str, schema: Type[BaseModel], max_retries: int = 3, ) -> Dict[str, Any]:`

Costanti dichiarate: `_GEMINI_JSON_SCHEMA_MODELS`, `_USER_INSTRUCTION`, `_JSON_SCHEMA_INSTRUCTION`.

### gui_app.py

- Classe `App`; basi: `tk.Tk`; dichiarata in `gui_app.py:16`.
  - `App.__init__`: `def __init__(self):` — `gui_app.py:17`.
  - `App.create_widgets`: `def create_widgets(self):` — `gui_app.py:32`.
  - `App.update_models`: `def update_models(self, provider):` — `gui_app.py:140`.
  - `App.setup_results_tab`: `def setup_results_tab(self):` — `gui_app.py:148`.
  - `App.select_images`: `def select_images(self):` — `gui_app.py:183`.
  - `App.select_csv`: `def select_csv(self):` — `gui_app.py:193`.
  - `App.log`: `def log(self, message):` — `gui_app.py:199`.
  - `App.show_log_guide`: `def show_log_guide(self):` — `gui_app.py:203`.
  - `App.start_extraction`: `def start_extraction(self):` — `gui_app.py:213`.
  - `App.run_process`: `def run_process(self):` — `gui_app.py:228`.
  - `App.display_results`: `def display_results(self, outputs, metrics=None):` — `gui_app.py:287`.

### main.py

Nessun callable pubblico definito direttamente; il modulo contiene import, costanti, dichiarazioni di schema o codice al livello modulo.

### prompt_store.py

- `prompt_store.py:220`: `def catalog_candidates() -> List[Path]:`
- `prompt_store.py:239`: `def load_prompts(directory: Path) -> Dict[str, Prompt]:`
- `prompt_store.py:287`: `def catalog_source() -> Path:`
- `prompt_store.py:292`: `def get_prompt(prompt_id: str) -> Prompt:`
- `prompt_store.py:302`: `def get_text(prompt_id: str) -> str:`
- `prompt_store.py:310`: `def get_part(prompt_id: str, part: str) -> str:`
- Classe `PromptSpec`; basi: nessuna; dichiarata in `prompt_store.py:47`.
- Classe `PromptStoreError`; basi: `RuntimeError`; dichiarata in `prompt_store.py:87`.
- Classe `Prompt`; basi: nessuna; dichiarata in `prompt_store.py:92`.

Costanti dichiarate: `CATALOG`.

### tools/benchmark_backbones.py

- `tools/benchmark_backbones.py:70`: `def load_backbone(name: str) -> Tuple[object, int]:`
- `tools/benchmark_backbones.py:88`: `def patch_grid(model: torch.nn.Module, patch: int, img: Image.Image, w: int, h: int) -> torch.Tensor:`
- `tools/benchmark_backbones.py:96`: `def localize( model: torch.nn.Module, patch: int, detector: torch.Tensor, frame: Image.Image, aspect_wh: float, sweep_w: int = 1120, ) -> Rect:`
- `tools/benchmark_backbones.py:131`: `def iou(a: Rect, b: Rect) -> float:`
- `tools/benchmark_backbones.py:139`: `def main() -> None:`
- Classe `HFBackbone`; basi: nessuna; dichiarata in `tools/benchmark_backbones.py:53`.
  - `HFBackbone.__init__`: `def __init__(self, path: str) -> None:` — `tools/benchmark_backbones.py:56`.
  - `HFBackbone.forward_features`: `def forward_features(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:` — `tools/benchmark_backbones.py:65`.

Costanti dichiarate: `NORM`, `BACKBONES`.

### tools/build_frame_registry.py

- `tools/build_frame_registry.py:74`: `def main() -> None:`

Costanti dichiarate: `FRAMES`, `VIDEO_DIRS`, `NAME_TO_CLUSTER`, `PAGE_NAMES`.

### tools/build_prototypes.py

- `tools/build_prototypes.py:67`: `def widen_for_roi(rect: Optional[Tuple[int, int, int, int]], size: Tuple[int, int]) -> Optional[Tuple[int, int, int, int]]:`
- `tools/build_prototypes.py:85`: `def main() -> None:`

Costanti dichiarate: `FRAMES`, `REFERENCES`, `REJECT_PREFIX`, `ROI_TOP_DROP`, `REJECT_GROUPS`, `PAGE_SLUGS`.

### tools/extract_frames.py

- `tools/extract_frames.py:69`: `def extract(video: Path, out: Path, mode: str, seconds: int, fps: float, scene: float, tag: str) -> List[Path]:`
- `tools/extract_frames.py:86`: `def deduplicate(frames: List[Path], threshold: int = DEDUP_HAMMING) -> List[Path]:`
- `tools/extract_frames.py:108`: `def main() -> None:`

Costanti dichiarate: `DEDUP_HAMMING`.

### tools/label_frames.py

- `tools/label_frames.py:61`: `def build_prompt(process: Dict[str, Any]) -> str:`
- `tools/label_frames.py:93`: `def save_atomic(path: Path, payload: Any) -> None:`
- `tools/label_frames.py:106`: `def load_model() -> Any:`
- `tools/label_frames.py:114`: `def patch_grid(model: Any, img: Image.Image, w: int, h: int) -> torch.Tensor:`
- `tools/label_frames.py:121`: `def localize(model: Any, detector: torch.Tensor, frame: Image.Image, aspect: float) -> Tuple[float, Tuple[int, int, int, int]]:`
- `tools/label_frames.py:156`: `def main() -> None:`

Costanti dichiarate: `NORM`, `MARGIN`, `MIN_AREA_FRACTION`.

### tools/make_contact_sheets.py

- `tools/make_contact_sheets.py:32`: `def main() -> None:`

Costanti dichiarate: `TILE_W`, `COLS`, `MAX_TILES`.

### tools/make_framing_corpus.py

- `tools/make_framing_corpus.py:91`: `def compose( page: Image.Image, screen: Tuple[int, int], scale: float, background: str, nesting: str, rng: random.Random, ) -> Tuple[Image.Image, Rect]:`
- `tools/make_framing_corpus.py:121`: `def main() -> None:`

Costanti dichiarate: `SCREENS`, `SCALES`, `BACKGROUNDS`, `NESTINGS`.

### tools/measure_classifier.py

- `tools/measure_classifier.py:43`: `def load_model() -> Any:`
- `tools/measure_classifier.py:51`: `def embed(model: Any, img: Image.Image, spatial: bool) -> torch.Tensor:`
- `tools/measure_classifier.py:60`: `def main() -> None:`

Costanti dichiarate: `NORM`, `SIDE`, `MIN_PROTOTYPE_EXAMPLES`.

### tools/measure_reject_prototypes.py

- `tools/measure_reject_prototypes.py:34`: `def embed(img):`
- `tools/measure_reject_prototypes.py:38`: `def rect_of(e): return new[e['frame']]['rect'] if e['frame'] in new else e.get('app_rect')  HOLD='20250922-parte01' train, test = {}, [] for e in reg['frames']:`
- `tools/measure_reject_prototypes.py:49`: `def emb_of(e):`
- `tools/measure_reject_prototypes.py:67`: `def rejects(mode, n=40):`
- `tools/measure_reject_prototypes.py:93`: `def run(mode):`

Costanti dichiarate: `NORM`, `FD`, `TPL`, `HOLD`.

### tools/measure_tooltip_prototypes.py

Nessun callable pubblico definito direttamente; il modulo contiene import, costanti, dichiarazioni di schema o codice al livello modulo.

Costanti dichiarate: `REPO`, `TPL`, `TOOLTIPS`, `BASE`, `MARGIN_GATE`, `PROTO`, `TEST`, `FUORI_PROCESSO`.

### tools/relocalize.py

- `tools/relocalize.py:31`: `def load_localizer() -> Any:`
- `tools/relocalize.py:38`: `def main() -> None:`

Costanti dichiarate: `FRAMES_DIR`.

## Cross-Partition Exports

| Exporting Partition | Symbol | Consumers (list of partitions) |
|---|---|---|

Nessuna esportazione tra partizioni: tutti i consumatori sono interni a `root`.

## Contracts (by partition)

### Partition: root

Le dichiarazioni seguenti sono quelle del sorgente; dataclass e Pydantic generano i propri costruttori. La sola presenza di un’annotazione non rende un dizionario validato a runtime.

### `ColumnSpec` — `edge-agent/excel_export.py:74`

```python
class ColumnSpec:
    schema_key: str
    label: str
    page_key: str
    page_name: str
```

### `RouterResult` — `edge-agent/llm_router.py:29`

```python
class RouterResult:
    page_type: Optional[str]
    confidence: float
    fields: Dict[str, Any]
    reason: Optional[str] = None
    expected: Optional[str] = None
```

### `Classification` — `edge-agent/page_classifier.py:73`

```python
class Classification:
    label: Optional[str]
    score: float
    margin: float
    runner_up: Optional[str]
    rejected_by: Optional[str]
```

### `Prototype` — `edge-agent/page_classifier.py:188`

```python
class Prototype:
    page_type: str
    embedding: Any
    count: int
```

### `PageDef` — `edge-agent/page_registry.py:18`

```python
class PageDef:
    name: str
    order: int
    template: Optional[str]
    slug: str
```

### `PracticeRecord` — `edge-agent/practice_consolidation.py:31`

```python
class PracticeRecord:
    ndg: Optional[str]
    denominazione: Optional[str]
    fields: Dict[str, Dict[str, Any]]
    source_pages: Tuple[str, ...]
    frame_count: int
```

### `StabilityConfig` — `edge-agent/stability.py:10`

```python
class StabilityConfig:
    min_matches: int = 2
    min_seconds: float = 2.0
    miss_tolerance: int = 1
```

### `FieldResult` — `extraction/schemas.py:31`

```python
class FieldResult(_ConfidenceModel):
    value: Optional[str] = None
    confidence: float = 0.0
    evidence_text: Optional[str] = None
    section: Optional[str] = None
```

### `Soggetto` — `extraction/schemas.py:37`

```python
class Soggetto(_ConfidenceModel):
    ndg: Optional[str] = None
    denominazione: Optional[str] = None
    ruolo: Optional[str] = None
    confidence: float = 0.0
    evidence_text: Optional[str] = None
```

### `Fido` — `extraction/schemas.py:44`

```python
class Fido(_ConfidenceModel):
    n_fido: Optional[str] = None
    rapporto: Optional[str] = None
    descrizione: Optional[str] = None
    scadenza: Optional[str] = None
    importo_euro: Optional[str] = None
    tipo_op: Optional[str] = None
    confidence: float = 0.0
    evidence_text: Optional[str] = None
```

### `Garanzia` — `extraction/schemas.py:54`

```python
class Garanzia(_ConfidenceModel):
    n_gar: Optional[str] = None
    descrizione: Optional[str] = None
    fido: Optional[str] = None
    ndg: Optional[str] = None
    denominazione: Optional[str] = None
    importo_percentuale: Optional[str] = None
    tipo_op: Optional[str] = None
    confidence: float = 0.0
    evidence_text: Optional[str] = None
```

### `ExtractionResponse` — `extraction/schemas.py:76`

```python
class ExtractionResponse(BaseModel):
    fields: FieldsModel = Field(default_factory=FieldsModel)
    soggetti: List[Soggetto] = Field(default_factory=list)
    fidi: List[Fido] = Field(default_factory=list)
    garanzie: List[Garanzia] = Field(default_factory=list)
```

### `AnchorFields` — `extraction/schemas.py:82`

```python
class AnchorFields(BaseModel):
    ndg: Optional[FieldResult] = None
    denominazione: Optional[FieldResult] = None
```

### `AnchorResponse` — `extraction/schemas.py:86`

```python
class AnchorResponse(BaseModel):
    fields: AnchorFields = Field(default_factory=AnchorFields)
```

### `PromptSpec` — `prompt_store.py:47`

```python
class PromptSpec:
    parts: FrozenSet[str] = frozenset()
    placeholders: Optional[FrozenSet[str]] = None
```

### `Prompt` — `prompt_store.py:92`

```python
class Prompt:
    id: str
    text: str
    parts: Mapping[str, str]
    description: str
    source: Path
```

### Modelli dinamici, dizionari e segnali

- `extraction/schemas.py:67`: `FieldsModel = create_model("FieldsModel", **{k: (Optional[FieldResult], None) for k in FIELD_KEYS})`; i 45 campi canonici condividono il formato `FieldResult`. `RESPONSE_SCHEMA` e `ANCHOR_SCHEMA` sono alias delle classi pubbliche.
- `extraction/schemas.py:21`: il parsing Pydantic del campo float respinge input non numerici e `None` prima del validatore; i valori non finiti, incluso NaN, diventano `0.0` e i numeri finiti sono limitati a `[0.0, 1.0]` tramite validatore della classe base. La verifica isolata è documentata nella [fase 06](06-documentation.md).
- `extraction/pipeline.py:122`: il risultato è `Dict[str, Any]`, con `fields`, `soggetti`, `fidi`, `garanzie`, `canonical_fields`, `_attempts`, `_meta_agg`, `_field_sources`, `_content_crop`, `_status`; il ramo di uscita anticipata ha una forma ridotta. `screen_id` è impostato anche dalle diverse implementazioni di `call_vlm()` (`extraction/vlm_client.py:118`; `extraction/vlm_client.py:178`; `extraction/vlm_client.py:225`).
- `extraction/vlm_client.py::call_vlm`: `_meta` contiene contabilizzazione e diagnostica del singolo tentativo; il contratto pubblico è un dizionario, non un modello separato validato. Le aggregazioni sono gestite da `ExtractionPipeline._aggregate_meta()`.
- `extraction/canonical_mapping.py::build_canonical_field_entries`: ogni voce canonica unisce chiave schema, nome campo, chiave/nome pagina e payload di valore/confidenza. Le colonne Excel sono definite da `ColumnSpec`, non dall’ordine fortuito dei dizionari.
- `edge-agent/local_extraction_client.py:87`: `result_ready = QtCore.pyqtSignal(str, dict)`; argomenti `(job_id, result)`. `frame_queued = QtCore.pyqtSignal(str, str)`; argomenti `(job_id, page_type)`.
- `edge-agent/workers/capture/base_capture_worker.py:17`: `tick = QtCore.pyqtSignal(str)`, `error = QtCore.pyqtSignal(Exception)`, `llm_debug = QtCore.pyqtSignal(str)`; quest’ultimo trasporta JSON testuale di debug.
- `edge-agent/ui/capture_tab.py`: `get_current_job_id()` espone la sessione alla finestra; `force_capture(page_name)` riceve il nome canonico della pagina, non un’immagine.

### Protocollo di visita, accettazione e completamento

Questi helper sono privati ma definiscono il confine tra thread e il significato dei risultati. Le firme sono quelle correnti.

- `def _queue_extraction_result(self, job_id: str, result: dict) -> None:` — `edge-agent/workers/capture/bper_capture_worker.py:278`.
- `def _drain_commands(self) -> bool:` — `edge-agent/workers/capture/bper_capture_worker.py:284`.
- `def _complete_capture(self, job_id: str, sequence: Optional[int], status: Optional[str]) -> None:` — `edge-agent/workers/capture/bper_capture_worker.py:299`.
- `def _restart_stability(self, page: PageDef) -> None:` — `edge-agent/workers/capture/bper_capture_worker.py:323`.
- `def _observe_frame(self, raw: Image.Image) -> None:` — `edge-agent/workers/capture/bper_capture_worker.py:329`.
- `def _acquire(self, job_id: str, img: Image.Image, page: PageDef, score: float, fields: dict) -> None:` — `edge-agent/workers/capture/bper_capture_worker.py:422`.
- `def _upload_page( self, job_id: str, img: Image.Image, page: PageDef, confidence: float = 0.0, fields: Optional[dict] = None, ) -> Optional[int]:` — `edge-agent/workers/capture/bper_capture_worker.py:687`.
- `def _execute_manual_capture(self, page_name: str) -> None:` — `edge-agent/workers/capture/bper_capture_worker.py:727`.

- `verified`: `ingest_frame(...) -> int` restituisce la sequenza zero-based per job solo quando il pool ha accettato il task; a pool fermo solleva `RuntimeError`, non consuma la sequenza e non emette `frame_queued` (`edge-agent/local_extraction_client.py:127`).
- `verified`: `result_ready` notifica ogni completamento, anche fuori ordine. Ogni payload ha `_capture_sequence`, `_page_type`, `_page_no`, `_page_confidence`; un’eccezione pipeline produce `_status="ERROR"` e `_error`. Un errore diagnostico è registrato in `_diagnostic_error` senza lasciare un buco permanente (`edge-agent/local_extraction_client.py:157`).
- `verified`: `get_results(job_id)` restituisce una nuova lista contenente il solo prefisso completato in ordine di cattura; i payload non sono copie profonde. L’ordine è per job e un job lento non impedisce la pubblicazione di un altro (`edge-agent/local_extraction_client.py:194`; `edge-agent/local_extraction_client.py:222`).
- `verified`: il worker collega `result_ready` con `DirectConnection`; lo slot accoda solo `(job_id, sequence, status)` e il loop applica gli acknowledgement. La tabella `_pending_captures[(job_id, sequence)]` conserva `(visit, PageDef)`; un completamento vecchio non libera il pending di una visita nuova (`edge-agent/workers/capture/bper_capture_worker.py:64`; `edge-agent/workers/capture/bper_capture_worker.py:278`; `edge-agent/workers/capture/bper_capture_worker.py:299`).
- `verified`: una visita è l’identità `(dimensioni, modalità immagine, digest BLAKE2b dei pixel)` del frame normalizzato. Una variazione anche piccola azzera stabilità e stato di visita; il pHash resta un risparmio per il routing, non il criterio di identità della pratica (`edge-agent/workers/capture/bper_capture_worker.py:329`).
- `verified`: pagina accodata e pagina completata sono stati diversi. `captured_page_types` viene aggiornato solo dopo acknowledgement non `ERROR`, incluso `ANCHOR_UNCERTAIN`; quest’ultimo non scatena ricatture infinite su pagine senza NDG (`edge-agent/workers/capture/bper_capture_worker.py:299`).
- `verified`: un errore della visita corrente riavvia l’intervallo di stabilità e mantiene selezione pagina/metadati dell’acquisizione; una visita completata e immobile non viene reinviata automaticamente (`edge-agent/workers/capture/bper_capture_worker.py:323`; `edge-agent/workers/capture/bper_capture_worker.py:346`; `edge-agent/workers/capture/bper_capture_worker.py:422`).
- `verified`: `force_capture(page_name)` accoda la richiesta; `_execute_manual_capture()` acquisisce nel thread della camera. Una richiesta sulla stessa pagina pending è coalescente; dopo successo può forzare un nuovo scatto. Lo scatto manuale usa confidenza `0.0` e campi `{}`, quindi non eredita accidentalmente metadati del routing automatico (`edge-agent/workers/capture/bper_capture_worker.py:722`).
- `verified`: dopo `stop()` il latch `_stop_requested` impedisce nuove catture e drenaggio delle richieste manuali. La camera viene creata/usata/chiusa nel `run()` del worker; la disconnessione del risultato è nel `finally` (`edge-agent/workers/capture/base_capture_worker.py:41`; `edge-agent/workers/capture/base_capture_worker.py:73`; `edge-agent/workers/capture/bper_capture_worker.py:216`).

### Altri contratti funzionali

- Batch: callback `on_complete(screen_id, result)` e `on_error(screen_id, exception)` sono invocate dal thread chiamante del runner, anche se le estrazioni lavorano in pool (`extraction/cli.py:210`).
- Pipeline: `extract_from_image(..., allow_content_crop=False)` serve il flusso live; `extract_from_screen(path)` abilita il crop condizionato alla famiglia calibrata. `extract_anchors(..., calibrated=False)` legge tutto il frame (`extraction/pipeline.py:78`; `extraction/pipeline.py:122`; `extraction/pipeline.py:223`).
- Consolidamento: `consolidate(results)` richiede sequenza cronologica; i frame senza NDG si agganciano all’ultima pratica, quelli iniziali alla prima riconosciuta. `normalize_ndg()` conserva l’identità alfanumerica; `pick_best()` definisce la fusione condivisa (`edge-agent/practice_consolidation.py:46`; `edge-agent/practice_consolidation.py:105`).
- Esportazione: `write_workbook()` scrive un workbook con intestazione a due livelli; `export_results()` consolida e restituisce il numero di pratiche. Le celle testuali sono di tipo `s`, incluse stringhe che iniziano con `=` (`edge-agent/excel_export.py:124`; `edge-agent/excel_export.py:177`; `edge-agent/excel_export.py:217`).
- Catalogo prompt: `load_prompts()` valida identificatori, parti e placeholder; override esplicito via `PROMPTS_DIR` non ha fallback implicito. Le funzioni `get_text()`/`get_part()` leggono il catalogo caricato all’import (`prompt_store.py:220`; `prompt_store.py:239`; `prompt_store.py:302`; `prompt_store.py:310`).
- Registro pagine: `PageRegistry.load()` può sollevare `ValueError` su metadati mancanti/duplicati; il worker usa `empty()` in caso di errore e passa a risoluzione permissiva (`edge-agent/page_registry.py:40`; `edge-agent/page_registry.py:63`; `edge-agent/workers/capture/bper_capture_worker.py:244`).
- Pool: `submit(...) -> bool` distingue accettazione/rifiuto; `pending()` conta i task ancora in coda, non quelli in esecuzione. `stop()` scarta quelli accodati e lascia concludere i daemon già attivi (`edge-agent/extraction_pool.py:33`; `edge-agent/extraction_pool.py:40`; `edge-agent/extraction_pool.py:44`).

## External Dependencies

| Libreria / sistema | Utilizzo verificato |
|---|---|
| LangChain core, OpenAI, Google GenAI | modelli estrattivi tramite `llm_factory.py`; messaggi e structured output tramite `vlm_client.py` |
| Pydantic | schemi e validatore confidenza in `schemas.py`; dipendenza importata direttamente ma non elencata direttamente in requirements |
| Pillow | immagini, crop, preprocessing e serializzazione in pipeline, worker e strumenti |
| Pandas | ground truth, valutazione e CSV |
| PyQt6, qt-material | UI, segnali, thread e tema edge-agent |
| Tkinter | GUI batch alternativa, parte della libreria standard |
| torch, torchvision | embedding DINOv2 e trasformazioni del classificatore locale |
| OpenAI SDK | router LLM e annotatore `tools/label_frames.py` |
| mss | cattura monitor nel worker BPER |
| pyscreenshot | cattura del worker generico; requisito limitato a Linux |
| imagehash | dedup pHash e strumenti corpus |
| openpyxl | esportazione workbook |
| requests | upload HTTP nel worker generico |
| python-dotenv | bootstrap ambiente nei punti d’ingresso e client locale |
| PyInstaller | build portable, non dipendenza della pipeline in esecuzione da sorgenti |
| pytest | suite in `tests/`, requisito dev |
| transformers | import nello strumento `tools/benchmark_backbones.py`, non presente in requirements principali |
| ffmpeg | sottoprocesso in `tools/extract_frames.py`; installazione di sistema esterna |

## Cross-Partition Inbound References

Non applicabile: esiste soltanto la partizione `root`. Non sono stati consultati output di altri worker. I consumatori interni sono elencati nel catalogo degli import di `01-structure.md`.

## Interfaccia della suite

I moduli `tests/test_*.py` espongono funzioni pytest e fixture. Il loro inventario completo di simboli è in `01-structure.md`; la presente fase non esegue test. Le nuove superfici hanno consumatori diretti in `test_bper_capture_lifecycle.py`, `test_local_extraction_client.py` e `test_base_capture_worker.py`. Il rapporto runtime resta responsabilità dell’orchestratore.

## How to Add a New Module (per partition)

### Partition: root

1. Collocare logica di estrazione in `extraction/` o un componente edge-agent nel sottosistema pertinente; adottare annotazioni complete per i nuovi callable.
2. Usare `ExtractionPipeline`/`create_chat_model()` per l’estrazione e `LocalExtractionClient.ingest_frame()` per l’accodamento live, preservando il contratto di sequenza restituita.
3. Registrare soltanto ciò che serve: facciata `extraction/__init__.py`, package `workers/capture/__init__.py`, UI o cataloghi. Per un campo nuovo aggiornare vocabolario, mapping canonico, aree retry e prompt insieme; il codice attuale non fornisce un `FIELD_RETRY_MAP` da estendere.
4. Aggiungere test del comportamento in `tests/`, con errore atteso prima dell’intervento; per cattura manuale/ack mantenere una vera coda e simulare soltanto confini esterni.
5. Aggiornare la presente analisi e gli eventuali contratti coinvolti dopo la modifica, riportando separatamente l’evidenza runtime realmente eseguita.
