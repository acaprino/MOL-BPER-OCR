"""LocalExtractionClient — bridges BPERCaptureWorker to ExtractionPipeline."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple
from PIL import Image
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from PyQt6 import QtCore

# Add project root to sys.path so extraction package is importable
# (solo da sorgente: nel bundle il package è già nell'archivio PyInstaller)
import app_paths

_SRC_DIR = str(app_paths.src_dir())
if not app_paths.is_frozen() and _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(app_paths.env_file())
except Exception:
    pass

from extraction.llm_factory import create_chat_model
from extraction.pipeline import ExtractionPipeline
from extraction.config import LLM_PROVIDER, LLM_MODEL, LLM_MODEL_ANCHOR, PARALLEL_WORKERS
from extraction.fields import FIELD_KEYS
from extraction.normalization import normalize_ndg
from prompt_store import catalog_source

from excel_export import export_results
from extraction_pool import DaemonThreadPool
from practice_consolidation import CORRECTABLE_KEYS, PracticeRecord, consolidate, has_content

# Excel refuses cells longer than this, so a pasted text is cut here.
MAX_CORRECTION_LENGTH = 32767


# ============================================================
# Diagnostics
# ============================================================


def _log_extraction(job_id: str, result: Dict[str, Any]) -> None:
    """Print the per-frame diagnostics to stdout.

    In the windowed bundle stdout is edge-agent.log (edge_agent.py:15-25). This
    is the only place confidence, cost and field provenance survive now that the
    diagnostic tab is gone: the UI shows business data only.
    """
    meta = result.get("_meta_agg") or {}
    sources = result.get("_field_sources") or {}

    print(
        f"[EXTRACT] job={job_id} screen={result.get('screen_id')!r} "
        f"page={result.get('_page_type')!r} status={result.get('_status')} "
        f"calls={meta.get('calls', 0)} tokens={meta.get('total_tokens', 0)} "
        f"cost=${float(meta.get('estimated_cost_usd', 0.0) or 0.0):.6f} "
        f"latency={meta.get('latency_ms', 0)}ms"
    )

    error = result.get("_error")
    if error:
        print(f"[EXTRACT]   error: {error}")

    for key, payload in (result.get("fields") or {}).items():
        if not isinstance(payload, dict):
            continue
        value = payload.get("value")
        if value is None or str(value).strip() == "":
            continue
        confidence = payload.get("confidence") or 0.0
        print(
            f"[EXTRACT]   {key}={value!r} conf={float(confidence):.2f} "
            f"src={sources.get(key, '?')}"
        )


# ============================================================
# Operator corrections
# ============================================================


def clean_correction(value: Optional[str]) -> Optional[str]:
    """Text the operator typed, made safe for the workbook; empty means cleared."""
    if value is None:
        return None
    text = ILLEGAL_CHARACTERS_RE.sub("", str(value)).strip()[:MAX_CORRECTION_LENGTH]
    return text or None


def _fingerprint(records: Sequence[PracticeRecord]) -> Optional[str]:
    """Hash of the exportable content, or None when there is nothing to export.

    An error-only session consolidates to one empty record: it has no content, so
    closing the app must not ask the operator to export it.
    """
    rows = [
        (record.ndg, [(key, record.fields[key]["value"]) for key in FIELD_KEYS])
        for record in records
    ]
    if not any(has_content(record) for record in records):
        return None
    return hashlib.sha1(json.dumps(rows, default=str, ensure_ascii=False).encode()).hexdigest()


class LocalExtractionClient(QtCore.QObject):
    """
    Local extraction client implementing the ingest_frame() interface
    expected by BPERCaptureWorker.

    Uses ExtractionPipeline to process each captured frame locally,
    stores results in memory, and emits result_ready when done.
    Compatible surface: start_job(), ingest_frame(), requeue_job(),
    get_results(), frame_queued (signal), shutdown(), pending_extractions().
    """

    result_ready = QtCore.pyqtSignal(str, dict)   # (job_id, result)
    frame_queued = QtCore.pyqtSignal(str, str)    # (job_id, page_type)

    def __init__(
        self,
        parent: Optional[QtCore.QObject] = None,
        pipeline: Optional[ExtractionPipeline] = None,
    ) -> None:
        super().__init__(parent)

        # Which prompt catalog is live: without this line a redirected or
        # tampered prompts/ folder leaves no trace in edge-agent.log.
        print(f"[PROMPTS] catalog loaded from {catalog_source()}")

        if pipeline is None:
            main_model = create_chat_model(LLM_PROVIDER, model=LLM_MODEL)
            anchor_model = create_chat_model(LLM_PROVIDER, model=LLM_MODEL_ANCHOR)
            pipeline = ExtractionPipeline(
                main_model=main_model,
                anchor_model=anchor_model,
                main_model_name=LLM_MODEL,
                anchor_model_name=LLM_MODEL_ANCHOR,
            )
        self._pipeline = pipeline

        # Extraction runs on a daemon pool; the shared-pipeline pattern matches
        # BatchRunner (src/extraction/cli.py): one pipeline, N worker threads.
        self._pool = DaemonThreadPool(max_workers=max(1, int(PARALLEL_WORKERS)))

        self._results: Dict[str, List[Dict[str, Any]]] = {}
        self._completed: Dict[str, Dict[int, Dict[str, Any]]] = {}
        self._next_capture_sequence: Dict[str, int] = {}
        self._lock = threading.Lock()

        # Operator state, in memory only like the results (no customer data on disk):
        # {job: {normalized NDG: {schema_key: value}}}, renamed column labels shared by
        # every export, the start (ordinal, time) of each session and the fingerprint
        # of what each session last exported.
        self._corrections: Dict[str, Dict[str, Dict[str, Optional[str]]]] = {}
        self._column_labels: Dict[str, str] = {}
        self._started: Dict[str, Tuple[int, datetime]] = {}
        self._exported: Dict[str, Optional[str]] = {}

    # ------------------------------------------------------------------ APIClient-compatible interface

    def _register_job_locked(self, job_id: str) -> None:
        self._started.setdefault(job_id, (len(self._started) + 1, datetime.now()))

    def start_job(self) -> str:
        """Generate a new local job ID.

        The session number is assigned with its first frame, so a start/stop with no
        frame in between does not leave a gap in "Sessione 1, 2, ...".
        """
        return str(uuid.uuid4())

    def ingest_frame(
        self,
        job_id: str,
        img: Image.Image,
        page_no: int = 0,
        page_type: str = "",
        confidence: float = 0.0,
        fields_json: str = "{}",
    ) -> int:
        """Enqueue a frame and return its zero-based capture sequence for the job.

        Called from the capture QThread; extraction runs on the internal
        daemon pool so the capture loop never waits for extraction. A stopped
        pool raises RuntimeError without emitting frame_queued.
        """
        # Reserve only accepted slots. A fast completion waits for this lock,
        # so it cannot publish before the sequence has been committed.
        with self._lock:
            self._register_job_locked(job_id)
            sequence = self._next_capture_sequence.get(job_id, 0)
            accepted = self._pool.submit(
                self._process_frame, job_id, img, page_no, page_type,
                confidence, fields_json, sequence,
            )
            if not accepted:
                raise RuntimeError("Extraction pool has stopped accepting frames")
            self._next_capture_sequence[job_id] = sequence + 1

        self.frame_queued.emit(job_id, page_type)
        return sequence

    def _process_frame(
        self,
        job_id: str,
        img: Image.Image,
        page_no: int,
        page_type: str,
        confidence: float,
        fields_json: str,
        capture_sequence: int,
    ) -> None:
        """Pool worker: run the pipeline and publish the result."""
        screen_id = page_type if page_type else f"pagina {page_no}"

        try:
            # extract_from_image (not extract_from_screen): the Edge Agent has
            # already pre-processed the image, normalize_image would be redundant.
            result = self._pipeline.extract_from_image(img, screen_id)
        except Exception as e:  # noqa: BLE001
            result = {
                "screen_id": screen_id,
                "fields": {},
                "_status": "ERROR",
                "_error": str(e),
            }

        result["_page_type"] = page_type
        result["_page_no"] = page_no
        result["_page_confidence"] = confidence
        result["_capture_sequence"] = capture_sequence

        try:
            _log_extraction(job_id, result)
        except Exception as exc:  # noqa: BLE001
            # Diagnostics must not leave a missing slot that blocks later results.
            result["_diagnostic_error"] = str(exc)

        with self._lock:
            completed = self._completed.setdefault(job_id, {})
            completed[capture_sequence] = result
            published = self._results.setdefault(job_id, [])
            # An anonymous frame belongs to the preceding captured practice.
            # Sorting only finished frames could temporarily attach it to an
            # earlier practice while the intervening identifier is still running.
            while len(published) in completed:
                published.append(completed.pop(len(published)))

        # Qt signal is thread-safe across thread boundaries
        self.result_ready.emit(job_id, dict(result))

    def requeue_job(self, job_id: str) -> bool:
        """No-op stub for local mode."""
        return True

    def pending_extractions(self) -> int:
        """Number of queued frames not yet being processed."""
        return self._pool.pending()

    def frames_in_progress(self) -> int:
        """Frames accepted whose result is not exportable yet.

        Unlike pending_extractions() this includes the frames a worker already picked
        up, and the finished ones still waiting for an earlier frame to be published:
        closing the window now would lose all of them.
        """
        with self._lock:
            return sum(
                accepted - len(self._results.get(job_id, []))
                for job_id, accepted in self._next_capture_sequence.items()
            )

    def shutdown(self) -> None:
        """Stop the pool: queued frames are discarded; running tasks cannot
        block process exit (daemon threads)."""
        with self._lock:
            self._pool.stop()

    # ------------------------------------------------------------------ Data access

    def get_results(self, job_id: str) -> List[Dict[str, Any]]:
        """Return the completed prefix in capture order, including error slots."""
        with self._lock:
            return list(self._results.get(job_id, []))

    def practice_count(self, job_id: str) -> int:
        """Practices with at least one value, corrections included: what an export would write."""
        with self._lock:
            results = list(self._results.get(job_id, []))
            corrections = self._corrections_locked(job_id)
        return sum(1 for record in consolidate(results, corrections) if has_content(record))

    def get_all_job_ids(self) -> List[str]:
        with self._lock:
            return list(self._results.keys())

    # ------------------------------------------------------------------ Sessions, corrections, export

    def session_label(self, job_id: str) -> str:
        """Readable name of a session, e.g. "Sessione 2 · 10:42"."""
        with self._lock:
            started = self._started.get(job_id)
        if started is None:
            return f"Sessione {job_id[:8]}"
        ordinal, at = started
        return f"Sessione {ordinal} · {at:%H:%M}"

    def set_correction(self, job_id: str, ndg: str, schema_key: str, value: Optional[str]) -> None:
        """Record the operator's value for one field of one practice (None = cleared)."""
        key = normalize_ndg(ndg)
        if key is None:
            raise ValueError(f"NDG non leggibile: {ndg!r}")
        if schema_key not in CORRECTABLE_KEYS:
            raise ValueError(f"Il campo {schema_key!r} non è correggibile")
        cleaned = clean_correction(value)
        with self._lock:
            self._corrections.setdefault(job_id, {}).setdefault(key, {})[schema_key] = cleaned

    def clear_correction(self, job_id: str, ndg: str, schema_key: str) -> None:
        """Drop one correction, restoring the extracted value."""
        key = normalize_ndg(ndg)
        with self._lock:
            by_ndg = self._corrections.get(job_id, {})
            fields = by_ndg.get(key or "", {})
            fields.pop(schema_key, None)
            if not fields:
                by_ndg.pop(key or "", None)
            if not by_ndg:
                self._corrections.pop(job_id, None)

    def get_corrections(self, job_id: str) -> Dict[str, Dict[str, Optional[str]]]:
        with self._lock:
            return self._corrections_locked(job_id)

    def _corrections_locked(self, job_id: str) -> Dict[str, Dict[str, Optional[str]]]:
        return {ndg: dict(fields) for ndg, fields in self._corrections.get(job_id, {}).items()}

    def get_column_labels(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._column_labels)

    def set_column_label(self, schema_key: str, label: str) -> None:
        """Rename a column for every export (an empty label restores the canonical name)."""
        if schema_key not in FIELD_KEYS:
            raise ValueError(f"Colonna sconosciuta: {schema_key!r}")
        cleaned = clean_correction(label)
        with self._lock:
            if cleaned:
                self._column_labels[schema_key] = cleaned
            else:
                self._column_labels.pop(schema_key, None)

    def export_workbook(self, job_id: str, path: str) -> int:
        """The only export path: corrections and shared labels included.

        Exports from one snapshot and remembers *its* fingerprint, so a result that
        lands mid-export keeps the session marked as not exported.
        """
        with self._lock:
            results = list(self._results.get(job_id, []))
            corrections = self._corrections_locked(job_id)
            labels = dict(self._column_labels)
        written = export_results(results, path, labels=labels, corrections=corrections)
        fingerprint = _fingerprint(consolidate(results, corrections))
        with self._lock:
            self._exported[job_id] = fingerprint
        return written

    def unexported_jobs(self) -> List[str]:
        """Sessions whose exportable content differs from their last export."""
        with self._lock:
            snapshot = [
                (job_id, list(results), self._corrections_locked(job_id), self._exported.get(job_id))
                for job_id, results in self._results.items()
            ]
        pending = []
        for job_id, results, corrections, exported in snapshot:
            fingerprint = _fingerprint(consolidate(results, corrections))
            if fingerprint is not None and fingerprint != exported:
                pending.append(job_id)
        return pending
