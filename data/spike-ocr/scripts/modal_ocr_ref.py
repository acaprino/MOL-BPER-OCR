"""RapidOCR (PP-OCRv6 small) boxes for the 9 LUNARDI reference screens, on Modal CPU.

Rebuilds ocr_probe_out/rapid_v6_small_1x.json (lost with the session scratchpad). RapidOCR is
deterministic, so the boxes match the ones the first evaluations used.

    modal run modal_ocr_ref.py
"""

import io
import json
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent  # local scripts dir; inside the container this is /root
app = modal.App("bper-ocr-ref")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install("rapidocr==3.9.2", "onnxruntime", "pillow", "numpy")
    .run_commands("python -c \"from rapidocr import RapidOCR, OCRVersion; "
                  "RapidOCR(params={'Det.ocr_version': OCRVersion.PPOCRV6, 'Rec.ocr_version': OCRVersion.PPOCRV6})\"")
)


@app.function(image=image, cpu=(4.0, 4.0), memory=8192, timeout=900)
def ocr_all(items: list) -> dict:
    import numpy as np
    from PIL import Image
    from rapidocr import OCRVersion, RapidOCR

    engine = RapidOCR(params={
        "Det.ocr_version": OCRVersion.PPOCRV6, "Rec.ocr_version": OCRVersion.PPOCRV6, "Global.log_level": "warning",
        "EngineConfig.onnxruntime.intra_op_num_threads": 4, "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    })
    out = {}
    for sid, png in items:
        res = engine(np.array(Image.open(io.BytesIO(png)).convert("RGB")))
        out[sid] = [] if res.txts is None else [
            {"text": t, "score": round(float(s), 3), "box": b.tolist()} for t, s, b in zip(res.txts, res.scores, res.boxes)]
    return out


@app.local_entrypoint()
def main():
    repo = HERE.parents[2]  # computed locally only: the container has no repo layout
    items = [(f"screen {i}", (repo / f"data/reference/screen {i}.png").read_bytes()) for i in range(1, 10)]
    dump = ocr_all.remote(items)
    out = HERE / "ocr_probe_out"
    out.mkdir(exist_ok=True)
    (out / "rapid_v6_small_1x.json").write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
    print("OCR screens", len(dump), "lines", sum(len(v) for v in dump.values()), flush=True)
