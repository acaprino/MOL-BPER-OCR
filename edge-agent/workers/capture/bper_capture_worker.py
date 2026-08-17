"""Worker di cattura specifico per il flusso BPER."""

from __future__ import annotations

import json
import time
import uuid
from typing import Optional, Set, Tuple, List, Any

import imagehash
from PIL import Image
from PyQt6 import QtCore
from llm_router import PageRouter, MLPageRouter, LLMPageRouter, RouterResult  # type: ignore

try:
    from page_classifier import BPERPagePrototypeClassifier  # type: ignore
except Exception:  # noqa: BLE001
    BPERPagePrototypeClassifier = None  # type: ignore

from .base_capture_worker import BaseCaptureWorker
from image_ops import preprocess_for_ocr
import app_paths
from page_registry import PageDef, PageRegistry
from stability import StabilityTracker


class BPERCaptureWorker(BaseCaptureWorker):
    """
    Worker di cattura per l'applicativo BPER.

    Funzionalità:
        - cattura screenshot full-screen
        - dedup frame via pHash
        - riconoscimento pagina con BPERPagePrototypeClassifier (MobileNetV3 + prototipi)
        - logica di stabilità (conteggio + permanenza, tollera 1 frame anomalo)
        - upload screenshot solo quando la pagina è stabile
    """

    # soglia di “uguale” per dedup frame (distanza Hamming su pHash)
    DEDUP_HASH_THRESHOLD = 3

    def __init__(
            self,
            config,
            job_id_getter,
            api_client: Optional[Any] = None,
            parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(config, job_id_getter, parent)
        self.api_client = api_client

        # Stato dedup
        self._last_frame_hash: Optional[imagehash.ImageHash] = None

        # Stabilità pagina (macchina a stati pura, vedi stability.py)
        self._tracker = StabilityTracker()

        # Pagine già acquisite in questo job (nomi canonici dal registro)
        self.captured_page_types: Set[str] = set()

        # Registro pagine: caricato in run() nel thread worker
        self.registry: PageRegistry = PageRegistry.empty()
        self._acquirable_names: List[str] = []

        # Routing (ML o LLM): l'inizializzazione vera avviene in run(), nel
        # thread worker — il caricamento DINOv2 non deve congelare la UI.
        self.classifier: Optional[Any] = None
        self.router: Optional[PageRouter] = None
        self._router_ready: bool = False

        # Throttling routing su frame duplicati: ultimo tentativo eseguito
        self._last_route_attempt_ts: Optional[float] = None

        # Contatore errori di cattura consecutivi (auto-stop oltre soglia)
        self._consecutive_capture_errors: int = 0
        self._MAX_CONSECUTIVE_CAPTURE_ERRORS: int = 5

        # mss context singleton (creato una volta nel QThread, non in __init__)
        self._mss_ctx: Optional[Any] = None

        # Anti-spam log: ultima guida emessa e ultima pagina "già acquisita"
        self._last_guidance_page: Optional[str] = None
        self._last_already_captured: Optional[str] = None

        # Ultimo errore router già loggato (per non ripeterlo a ogni frame)
        self._last_router_error: Optional[str] = None

    # ------------------------------------------------------------------ init classifier

    def _init_router(self) -> None:
        """Inizializza il router pagina in base a config.router_mode."""
        try:
            # Struttura attesa:
            #   <root_edge_agent>/assets/templates/bper/...
            templates_dir = app_paths.templates_dir()

            mode = (self.config.router_mode or "ml").lower()
            if mode == "llm":
                prompts_path = templates_dir / "prompts.json"
                api_key, base_url, model = self.config.resolve_llm_settings()
                self.router = LLMPageRouter(
                    prompts_path=prompts_path,
                    provider=self.config.llm_provider,
                    base_url=base_url,
                    model=model,
                    api_key=api_key or "",
                    timeout=self.config.llm_timeout,
                )
                # Log diagnostico
                pages_count = 0
                try:
                    spec = json.loads(prompts_path.read_text(encoding="utf-8")) if prompts_path.exists() else {}
                    pages_count = len(spec.get("pages", [])) if isinstance(spec, dict) else 0
                except Exception:
                    pages_count = 0
                has_key = bool(api_key)
                self.tick.emit(
                    f"[BPER-LLM] Router LLM inizializzato (provider={self.config.llm_provider}, model={model}, pages={pages_count}, api_key={'yes' if has_key else 'no'})"
                )
            elif mode == "hybrid":
                # per ora: usa LLM, altrimenti fallback su ML
                prompts_path = templates_dir / "prompts.json"
                api_key, base_url, model = self.config.resolve_llm_settings()
                self.router = LLMPageRouter(
                    prompts_path=prompts_path,
                    provider=self.config.llm_provider,
                    base_url=base_url,
                    model=model,
                    api_key=api_key or "",
                    timeout=self.config.llm_timeout,
                )
                # Log diagnostico
                pages_count = 0
                try:
                    spec = json.loads(prompts_path.read_text(encoding="utf-8")) if prompts_path.exists() else {}
                    pages_count = len(spec.get("pages", [])) if isinstance(spec, dict) else 0
                except Exception:
                    pages_count = 0
                has_key = bool(api_key)
                self.tick.emit(
                    f"[BPER-LLM] Router ibrido inizializzato (LLM→fallback ML, provider={self.config.llm_provider}, model={model}, pages={pages_count}, api_key={'yes' if has_key else 'no'})"
                )
                # In parallelo inizializza ML per fallback, se disponibile
                if BPERPagePrototypeClassifier is not None:
                    try:
                        from page_classifier import DEFAULT_CROP_ROI, DEFAULT_SIMILARITY_THRESHOLD
                        self.classifier = BPERPagePrototypeClassifier(
                            templates_dir=templates_dir,
                            crop_roi=DEFAULT_CROP_ROI,
                            similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD,
                            device="cpu",
                        )
                    except Exception:
                        self.classifier = None
            else:
                # ML: MLPageRouter è l'unico proprietario del classificatore
                # (una sola istanza DINOv2, condivisa per log/diagnostica)
                self.router = MLPageRouter(templates_dir)
                self.classifier = self.router.classifier
                if self.classifier is not None:
                    try:
                        info = self.classifier.info()
                        self.tick.emit(
                            "[BPER-ML] classifier init: "
                            f"disabled={info['disabled']} "
                            f"num_prototypes={info['num_prototypes']} "
                            f"templates_dir={info['templates_dir']}"
                        )
                        if info.get("import_error"):
                            self.tick.emit(f"[BPER-ML] import_error: {info['import_error']}")
                    except Exception:
                        pass
        except Exception as exc:  # noqa: BLE001
            # Se qualcosa va storto (es. torch non disponibile), il worker rimane operativo
            # ma senza riconoscimento pagina.
            self.classifier = None
            self.router = None
            self.on_error(exc)
            self.tick.emit("[BPER] Router disabilitato.")

    # ------------------------------------------------------------------ lifecycle

    def run(self) -> None:
        """Inizializza router e registro pagine nel thread worker, poi entra nel loop."""
        if not self._router_ready:
            self.tick.emit("[Worker] Inizializzazione riconoscimento in corso...")
            self._init_router()
            self._load_registry()
            self._router_ready = True
        super().run()

    def stop(self) -> None:
        """Override: ferma il loop e rilascia il contesto mss."""
        super().stop()
        if self._mss_ctx is not None:
            try:
                self._mss_ctx.close()
            except Exception:
                pass
            self._mss_ctx = None

    # ------------------------------------------------------------------ page registry

    def _load_registry(self) -> None:
        """Carica il registro pagine da prompts.json e annuncia la sequenza."""
        try:
            self.registry = PageRegistry.load(app_paths.templates_dir() / "prompts.json")
        except Exception as exc:  # noqa: BLE001
            self.on_error(exc)
            self.registry = PageRegistry.empty()
            self.tick.emit("[BPER] prompts.json non valido: acquisizione libera senza sequenza.")

        mode = (self.config.router_mode or "ml").lower()
        pages = self.registry.acquirable(mode)
        self._acquirable_names = [p.name for p in pages]

        if pages:
            self.tick.emit(f"─── Schermate da acquisire: {len(pages)} ───")
            for i, page in enumerate(pages, 1):
                self.tick.emit(f"  {i:2}. {page.name}")
            self.tick.emit("──────────────────────────────────────")
            first = self._next_pending_page()
            if first:
                self.tick.emit(f"→ Prima schermata da aprire nel sistema BPER: «{first}»")
        else:
            self.tick.emit("[BPER] Attenzione: nessuna pagina definita; funzionamento libero.")

    def _next_pending_page(self) -> Optional[str]:
        """Nome canonico della prossima pagina non ancora acquisita."""
        for name in self._acquirable_names:
            if name not in self.captured_page_types:
                return name
        return None

    # ------------------------------------------------------------------ core loop

    def _capture_once(self) -> None:
        """
        Loop di cattura per BPER:

            - legge job_id
            - cattura screenshot
            - dedup via pHash (con throttling del routing sui duplicati)
            - riconosce pagina via router e la risolve nel registro
            - applica la macchina a stati di stabilità
            - accoda il frame stabile per l'estrazione in background
        """
        job_id = self.job_id_getter()
        if not job_id:
            return

        raw = self._grab_raw()
        if raw is None:
            return

        is_dup = self._is_duplicate_frame(raw)
        if is_dup:
            now_ts = time.time()
            min_interval = float(getattr(self.config, "route_retry_seconds", 1.0) or 1.0)
            if self._last_route_attempt_ts is not None and (now_ts - self._last_route_attempt_ts) < min_interval:
                return

        self._last_route_attempt_ts = time.time()
        img = self._preprocess(raw)
        label, score, fields = self._detect_page(img)
        page = self.registry.resolve(label)

        # Pagina già acquisita: non riacquisire (con l'estrazione asincrona una
        # ri-acquisizione costerebbe una seconda estrazione completa).
        if page is not None and page.name in self.captured_page_types:
            if self._last_already_captured != page.name:
                nxt = self._next_pending_page()
                hint = f" → apri nel sistema BPER: «{nxt}»" if nxt else ""
                self.tick.emit(f"ℹ️ «{page.name}» già acquisita{hint}")
                self._last_already_captured = page.name
            self._tracker.observe(None, time.time())
            return

        prev_candidate = self._tracker.candidate
        ready = self._tracker.observe(page.name if page else None, time.time())

        if page is not None and self._tracker.candidate == page.name and prev_candidate != page.name:
            self.tick.emit(
                f"⏳ Rilevata «{page.name}» — mantieni aperta la schermata "
                f"({self._tracker.config.min_seconds:.0f}s richiesti per la stabilità)"
            )

        if ready is None or page is None:
            return

        n_captured = len(self.captured_page_types) + 1
        n_total: Any = len(self._acquirable_names) or "?"
        self._upload_page(job_id, img, page, score, fields)
        self.captured_page_types.add(page.name)
        self._tracker.reset()
        self._last_already_captured = None

        next_page = self._next_pending_page()
        if next_page:
            self.tick.emit(
                f"✅ «{page.name}» acquisita [{n_captured}/{n_total}] "
                f"→ apri nel sistema BPER: «{next_page}»"
            )
            self._last_guidance_page = next_page
        else:
            self.tick.emit(
                f"✅ «{page.name}» acquisita [{n_captured}/{n_total}] — tutte le schermate completate!"
            )

    # ------------------------------------------------------------------ screenshot & dedup

    def _grab_raw(self) -> Optional[Image.Image]:
        """
        Cattura il frame raw del monitor configurato (mss – veloce e cross‑platform).

        Usa config.monitor_index (1..N). Se l'indice non esiste, ripiega su monitor 1.
        Nessun preprocess: serve solo per dedup; il preprocess è in _preprocess().
        """
        # Inizializza il contesto mss una volta sola (non ad ogni frame)
        if self._mss_ctx is None:
            try:
                import mss as _mss  # type: ignore
                self._mss_ctx = _mss.mss()
            except Exception as exc:  # noqa: BLE001
                self.on_error(RuntimeError(f"mss non disponibile: {exc}"))
                self._running = False
                return None

        try:
            sct = self._mss_ctx
            monitors = sct.monitors  # [0]=all, [1..]=per-monitor
            idx = int(self.config.monitor_index or 1)
            if idx < 1 or idx >= len(monitors):
                idx = 1
            mon = monitors[idx]
            shot = sct.grab(mon)
            img = Image.frombytes('RGB', shot.size, shot.rgb)
            self._consecutive_capture_errors = 0
            return img
        except Exception as exc:  # noqa: BLE001
            self._consecutive_capture_errors += 1
            self.tick.emit(
                f"[Cattura] Errore screenshot ({self._consecutive_capture_errors}/{self._MAX_CONSECUTIVE_CAPTURE_ERRORS}): {exc}"
            )
            if self._consecutive_capture_errors >= self._MAX_CONSECUTIVE_CAPTURE_ERRORS:
                self.on_error(RuntimeError(
                    f"Cattura fallita {self._consecutive_capture_errors} volte consecutive. "
                    f"Ultimo errore: {exc}"
                ))
                self._running = False
            return None

    def _preprocess(self, img: Image.Image) -> Image.Image:
        """Applica il preprocess OCR (scala, unsharp, contrasto); best-effort."""
        try:
            return preprocess_for_ocr(
                img,
                scale=self.config.image_scale,
                unsharp_amount=self.config.unsharp_amount,
                unsharp_radius=self.config.unsharp_radius,
                unsharp_threshold=self.config.unsharp_threshold,
                contrast_stretch=True,
            )
        except Exception:  # noqa: BLE001
            return img

    def _capture_screenshot(self) -> Optional[Image.Image]:
        """Frame già preprocessato (usato dal forza scatto)."""
        raw = self._grab_raw()
        return None if raw is None else self._preprocess(raw)

    def _is_duplicate_frame(self, img: Image.Image) -> bool:
        """
        Ritorna True se il frame è "uguale" al precedente (entro una soglia pHash),
        in modo da evitare lavoro inutile / upload duplicati.
        """
        try:
            resized = img.resize((256, 256))
            cur_hash = imagehash.phash(resized)
        except Exception:
            # Se per qualche ragione fallisce il pHash, non facciamo dedup
            return False

        if self._last_frame_hash is None:
            self._last_frame_hash = cur_hash
            return False

        dist = self._last_frame_hash - cur_hash
        threshold = getattr(self.config, "dedup_threshold", None) or self.DEDUP_HASH_THRESHOLD
        if dist <= threshold:
            # Frame troppo simile al precedente
            return True

        self._last_frame_hash = cur_hash
        return False

    # ------------------------------------------------------------------ detection

    def _detect_page(self, img: Image.Image) -> Tuple[Optional[str], float, dict]:
        """Usa il router configurato per riconoscere la pagina e (se LLM) estrarre campi."""
        if self.router is None and self.classifier is None:
            return None, 0.0, {}

        # Se abbiamo un router, usiamolo
        if self.router is not None:
            res: RouterResult = self.router.route(img)
            # Se debug attivo e router LLM, emetti dettagli
            try:
                if self.config.show_llm_debug_tab and isinstance(self.router, LLMPageRouter):
                    dbg = self.router.get_last_debug()
                    self.llm_debug.emit(json.dumps(dbg, ensure_ascii=False))
            except Exception:
                pass

            if res.page_type:
                resolved = self.registry.resolve(res.page_type)
                shown = resolved.name if resolved else res.page_type
                self.tick.emit(
                    f"[Router] Riconosciuta: «{shown}» (score={res.confidence:.3f})"
                )
                return res.page_type, float(res.confidence), dict(res.fields or {})
            else:
                # Nessun match: se il router riporta un errore (es. 401 API key),
                # rendilo visibile nel log invece di fallire in silenzio.
                reason = getattr(res, "reason", None)
                if reason and reason != self._last_router_error:
                    self.tick.emit(f"[Router] Errore riconoscimento: {reason}")
                    self._last_router_error = reason
                # Guida l'operatore verso la schermata attesa
                try:
                    next_page = self._next_pending_page()
                    if next_page and next_page != self._last_guidance_page:
                        self.tick.emit(
                            f"🔍 Schermata non riconosciuta — "
                            f"apri nel sistema BPER: «{next_page}»"
                        )
                        self._last_guidance_page = next_page
                    elif not next_page:
                        self.tick.emit("🔍 Schermata non riconosciuta.")
                except Exception:
                    self.tick.emit("🔍 Schermata non riconosciuta.")
                # Fallback a ML solo in modalità hybrid: se il router È già il
                # classificatore ML, riclassificare lo stesso frame è identico.
                if self.classifier is not None and isinstance(self.router, LLMPageRouter):
                    label, score = self.classifier.classify(img)
                    if label is not None:
                        resolved = self.registry.resolve(label)
                        shown = resolved.name if resolved else label
                        self.tick.emit(f"[ML] Riconosciuta via fallback: «{shown}» (score={score:.3f})")
                        return label, float(score or 0.0), {}
                return None, 0.0, {}

        # Fallback: solo ML classifier
        label, score = self.classifier.classify(img) if self.classifier else (None, 0.0)
        if label is not None:
            resolved = self.registry.resolve(label)
            shown = resolved.name if resolved else label
            self.tick.emit(f"[ML] Riconosciuta: «{shown}» (score={score:.3f})")
        return label, float(score or 0.0), {}

    # ------------------------------------------------------------------ upload

    def _upload_page(
        self,
        job_id: str,
        img: Image.Image,
        page: PageDef,
        confidence: float = 0.0,
        fields: Optional[dict] = None,
    ) -> None:
        """Accoda lo screenshot di una pagina riconosciuta per l'estrazione."""
        if page.order > 0:
            filename = f"{page.order:02d}-{page.slug}.png"
        else:
            filename = f"{page.slug}-{uuid.uuid4().hex}.png"

        if self.api_client and hasattr(self.api_client, "ingest_frame"):
            try:
                self.api_client.ingest_frame(
                    job_id=job_id,
                    img=img,
                    page_no=page.order,
                    page_type=page.name,
                    confidence=confidence,
                    fields_json=json.dumps(fields or {}),
                )
                self.tick.emit(f"📤 In coda per estrazione: {filename}")
                return
            except Exception as exc:  # noqa: BLE001
                self.on_error(exc)
                return

        self.tick.emit(f"[ERRORE] Client locale non configurato correttamente per {filename}")

    # ------------------------------------------------------------------ forza scatto manuale
    @QtCore.pyqtSlot(str)
    def force_capture(self, page_name: str) -> None:
        """
        Forza lo scatto e l'accodamento dell'immagine corrente come pagina indicata.

        Il nome arriva dal combo della UI (nomi canonici del registro); accetta
        anche uno stem template ("screen 5"). Non richiede stabilità né match
        del router. Aggiunge la pagina a `captured_page_types`.
        """
        try:
            if not self._router_ready:
                self.tick.emit("[BPER] Forza scatto: inizializzazione in corso, riprova tra qualche secondo.")
                return

            job_id = self.job_id_getter()
            if not job_id:
                self.tick.emit("[BPER] Forza scatto: nessun job attivo.")
                return

            page = self.registry.resolve(page_name)
            if page is None:
                self.tick.emit(f"[BPER] Forza scatto: pagina sconosciuta: '{page_name}'.")
                return

            img = self._capture_screenshot()
            if img is None:
                self.tick.emit("[BPER] Forza scatto: nessuno screenshot disponibile.")
                return

            self._upload_page(job_id, img, page, 0.0, {})
            self.captured_page_types.add(page.name)
            self._tracker.reset()
            self._last_already_captured = None
            self.tick.emit(f"[BPER] Forza scatto completato per «{page.name}».")
        except Exception as exc:  # noqa: BLE001
            self.on_error(exc)
