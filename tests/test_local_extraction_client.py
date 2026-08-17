"""Async behavior tests for LocalExtractionClient with an injected fake pipeline."""

import os
import time

# Must be set before importing extraction.config (read at import time).
os.environ.setdefault("LLM_API_KEY", "test-key")

from PIL import Image
from PyQt6.QtCore import QCoreApplication

import local_extraction_client as lec


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
