"""Run RapidOCR (PP-OCRv6 small, ONNX, CPU) on every screenshot of a folder and save the raw text boxes.

Usage: python ocr_local_rapid.py <input_dir> <out.json> [scale]
Everything stays on this machine. Same engine and settings as the 2026-09-29 CPU benchmark.
"""
import json
import os
import sys
import time

import numpy as np
from PIL import Image
from rapidocr import OCRVersion, RapidOCR

input_dir, out_path = sys.argv[1], sys.argv[2]
scale = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
engine = RapidOCR(params={
    "Det.ocr_version": OCRVersion.PPOCRV6,
    "Rec.ocr_version": OCRVersion.PPOCRV6,
    "Global.log_level": "warning",
    "EngineConfig.onnxruntime.intra_op_num_threads": 4,
    "EngineConfig.onnxruntime.inter_op_num_threads": 1,
})
result = {}
names = sorted(f for f in os.listdir(input_dir) if f.lower().endswith(".png"))
for i, name in enumerate(names):
    img = Image.open(os.path.join(input_dir, name)).convert("RGB")
    if scale != 1.0:
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    started = time.time()
    res = engine(np.array(img))
    elapsed = time.time() - started
    items = [] if res.txts is None else [
        [text, float(score), [[float(v) / scale for v in point] for point in box.tolist()]]
        for text, score, box in zip(res.txts, res.scores, res.boxes)
    ]
    result[os.path.splitext(name)[0]] = {"seconds": round(elapsed, 2), "items": items}
    if i % 10 == 0:
        print(f"{i + 1}/{len(names)} {name} {elapsed:.1f}s {len(items)} boxes", flush=True)
json.dump(result, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
times = [v["seconds"] for v in result.values()][1:]
print(f"done: {len(result)} screens, mean {sum(times) / max(len(times), 1):.2f}s, max {max(times):.2f}s (first screen excluded as warm-up)")
