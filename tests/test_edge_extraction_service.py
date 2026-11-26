"""Exercise the desktop's real process boundary with synthetic pixels."""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PIL import Image

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QApplication


@pytest.mark.parametrize(("cpus", "expected"), [(1, 1), (4, 3), (32, 4)])
def test_auto_job_limit_reserves_cpu_for_the_desktop(
    monkeypatch: pytest.MonkeyPatch, cpus: int, expected: int,
) -> None:
    from extraction_service import worker_limit

    monkeypatch.setenv("EDGE_AGENT_MAX_JOBS", "auto")
    monkeypatch.setattr(os, "process_cpu_count", lambda: cpus, raising=False)
    assert worker_limit(8) == expected


class PixelReader:
    def __init__(self) -> None:
        self.rendezvous = threading.Barrier(2)

    def extract_from_image(self, image: Image.Image, screen_id: str) -> dict:
        if screen_id == "crash":
            os._exit(17)
        if screen_id.startswith("parallel"):
            self.rendezvous.wait(timeout=10)
        return {"screen_id": screen_id, "pixel": image.getpixel((0, 0)), "pid": os.getpid()}


def test_two_screens_run_concurrently_in_one_separate_model_process() -> None:
    from extraction_service import ExtractionService

    service = ExtractionService(2, PixelReader)
    try:
        with ThreadPoolExecutor(2) as callers:
            futures = [callers.submit(service.extract_from_image, Image.new("L", (4, 4), i),
                                      f"parallel-{i}") for i in (1, 2)]
            first, second = [future.result(timeout=25) for future in futures]
        assert first["pid"] == second["pid"] != os.getpid()
        assert [(row["screen_id"], row["pixel"]) for row in (first, second)] == [
            ("parallel-1", 1), ("parallel-2", 2)]
    finally:
        service.close()


def test_losing_the_reader_process_allows_the_next_capture_to_run() -> None:
    from extraction_service import ExtractionService

    service = ExtractionService(1, PixelReader)
    image = Image.new("L", (2, 2), 43)
    try:
        with pytest.raises(RuntimeError):
            service.extract_from_image(image, "crash")
        assert service.extract_from_image(image, "next")["pixel"] == 43
    finally:
        service.close()


def _missing_model() -> PixelReader:
    raise ValueError("missing model weights")


def test_failed_model_initialization_reports_the_cause_for_each_capture() -> None:
    from extraction_service import ExtractionService

    service = ExtractionService(1, _missing_model)
    try:
        for _ in range(2):
            with pytest.raises(RuntimeError, match="missing model weights"):
                service.extract_from_image(Image.new("L", (512, 512)), "header")
    finally:
        service.close()


class RecoverableReader:
    def extract_from_image(self, image: Image.Image, screen_id: str) -> dict:
        marker = Path(os.environ["SYNTHETIC_CAPTURE_MARKER"])
        if screen_id == "header":
            gate = os.environ.get("SYNTHETIC_GUI_GATE")
            if gate:
                Path(gate + ".started").touch()
                deadline = time.monotonic() + 10
                while not Path(gate).exists():
                    if time.monotonic() > deadline:
                        raise TimeoutError("Qt did not release the reader")
                    time.sleep(0.01)
            remaining = int(marker.read_text())
            if remaining:
                marker.write_text(str(remaining - 1))
                os._exit(17)
        field = "ndg" if screen_id == "header" else "note_della_richiesta"
        return {"screen_id": screen_id, "_status": "OK", "fields": {
            field: {"value": str(image.getpixel((0, 0))), "confidence": 1.0}}}


def test_desktop_recovers_pixels_after_model_crash_and_merges_the_later_note(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_edge_backup: Path,
) -> None:
    from PyQt6.QtCore import QTimer
    import local_extraction_client as lec
    from extraction_service import ExtractionService

    monkeypatch.setenv("EDGE_AGENT_MAX_JOBS", "1")
    marker = tmp_path / "crashes-remaining"
    marker.write_text("2")
    monkeypatch.setenv("SYNTHETIC_CAPTURE_MARKER", str(marker))
    gate = tmp_path / "ui-ready"
    monkeypatch.setenv("SYNTHETIC_GUI_GATE", str(gate))
    monkeypatch.setattr(lec, "ExtractionService", partial(ExtractionService, factory=RecoverableReader))
    directory = tmp_path / "session"
    client = lec.LocalExtractionClient(recovery_dir=directory)
    heartbeat = []
    timer = QTimer()

    def release_reader() -> None:
        if gate.with_suffix(".started").exists():
            heartbeat.append(client.frames_in_progress())
            gate.touch()
            timer.stop()

    try:
        client.ingest_frame("job", Image.new("L", (4, 4), 111), page_type="header")
        client.ingest_frame("job", Image.new("L", (4, 4), 43), page_type="note")
        timer.timeout.connect(release_reader)
        timer.start(10)
        deadline = time.monotonic() + 20
        while client.frames_in_progress() and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.01)
        assert heartbeat and heartbeat[0] > 0
        assert [r["_status"] for r in client.get_results("job")] == ["ERROR", "OK"]
        assert marker.read_text() == "0"
    finally:
        timer.stop()
        client.shutdown()
    restored = lec.LocalExtractionClient(recovery_dir=directory)
    try:
        deadline = time.monotonic() + 20
        while restored.frames_in_progress() and time.monotonic() < deadline:
            time.sleep(0.01)
        record, = restored.get_practices("job")
        assert (record.ndg, record.source_pages) == ("111", ("header", "note"))
        assert record.fields["note_della_richiesta"]["value"] == "43"
    finally:
        restored.shutdown()


def test_desktop_retries_a_crashed_process_in_the_original_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_edge_backup: Path,
) -> None:
    import local_extraction_client as lec
    from extraction_service import ExtractionService

    marker = tmp_path / "crashes-remaining"
    marker.write_text("1")
    monkeypatch.setenv("SYNTHETIC_CAPTURE_MARKER", str(marker))
    monkeypatch.setattr(lec, "ExtractionService", partial(ExtractionService, factory=RecoverableReader))
    client = lec.LocalExtractionClient(recovery_dir=tmp_path / "session")
    try:
        sequence = client.ingest_frame("job", Image.new("L", (4, 4), 111), page_type="header")
        deadline = time.monotonic() + 20
        while client.frames_in_progress() and time.monotonic() < deadline:
            time.sleep(0.01)
        result, = client.get_results("job")
        assert (result["_status"], result["_capture_sequence"]) == ("OK", sequence)
        assert client.capture_counts("job") == (1, 1)
    finally:
        client.shutdown()
