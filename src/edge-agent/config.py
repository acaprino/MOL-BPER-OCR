"""Modulo per la gestione della configurazione dell'agente."""

import configparser
import os
from pathlib import Path
from typing import Optional, Tuple


class AgentConfig:
    """
    Configurazione dell'agente edge per cattura e comunicazione API.

    Carica i parametri da un file INI (config.ini per default), applicando
    valori di fallback sensati se alcune chiavi non sono presenti.
    """

    # Valori di default “di sicurezza”
    DEFAULT_FPS = 1
    DEFAULT_API_BASE = "http://localhost:8000"
    DEFAULT_WINDOW_FILTER = ""
    DEFAULT_MINIO_ENDPOINT = "http://localhost:9000"
    DEFAULT_MINIO_BUCKET = "edge-agent-frames"
    DEFAULT_MINIO_ACCESS_KEY = "minioadmin"
    DEFAULT_MINIO_SECRET_KEY = "minioadmin"
    # Nuovi default per router/LLM/dataset
    # ml | llm | hybrid | local-first
    #   ml          solo classificatore locale
    #   llm         solo router VLM (una chiamata per frame instradato)
    #   hybrid      prova LLM, ripiega su ML: la rete si paga sempre
    #   local-first classificatore locale, con ripiego sull'LLM solo quando il margine
    #               sul secondo classificato non basta. E' l'inversa di hybrid, ed e'
    #               quella che toglie la rete dal caso comune (docs/adr/0008)
    DEFAULT_ROUTER_MODE = "ml"
    DEFAULT_LLM_PROVIDER = "openai"
    DEFAULT_LLM_MODEL = "gpt-4o-mini"
    DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
    GEMINI_OPENAI_COMPAT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
    DEFAULT_LLM_TIMEOUT = 60
    DEFAULT_DATASET_ENABLED = True
    DEFAULT_DATASET_BUCKET = "page-dataset"
    DEFAULT_DATASET_CONFIDENCE = 0.8
    DEFAULT_DATASET_MAX_PER_PAGE = 3
    # Cattura monitor e overlay
    DEFAULT_MONITOR_INDEX = 1  # mss usa 1..N
    DEFAULT_SHOW_CAPTURE_BORDER = True
    # Debug tab
    DEFAULT_SHOW_LLM_DEBUG_TAB = False
    # Preprocessing / upload
    DEFAULT_IMAGE_SCALE: float | None = None  # None = auto
    DEFAULT_UNSHARP_AMOUNT = 0.8
    DEFAULT_UNSHARP_RADIUS = 1.2
    DEFAULT_UNSHARP_THRESHOLD = 2
    DEFAULT_UPLOAD_FORMAT = "png"  # png | png8 | webp
    DEFAULT_DEDUP_THRESHOLD = 3
    # Intervallo minimo tra tentativi di routing su frame duplicati (per evitare blocchi)
    DEFAULT_ROUTE_RETRY_SECONDS = 1.0

    def __init__(self, config_path: Optional[Path] = None):
        """
        Inizializza la configurazione da file INI.

        Args:
            config_path:
                Percorso al file config.ini.
                Se None, usa "config.ini" nella directory corrente.
        """
        if config_path is None:
            config_path = Path("config.ini")

        self.config_path = Path(config_path)

        # Valori iniziali (fallback)
        self.fps: int = self.DEFAULT_FPS
        self.window_title_contains: str = self.DEFAULT_WINDOW_FILTER
        self.monitor_index: int = self.DEFAULT_MONITOR_INDEX
        self.show_capture_border: bool = self.DEFAULT_SHOW_CAPTURE_BORDER
        self.show_llm_debug_tab: bool = self.DEFAULT_SHOW_LLM_DEBUG_TAB
        # Preprocess / upload
        self.image_scale: float | None = self.DEFAULT_IMAGE_SCALE
        self.unsharp_amount: float = self.DEFAULT_UNSHARP_AMOUNT
        self.unsharp_radius: float = self.DEFAULT_UNSHARP_RADIUS
        self.unsharp_threshold: int = self.DEFAULT_UNSHARP_THRESHOLD
        self.upload_format: str = self.DEFAULT_UPLOAD_FORMAT
        self.dedup_threshold: int = self.DEFAULT_DEDUP_THRESHOLD
        self.route_retry_seconds: float = self.DEFAULT_ROUTE_RETRY_SECONDS

        self.api_base: str = self.DEFAULT_API_BASE

        self.minio_endpoint: str = self.DEFAULT_MINIO_ENDPOINT
        self.minio_bucket: str = self.DEFAULT_MINIO_BUCKET
        self.minio_access_key: str = self.DEFAULT_MINIO_ACCESS_KEY
        self.minio_secret_key: str = self.DEFAULT_MINIO_SECRET_KEY

        # Router / LLM
        self.router_mode: str = self.DEFAULT_ROUTER_MODE

        # Margine minimo perche' la risposta locale sia accettata senza interrogare
        # l'LLM, in modalita' local-first. Il margine e non il punteggio: misurato su
        # fotogrammi tenuti fuori, i punteggi assoluti di risposte giuste e sbagliate
        # si sovrappongono, i margini no.
        self.local_margin_min: float = 0.10
        self.llm_provider: str = self.DEFAULT_LLM_PROVIDER
        self.llm_base_url: str = "https://api.openai.com/v1"
        self.llm_model: str = self.DEFAULT_LLM_MODEL
        self.llm_timeout: int = self.DEFAULT_LLM_TIMEOUT
        self.llm_api_key: str = ""  # può arrivare dall'env OPENAI_API_KEY/LLM_API_KEY
        # Traccia quali voci [llm] sono state scritte esplicitamente nell'INI:
        # i valori espliciti sono autoritativi in resolve_llm_settings().
        self._ini_has_llm_base_url: bool = False
        self._ini_has_llm_model: bool = False

        # Dataset (raccolta per futura CNN)
        self.dataset_enabled: bool = self.DEFAULT_DATASET_ENABLED
        self.dataset_bucket: str = self.DEFAULT_DATASET_BUCKET
        self.dataset_confidence_threshold: float = self.DEFAULT_DATASET_CONFIDENCE
        self.dataset_max_per_page: int = self.DEFAULT_DATASET_MAX_PER_PAGE

        # Carica da file se esiste
        self._load_from_ini()

    # ------------------------------------------------------------------ caricamento INI

    def _load_from_ini(self) -> None:
        """
        Carica i parametri dal file INI se presente.

        Struttura attesa (non obbligatoria, i campi mancanti usano default):

            [agent]
            fps = 1
            window_title_contains = BPER

            [api]
            base_url = http://localhost:8000

            [minio]
            endpoint = http://localhost:9000
            access_key = minioadmin
            secret_key = minioadmin
            bucket = edge-agent-frames
        """
        parser = configparser.ConfigParser()

        if not self.config_path.exists():
            # Nessun file: si rimane con i default.
            return

        parser.read(self.config_path, encoding="utf-8")

        # --- Sezione [agent] ---
        agent_section = parser["agent"] if "agent" in parser else {}
        if agent_section:
            fps_str = agent_section.get("fps", str(self.DEFAULT_FPS))
            try:
                fps_val = int(fps_str)
                self.fps = max(1, fps_val)
            except ValueError:
                self.fps = self.DEFAULT_FPS

            self.window_title_contains = agent_section.get(
                "window_title_contains",
                self.DEFAULT_WINDOW_FILTER,
            )

        # --- Sezione [api] ---
        api_section = parser["api"] if "api" in parser else {}
        if api_section:
            self.api_base = api_section.get("base_url", self.DEFAULT_API_BASE).rstrip(
                "/"
            )

        # --- Sezione [agent] estesa per router ---
        if agent_section:
            self.router_mode = agent_section.get("router", self.DEFAULT_ROUTER_MODE).lower()
            self.local_margin_min = agent_section.getfloat(
                "local_margin_min", self.local_margin_min
            )
            # monitor index
            try:
                self.monitor_index = int(agent_section.get("monitor_index", str(self.DEFAULT_MONITOR_INDEX)))
                if self.monitor_index < 1:
                    self.monitor_index = self.DEFAULT_MONITOR_INDEX
            except ValueError:
                self.monitor_index = self.DEFAULT_MONITOR_INDEX
            # overlay border flag
            show_border_val = agent_section.get("show_capture_border", str(self.DEFAULT_SHOW_CAPTURE_BORDER))
            self.show_capture_border = str(show_border_val).strip().lower() in {"1", "true", "yes", "on"}

            # Preprocessing / upload
            try:
                sc = agent_section.get("image_scale", "auto").strip().lower()
                if sc in {"auto", "", "none"}:
                    self.image_scale = None
                else:
                    self.image_scale = float(sc)
            except Exception:
                self.image_scale = self.DEFAULT_IMAGE_SCALE
            try:
                self.unsharp_amount = float(agent_section.get("unsharp_amount", str(self.DEFAULT_UNSHARP_AMOUNT)))
            except Exception:
                self.unsharp_amount = self.DEFAULT_UNSHARP_AMOUNT
            try:
                self.unsharp_radius = float(agent_section.get("unsharp_radius", str(self.DEFAULT_UNSHARP_RADIUS)))
            except Exception:
                self.unsharp_radius = self.DEFAULT_UNSHARP_RADIUS
            try:
                self.unsharp_threshold = int(agent_section.get("unsharp_threshold", str(self.DEFAULT_UNSHARP_THRESHOLD)))
            except Exception:
                self.unsharp_threshold = self.DEFAULT_UNSHARP_THRESHOLD
            self.upload_format = agent_section.get("upload_format", self.DEFAULT_UPLOAD_FORMAT).strip().lower()
            try:
                self.dedup_threshold = int(agent_section.get("dedup_threshold", str(self.DEFAULT_DEDUP_THRESHOLD)))
            except Exception:
                self.dedup_threshold = self.DEFAULT_DEDUP_THRESHOLD
            # Intervallo minimo tra tentativi di routing quando il frame è duplicato
            try:
                self.route_retry_seconds = float(
                    agent_section.get("route_retry_seconds", str(self.DEFAULT_ROUTE_RETRY_SECONDS))
                )
                if self.route_retry_seconds < 0:
                    self.route_retry_seconds = self.DEFAULT_ROUTE_RETRY_SECONDS
            except Exception:
                self.route_retry_seconds = self.DEFAULT_ROUTE_RETRY_SECONDS

        # --- Sezione [llm] ---
        llm_section = parser["llm"] if "llm" in parser else {}
        if llm_section:
            self.llm_provider = llm_section.get("provider", self.DEFAULT_LLM_PROVIDER)
            self.llm_base_url = llm_section.get("base_url", self.llm_base_url)
            self.llm_model = llm_section.get("model", self.DEFAULT_LLM_MODEL)
            self._ini_has_llm_base_url = bool((llm_section.get("base_url") or "").strip())
            self._ini_has_llm_model = bool((llm_section.get("model") or "").strip())
            try:
                self.llm_timeout = int(llm_section.get("timeout", str(self.DEFAULT_LLM_TIMEOUT)))
            except ValueError:
                self.llm_timeout = self.DEFAULT_LLM_TIMEOUT
            # Rimuovi spazi accidentali attorno alla chiave
            self.llm_api_key = (llm_section.get("api_key", "") or "").strip()
            # I placeholder di bonifica (es. REDACTED_OPENAI_API_KEY) non sono chiavi:
            # trattali come vuoto così scatta il fallback su OPENAI_API_KEY/LLM_API_KEY.
            if self.llm_api_key.upper().startswith("REDACTED"):
                self.llm_api_key = ""

        # --- Sezione [dataset] ---
        dataset_section = parser["dataset"] if "dataset" in parser else {}
        if dataset_section:
            self.dataset_enabled = dataset_section.get("enabled",
                                                       str(self.DEFAULT_DATASET_ENABLED)).strip().lower() in {"1",
                                                                                                              "true",
                                                                                                              "yes",
                                                                                                              "on"}
            self.dataset_bucket = dataset_section.get("bucket", self.DEFAULT_DATASET_BUCKET)
            try:
                self.dataset_confidence_threshold = float(
                    dataset_section.get("confidence_threshold", str(self.DEFAULT_DATASET_CONFIDENCE)))
            except ValueError:
                self.dataset_confidence_threshold = self.DEFAULT_DATASET_CONFIDENCE
            try:
                self.dataset_max_per_page = int(
                    dataset_section.get("max_per_page", str(self.DEFAULT_DATASET_MAX_PER_PAGE)))
            except ValueError:
                self.dataset_max_per_page = self.DEFAULT_DATASET_MAX_PER_PAGE

        # --- Sezione [debug] ---
        debug_section = parser["debug"] if "debug" in parser else {}
        if debug_section:
            show_dbg_val = debug_section.get("show_llm_tab", str(self.DEFAULT_SHOW_LLM_DEBUG_TAB))
            self.show_llm_debug_tab = str(show_dbg_val).strip().lower() in {"1", "true", "yes", "on"}

        # --- Sezione [minio] ---
        minio_section = parser["minio"] if "minio" in parser else {}
        if minio_section:
            self.minio_endpoint = minio_section.get(
                "endpoint",
                self.DEFAULT_MINIO_ENDPOINT,
            ).rstrip("/")
            self.minio_bucket = minio_section.get(
                "bucket",
                self.DEFAULT_MINIO_BUCKET,
            )
            self.minio_access_key = minio_section.get(
                "access_key",
                self.DEFAULT_MINIO_ACCESS_KEY,
            )
            self.minio_secret_key = minio_section.get(
                "secret_key",
                self.DEFAULT_MINIO_SECRET_KEY,
            )

    # ------------------------------------------------------------------ risoluzione LLM

    def resolve_llm_settings(self) -> Tuple[str, str, str]:
        """
        Risolve (api_key, base_url, model) per il router LLM in base al provider.

        I valori espliciti in config.ini sono autoritativi; i default per
        provider si applicano solo alle voci assenti o vuote. Catena chiavi:
        api_key INI se non vuota, poi env (gemini: GEMINI_API_KEY →
        GOOGLE_API_KEY → LLM_API_KEY; openai: OPENAI_API_KEY → LLM_API_KEY).
        """
        provider = (self.llm_provider or "openai").lower()
        if provider == "gemini":
            api_key = (
                self.llm_api_key
                or os.getenv("GEMINI_API_KEY")
                or os.getenv("GOOGLE_API_KEY")
                or os.getenv("LLM_API_KEY", "")
            )
            base_url = self.llm_base_url if self._ini_has_llm_base_url else self.GEMINI_OPENAI_COMPAT_BASE_URL
            model = self.llm_model if self._ini_has_llm_model else self.DEFAULT_GEMINI_MODEL
        else:
            api_key = (
                self.llm_api_key
                or os.getenv("OPENAI_API_KEY")
                or os.getenv("LLM_API_KEY", "")
            )
            base_url = self.llm_base_url if self._ini_has_llm_base_url else "https://api.openai.com/v1"
            model = self.llm_model if self._ini_has_llm_model else self.DEFAULT_LLM_MODEL
        return api_key, base_url, model

    # ------------------------------------------------------------------ aggiornamento da UI

    def update_from_ui(self, fps: int, window_filter: str) -> None:
        """
        Aggiorna i parametri principali a partire dall'input della UI.

        Args:
            fps:
                Frame per secondo per la cattura. Valori < 1 vengono forzati a 1.
            window_filter:
                Filtro per il titolo della finestra (substring case-sensitive
                utilizzata, se implementato, per limitare la cattura a una finestra).
        """
        self.fps = max(1, int(fps))
        self.window_title_contains = window_filter or ""

    # ------------------------------------------------------------------ salvataggio opzionale

    def save(self) -> None:
        """
        Salva la configurazione corrente su file INI.

        Nota: questa implementazione scrive tutte le sezioni/chiavi usate
        dall'agente, sovrascrivendo eventualmente il file esistente.
        """
        parser = configparser.ConfigParser()

        parser["agent"] = {
            "fps": str(self.fps),
            "window_title_contains": self.window_title_contains,
            "router": self.router_mode,
            "local_margin_min": str(self.local_margin_min),
            "monitor_index": str(self.monitor_index),
            "show_capture_border": "true" if self.show_capture_border else "false",
            "image_scale": str(self.image_scale) if self.image_scale is not None else "auto",
            "unsharp_amount": str(self.unsharp_amount),
            "unsharp_radius": str(self.unsharp_radius),
            "unsharp_threshold": str(self.unsharp_threshold),
            "upload_format": self.upload_format,
            "dedup_threshold": str(self.dedup_threshold),
            "route_retry_seconds": str(self.route_retry_seconds),
        }

        parser["api"] = {
            "base_url": self.api_base.rstrip("/"),
        }

        parser["minio"] = {
            "endpoint": self.minio_endpoint.rstrip("/"),
            "bucket": self.minio_bucket,
            "access_key": self.minio_access_key,
            "secret_key": self.minio_secret_key,
        }

        parser["llm"] = {
            "provider": self.llm_provider,
            "base_url": self.llm_base_url,
            "model": self.llm_model,
            "timeout": str(self.llm_timeout),
            "api_key": self.llm_api_key,
        }

        parser["dataset"] = {
            "enabled": "true" if self.dataset_enabled else "false",
            "bucket": self.dataset_bucket,
            "confidence_threshold": str(self.dataset_confidence_threshold),
            "max_per_page": str(self.dataset_max_per_page),
        }

        parser["debug"] = {
            "show_llm_tab": "true" if self.show_llm_debug_tab else "false",
        }

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as f:
            parser.write(f)

    # ------------------------------------------------------------------ rappresentazione

    def __repr__(self) -> str:
        """
        Rappresentazione sintetica utile per log/debug.
        """
        return (
            "AgentConfig("
            f"fps={self.fps}, "
            f"api_base={self.api_base}, "
            f"minio_endpoint={self.minio_endpoint}, "
            f"minio_bucket={self.minio_bucket}"
            f", router={self.router_mode}, llm_model={self.llm_model}"
            ")"
        )
