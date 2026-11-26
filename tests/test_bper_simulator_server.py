"""HTTP contract for the local BPER capture simulator."""

from collections.abc import Iterator
from contextlib import closing
import csv
from http.client import HTTPConnection, HTTPResponse
import importlib.util
from http.server import ThreadingHTTPServer
from io import BytesIO, StringIO
import json
from pathlib import Path
import re
from socket import create_connection as socket_connection, socket
import sqlite3
import subprocess
import sys
from threading import Thread
from unittest.mock import Mock

import pytest

from bper_archive import archive_profiles
from bper_site_fixture import (
    ALL_ROLES, archive_identities, assert_site_pixels, fictitious_profile, leaks, reference_scheda,
    scheda_personal_values, sealed_only, strings, write_profiles,
)
from bper_synthetic_db import APPLICATION_ID, SCHEMA_VERSION, synthetic_practices
import serve_bper_simulator
from serve_bper_simulator import create_server

REPO = Path(__file__).resolve().parents[1]
SCHEDA_PAGE = "/schede/SchedaPrivati/"
# The customer of practice 52062600, whose Scheda Privati the five repository screenshots show.
REFERENCE_SCHEDA = f"/api/scheda/{reference_scheda()['ndg']}.json"


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


@pytest.fixture(scope="module")
def archive_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ThreadingHTTPServer]:
    db = tmp_path_factory.mktemp("archive-api") / "synthetic.sqlite3"
    with create_server(port=0, db_path=db, include_archive=True) as instance:
        yield instance


@pytest.fixture(scope="module")
def sealed_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ThreadingHTTPServer]:
    # In memory only: the responses of the test practices are never written to disk (ADR 0027).
    db = tmp_path_factory.mktemp("sealed-api") / "synthetic.sqlite3"
    with create_server(port=0, db_path=db, include_archive=True, include_test=True) as instance:
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


def test_default_server_serves_no_real_personal_values_of_the_reference_scheda(server: ThreadingHTTPServer) -> None:
    with get(server, REFERENCE_SCHEDA) as response:
        assert response.status == 404
    with get(server, SCHEDA_PAGE) as response:
        bodies = [response.read().decode("utf-8")]
    for path in [*re.findall(r'(?:src|href)="(/[^"]+)"', bodies[0]), "/api/practices.json"]:
        with get(server, path) as response:
            bodies.append(response.read().decode("utf-8"))
    for value in scheda_personal_values():
        assert not any(value in body for body in bodies)


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
        body = response.read().decode("utf-8")
    assert all(value in body for value in scheda_personal_values())
    scheda = json.loads(body)
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


def test_scheda_api_serves_the_scheda_privati_of_every_synthetic_practice(server: ThreadingHTTPServer) -> None:
    with get(server, "/api/practices.json") as response:
        practices = json.loads(response.read())["practices"]
    for practice in practices:
        with get(server, f"/api/scheda/{practice['ndg']}.json") as response:
            assert response.status == 200, practice["key"]
            assert response.getheader("Content-Type") == "application/json; charset=utf-8"
            assert json.loads(response.read()) == practice["scheda"]
        assert [s["name"] for s in practice["schedaStates"]][:2] == ["scheda-privati-01", "scheda-privati-02"]


def test_scheda_api_reads_the_sqlite_database_on_every_request(tmp_path: Path) -> None:
    db = tmp_path / "custom.sqlite3"
    with create_server(port=0, db_path=db) as instance:
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE scheda SET notes = ? WHERE ndg = ?", ("Nota aggiornata.\n", "90000001"))
        with get(instance, "/api/scheda/90000001.json") as response:
            assert json.loads(response.read())["fields"]["note_scheda_privati"] == "Nota aggiornata.\n"


def test_practice_truth_download_includes_the_scheda_privati_states(server: ThreadingHTTPServer) -> None:
    with get(server, "/api/truth/demo.csv") as response:
        rows = list(csv.DictReader(StringIO(response.read().decode("utf-8-sig"), newline="")))
    states = {row["Fotogramma"] for row in rows if row["Fotogramma"].startswith("scheda-privati-")}
    assert {"scheda-privati-01", "scheda-privati-02"} <= states
    assert any(row["Denominazione da attribuire"] == "Note Scheda Privati" for row in rows)


def test_practice_truth_endpoint_serves_one_row_per_field_of_the_practice(server: ThreadingHTTPServer) -> None:
    with get(server, "/api/truth-practice/demo.csv") as response:
        assert response.status == 200
        assert response.getheader("Content-Type") == "text/csv; charset=utf-8"
        rows = list(csv.DictReader(StringIO(response.read().decode("utf-8-sig"), newline=""), delimiter=";"))
    values = {row["Chiave"]: row["Valore"] for row in rows}
    assert len(rows) == len(values) == 45
    assert (values["ndg"], values["denominazione"]) == ("90000001", "ALBA MARTINA")


def test_practice_truth_endpoint_is_behind_the_same_gates(server: ThreadingHTTPServer,
                                                          archive_server: ThreadingHTTPServer) -> None:
    key = next(p["key"] for p in archive_profiles())
    for path, status in ((f"/api/truth-practice/{key}.csv", 404), ("/api/truth-practice/missing.csv", 404),
                         ("/api/truth-practice/../../.env.csv", 404)):
        with get(server, path) as response:
            assert response.status == status, path
    with get(archive_server, f"/api/truth-practice/{key}.csv") as response:
        assert response.status == 200


def test_practice_truth_download_matches_selected_dossier(server: ThreadingHTTPServer) -> None:
    with get(server, "/api/truth/demo.csv") as response:
        assert response.status == 200
        assert response.getheader("Content-Type") == "text/csv; charset=utf-8"
        truth = response.read().decode("utf-8-sig")
    assert "Fotogramma,Denominazione da attribuire,Valore rilevato" in truth
    assert "ALBA MARTINA" in truth and "90000001" in truth
    assert "LUNARDI" not in truth


# 1: before the Scheda Privati. 2: without practice types, offices and income kinds. 3: without the product table.
# 6: without the autonomous contract and the one-payment self-employed.
OLDER_VERSIONS = (1, 2, 3, 6)


def served_text(server: ThreadingHTTPServer) -> str:
    """Everything the server shows: the pages and their assets, the catalogue, every truth CSV and scheda."""
    bodies = []
    for page in ("/", SCHEDA_PAGE):
        with get(server, page) as response:
            html = response.read().decode("utf-8")
        bodies.append(html)
        for asset in re.findall(r'(?:src|href)="(/[^"]+)"', html):
            with get(server, asset) as response:
                bodies.append(response.read().decode("utf-8"))
    with get(server, "/api/practices.json") as response:
        catalogue = response.read().decode("utf-8")
    bodies.append(strings(catalogue))
    for practice in json.loads(catalogue)["practices"]:
        with get(server, f"/api/truth/{practice['key']}.csv") as response:
            bodies.append(response.read().decode("utf-8-sig"))
        if practice["scheda"]:
            with get(server, f"/api/scheda/{practice['scheda']['ndg']}.json") as response:
                bodies.append(strings(response.read().decode("utf-8")))
    return "\n".join(bodies)


def open_and_sealed() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Identities of the training and control practices, and those only the test practices carry."""
    return archive_identities({"addestramento", "controllo"}), sealed_only()


def test_default_server_serves_no_value_of_the_archive(server: ThreadingHTTPServer) -> None:
    assert leaks(served_text(server), archive_identities(ALL_ROLES)) == {"ndg": 0, "name": 0, "note": 0}


def test_default_server_has_no_scheda_of_an_archive_customer(server: ThreadingHTTPServer) -> None:
    schede = [p["scheda"]["ndg"] for p in archive_profiles() if p["scheda"]]
    statuses = []
    for ndg in schede:
        with get(server, f"/api/scheda/{ndg}.json") as response:
            statuses.append(response.status)
    all_refused = bool(schede) and statuses == [404] * len(schede)
    assert all_refused  # a boolean, so a failure prints no real NDG


def test_include_archive_serves_the_training_and_control_practices_only(archive_server: ThreadingHTTPServer) -> None:
    opened, sealed = open_and_sealed()
    text = served_text(archive_server)
    found = leaks(text, opened)
    assert found["ndg"] == len(opened["ndg"]) and found["name"] > 0 and found["note"] > 0
    assert leaks(text, sealed) == {"ndg": 0, "name": 0, "note": 0}


def test_include_test_adds_the_test_practices(sealed_server: ThreadingHTTPServer) -> None:
    _, sealed = open_and_sealed()
    found = leaks(served_text(sealed_server), sealed)
    assert found["ndg"] == len(sealed["ndg"]) and found["name"] > 0 and found["note"] > 0


def test_catalogue_marks_every_archive_practice_with_its_role(sealed_server: ThreadingHTTPServer) -> None:
    with get(sealed_server, "/api/practices.json") as response:
        practices = json.loads(response.read())["practices"]
    roles = {p["role"] for p in practices if p["key"].startswith("arch-")}
    assert roles == ALL_ROLES
    assert {p["role"] for p in practices if not p["key"].startswith("arch-")} == {"sintetica"}


def test_with_the_reference_too_the_archive_scheda_of_its_customer_is_served(tmp_path: Path) -> None:
    # The fixture of the same customer carries invented note text; the archive's authored page wins.
    expected = next(p["scheda"] for p in archive_profiles() if p["scheda"])
    with create_server(port=0, db_path=tmp_path / "s.sqlite3", include_reference=True, include_archive=True) as both:
        with get(both, f"/api/scheda/{expected['ndg']}.json") as response:
            served = json.loads(response.read())
    same = served == expected  # a boolean, so a failure prints no value
    assert same


def older_database(path: Path, version: int) -> bytes:
    """A database this simulator wrote at an earlier schema version."""
    con = sqlite3.connect(path)
    con.execute(f"PRAGMA application_id = {APPLICATION_ID}")
    con.execute(f"PRAGMA user_version = {version}")
    con.execute("CREATE TABLE practice (key TEXT PRIMARY KEY)")
    con.commit()
    con.close()
    return path.read_bytes()


@pytest.mark.parametrize("version", OLDER_VERSIONS)
def test_server_refuses_to_start_on_a_named_database_of_an_older_version(tmp_path: Path, version: int) -> None:
    db = tmp_path / "mio-archivio.sqlite3"
    contents = older_database(db, version)
    with pytest.raises(ValueError, match=r"mio-archivio\.sqlite3"):
        create_server(port=0, db_path=db)
    assert db.read_bytes() == contents and [p.name for p in tmp_path.iterdir()] == [db.name]


@pytest.mark.parametrize("version", OLDER_VERSIONS)
def test_cli_refuses_an_older_database_given_with_db(tmp_path: Path, version: int) -> None:
    db = tmp_path / "mio-archivio.sqlite3"
    contents = older_database(db, version)
    script = REPO / "bper-emulator" / "serve_bper_simulator.py"
    result = subprocess.run([sys.executable, str(script), "--db", str(db), "--export", str(tmp_path / "x.html")],
                            cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 1
    assert "mio-archivio.sqlite3" in result.stderr
    assert db.read_bytes() == contents and [p.name for p in tmp_path.iterdir()] == [db.name]


def test_cli_creates_no_database_when_the_export_would_overwrite_it(tmp_path: Path) -> None:
    same = tmp_path / "stesso-file.sqlite3"
    script = REPO / "bper-emulator" / "serve_bper_simulator.py"
    result = subprocess.run([sys.executable, str(script), "--db", str(same), "--export", str(same)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("version", OLDER_VERSIONS)
def test_cli_rebuilds_the_default_database_of_an_older_version_and_keeps_the_old_one(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], version: int) -> None:
    # The launcher passes no --db: the default file is the only one the simulator may replace.
    default = tmp_path / "local" / "bper-synthetic.sqlite3"
    default.parent.mkdir()
    contents = older_database(default, version)
    monkeypatch.setattr(serve_bper_simulator, "DEFAULT_DB", default)
    monkeypatch.setattr(sys, "argv", ["serve_bper_simulator.py", "--export", str(tmp_path / "sito.html")])
    serve_bper_simulator.main()
    backup = default.with_name(f"bper-synthetic.v{version}.bak.sqlite3")
    assert backup.read_bytes() == contents
    assert len(synthetic_practices(default)) == 64
    with closing(sqlite3.connect(default)) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    lines = [line for line in capsys.readouterr().out.splitlines() if backup.name in line]
    assert len(lines) == 1
    assert (tmp_path / "sito.html").exists()


def exported_keys(page: Path) -> set[str]:
    text = page.read_text(encoding="utf-8")
    start = text.index("window.BperOffline = ") + len("window.BperOffline = ")
    return {p["key"] for p in json.loads(text[start:text.index(";</script>", start)])["practices"]}


@pytest.mark.parametrize("flags, shown", [
    ([], {"fittizia-001"}),
    (["--include-test"], {"fittizia-001", "fittizia-002"}),
])
def test_cli_adds_profile_files_and_a_test_practice_only_with_include_test(
        tmp_path: Path, flags: list[str], shown: set[str]) -> None:
    profiles = write_profiles(tmp_path / "profili.json",
                              [fictitious_profile("fittizia-001"), fictitious_profile("fittizia-002", "test")])
    script = REPO / "bper-emulator" / "serve_bper_simulator.py"
    page = tmp_path / "sito.html"
    result = subprocess.run([sys.executable, str(script), "--db", str(tmp_path / "s.sqlite3"), "--profiles",
                             str(profiles), *flags, "--export", str(page)], cwd=tmp_path, capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert {key for key in exported_keys(page) if key.startswith("fittizia-")} == shown


def test_server_refuses_two_practices_whose_different_schede_share_a_customer(tmp_path: Path) -> None:
    # The page is looked up by NDG: one scheda would hide the other while its truth still asserted it.
    other = fictitious_profile("fittizia-002")
    other["scheda"]["name"] = "ALTRO CLIENTE"
    profiles = write_profiles(tmp_path / "ombra.json", [other])
    with pytest.raises(ValueError, match="fittizia-002"):
        create_server(port=0, db_path=tmp_path / "s.sqlite3", profiles=[profiles])


def test_server_refuses_a_profile_file_that_reuses_a_catalogue_key(tmp_path: Path) -> None:
    profiles = write_profiles(tmp_path / "doppione.json", [fictitious_profile("demo")])
    with pytest.raises(ValueError, match="demo"):
        create_server(port=0, db_path=tmp_path / "s.sqlite3", profiles=[profiles])


def test_cli_refuses_a_profile_file_that_does_not_validate(tmp_path: Path) -> None:
    broken = fictitious_profile()
    del broken["notes"]
    profiles = write_profiles(tmp_path / "rotto.json", [broken])
    script = REPO / "bper-emulator" / "serve_bper_simulator.py"
    result = subprocess.run([sys.executable, str(script), "--db", str(tmp_path / "s.sqlite3"), "--profiles",
                             str(profiles), "--export", str(tmp_path / "sito.html")], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 1 and "rotto.json" in result.stderr and "notes" in result.stderr
    assert not (tmp_path / "sito.html").exists()


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


def test_server_queues_a_burst_of_connections_it_has_not_accepted_yet(tmp_path: Path) -> None:
    # Chrome opens six connections per page and the browser tests run pages side by side: a connection that arrives
    # while the server is busy waits in the listen queue. With the standard queue of 5 Windows refuses the sixth,
    # and a script of the page goes missing. The server is not serving here, so nothing leaves the queue.
    with create_server(port=0, db_path=tmp_path / "burst.sqlite3") as server:
        connections = []
        try:
            for _ in range(40):
                connections.append(socket_connection(("127.0.0.1", server.server_port), timeout=5))
        finally:
            for connection in connections:
                connection.close()
    assert len(connections) == 40
