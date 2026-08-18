"""Recompute app_rect for every registry frame, with progress and resume.

The registry stores where the application window was found in each reference
frame. When the localizer changes, those rectangles are stale: this recomputes
them without touching labels, so a geometry change can be measured on its own.

Checkpoints every 25 frames into the output file, and skips frames already
present there, so an interrupted run resumes instead of restarting.

    python tools/relocalize.py --out <path.json> [--limit N]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict

import torch
import torch.nn.functional as F
from PIL import Image

FRAMES_DIR = Path("tests/fixtures/frames")


def load_localizer() -> Any:
    spec = importlib.util.spec_from_file_location("lf", "tools/label_frames.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="tests/fixtures/frames/relocalized.json")
    ap.add_argument("--templates", default="edge-agent/assets/templates/bper")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--subset", default="",
                    help="json list of frame paths to restrict the run to; the rest of "
                         "the registry keeps its stored rectangles")
    args = ap.parse_args()

    lf = load_localizer()
    print(f"vincolo di area minima: {lf.MIN_AREA_FRACTION:.0%} del frame", flush=True)

    registry = json.loads((FRAMES_DIR / "registry.json").read_text(encoding="utf-8"))
    out_path = Path(args.out)
    done: Dict[str, Any] = {}
    if out_path.exists():
        done = json.loads(out_path.read_text(encoding="utf-8"))
        print(f"ripresa: {len(done)} rettangoli gia' calcolati", flush=True)

    wanted = None
    if args.subset:
        wanted = set(json.loads(Path(args.subset).read_text(encoding="utf-8")))
        print(f"sottoinsieme richiesto: {len(wanted)} fotogrammi", flush=True)

    frames = [e for e in registry["frames"]
              if (FRAMES_DIR / e["frame"]).exists() and e["frame"] not in done
              and (wanted is None or e["frame"] in wanted)]
    if args.limit:
        frames = frames[:args.limit]
    print(f"da calcolare: {len(frames)}", flush=True)

    model = lf.load_model()
    means = []
    templates = sorted(Path(args.templates).glob("*.png"))
    for tpl in templates:
        grid = lf.patch_grid(model, Image.open(tpl), 224, 224)
        means.append(grid.reshape(-1, grid.shape[-1]).mean(0))
    detector = F.normalize(torch.stack(means).mean(0), dim=0)
    reference = Image.open(templates[0])
    aspect = reference.width / reference.height
    print("modello e prototipi pronti, inizio", flush=True)

    start = time.time()
    for i, entry in enumerate(frames, 1):
        img = Image.open(FRAMES_DIR / entry["frame"]).convert("RGB")
        score, rect = lf.localize(model, detector, img, aspect)
        done[entry["frame"]] = {"rect": list(rect), "score": round(score, 4)}
        if i % 25 == 0 or i == len(frames):
            out_path.write_text(json.dumps(done, indent=1), encoding="utf-8")
            elapsed = time.time() - start
            print(f"{i}/{len(frames)}  {elapsed/i:.2f}s/frame  "
                  f"residuo ~{(len(frames)-i)*elapsed/i/60:.0f} min", flush=True)

    out_path.write_text(json.dumps(done, indent=1), encoding="utf-8")
    areas = sorted((v["rect"][2] - v["rect"][0]) * (v["rect"][3] - v["rect"][1])
                   for v in done.values())
    print(f"\nFATTO: {len(areas)} rettangoli")
    print(f"area mediana {statistics.median(areas)/1e6:.2f} Mpx, "
          f"minima {areas[0]/1e6:.3f}, massima {areas[-1]/1e6:.2f}")
    print(f"sotto 0.6 Mpx: {sum(1 for a in areas if a < 0.6e6)}/{len(areas)}")


if __name__ == "__main__":
    main()
