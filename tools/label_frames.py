"""Localize the application window in each frame and classify it against a process.

Two things this does that the first labelling pass did not, and both were the
cause of its errors:

1. It builds the prompt from processes/<id>.json instead of a hand-written list of
   page names. The catalog carries each page's positive signature *and* what
   excludes it, plus the application's identifying marks and, decisively,
   `not_this_application`. Without that last part a classifier forced to choose
   among N pages picks the closest one even when the application is a different
   one entirely, which is exactly what happened: screens from the qtask
   underwriting tool were labelled as BPER pages because they carry fields named
   "Nota ...".

2. It distinguishes three kinds of negative rather than one. A screen belonging to
   the right application but outside the process (Gestione Documentale, reached
   from the navigator's Funzioni) is the hard case and must be told apart from a
   different application and from a black frame, because a rejection threshold
   calibrated on the easy ones says nothing about the hard one.

    python tools/label_frames.py --frames <list.json> --out <dir> --process bper-p1
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, "src/edge-agent")

import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms as T

NORM = T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
PATCH, SWEEP_W, SWEEP_H = 14, 1120, 700
MARGIN = 0.04  # widen the found rectangle: overshooting is harmless, amputating is not

# A candidate window must cover at least this fraction of the frame. Without it the
# sweep sometimes settles on a panel or a table inside the page: measured across 2098
# frames, 36% of rectangles came back under 0.6 Mpx against a median of 1.10, the worst
# being 249x203 on a 1920x1080 desktop. The score is normalized per window, so a small
# uniform region can outscore the real window on average similarity while containing
# none of the marks that identify the application: URL bar, BPER logo, navigator. The
# classifier then answers about a table it was handed, and the answer gets recorded as
# a classification error rather than the localization error it is.
MIN_AREA_FRACTION = 0.20


def build_prompt(process: Dict[str, Any]) -> str:
    """Compose the classification prompt out of the process catalog."""
    app = process["application"]
    lines = [
        f"Classifichi schermate del processo <<{process['name']} - {process['title']}>>.",
        "",
        f"PRIMA verifica che l'applicativo sia <<{app['name']}>>. Lo riconosci da:",
    ]
    lines += [f"  - {mark}" for mark in app["identifying_marks"]]
    lines += ["", "NON e' questo applicativo (rispondi 'altro-app'):"]
    lines += [f"  - {mark}" for mark in app["not_this_application"]]
    lines += ["", "Se l'applicativo e' quello giusto, scegli la pagina del processo:"]
    for page in process["pages"]:
        lines.append(f"  [{page['order']}] {page['name']}")
        lines.append(f"      e': {page['signature']}")
        for excl in page["excludes"]:
            lines.append(f"      non e': {excl}")
    lines += [
        "",
        "Se e' l'applicativo giusto ma NESSUNA di queste pagine, rispondi 'altro-bper'.",
        "Se e' un altro applicativo, rispondi 'altro-app'.",
        "Se e' nero, una transizione o un popup senza contenuto, rispondi 'altro-nulla'.",
        "",
        "Preferisci un 'altro-*' ogni volta che la corrispondenza e' dubbia: un falso "
        "positivo consuma lo slot di una pagina per l'intero lavoro.",
        "",
        'Rispondi SOLO JSON: {"cluster": "<1..9 oppure altro-bper/altro-app/altro-nulla>", '
        '"confidence": 0.0, "perche": "<max 12 parole>"}',
    ]
    return "\n".join(lines)


def save_atomic(path: Path, payload: Any) -> None:
    """Write via a temporary file and rename, so a reader never sees a half file.

    Reading labels.json mid-write once showed 425 records where 505 existed, and
    that was diagnosed as data loss before it was recognised as a torn read. The
    rename is atomic on the same filesystem, so a reader sees either the previous
    complete file or the new one, never a prefix.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_model() -> Any:
    from page_classifier import DINOV2_HUB_REPO, DINOV2_MODEL_NAME

    model = torch.hub.load(DINOV2_HUB_REPO, DINOV2_MODEL_NAME)
    model.eval()
    return model


def patch_grid(model: Any, img: Image.Image, w: int, h: int) -> torch.Tensor:
    x = NORM(T.ToTensor()(img.convert("RGB").resize((w, h), Image.Resampling.BICUBIC))).unsqueeze(0)
    with torch.no_grad():
        tokens = model.forward_features(x)["x_norm_patchtokens"][0]
    return F.normalize(tokens, dim=-1).reshape(h // PATCH, w // PATCH, -1)


def localize(model: Any, detector: torch.Tensor, frame: Image.Image,
             aspect: float) -> Tuple[float, Tuple[int, int, int, int]]:
    """Best-matching window over an integral image of patch tokens."""
    W, H = frame.size
    grid = patch_grid(model, frame, SWEEP_W, SWEEP_H)
    gh, gw, dim = grid.shape
    integral = torch.zeros(gh + 1, gw + 1, dim)
    integral[1:, 1:] = grid.cumsum(0).cumsum(1)
    grid_aspect = aspect * (SWEEP_W / W) * (H / SWEEP_H)

    best: Optional[Tuple[float, int, int, int, int]] = None
    cells = gh * gw
    for win_w in range(10, gw + 1, 2):
        win_h = int(round(win_w / grid_aspect))
        if win_h < 4 or win_h > gh:
            continue
        if (win_w * win_h) / cells < MIN_AREA_FRACTION:
            continue
        sums = (integral[win_h:, win_w:] - integral[win_h:, :-win_w]
                - integral[:-win_h, win_w:] + integral[:-win_h, :-win_w])
        scores = F.normalize(sums, dim=-1) @ detector
        peak = float(scores.max())
        if best is None or peak > best[0]:
            idx = int(scores.argmax())
            top, left = divmod(idx, scores.shape[1])
            best = (peak, left, top, win_w, win_h)

    score, l, t, ww, hh = best  # type: ignore[misc]
    x1, y1 = l * PATCH / SWEEP_W * W, t * PATCH / SWEEP_H * H
    x2, y2 = (l + ww) * PATCH / SWEEP_W * W, (t + hh) * PATCH / SWEEP_H * H
    mx, my = (x2 - x1) * MARGIN, (y2 - y1) * MARGIN
    return score, (max(0, int(x1 - mx)), max(0, int(y1 - my)),
                   min(W, int(x2 + mx)), min(H, int(y2 + my)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frames", required=True, help="json list of frame paths")
    ap.add_argument("--out", required=True, help="directory for crops and labels.json")
    ap.add_argument("--process", default="bper-p1")
    ap.add_argument("--templates", default="src/edge-agent/assets/templates/bper")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--batch", type=int, default=50,
                    help="frames per batch; results are checkpointed after each one")
    ap.add_argument("--restart", action="store_true",
                    help="ignore existing results and label everything again")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after this many frames and exit; together with resume this "
                         "lets a driver run each batch as a fresh process, so torch arenas "
                         "and decoded images go back to the OS between batches instead of "
                         "accumulating for the whole run (0 = no limit)")
    args = ap.parse_args()

    process = json.loads(Path(f"processes/{args.process}.json").read_text(encoding="utf-8"))
    prompt = build_prompt(process)
    out = Path(args.out)
    (out / "crops").mkdir(parents=True, exist_ok=True)
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")

    model = load_model()
    templates = sorted(Path(args.templates).glob("*.png"))
    means = []
    for tpl in templates:
        grid = patch_grid(model, Image.open(tpl), 224, 224)
        means.append(grid.reshape(-1, grid.shape[-1]).mean(0))
    detector = F.normalize(torch.stack(means).mean(0), dim=0)
    reference = Image.open(templates[0])
    aspect = reference.width / reference.height

    from dotenv import load_dotenv

    load_dotenv(".env")
    from config import AgentConfig
    from openai import OpenAI

    cfg = AgentConfig(Path("src/edge-agent/config.ini"))
    key, base_url, model_name = cfg.resolve_llm_settings()
    client = OpenAI(api_key=key, base_url=base_url)

    labels_path = out / "labels.json"
    records: List[Dict[str, Any]] = []
    if labels_path.exists() and not args.restart:
        records = json.loads(labels_path.read_text(encoding="utf-8"))
        # A record without a cluster is a failed call, not a done frame: retry it.
        records = [r for r in records if r.get("cluster")]
    done = {r["source"] for r in records}

    frames = [Path(p) for p in json.loads(Path(args.frames).read_text(encoding="utf-8"))]
    total = len(frames)
    frames = [f for f in frames if f.name not in done]
    remaining = len(frames)
    if args.limit:
        frames = frames[:args.limit]
    if done:
        tail = f", ne prendo {len(frames)} in questa esecuzione" if args.limit else ""
        print(f"ripresa: {len(done)} gia' fatti, {remaining} da fare{tail}", flush=True)
    if not frames:
        print("niente da fare: tutti i fotogrammi sono gia' etichettati", flush=True)
        return
    lock = threading.Lock()

    def classify(base: Dict[str, Any], crop: Image.Image) -> None:
        buf = io.BytesIO()
        crop.save(buf, "JPEG", quality=88, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode()
        try:
            reply = client.chat.completions.create(
                model=model_name, temperature=0.0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": "Classifica questa schermata."},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]},
                ])
            payload = re.sub(r"```(?:json)?|```", "", reply.choices[0].message.content).strip()
            data = json.loads(payload)
            base["cluster"] = str(data.get("cluster", "altro-nulla"))
            base["confidence"] = data.get("confidence")
            base["perche"] = data.get("perche")
        except Exception as exc:  # noqa: BLE001
            base["cluster"] = None
            base["error"] = str(exc)[:140]
        with lock:
            records.append(base)

    start = time.time()
    processed = 0
    for offset in range(0, len(frames), args.batch):
        batch = frames[offset:offset + args.batch]
        # One pool per batch: leaving the block waits for every call in it, so the
        # checkpoint below is written only once the batch is genuinely complete.
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for path in batch:
                frame = Image.open(path).convert("RGB")
                score, rect = localize(model, detector, frame, aspect)
                crop = frame.crop(rect)
                crop.save(out / "crops" / f"{path.stem}.jpg", "JPEG", quality=88, optimize=True)
                pool.submit(classify, {"file": f"{path.stem}.jpg", "source": path.name,
                                       "video": path.parent.name, "rect": list(rect),
                                       "loc_score": round(score, 4)}, crop)
        save_atomic(labels_path, records)
        processed += len(batch)
        elapsed = time.time() - start
        print(f"[checkpoint] {len(records)}/{total} totali, {processed} in questa sessione, "
              f"{elapsed/processed:.2f}s/frame, residuo ~{(len(frames)-processed)*elapsed/processed/60:.0f} min",
              flush=True)

    save_atomic(labels_path, records)
    counts = Counter(r.get("cluster") or "(errore)" for r in records)
    print(f"\nFINITO: {len(records)} in {(time.time()-start)/60:.1f} min")
    for cluster, n in counts.most_common():
        print(f"  {n:4}  {cluster}")

    left = remaining - len(frames)
    if left > 0:
        # Exit 10 means "work remains": the driver loop reads this and starts a
        # fresh process, which is the point of the limit.
        print(f"restano {left} fotogrammi: richiamare per continuare", flush=True)
        raise SystemExit(10)


if __name__ == "__main__":
    main()
