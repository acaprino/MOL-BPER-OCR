"""Measure the PEF 2.0 pages of the recordings beyond the reference screenshots (site/pef-extra.js) against frames.

The frames are the C18_* cuts of the MOL recordings (spec 18.2) and 02m52s of the main recording (spec 15.5):
1350 x 1080 crops of a 1280 x 1024 desktop enlarged 1.0547 times (spec 16.1), one video px = 0.948 CSS px; the browser
viewport is the band y=92..1038 (897 CSS px) with the taskbar, y=92..1080 (937) without it. For each frame this opens
the emulator at native scale in headless Chrome with that viewport, on an invented practice shaped like the recorded
one, fills the page with the frame's layout (same rows, dots, states and amounts of zero; invented names and numbers),
reproduces the operator's state (navigator clicks, open groups, waits) and compares, after a light blur:
  - frame: the whole PEF 2.0 frame area as rendered (mast, navigator, identity box, page);
  - part:  the new page or block alone, shifted vertically by the dy that aligns it best (reported), which isolates it
           from what differs above it (the identity box of another practice, a longer strategy text);
  - same text: the boxes whose text is identical on both sides (titles, labels, headers, buttons), aligned like
           part: the figure comparable with measure_fidelity.py, where all text matches;
  - the per-band drift (dx, dy) left inside the aligned part.

    python bper-emulator/measure_pef_pages.py --frames <dir of the C18_* frames> --main <dir of 02m52s_*> --out <dir>
        [--only r2,r3]

Side-by-side images go to --out; keep it outside the repository, the frames show real practices.
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
FRAME_X = (140, 1312)     # PEF 2.0 frame area, video px
BAND, SEARCH = 32, 6

# Invented subjects shaped like the recorded ones (a person; a joint account of two holders).
PERSON = [("81273520", "LORENZINI MATTIA", "Richiedente")]
JOINT = [("81273531", "FERRARI GIULIO,MANCINI SARA", "Richiedente"), ("81273532", "FERRARI GIULIO", "Cointestato"),
         ("81273533", "MANCINI SARA", "Cointestato")]


def row(label: str, link: bool, text: str = "", dot: str = "", side: str = "") -> dict:
    return {"label": label, "link": link, "text": text, "dot": dot, "side": side}


# MOL 11 02:23, row for row: same states and dots, the amounts of the frame (all zero).
ALERTS_MOL11 = {
    "internal": [row("Rating Ufficiale", True, "Non Disponibile"), row("Rating Andamentale", True, "Non Disponibile"),
                 row("RDB", True, dot="green"), row("Verifiche Precedenti Archiviate", False, dot="green"),
                 row("Pratiche in Corso", True, side="Sì"), row("Dati Anagrafici", True, dot="red")],
    "external": [row("Protesti", False, dot="green"), row("Pregiudizievoli", False, dot="green"),
                 row("Procedure Concorsuali", False, dot="green"), row("Dossier CERVED", True),
                 row("Sofferenze CR", False, dot="green"), row("Segnalazioni Status Sofferenze da Sistema", False, dot="green")],
    "strategy": "Non calcolabile (mancanza di rating)", "policy": [], "granted": [["0", "0"], ["0", "0"]],
}
# MOL 04 02:13: two resolutions of the holder; invented numbers, branch and amounts of the frame's lengths.
RESOLUTIONS_MOL04 = [{"ndg": JOINT[0][0], "date": "09/09/2026", "body": "BOLOGNA 4", "number": "47518230", "amount": "0"},
                     {"ndg": JOINT[0][0], "date": "09/09/2026", "body": "BOLOGNA 4", "number": "47524917", "amount": "8.000"}]
# MOL 05 20:59: Richiesta passed, no Parere, in Proposta, the deliberating body under Delibera.
NAVIGATOR_MOL05 = {"groups": ["VEP", "RIC", "IST", "PRO", "DEL"], "phase": "PRO", "returned": False,
                   "body": "UFF.AN. E<br>CONC.CR.CALABRIA-..."}

# frame -> (directory key, viewport height, route, init overrides, actions, part box, same-text boxes).
# Boxes are x0 y0 x1 y1 in video px of the frame. Actions: ("click", selector), ("wait", js), ("sleep", s),
# ("scroll", selector, frame y of its top). A same-text box marked "fixed" is drawn on the frame, not on the page,
# so it is compared where it is, without the page's alignment. Avvertenza leaves out Conferma, under the pointer.
WORK = (322, 1190)
FRAMES = {
    "C18_r2_mol11_02m23s_recupero_segnalazioni.png": (
        "frames", 937, "?practice=misura-pef&loading=off#4", {"alertsOf": ALERTS_MOL11, "subjects": PERSON},
        [("click", '[data-nav="VEP.segnalazioni"]')],
        (WORK[0], 466, WORK[1], 840),
        [(325, 548, 746, 688), (762, 548, 1183, 688), (325, 705, 746, 729), (762, 696, 1183, 738),
         (1066, 779, 1182, 807), (325, 813, 1183, 838), (1108, 507, 1178, 535)]),
    "C18_r3_mol04_02m13s_note_delibere_precedenti_con_righe.png": (
        "frames", 937, "?practice=misura-pef&loading=off#5", {"resolutionsOf": RESOLUTIONS_MOL04, "subjects": JOINT},
        [("click", '[data-nav="IST.delibere"]')],
        (WORK[0], 481, WORK[1], 640),
        [(324, 513, 1186, 559), (1054, 612, 1188, 638), (1115, 482, 1184, 508)]),
    "02m52s_pef20_note_delibere_precedenti_recupero_in_corso.png": (
        "main", 897, "?practice=misura-pef#4", {"resolutionsOf": [], "subjects": JOINT},
        [("click", '[data-action="next"]'), ("wait", "!!document.querySelector('.nd-notice')"), ("sleep", 0.2)],
        (WORK[0], 481, WORK[1], 775),
        [(324, 513, 1186, 572), (1054, 573, 1188, 600), (507, 670, 897, 769, "fixed")]),
    "C18_r4_mol05_06m53s_fidi_visualizzazione_bottoni_disabilitati.png": (
        "frames", 937, "?practice=misura-pef&loading=off&visualizzazione=1#5", {"subjects": PERSON},
        [("scroll", ".pd-decalage", 926)],
        (326, 925, 1186, 1040),
        [(329, 926, 589, 992), (329, 1026, 1183, 1040)]),
    "C18_r4_mol02_01m49s_fidi_decalage_note_politiche_creditizie.png": (
        "frames", 937, "?practice=misura-pef&loading=off#5", {"subjects": PERSON},
        [("scroll", ".pd-decalage", 929)],
        (326, 925, 1186, 1040),
        [(329, 928, 589, 995), (329, 1028, 1183, 1040)]),
    "C18_r1_mol05_20m59s_navigatore_piu_gruppi_aperti_richiesta_proposta_delibera.png": (
        "frames", 937, "?practice=misura-pef&loading=off&visualizzazione=1#4", {"navigatorOf": NAVIGATOR_MOL05, "subjects": PERSON},
        [("click", '[data-group="RIC"]')],
        (144, 383, 307, 945),
        [(144, 383, 307, 945)]),
    "C18_r5_mol06_08m22s_avvertenza_uscire_dalla_pratica.png": (
        "frames", 897, "?practice=misura-pef&loading=off#5", {"subjects": PERSON},
        [("click", '[data-action="exit"]')],
        (184, 594, 944, 688),
        [(188, 598, 940, 619), (188, 625, 700, 645), (190, 645, 265, 675)]),
}


def browser() -> str:
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise SystemExit("Chrome or Edge not found")


class Chrome:
    """Just enough of the DevTools protocol: a script before the page's own, navigate, evaluate, click, screenshot."""

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

    def wait(self, expression: str, timeout: float = 15) -> None:
        end = time.monotonic() + timeout
        while not self.evaluate(expression):
            if time.monotonic() > end:
                raise TimeoutError(expression)
            time.sleep(0.02)

    def click(self, selector: str) -> None:
        x, y = self.evaluate(f"(() => {{ const el = document.querySelector({json.dumps(selector)});"
                             "const r = el.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()")
        for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.send("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left" if kind != "mouseMoved" else "none",
                      clickCount=1)
        # The pointer leaves, like the operator's, which the frames do not show over the page.
        self.send("Input.dispatchMouseEvent", type="mouseMoved", x=1, y=1, button="none")

    def screenshot(self) -> Image.Image:
        return Image.open(BytesIO(b64decode(self.send("Page.captureScreenshot", format="png")["data"]))).convert("RGB")

    def close(self) -> None:
        try:
            self.socket.close()
        finally:
            self.process.kill()
            self.process.wait()
            self.profile.cleanup()


def profile(subjects: list[tuple[str, str, str]]) -> dict:
    practice = deepcopy(synthetic_practices()[0])
    practice.update(key="misura-pef", number="99731846", ndg=subjects[0][0], name=subjects[0][1], created="22/09/2026",
                    type="BPI Mutui", scheda=None, subjects=[{"ndg": n, "name": name, "role": role} for n, name, role in subjects])
    return practice


def overrides(fixed: dict) -> str:
    """A script run before the page's own: pef-extra.js's data functions answer the frame's content."""
    functions = {name: f"() => ({json.dumps(value)})" for name, value in fixed.items() if name != "subjects"}
    body = ", ".join(f"{name}: {source}" for name, source in functions.items())
    return ("Object.defineProperty(window, 'BperPefExtra', { configurable: true, set(api) {"
            f" Object.defineProperty(window, 'BperPefExtra', {{ value: Object.assign(api, {{ {body} }}),"
            " writable: true, configurable: true }); } });")


def render(exe: str, port: int, name: str) -> Image.Image:
    _, height, route, fixed, actions, _, _ = FRAMES[name]
    chrome = Chrome(exe, 1280, height)
    try:
        chrome.send("Page.enable")
        chrome.send("Page.addScriptToEvaluateOnNewDocument", source=overrides(fixed))
        chrome.send("Page.navigate", url=f"http://127.0.0.1:{port}/{route}")
        chrome.wait("document.readyState === 'complete' && !!document.querySelector('#frame[data-ready]')")
        for action in actions:
            if action[0] == "click":
                chrome.click(action[1])
            elif action[0] == "wait":
                chrome.wait(action[1])
            elif action[0] == "sleep":
                time.sleep(action[1])
            elif action[0] == "scroll":
                # Scroll the PEF 2.0 frame until the element's top is at that frame y (video px), like the operator.
                css = (action[2] - TOP) * VIDEO_PX
                chrome.evaluate(f"""(() => {{ const frame = document.querySelector('.pd-window');
                    const el = document.querySelector({json.dumps(action[1])});
                    const zoom = frame.getBoundingClientRect().height / frame.offsetHeight;
                    frame.scrollTop += (el.getBoundingClientRect().top - {css}) / zoom; }})()""")
        time.sleep(0.15)
        return chrome.screenshot()
    finally:
        chrome.close()


def gray(img: Image.Image, blur: float) -> np.ndarray:
    return np.asarray(img.convert("L").filter(ImageFilter.GaussianBlur(blur)), dtype=np.float32)


def best_shift(ref: np.ndarray, emu: np.ndarray, x0: int, x1: int, y0: int, y1: int, reach: int = 80) -> int:
    scores = {dy: float(np.abs(ref[y0:y1, x0:x1] - emu[y0 + dy:y1 + dy, x0:x1]).mean())
              for dy in range(-reach, reach + 1) if y0 + dy >= 0 and y1 + dy <= emu.shape[0]}
    return min(scores, key=scores.get)


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
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    names = [n for n in FRAMES if not args.only or any(part and part in n for part in args.only.split(","))]
    args.out.mkdir(parents=True, exist_ok=True)
    exe = browser()
    renders = {}
    for name in names:
        # One practice per frame: its subjects are part of what the page shows.
        profiles = args.out / "profilo-misura.json"
        practice = profile(FRAMES[name][3]["subjects"])
        profiles.write_text(json.dumps({"format": FORMAT, "profiles": [practice]}, ensure_ascii=False), encoding="utf-8")
        with create_server(port=0, db_path=args.out / "misura.sqlite3", profiles=[profiles]) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            renders[name] = render(exe, server.server_port, name)
            server.shutdown()

    print("frame                                    frame|diff|  part|diff| (dy)  same text  drift bands (y: dx,dy)")
    for name in names:
        folder, height, _, _, _, part, same = FRAMES[name]
        with Image.open((args.frames if folder == "frames" else args.main) / name) as source:
            frame = source.convert("RGB")
        size = (1350, round(height / VIDEO_PX))
        emu = Image.new("RGB", frame.size, "white")
        emu.paste(renders[name].resize(size, Image.LANCZOS), (0, TOP))
        ref_g, emu_g = gray(frame, 1.2), gray(emu, 1.2)
        bottom = min(TOP + size[1], frame.height)
        whole = float(np.abs(ref_g[282:bottom, FRAME_X[0]:FRAME_X[1]] - emu_g[282:bottom, FRAME_X[0]:FRAME_X[1]]).mean())
        x0, y0, x1, y1 = part
        y1 = min(y1, bottom)
        dy = best_shift(ref_g, emu_g, x0, x1, y0, y1)
        aligned = np.roll(emu_g, -dy, axis=0)
        part_diff = float(np.abs(ref_g[y0:y1, x0:x1] - aligned[y0:y1, x0:x1]).mean())
        drift = band_drift(ref_g[y0:y1, x0:x1], aligned[y0:y1, x0:x1])
        moved = " ".join(f"{y + y0}:{ddx:+d},{ddy:+d}" for y, ddx, ddy, zero, best in drift
                         if (ddx, ddy) != (0, 0) and zero - best > 1.0)
        same_diff = np.concatenate([
            np.abs(ref_g[by0:min(by1, bottom), bx0:bx1] - (emu_g if fixed else aligned)[by0:min(by1, bottom), bx0:bx1]).ravel()
            for bx0, by0, bx1, by1, *fixed in same])
        print(f"{name[:40]:<40} {whole:>10.2f}  {part_diff:>9.2f} ({dy:+d})  {same_diff.mean():>9.2f}  {moved or 'aligned'}")
        shifted = Image.new("RGB", frame.size, "white")
        shifted.paste(emu, (0, -dy))
        pair = Image.new("RGB", (2 * (x1 - x0), y1 - y0), "white")
        pair.paste(frame.crop((x0, y0, x1, y1)), (0, 0))
        pair.paste(shifted.crop((x0, y0, x1, y1)), (x1 - x0, 0))
        pair.save(args.out / f"part_{name}")
        side = Image.new("RGB", (frame.width * 2, frame.height), "white")
        side.paste(frame, (0, 0))
        side.paste(emu, (frame.width, 0))
        side.save(args.out / f"side_{name}")


main()
