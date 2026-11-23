"""Gestione Documentale and its PDF viewer (site/docs.js, site/docs.css): served, inlined offline, protected.

The page itself is exercised in Chrome by tests/browser/bper_documents.cjs.
"""

from collections.abc import Iterator
from html.parser import HTMLParser
from http.client import HTTPConnection, HTTPResponse
from http.server import ThreadingHTTPServer
from pathlib import Path
import re
from threading import Thread

import pytest

from bper_simulator_export import export_simulator
from serve_bper_simulator import create_server

SITE = Path(__file__).resolve().parents[1] / "bper-emulator" / "site"
ASSETS = {"/docs.js": "text/javascript; charset=utf-8", "/docs.css": "text/css; charset=utf-8"}


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ThreadingHTTPServer]:
    db = tmp_path_factory.mktemp("docs-api") / "synthetic.sqlite3"
    with create_server(port=0, db_path=db) as instance:
        thread = Thread(target=instance.serve_forever, daemon=True)
        thread.start()
        yield instance
        instance.shutdown()
        thread.join()


def fetch(server: ThreadingHTTPServer, path: str, host: str = "127.0.0.1") -> tuple[HTTPResponse, bytes]:
    connection = HTTPConnection(*server.server_address, timeout=5)
    try:
        try:
            connection.connect()
        except PermissionError:
            pytest.skip("This environment denies local TCP client connections")
        connection.request("GET", path, headers={"Host": host})
        response = connection.getresponse()
        return response, response.read()
    finally:
        connection.close()


def test_home_page_links_the_documents_page_assets(server: ThreadingHTTPServer) -> None:
    _, body = fetch(server, "/")
    assert set(ASSETS) <= set(re.findall(r'(?:src|href)="(/[^"]+)"', body.decode("utf-8")))


@pytest.mark.parametrize("asset", sorted(ASSETS))
def test_documents_page_assets_are_served_as_their_files(server: ThreadingHTTPServer, asset: str) -> None:
    response, body = fetch(server, asset)
    assert response.status == 200
    assert response.getheader("Content-Type") == ASSETS[asset]
    assert response.getheader("Cross-Origin-Resource-Policy") == "same-origin"
    assert body == (SITE / asset.lstrip("/")).read_bytes()


@pytest.mark.parametrize("asset", sorted(ASSETS))
def test_documents_page_assets_refuse_a_foreign_host(server: ThreadingHTTPServer, asset: str) -> None:
    response, _ = fetch(server, asset, host="external.example")
    assert response.status == 403


@pytest.mark.parametrize("path", ["/docs.js/../.env", "/site/docs.js", "/docs.json", "/docs.css/"])
def test_paths_near_the_documents_assets_are_not_served(server: ThreadingHTTPServer, path: str) -> None:
    response, _ = fetch(server, path)
    assert response.status == 404


def test_documents_script_runs_before_the_application_starts() -> None:
    # app.js renders the detail at start, and the detail hosts the documents page.
    page = (SITE / "index.html").read_text(encoding="utf-8")
    assert page.index('src="/docs.js"') < page.index('src="/app.js"')


class Parts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.external: list[str] = []
        self.blocks: list[tuple[str, str]] = []
        self.open: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        url = dict(attrs).get("src") or dict(attrs).get("href")
        if tag in {"script", "link", "img"} and url and not url.startswith("data:"):
            self.external.append(url)
        self.open = tag if tag in {"script", "style"} else None

    def handle_endtag(self, tag: str) -> None:
        self.open = None

    def handle_data(self, data: str) -> None:
        if self.open:
            self.blocks.append((self.open, data.strip()))


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> Parts:
    directory = tmp_path_factory.mktemp("docs-portable")
    target = directory / "simulatore.html"
    export_simulator(target, db_path=directory / "demo.sqlite3")
    parts = Parts()
    parts.feed(target.read_text(encoding="utf-8"))
    parts.close()
    return parts


def test_portable_page_inlines_the_documents_styles(exported: Parts) -> None:
    assert exported.external == []
    assert ("style", (SITE / "docs.css").read_text(encoding="utf-8").strip()) in exported.blocks


def test_portable_page_inlines_the_documents_script_before_the_application(exported: Parts) -> None:
    scripts = [text for tag, text in exported.blocks if tag == "script"]
    position = scripts.index((SITE / "docs.js").read_text(encoding="utf-8").strip())
    assert position < scripts.index((SITE / "app.js").read_text(encoding="utf-8").strip())
