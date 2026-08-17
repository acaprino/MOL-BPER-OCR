"""Worker di cattura specifico per il flusso BPER."""

from __future__ import annotations

import io
import json
import re
import time
import uuid
from pathlib import Path
from typing import Optional, Set, Tuple, List, Dict, Any

import imagehash
from PIL import Image
from PyQt6 import QtCore
from llm_router import PageRouter, MLPageRouter, LLMPageRouter, RouterResult  # type: ignore

try:
    from page_classifier import BPERPagePrototypeClassifier  # type: ignore
except Exception:  # noqa: BLE001
    BPERPagePrototypeClassifier = None  # type: ignore

from .base_capture_worker import BaseCaptureWorker
from image_ops import preprocess_for_ocr, to_png8, to_webp_lossless

# Nota: l'ordine delle pagine viene caricato dinamicamente dall'Excel
# "Guida pagine ITA .xlsx" se presente; in fallback dall'ordine in prompts.json.
# Manteniamo una costante di riserva vuota.
PAGE_ORDER_FALLBACK: Dict[str, int] = {}

# Pagine catch-all che il router può restituire ma che non devono essere acquisite
_SKIP_PAGE_TYPES: frozenset = frozenset({"Altro / Non riconosciuto"})


class BPERCaptureWorker(BaseCaptureWorker):
    """
    Worker di cattura per l'applicativo BPER.

    Funzionalità:
        - cattura screenshot full-screen
        - dedup frame via pHash
        - riconoscimento pagina con BPERPagePrototypeClassifier (MobileNetV3 + prototipi)
        - logica di stabilità temporale
        - upload screenshot solo quando la pagina è stabile
        - stop automatico quando tutte le pagine previste sono acquisite
    """

    # secondi di stabilità richiesti perché una pagina sia considerata “ferma”
    STABILITY_SECONDS = 2.0

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

        # Stato di stabilità
        self._candidate_page_type: Optional[str] = None
        self._candidate_since: Optional[float] = None
        self._stability_log_sent: bool = False

        # Pagine già acquisite in questo job
        self.captured_page_types: Set[str] = set()

        # Sequenza attesa e mapping ordine pagina→indice
        self.page_sequence: List[str] = []
        self.page_order: Dict[str, int] = {}
        # Cache chiavi disponibili negli asset (basenames dei file .png/.jpg)
        self._available_page_keys: Set[str] = set()
        # Unione di chiavi valide (asset + nomi pagina in prompts.json)
        self._valid_page_keys: Set[str] = set()
        # Per evitare log ripetuti su riferimenti non risolvibili
        self._skipped_unknown_pages: Set[str] = set()
        # Nomi pagina definiti in prompts.json (per normalizzazione)
        self._prompts_page_names: Set[str] = set()

        # Inizializza routing (ML o LLM)
        self.classifier: Optional[Any] = None
        self.router: Optional[PageRouter] = None
        self._init_router()
        self._load_page_sequence()

        # Throttling routing su frame duplicati: ultimo tentativo eseguito
        self._last_route_attempt_ts: Optional[float] = None

        # Contatore errori di cattura consecutivi (auto-stop oltre soglia)
        self._consecutive_capture_errors: int = 0
        self._MAX_CONSECUTIVE_CAPTURE_ERRORS: int = 5

        # mss context singleton (creato una volta nel QThread, non in __init__)
        self._mss_ctx: Optional[Any] = None

        # Traccia l'ultima guidance "apri pagina X" emessa per non spammare
        self._last_guidance_page: Optional[str] = None

        # Ultimo errore router già loggato (per non ripeterlo a ogni frame)
        self._last_router_error: Optional[str] = None

    # ------------------------------------------------------------------ init classifier

    def _resolve_llm_settings(self) -> Tuple[str, str, str]:
        """
        Risolve (api_key, base_url, model) del router LLM in base al provider configurato.

        Con provider=gemini usa l'endpoint OpenAI-compatibile di Google e le chiavi
        GEMINI_API_KEY/GOOGLE_API_KEY/LLM_API_KEY; con openai la catena classica
        OPENAI_API_KEY/LLM_API_KEY. La api_key in config.ini, se presente, vince sempre.
        """
        import os

        provider = (self.config.llm_provider or "openai").lower()
        if provider == "gemini":
            api_key = (
                self.config.llm_api_key
                or os.getenv("GEMINI_API_KEY")
                or os.getenv("GOOGLE_API_KEY")
                or os.getenv("LLM_API_KEY", "")
            )
            base_url = self.config.llm_base_url or ""
            if not base_url or "api.openai.com" in base_url:
                base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
            model = self.config.llm_model or ""
            if not model or model.lower().startswith("gpt"):
                env_model = os.getenv("LLM_MODEL", "")
                model = env_model if env_model.lower().startswith("gemini") else "gemini-3.6-flash"
        else:
            api_key = (
                self.config.llm_api_key
                or os.getenv("OPENAI_API_KEY")
                or os.getenv("LLM_API_KEY", "")
            )
            base_url = self.config.llm_base_url or "https://api.openai.com/v1"
            model = self.config.llm_model
        return api_key, base_url, model

    def _init_router(self) -> None:
        """Inizializza il router pagina in base a config.router_mode."""
        try:
            # Struttura attesa:
            #   <root_edge_agent>/assets/templates/bper/...
            root = Path(__file__).resolve().parents[2]
            templates_dir = root / "assets" / "templates" / "bper"

            mode = (self.config.router_mode or "ml").lower()
            if mode == "llm":
                prompts_path = templates_dir / "prompts.json"
                api_key, base_url, model = self._resolve_llm_settings()
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
                api_key, base_url, model = self._resolve_llm_settings()
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
                        self.classifier = BPERPagePrototypeClassifier(
                            templates_dir=templates_dir,
                            crop_roi=(0.0, 0.12, 1.0, 0.30),
                            similarity_threshold=0.70,
                            device="cpu",
                        )
                    except Exception:
                        self.classifier = None
            else:
                # ML
                if BPERPagePrototypeClassifier is not None:
                    try:
                        self.classifier = BPERPagePrototypeClassifier(
                            templates_dir=templates_dir,
                            crop_roi=(0.0, 0.12, 1.0, 0.30),  # fascia alta (header + tab)
                            similarity_threshold=0.70,
                            device="cpu",
                        )
                    except Exception:
                        self.classifier = None
                self.router = MLPageRouter(templates_dir)
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

    def stop(self) -> None:
        """Override: ferma il loop e rilascia il contesto mss."""
        super().stop()
        if self._mss_ctx is not None:
            try:
                self._mss_ctx.close()
            except Exception:
                pass
            self._mss_ctx = None

    # ------------------------------------------------------------------ helpers UI
    @staticmethod
    def _friendly_name(page_key: str) -> str:
        """Converte una chiave tecnica di pagina in un nome leggibile per l'operatore.
        Es. '09.7_scheda_privati_base' → 'Scheda Privati Base'
        """
        import re as _re
        s = page_key.strip()
        # Rimuovi prefisso numerico tipo "09.7_" o "09.7 "
        s = _re.sub(r'^[0-9][0-9A-Za-z\.]*[_\s]+', '', s)
        # Sostituisci separatori con spazio
        s = s.replace('_', ' ').replace('-', ' ')
        # Riduci spazi multipli e title-case
        s = _re.sub(r'\s+', ' ', s).strip().title()
        return s or page_key

    def _next_pending_page(self) -> Optional[str]:
        """Ritorna il nome friendly della prossima pagina non ancora acquisita."""
        for name in self.page_sequence:
            if name not in self.captured_page_types:
                return self._friendly_name(name)
        # Se page_sequence è vuota, usa valid_page_keys meno captured
        remaining = self._valid_page_keys - self.captured_page_types
        if remaining:
            return self._friendly_name(next(iter(sorted(remaining))))
        return None

    # ------------------------------------------------------------------ page sequence
    def _load_page_sequence(self) -> None:
        """Carica la sequenza pagine dall'Excel; fallback a prompts.json."""
        try:
            root = Path(__file__).resolve().parents[2]
            bper_dir = root / "assets" / "templates" / "bper"
            xlsx_path = bper_dir / "Guida pagine ITA .xlsx"
            pages: List[str] = []
            prompts_page_names: Set[str] = set()

            # Prepara l'elenco delle chiavi disponibili dagli asset (basenames senza estensione)
            try:
                avail = set()
                for p in bper_dir.iterdir():
                    if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                        avail.add(p.stem.strip())
                self._available_page_keys = avail
            except Exception:
                self._available_page_keys = set()
            # 1) Excel
            if xlsx_path.exists():
                try:
                    from openpyxl import load_workbook  # type: ignore
                    wb = load_workbook(filename=str(xlsx_path), read_only=True)
                    ws = wb.active
                    # raccogli dalla prima colonna non vuota saltando la riga header
                    first_row = True
                    for row in ws.iter_rows(min_row=1, values_only=True):
                        if not row:
                            continue
                        name = (row[0] or "").strip() if isinstance(row[0], str) else row[0]
                        if first_row:
                            # salta header comune (es. "pagina"/"name")
                            first_row = False
                            # se sembra già una key valida conosciuta, non saltare
                            if name and isinstance(name, str) and name.isidentifier():
                                pages.append(name)
                            continue
                        if isinstance(name, str) and name:
                            pages.append(name)
                    wb.close()
                except Exception as exc:
                    self.on_error(exc)
            # 2) prompts.json (sempre letto per definire l'insieme di nomi validi)
            try:
                spec = json.loads((bper_dir / "prompts.json").read_text(encoding="utf-8"))
                for p in spec.get("pages", []):
                    name = p.get("name")
                    if isinstance(name, str) and name:
                        prompts_page_names.add(name.strip())

                # Se l'Excel non fornisce pagine, usa i nomi dal prompts come fallback
                if not pages:
                    pages = list(prompts_page_names)
            except Exception:
                pass

            # Memorizza in attributo per normalizzazione successiva
            self._prompts_page_names = set(prompts_page_names)

            # Limita la sequenza alle sole pagine presenti nel CSV fornito
            # Attivazione se:
            #  - config.required_pages_only = true
            #  - OPPURE è specificato un percorso CSV esistente
            #  - OPPURE esiste un file Nomenclatura.csv nella cartella bper
            csv_path_value = (getattr(self.config, "required_pages_csv", "") or "").strip()
            use_csv = False
            csv_path = None
            if csv_path_value:
                csv_path = Path(csv_path_value)
                if not csv_path.is_absolute():
                    candidate = bper_dir / csv_path
                    if candidate.exists():
                        csv_path = candidate
                use_csv = csv_path.exists()
            else:
                # Fallback: cerca Nomenclatura.csv nella cartella bper
                default_csv = bper_dir / "Nomenclatura.csv"
                if default_csv.exists():
                    csv_path = default_csv
                    use_csv = True
            if getattr(self.config, "required_pages_only", False) or use_csv:
                if csv_path and csv_path.exists():
                    try:
                        import csv
                        req_pages: List[str] = []
                        with csv_path.open("r", encoding="utf-8") as f:
                            reader = csv.DictReader(f)
                            # supporto anche a CSV senza header: fallback a prima colonna
                            if not reader.fieldnames:
                                # leggi grezzo
                                f.seek(0)
                                for line in f:
                                    part = (line.split(",", 1)[0] or "").strip()
                                    if part and part.lower() != "schermata":
                                        req_pages.append(part)
                            else:
                                # tollera varianti del nome colonna (case/whitespace)
                                field_schermata = None
                                for fn in reader.fieldnames:
                                    if fn.strip().lower() == "schermata":
                                        field_schermata = fn
                                        break
                                for row in reader:
                                    name = (row.get(field_schermata) or "").strip() if field_schermata else ""
                                    if name and name.lower() != "schermata":
                                        req_pages.append(name)
                        if req_pages:
                            pages = req_pages
                            self.tick.emit(f"[BPER] Sequenza limitata alle pagine richieste da CSV ({len(req_pages)} voci).")
                        else:
                            self.tick.emit("[BPER] CSV pagine richieste vuoto: nessuna voce caricata, uso sequenza standard.")
                    except Exception as exc:
                        self.on_error(exc)

            # Costruisci insieme chiavi valide: asset OR nomi da prompts.json
            self._valid_page_keys = set(self._available_page_keys) | set(prompts_page_names)

            self.page_sequence = pages
            self.page_order = {name: i + 1 for i, name in enumerate(self.page_sequence)}

            if self._valid_page_keys:
                total = len(self._valid_page_keys)
                self.tick.emit(f"─── Schermate da acquisire: {total} ───")
                for i, name in enumerate(sorted(self._valid_page_keys), 1):
                    self.tick.emit(f"  {i:2}. {self._friendly_name(name)}")
                self.tick.emit("──────────────────────────────────────")
                first = self._next_pending_page()
                if first:
                    self.tick.emit(f"→ Prima schermata da aprire nel sistema BPER: «{first}»")
            else:
                self.tick.emit("[BPER] Attenzione: nessuna pagina rilevata negli asset; funzionamento libero.")
        except Exception as exc:  # noqa: BLE001
            self.on_error(exc)
            self.page_sequence = []
            self.page_order = dict(PAGE_ORDER_FALLBACK)

    def _normalize_page_label(self, label: str) -> str:
        """
        Normalizza un'etichetta proveniente dall'Excel verso una chiave coerente con:
        - i basenames dei file in assets/templates/bper (preferito)
        - altrimenti la stringa pulita originale

        Regole:
        - strip
        - normalizza spazi multipli a singolo spazio
        - confronta case-insensitive con le chiavi disponibili
        - se non trovato, prova best-match via difflib
        - se esiste un prefisso numerico (es. "09.7_" o "09.7 "), usalo per matchare tra disponibili
        """
        try:
            import difflib

            s = re.sub(r"\s+", " ", label).strip()
            if not s:
                return s

            # Prepara insiemi di ricerca
            avail = set(self._available_page_keys)
            prompt_names = set(getattr(self, "_prompts_page_names", set()))
            union_names = avail | prompt_names

            # 1) match esatto sugli asset o sui nomi da prompts
            if s in union_names:
                return s

            # 2) match case-insensitive
            low_map = {k.lower(): k for k in union_names}
            if s.lower() in low_map:
                mapped = low_map[s.lower()]
                if mapped != s:
                    self.tick.emit(f"[BPER] Mappo Excel→asset: '{s}' → '{mapped}' (case-insensitive)")
                return mapped

            # 3) se c'è un prefisso numerico tipo 09.7_PEF... prova per prefisso
            m = re.match(r"^([0-9][0-9A-Za-z\.]*)", s)
            if m:
                pref = m.group(1)
                # normalizza separatori comuni
                candidates = [k for k in union_names if k.startswith(pref)]
                if candidates:
                    # scegli la più simile globalmente
                    best = difflib.get_close_matches(s, candidates, n=1, cutoff=0.0)
                    mapped = best[0] if best else candidates[0]
                    if mapped != s:
                        self.tick.emit(f"[BPER] Mappo Excel→asset per prefisso: '{s}' → '{mapped}'")
                    return mapped

            # 4) best-effort globale tra tutti gli asset
            if union_names:
                best = difflib.get_close_matches(s, list(union_names), n=1, cutoff=0.6)
                if best:
                    mapped = best[0]
                    if mapped != s:
                        self.tick.emit(f"[BPER] Mappo Excel→asset (similarità): '{s}' → '{mapped}'")
                    return mapped

            # 5) nessun mapping: ritorna la stringa pulita
            return s
        except Exception:
            return label

    # ------------------------------------------------------------------ core loop

    def _capture_once(self) -> None:
        """
        Loop di cattura per BPER:

            - legge job_id
            - cattura screenshot
            - dedup via pHash
            - riconosce pagina con ML
            - applica logica di stabilità
            - eventuale upload screenshot
        """
        job_id = self.job_id_getter()
        if not job_id:
            # Nessun job attivo: non fa nulla
            return

        # Cattura screenshot
        img = self._capture_screenshot()
        if img is None:
            return

        # Dedup basato su pHash con throttling: se frame duplicato, prova il routing
        # solo a intervalli regolari per evitare che un primo fallimento blocchi tutto.
        is_dup = self._is_duplicate_frame(img)
        if is_dup:
            now_ts = time.time()
            min_interval = float(getattr(self.config, "route_retry_seconds", 1.0) or 1.0)
            if self._last_route_attempt_ts is not None and (now_ts - self._last_route_attempt_ts) < min_interval:
                # Salta questo ciclo ma non bloccare per sempre: verrà ritentato dopo min_interval
                # (utile quando l'LLM non riconosce al primo colpo una schermata statica)
                return

        # Riconoscimento pagina tramite router (LLM/ML)
        self._last_route_attempt_ts = time.time()
        page_type, score, fields = self._detect_page(img)

        if page_type is None or page_type in _SKIP_PAGE_TYPES:
            # Nessuna pagina riconosciuta (o pagina catch-all) -> reset stabilità
            self._reset_stability()
            return

        # Gestione stabilità temporale
        now = time.time()
        if self._candidate_page_type != page_type:
            # Nuovo candidato
            self._candidate_page_type = page_type
            self._candidate_since = now
            self._stability_log_sent = False
            # Log discreto
            # self.tick.emit(f"[BPER-ML] rilevato: {page_type} (score={score:.3f})")
            return

        # Candidato invariato: verifichiamo da quanto tempo
        if self._candidate_since is None:
            self._candidate_since = now
            return

        elapsed = now - self._candidate_since
        if elapsed < self.STABILITY_SECONDS:
            if not self._stability_log_sent:
                friendly = self._friendly_name(page_type)
                self.tick.emit(
                    f"⏳ Rilevata «{friendly}» — mantieni aperta la schermata "
                    f"({self.STABILITY_SECONDS:.0f}s richiesti per la stabilità)"
                )
                self._stability_log_sent = True
            return

        # Scatto & upload
        friendly = self._friendly_name(page_type)
        n_captured = len(self.captured_page_types) + 1
        n_total = len(self._valid_page_keys) or "?"
        self._upload_page(job_id, img, page_type, score, fields)
        try:
            self._maybe_upload_dataset(job_id, img, page_type, score, fields)
        except Exception as exc:  # noqa: BLE001
            self.on_error(exc)
        self.captured_page_types.add(page_type)
        self._reset_stability()

        # Calcola prossima pagina pendente
        next_page = self._next_pending_page()
        if next_page:
            self.tick.emit(
                f"✅ «{friendly}» acquisita [{n_captured}/{n_total}] "
                f"→ apri nel sistema BPER: «{next_page}»"
            )
            self._last_guidance_page = next_page
        else:
            self.tick.emit(
                f"✅ «{friendly}» acquisita [{n_captured}/{n_total}] — tutte le schermate completate!"
            )

    # ------------------------------------------------------------------ screenshot & dedup

    def _capture_screenshot(self) -> Optional[Image.Image]:
        """
        Cattura screenshot del monitor configurato (mss – veloce e cross‑platform).

        Usa config.monitor_index (1..N). Se l'indice non esiste, ripiega su monitor 1.
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
            try:
                img = preprocess_for_ocr(
                    img,
                    scale=self.config.image_scale,
                    unsharp_amount=self.config.unsharp_amount,
                    unsharp_radius=self.config.unsharp_radius,
                    unsharp_threshold=self.config.unsharp_threshold,
                    contrast_stretch=True,
                )
            except Exception:
                pass
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
                self.tick.emit(
                    f"[Router] Riconosciuta: «{self._friendly_name(res.page_type)}» (score={res.confidence:.3f})"
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
                # Fallback a ML se disponibile (modalità hybrid)
                if self.classifier is not None:
                    label, score = self.classifier.classify(img)
                    if label is not None:
                        self.tick.emit(f"[ML] Riconosciuta via fallback: «{self._friendly_name(label)}» (score={score:.3f})")
                        return label, float(score or 0.0), {}
                return None, 0.0, {}

        # Fallback: solo ML classifier
        label, score = self.classifier.classify(img) if self.classifier else (None, 0.0)
        if label is not None:
            self.tick.emit(f"[ML] Riconosciuta: «{self._friendly_name(label)}» (score={score:.3f})")
        return label, float(score or 0.0), {}

    # ------------------------------------------------------------------ upload

    def _upload_page(self, job_id: str, img: Image.Image, page_type: str, confidence: float = 0.0,
                     fields: Optional[dict] = None) -> None:
        """
        Esegue l'upload dello screenshot per una pagina riconosciuta.
        """
        page_index = self.page_order.get(page_type, 0)

        if page_index > 0:
            filename = f"{page_index:02d}-{page_type}.png"
        else:
            # Per pagine extra o non ordinate
            filename = f"{page_type}-{uuid.uuid4().hex}.png"

        # Se abbiamo un api_client locale (lite), usiamolo direttamente
        if self.api_client and hasattr(self.api_client, "ingest_frame"):
            try:
                # Passiamo l'immagine PIL direttamente (LocalExtractionClient ora la accetta)
                self.api_client.ingest_frame(
                    job_id=job_id,
                    img=img,
                    page_no=page_index,
                    page_type=page_type,
                    confidence=confidence,
                    fields_json=json.dumps(fields or {})
                )
                self.tick.emit(f"✅ Elaborazione locale completata: {filename}")
                return
            except Exception as exc:
                self.on_error(exc)
                return

        # Rimossa logica di upload remoto (SaaS/Sauron) per consolidamento locale.
        self.tick.emit(f"[ERRORE] Client locale non configurato correttamente per {filename}")

    def _maybe_upload_dataset(self, job_id: str, img: Image.Image, page_type: str, score: float, fields: dict) -> None:
        """Logica di salvataggio dataset (disabilitata per consolidamento locale)."""
        return

    # ------------------------------------------------------------------ helpers stabilità

    def _reset_stability(self) -> None:
        self._candidate_page_type = None
        self._candidate_since = None
        self._stability_log_sent = False

    # ------------------------------------------------------------------ forza scatto manuale
    @QtCore.pyqtSlot(str)
    def force_capture(self, page_name: str) -> None:
        """
        Forza lo scatto e l'upload dell'immagine corrente come se fosse la pagina indicata.

        Usa la normalizzazione per mappare il nome passato a una chiave valida.
        Non richiede stabilità né match del router. Aggiunge la pagina a `captured_page_types`.
        """
        try:
            job_id = self.job_id_getter()
            if not job_id:
                self.tick.emit("[BPER] Forza scatto: nessun job attivo.")
                return

            img = self._capture_screenshot()
            if img is None:
                self.tick.emit("[BPER] Forza scatto: nessuno screenshot disponibile.")
                return

            key = self._normalize_page_label(page_name or "").strip()
            if not key:
                self.tick.emit(f"[BPER] Forza scatto: nome pagina vuoto/non valido ('{page_name}').")
                return

            # Verifica che la pagina sia tra quelle riconosciute (asset/prompts)
            if self._valid_page_keys and key not in self._valid_page_keys:
                self.tick.emit(f"[BPER] Forza scatto: pagina non presente negli asset/prompts: '{key}'.")
                return

            # Esegue upload con conf=0 e senza fields
            self._upload_page(job_id, img, key, 0.0, {})
            try:
                self._maybe_upload_dataset(job_id, img, key, 0.0, {})
            except Exception as exc:  # noqa: BLE001
                self.on_error(exc)
            self.captured_page_types.add(key)
            self._reset_stability()
            self.tick.emit(f"[BPER] Forza scatto completato per '{key}'.")
        except Exception as exc:  # noqa: BLE001
            self.on_error(exc)
