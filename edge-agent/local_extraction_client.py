"""LocalExtractionClient — bridges BPERCaptureWorker to ExtractionPipeline."""

from __future__ import annotations

import csv
import io
import os
import sys
import tempfile
import threading
import uuid
from typing import Any, Dict, List, Optional

from PyQt6 import QtCore

# Add project root to sys.path so extraction package is importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
except Exception:
    pass

from extraction.llm_factory import create_chat_model
from extraction.pipeline import ExtractionPipeline
from extraction.config import LLM_MODEL, LLM_MODEL_ANCHOR


class LocalExtractionClient(QtCore.QObject):
    """
    Local extraction client implementing the ingest_frame() interface
    expected by BPERCaptureWorker.

    Uses ExtractionPipeline to process each captured frame locally,
    stores results in memory, and emits result_ready when done.
    Compatible surface: start_job(), ingest_frame(), requeue_job(), export_csv().
    """

    result_ready = QtCore.pyqtSignal(str, dict)  # (job_id, result)

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)

        main_model = create_chat_model()
        anchor_model = create_chat_model(model_override=LLM_MODEL_ANCHOR)
        self._pipeline = ExtractionPipeline(
            main_model=main_model,
            anchor_model=anchor_model,
            main_model_name=LLM_MODEL,
            anchor_model_name=LLM_MODEL_ANCHOR,
        )

        self._results: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ APIClient-compatible interface

    def start_job(self) -> str:
        """Generate a new local job ID."""
        return str(uuid.uuid4())

    def ingest_frame(
        self,
        job_id: str,
        image_bytes: bytes,
        page_no: int = 0,
        page_type: str = "",
        confidence: float = 0.0,
        fields_json: str = "{}",
    ) -> None:
        """
        Process an image through ExtractionPipeline and store the result.

        Called synchronously from BPERCaptureWorker._upload_page().
        Runs extraction in the caller's thread (capture QThread).
        """
        # Save to temp file — pipeline works on file paths
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(image_bytes)
            tmp_path = f.name

        try:
            result = self._pipeline.extract_from_screen(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        result["_page_type"] = page_type
        result["_page_no"] = page_no
        result["_page_confidence"] = confidence

        with self._lock:
            if job_id not in self._results:
                self._results[job_id] = []
            self._results[job_id].append(result)

        # Qt signal is thread-safe across QThread boundaries
        self.result_ready.emit(job_id, dict(result))

    def requeue_job(self, job_id: str) -> bool:
        """No-op stub for local mode."""
        return True

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
            writer.writerow(row)

        return output.getvalue()

    # ------------------------------------------------------------------ Data access

    def get_results(self, job_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._results.get(job_id, []))

    def get_all_job_ids(self) -> List[str]:
        with self._lock:
            return list(self._results.keys())
