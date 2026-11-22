"""HTTP contract for the local BPER capture simulator."""

from collections.abc import Iterator
import csv
from http.client import HTTPConnection, HTTPResponse
import importlib.util
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import re
from socket import socket
import sqlite3
import subprocess
import sys
from threading import Thread
from unittest.mock import Mock

import pytest

from bper_site_fixture import assert_site_pixels
from serve_bper_simulator import create_server

REPO = Path(__file__).resolve().parents[1]
SCHEDA_PAGE = "/schede/SchedaPrivati/"
# The customer of practice 52062600, whose Scheda Privati the five repository screenshots show.
REFERENCE_SCHEDA = "/api/scheda/036214640.json"


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ThreadingHTTPServer]:
    db = tmp_path_factory.mktemp("api") / "synthetic.sqlite3"
    with create_server(port=0, db_path=db) as instance:
        yield instance


@pytest.fixture(scope="module")
def reference_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ThreadingHTTPServer]:
    db = tmp_path_factory.mktemp("reference-api") / "synthetic.sqlite3"
    with create_server(port=0, db_path=db, include_reference=True) as instance:
        yield instance


def get(server: ThreadingHTTPServer, path: str, host: str = "127.0.0.1") -> HTTPResponse:
    """Exercise the real HTTP request handler, with a byte stream at the socket boundary."""
    channel = Mock(spec=socket)
    request = f"GET {path} HTTP/1.1\r\nHost: {host}\r\n\r\n".encode("ascii")
    channel.makefile.return_value = BytesIO(request)
    output = BytesIO()
    channel.sendall.side_effect = output.write
    server.finish_request(channel, ("127.0.0.1", 12345))
    channel.makefile.return_value = BytesIO(output.getvalue())
    response = HTTPResponse(channel)
    response.begin()
    return response


def test_server_binds_to_loopback(server: ThreadingHTTPServer) -> None:
    assert server.server_address[0] == "127.0.0.1"


def test_accepts_a_browser_connection_on_loopback(server: ThreadingHTTPServer) -> None:
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection(*server.server_address, timeout=3)
    try:
        try:
            connection.connect()
        except PermissionError:
            pytest.skip("This environment denies local TCP client connections")
        connection.request("GET", "/api/practices.json")
        assert connection.getresponse().status == 200
    finally:
        connection.close()
        server.shutdown()
        thread.join()


def test_refuses_a_foreign_host_header(server: ThreadingHTTPServer) -> None:
    with get(server, "/reference/1.png", host="external.example") as response:
        assert response.status == 403


def test_home_page_can_load_all_its_local_assets(server: ThreadingHTTPServer) -> None:
    with get(server, "/?capture=1") as response:
        assert response.status == 200
        page = response.read().decode("utf-8")
    assets = re.findall(r'(?:src|href)="(/[^"]+)"', page)
    assert assets
    for asset in assets:
        with get(server, asset) as response:
            assert response.status == 200, asset
            assert response.read(), asset


def test_scheda_privati_page_can_load_all_its_local_assets(server: ThreadingHTTPServer) -> None:
    with get(server, SCHEDA_PAGE) as response:
        assert response.status == 200
        assert response.getheader("Content-Type") == "text/html; charset=utf-8"
        page = response.read().decode("utf-8")
    assert "<title>BPER Scheda Privati</title>" in page
    assets = re.findall(r'(?:src|href)="(/[^"]+)"', page)
    content_types = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}
    assert {Path(asset).suffix for asset in assets} == set(content_types)
    for asset in assets:
        with get(server, asset) as response:
            assert response.status == 200, asset
            assert response.getheader("Content-Type") == content_types[Path(asset).suffix], asset
            assert response.read(), asset


def scheda_privati_field_keys() -> set[str]:
    """The 13 extracted fields whose source page is Scheda Privati, from the canonical definitions."""
    path = REPO / "src" / "extraction" / "field_definitions.py"
    # Load the file alone: importing the package would pull in the VLM runtime.
    spec = importlib.util.spec_from_file_location("scheda_field_definitions", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {key for key, value in module.CANONICAL_FIELD_DEFINITIONS.items() if value["page_key"] == "scheda_privati"}


def squash(text: str) -> str:
    return " ".join(text.split())


def test_reference_scheda_privati_reproduces_the_transcribed_values(reference_server: ThreadingHTTPServer) -> None:
    with get(reference_server, REFERENCE_SCHEDA) as response:
        assert response.status == 200
        assert response.getheader("Content-Type") == "application/json; charset=utf-8"
        scheda = json.loads(response.read())
    assert len(scheda_privati_field_keys()) == 13
    assert set(scheda["fields"]) == scheda_privati_field_keys()
    with (REPO / "data" / "dataset" / "valori.csv").open(encoding="utf-8-sig", newline="") as source:
        rows = [row for row in csv.DictReader(source, delimiter=";")
                if row["Schermata"].startswith("52062600/scheda-privati-")]
    assert len(rows) == 38
    for row in rows:
        key, value = row["Chiave"], row["Valore"]
        if key == "ndg":
            assert scheda["ndg"] == value
        elif key == "denominazione":
            assert scheda["name"] == value
        elif key == "note_scheda_privati":
            # Each screenshot shows only the paragraphs its scroll position reveals.
            assert squash(value) in squash(scheda["fields"][key]), row["Schermata"]
        elif key == "datore_di_lavoro_anagrafica" and row["Esito"] == "VUOTO":
            # Pending decision: screenshot 01 shows the employer "AL - POSA SRLS", while 02-05 show
            # the same box (same page position) emptied. One page state reproduces 01 only.
            assert row["Schermata"] != "52062600/scheda-privati-01"
        else:
            assert scheda["fields"][key] == value, row["Schermata"]


def test_interactive_reference_profile_contains_the_original_subjects(reference_server: ThreadingHTTPServer) -> None:
    with get(reference_server, "/reference/practice.json") as response:
        assert response.status == 200
        assert response.getheader("Content-Type") == "application/json; charset=utf-8"
        profile = json.loads(response.read())
    assert profile["ndg"] == "26871394"
    assert len(profile["subjects"]) == 3


@pytest.mark.parametrize("step", range(1, 10))
def test_reference_route_serves_only_the_website_area(reference_server: ThreadingHTTPServer, step: int) -> None:
    with get(reference_server, f"/reference/{step}.png") as response:
        assert response.status == 200
        assert response.getheader("Content-Type") == "image/png"
        assert_site_pixels(step, response.read())


@pytest.mark.parametrize("path", [
    "/.env", "/data/", "/reference/10.png", "/app.js/../.env",
    "/reference/practice.json", "/reference/1.png", "/api/truth/missing.csv", "/api/truth/../../.env",
    REFERENCE_SCHEDA, "/api/scheda/99999999.json", "/api/scheda/../../.env",
    "/schede/SchedaPrivati/../.env", "/schede/SchedaPrivati/reference.json",
])
def test_rejects_paths_outside_the_simulator(server: ThreadingHTTPServer, path: str) -> None:
    with get(server, path) as response:
        assert response.status == 404


def test_catalog_reads_existing_sqlite_dossiers_on_every_request(tmp_path: Path) -> None:
    db = tmp_path / "custom.sqlite3"
    with create_server(port=0, db_path=db) as instance:
        with get(instance, "/api/practices.json") as response:
            assert response.status == 200
            data = json.loads(response.read())
        assert data["hasReference"] is False
        assert len(data["practices"]) == 64
        first = next(p for p in data["practices"] if p["key"] == "demo")
        assert first["name"] == "ALBA MARTINA"
        assert first["availableSteps"] == list(range(1, 10))
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE subject SET name = ? WHERE ndg = ?", ("PROVA EMILIA", first["ndg"]))
        with get(instance, "/api/practices.json") as response:
            assert next(p for p in json.loads(response.read())["practices"] if p["key"] == "demo")["name"] == "PROVA EMILIA"


def test_practice_truth_download_matches_selected_dossier(server: ThreadingHTTPServer) -> None:
    with get(server, "/api/truth/demo.csv") as response:
        assert response.status == 200
        assert response.getheader("Content-Type") == "text/csv; charset=utf-8"
        truth = response.read().decode("utf-8-sig")
    assert "Fotogramma,Denominazione da attribuire,Valore rilevato" in truth
    assert "ALBA MARTINA" in truth and "90000001" in truth
    assert "LUNARDI" not in truth


def test_export_cli_writes_a_standalone_page_without_starting_a_server(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "bper-emulator" / "serve_bper_simulator.py"
    output = tmp_path / "offline.html"
    result = subprocess.run(
        [sys.executable, str(script), "--db", str(tmp_path / "new.sqlite3"), "--export", str(output)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "<html" in output.read_text(encoding="utf-8").lower()
