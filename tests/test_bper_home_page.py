"""The Home and Ricerca Pratica pages of Nuova PEF: served by the local simulator and carried by its offline file."""

from collections.abc import Iterator
from http.client import HTTPConnection
from html.parser import HTMLParser
from pathlib import Path
from threading import Thread

import pytest

from bper_simulator_export import export_simulator
from serve_bper_simulator import create_server

SITE = Path(__file__).resolve().parents[1] / "bper-emulator" / "site"
ASSETS = {
    "/home.js": "text/javascript; charset=utf-8",
    "/home.css": "text/css; charset=utf-8",
    "/search.js": "text/javascript; charset=utf-8",
    "/search.css": "text/css; charset=utf-8",
}


class Resources(HTMLParser):
    """External scripts and styles a page loads."""

    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"script", "link"} and (url := attributes.get("src") or attributes.get("href")):
            if not url.startswith("data:"):
                self.urls.append(url)


def resources(html: str) -> list[str]:
    parser = Resources()
    parser.feed(html)
    parser.close()
    return parser.urls


@pytest.fixture(scope="module")
def port(tmp_path_factory: pytest.TempPathFactory) -> Iterator[int]:
    with create_server(port=0, db_path=tmp_path_factory.mktemp("home") / "synthetic.sqlite3") as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield server.server_port
        server.shutdown()


def fetch(port: int, path: str) -> tuple[int, str, bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type", ""), response.read()
    finally:
        connection.close()


@pytest.mark.parametrize("path", sorted(ASSETS))
def test_server_serves_each_home_and_search_asset_from_the_site_folder(port: int, path: str) -> None:
    status, content_type, body = fetch(port, path)
    assert (status, content_type) == (200, ASSETS[path])
    assert body == (SITE / path.removeprefix("/")).read_bytes()


def test_the_simulator_page_loads_the_home_and_search_assets(port: int) -> None:
    status, _, body = fetch(port, "/")
    assert status == 200
    assert set(ASSETS) <= set(resources(body.decode("utf-8")))


def test_the_offline_file_inlines_the_home_and_search_pages(tmp_path: Path) -> None:
    target = tmp_path / "simulatore.html"
    export_simulator(target, db_path=tmp_path / "pratiche.sqlite3")
    html = target.read_text(encoding="utf-8")
    assert resources(html) == []
    for path in ASSETS:
        assert (SITE / path.removeprefix("/")).read_text(encoding="utf-8") in html
