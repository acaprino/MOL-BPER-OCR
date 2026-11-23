"""Loading states of the simulator (site/loading.js, site/loading.css): served, linked before their users, inlined offline.

The states themselves, and their timing, are exercised in Chrome by tests/browser/bper_loading.cjs.
"""

from collections.abc import Iterator
from html.parser import HTMLParser
from http.client import HTTPConnection
from pathlib import Path
import re
from threading import Thread

import numpy as np
import pytest

from bper_simulator_export import export_simulator
from serve_bper_simulator import create_server

SITE = Path(__file__).resolve().parents[1] / "bper-emulator" / "site"
ASSETS = {"/loading.js": "text/javascript; charset=utf-8", "/loading.css": "text/css; charset=utf-8"}
# Every script that asks BperLoading whether to wait.
USERS = ["/list.js", "/search.js", "/app.js"]


@pytest.fixture(scope="module")
def port(tmp_path_factory: pytest.TempPathFactory) -> Iterator[int]:
    with create_server(port=0, db_path=tmp_path_factory.mktemp("loading") / "synthetic.sqlite3") as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield server.server_port
        server.shutdown()
        thread.join()


def fetch(port: int, path: str) -> tuple[int, str, bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type", ""), response.read()
    finally:
        connection.close()


@pytest.mark.parametrize("path", sorted(ASSETS))
def test_server_serves_each_loading_asset_from_the_site_folder(port: int, path: str) -> None:
    status, content_type, body = fetch(port, path)
    assert (status, content_type) == (200, ASSETS[path])
    assert body == (SITE / path.removeprefix("/")).read_bytes()


def test_the_simulator_page_links_the_loading_assets(port: int) -> None:
    _, _, body = fetch(port, "/")
    assert set(ASSETS) <= set(re.findall(r'(?:src|href)="(/[^"]+)"', body.decode("utf-8")))


@pytest.mark.parametrize("user", USERS)
def test_the_loading_script_runs_before_each_script_that_uses_it(user: str) -> None:
    page = (SITE / "index.html").read_text(encoding="utf-8")
    assert page.index('src="/loading.js"') < page.index(f'src="{user}"')


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
    directory = tmp_path_factory.mktemp("loading-portable")
    target = directory / "simulatore.html"
    export_simulator(target, db_path=directory / "demo.sqlite3")
    parts = Parts()
    parts.feed(target.read_text(encoding="utf-8"))
    parts.close()
    return parts


def test_portable_page_inlines_the_loading_styles(exported: Parts) -> None:
    assert exported.external == []
    assert ("style", (SITE / "loading.css").read_text(encoding="utf-8").strip()) in exported.blocks


def test_portable_page_inlines_the_loading_script_before_the_application(exported: Parts) -> None:
    scripts = [text for tag, text in exported.blocks if tag == "script"]
    position = scripts.index((SITE / "loading.js").read_text(encoding="utf-8").strip())
    assert position < scripts.index((SITE / "app.js").read_text(encoding="utf-8").strip())


@pytest.mark.parametrize("gap_start", [0, 90, 180, 270])
def test_measure_finds_the_centre_of_a_three_quarter_ring_whatever_its_gap(gap_start: int) -> None:
    from PIL import Image, ImageDraw

    from measure_loading import TEAL, ring_centre

    image = Image.new("RGB", (200, 160), (253, 251, 249))
    # A teal ring 50 px across, centred on (101.5, 77.5), open over a quarter turn.
    ImageDraw.Draw(image).arc((76.5, 52.5, 126.5, 102.5), gap_start + 90, gap_start + 360, fill=(31, 145, 155), width=5)
    x, y = ring_centre(np.asarray(image), (95, 80), TEAL)
    assert abs(x - 101.5) <= 0.75 and abs(y - 77.5) <= 0.75
