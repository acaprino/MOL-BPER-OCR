"""Files the capture script publishes per practice, with a stand-in for the browser.

Playwright is not installed everywhere the suite runs. The script loads it from PLAYWRIGHT_MODULE, so a
small fake takes its place at that boundary: it serves the exported catalogue, records the address and
viewport of every screenshot and writes a PNG header of that size. What the real browser renders is
covered by tests/browser/bper_capture_pack.cjs where Playwright exists.
"""

import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import parse_qs, urlsplit

import pytest

from bper_simulator_export import export_simulator
from bper_site_fixture import fictitious_profile, write_profiles

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bper-emulator" / "capture_bper_dataset.cjs"
FAKE_PLAYWRIGHT = r"""
const fs = require('node:fs');
const { fileURLToPath } = require('node:url');

function png(width, height) {
    const header = Buffer.alloc(24);
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).copy(header);
    header.writeUInt32BE(13, 8);
    header.write('IHDR', 12);
    header.writeUInt32BE(width, 16);
    header.writeUInt32BE(height, 20);
    return header;
}

function catalogue(href) {
    const html = fs.readFileSync(fileURLToPath(href.split(/[?#]/)[0]), 'utf8');
    const start = html.indexOf('window.BperOffline = ') + 'window.BperOffline = '.length;
    return JSON.parse(html.slice(start, html.indexOf(';</script>', start)));
}

exports.chromium = { async launch() {
    return {
        async newPage({ viewport }) {
            let url;
            let size = viewport;
            return {
                setDefaultTimeout() {},
                async setViewportSize(next) { size = next; },
                async goto(href) {
                    url = href;
                    globalThis.window = { BperOffline: catalogue(href) };
                },
                async waitForFunction() {},
                async evaluate(fn, arg) {
                    globalThis.document = { fonts: { ready: Promise.resolve() } };
                    globalThis.requestAnimationFrame = callback => callback();
                    return fn(arg);
                },
                async screenshot({ path }) {
                    fs.writeFileSync(path, png(size.width, size.height));
                    fs.appendFileSync(process.env.FAKE_PLAYWRIGHT_LOG, JSON.stringify({ path, url, ...size }) + '\n');
                },
            };
        },
        async close() {},
    };
} };
"""

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")


@pytest.fixture(scope="module")
def html(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("capture-html")
    target = directory / "simulatore.html"
    export_simulator(target, db_path=directory / "pratiche.sqlite3")
    return target


def capture(html: Path, tmp_path: Path, *args: str) -> tuple[subprocess.CompletedProcess, list[dict]]:
    fake = tmp_path / "fake_playwright.cjs"
    fake.write_text(FAKE_PLAYWRIGHT, encoding="utf-8")
    log = tmp_path / "shots.jsonl"
    log.touch()
    env = {**os.environ, "PLAYWRIGHT_MODULE": str(fake), "FAKE_PLAYWRIGHT_LOG": str(log)}
    result = subprocess.run(["node", str(SCRIPT), "--html", str(html), *args],
                            cwd=REPO, env=env, capture_output=True, text=True, timeout=60)
    return result, [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[16:24]
    return int.from_bytes(header[:4], "big"), int.from_bytes(header[4:], "big")


def catalogue(html: Path) -> dict:
    text = html.read_text(encoding="utf-8")
    start = text.index("window.BperOffline = ") + len("window.BperOffline = ")
    return json.loads(text[start:text.index(";</script>", start)])


def test_capture_writes_every_scheda_state_with_matching_truth_rows(html: Path, tmp_path: Path) -> None:
    result, _ = capture(html, tmp_path, "--out", str(tmp_path / "pacco"), "--practice", "demo,sim-004")
    assert result.returncode == 0, result.stderr
    for key in ("demo", "sim-004"):
        directory = tmp_path / "pacco" / key
        with (directory / "dati.csv").open(encoding="utf-8-sig", newline="") as source:
            ids = {row["Fotogramma"] for row in csv.DictReader(source)}
        images = {path.stem for path in directory.glob("*.png")}
        assert ids == images, key
        assert {"scheda-privati-01", "scheda-privati-02"} <= images, key


def test_each_scheda_state_is_shot_at_its_own_scroll_in_a_full_hd_window(html: Path, tmp_path: Path) -> None:
    practice = max(catalogue(html)["practices"], key=lambda p: len(p["schedaStates"]))
    assert len(practice["schedaStates"]) >= 4
    result, shots = capture(html, tmp_path, "--out", str(tmp_path / "pacco"), "--practice", practice["key"])
    assert result.returncode == 0, result.stderr
    by_name = {Path(shot["path"]).stem: shot for shot in shots}
    for state in practice["schedaStates"]:
        shot = by_name[state["name"]]
        url = urlsplit(shot["url"])
        query = parse_qs(url.query)
        assert url.fragment == f"/schede/{practice['ndg']}/{practice['scheda']['schedaId']}"
        assert (query["scroll"], query["noteScroll"]) == ([str(state["scroll"])], [str(state["noteScroll"])])
        assert (shot["width"], shot["height"]) == (1920, 945)
    directory = tmp_path / "pacco" / practice["key"]
    assert png_size(directory / "scheda-privati-01.png") == (1920, 945)
    assert png_size(directory / "screen 1.png") == (842, 617)


def test_each_practice_folder_holds_its_practice_truth(html: Path, tmp_path: Path) -> None:
    result, _ = capture(html, tmp_path, "--out", str(tmp_path / "pacco"), "--practice", "demo")
    assert result.returncode == 0, result.stderr
    with (tmp_path / "pacco" / "demo" / "practice-truth.csv").open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source, delimiter=";"))
    assert len(rows) == 45 and rows[0] == {"Chiave": "ndg", "Campo": "NDG", "Valore": "90000001"}


def test_each_practice_folder_records_its_key_role_and_generator(html: Path, tmp_path: Path) -> None:
    result, _ = capture(html, tmp_path, "--out", str(tmp_path / "pacco"), "--practice", "demo")
    assert result.returncode == 0, result.stderr
    manifest = json.loads((tmp_path / "pacco" / "demo" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == {"practice": "demo", "role": "sintetica", "generator": "bper-emulator"}


@pytest.fixture(scope="module")
def roles_html(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A page with invented practices of the archive roles: a test one, and one whose scheda is another
    customer's (as the joint practice of the archive whose Scheda Privati is one holder's)."""
    directory = tmp_path_factory.mktemp("roles-html")
    other = fictitious_profile("fittizia-controllo", "controllo")
    other["scheda"].update(ndg="97000001", name="CLIENTE COINTESTATARIO")
    profiles = write_profiles(directory / "profili.json", [fictitious_profile("fittizia-test", "test"), other])
    target = directory / "simulatore.html"
    export_simulator(target, db_path=directory / "pratiche.sqlite3", profiles=[profiles], include_test=True)
    return target


def test_capture_refuses_a_test_practice_without_include_test(roles_html: Path, tmp_path: Path) -> None:
    result, shots = capture(roles_html, tmp_path, "--out", str(tmp_path / "pacco"), "--practice", "fittizia-test")
    assert result.returncode != 0
    assert "--include-test" in result.stderr and "test" in result.stderr
    assert shots == [] and not (tmp_path / "pacco").exists()


def test_capture_of_all_practices_refuses_a_page_holding_a_test_practice(roles_html: Path, tmp_path: Path) -> None:
    result, shots = capture(roles_html, tmp_path, "--out", str(tmp_path / "pacco"), "--all")
    assert result.returncode != 0 and "--include-test" in result.stderr
    assert shots == [] and not (tmp_path / "pacco").exists()


def test_capture_of_a_test_practice_with_include_test_records_its_role(roles_html: Path, tmp_path: Path) -> None:
    result, _ = capture(roles_html, tmp_path, "--out", str(tmp_path / "pacco"), "--practice", "fittizia-test",
                        "--include-test")
    assert result.returncode == 0, result.stderr
    manifest = json.loads((tmp_path / "pacco" / "fittizia-test" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == {"practice": "fittizia-test", "role": "test", "generator": "bper-emulator"}


def test_the_scheda_is_shot_on_the_customer_its_page_belongs_to(roles_html: Path, tmp_path: Path) -> None:
    result, shots = capture(roles_html, tmp_path, "--out", str(tmp_path / "pacco"), "--practice", "fittizia-controllo")
    assert result.returncode == 0, result.stderr
    fragments = {urlsplit(shot["url"]).fragment for shot in shots if Path(shot["path"]).stem.startswith("scheda-")}
    assert fragments and all(f.startswith("/schede/97000001/") for f in fragments)


def test_capture_refuses_a_practice_without_a_role(html: Path, tmp_path: Path) -> None:
    unmarked = tmp_path / "senza-ruolo.html"
    unmarked.write_text(html.read_text(encoding="utf-8").replace('"role":"sintetica"', '"role":""'), encoding="utf-8")
    result, shots = capture(unmarked, tmp_path, "--out", str(tmp_path / "pacco"), "--practice", "demo")
    assert result.returncode != 0
    assert "ruolo" in result.stderr.lower()
    assert shots == [] and not (tmp_path / "pacco").exists()
