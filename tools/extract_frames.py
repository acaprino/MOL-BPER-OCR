"""Extract reference frames from session recordings.

READ THIS BEFORE CHANGING THE SAMPLING. Two extractions were run on the same six
recordings and produced almost opposite material, for reasons that are not obvious
and cost a day to find.

## Scene detection is the wrong default here

The first pass used ffmpeg's scene-change filter over the whole video:

    -vf "select='gt(scene,0.10)'"

It looks efficient, and on these recordings it is actively misleading. Measured on
`Bper-20250919_Parte 02`: **zero frames selected in the first five minutes**. The
recordings are teaching sessions, so the screen sits still while people talk, and
the filter has nothing to fire on. Asking for "the first 20 minutes" did not mean
the first 20 minutes were sampled.

What it did select, in bulk, was the long tail: uploading and reviewing documents,
where the screen changes constantly. Of 505 frames taken that way, 8% were process
pages and two thirds were Gestione Documentale.

## The demonstration is at the beginning

In `Bper-20250922_Parte 01`, the whole opening of the process fits in 46 seconds:
Teams intro, the qtask tool, the iSpace portal, BPER opens at t=26s, Ricerca
Pratica at t=28s, Elenco Pratiche at t=37s, the same list scrolled right at t=41s.
That last pair is process pages 1 and 2. Everything after is document handling.

So the frames worth having are dense at the start and sparse afterwards, which is
the opposite of what a scene-change filter yields.

## Tooltips lose twice

Process pages 3, 6, 7 and 8 are a base page with a tooltip open. A tooltip appears
on hover, covers a small part of the screen, and lasts a second or two. Scene
detection does not fire on a change that small, and perceptual-hash dedup then
merges whatever survived back into the base page. Both stages work against exactly
the four pages that are hardest to distinguish and that hold five of the 45 fields.
Across 984 scene-selected frames, those four pages appeared zero times.

Fixed-rate sampling at 1 fps or better is the only mode that can catch them, and
the dedup threshold has to stay tight (Hamming > 2, not > 6) or they are merged
away after being caught. A first attempt at > 6 collapsed 53 frames into 12.

## Therefore

`fixed` mode over the opening minutes is the default. `scene` mode remains for
sweeping a long recording cheaply when the goal is negatives rather than process
pages, and it is genuinely good at that: the hard negatives (right application,
wrong screen) came from exactly that pass.

    python tools/extract_frames.py --video <path> --out <dir> [--mode fixed|scene]
                                   [--seconds 600] [--fps 1] [--scene 0.04]
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import List

# Dedup threshold. Tight on purpose: see "Tooltips lose twice" above.
DEDUP_HAMMING = 2


def extract(video: Path, out: Path, mode: str, seconds: int, fps: float,
            scene: float, tag: str) -> List[Path]:
    out.mkdir(parents=True, exist_ok=True)
    if mode == "fixed":
        vf = f"fps={fps}"
    else:
        vf = f"select='gt(scene,{scene})'"

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-ss", "0", "-t", str(seconds), "-i", str(video),
        "-vf", vf, "-fps_mode", "vfr", str(out / f"{tag}_%04d.png"),
    ]
    subprocess.run(cmd, check=True)
    return sorted(out.glob(f"{tag}_*.png"))


def deduplicate(frames: List[Path], threshold: int = DEDUP_HAMMING) -> List[Path]:
    """Drop near-identical frames, comparing whole frames.

    Comparing whole frames is a known compromise: the hash is dominated by the
    static parts (desktop, participant tiles), so two genuinely different pages
    can hash close together. Deduplicating after cropping to the application area
    would be correct, but that needs the localizer and therefore a model load per
    frame. The tight threshold is what keeps this usable meanwhile.
    """
    import imagehash
    from PIL import Image

    kept: List[Path] = []
    hashes: List[object] = []
    for path in frames:
        h = imagehash.phash(Image.open(path).resize((256, 256)))
        if all(h - k > threshold for k in hashes):  # type: ignore[operator]
            hashes.append(h)
            kept.append(path)
    return kept


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", required=True, action="append",
                    help="recording to extract from; repeat for several")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--mode", choices=("fixed", "scene"), default="fixed")
    ap.add_argument("--seconds", type=int, default=600,
                    help="how much of the opening to cover (default 600 = 10 min)")
    ap.add_argument("--fps", type=float, default=1.0, help="fixed mode sampling rate")
    ap.add_argument("--scene", type=float, default=0.04, help="scene mode threshold")
    ap.add_argument("--manifest", default="", help="write the kept frame list here")
    args = ap.parse_args()

    out = Path(args.out)
    kept_all: List[Path] = []
    for i, video in enumerate(args.video, 1):
        tag = f"v{i}"
        frames = extract(Path(video), out / tag, args.mode, args.seconds,
                         args.fps, args.scene, tag)
        kept = deduplicate(frames)
        kept_all += kept
        print(f"{tag}: {len(frames):5} estratti -> {len(kept):4} distinti   {Path(video).name}")

    print(f"\ntotale: {len(kept_all)} fotogrammi distinti "
          f"(modo {args.mode}, primi {args.seconds}s)")
    if args.manifest:
        Path(args.manifest).write_text(
            json.dumps([str(p) for p in kept_all], indent=1), encoding="utf-8")
        print(f"manifest -> {args.manifest}")


if __name__ == "__main__":
    main()
