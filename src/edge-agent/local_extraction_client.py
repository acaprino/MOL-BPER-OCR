"""LocalExtractionClient — bridges BPERCaptureWorker to ExtractionPipeline."""

from __future__ import annotations

import os
import sys
import threading
import uuid
from typing import Any, Dict, List, Optional
from PIL import Image

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
from prompt_store import catalog_source

from extraction_pool import DaemonThreadPool


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

    # ------------------------------------------------------------------ APIClient-compatible interface

    def start_job(self) -> str:
        """Generate a new local job ID."""
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

    def get_all_job_ids(self) -> List[str]:
        with self._lock:
            return list(self._results.keys())
