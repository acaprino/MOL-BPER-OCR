"""Iteration 2: RapidOCR (PP-OCRv6 small) boxes for the framed recording frames, in parallel on Modal CPU.

    modal run modal_ocr_frames.py
"""

import io
import json
import time
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent  # local scripts dir; inside the container this is /root
app = modal.App("bper-ocr-frames")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install("rapidocr==3.9.2", "onnxruntime", "pillow", "numpy")
    .run_commands("python -c \"from rapidocr import RapidOCR, OCRVersion; "
                  "RapidOCR(params={'Det.ocr_version': OCRVersion.PPOCRV6, 'Rec.ocr_version': OCRVersion.PPOCRV6})\"")
)


@app.cls(image=image, cpu=(4.0, 4.0), memory=8192, timeout=1800)
class OCR:
    @modal.enter()
    def load(self):
        from rapidocr import OCRVersion, RapidOCR

        self.engine = RapidOCR(params={
            "Det.ocr_version": OCRVersion.PPOCRV6, "Rec.ocr_version": OCRVersion.PPOCRV6, "Global.log_level": "warning",
            "EngineConfig.onnxruntime.intra_op_num_threads": 4, "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        })

    @modal.method()
    def run(self, item):
        import numpy as np
        from PIL import Image

        fid, png = item
        im = Image.open(io.BytesIO(png)).convert("RGB")
        t0 = time.time()
        res = self.engine(np.array(im))
        lines = [] if res.txts is None else [
            {"text": t, "score": round(float(s), 3), "box": b.tolist()} for t, s, b in zip(res.txts, res.scores, res.boxes)]
        return fid, {"size": list(im.size), "seconds": round(time.time() - t0, 2), "lines": lines}


@app.local_entrypoint()
def main():
    items = [(p.stem, p.read_bytes()) for p in sorted((HERE / "iter2_frames").glob("*.png"))]
    dump = dict(OCR().run.map(items))
    out = HERE / "ocr_probe_out"
    out.mkdir(exist_ok=True)
    (out / "iter2_boxes.json").write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
    secs = [v["seconds"] for v in dump.values()]
    print(f"OCR frames={len(dump)} mean={sum(secs)/len(secs):.2f}s max={max(secs):.2f}s", flush=True)
