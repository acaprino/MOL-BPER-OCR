"""Worker di cattura specifico per il flusso BPER."""

from __future__ import annotations

import json
import hashlib
import queue
import time
import uuid
from typing import Optional, Set, Tuple, List, Any, Callable

import imagehash
from PIL import Image
from PyQt6 import QtCore
from llm_router import PageRouter, MLPageRouter, LLMPageRouter, RouterResult  # type: ignore

try:
    from page_classifier import BPERPagePrototypeClassifier  # type: ignore
except Exception:  # noqa: BLE001
    BPERPagePrototypeClassifier = None  # type: ignore

from .base_capture_worker import BaseCaptureWorker
from frame_normalize import UNCHANGED, find_window_rect, normalize_frame
from image_ops import preprocess_for_ocr
import app_paths
from page_registry import PageDef, PageRegistry
from stability import StabilityTracker


class BPERCaptureWorker(BaseCaptureWorker):
    """
    Worker di cattura per l'applicativo BPER.

    Funzionalità:
        - cattura screenshot del monitor intero
        - riporta l'inquadratura sulla finestra applicativa (frame_normalize)
        - dedup frame via pHash
        - riconoscimento pagina con BPERPagePrototypeClassifier (DINOv2 ViT-S/14 + prototipi)
        - logica di stabilità (conteggio + permanenza, tollera 1 frame anomalo)
        - accodamento per estrazione solo quando la pagina è stabile
    """

    # soglia di “uguale” per dedup frame (distanza Hamming su pHash)
    DEDUP_HASH_THRESHOLD = 3

    def __init__(
            self,
            config: Any,
            job_id_getter: Callable[[], Optional[str]],
            api_client: Optional[Any] = None,
            parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(config, job_id_getter, parent)
        self.api_client = api_client

        # Only the capture thread mutates visit, camera and acknowledgement state.
        # QThread.run() owns a polling loop, not a Qt event loop: slots only enqueue.
        self._commands: queue.Queue[Tuple[str, Any]] = queue.Queue()
        self._frame_identity: Optional[Tuple[Tuple[int, int], str, bytes]] = None
        self._visit_sequence: int = 0
        self._visit_pending: Optional[int] = None
        self._visit_completed: bool = False
        self._pending_captures: dict[Tuple[str, int], Tuple[int, PageDef]] = {}
        self._result_connected = api_client is not None and hasattr(api_client, "result_ready")
        if self._result_connected:
            api_client.result_ready.connect(
                self._queue_extraction_result, QtCore.Qt.ConnectionType.DirectConnection
            )

        # Stato dedup
        self._last_frame_hash: Optional[imagehash.ImageHash] = None

        # Stabilità pagina (macchina a stati pura, vedi stability.py)
        self._tracker = StabilityTracker()

        # Successfully processed page names for guidance, never a dedup gate.
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

        # Ultimo errore router già loggato (per non ripeterlo a ogni frame)
        self._last_router_error: Optional[str] = None

        # Ultima strategia di inquadratura annunciata (una riga per strategia)
        self._last_framing_strategy: Optional[str] = None

        # Ultimo esito locale annunciato, per non ripetere la stessa riga a ogni frame
        self._last_local_note: Optional[str] = None

        # Margine minimo per fidarsi della risposta locale senza interrogare il router
        self.local_margin_min: float = float(
            getattr(config, "local_margin_min", 0.10) or 0.10
        )

        # Ultimo esito di routing, per acquisire su conferma senza re-interrogare
        self._last_routed_page: Optional[PageDef] = None
        self._last_route_score: float = 0.0
        self._last_route_fields: dict = {}

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
        """Initialize, capture and release the camera in the same thread."""
        try:
            if self._stop_requested:
                return
            if not self._router_ready:
                self.tick.emit("[Worker] Inizializzazione riconoscimento in corso...")
                self._init_router()
                self._load_registry()
                self._router_ready = True
            super().run()
        finally:
            if self._mss_ctx is not None:
                try:
                    self._mss_ctx.close()
                except Exception:
                    pass
                self._mss_ctx = None
            if self._result_connected:
                try:
                    self.api_client.result_ready.disconnect(self._queue_extraction_result)
                except (TypeError, RuntimeError):
                    # Qt may already have disconnected or destroyed the sender.
                    pass
                self._result_connected = False

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

    @QtCore.pyqtSlot(str, dict)
    def _queue_extraction_result(self, job_id: str, result: dict) -> None:
        """Cross-thread entry point: enqueue only, including very fast completions."""
        self._commands.put(("result", (
            job_id, result.get("_capture_sequence"), result.get("_status"),
        )))

    def _drain_commands(self) -> bool:
        """Apply acknowledgements and manual requests inside the capture loop."""
        manual = False
        while not self._stop_requested:
            try:
                command, payload = self._commands.get_nowait()
            except queue.Empty:
                break
            if command == "manual":
                self._execute_manual_capture(payload)
                manual = True
            else:
                self._complete_capture(*payload)
        return manual

    def _complete_capture(self, job_id: str, sequence: Optional[int], status: Optional[str]) -> None:
        """An old completion cannot change the pending state of a newer visit."""
        if sequence is None:
            return
        pending = self._pending_captures.pop((job_id, sequence), None)
        if pending is None:
            return
        visit, page = pending
        current = visit == self._visit_sequence and sequence == self._visit_pending
        if status == "ERROR":
            if current:
                self._visit_pending = None
                self._restart_stability(page)
            self.tick.emit(f"⚠️ Estrazione fallita per «{page.name}»; la pagina può essere acquisita nuovamente.")
            return
        # ANCHOR_UNCERTAIN can contain useful fields from pages without an NDG.
        self.captured_page_types.add(page.name)
        if current:
            self._visit_pending = None
            self._visit_completed = True
        next_page = self._next_pending_page()
        hint = f" → prossima schermata: «{next_page}»" if next_page else ""
        self.tick.emit(f"✅ Estrazione completata per «{page.name}»{hint}")

    def _restart_stability(self, page: PageDef) -> None:
        """An error requires another stable interval, not a retry every frame."""
        self._tracker.reset()
        self._tracker.observe(page.name, time.time())
        self._last_routed_page = page

    def _observe_frame(self, raw: Image.Image) -> None:
        """A visit is one unchanged normalized image, including small ID edits.

        pHash is useful for routing cost but can miss a one-digit NDG change.
        Pixel identity therefore controls rearming and the stability interval.
        Animated content must settle, or the operator can request a manual shot.
        """
        identity = (raw.size, raw.mode, hashlib.blake2b(raw.tobytes(), digest_size=16).digest())
        if identity != self._frame_identity:
            self._frame_identity = identity
            self._visit_sequence += 1
            self._visit_pending = None
            self._visit_completed = False
            self._tracker.reset()
            self._last_routed_page = None
            self._last_route_attempt_ts = None

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
        if self._stop_requested:
            return
        if self._drain_commands() or self._stop_requested:
            return
        job_id = self.job_id_getter()
        if not job_id:
            return

        raw = self._grab_raw()
        if raw is None or self._stop_requested:
            return

        self._observe_frame(raw)
        if self._visit_pending is not None or self._visit_completed:
            return

        is_dup = self._is_duplicate_frame(raw)
        if is_dup:
            # Frame identico al precedente: e' la prova diretta che la pagina non
            # e' cambiata, cioe' esattamente cio' per cui serviva una seconda
            # risposta del router. Confermare qui costa nulla; interrogare di
            # nuovo il router costa una chiamata VLM (4-5s), e con quella cadenza
            # "due osservazioni concordi" significa tenere ferma una schermata
            # per 10-24 secondi invece dei 2 per cui le soglie erano scritte.
            if (self._last_routed_page is not None
                    and self._tracker.candidate == self._last_routed_page.name):
                if self._tracker.confirm(time.time()) is not None:
                    self._acquire(
                        job_id,
                        self._preprocess(raw),
                        self._last_routed_page,
                        self._last_route_score,
                        self._last_route_fields,
                    )
                return

            now_ts = time.time()
            min_interval = float(getattr(self.config, "route_retry_seconds", 1.0) or 1.0)
            if self._last_route_attempt_ts is not None and (now_ts - self._last_route_attempt_ts) < min_interval:
                return

        self._last_route_attempt_ts = time.time()
        img = self._preprocess(raw)
        label, score, fields = self._detect_page(img)
        if self._stop_requested:
            return
        page = self.registry.resolve(label)
        self._last_routed_page = page
        self._last_route_score = score
        self._last_route_fields = fields

        prev_candidate = self._tracker.candidate
        ready = self._tracker.observe(page.name if page else None, time.time())

        if page is not None and self._tracker.candidate == page.name and prev_candidate != page.name:
            self.tick.emit(
                f"⏳ Rilevata «{page.name}» — mantieni aperta la schermata "
                f"({self._tracker.config.min_seconds:.0f}s richiesti per la stabilità)"
            )

        if ready is None or page is None:
            return

        self._acquire(job_id, img, page, score, fields)

    def _acquire(self, job_id: str, img: Image.Image, page: PageDef, score: float, fields: dict) -> None:
        """Record acceptance; only the matching completion confirms extraction."""
        if self._stop_requested:
            return
        # A stable retry must retain this capture's selection and metadata,
        # including a manual page override of the previous router answer.
        self._last_routed_page = page
        self._last_route_score = score
        self._last_route_fields = fields
        sequence = self._upload_page(job_id, img, page, score, fields)
        if sequence is None:
            self._restart_stability(page)
            return
        self._pending_captures[(job_id, sequence)] = (self._visit_sequence, page)
        self._visit_pending = sequence
        self._visit_completed = False
        self._tracker.reset()

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
            # Riporta l'inquadratura sulla finestra applicativa: i prototipi del
            # router, la ROI del classificatore e le bande RETRY_AREAS della
            # pipeline sono tarati su screenshot di finestra, e su un frame a
            # schermo intero le stesse coordinate relative cadono su contenuto
            # diverso. (CONTENT_CROP invece non si applica piu' al percorso
            # live: ADR 0010.)
            full_size = img.size
            img, strategy = normalize_frame(
                img,
                mon,
                lambda: find_window_rect(getattr(self.config, "window_title_contains", "")),
            )
            self._announce_framing(strategy, full_size, img.size)
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

    def _announce_framing(
        self,
        strategy: str,
        full_size: Tuple[int, int],
        framed_size: Tuple[int, int],
    ) -> None:
        """Dichiara nel feed quale strategia ha inquadrato il frame.

        Una volta sola per strategia: a 3 FPS una riga per frame seppellirebbe il
        log. UNCHANGED e' l'unica che vale un avviso, perche' significa che al
        classificatore arriva un monitor intero mentre i prototipi sono
        screenshot di finestra, ed e' un fallimento che altrimenti si legge solo
        come pagina sbagliata con punteggio mediocre.
        """
        if strategy == self._last_framing_strategy:
            return
        self._last_framing_strategy = strategy

        w, h = full_size
        fw, fh = framed_size
        if strategy == UNCHANGED:
            self.tick.emit(
                f"⚠️ Inquadratura non normalizzata (unchanged): il frame resta {w}x{h}. "
                f"Nessuna finestra col titolo «{getattr(self.config, 'window_title_contains', '')}» "
                "e nessuno sfondo uniforme attorno: il riconoscimento pagina lavora "
                "fuori distribuzione e sbaglierà."
            )
        else:
            self.tick.emit(
                f"[Inquadratura] {strategy}: {w}x{h} → {fw}x{fh}"
            )

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

    def _try_local_first(self, img: Image.Image) -> Optional[Tuple[Optional[str], float, dict]]:
        """Modalita' local-first: decide in locale quando il margine lo consente.

        Ritorna None quando la decisione va passata al router, cioe' quando il
        classificatore locale non e' abbastanza sicuro. Ritorna una risposta quando:

        - il margine sul secondo classificato supera la soglia: la risposta locale e'
          separabile, e interrogare il router costerebbe una chiamata VLM (4-5s) per
          confermare qualcosa che gia' sappiamo;
        - il frame ha perso contro un prototipo di scarto: e' stato *riconosciuto* come
          non-pagina, non semplicemente non riconosciuto. Le classi di scarto esistono
          per rispondere a questo caso senza rete.

        Il margine, e non il punteggio, e' la grandezza giusta: misurato su fotogrammi
        tenuti fuori dall'addestramento, le risposte corrette portavano margini di un
        ordine di grandezza superiori a quelle sbagliate, mentre i punteggi assoluti si
        sovrapponevano. Vedi docs/adr/0008.

        Questa e' l'inversa di `hybrid`, che prova prima l'LLM e ripiega su ML: li' la
        rete si paga sempre.
        """
        if (self.config.router_mode or "").lower() != "local-first":
            return None
        if self.classifier is None or not hasattr(self.classifier, "classify_detailed"):
            return None

        try:
            res = self.classifier.classify_detailed(img)
        except Exception:  # noqa: BLE001 — il riconoscimento non deve fermare la cattura
            return None

        if res.rejected_by:
            if self._last_local_note != res.rejected_by:
                self.tick.emit(f"[ML] Scartata in locale ({res.rejected_by})")
                self._last_local_note = res.rejected_by
            return None, float(res.score), {}

        floor = float(getattr(self, "local_margin_min", 0.10))
        if res.label is not None and res.margin >= floor:
            resolved = self.registry.resolve(res.label)
            shown = resolved.name if resolved else res.label
            self.tick.emit(
                f"[ML] Riconosciuta in locale: «{shown}» "
                f"(score={res.score:.3f}, margine={res.margin:.3f})"
            )
            self._last_local_note = None
            return res.label, float(res.score), {}

        return None

    def _detect_page(self, img: Image.Image) -> Tuple[Optional[str], float, dict]:
        """Usa il router configurato per riconoscere la pagina e (se LLM) estrarre campi."""
        if self.router is None and self.classifier is None:
            return None, 0.0, {}

        local = self._try_local_first(img)
        if local is not None:
            return local

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
    ) -> Optional[int]:
        """Return the accepted capture sequence, or None when enqueue failed."""
        if page.order > 0:
            filename = f"{page.order:02d}-{page.slug}.png"
        else:
            filename = f"{page.slug}-{uuid.uuid4().hex}.png"

        if self.api_client and hasattr(self.api_client, "ingest_frame"):
            try:
                sequence = self.api_client.ingest_frame(
                    job_id=job_id,
                    img=img,
                    page_no=page.order,
                    page_type=page.name,
                    confidence=confidence,
                    fields_json=json.dumps(fields or {}),
                )
                self.tick.emit(f"📤 In coda per estrazione: {filename}")
                return sequence
            except Exception as exc:  # noqa: BLE001
                self.on_error(exc)
                return None

        self.tick.emit(f"[ERRORE] Client locale non configurato correttamente per {filename}")
        return None

    # ------------------------------------------------------------------ forza scatto manuale
    @QtCore.pyqtSlot(str)
    def force_capture(self, page_name: str) -> None:
        """Request a manual shot without touching camera or capture state."""
        if not self._stop_requested:
            self._commands.put(("manual", page_name))

    def _execute_manual_capture(self, page_name: str) -> None:
        """Process the UI request in the same thread as automatic capture."""
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

            raw = self._grab_raw()
            if raw is None or self._stop_requested:
                self.tick.emit("[BPER] Forza scatto: nessuno screenshot disponibile.")
                return
            self._observe_frame(raw)
            pending = (
                self._pending_captures.get((job_id, self._visit_pending))
                if self._visit_pending is not None else None
            )
            if pending is not None and pending[1].name == page.name:
                self.tick.emit(f"[BPER] «{page.name}» è già in elaborazione.")
                return
            # Seed the same frame reference used by automatic confirmation.
            # The first manual shot may precede any automatic routing attempt.
            self._is_duplicate_frame(raw)
            self._acquire(job_id, self._preprocess(raw), page, 0.0, {})
        except Exception as exc:  # noqa: BLE001
            self.on_error(exc)
