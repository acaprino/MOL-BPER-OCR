"""Recover the available workbook with no running GUI or model provider."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from openpyxl import load_workbook
from PIL import Image

from local_extraction_client import LocalExtractionClient
from recovery_store import RecoveryStore


class _OfflineExtraction:
    def extract_from_image(self, image: Image.Image, screen_id: str) -> dict[str, Any]:
        if screen_id == "offline":
            raise ConnectionError("synthetic provider unavailable")
        return {"screen_id": screen_id, "_status": "OK", "fields": {
            "ndg": {"value": screen_id, "confidence": 1.0},
            "tipo": {"value": "Originale", "confidence": 1.0},
        }}


def _saved_session(directory: Path) -> None:
    client = LocalExtractionClient(pipeline=_OfflineExtraction(), recovery_dir=directory)
    try:
        for page in ("111", "offline", "222"):
            client.ingest_frame("synthetic", Image.new("L", (3, 3)), page_type=page)
        deadline = time.monotonic() + 10
        while client.capture_counts("synthetic") != (3, 3):
            assert time.monotonic() < deadline
            time.sleep(0.01)
        client.set_column_label("tipo", "Voce verificata")
        client.set_correction("synthetic", "111", "tipo", "Confermato")
        client.set_cell_draft("synthetic", "111", "tipo", "Bozza non confermata")
    finally:
        client.shutdown()


def test_offline_export_keeps_the_ordered_prefix_and_leaves_the_session_recoverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, destination = tmp_path / "source", tmp_path / "output"
    monkeypatch.setenv("EDGE_AGENT_BACKUP_DIR", str(source))
    _saved_session(source)
    with closing(RecoveryStore(source)) as store:
        before = {key: store.read(key) for key in store.keys()}
    entry = Path(__file__).resolve().parents[1] / "src" / "edge-agent" / "edge_agent.py"
    env = {**os.environ, "EDGE_AGENT_RECOVERY_DIR": str(source),
           "LLM_MODEL": "provider-unavailable", "PYTHON_DOTENV_DISABLED": "1",
           "LLM_API_KEY": "", "OPENAI_API_KEY": "", "GEMINI_API_KEY": "", "GOOGLE_API_KEY": "",
           "QT_QPA_PLATFORM": "absent-on-purpose"}
    run = subprocess.run([sys.executable, str(entry), "--recovery-export", str(destination)],
                         env=env, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    books = list(destination.glob("*.xlsx"))
    assert len(books) == 1 and "PARZIALE" in books[0].stem
    with closing(load_workbook(books[0], read_only=True)) as book:
        _, labels, row = list(book.active.values)
        assert row[0] == "111"
        assert row[labels.index("Voce verificata")] == "Confermato"
    report = (destination / "riepilogo.txt").read_text(encoding="utf-8-sig")
    assert "Fotogrammi da elaborare: 2" in report
    assert "Risultati completati dopo il primo fotogramma in attesa: 1" in report
    assert "Bozza da confermare: presente" in report
    with closing(RecoveryStore(source)) as store:
        assert {key: store.read(key) for key in store.keys()} == before


def test_offline_export_refuses_an_existing_destination(tmp_path: Path) -> None:
    from recovery_export import export_recovery

    destination = tmp_path / "operator"
    destination.mkdir()
    workbook = destination / "sessione-001.xlsx"
    workbook.write_bytes(b"operator workbook")
    with pytest.raises(FileExistsError):
        export_recovery(tmp_path / "absent", destination)
    assert workbook.read_bytes() == b"operator workbook"


def test_offline_export_refuses_a_missing_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from recovery_export import export_recovery

    monkeypatch.setenv("EDGE_AGENT_BACKUP_DIR", str(tmp_path / "backup"))
    directory = tmp_path / "absent"
    with pytest.raises(OSError):
        export_recovery(directory, tmp_path / "export")
    assert not directory.exists()
