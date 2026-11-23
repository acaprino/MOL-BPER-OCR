"""Measure the emulated Gestione Documentale and its PDF viewer against the frames of the recording.

The frames (spec 10.4) are 1350 x 1080 crops of a 1280 x 1024 desktop enlarged by 1.0547 (spec 16.1): the
browser viewport is the band y=92..1038, 1280 x 897 CSS px (937 where the taskbar is hidden). For every frame this
opens the emulator at native scale in headless Chrome with that viewport, on a practice shaped like the recorded
one and a documents list mirroring the frame's rows (same categories, codes, icons and states; invented names and
wording), reproduces the operator's state with clicks, scrolling and the pointer (open sections, frame and viewer
scroll, an info icon, wait or toast), and compares, after a light blur:
  - frame: the whole PEF 2.0 frame area as rendered (navigator, mast and identity box included);
  - work:  the documents page alone (right of the navigator, under the identity box), shifted vertically by the dy
           that aligns it best (reported), which isolates it from the identity box and navigator of the practice;
  - same text: the boxes whose text is identical on both sides (Filtro panel, table header, viewer toolbar), in
           the aligned documents page: the figure comparable with measure_fidelity.py, where all text matches;
  - the per-band drift (dx, dy) left inside the aligned documents page.

    python bper-emulator/measure_documents.py --frames <directory of the frames> --out <dir> [--only 02m59s,18m48s]

Side-by-side images go to --out; keep it outside the repository, the frames show a real practice.
"""

import argparse
from base64 import b64decode
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import numpy as np
from PIL import Image, ImageFilter
from websockets.sync.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bper_profiles import FORMAT  # noqa: E402
from bper_synthetic_db import synthetic_practices  # noqa: E402
from serve_bper_simulator import create_server  # noqa: E402

CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)
VIDEO_PX = 0.948          # CSS px per video px (spec 16.1)
TOP = 92                  # viewport top in the frame
FRAME_BOX = (140, 282, 1312, 1000)   # PEF 2.0 frame area, video px
WORK_X = (322, 1192)
BAND, SEARCH = 32, 6

# A practice shaped like the recorded one: a joint account of two holders and two guarantors. Invented values.
SUBJECTS = [
    ("58201377", "BERTOLI GIADA SERENA", "Cointestato"),
    ("58201376", "GALLINI ARMANDO", "Cointestato"),
    ("58201378", "GALLINI ARMANDO,BERTOLI GIADA SERENA", "Richiedente"),
    ("61944250", "MAZZOLENI EDOARDO", "Nuovo Garante/nuovo Datore Di Pegno"),
    ("27530916", "GALLINI FEDERICO", "Nuovo Garante/nuovo Datore Di Pegno"),
]
ANAG, INCOME, ASSETS, PRODUCT = ("Documenti anagrafici", "Documenti reddituali e contabili", "Documenti patrimoniali",
                                 "Documentazione specifica prodotto")
TIP = "Si richiede il documento indicato per tutti i soggetti della pratica, se presente"


def row(category: str, kind: str, code: str, group: str = "", tip: bool = True, acquired: bool = False,
        note: str = "") -> dict:
    return {"category": category, "type": kind, "code": code, "group": group, "tip": TIP if tip else "", "note": note,
            "acquired": acquired, "date": "05/10/2026" if acquired else ""}


# The frames' rows, row for row: same categories, codes, groups, icons and acquisition, invented wording.
PERSON = [
    row(ANAG, "Mod. 07.31.0512 - Autocertificazione stato di famiglia", "OA", "14", acquired=True),
    row(ANAG, "Stato di famiglia rilasciato dal Comune", "OA", "14", tip=False),
    row(ANAG, "Certificato di stato civile libero", "OA", "15"),
    row(ANAG, "Mod. 07.31.0533 - Dichiarazione del regime patrimoniale", "OA", "15", tip=False, acquired=True),
    row(ANAG, "Certificato storico di residenza cittadini extra UE", "E"),
    row(ANAG, "Iscrizione all'anagrafe dei residenti all'estero", "E"),
    row(ANAG, "Permesso di soggiorno cittadini extra UE", "E"),
    row(ASSETS, "Titoli in deposito", "E"),
    row(ASSETS, "Visura catastale - immobili posseduti", "E"),
    row(INCOME, "Cedolino - Retribuzione Annua Netta", "O", acquired=True),
    row(INCOME, "Visura camerale del datore di lavoro", "O", acquired=True),
    row(INCOME, "Mod. 07.31.0587 - Autocertificazione spese ricorrenti", "O", tip=False, acquired=True),
    row(INCOME, "Mod. 07.31.0601 - Piani di ammortamento dei debiti presso altre banche", "O", acquired=True),
    row(INCOME, "Estratti conto degli ultimi tre mesi", "O", acquired=True),
]
OTHER = [row("Altro", "Altro", "E", tip=False, acquired=True, note="Estratto conto contributivo")]
CREDIT = [
    row(PRODUCT, "Mod. 07.12.0244 - Richiesta di perizia sottoscritta", "O", tip=False, acquired=True),
    row(PRODUCT, "Simulazione Rata / Reddito", "O", acquired=True),
    row(PRODUCT, "Visura catastale", "O", tip=False, acquired=True),
    row(PRODUCT, "Altri allegati previsti dal modulo 07.12.0263 e Mod. 07.12.0270", "E"),
    row(PRODUCT, "Copia dell'atto costitutivo del fondo comune", "E"),
    row(PRODUCT, "Documentazione sulla prestazione energetica", "E", acquired=True),
    row(PRODUCT, "Mod. 07.12.0270 - Lettera di presentazione del mediatore", "E"),
    row(PRODUCT, "Modulo di adesione firmato dal cliente per proposte assicurative", "E"),
    row(PRODUCT, "Preventivo ricevuto da un comparatore online convenzionato", "E", tip=False, acquired=True),
    row(PRODUCT, "Listino / mail di pre-autorizzazione delle condizioni", "E"),
]
GUARANTOR = [
    row(ANAG, "Iscrizione all'anagrafe dei residenti all'estero", "E"),
    row(ANAG, "Permesso di soggiorno cittadini extra UE", "E"),
    row(ANAG, "Estratto di matrimonio o unione civile con il regime patrimoniale [richiesto al terzo datore d'ipoteca]",
        "EA", "37", tip=False),
    row(ANAG, "Mod. 07.31.0533 - Dichiarazione del regime patrimoniale [richiesta al terzo datore d'ipoteca]",
        "EA", "37", tip=False, acquired=True),
]
DOCUMENTS = [
    {"ndg": n, "name": name, "role": role, "groups": groups} for (n, name, role), groups in zip(SUBJECTS, [
        [{"title": "Documenti CONTROPARTE", "rows": PERSON + OTHER}],
        [{"title": "Documenti CONTROPARTE", "rows": PERSON}],
        [{"title": "Documenti relativi al Fido F1 MUTUO IPOTECARIO PRIVATI", "rows": CREDIT}],
        [{"title": "Documenti GARANTE", "rows": GUARANTOR}],
        [{"title": "Documenti GARANTE", "rows": GUARANTOR}],
    ])
]

# frame -> (viewport height, loading off?, open bars, top of the documents page in the frame (video px), actions,
# boxes whose text is the same on both sides (Filtro panel, table header, viewer toolbar), x0 y0 x1 y1 in the frame).
# Actions: ("scroll", selector, frame y wanted for its top), ("viewer",), ("view", viewer scroll in reference px),
# ("hover", x, y in video px), ("apply",) for a wait in progress, ("toast",) for the extraction toast.
FILTER, HEADER, TOOLBAR = (333, 1177), (343, 1176), (326, 1186)
FRAMES = {
    "02m59s_pef20_gestione_documentale.png": (897, True, [1], 481, [],
                                              [(FILTER[0], 522, FILTER[1], 662), (HEADER[0], 739, HEADER[1], 770)]),
    "03m45s_pef20_documentale_accordion_soggetti.png": (897, True, [4], 481, [],
                                                        [(FILTER[0], 522, FILTER[1], 662), (HEADER[0], 814, HEADER[1], 846)]),
    "03m55s_pef20_documentale_tooltip.png": (897, True, [2], 282, [("scroll", ".gd-panel h3", 313)],
                                             [(FILTER[0], 311, FILTER[1], 451), (HEADER[0], 553, HEADER[1], 584)]),
    "05m00s_pef20_spinner_attendere_caricamento.png": (897, False, [4], 435,
                                                       [("scroll", ".pd-mainnav", 282), ("apply",)],
                                                       [(FILTER[0], 475, FILTER[1], 615), (HEADER[0], 768, HEADER[1], 799)]),
    "18m48s_pef20_pdf_viewer_caricamento.png": (897, False, [1], 481, [("viewer",), ("toast",)],
                                                [(TOOLBAR[0], 499, TOOLBAR[1], 558)]),
    "18m53s_pef20_pdf_viewer.png": (897, True, [1], 375, [("viewer",), ("scroll", ".pv-frame", 392), ("view", 217)],
                                    [(TOOLBAR[0], 394, TOOLBAR[1], 452)]),
    "39m11s_pef20_documentale_tooltip_giallo.png": (937, True, [0, 1], 282,
                                                    [("scroll", ".gd-subject:nth-of-type(3) h3", 312),
                                                     ("hover", 785, 760)],
                                                    [(HEADER[0], 362, HEADER[1], 393)]),
}


def browser() -> str:
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise SystemExit("Chrome or Edge not found")


class Chrome:
    """Just enough of the DevTools protocol: navigate, evaluate, real mouse input, screenshot."""

    def __init__(self, exe: str, width: int, height: int) -> None:
        self.profile = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.process = subprocess.Popen(
            [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
             "--remote-debugging-port=0", f"--user-data-dir={self.profile.name}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_file = Path(self.profile.name) / "DevToolsActivePort"
        for _ in range(300):
            try:
                lines = port_file.read_text().split()
            except OSError:  # not there yet, or still being written
                lines = []
            if len(lines) >= 2:
                break
            time.sleep(0.05)
        port = int(lines[0])
        request = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
        target = json.load(urllib.request.urlopen(request, timeout=10))
        self.socket = connect(target["webSocketDebuggerUrl"], max_size=None)
        self.last = 0
        self.send("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)

    def send(self, method: str, **params: object) -> dict:
        self.last += 1
        self.socket.send(json.dumps({"id": self.last, "method": method, "params": params}))
        while True:
            message = json.loads(self.socket.recv())
            if message.get("id") == self.last:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message["result"]

    def evaluate(self, expression: str) -> object:
        result = self.send("Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"].get("exception", {}).get("description", expression))
        return result["result"].get("value")

    def wait(self, expression: str, timeout: float = 10) -> None:
        end = time.monotonic() + timeout
        while not self.evaluate(expression):
            if time.monotonic() > end:
                raise TimeoutError(expression)
            time.sleep(0.02)

    def click(self, x: float, y: float) -> None:
        self.move(x, y)
        for kind in ("mousePressed", "mouseReleased"):
            self.send("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left", clickCount=1)

    def move(self, x: float, y: float) -> None:
        self.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, button="none")

    def click_on(self, selector: str) -> None:
        box = self.evaluate(f"(() => {{ const el = document.querySelector({json.dumps(selector)});"
                            "el.scrollIntoView({block: 'nearest'}); const r = el.getBoundingClientRect();"
                            "return [r.x + r.width / 2, r.y + r.height / 2]; })()")
        self.click(*box)

    def screenshot(self) -> Image.Image:
        return Image.open(BytesIO(b64decode(self.send("Page.captureScreenshot", format="png")["data"]))).convert("RGB")

    def close(self) -> None:
        try:
            self.socket.close()
        finally:
            self.process.kill()
            self.process.wait()
            self.profile.cleanup()


def profile() -> dict:
    practice = deepcopy(synthetic_practices()[0])
    practice.update(key="misura-documentale", number="99724153", ndg=SUBJECTS[2][0], name=SUBJECTS[2][1],
                    created="06/10/2026", type="BPI Mutui", scheda=None,
                    subjects=[{"ndg": n, "name": name, "role": role} for n, name, role in SUBJECTS])
    return practice


def render(exe: str, port: int, name: str) -> Image.Image:
    height, instant, opened, _, actions, _ = FRAMES[name]
    chrome = Chrome(exe, 1280, height)
    try:
        query = "practice=misura-documentale" + ("&loading=off" if instant else "")
        chrome.send("Page.navigate", url=f"http://127.0.0.1:{port}/?{query}#5")
        chrome.wait("document.readyState === 'complete' && !!document.querySelector('#frame[data-ready]')")
        chrome.evaluate(f"BperDocs.documentsOf = () => {json.dumps(DOCUMENTS)}")
        chrome.click_on("#detail-view [data-docs-link]:not([hidden] *)")
        chrome.wait("document.querySelector('.gd-page')?.dataset.phase === 'list'")
        # The first bar opens with the page; the frame's own selection is then made by clicking, like the operator.
        chrome.evaluate(f"""(() => {{ const want = {json.dumps(opened)};
            document.querySelectorAll('.gd-subject > h3 button').forEach((bar, i) => {{
                if ((bar.getAttribute('aria-expanded') === 'true') !== want.includes(i)) bar.click(); }}); }})()""")
        for action in actions:
            if action[0] == "scroll":
                # Scroll the PEF 2.0 frame until the element's top is at that frame y (video px).
                css = (action[2] - TOP) * VIDEO_PX
                chrome.evaluate(f"""(() => {{ const frame = document.querySelector('.pd-window');
                    const el = document.querySelector({json.dumps(action[1])});
                    const zoom = frame.getBoundingClientRect().height / frame.offsetHeight;
                    frame.scrollTop += (el.getBoundingClientRect().top - {css}) / zoom; }})()""")
            elif action[0] == "viewer":
                chrome.click_on(".gd-subject:not(:has(> .gd-body[hidden])) .gd-file")
                chrome.wait("document.querySelector('.gd-page')?.dataset.phase?.startsWith('viewer')", 5)
            elif action[0] == "toast":
                chrome.wait("document.querySelector('.gd-page')?.dataset.phase === 'viewer-text'", 5)
            elif action[0] == "view":
                chrome.evaluate(f"document.querySelector('.pv-view').scrollTop = {action[1]}")
            elif action[0] == "hover":
                chrome.move(action[1] * VIDEO_PX, (action[2] - TOP) * VIDEO_PX)
                chrome.wait("!document.querySelector('.gd-tip').hidden", 3)
            elif action[0] == "apply":
                chrome.click_on(".gd-apply")
                chrome.wait("!!document.querySelector('.gd-spinner')", 3)
        time.sleep(0.15)
        return chrome.screenshot()
    finally:
        chrome.close()


def gray(img: Image.Image, blur: float) -> np.ndarray:
    return np.asarray(img.convert("L").filter(ImageFilter.GaussianBlur(blur)), dtype=np.float32)


def best_shift(ref: np.ndarray, emu: np.ndarray, x0: int, x1: int, y0: int, y1: int,
               reach: int = 40) -> tuple[int, float]:
    scores = {dy: float(np.abs(ref[y0:y1, x0:x1] - emu[y0 + dy:y1 + dy, x0:x1]).mean())
              for dy in range(-reach, reach + 1) if y0 + dy >= 0 and y1 + dy <= emu.shape[0]}
    dy = min(scores, key=scores.get)
    return dy, scores[dy]


def band_drift(ref: np.ndarray, emu: np.ndarray) -> list[tuple[int, int, int, float, float]]:
    rows = []
    height, width = ref.shape
    for y0 in range(SEARCH, height - BAND - SEARCH, BAND):
        target = ref[y0:y0 + BAND, SEARCH:width - SEARCH]
        if target.std() < 3:
            continue
        best, zero = (0, 0, 1e9), 0.0
        for dy in range(-SEARCH, SEARCH + 1):
            for dx in range(-SEARCH, SEARCH + 1):
                score = float(np.abs(target - emu[y0 + dy:y0 + dy + BAND, SEARCH + dx:width - SEARCH + dx]).mean())
                if dx == 0 and dy == 0:
                    zero = score
                if score < best[2]:
                    best = (dx, dy, score)
        rows.append((y0, best[0], best[1], zero, best[2]))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    names = [n for n in FRAMES if not args.only or any(part and part in n for part in args.only.split(","))]
    args.out.mkdir(parents=True, exist_ok=True)
    profiles = args.out / "profilo-misura.json"
    profiles.write_text(json.dumps({"format": FORMAT, "profiles": [profile()]}, ensure_ascii=False), encoding="utf-8")
    exe = browser()
    with create_server(port=0, db_path=args.out / "fidelity.sqlite3", profiles=[profiles]) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        renders = {name: render(exe, server.server_port, name) for name in names}
        server.shutdown()

    print("frame                                    frame|diff|  work|diff| (dy)  same text  drift bands (y: dx,dy)")
    for name in names:
        with Image.open(args.frames / name) as source:
            frame = source.convert("RGB")
        height, top = FRAMES[name][0], FRAMES[name][3]
        size = (1350, round(height / VIDEO_PX))
        emu = Image.new("RGB", frame.size, "white")
        emu.paste(renders[name].resize(size, Image.LANCZOS), (0, TOP))
        ref_g, emu_g = gray(frame, 1.2), gray(emu, 1.2)
        x0, y0, x1, y1 = FRAME_BOX
        y1 = min(y1 + (height - 897), TOP + size[1])
        whole = float(np.abs(ref_g[y0:y1, x0:x1] - emu_g[y0:y1, x0:x1]).mean())
        # The documents page only, the emulator moved by the dy that aligns it best.
        top = max(top + 4, y0)
        dy, work = best_shift(ref_g, emu_g, WORK_X[0], WORK_X[1], top + 40, y1 - 40)
        aligned = np.roll(emu_g, -dy, axis=0)
        work = float(np.abs(ref_g[top:y1, WORK_X[0]:WORK_X[1]] - aligned[top:y1, WORK_X[0]:WORK_X[1]]).mean())
        drift = band_drift(ref_g[top:y1, WORK_X[0]:WORK_X[1]], aligned[top:y1, WORK_X[0]:WORK_X[1]])
        moved = " ".join(f"{y + top}:{ddx:+d},{ddy:+d}" for y, ddx, ddy, zero, best in drift
                         if (ddx, ddy) != (0, 0) and zero - best > 1.0)
        same = np.concatenate([np.abs(ref_g[y0b:y1b, x0b:x1b] - aligned[y0b:y1b, x0b:x1b]).ravel()
                               for x0b, y0b, x1b, y1b in FRAMES[name][5]])
        print(f"{name[:40]:<40} {whole:>10.2f}  {work:>9.2f} ({dy:+d})  {same.mean():>9.2f}  {moved or 'aligned'}")
        box = (WORK_X[0], top, WORK_X[1], y1)
        shifted = Image.new("RGB", frame.size, "white")
        shifted.paste(emu, (0, -dy))
        pair = Image.new("RGB", (2 * (box[2] - box[0]), box[3] - box[1]), "white")
        pair.paste(frame.crop(box), (0, 0))
        pair.paste(shifted.crop(box), (box[2] - box[0], 0))
        pair.save(args.out / f"work_{name}")
        side = Image.new("RGB", (frame.width * 2, frame.height), "white")
        side.paste(frame, (0, 0))
        side.paste(emu, (frame.width, 0))
        side.save(args.out / f"side_{name}")


main()
