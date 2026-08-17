"""LocalExtractionClient — bridges BPERCaptureWorker to ExtractionPipeline."""

from __future__ import annotations

import csv
import io
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

_PROJECT_ROOT = str(app_paths.project_root())
if not app_paths.is_frozen() and _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(app_paths.env_file())
except Exception:
    pass

from extraction.llm_factory import create_chat_model
from extraction.pipeline import ExtractionPipeline
from extraction.config import LLM_PROVIDER, LLM_MODEL, LLM_MODEL_ANCHOR, PARALLEL_WORKERS
from extraction.normalization import escape_csv_formula

from extraction_pool import DaemonThreadPool


class LocalExtractionClient(QtCore.QObject):
    """
    Local extraction client implementing the ingest_frame() interface
    expected by BPERCaptureWorker.

    Uses ExtractionPipeline to process each captured frame locally,
    stores results in memory, and emits result_ready when done.
    Compatible surface: start_job(), ingest_frame(), requeue_job(), export_csv().
    """

    result_ready = QtCore.pyqtSignal(str, dict)   # (job_id, result)
    frame_queued = QtCore.pyqtSignal(str, str)    # (job_id, page_type)

    def __init__(
        self,
        parent: Optional[QtCore.QObject] = None,
        pipeline: Optional[ExtractionPipeline] = None,
    ) -> None:
        super().__init__(parent)

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
        # BatchRunner (extraction/cli.py): one pipeline, N worker threads.
        self._pool = DaemonThreadPool(max_workers=max(1, int(PARALLEL_WORKERS)))

        self._results: Dict[str, List[Dict[str, Any]]] = {}
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
    ) -> None:
        """Enqueue a frame for background extraction and return immediately.

        Called from the capture QThread; extraction runs on the internal
        daemon pool so the capture loop is never blocked.
        """
        self.frame_queued.emit(job_id, page_type)
        self._pool.submit(
            self._process_frame, job_id, img, page_no, page_type, confidence, fields_json
        )

    def _process_frame(
        self,
        job_id: str,
        img: Image.Image,
        page_no: int,
        page_type: str,
        confidence: float,
        fields_json: str,
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

        with self._lock:
            self._results.setdefault(job_id, []).append(result)

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
        self._pool.stop()

    def export_csv(self, job_id: str, schema: str = "flat") -> Optional[str]:
        """Export extraction results for a job as CSV text."""
        results = self.get_results(job_id)
        if not results:
            return None

        # Collect union of all field keys across results
        all_field_keys: List[str] = []
        for r in results:
            for k in (r.get("fields") or {}).keys():
                if k not in all_field_keys:
                    all_field_keys.append(k)

        header = (
            ["screen_id", "_page_type", "_status"]
            + [f"{k}_value" for k in all_field_keys]
            + [f"{k}_conf" for k in all_field_keys]
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(header)
        for r in results:
            fields = r.get("fields") or {}
            row = (
                [r.get("screen_id", ""), r.get("_page_type", ""), r.get("_status", "")]
                + [(fields.get(k) or {}).get("value", "") for k in all_field_keys]
                + [(fields.get(k) or {}).get("confidence", "") for k in all_field_keys]
            )
            # Neutralize CSV/formula injection on untrusted OCR values
            writer.writerow([escape_csv_formula(c) for c in row])

        return output.getvalue()

    # ------------------------------------------------------------------ Data access

    def get_results(self, job_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._results.get(job_id, []))

    def get_all_job_ids(self) -> List[str]:
        with self._lock:
            return list(self._results.keys())
