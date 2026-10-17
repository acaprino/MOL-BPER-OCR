"""Measure whether page classification can run locally on DINO prototypes.

The question this answers: with prototypes built from *real* crops instead of the
nine window screenshots, can the local classifier decide the page, so the VLM call
leaves the recognition path?

Two design choices matter more than the numbers.

Split by recording, never by frame. Frames from one session are near-duplicates of
each other: a random split would put a frame in the prototypes and its neighbour in
the test set, and report a score that says nothing about a new session. Held-out
recordings are the only honest test here.

Report the margin, not just accuracy. The intended architecture decides locally when
confident and defers to the VLM when not, so what matters is whether the two are
separable: correct decisions should carry a margin that wrong ones do not. Accuracy
alone hides that.

    python tools/measure_classifier.py --registry <path> --frames-dir <dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, "src/edge-agent")

import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms as T

NORM = T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
SIDE = 224
MIN_PROTOTYPE_EXAMPLES = 3  # below this a class is reported, not silently dropped


def load_model() -> Any:
    from page_classifier import DINOV2_HUB_REPO, DINOV2_MODEL_NAME

    model = torch.hub.load(DINOV2_HUB_REPO, DINOV2_MODEL_NAME)
    model.eval()
    return model


def embed(model: Any, img: Image.Image, spatial: bool) -> torch.Tensor:
    """One descriptor per image. spatial=True keeps the patch layout."""
    x = NORM(T.ToTensor()(img.convert("RGB").resize((SIDE, SIDE), Image.Resampling.BICUBIC)))
    with torch.no_grad():
        tokens = model.forward_features(x.unsqueeze(0))["x_norm_patchtokens"][0]
    tokens = F.normalize(tokens, dim=-1)
    return F.normalize(tokens.reshape(-1) if spatial else tokens.mean(0), dim=0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--registry", default="tests/fixtures/frames/registry.json")
    ap.add_argument("--frames-dir", default="tests/fixtures/frames")
    ap.add_argument("--holdout", default="20250922-parte01",
                    help="substring of the recordings held out for testing")
    args = ap.parse_args()

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    frames_dir = Path(args.frames_dir)

    train: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    test: List[Dict[str, Any]] = []
    for entry in registry["frames"]:
        cluster = entry.get("cluster")
        if not entry.get("video"):
            continue  # first pass did not record provenance; cannot be split honestly
        if args.holdout in entry["video"]:
            test.append(entry)
        elif cluster and cluster.isdigit():
            train[cluster].append(entry)

    usable = {c: rows for c, rows in train.items() if len(rows) >= MIN_PROTOTYPE_EXAMPLES}
    thin = {c: len(rows) for c, rows in train.items() if len(rows) < MIN_PROTOTYPE_EXAMPLES}
    print(f"prototipi da {sum(len(v) for v in usable.values())} ritagli, "
          f"classi utilizzabili: {sorted(usable)}")
    if thin:
        print(f"classi scartate per pochi esempi (<{MIN_PROTOTYPE_EXAMPLES}): {thin}")
    print(f"test: registrazione tenuta fuori '{args.holdout}', {len(test)} fotogrammi\n")

    model = load_model()
    for spatial in (False, True):
        kind = "griglia spaziale" if spatial else "media dei patch"
        protos: Dict[str, torch.Tensor] = {}
        for cluster, rows in usable.items():
            vecs = []
            for row in rows:
                path = frames_dir / row["frame"]
                if not path.exists():
                    continue
                rect = row.get("app_rect")
                img = Image.open(path)
                if rect:
                    img = img.crop(tuple(rect))
                vecs.append(embed(model, img, spatial))
            if vecs:
                protos[cluster] = F.normalize(torch.stack(vecs).mean(0), dim=0)

        names = sorted(protos)
        matrix = torch.stack([protos[n] for n in names])
        centroid = matrix.mean(0)
        centered = F.normalize(matrix - centroid, p=2, dim=1)

        stats = {"pagina": [], "negativo": []}
        for entry in test:
            path = frames_dir / entry["frame"]
            if not path.exists():
                continue
            rect = entry.get("app_rect")
            img = Image.open(path)
            if rect:
                img = img.crop(tuple(rect))
            q = F.normalize(embed(model, img, spatial) - centroid, dim=0)
            scores = centered @ q
            order = scores.argsort(descending=True)
            top, runner = names[int(order[0])], float(scores[order[0]]) - float(scores[order[1]])
            truth = entry.get("cluster")
            bucket = "pagina" if truth and truth.isdigit() else "negativo"
            stats[bucket].append((truth, top, float(scores[order[0]]), runner))

        pages = stats["pagina"]
        known = [r for r in pages if r[0] in names]
        correct = [r for r in known if r[0] == r[1]]
        print(f"--- {kind} ---")
        if known:
            print(f"  pagine con prototipo: {len(correct)}/{len(known)} corrette "
                  f"({100*len(correct)/len(known):.0f}%)")
            good_margin = sorted(r[3] for r in correct)
            bad = [r for r in known if r[0] != r[1]]
            if good_margin:
                print(f"    margine corrette: mediano {good_margin[len(good_margin)//2]:.3f}, "
                      f"minimo {good_margin[0]:.3f}")
            if bad:
                bm = sorted(r[3] for r in bad)
                print(f"    margine sbagliate: mediano {bm[len(bm)//2]:.3f}, massimo {bm[-1]:.3f}")
        others = [r for r in pages if r[0] not in names]
        if others:
            print(f"  pagine senza prototipo (non valutabili): {len(others)} "
                  f"{Counter(r[0] for r in others)}")
        negs = stats["negativo"]
        if negs:
            nm = sorted(r[3] for r in negs)
            print(f"  negativi: {len(negs)}, margine mediano {nm[len(nm)//2]:.3f}, "
                  f"massimo {nm[-1]:.3f}")
            print("    (un negativo con margine alto e' un falso positivo sicuro di se')")
        print()


if __name__ == "__main__":
    main()
