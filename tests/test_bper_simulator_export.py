"""The portable simulator must run with only its exported HTML file available."""

from base64 import b64decode
from html.parser import HTMLParser
import json
from pathlib import Path
import sqlite3

import pytest

from bper_site_fixture import assert_site_pixels
from bper_simulator_export import export_simulator


class Document(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.resources: list[str] = []
        self.scripts: list[str] = []
        self.in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"script", "img", "link"}:
            url = attributes.get("src") or attributes.get("href")
            if url and not url.startswith("data:"):
                self.resources.append(url)
        self.in_script = tag == "script"

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_script = False

    def handle_data(self, data: str) -> None:
        if self.in_script:
            self.scripts.append(data.strip())


def read_html(target: Path) -> Document:
    document = Document()
    document.feed(target.read_text(encoding="utf-8"))
    document.close()
    return document


def offline_payload(exported: Document) -> dict:
    config = next(script for script in exported.scripts if script.startswith("window.BperOffline"))
    return json.loads(config.split("=", 1)[1].rstrip(";"))


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> Document:
    directory = tmp_path_factory.mktemp("portable")
    target = directory / "simulatore.html"
    export_simulator(target, db_path=directory / "demo.sqlite3")
    return read_html(target)


def test_portable_page_embeds_styles_scripts_and_images(exported: Document) -> None:
    assert exported.resources == []


def test_portable_site_only_contains_synthetic_practices_by_default(exported: Document) -> None:
    dataset = offline_payload(exported)
    assert dataset["hasReference"] is False
    assert "practice" not in dataset and "screens" not in dataset
    assert {p["key"] for p in dataset["practices"]} == dataset["truth"].keys()
    assert len(dataset["truth"]) == 64
    assert "90000001" in dataset["truth"]["demo"]
    assert "LUNARDI" not in json.dumps(dataset)


def test_portable_site_hosts_the_scheda_privati_page_without_external_files(exported: Document) -> None:
    page = offline_payload(exported)["schedaPage"]
    assert "<title>BPER Scheda Privati</title>" in page
    scheda = Document()
    scheda.feed(page)
    scheda.close()
    assert scheda.resources == []
    assert any("/api/scheda/" in script for script in scheda.scripts)


def test_portable_site_keeps_the_reference_scheda_privati_out_by_default(exported: Document) -> None:
    dataset = offline_payload(exported)
    assert dataset["schede"] == {}
    assert "KOLA" not in json.dumps(dataset)


def test_portable_reference_includes_the_reference_scheda_privati(tmp_path: Path) -> None:
    target = tmp_path / "with-reference.html"
    export_simulator(target, db_path=tmp_path / "reference.sqlite3", include_reference=True)
    schede = offline_payload(read_html(target))["schede"]
    assert schede["036214640"]["name"] == "KOLA ALTIN"


def test_export_respects_local_changes_in_the_selected_sqlite_database(tmp_path: Path) -> None:
    db = tmp_path / "source.sqlite3"
    target = tmp_path / "site.html"
    export_simulator(target, db_path=db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE subject SET name = 'MARE EMMA' WHERE ndg = '90000001'")
    export_simulator(target, db_path=db)
    payload = offline_payload(read_html(target))
    practice = next(p for p in payload["practices"] if p["key"] == "demo")
    assert practice["name"] == "MARE EMMA"
    assert "MARE EMMA" in payload["truth"]["demo"]


def test_export_cannot_overwrite_its_source_database(tmp_path: Path) -> None:
    db = tmp_path / "source.sqlite3"
    export_simulator(tmp_path / "site.html", db_path=db)
    contents = db.read_bytes()
    with pytest.raises(ValueError):
        export_simulator(db, db_path=db)
    assert db.read_bytes() == contents


def test_portable_practice_includes_only_the_website_area_of_each_frame(tmp_path: Path) -> None:
    target = tmp_path / "opt-in.html"
    export_simulator(target, db_path=tmp_path / "reference.sqlite3", include_reference=True)
    offline = offline_payload(read_html(target))
    assert offline["hasReference"] is True
    assert offline["practice"]["ndg"] == "26871394"
    frames = offline["screens"]
    assert set(frames) == {str(step) for step in range(1, 10)}
    for step, data_url in frames.items():
        header, data = data_url.split(",", 1)
        assert header == "data:image/png;base64"
        assert_site_pixels(int(step), b64decode(data, validate=True))
