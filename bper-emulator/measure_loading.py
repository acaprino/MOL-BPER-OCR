"""Measure the loading states of Nuova PEF against the frames of the recordings, and how long each one lasts.

The frames are 1350 x 1080 crops of a 1280 x 1024 desktop enlarged 1.0547 times (spec 16.1). The main recording is
at 100%: the page viewport is the band y=92..1038, 1280 x 897 CSS px, one video px 0.948 CSS px. MOL 01 is at 110%
until 09:08 (spec 16.2, 16.7): no taskbar, viewport y=92..1080, 1164 x 852 CSS px, one video px 0.862 CSS px.

For every frame this drives the emulator at native scale in headless Chrome (DevTools protocol, real mouse input) to
the state the frame shows: after the operator's click, at the delay the 8 fps cuts of the recordings give, or as
soon as the loading phase is on screen when the recording gives no click. It checks which phase is on screen at that
moment and compares like measure_video_pages.py: raw and blurred grey difference over the page area, then the same
with boxes masked (copied from the render into the frame): the ring, whose angle is arbitrary, the mouse pointer,
the operator, Chrome's translate bubble and what belongs to the recorded practice (another customer, other rows).
The ring itself is compared by its centre (frame: a circle fitted to its colour around it; emulator: its box).
Then it times every phase from the click that starts it, page side (performance.now), against the recordings.

    python bper-emulator/measure_loading.py --frames <video-notes\frames> <video-work3\frames> --out <dir>

--frames takes every directory holding one of the frames; the frame names are those of the spec; side-by-side images go to --out, which must stay outside the repository:
the frames show a real practice.
"""

import argparse
from base64 import b64decode
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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from serve_bper_simulator import create_server  # noqa: E402

CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)
# Recording -> (viewport in CSS px, page area of the frame in video px).
SCREENS = {"main": ((1280, 897), (0, 92, 1350, 1038)), "mol01": ((1164, 852), (0, 92, 1350, 1080))}
OPERATOR = (1040, 105, 1285, 165)
CAPTION = (695, 208, 915, 240)  # the practice number in the PEF 2.0 tab
TEAL = "teal"
WHITE = "white"
# State -> frame, recording, route, how to reach the state, ms after the click (None: when the phase shows),
# expected phase, ring (centre in video px of the frame, colour), masks in video px. The 02m01s frame is taken at
# 1 fps: its content (table bar drawn, main nav and identity bar not yet) is that of 01:59.75-02:00.6 in the 8 fps
# cut, so it is compared with both phases around it.
FRAMES = {
    "row busy": ("18m11s_elenco_pratiche_spinner_dopo_click_kebab.png",
                 "main", "/?practice=demo#1", "kebab", 120, "busy", ((674, 500), TEAL),
                 [OPERATOR, (1293, 488, 1316, 522), (100, 482, 1290, 520)]),
    "blank": ("01m57s_pef20_tab_spinner.png",
              "main", "/?practice=demo#1", "open", 2125, "blank", ((675, 668), TEAL), [OPERATOR, CAPTION]),
    "half drawn": ("02m01s_pef20_overlay_caricamento.png",
                   "main", "/?practice=demo#1", "open", 5250, "partial", ((675, 668), TEAL),
                   [OPERATOR, CAPTION, (626, 548, 650, 580)]),
    "washed": ("02m01s_pef20_overlay_caricamento.png",
               "main", "/?practice=demo#1", "open", 6125, "washed", ((675, 668), TEAL),
               [OPERATOR, CAPTION, (626, 548, 650, 580)]),
    # The recorded practice has five subjects and other documents (measure_documents.py rebuilds them): its list,
    # under the identity box, is masked, which leaves the shell, the frame, the navigator and the ring.
    "PEF 2.0 wait": ("05m00s_pef20_spinner_attendere_caricamento.png",
                     "main", "/?practice=demo#5", "pef-wait", None, "pef-wait", ((717, 641), WHITE),
                     [OPERATOR, CAPTION, (668, 544, 692, 576), (322, 436, 1192, 1000)]),
    "home loading": ("C18_r6_mol01_01m13s_home_in_caricamento_traduttore.png",
                     "mol01", "/", "start", None, "home", None,
                     [(814, 84, 1172, 184), (1160, 108, 1270, 145), (484, 526, 508, 556)]),
    "Scheda blank": ("B17_mol01_09m13s_new_tab_right_of_profilo_about_blank.png",
                     "mol01", "/?console=1&practice=demo#4", "scheda", 1000, "scheda-blank", None, []),
}
# Click -> phase in ms, as the recordings show them (8 fps cuts unless noted).
RECORDED = [
    ("kebab -> row menu", "kebab", "menu", 500, "18:10.6-18:11.1"),
    ("item -> tab over a blank area", "open", "blank", 0, "01:54.875 (same frame as the menu closing)"),
    ("item -> page half drawn", "open", "partial", 4625, "01:59.5"),
    ("item -> page washed out", "open", "washed", 5875, "02:00.75"),
    ("item -> ring gone", "open", "settle", 6625, "02:01.5"),
    ("item -> full contrast", "open", "idle", 7375, "02:02.25; spec 7 at 1 fps: ~8 s"),
    # The dialog is laid out at once under the blank: it shows when the blank goes.
    ("item -> dialog (?modal=1)", "dialog", "idle", 250, "18:12.1-18:12.4"),
    ("Conferma -> page", "confirm", "idle", 375, "18:19.1-18:19.5"),
    ("start -> splash", "start", "splash", 250, "01:32.75-01:33.0"),
    ("start -> faded home", "start", "home", 750, "01:33.25; MOL 01 01:12.9"),
    ("start -> home", "start", "idle", 1125, "01:33.5"),
    ("Apri Scheda -> Scheda Privati", "scheda", "scheda", 4000, "ASSUMPTION: PRICELAB MOL 01 09:13-09:17, 1 fps"),
    ("navigator click -> answer", "pef-wait", "answered", 3000, "04:59.5-05:02.5"),
]
# Records, in every document, each change of the shell's phase, of the row's wait, of the menu and of the dialog.
TRACER = """(() => {
  window.__trace = []; window.__clicks = [];
  addEventListener('click', () => window.__clicks.push(performance.now()), true);
  let last = null;
  setInterval(() => {
    const app = document.querySelector('#application');
    if (!app) return;
    const menu = document.querySelector('.bl-menu:not(.bl-ghost)');
    const state = [app.dataset.loading || 'idle',
      document.querySelector('.bl-results')?.getAttribute('aria-busy') === 'true' ? 'busy' : '',
      menu && !menu.hidden ? 'menu' : '', document.querySelector('.pm-veil:not([hidden])') ? 'dialog' : ''].join('|');
    if (state !== last) window.__trace.push([state, performance.now()]);
    last = state;
  }, 4);
})()"""
BAND, SEARCH = 32, 6


def browser() -> str:
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise SystemExit("Chrome or Edge not found")


class Chrome:
    """Just enough of the DevTools protocol: navigate, evaluate, real mouse input, screenshot."""

    def __init__(self, exe: str, width: int, height: int) -> None:
        # Not in requirements.txt (measure_documents.py uses it too): imported only when Chrome is driven, so the
        # ring fit stays importable without it.
        from websockets.sync.client import connect

        self.profile = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.process = subprocess.Popen(
            [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
             "--remote-debugging-port=0", f"--user-data-dir={self.profile.name}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_file = Path(self.profile.name) / "DevToolsActivePort"
        lines: list[str] = []
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
        self.send("Page.enable")
        self.send("Page.addScriptToEvaluateOnNewDocument", source=TRACER)

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
            time.sleep(0.01)

    def click_on(self, expression: str) -> float:
        """Clicks the middle of the element the expression returns; the monotonic time of the release."""
        x, y = self.evaluate(f"(() => {{ const r = ({expression}).getBoundingClientRect(); "
                             "return [r.x + r.width / 2, r.y + r.height / 2]; })()")
        self.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, button="none")
        for kind in ("mousePressed", "mouseReleased"):
            self.send("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left", clickCount=1)
        return time.monotonic()

    def screenshot(self) -> Image.Image:
        return Image.open(BytesIO(b64decode(self.send("Page.captureScreenshot", format="png")["data"]))).convert("RGB")

    def close(self) -> None:
        try:
            self.socket.close()
        finally:
            self.process.kill()
            self.process.wait()
            self.profile.cleanup()


KEBAB = "document.querySelector('.bl-kebab')"
ITEM = "[...document.querySelectorAll('.bl-menu:not(.bl-ghost) button')].find(b => b.textContent === 'Visualizza Pratica')"
# What is on screen now: the shell's phase, the row's wait, the PEF 2.0 wait, the Scheda window's page.
NOW = """(() => {
  if (window.__scheda) return window.__scheda.contentDocument?.title === 'Caricamento in corso...' ? 'scheda-blank' : 'scheda';
  if (document.querySelector('.bl-results')?.getAttribute('aria-busy') === 'true') return 'busy';
  if (document.querySelector('#detail-view .ld-spinner')) return 'pef-wait';
  return document.querySelector('#application').dataset.loading || 'idle';
})()"""
# The Scheda window as a full-window frame of this page, which window.open hands back (one target is driven).
CATCH_WINDOW = """window.open = (url, name) => {
  const frame = document.createElement('iframe');
  frame.style.cssText = 'position: fixed; inset: 0; width: 100%; height: 100%; border: 0; z-index: 99; background: #fff';
  document.body.append(frame);
  window.__scheda = frame;
  if (url) frame.src = url;
  return frame.contentWindow;
}"""


def ready(chrome: Chrome, route: str, port: int) -> None:
    # A machine busy with other work can lose a script of the page now and then: one more try, then the page's error.
    for attempt in range(2):
        chrome.send("Page.navigate", url=f"http://127.0.0.1:{port}{route}")
        try:
            chrome.wait("document.readyState === 'complete' && !!document.querySelector('#frame[data-ready]')", 20)
            return
        except TimeoutError:
            if attempt:
                error = chrome.evaluate("document.querySelector('#error-message')?.textContent")
                raise RuntimeError(f"{route}: {error}") from None


def reach(chrome: Chrome, port: int, route: str, how: str) -> float:
    """Brings the page to the action that starts the measured state; the monotonic time of its click."""
    if how == "start":
        chrome.send("Page.navigate", url=f"http://127.0.0.1:{port}{route}")
        return time.monotonic()
    ready(chrome, route, port)
    if how == "kebab":
        return chrome.click_on(KEBAB)
    if how in ("open", "dialog"):
        chrome.click_on(KEBAB)
        chrome.wait(f"!!({ITEM})?.checkVisibility()", 3)
        return chrome.click_on(ITEM)
    if how == "pef-wait":
        # Gestione Documentale, then back to Fidi with the navigator (05:00): the frame scrolled so that its main nav
        # is at its top, as in the frame. detail.js does not call the wait yet: it is started as it will be.
        chrome.click_on("document.querySelector('#detail-view [data-docs-link]:not([hidden] *)')")
        chrome.wait("document.querySelector('.gd-page')?.dataset.phase === 'list'", 5)
        chrome.evaluate("""(() => { const frame = document.querySelector('.pd-window');
            const zoom = frame.getBoundingClientRect().height / frame.offsetHeight;
            frame.scrollTop += (document.querySelector('.pd-mainnav').getBoundingClientRect().top
                                - frame.getBoundingClientRect().top) / zoom; })()""")
        chrome.evaluate("window.__answered = null; window.__asked = performance.now(); BperLoading.run("
                        "document.querySelector('#detail-view'), BperLoading.TIMES.navigator, "
                        "() => { window.__answered = performance.now() - window.__asked; })")
        return time.monotonic()
    if how == "scheda":
        chrome.evaluate(CATCH_WINDOW)
        return chrome.click_on("document.querySelector('#open-scheda')")
    raise ValueError(how)


def render(exe: str, port: int, name: str) -> tuple[Image.Image, str, int | None, tuple[float, float] | None]:
    """The screenshot, the phase on screen around it ("a>b" if it changed meanwhile), ms after the click, the
    centre of the ring on screen, CSS px."""
    _, recording, route, how, delay, expected, _, _ = FRAMES[name]
    chrome = Chrome(exe, *SCREENS[recording][0])
    try:
        clicked = reach(chrome, port, route, how)
        if delay is None:
            chrome.wait(f"(() => {{ try {{ return {NOW} === {json.dumps(expected)}; }} catch {{ return false; }} }})()", 10)
            time.sleep(0.05)
        else:
            time.sleep(max(0.0, delay / 1000 - (time.monotonic() - clicked)))
        state = chrome.evaluate(NOW)
        since = chrome.evaluate("window.__clicks?.length ? Math.round(performance.now() - window.__clicks.at(-1)) : null")
        ring = chrome.evaluate("""(() => { const ring = [...document.querySelectorAll('.ld-ring, .ld-spinner')]
            .find(node => node.checkVisibility()); if (!ring) return null; const r = ring.getBoundingClientRect();
            return [r.x + r.width / 2, r.y + r.height / 2]; })()""")
        image = chrome.screenshot()
        after = chrome.evaluate(NOW)
        return image, state if after == state else f"{state}>{after}", since, ring
    finally:
        chrome.close()


def timings(exe: str, port: int) -> dict[tuple[str, str], float | None]:
    """Page-side ms from the click (or from the start of the page) to the first entry into each phase."""
    found: dict[tuple[str, str], float | None] = {}
    for how in ("kebab", "open", "dialog", "start", "scheda", "pef-wait"):
        route = {"dialog": "/?practice=demo&modal=1#1", "start": "/", "pef-wait": "/?practice=demo#5",
                 "scheda": "/?console=1&practice=demo#4"}.get(how, "/?practice=demo#1")
        chrome = Chrome(exe, 1280, 897)
        try:
            reach(chrome, port, route, how)
            if how == "scheda":
                chrome.wait("window.__scheda?.contentDocument?.title === 'BPER Scheda Privati'", 10)
                found[(how, "scheda")] = chrome.evaluate("performance.now() - window.__clicks.at(-1)")
                continue
            if how == "pef-wait":
                chrome.wait("window.__answered !== null", 10)
                found[(how, "answered")] = chrome.evaluate("window.__answered")
                continue
            chrome.wait("document.readyState === 'complete' && !!document.querySelector('#frame[data-ready]')", 10)
            chrome.wait("!document.querySelector('#application').dataset.loading"
                        + (" && !!document.querySelector('.bl-menu:not(.bl-ghost):not([hidden])')" if how == "kebab" else ""), 12)
            time.sleep(0.05)
            trace = chrome.evaluate("window.__trace")
            clicks = chrome.evaluate("window.__clicks")
            origin = next(at for state, at in trace if state.startswith("boot")) if how == "start" else clicks[-1]
            for state, at in trace:
                phase, busy, menu, dialog = state.split("|")
                for key in (phase, busy, menu, dialog):
                    if key and at >= origin and (how, key) not in found:
                        found[(how, key)] = at - origin
            if how == "dialog":
                # Conferma once the dialog is up: a blank without the ring, then the page.
                chrome.click_on("[...document.querySelectorAll('.pm-buttons button')].at(-1)")
                chrome.wait("!document.querySelector('#application').dataset.loading", 5)
                time.sleep(0.05)
                trace = chrome.evaluate("window.__trace")
                confirm = chrome.evaluate("window.__clicks.at(-1)")
                found[("confirm", "idle")] = next(at for state, at in trace if at > confirm and state.startswith("idle")) - confirm
        finally:
            chrome.close()
    return found


def gray(img: Image.Image, blur: float) -> np.ndarray:
    out = img.convert("L")
    return np.asarray(out.filter(ImageFilter.GaussianBlur(blur)) if blur else out, dtype=np.float32)


def ring_centre(frame: np.ndarray, centre: tuple[int, int], colour: str) -> tuple[float, float] | None:
    """Centre of the circle fitted to the ring's colour in a box around where the frame has it, video px. A fit,
    not a centroid: the gap of a three-quarter ring, at any angle, would pull a centroid by several px."""
    x0, y0 = centre[0] - 45, centre[1] - 32
    box = frame[y0:y0 + 64, x0:x0 + 90].astype(int)
    if colour == TEAL:
        hit = ((box.max(2) - box.min(2)) > 60) & (box[..., 1] > 100) & (box[..., 0] < 120)
    else:  # the navy ring over navy bars: its white inner circle, without the white lines between the bars
        hit = (box > 225).all(2)
        hit[hit.mean(axis=1) > 0.6] = False
    ys, xs = np.nonzero(hit)
    if len(xs) <= 20:
        return None
    # x^2 + y^2 + D x + E y + F = 0, least squares (Kasa); the centre is (-D/2, -E/2).
    (d, e, _), *_ = np.linalg.lstsq(np.column_stack([xs, ys, np.ones(len(xs))]), -(xs ** 2 + ys ** 2), rcond=None)
    return x0 - d / 2, y0 - e / 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--frames", type=Path, nargs="+", required=True, help="directories holding the frames")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    names = [n for n in FRAMES if not args.only or any(part and part in n for part in args.only.split(","))]
    args.out.mkdir(parents=True, exist_ok=True)
    exe = browser()
    with create_server(port=0, db_path=args.out / "loading.sqlite3") as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        renders = {name: render(exe, server.server_port, name) for name in names}
        measured = timings(exe, server.server_port)
        server.shutdown()

    print("state (frame)                     phase (expected) at        raw|diff| blur|diff| masked blur  px>24  ring d(CSS px)")
    for name in names:
        file, recording, _, _, delay, expected, ring, masks = FRAMES[name]
        (width, height), area = SCREENS[recording]
        scale = width / (area[2] - area[0])
        path = next(d / file for d in args.frames if (d / file).exists())
        with Image.open(path) as source:
            frame = source.convert("RGB")
        ref = frame.crop(area).resize((width, height), Image.Resampling.LANCZOS)
        emu, state, since, drawn = renders[name]
        to_page = lambda box: tuple(round(v * scale) for v in (box[0], box[1] - area[1], box[2], box[3] - area[1]))  # noqa: E731
        masked = ref.copy()
        boxes = list(masks)
        moved = "-"
        if ring:
            (cx, cy), colour = ring
            boxes.append((cx - 36, cy - 36, cx + 36, cy + 36))
            seen = ring_centre(np.asarray(frame), (cx, cy), colour)
            if seen and drawn:
                moved = f"{drawn[0] - seen[0] * scale:+.1f},{drawn[1] - (seen[1] - area[1]) * scale:+.1f}"
            else:
                moved = "no ring" if seen else "no ring in the frame"
        for box in map(to_page, boxes):
            masked.paste(emu.crop(box), box[:2])
        raw = np.abs(np.asarray(ref, dtype=np.float32) - np.asarray(emu, dtype=np.float32)).mean(axis=2)
        blurred = float(np.abs(gray(ref, 1.2) - gray(emu, 1.2)).mean())
        blurred_masked = float(np.abs(gray(masked, 1.2) - gray(emu, 1.2)).mean())
        when = f"{since} ms" if since is not None and delay is not None else "on phase"
        print(f"{name + ' (' + file[:6] + ')':<33} {state + ' (' + expected + ')':<24} {when:<9} {raw.mean():>7.2f}"
              f" {blurred:>10.2f} {blurred_masked:>11.2f}  {(raw > 24).mean() * 100:>4.1f}%  {moved}")
        side = Image.new("RGB", (width * 3, height), "white")
        side.paste(masked, (0, 0))
        side.paste(emu, (width, 0))
        side.paste(Image.fromarray(np.clip(raw * 4, 0, 255).astype(np.uint8)).convert("RGB"), (width * 2, 0))
        side.save(args.out / f"side_{name.replace(' ', '_')}.png")

    print("\ntiming (ms from the click)               emulator  recording  source")
    for label, how, phase, recorded, source in RECORDED:
        value = measured.get((how, phase))
        shown = "-" if value is None else f"{value:.0f}"
        print(f"{label:<40} {shown:>8}  {recorded:>9}  {source}")


if __name__ == "__main__":
    main()
