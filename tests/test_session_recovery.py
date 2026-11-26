"""Restart a real local client with synthetic captures and isolated recovery storage."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.usefixtures("isolated_edge_backup")
from PIL import Image
from PyQt6.QtCore import QCoreApplication

os.environ.setdefault("LLM_API_KEY", "offline-test")
from local_extraction_client import LocalExtractionClient


class SyntheticExtraction:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict[str, Any]:
        self.calls.append(screen_id)
        return {"screen_id": screen_id, "_status": "OK", "fields": {
            "ndg": {"value": "111", "confidence": 1.0},
            "tipo": {"value": str(img.getpixel((0, 0))), "confidence": 1.0},
        }}


def wait_results(client: LocalExtractionClient, job: str, count: int) -> list[dict]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        rows = client.get_results(job)
        if len(rows) == count:
            return rows
        time.sleep(0.01)
    pytest.fail("Capture order was not recovered")


def crash_writer(directory: Path) -> None:
    """Exit without destructors while one earlier frame is waiting for the provider."""
    app = QCoreApplication([])
    class Delayed(SyntheticExtraction):
        def extract_from_image(self, img: Image.Image, screen_id: str) -> dict[str, Any]:
            if screen_id == "interrupted":
                threading.Event().wait(60)
            return super().extract_from_image(img, screen_id)

    client = LocalExtractionClient(pipeline=Delayed(), recovery_dir=directory)
    client.ingest_frame("job", Image.new("L", (5, 5), 7), page_type="first")
    wait_results(client, "job", 1)
    client.set_correction("job", "111", "tipo", "correzione sintetica")
    client.set_column_label("tipo", "Colonna di prova")
    client.export_workbook("job", directory.parent / "before.xlsx")
    client.set_cell_draft("job", "111", "denominazione", "bozza non confermata")
    client.record_navigation_decision("job", "111", "sezione", "skip", 0)
    done = threading.Event()
    from PyQt6.QtCore import Qt
    client.result_ready.connect(lambda j, r: done.set() if r["screen_id"] == "third" else None,
                                Qt.ConnectionType.DirectConnection)
    client.ingest_frame("job", Image.new("L", (5, 5), 8), page_type="interrupted")
    client.ingest_frame("job", Image.new("L", (5, 5), 9), page_type="third")
    assert done.wait(15)
    os._exit(43)


def test_abrupt_exit_recovers_confirmed_edits_and_replays_only_the_missing_slot(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    directory = tmp_path / "protected"
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (root/"src", root/"src"/"edge-agent"))),
               PARALLEL_WORKERS="2", LLM_API_KEY="offline-only")
    run = subprocess.run([sys.executable, __file__, str(directory)], env=env, capture_output=True, timeout=60)
    assert run.returncode == 43, run.stderr.decode(errors="replace")
    model = SyntheticExtraction()
    client = LocalExtractionClient(pipeline=model, recovery_dir=directory)
    try:
        assert client.recovered_jobs == ("job",)
        results = wait_results(client, "job", 3)
        assert [row["fields"]["tipo"]["value"] for row in results] == ["7", "8", "9"]
        assert model.calls == ["interrupted"]
        assert client.last_accepted_sequence("job") == 2
        assert client.practice_count("job") == 1
        assert client.get_corrections("job")["111"]["tipo"] == "correzione sintetica"
        assert client.get_column_labels()["tipo"] == "Colonna di prova"
        assert client.get_cell_draft("job") == {
            "ndg": "111", "key": "denominazione", "text": "bozza non confermata",
        }
        assert client.navigation_decisions("job")[0]["action"] == "skip"
        assert not client.unexported_jobs()  # consolidated content is identical to the export
        assert client.ingest_frame("job", Image.new("L", (5, 5), 10), page_type="new") == 3
        wait_results(client, "job", 4)
    finally:
        client.shutdown()


def test_unfinished_typing_survives_restart_until_the_cell_is_confirmed(tmp_path: Path) -> None:
    with_client = lambda: LocalExtractionClient(pipeline=SyntheticExtraction(), recovery_dir=tmp_path)
    client = with_client()
    client.ingest_frame("edit", Image.new("L", (5, 5)), page_type="base")
    wait_results(client, "edit", 1)
    client.set_cell_draft("edit", "111", "tipo", "bozza  ")
    client.shutdown()
    resumed = with_client()
    try:
        assert resumed.get_cell_draft("edit") == {"ndg": "111", "key": "tipo", "text": "bozza  "}
        assert resumed.get_corrections("edit") == {}
        resumed.set_correction("edit", "111", "tipo", "Confermato")
    finally:
        resumed.shutdown()
    final = with_client()
    try:
        assert final.get_cell_draft("edit") is None
        assert final.get_corrections("edit")["111"]["tipo"] == "Confermato"
    finally:
        final.shutdown()


def test_replay_keeps_late_results_with_the_selected_practice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EDGE_AGENT_MAX_JOBS", "2")
    released = threading.Event()
    note_finished = threading.Event()

    class Reader:
        def extract_from_image(self, image: Image.Image, screen_id: str) -> dict:
            if screen_id == "Testata B":
                assert released.wait(10)
            if screen_id == "Note B":
                return {"fields": {"note_della_richiesta": {"value": "Solo B", "confidence": 1.0}}}
            number = "31" if screen_id == "Fidi A" else "42"
            source = "elenco" if screen_id == "Ricerca B" else "dettaglio"
            return {"_practice_number": number, "_practice_number_source": source,
                    "fields": {"ndg": {"value": "100", "confidence": 1.0}}}

    from PyQt6.QtCore import Qt
    directory = tmp_path / "recovery"
    client = LocalExtractionClient(pipeline=Reader(), recovery_dir=directory)
    try:
        client.result_ready.connect(
            lambda job, result: note_finished.set() if result["_page_type"] == "Note B" else None,
            Qt.ConnectionType.DirectConnection,
        )
        for name, view in [("Fidi A", "selection"), ("Ricerca B", "list"),
                           ("Testata B", "selection"), ("Note B", "detail")]:
            client.ingest_frame("p1", Image.new("L", (3, 3)), page_type=name, practice_view=view)
        assert note_finished.wait(10)
        assert [row.practice_number for row in client.get_practices("p1")] == ["31"]
        # The earlier in-flight header stays as pixels when the process stops.
    finally:
        client.shutdown()
        released.set()
    resumed = LocalExtractionClient(pipeline=Reader(), recovery_dir=directory)
    try:
        results = wait_results(resumed, "p1", 4)
        assert [f["_practice_view"] for f in results] == ["selection", "list", "selection", "detail"]
        assert next(r.state for r in resumed.queue_snapshot().rows if r.sequence == 3) == "unassigned"
        resumed.ingest_frame("p1", Image.new("L", (3, 3)), page_type="Conferma B", practice_view="detail")
        wait_results(resumed, "p1", 5)
        assert [(r.practice_number, r.fields["note_della_richiesta"]["value"])
                for r in resumed.get_practices("p1")] == [("31", None), ("42", "Solo B")]
        assert next(r.state for r in resumed.queue_snapshot().rows if r.sequence == 3) == "done"
        resumed.set_correction("p1", "pef:42", "tipo", "Corretto B")
        resumed.set_cell_draft("p1", "pef:31", "tipo", "Bozza A")
    finally:
        resumed.shutdown()
    offline = LocalExtractionClient(export_only=True, recovery_dir=directory)
    try:
        assert offline.get_cell_draft("p1")["ndg"] == "pef:31"
        assert [row.fields["tipo"]["value"] for row in offline.get_practices("p1")] == [None, "Corretto B"]
        assert offline.export_workbook("p1", str(tmp_path / "pratiche.xlsx")) == 2
    finally:
        offline.shutdown()


def test_capture_ownership_survives_restart_while_another_practice_is_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PyQt6.QtCore import Qt

    monkeypatch.setenv("EDGE_AGENT_MAX_JOBS", "2")
    release, later_read = threading.Event(), threading.Event()

    class Reader:
        def extract_from_image(self, image: Image.Image, screen_id: str) -> dict:
            fields = {"ndg": {"value": "100"}}
            if screen_id == "Nota A":
                assert release.wait(15)
                fields["note_della_richiesta"] = {"value": "Solo A"}
            return {"_practice_number": "42" if screen_id.endswith(" B") else "31",
                    "_practice_number_source": "dettaglio", "fields": fields}

    directory = tmp_path / "recovery"
    client = LocalExtractionClient(pipeline=Reader(), recovery_dir=directory)
    picture = Image.new("L", (4, 4))
    try:
        client.result_ready.connect(lambda job, row: later_read.set() if row["_page_type"] == "Testata B" else None,
                                    Qt.ConnectionType.DirectConnection)
        client.ingest_frame("session", picture, page_type="Testata A", practice_view="selection")
        wait_results(client, "session", 1)
        client.ingest_frame("session", picture, page_type="Nota A", practice_view="detail")
        client.ingest_frame("session", picture, page_type="Testata B", practice_view="selection")
        assert later_read.wait(10)
        client.ingest_frame("session", picture, page_type="Fidi B", practice_view="detail")
        queue = {r.page: r for r in client.queue_snapshot().rows}
        assert queue["Nota A"].practice == "31"
        assert queue["Fidi B"].practice == "42"
        assert queue["Nota A"].context != queue["Testata B"].context
        original_context = queue["Nota A"].context
    finally:
        client.shutdown()
        release.set()
    resumed = LocalExtractionClient(pipeline=Reader(), recovery_dir=directory)
    try:
        results = wait_results(resumed, "session", 4)
        assert results[1]["_capture_context"] == original_context == results[0]["_capture_context"]
        assert results[1]["_capture_practice"] == "31"
        assert results[2]["_capture_context"] != original_context
        assert [(r.practice_number, r.fields["note_della_richiesta"]["value"])
                for r in resumed.get_practices("session")] == [("31", "Solo A"), ("42", None)]
    finally:
        resumed.shutdown()


def test_failed_checkpoint_does_not_acknowledge_frame(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from recovery_store import RecoveryStore

    client = LocalExtractionClient(pipeline=SyntheticExtraction(), recovery_dir=tmp_path)
    frames: list[str] = []
    client.frame_queued.connect(lambda job, page: frames.append(page))
    def full_disk(self: RecoveryStore, key: str, payload: bytes) -> None:
        raise OSError("disco pieno")
    monkeypatch.setattr(RecoveryStore, "put", full_disk)
    try:
        with pytest.raises(OSError):
            client.ingest_frame("test", Image.new("L", (2, 2)), page_type="fidi")
        assert frames == [] and client.frames_in_progress() == 0
        assert client.recovery_problem
    finally:
        client.shutdown()


def test_emergency_export_remains_readable_when_recovery_disk_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from openpyxl import load_workbook
    from recovery_store import RecoveryStore

    client = LocalExtractionClient(pipeline=SyntheticExtraction(), recovery_dir=tmp_path / "recovery")
    try:
        client.ingest_frame("job", Image.new("L", (2, 2)), page_type="base")
        wait_results(client, "job", 1)

        def unavailable(self: RecoveryStore, key: str, payload: bytes) -> None:
            raise OSError("simulated storage error")

        monkeypatch.setattr(RecoveryStore, "put", unavailable)
        path = tmp_path / "emergency.xlsx"
        assert client.export_workbook("job", str(path)) == 1
        book = load_workbook(path)
        try:
            assert book.active.cell(3, 1).value == "111"
        finally:
            book.close()
        assert client.recovery_problem
        assert client.unexported_jobs() == ["job"]
    finally:
        client.shutdown()


def test_first_capture_creates_an_independent_history_for_restore(tmp_path: Path, isolated_edge_backup: Path) -> None:
    from recovery_history import restore_snapshot
    from recovery_store import RecoveryStore

    directory = tmp_path / "primary"
    client = LocalExtractionClient(pipeline=SyntheticExtraction(), recovery_dir=directory)
    try:
        client.ingest_frame("job", Image.new("L", (2, 2)), page_type="base")
        wait_results(client, "job", 1)
        limit = time.monotonic() + 4
        while time.monotonic() < limit:
            copies = list((isolated_edge_backup / "history").glob("snapshot-*"))
            if copies:
                break
            time.sleep(0.02)
        assert copies
        destination = tmp_path / "restored"
        restore_snapshot(copies[0], destination)
        verified = RecoveryStore(destination)
        try:
            assert {"session/job", "frame/job/0"} <= set(verified.keys())
        finally:
            verified.close()
    finally:
        client.shutdown()


def test_waiting_captures_release_their_image_memory_after_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import weakref

    monkeypatch.setattr("local_extraction_client.PARALLEL_WORKERS", 1)
    busy = threading.Event()
    release = threading.Event()

    class Busy(SyntheticExtraction):
        def extract_from_image(self, img: Image.Image, screen_id: str) -> dict[str, Any]:
            busy.set()
            release.wait(15)
            return super().extract_from_image(img, screen_id)

    client = LocalExtractionClient(pipeline=Busy(), recovery_dir=tmp_path)
    try:
        client.ingest_frame("job", Image.new("L", (2, 2)), page_type="first")
        assert busy.wait(5)
        image = Image.new("L", (20, 20), 32)
        original = weakref.ref(image)
        client.ingest_frame("job", image, page_type="second")
        del image
        import gc
        gc.collect()
        assert original() is None
        release.set()
        assert wait_results(client, "job", 2)[1]["fields"]["tipo"]["value"] == "32"
    finally:
        release.set()
        client.shutdown()


if __name__ == "__main__":
    crash_writer(Path(sys.argv[1]))
