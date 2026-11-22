"""Async behavior tests for LocalExtractionClient with an injected fake pipeline."""

import os
import re
import threading
import time
from typing import Any

import pytest

# Must be set before importing extraction.config (read at import time).
os.environ.setdefault("LLM_API_KEY", "test-key")

from PIL import Image
from PyQt6.QtCore import QCoreApplication

import local_extraction_client as lec
from excel_export import build_columns
from openpyxl import load_workbook
from practice_consolidation import consolidate


class FakePipeline:
    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict:
        time.sleep(0.2)  # simulate slow VLM work
        return {
            "screen_id": screen_id,
            "fields": {"ndg": {"value": "123", "confidence": 1.0}},
            "_status": "OK",
        }


class BrokenPipeline:
    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict:
        raise RuntimeError("VLM down")


def _app() -> QCoreApplication:
    return QCoreApplication.instance() or QCoreApplication([])


def _wait_for(condition, app: QCoreApplication, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while not condition() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)


def test_ingest_frame_returns_immediately_and_result_arrives_async() -> None:
    app = _app()
    client = lec.LocalExtractionClient(pipeline=FakePipeline())
    queued: list = []
    got: list = []
    client.frame_queued.connect(lambda job, page: queued.append((job, page)))
    client.result_ready.connect(lambda job, result: got.append((job, result)))

    img = Image.new("RGB", (10, 10))
    t0 = time.time()
    client.ingest_frame("job1", img, page_no=5, page_type="Gestione Fidi e Garanzie")
    assert time.time() - t0 < 0.15  # ben sotto i 0.2s del fake: non ha atteso l'estrazione
    assert queued == [("job1", "Gestione Fidi e Garanzie")]

    _wait_for(lambda: got, app)
    assert got and got[0][0] == "job1"
    result = got[0][1]
    assert result["_page_type"] == "Gestione Fidi e Garanzie"
    assert result["_page_no"] == 5
    assert result["screen_id"] == "Gestione Fidi e Garanzie"  # no .title() mangling
    assert client.get_results("job1")[0]["_status"] == "OK"
    client.shutdown()


def test_pipeline_error_produces_error_result() -> None:
    app = _app()
    client = lec.LocalExtractionClient(pipeline=BrokenPipeline())
    got: list = []
    client.result_ready.connect(lambda job, result: got.append(result))
    client.ingest_frame("job2", Image.new("RGB", (10, 10)), page_no=1, page_type="Elenco Soggetti")
    _wait_for(lambda: got, app)
    assert got[0]["_status"] == "ERROR"
    assert "VLM down" in got[0]["_error"]
    client.shutdown()


def test_shutdown_stops_accepting_work() -> None:
    app = _app()
    client = lec.LocalExtractionClient(pipeline=FakePipeline())
    client.shutdown()
    _wait_for(lambda: client.pending_extractions() == 0, app, timeout=2.0)
    assert client.pending_extractions() == 0


class ControlledPipeline:
    """Gate the external extraction boundary while using the real worker pool."""

    def __init__(self, replies: dict[str, dict[str, Any] | Exception]) -> None:
        self.replies = replies
        self.started = {name: threading.Event() for name in replies}
        self.release = {name: threading.Event() for name in replies}

    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict[str, Any]:
        self.started[screen_id].set()
        if not self.release[screen_id].wait(timeout=5.0):
            raise TimeoutError(f"Test did not release {screen_id}")
        reply = self.replies[screen_id]
        if isinstance(reply, Exception):
            raise reply
        return {"screen_id": screen_id, "fields": reply, "_status": "OK"}

    def release_all(self) -> None:
        for event in self.release.values():
            event.set()


def _field(value: str) -> dict[str, Any]:
    return {"value": value, "confidence": 1.0}


@pytest.mark.parametrize("delayed_page", ["second-practice", "anonymous-note"])
def test_out_of_order_completions_preserve_practice_assignment(
    monkeypatch: pytest.MonkeyPatch, delayed_page: str
) -> None:
    monkeypatch.setattr(lec, "PARALLEL_WORKERS", 3)
    app = _app()
    pipeline = ControlledPipeline({
        "first-practice": {"ndg": _field("111")},
        "second-practice": {"ndg": _field("222")},
        "anonymous-note": {"note_della_richiesta": _field("Note from capture")},
    })
    client = lec.LocalExtractionClient(pipeline=pipeline)
    completions: list[str] = []
    client.result_ready.connect(lambda job, result: completions.append(result["screen_id"]))
    pages = ["first-practice", delayed_page]
    pages.append("anonymous-note" if delayed_page == "second-practice" else "second-practice")
    try:
        for page in pages:
            client.ingest_frame("job", Image.new("RGB", (10, 10)), page_type=page)
        assert all(event.wait(timeout=2.0) for event in pipeline.started.values())

        pipeline.release[pages[0]].set()
        _wait_for(lambda: pages[0] in completions, app)
        pipeline.release[pages[2]].set()
        _wait_for(lambda: pages[2] in completions, app)
        assert completions == [pages[0], pages[2]]

        visible = client.get_results("job")
        assert [result["screen_id"] for result in visible] == [pages[0]]
        assert consolidate(visible)[0].fields["note_della_richiesta"]["value"] is None

        pipeline.release[delayed_page].set()
        _wait_for(lambda: len(completions) == 3, app)
        results = client.get_results("job")
        assert [result["screen_id"] for result in results] == pages
        records = {record.ndg: record for record in consolidate(results)}
        note_owner = "222" if delayed_page == "second-practice" else "111"
        other_practice = "111" if note_owner == "222" else "222"
        assert records[note_owner].fields["note_della_richiesta"]["value"] == "Note from capture"
        assert records[other_practice].fields["note_della_richiesta"]["value"] is None
    finally:
        pipeline.release_all()
        client.shutdown()


def test_slow_job_does_not_delay_another_jobs_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lec, "PARALLEL_WORKERS", 2)
    app = _app()
    pipeline = ControlledPipeline({"slow": {"ndg": _field("111")}, "fast": {"ndg": _field("222")}})
    client = lec.LocalExtractionClient(pipeline=pipeline)
    completions: list[tuple[str, dict[str, Any]]] = []
    client.result_ready.connect(lambda job, result: completions.append((job, result)))
    try:
        slow_sequence = client.ingest_frame("slow-job", Image.new("RGB", (10, 10)), page_type="slow")
        fast_sequence = client.ingest_frame("fast-job", Image.new("RGB", (10, 10)), page_type="fast")
        assert all(event.wait(timeout=2.0) for event in pipeline.started.values())
        pipeline.release["fast"].set()
        _wait_for(lambda: completions, app)
        assert client.get_results("slow-job") == []
        assert client.get_results("fast-job")[0]["fields"]["ndg"]["value"] == "222"
        assert slow_sequence == fast_sequence == 0
        assert completions[0][1]["_capture_sequence"] == fast_sequence
    finally:
        pipeline.release_all()
        client.shutdown()


def test_error_completion_releases_the_following_ordered_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lec, "PARALLEL_WORKERS", 2)
    app = _app()
    pipeline = ControlledPipeline({"broken": RuntimeError("VLM down"), "next": {"ndg": _field("222")}})
    client = lec.LocalExtractionClient(pipeline=pipeline)
    completions: list[dict[str, Any]] = []
    client.result_ready.connect(lambda job, result: completions.append(result))
    try:
        first_sequence = client.ingest_frame("job", Image.new("RGB", (10, 10)), page_type="broken")
        next_sequence = client.ingest_frame("job", Image.new("RGB", (10, 10)), page_type="next")
        assert all(event.wait(timeout=2.0) for event in pipeline.started.values())
        pipeline.release["next"].set()
        _wait_for(lambda: completions, app)
        assert client.get_results("job") == []
        pipeline.release["broken"].set()
        _wait_for(lambda: len(completions) == 2, app)
        results = client.get_results("job")
        assert [result["_status"] for result in results] == ["ERROR", "OK"]
        assert [result["_capture_sequence"] for result in results] == [first_sequence, next_sequence] == [0, 1]
        assert completions[-1]["_capture_sequence"] == first_sequence
    finally:
        pipeline.release_all()
        client.shutdown()


def test_rejected_ingest_does_not_emit_frame_queued() -> None:
    _app()
    client = lec.LocalExtractionClient(pipeline=BrokenPipeline())
    queued: list[tuple[str, str]] = []
    client.frame_queued.connect(lambda job, page: queued.append((job, page)))
    client.shutdown()
    with pytest.raises(RuntimeError, match="stopped"):
        client.ingest_frame("job", Image.new("RGB", (10, 10)), page_type="rejected")
    assert queued == []
    assert client.get_results("job") == []


def test_log_write_error_does_not_block_ordered_results(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app()
    client = lec.LocalExtractionClient(pipeline=FakePipeline())
    completions: list[dict[str, Any]] = []
    client.result_ready.connect(lambda job, result: completions.append(result))

    def broken_output(*args: Any, **kwargs: Any) -> None:
        raise OSError("Log output unavailable")

    monkeypatch.setattr(lec, "print", broken_output, raising=False)
    try:
        client.ingest_frame("job", Image.new("RGB", (10, 10)), page_type="first")
        client.ingest_frame("job", Image.new("RGB", (10, 10)), page_type="next")
        _wait_for(lambda: len(completions) == 2, app)
        results = client.get_results("job")
        assert [result["screen_id"] for result in results] == ["first", "next"]
        assert [result["_status"] for result in results] == ["OK", "OK"]
        assert all(result["fields"]["ndg"]["value"] == "123" for result in results)
        assert len(completions) == 2
    finally:
        client.shutdown()


# ============================================================
# Operator corrections, shared labels, export and unexported tracking
# ============================================================


class ScriptedPipeline:
    """Replies per page type with scripted fields (the extraction boundary)."""

    def __init__(self, replies: dict[str, dict[str, Any]]) -> None:
        self.replies = replies

    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict[str, Any]:
        return {"screen_id": screen_id, "fields": self.replies[screen_id], "_status": "OK"}


def _ingest(client: lec.LocalExtractionClient, job: str, page: str, app: QCoreApplication) -> None:
    """Queue one frame and wait until its result is published."""
    before = len(client.get_results(job))
    client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type=page)
    _wait_for(lambda: len(client.get_results(job)) > before, app)


def _client_with_practice(app: QCoreApplication, **extra: dict[str, Any]) -> tuple[lec.LocalExtractionClient, str]:
    replies = {"p1": {"ndg": _field("123"), "tipo": _field("BPI Mutui")}, **extra}
    client = lec.LocalExtractionClient(pipeline=ScriptedPipeline(replies))
    job = client.start_job()
    _ingest(client, job, "p1", app)
    return client, job


def _cell(path: str, schema_key: str, row: int = 3) -> Any:
    column = [c.schema_key for c in build_columns()].index(schema_key) + 1
    return load_workbook(path).active.cell(row=row, column=column)


def test_set_correction_cleans_the_text() -> None:
    app = _app()
    client, job = _client_with_practice(app)
    client.set_correction(job, "123", "tipo", "  Mu\x00tuo\x07 ")
    assert client.get_corrections(job) == {"123": {"tipo": "Mutuo"}}
    client.set_correction(job, "123", "tipo", "")
    assert client.get_corrections(job) == {"123": {"tipo": None}}
    client.set_correction(job, "123", "tipo", "x" * 40000)
    assert len(client.get_corrections(job)["123"]["tipo"]) == 32767
    client.shutdown()


def test_set_correction_normalizes_the_ndg() -> None:
    app = _app()
    client, job = _client_with_practice(app)
    client.set_correction(job, "012.123", "tipo", "Mutuo")
    assert client.get_corrections(job) == {"12123": {"tipo": "Mutuo"}}
    client.shutdown()


@pytest.mark.parametrize("ndg, key", [("123", "ndg"), ("123", "boh"), ("n/d", "tipo")])
def test_set_correction_refuses_ndg_unknown_fields_and_unreadable_ndg(ndg: str, key: str) -> None:
    app = _app()
    client, job = _client_with_practice(app)
    with pytest.raises(ValueError):
        client.set_correction(job, ndg, key, "x")
    client.shutdown()


def test_corrections_are_per_session_and_returned_as_copies() -> None:
    app = _app()
    client, job1 = _client_with_practice(app)
    job2 = client.start_job()
    _ingest(client, job2, "p1", app)
    client.set_correction(job1, "123", "tipo", "Mutuo")
    assert client.get_corrections(job2) == {}
    client.get_corrections(job1)["123"]["tipo"] = "tampered"
    assert client.get_corrections(job1) == {"123": {"tipo": "Mutuo"}}
    client.clear_correction(job1, "123", "tipo")
    assert client.get_corrections(job1) == {}
    client.shutdown()


def test_export_workbook_writes_corrections_and_shared_labels(tmp_path) -> None:
    app = _app()
    client, job = _client_with_practice(app)
    client.set_correction(job, "123", "tipo", "Mutuo")
    client.set_column_label("tipo", "Tipo pratica")
    path = str(tmp_path / "out.xlsx")
    assert client.export_workbook(job, path) == 1
    assert _cell(path, "tipo").value == "Mutuo"
    assert _cell(path, "tipo", row=2).value == "Tipo pratica"
    assert client.get_column_labels() == {"tipo": "Tipo pratica"}
    client.shutdown()


@pytest.mark.parametrize("typed", ["=1+1", "+5", "-300,50", "@x"])
def test_formula_like_corrections_are_exported_as_inert_text(tmp_path, typed: str) -> None:
    app = _app()
    client, job = _client_with_practice(app)
    client.set_correction(job, "123", "tipo", typed)
    path = str(tmp_path / "out.xlsx")
    client.export_workbook(job, path)
    cell = _cell(path, "tipo")
    assert (cell.data_type, cell.value) == ("s", typed)
    client.shutdown()


def test_correction_with_control_characters_exports_without_error(tmp_path) -> None:
    app = _app()
    client, job = _client_with_practice(app)
    client.set_correction(job, "123", "tipo", "\x00a\x1fb")
    path = str(tmp_path / "out.xlsx")
    client.export_workbook(job, path)
    assert _cell(path, "tipo").value == "ab"
    client.shutdown()


def test_job_is_unexported_until_exported_and_again_after_a_change(tmp_path) -> None:
    app = _app()
    client, job = _client_with_practice(app, p2={"ndg": _field("123"), "stato": _field("Aperta")})
    assert client.unexported_jobs() == [job]
    client.export_workbook(job, str(tmp_path / "a.xlsx"))
    assert client.unexported_jobs() == []
    _ingest(client, job, "p2", app)
    assert client.unexported_jobs() == [job]
    client.export_workbook(job, str(tmp_path / "b.xlsx"))
    client.set_correction(job, "123", "tipo", "Mutuo")
    assert client.unexported_jobs() == [job]
    client.shutdown()


def test_reverting_a_correction_restores_the_exported_state(tmp_path) -> None:
    app = _app()
    client, job = _client_with_practice(app)
    client.export_workbook(job, str(tmp_path / "a.xlsx"))
    client.set_correction(job, "123", "tipo", "Mutuo")
    assert client.unexported_jobs() == [job]
    client.clear_correction(job, "123", "tipo")
    assert client.unexported_jobs() == []
    client.shutdown()


def test_error_only_job_is_never_unexported() -> None:
    app = _app()
    client = lec.LocalExtractionClient(pipeline=BrokenPipeline())
    job = client.start_job()
    _ingest(client, job, "p1", app)
    assert client.get_results(job)[0]["_status"] == "ERROR"
    assert client.unexported_jobs() == []
    client.shutdown()


def test_session_labels_number_sessions_in_start_order() -> None:
    client = lec.LocalExtractionClient(pipeline=FakePipeline())
    first, second = client.start_job(), client.start_job()
    assert re.fullmatch(r"Sessione 1 · \d\d:\d\d", client.session_label(first))
    assert client.session_label(second).startswith("Sessione 2 · ")
    client.shutdown()
