"""The simplest live test: the browser shows the emulator, the edge agent's grab reads it, local OCR reads the grabs.

    python bper-emulator/live_simple.py --practices 3 [--url http://127.0.0.1:8765]

The first N practices are shown page by page in a headed window. Near the end of each page's dwell ONE frame is
grabbed as the real worker grabs (window and foreground guards, desktop greyed, preprocess_for_ocr) and kept whatever
the classifier says. RapidOCR A1 reads the frames offline (.venv-ocr); each truth value is looked for in them with the
archive's aligner. Nothing paid or remote is called; LiLT is not part of this version.
"""

from __future__ import annotations

import argparse, csv, ctypes, io, json, os, queue, subprocess, sys, time  # noqa: E401 - one stdlib line keeps it short
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import live_test as lt

OUT = Path(r"D:\claude-scratch\poc-data-extraction-emulator\live-test\simple")
OCR_PYTHON = lt.REPO / ".venv-ocr" / "Scripts" / "python.exe"
OCR = ("import sys\nfrom pathlib import Path\nfrom training.ocr_runner import Screen, _sha256, run_ocr\n"
       "frames = sorted(Path(sys.argv[1]).glob('*.png'))\n"
       "run_ocr(sys.argv[3], 'pc4', [Screen(p.stem, p, _sha256(p)) for p in frames], Path(sys.argv[2]))\n")
DWELL_MS = 5000
# The page kind the aligner reads its regions from (training.dataset.alignment_name), by the page on screen.
KIND = {"screen 1": "elenco", "screen 2": "elenco_dx", "screen 3": "elenco_tooltip", "screen 4": "soggetti",
        "screen 5": "gestionefidi", **dict.fromkeys(("screen 6", "screen 7", "screen 8"), "gestionefidi_tooltip"), "screen 9": "note"}


def walk(keys: Sequence[str]) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = [{"do": "start", "dwell_ms": 2000}]
    for key in keys:
        steps += [{"do": "search", "practice": key}, {"do": "hover", "target": "evidence"},
                  {"do": "unhover", "dwell_ms": 0}, {"do": "open", "practice": key}, {"do": "next"},
                  *({"do": "hover", "target": t} for t in ("fido", "guarantee-1", "guarantee-2")),
                  {"do": "unhover", "dwell_ms": 0}, {"do": "tab", "to": "note"}]
    return lt.load_scenario({"name": "simple", "geometry": "wide", "dwell_ms": DWELL_MS, "practices": list(keys),
                             "steps": steps})


def grab_time(step: Dict[str, Any], settled: Dict[str, Any], dwell_ms: int) -> Optional[float]:
    """1 s before the dwell of a page ends; never for Home, unhover, or a wait inside a step (search form, row menu)."""
    dwell = step.get("dwell_ms", dwell_ms) / 1000
    if step.get("do") in (None, "start") or dwell <= 1 or settled.get("what") in ("search form", "row menu"):
        return None
    return settled["t"] + dwell - 1.0


def capture(worker: Any, state: Dict[str, Any], folder: Path, number: int, recorder: Any = None) -> Optional[dict]:
    """One frame as the worker grabs and preprocesses it, kept whatever the classifier says; None if a guard drops it."""
    raw = worker._grab_raw()
    if raw is None:
        return None
    img = worker._preprocess(raw)
    label, score, _ = worker._detect_page(img)
    best = ((recorder.current.get("routed") or {}) if recorder else {})
    name = f"{number:05d}.png"
    img.save(folder / name)
    return {"file": name, "ndg": lt.practice_of(state), "page": lt.label_for_probe(state)[0], "classifier": label,
            "best": best.get("best", label), "score": round(float(best.get("best_score") or score or 0.0), 3)}


def found_table(truths: Dict[str, List[tuple]], frames: Sequence[Dict[str, Any]], folder: Path) -> List[Dict[str, Any]]:
    """Per practice and field with a value: is it in the OCR of a kept frame of that practice (yes/no)."""
    from PIL import Image
    from extraction.field_definitions import CANONICAL_FIELD_DEFINITIONS
    from extraction.normalization import normalize_ndg
    from training.alignment import align_screen
    from training.evaluation import _available

    scheda = {k for k, d in CANONICAL_FIELD_DEFINITIONS.items() if d.get("page_key") == "scheda_privati"}
    rows: List[Dict[str, Any]] = []
    for practice, truth in truths.items():
        wanted = [(f, label, v) for f, label, v in truth if v and f not in scheda]
        ndg = normalize_ndg(next((v for f, _l, v in truth if f == "ndg"), None))
        found = set()
        for frame in (fr for fr in frames if normalize_ndg(fr["ndg"]) == ndg and fr["page"] in KIND):
            lines = [{"text": t, "score": s, "box": b} for t, s, b in frame["items"]]
            with Image.open(folder / frame["file"]) as image:
                located = align_screen(KIND[frame["page"]], [(l, v) for _f, l, v in wanted], lines, image.convert("RGB"))
            found |= {f for f, l, v in wanted if _available({"field_alignment": {f: located["fields"][l]}}, f, v, {})}
        rows += [{"practice": practice, "field": f, "expected": v, "found": "yes" if f in found else "no"}
                 for f, _l, v in wanted]
    return rows


def percentages(rows: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    share = lambda chosen: round(100 * sum(r["found"] == "yes" for r in chosen) / len(chosen), 1) if chosen else 0.0  # noqa: E731
    out = {p: share([r for r in rows if r["practice"] == p]) for p in dict.fromkeys(r["practice"] for r in rows)}
    return {**out, "overall": share(rows)}


def browse_and_grab(url: str, scenario: Dict[str, Any], run: Path) -> List[Dict[str, Any]]:
    """The headed walk: the driver shows the pages, one frame is kept per page dwell."""
    from PyQt6.QtCore import QCoreApplication
    from frame_normalize import find_window_rect

    if lt.matching_window_pids(lt.WINDOW_TITLE):
        raise lt.GuardError(f"a window titled «{lt.WINDOW_TITLE}» is already open: close it first")
    QCoreApplication.instance() or QCoreApplication([])
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    box: Dict[str, int] = {}
    own = lambda: lt.window_rect(box["hwnd"]) if box else None  # noqa: E731
    screen = (ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1))

    def mask() -> tuple:  # what the crop holds outside the drawn window, clipped to the monitor
        o, d = own(), lt.visible_frame_bounds(box["hwnd"])
        o = (max(o[0], 0), max(o[1], 0), min(o[2], screen[0]), min(o[3], screen[1]))
        return tuple(max(0, v) for v in (d[0] - o[0], d[1] - o[1], o[2] - d[2], o[3] - d[3]))

    recorder = lt.Recorder()
    worker = lt.make_harness_worker(lt.harness_config(run / "agent"), lambda: "simple", None, recorder=recorder,
                                    rect_provider=find_window_rect, own_rect=own, guard=lt.PrivacyGuard(), live=True,
                                    exposure=lambda: bool(own()) and lt.window_exposed(box["pid"], own()),
                                    scrub=lambda img: lt.blank_outside_window(img, mask()))
    worker._init_router()  # DINOv2, for the informational label only
    for left in range(10, 0, -1):
        print(f"HEADED RUN in {left} s: a Chrome window takes over the primary monitor; do not cover it.", flush=True)
        time.sleep(1)
    driver = lt.DriverProcess(lt._driver_args(scenario, url, run, headless=False, record=False), run / "driver.log")
    frames: List[Dict[str, Any]] = []
    try:
        pid = int(driver.wait_for("ready", 60)["pid"])
        mine = lt.own_windows(pid, lt.WINDOW_TITLE)
        if len(mine) != 1 or lt.matching_window_pids(lt.WINDOW_TITLE) != [pid]:
            raise lt.GuardError("the emulator window is not the only one with its title")
        box.update(hwnd=mine[0][0], pid=pid)
        lt.set_topmost(box["hwnd"], True)
        driver.send("go")
        step, end = {}, time.time() + lt.estimate_seconds(scenario) + 60
        while time.time() < end and not recorder.abort:
            try:
                event = driver.queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if event["event"] in ("done", "exit"):
                break
            step = event if event["event"] == "action" and "index" in event else step
            at = grab_time(step, event, scenario["dwell_ms"]) if event["event"] == "settled" else None
            if at is not None:
                time.sleep(max(0.0, at - time.time()))
                kept = capture(worker, driver.probes()[-1]["state"], run / "frames", len(frames), recorder)
                frames += [{**kept, "step": step["do"]}] if kept else []
                if not kept:  # say why, so a missing page is not mistaken for an OCR miss
                    print(f"dropped {step['do']}: {recorder.current.get('reason')}", flush=True)
    finally:
        if box:
            lt.set_topmost(box["hwnd"], False)
        driver.close()
    if recorder.abort:
        raise lt.PrivacyAbort(recorder.abort)
    return frames


def main(argv: Optional[Sequence[str]] = None) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--practices", type=int, default=3, help="how many practices, from the top of the catalogue")
    parser.add_argument("--config", default="A1", help="OCR configuration of training.ocr_runner (A0 reads faster)")
    parser.add_argument("--url", help="an emulator already running (default: start our own on a free port)")
    args = parser.parse_args(argv)
    run = OUT / time.strftime("%Y%m%d-%H%M%S")
    (run / "frames").mkdir(parents=True)
    server: Any = lt.RemoteServer(args.url) if args.url else lt.EmulatorServer(lt._default_db(), [])
    try:
        keys = [p["key"] for p in json.loads(server.get("/api/practices.json"))["practices"][: args.practices]]
        truths = {key: [(r["Chiave"], r["Campo"], r["Valore"]) for r in csv.DictReader(io.StringIO(
            server.get(f"/api/truth-practice/{key}.csv").decode("utf-8-sig")), delimiter=";")] for key in keys}
        started = time.time()
        frames = browse_and_grab(server.url, walk(keys), run)
    except (lt.GuardError, lt.ScenarioError, lt.PrivacyAbort) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    finally:
        server.stop()
        lt._clean_temp()
    walked, started = time.time() - started, time.time()
    if frames:  # the OCR interpreter, offline: RapidOCR and its models are local
        env = {**os.environ, "PYTHONPATH": str(lt.REPO / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
        subprocess.run([str(OCR_PYTHON), "-c", OCR, str(run / "frames"), str(run / "ocr"), args.config], check=True, env=env)
        cache = json.loads((run / "ocr" / "cache.json").read_text(encoding="utf-8"))
        frames = [{**f, "items": cache[Path(f["file"]).stem]["items"]} for f in frames]
    rows = found_table(truths, frames, run / "frames")
    for f in frames:
        print(f"frame {f['file']} {f['step']:<6} shown {f['page'] or '-':<9} classifier {f['classifier'] or '-'} "
              f"(best {f['best'] or '-'} {f['score']})")
    for r in rows:
        print(f"{r['practice']:<10} {r['field']:<30} {str(r['expected'])[:50]:<52} {r['found']}")
    print(f"Frames kept per page: {dict(Counter(f['page'] or '-' for f in frames))}")
    print(" ".join(f"{p}: {s}%" for p, s in percentages(rows).items()) + f". Walk {walked:.0f} s, OCR {time.time() - started:.0f} s. "
          "LiLT: not part of this version (its weights are on the Modal volume).")
    with (run / "found.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle, delimiter=";").writerows([["practice", "field", "expected", "found"], *map(dict.values, rows)])
    print(f"Table: {run / 'found.csv'}; frames kept: {run / 'frames'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
