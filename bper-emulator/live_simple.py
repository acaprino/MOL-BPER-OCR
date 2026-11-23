"""The simplest live test: the edge agent captures the emulator in a real Chrome window, local OCR reads what it captured.

    python bper-emulator/live_simple.py --practices 3 [--url http://127.0.0.1:8765]

The first N practices of /api/practices.json are shown page by page in a headed window; the real BPERCaptureWorker
keeps each frame it adopts (outside of the window greyed), RapidOCR A1 reads them offline in .venv-ocr, and each value
of /api/truth-practice/<key>.csv is looked for in that practice's OCR with the archive's aligner (Scheda Privati left
out: the walk never shows it). Nothing paid or remote is called; LiLT is not part of this version.
"""

from __future__ import annotations

import argparse, csv, io, json, math, os, subprocess, sys, time  # noqa: E401 - one stdlib line keeps it short
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import live_test as lt

OUT = Path(r"D:\claude-scratch\poc-data-extraction-emulator\live-test\simple")
OCR_PYTHON = lt.REPO / ".venv-ocr" / "Scripts" / "python.exe"
OCR = ("import sys\nfrom pathlib import Path\nfrom training.ocr_runner import Screen, _sha256, run_ocr\n"
       "frames = sorted(Path(sys.argv[1]).glob('*.png'))\n"
       "run_ocr('A1', 'pc4', [Screen(p.stem, p, _sha256(p)) for p in frames], Path(sys.argv[2]))\n")
DWELL_MS = 5000  # routing took about 1 s per frame on a busy PC, and stability needs 2.0 s after it
WINDOW_WIDTH = lt.GEOMETRIES["wide"]["window"][0]
# The page kind the aligner reads its regions from (training.dataset.alignment_name), by the page the agent adopted.
KIND = {"screen 1": "elenco", "screen 2": "elenco_dx", "screen 3": "elenco_tooltip", "screen 4": "soggetti",
        "screen 5": "gestionefidi", **dict.fromkeys(("screen 6", "screen 7", "screen 8"), "gestionefidi_tooltip"), "screen 9": "note"}
LILT = "LiLT: not part of this version (its weights are on the Modal volume, not on this machine)."


def walk(keys: Sequence[str]) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = [{"do": "start", "dwell_ms": 2000}]
    for key in keys:
        steps += [{"do": "search", "practice": key}, {"do": "hover", "target": "evidence"},
                  {"do": "unhover", "dwell_ms": 0}, {"do": "open", "practice": key}, {"do": "next"},
                  *({"do": "hover", "target": t} for t in ("fido", "guarantee-1", "guarantee-2")),
                  {"do": "unhover", "dwell_ms": 0}, {"do": "tab", "to": "note"}]
    return {"name": "simple", "geometry": "wide", "dwell_ms": DWELL_MS, "practices": list(keys), "steps": steps}


def frame_keeper(folder: Path) -> Any:
    """live_test's oracle (it keeps the run's consolidation), also saving each adopted frame for the OCR."""
    import app_paths
    from PIL import ImageDraw
    from page_registry import PageRegistry

    folder.mkdir(parents=True, exist_ok=True)
    registry = PageRegistry.load(app_paths.templates_dir() / "prompts.json")

    class FrameKeeper(lt.OraclePipeline):
        def __init__(self, *args: Any) -> None:
            super().__init__(*args)
            self.frames: List[Dict[str, Any]] = []

        def extract_from_image(self, img: Any, screen_id: str, **kwargs: Any) -> Dict[str, Any]:
            t = self._acquired_at()
            state = lt.state_at(self._probes(), t if t is not None else time.time())
            # The invisible borders and rounded corners show the desktop: grey them, scaled like the frame.
            b, (w, h), copy = math.ceil((lt.INVISIBLE_BORDER + 1) * img.width / WINDOW_WIDTH), img.size, img.copy()
            draw = ImageDraw.Draw(copy)
            for box in ((0, 0, b, h), (w - b, 0, w, h), (0, h - b, w, h), *((x, y, x + 2 * b, y + 2 * b)
                        for x in (0, w - 2 * b) for y in (0, h - 2 * b))):
                draw.rectangle(box, fill=(128, 128, 128))
            name = f"{len(self.frames):05d}.png"
            copy.save(folder / name)
            page = registry.resolve(screen_id)
            self.frames.append({"file": name, "ndg": lt.practice_of(state), "page": page.template if page else None})
            return super().extract_from_image(img, screen_id, **kwargs)

    return FrameKeeper


def found_table(truths: Dict[str, List[tuple]], frames: Sequence[Dict[str, Any]], folder: Path) -> List[Dict[str, Any]]:
    """Per practice and field with a value: is it in the OCR of a captured frame of that practice (yes/no)."""
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--practices", type=int, default=3, help="how many practices, from the top of the catalogue")
    parser.add_argument("--url", help="an emulator already running (default: start our own on a free port)")
    args = parser.parse_args(argv)
    run = OUT / time.strftime("%Y%m%d-%H%M%S")
    keeper, made, oracle = frame_keeper(run / "read"), [], lt.OraclePipeline
    server: Any = lt.RemoteServer(args.url) if args.url else lt.EmulatorServer(lt._default_db(), [])
    try:
        keys = [p["key"] for p in json.loads(server.get("/api/practices.json"))["practices"][: args.practices]]
        truths = {key: [(r["Chiave"], r["Campo"], r["Valore"]) for r in csv.DictReader(io.StringIO(
            server.get(f"/api/truth-practice/{key}.csv").decode("utf-8-sig")), delimiter=";")] for key in keys}
        scenario = walk(keys)
        lt.OraclePipeline = lambda *a: made.append(keeper(*a)) or made[-1]  # this run's frames go to the keeper
        report = lt.run_live(scenario, run / "live", db=lt._default_db(), url=server.url,
                             max_seconds=lt.estimate_seconds(lt.load_scenario(scenario)) + 60)
    except (lt.GuardError, lt.ScenarioError, lt.PrivacyAbort) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    finally:
        lt.OraclePipeline = oracle
        server.stop()
    frames, started = (made[0].frames if made else []), time.time()  # OCR only what the worker adopted
    if frames:
        env = {**os.environ, "PYTHONPATH": str(lt.REPO / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
        subprocess.run([str(OCR_PYTHON), "-c", OCR, str(run / "read"), str(run / "ocr")], check=True, env=env)
        cache = json.loads((run / "ocr" / "cache.json").read_text(encoding="utf-8"))
        for frame in frames:
            frame["items"] = cache[Path(frame["file"]).stem]["items"]
    rows = found_table(truths, frames, run / "read")
    scores = percentages(rows)
    for r in rows:
        print(f"{r['practice']:<10} {r['field']:<30} {str(r['expected'])[:50]:<52} {r['found']}")
    from extraction.normalization import normalize_ndg
    owner = {normalize_ndg(next((v for f, _l, v in t if f == "ndg"), None)): k for k, t in truths.items()}
    for key in keys:
        pages = sorted({f["page"] or "-" for f in frames if owner.get(normalize_ndg(f["ndg"])) == key})
        print(f"{key}: {scores.get(key, 0.0)}% of the values found; pages recognised {pages}")
    print(f"overall: {scores['overall']}%. Rows consolidated: {report['consolidation']['rows']} for {len(keys)} "
          f"practices. Walk {report['duration_s']:.0f} s, OCR of {len(frames)} frames {time.time() - started:.0f} s. {LILT}")
    with (run / "found.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle, delimiter=";").writerows([["practice", "field", "expected", "found"], *map(dict.values, rows)])
    print(f"Table: {run / 'found.csv'}; frames read: {run / 'read'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
