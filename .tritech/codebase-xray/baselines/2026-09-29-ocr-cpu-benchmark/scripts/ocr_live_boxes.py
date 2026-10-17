"""Throwaway: RapidOCR boxes for the 38 live captures (native ~1890 px), saved for the anchor-rules spike."""

import glob
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image
from rapidocr import OCRVersion, RapidOCR

REPO = Path(r"D:\Projects\poc-data-extraction")
OUT = Path(__file__).resolve().parent / "ocr_probe_out" / "live_boxes.json"

engine = RapidOCR(params={
    "Det.ocr_version": OCRVersion.PPOCRV6, "Rec.ocr_version": OCRVersion.PPOCRV6, "Global.log_level": "warning",
    "EngineConfig.onnxruntime.intra_op_num_threads": 4, "EngineConfig.onnxruntime.inter_op_num_threads": 1,
})
paths = sorted(glob.glob(str(REPO / "tests/fixtures/frames/no-tooltip-rita/*.png"))) + \
        sorted(glob.glob(str(REPO / "tests/fixtures/frames/tooltips-rita/*.png")))
dump = {}
for p in paths:
    im = Image.open(p).convert("RGB")
    t0 = time.perf_counter()
    res = engine(np.array(im))
    dt = time.perf_counter() - t0
    rel = str(Path(p).relative_to(REPO / "tests/fixtures/frames")).replace("\\", "/")
    lines = [] if res.txts is None else [
        {"text": t, "score": round(float(s), 3), "box": b.tolist()} for t, s, b in zip(res.txts, res.scores, res.boxes)]
    dump[rel] = {"size": list(im.size), "seconds": round(dt, 2), "lines": lines}
    print(f"{rel} {im.size} {dt:.1f}s {len(lines)} lines", flush=True)
OUT.write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
