"""Benchmark DINO backbones on the framing corpus: localization IoU and latency.

"Best backbone" is a measurement, not an opinion. This runs the same patch-token
localization sweep with each candidate backbone over the composition corpus
produced by make_framing_corpus.py (ground-truth rectangles known to the pixel)
and reports IoU statistics and per-frame cost side by side.

    python tools/benchmark_backbones.py --corpus <dir> \
        --backbones dinov2_vits14,dinov2_vits14_reg,dinov3_vits16

DINOv3 weights are license-gated (HTTP 403 on the public URL). Two ways in:
place the torch.hub checkpoint under %USERPROFILE%/.cache/torch/hub/checkpoints/
(or point DINOV3_WEIGHTS at it), or pass a transformers-format directory as
`hf:<path>` -- the layout the gated Hugging Face download actually ships, holding
config.json + model.safetensors. Patch size and register count are read from the
model config.

Classification benchmarking is deliberately absent until a human-validated
label set exists: measuring one model's labels against another model's labels
would measure agreement, not accuracy.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms as T

Rect = Tuple[int, int, int, int]

NORM = T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])

# name -> (hub repo, patch size). dinov2 entries use the main branch here rather
# than the commit page_classifier.py pins: this is a dev-side benchmark, and the
# _reg entrypoints postdate that pin. Production adoption re-pins.
BACKBONES: Dict[str, Tuple[str, int]] = {
    "dinov2_vits14": ("facebookresearch/dinov2", 14),
    "dinov2_vits14_reg": ("facebookresearch/dinov2", 14),
    "dinov2_vitb14_reg": ("facebookresearch/dinov2", 14),
    "dinov3_vits16": ("facebookresearch/dinov3", 16),
    "dinov3_vitb16": ("facebookresearch/dinov3", 16),
}


class HFBackbone:
    """Adapter: a transformers DINOv3 checkpoint behind the forward_features dict API."""

    def __init__(self, path: str) -> None:
        from transformers import AutoModel  # dev-side dependency, benchmark only

        self.model = AutoModel.from_pretrained(path)
        self.model.eval()
        cfg = self.model.config
        self.patch = int(cfg.patch_size)
        self._specials = 1 + int(getattr(cfg, "num_register_tokens", 0))

    def forward_features(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
        out = self.model(pixel_values=x)
        return {"x_norm_patchtokens": out.last_hidden_state[:, self._specials:, :]}


def load_backbone(name: str) -> Tuple[object, int]:
    """Returns (model exposing forward_features, patch size)."""
    if name.startswith("hf:"):
        adapter = HFBackbone(name[3:])
        return adapter, adapter.patch
    repo, patch = BACKBONES[name]
    try:
        model = torch.hub.load(repo, name)
    except Exception:
        override = os.environ.get("DINOV3_WEIGHTS")
        if name.startswith("dinov3") and override:
            model = torch.hub.load(repo, name, weights=override)
        else:
            raise
    model.eval()
    return model, patch


def patch_grid(model: torch.nn.Module, patch: int, img: Image.Image, w: int, h: int) -> torch.Tensor:
    """[gh, gw, D] L2-normalized patch tokens for `img` resized to (w, h)."""
    x = NORM(T.ToTensor()(img.convert("RGB").resize((w, h), Image.Resampling.BICUBIC))).unsqueeze(0)
    with torch.no_grad():
        tokens = model.forward_features(x)["x_norm_patchtokens"][0]
    return F.normalize(tokens, dim=-1).reshape(h // patch, w // patch, -1)


def localize(
    model: torch.nn.Module,
    patch: int,
    detector: torch.Tensor,
    frame: Image.Image,
    aspect_wh: float,
    sweep_w: int = 1120,
) -> Rect:
    """Best-matching window over an integral image of patch tokens."""
    W, H = frame.size
    fh = round(sweep_w * 0.625 / patch) * patch  # ~16:10 sweep canvas
    grid = patch_grid(model, patch, frame, sweep_w, fh)
    gh, gw, dim = grid.shape
    integral = torch.zeros(gh + 1, gw + 1, dim)
    integral[1:, 1:] = grid.cumsum(0).cumsum(1)

    grid_aspect = aspect_wh * (sweep_w / W) * (H / fh)
    best: Optional[Tuple[float, int, int, int, int]] = None
    for win_w in range(10, gw + 1, 2):
        win_h = int(round(win_w / grid_aspect))
        if win_h < 4 or win_h > gh:
            continue
        for top in range(0, gh - win_h + 1, 2):
            for left in range(0, gw - win_w + 1, 2):
                s = (integral[top + win_h, left + win_w] - integral[top, left + win_w]
                     - integral[top + win_h, left] + integral[top, left])
                score = float(F.normalize(s / (win_w * win_h), dim=0) @ detector)
                if best is None or score > best[0]:
                    best = (score, left, top, win_w, win_h)

    _, l, t, ww, hh = best  # type: ignore[misc]
    return (int(l * patch / sweep_w * W), int(t * patch / fh * H),
            int((l + ww) * patch / sweep_w * W), int((t + hh) * patch / fh * H))


def iou(a: Rect, b: Rect) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)
    return inter / union if union else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", required=True, help="dir with manifest.json from make_framing_corpus.py")
    ap.add_argument("--pages", default="src/edge-agent/assets/templates/bper", help="source page images")
    ap.add_argument("--backbones", default="dinov2_vits14,dinov2_vits14_reg")
    ap.add_argument("--limit", type=int, default=0, help="cap frames per backbone (0 = all)")
    ap.add_argument("--report", default="", help="optional JSON output path")
    args = ap.parse_args()

    corpus = Path(args.corpus)
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    if args.limit:
        manifest = manifest[: args.limit]
    sources = {p.stem: Image.open(p).convert("RGB")
               for p in Path(args.pages).glob("*.png")}

    results: Dict[str, Dict[str, object]] = {}
    for name in [b.strip() for b in args.backbones.split(",") if b.strip()]:
        if not name.startswith("hf:") and name not in BACKBONES:
            print(f"{name}: sconosciuto (noti: {', '.join(BACKBONES)}, oppure hf:<dir>)")
            continue
        try:
            model, patch = load_backbone(name)
        except Exception as e:
            print(f"{name}: NON DISPONIBILE ({type(e).__name__}: {str(e)[:120]})")
            continue

        template_means: List[torch.Tensor] = []
        for img in sources.values():
            g = patch_grid(model, patch, img, 224, 224)
            template_means.append(g.reshape(-1, g.shape[-1]).mean(0))
        detector = F.normalize(torch.stack(template_means).mean(0), dim=0)

        ious: List[float] = []
        t0 = time.time()
        for entry in manifest:
            frame = Image.open(corpus / entry["file"]).convert("RGB")
            src = sources[entry["label"]]
            rect = localize(model, patch, detector, frame, src.width / src.height)
            ious.append(iou(rect, tuple(entry["rect"])))
        per_frame = (time.time() - t0) / len(manifest)

        ious.sort()
        stats = {
            "frames": len(ious),
            "iou_median": round(ious[len(ious) // 2], 3),
            "iou_mean": round(sum(ious) / len(ious), 3),
            "iou_min": round(ious[0], 3),
            "iou_ge_0.5": sum(1 for v in ious if v >= 0.5),
            "iou_ge_0.7": sum(1 for v in ious if v >= 0.7),
            "iou_ge_0.9": sum(1 for v in ious if v >= 0.9),
            "s_per_frame": round(per_frame, 2),
        }
        results[name] = stats
        print(f"{name:22} mediana {stats['iou_median']:.3f}  media {stats['iou_mean']:.3f}  "
              f"min {stats['iou_min']:.3f}  >=0.7: {stats['iou_ge_0.7']}/{len(ious)}  "
              f">=0.9: {stats['iou_ge_0.9']}/{len(ious)}  {stats['s_per_frame']}s/frame")

    if args.report and results:
        Path(args.report).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nreport -> {args.report}")


if __name__ == "__main__":
    main()
