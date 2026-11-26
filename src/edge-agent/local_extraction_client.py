"""LocalExtractionClient — bridges BPERCaptureWorker to ExtractionPipeline."""

from __future__ import annotations

import hashlib
import json
import math
import sys
import threading
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
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

from extraction.config import PARALLEL_WORKERS
from extraction.fields import FIELD_KEYS
from extraction.normalization import safe_field
from prompt_store import catalog_source

from excel_export import build_columns, write_workbook
from extraction_pool import DaemonThreadPool
from extraction_service import ExtractionService, ImageReader, worker_limit
from practice_consolidation import CORRECTABLE_KEYS, PracticeEngine, PracticeRecord, correction_key, has_content
from session_frames import encode_pixels, json_bytes, pack_pending, pending_metadata, unpack_pending
from work_queue import QueueSnapshot, WorkQueue

# Excel refuses cells longer than this, so a pasted text is cut here.
MAX_CORRECTION_LENGTH = 32767


def _checked_result(result: dict) -> dict:
    """Reject unusable field payloads before they can enter the ordered merge."""
    fields = result.get("fields") or {}
    try:
        if not isinstance(fields, dict):
            raise ValueError("Formato dei campi non valido.")
        for key in fields.keys() & FIELD_KEYS:
            if not math.isfinite(safe_field(fields, key)["confidence"]):
                raise ValueError("Confidenza del campo non valida.")
    except (TypeError, ValueError, OverflowError) as exc:
        return {**result, "fields": {}, "_status": "ERROR", "_error": str(exc)}
    return result


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
        print("[EXTRACT]   extraction failed")

    for key, payload in (result.get("fields") or {}).items():
        if not isinstance(payload, dict):
            continue
        value = payload.get("value")
        if value is None or str(value).strip() == "":
            continue
        confidence = payload.get("confidence") or 0.0
        print(
            f"[EXTRACT]   {key} present conf={float(confidence):.2f} "
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


def _fingerprint(records: Sequence[PracticeRecord], labels: Dict[str, str]) -> Optional[str]:
    """Hash of the exportable content, or None when there is nothing to export.

    An error-only session consolidates to one empty record: it has no content, so
    closing the app must not ask the operator to export it.
    """
    rows = [
        (record.edit_key, [(key, record.fields[key]["value"]) for key in FIELD_KEYS])
        for record in records
    ]
    if not any(has_content(record) for record in records):
        return None
    return hashlib.sha256(json_bytes([rows, sorted(labels.items())])).hexdigest()


class LocalExtractionClient(QtCore.QObject):
    """
    Local extraction client implementing the ingest_frame() interface
    expected by BPERCaptureWorker.

    Runs extraction on the local pool and emits result_ready when done.
    The desktop provides a recovery directory for all accepted work.
    Compatible surface: start_job(), ingest_frame(), requeue_job(),
    get_results(), frame_queued (signal), shutdown(), pending_extractions().
    """

    tracks_practice_selection = True
    result_ready = QtCore.pyqtSignal(str, dict)   # (job_id, result)
    practices_updated = QtCore.pyqtSignal(str)    # consolidated snapshot available
    frame_finished = QtCore.pyqtSignal(str, str, str)  # session, page, status
    frame_queued = QtCore.pyqtSignal(str, str)    # (job_id, page_type)
    recovery_error = QtCore.pyqtSignal(str)
    history_warning = QtCore.pyqtSignal(str)

    def __init__(
        self,
        parent: Optional[QtCore.QObject] = None,
        pipeline: Optional[ImageReader] = None,
        *,
        recovery_dir: Optional[Path] = None,
        export_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self._export_only = export_only
        if export_only and recovery_dir is None:
            raise ValueError("L'esportazione di recupero richiede un archivio esistente.")

        # Which prompt catalog is live: without this line a redirected or
        # tampered prompts/ folder leaves no trace in edge-agent.log.
        if not export_only:
            print(f"[PROMPTS] catalog loaded from {catalog_source()}")

        self._service = None
        self._pool = None
        self._queue = WorkQueue()
        self._worker_limit = 0
        if not export_only:
            limit = worker_limit(PARALLEL_WORKERS)
            self._worker_limit = limit
            if pipeline is None:
                self._service = ExtractionService(limit)
                pipeline = self._service
            self._pool = DaemonThreadPool(max_workers=limit)
        self._pipeline = pipeline

        self._results: Dict[str, List[Dict[str, Any]]] = {}
        self._engines: dict[str, PracticeEngine] = defaultdict(PracticeEngine)
        self._records: dict[str, tuple[PracticeRecord, ...]] = {}
        self._completed: Dict[str, Dict[int, Dict[str, Any]]] = {}
        self._next_capture_sequence: Dict[str, int] = {}
        # Last accepted visit, never the practice displayed by the GUI.
        self._capture_contexts: dict[str, tuple[int | None, str]] = {}
        self._lock = threading.Lock()

        # In-memory views of the committed session data.
        # {job: {normalized NDG: {schema_key: value}}}, renamed column labels shared by
        # every export, the start (ordinal, time) of each session and the fingerprint
        # of what each session last exported.
        self._corrections: Dict[str, Dict[str, Dict[str, Optional[str]]]] = {}
        self._column_labels: Dict[str, str] = {}
        self._started: Dict[str, Tuple[int, datetime]] = {}
        self._exported: Dict[str, Optional[str]] = {}
        self._drafts: dict[str, dict[str, str]] = {}
        self._navigation: dict[str, list[dict]] = {}
        self._writer = threading.RLock()
        self._closed = False
        self._store = None
        self._history = None
        self.has_recovery = recovery_dir is not None
        self.recovered_jobs: tuple[str, ...] = ()
        self.recovered_from_backup = False
        self.recovery_problem = ""
        self.history_problem = ""
        if recovery_dir is not None:
            from recovery_history import RecoveryHistory
            from recovery_store import RecoveryStore
            try:
                self._store = RecoveryStore(recovery_dir, backup_directory=app_paths.backup_dir(),
                                            create=not export_only)
                self.recovered_from_backup = self._store.recovered_from_backup
                if not export_only:
                    self._history = RecoveryHistory(
                        self._store.primary_path, self._store.replica_directory,
                        on_error=self._report_history_warning,
                    )
                self._recover_sessions()
            except Exception as exc:
                self.shutdown()
                raise OSError(f"Archivio delle sessioni non disponibile. {exc}") from exc

    def _recover_sessions(self) -> None:
        """Load ordered results and defer pending image decoding to the pool."""
        pending = []
        slots: dict[str, set[int]] = defaultdict(set)
        recovered: dict[str, dict[int, dict]] = defaultdict(dict)
        captures: dict[tuple[str, int], tuple[str, str, int | None, str | None]] = {}
        for key in self._store.keys():
            data = self._store.read(key)
            if key == "labels":
                self._column_labels = json.loads(data)
                continue
            kind, job, *tail = key.split("/")
            if kind == "session":
                ordinal, timestamp = json.loads(data)
                self._started[job] = ordinal, datetime.fromisoformat(timestamp)
            elif kind == "edits":
                edits = json.loads(data)
                self._corrections[job] = edits["corrections"]
                if edits.get("draft") is not None:
                    self._drafts[job] = edits["draft"]
            elif kind == "export":
                self._exported[job] = json.loads(data)
            elif kind == "navigation":
                self._navigation[job] = json.loads(data)
            elif kind == "frame":
                sequence = int(tail[0])
                slots[job].add(sequence)
                if data.startswith(b"P1\n"):
                    pending.append((job, sequence))
                    number, page, _, view, context, practice = pending_metadata(data)
                    page = page or f"pagina {number}"
                elif data.startswith(b"R1\n"):
                    result = json.loads(data[3:])
                    if result["_capture_sequence"] != sequence:
                        raise ValueError("Progressivo del risultato incoerente.")
                    recovered[job][sequence] = _checked_result(result)
                    page = result.get("_page_type") or result.get("screen_id") or "Schermata"
                    view = result.get("_practice_view", "")
                    context, practice = result.get("_capture_context"), result.get("_capture_practice")
                else:
                    raise ValueError("Formato del fotogramma non riconosciuto.")
                captures[job, sequence] = page, view, context, practice
            else:
                raise ValueError("Versione dell'archivio delle sessioni non riconosciuta.")
        for job in sorted(slots, key=lambda item: self._started.get(item, (0,))[0]):
            sequences = slots[job]
            if job not in self._started or sequences != set(range(len(sequences))):
                raise ValueError("Sequenza di catture incompleta.")
            self._next_capture_sequence[job] = len(sequences)
            label = self.session_label(job)
            for sequence in range(len(sequences)):
                page, view, context, practice = captures[job, sequence]
                self._queue.accept(job, sequence, label, page, context, practice)
                self._capture_contexts[job] = context, view
            self._publish_completed(job, recovered[job])
        self.recovered_jobs = tuple(job for job in sorted(slots, key=self._started.__getitem__))
        if self._pool is not None:
            for job, sequence in sorted(pending):
                self._pool.submit(self._resume_frame, job, sequence)

    def pending_capture_sequences(self, job: str) -> tuple[int, ...]:
        """Slots without a result, excluding completed results held behind a gap."""
        with self._lock:
            prefix = len(self._results.get(job, []))
            completed = self._completed.get(job, {})
            return tuple(slot for slot in range(prefix, self._next_capture_sequence.get(job, 0))
                         if slot not in completed)

    def _resume_frame(self, job: str, sequence: int) -> None:
        self._queue_state(job, sequence, "preparing")
        try:
            with self._writer:
                if self._closed:
                    return
                data = self._store.read(f"frame/{job}/{sequence}")
            image, page_no, page, confidence, view, context, practice = unpack_pending(data)
        except Exception as exc:
            self._queue_state(job, sequence, "storage_error")
            self._report_recovery_failure(exc)
            return
        self._process_frame(job, image, page_no, page, confidence, "{}", sequence, view, context, practice)

    def _report_recovery_failure(self, exc: Exception) -> None:
        with self._writer:
            if self.recovery_problem:
                return
            self.recovery_problem = f"Archivio di recupero non disponibile. Verifica spazio e accesso, poi riapri l’agent. {type(exc).__name__}"
        self.recovery_error.emit(self.recovery_problem)

    def _report_history_warning(self, message: str) -> None:
        with self._writer:
            if self._closed:
                return
            self.history_problem = message
        self.history_warning.emit(message)

    def _write(self, key: str, data: bytes) -> None:
        if self._export_only:
            raise RuntimeError("L'archivio è aperto per la sola esportazione.")
        if self._closed:
            raise RuntimeError("Extraction pool has stopped accepting frames")
        if self._store is None:
            return
        if self.recovery_problem:
            raise OSError(self.recovery_problem)
        try:
            self._store.put(key, data)
        except Exception as exc:
            self._report_recovery_failure(exc)
            raise OSError(self.recovery_problem) from exc
        # Avoid taking a first historical snapshot of an empty, newly registered job.
        if self._history is not None and not key.startswith("session/"):
            self._history.request()

    # ------------------------------------------------------------------ APIClient-compatible interface

    def _register_job_locked(self, job_id: str) -> None:
        if job_id not in self._started:
            ordinal, timestamp = len(self._started) + 1, datetime.now()
            self._write(f"session/{job_id}", json_bytes([ordinal, timestamp.isoformat()]))
            with self._lock:
                self._started[job_id] = ordinal, timestamp

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
        practice_view: str = "",
    ) -> int:
        """Enqueue a frame and return its zero-based capture sequence for the job.

        Called from the capture QThread; extraction runs on the internal
        daemon pool so the capture loop never waits for extraction. A stopped
        pool raises RuntimeError without emitting frame_queued.
        """
        # Reserve only accepted slots. A fast completion waits for this lock,
        # so it cannot publish before the sequence has been committed.
        if self.has_recovery and (not job_id or "/" in job_id):
            raise ValueError("Identificativo di sessione non valido.")
        if practice_view not in ("", "list", "detail", "selection", "unknown"):
            raise ValueError("Contesto di navigazione non valido.")
        pixels = encode_pixels(img) if self.has_recovery else None
        with self._writer:
            if self._closed or self._pool is None:
                raise RuntimeError("Extraction pool has stopped accepting frames")
            self._register_job_locked(job_id)
            label = self.session_label(job_id)
            sequence = self._next_capture_sequence.get(job_id, 0)
            context, prior_view = self._capture_contexts.get(job_id, (None, ""))
            engine = self._engines[job_id]
            if not practice_view:
                context = None
            elif (practice_view != "detail" or prior_view not in {"selection", "detail"}
                  or context is None or engine.context_closed(context)):
                context = sequence
            practice = (engine.confirmed_practice(context, self._completed.get(job_id, {}).get(context))
                        if context is not None else None)
            if pixels is not None:
                payload = pack_pending(pixels, page_no, page_type, confidence, practice_view, context, practice)
                self._write(f"frame/{job_id}/{sequence}", payload)
            with self._lock:
                if self.has_recovery:
                    accepted = self._pool.submit(self._resume_frame, job_id, sequence)
                else:
                    accepted = self._pool.submit(
                        self._process_frame, job_id, img, page_no, page_type,
                        confidence, fields_json, sequence, practice_view, context, practice,
                    )
                if not accepted:
                    raise RuntimeError("Extraction pool has stopped accepting frames")
                self._queue.accept(job_id, sequence, label, page_type or f"pagina {page_no}", context, practice)
                self._capture_contexts[job_id] = context, practice_view
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
        practice_view: str = "",
        context: int | None = None,
        practice: str | None = None,
    ) -> None:
        """Pool worker: run the pipeline and publish the result."""
        screen_id = page_type if page_type else f"pagina {page_no}"

        self._queue_state(job_id, capture_sequence, "reading")
        try:
            # extract_from_image (not extract_from_screen): the Edge Agent has
            # already pre-processed the image, normalize_image would be redundant.
            if self._service is None:
                response = self._pipeline.extract_from_image(img, screen_id)
            else:
                response = self._service.read(img, screen_id, on_retry=lambda: self._queue_state(
                    job_id, capture_sequence, "retrying"))
            result = _checked_result(response)
        except Exception as e:  # noqa: BLE001
            result = {
                "screen_id": screen_id,
                "fields": {},
                "_status": "ERROR",
                "_error": str(e),
            }
            if isinstance(e, TimeoutError):
                result["_timed_out"] = True

        if practice_view:
            if context is not None:
                result["_capture_context"] = context
                result["_capture_practice"] = practice
            source = result.get("_practice_number_source")
            expected = "elenco" if practice_view == "list" else "dettaglio"
            if result.get("_practice_number") and source != expected:
                # The router and the identity reader must agree that a file was opened.
                result["_practice_number"] = None
                result["_practice_context_conflict"] = True
            result["_practice_view"] = practice_view
        result["_page_type"] = page_type
        result["_page_no"] = page_no
        result["_page_confidence"] = confidence
        result["_capture_sequence"] = capture_sequence

        try:
            _log_extraction(job_id, result)
        except Exception as exc:  # noqa: BLE001
            # Diagnostics must not leave a missing slot that blocks later results.
            result["_diagnostic_error"] = str(exc)

        payload = None
        if self.has_recovery and result.get("_status") != "ERROR":
            self._queue_state(job_id, capture_sequence, "saving")
            try:
                payload = b"R1\n" + json_bytes(result)
            except (TypeError, ValueError, OverflowError) as exc:
                result.update(fields={}, _status="ERROR", _error=str(exc))
        with self._writer:
            if self._closed and self.has_recovery:
                return  # Pending slots are replayed by the next owner.
            if payload is not None:
                try:
                    self._write(f"frame/{job_id}/{capture_sequence}", payload)
                except Exception as exc:
                    self._queue_state(job_id, capture_sequence, "storage_error")
                    self._report_recovery_failure(exc)
                    return
            # When the provider failed, keep the original pixels on disk for retry on restart.
            merged = self._publish_completed(job_id, {capture_sequence: result})

        if merged:
            self.practices_updated.emit(job_id)
        self.frame_finished.emit(job_id, screen_id, str(result.get("_status") or "OK"))
        self.result_ready.emit(job_id, dict(result))

    def _publish_completed(self, job: str, incoming: dict[int, dict]) -> bool:
        """The single writer merges off the UI lock and publishes the prefix atomically."""
        engine = self._engines[job]
        with self._lock:
            completed = self._completed.setdefault(job, {})
            completed.update(incoming)
            published = self._results.setdefault(job, [])
            start = len(published)
            for sequence, result in incoming.items():
                state = "failed_waiting" if result.get("_status") == "ERROR" else "waiting"
                practice = (engine.confirmed_practice(sequence, result)
                            if result.get("_capture_context") == sequence else None)
                self._queue.update(job, sequence, state, practice)
        end = start
        while end in completed:
            end += 1
        if end == start:
            return False
        frames = [completed[i] for i in range(start, end)]
        excluded: set[int] = set()
        assigned = engine.merge(frames, self._corrections.get(job, {}), excluded=excluded)
        records = engine.records(exportable_only=True)
        with self._lock:
            for seq in assigned:
                if seq < start:
                    state = "uncertain" if published[seq].get("_status") == "ANCHOR_UNCERTAIN" else "done"
                    self._queue.mark_assigned(job, seq, state, assigned[seq])
            for i in range(start, end):
                result = completed.pop(i)
                state = {"ERROR": "failed", "ANCHOR_UNCERTAIN": "uncertain"}.get(result.get("_status"), "done")
                if result.get("_practice_view") and i not in assigned and state != "failed":
                    state = "conflict" if i in excluded else "unassigned"
                self._queue.update(job, i, "timed_out" if result.get("_timed_out") else state, assigned.get(i))
            published.extend(frames)
            self._records[job] = records
        return True

    def _queue_state(self, job: str, sequence: int, state: str) -> None:
        with self._lock:
            self._queue.update(job, sequence, state)

    def queue_snapshot(self, previous: QueueSnapshot | None = None) -> QueueSnapshot:
        """Return display metadata only. Idle refreshes reuse the last snapshot."""
        pid = self._service.pid if self._service is not None else None
        with self._lock:
            if previous is not None and previous.revision == self._queue.revision and previous.pid == pid:
                return previous
            return QueueSnapshot(self._queue.revision, self._worker_limit, pid, self._queue.rows())

    def requeue_job(self, job_id: str) -> bool:
        """No-op stub for local mode."""
        return True

    def pending_extractions(self) -> int:
        """Number of queued frames not yet being processed."""
        return self._pool.pending() if self._pool is not None else 0

    def frames_in_progress(self) -> int:
        """Frames accepted whose result is not exportable yet.

        Unlike pending_extractions() this includes the frames a worker already picked
        up, and finished ones still waiting for an earlier frame to be published.
        """
        with self._lock:
            return sum(
                accepted - len(self._results.get(job_id, []))
                for job_id, accepted in self._next_capture_sequence.items()
            )

    def shutdown(self) -> None:
        """Stop scheduling work. Durable unfinished slots resume on the next launch."""
        with self._writer:
            if self._closed:
                return
            self._closed = True
            if self._history is not None:
                self._history.close()
            if self._pool is not None:
                self._pool.stop()
            if self._service is not None:
                self._service.close()
            if self._store is not None:
                self._store.close()

    # ------------------------------------------------------------------ Data access

    def get_results(self, job_id: str) -> List[Dict[str, Any]]:
        """Return the completed prefix in capture order, including error slots."""
        with self._lock:
            return list(self._results.get(job_id, []))

    def practice_count(self, job_id: str) -> int:
        """Practices with at least one value, corrections included: what an export would write."""
        return len(self.get_practices(job_id))

    def get_practices(self, job_id: str) -> tuple[PracticeRecord, ...]:
        """Ready-to-display rows from the last completed merge."""
        with self._lock:
            return self._records.get(job_id, ())

    def get_all_job_ids(self) -> List[str]:
        with self._lock:
            return list(self._next_capture_sequence)

    def capture_counts(self, job: str) -> tuple[int, int]:
        with self._lock:
            return self._next_capture_sequence.get(job, 0), len(self._results.get(job, []))

    def last_accepted_sequence(self, job: str) -> int:
        return self.capture_counts(job)[0] - 1

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
        key = correction_key(ndg)
        if key is None:
            raise ValueError(f"NDG non leggibile: {ndg!r}")
        if schema_key not in CORRECTABLE_KEYS:
            raise ValueError(f"Il campo {schema_key!r} non è correggibile")
        cleaned = clean_correction(value)
        with self._writer:
            corrections = self.get_corrections(job_id)
            corrections.setdefault(key, {})[schema_key] = cleaned
            self._save_confirmed_edits(job_id, key, schema_key, corrections)
        self.practices_updated.emit(job_id)

    def clear_correction(self, job_id: str, ndg: str, schema_key: str) -> None:
        """Drop one correction, restoring the extracted value."""
        key = correction_key(ndg)
        with self._writer:
            by_ndg = self.get_corrections(job_id)
            fields = by_ndg.get(key or "", {})
            fields.pop(schema_key, None)
            if not fields:
                by_ndg.pop(key or "", None)
            self._save_confirmed_edits(job_id, key or "", schema_key, by_ndg)
        self.practices_updated.emit(job_id)

    def _save_confirmed_edits(self, job: str, ndg: str, key: str, corrections: dict) -> None:
        draft = self.get_cell_draft(job)
        if draft and (draft["ndg"], draft["key"]) == (ndg, key):
            draft = None
        self._save_edits(job, corrections, draft)
        engine = self._engines.get(job)
        if engine is not None:
            engine.refresh(ndg, corrections)
            records = engine.records(exportable_only=True)
            with self._lock:
                self._records[job] = records

    def _save_edits(self, job: str, corrections: dict, draft: Optional[dict]) -> None:
        self._write(f"edits/{job}", json_bytes({"corrections": corrections, "draft": draft}))
        with self._lock:
            self._corrections[job] = corrections
            if draft is None:
                self._drafts.pop(job, None)
            else:
                self._drafts[job] = draft

    def set_cell_draft(self, job: str, ndg: str, key: str, text: str) -> None:
        normalized = correction_key(ndg)
        if normalized is None or key not in CORRECTABLE_KEYS:
            raise ValueError("La cella non è modificabile.")
        draft = {"ndg": normalized, "key": key, "text": text}
        with self._writer:
            self._save_edits(job, self.get_corrections(job), draft)

    def clear_cell_draft(self, job: str) -> None:
        with self._writer:
            if job in self._drafts:
                self._save_edits(job, self.get_corrections(job), None)

    def get_cell_draft(self, job: str) -> Optional[dict[str, str]]:
        with self._lock:
            return dict(self._drafts[job]) if job in self._drafts else None

    def navigation_decisions(self, job: str) -> list[dict]:
        with self._lock:
            return [dict(decision) for decision in self._navigation.get(job, [])]

    def record_navigation_decision(self, job: str, ndg: str, page: str, action: str, sequence: int) -> None:
        if action not in {"reopen", "skip", "restore"}:
            raise ValueError("Azione di navigazione non valida.")
        with self._writer:
            decisions = self.navigation_decisions(job)
            decisions.append(dict(ndg=ndg, page=page, action=action, sequence=sequence))
            self._write(f"navigation/{job}", json_bytes(decisions))
            with self._lock:
                self._navigation[job] = decisions

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
        with self._writer:
            labels = self.get_column_labels()
            if cleaned:
                labels[schema_key] = cleaned
            else:
                labels.pop(schema_key, None)
            self._write("labels", json_bytes(labels))
            with self._lock:
                self._column_labels = labels

    def export_workbook(self, job_id: str, path: str) -> int:
        """The only export path: corrections and shared labels included.

        Exports from one snapshot and remembers *its* fingerprint, so a result that
        lands mid-export keeps the session marked as not exported.
        """
        with self._lock:
            records = self._records.get(job_id, ())
            labels = dict(self._column_labels)
        write_workbook(records, build_columns(labels), path)
        written = len(records)
        if self._export_only:
            return written
        fingerprint = _fingerprint(records, labels)
        with self._writer:
            try:
                self._write(f"export/{job_id}", json_bytes(fingerprint))
            except OSError:
                # The workbook was committed. Keep the previous export marker and
                # let recovery_error explain the journal fault to the operator.
                return written
            with self._lock:
                self._exported[job_id] = fingerprint
        return written

    def unexported_jobs(self) -> List[str]:
        """Sessions whose exportable content differs from their last export."""
        with self._lock:
            labels = dict(self._column_labels)
            snapshot = [
                (job_id, records, self._exported.get(job_id))
                for job_id, records in self._records.items()
            ]
        pending = []
        for job_id, records, exported in snapshot:
            fingerprint = _fingerprint(records, labels)
            if fingerprint is not None and fingerprint != exported:
                pending.append(job_id)
        return pending
