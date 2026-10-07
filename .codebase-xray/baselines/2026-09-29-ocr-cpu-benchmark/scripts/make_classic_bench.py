"""Generate one throwaway Modal app per classic OCR engine (isolated image builds)."""

from pathlib import Path

HERE = Path(__file__).resolve().parent

COMMON = '''"""Throwaway: {engine} on the 9 BPER screens, CPU-limited operator profiles, on Modal."""

import json
import os
import time
from pathlib import Path

import modal

REPO = Path(r"D:\\Projects\\poc-data-extraction")
OUT = Path(__file__).resolve().parent / "ocr_probe_out"
BUDGET_S = 1500
app = modal.App("ocr-bench-{engine}")

{image}


def _setup(threads):
{setup}


def _run(images, threads):
    import io
    from PIL import Image

    t0 = time.time()
    ocr = _setup(threads)
    load_s = round(time.time() - t0, 1)
    results, spent = {{}}, 0.0
    for scale in (1, 2):
        first = True
        for sid, png in images.items():
            if spent > BUDGET_S:
                break
            im = Image.open(io.BytesIO(png)).convert("RGB")
            if scale != 1:
                im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
            if first:
                ocr(im)  # warm-up
                first = False
            t1 = time.time()
            try:
                lines = [str(t) for t in ocr(im)]
            except Exception as exc:  # noqa: BLE001
                results[f"{{sid}}@{{scale}}x"] = {{"error": repr(exc)[:2000], "seconds": round(time.time() - t1, 2)}}
                continue
            dt = time.time() - t1
            spent += dt
            results[f"{{sid}}@{{scale}}x"] = {{"text": "\\n".join(lines), "seconds": round(dt, 2)}}
    return {{"threads": threads, "load_seconds": load_s, "screens": results}}


@app.function(image=image, cpu=(4.0, 4.0), memory=8192, timeout=3600)
def pc4(images):
    return {{"engine": "{engine}", "profile": "pc4", **_run(images, 4)}}


@app.function(image=image, cpu=(2.0, 2.0), memory=8192, timeout=3600)
def vdi2(images):
    return {{"engine": "{engine}", "profile": "vdi2", **_run(images, 2)}}


@app.local_entrypoint()
def main():
    images = {{f"screen {{i}}": (REPO / f"mnt/data/screen {{i}}.png").read_bytes() for i in range(1, 10)}}
    OUT.mkdir(exist_ok=True)
    for call in (pc4.spawn(images), vdi2.spawn(images)):
        try:
            res = call.get()
        except Exception as exc:  # noqa: BLE001
            print("CALL FAILED:", repr(exc)[:500], flush=True)
            continue
        name = f"{{res['engine']}}_{{res['profile']}}"
        (OUT / f"modal_{{name}}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        secs = [s.get("seconds", 0) for s in res["screens"].values()]
        errs = [k for k, s in res["screens"].items() if "error" in s]
        print(f"RESULT {{name}}: threads={{res['threads']}} load={{res['load_seconds']}}s screens={{len(secs)}} "
              f"mean={{round(sum(secs)/max(1, len(secs)), 1)}}s errors={{errs[:3]}}", flush=True)
'''

ENGINES = {
    "tesseract": (
        'image = (modal.Image.debian_slim(python_version="3.12")\n'
        '    .apt_install("tesseract-ocr", "tesseract-ocr-ita", "tesseract-ocr-eng")\n'
        '    .pip_install("pytesseract", "pillow", "numpy"))',
        '    os.environ["OMP_THREAD_LIMIT"] = str(threads)\n'
        '    import pytesseract\n'
        '    return lambda im: [ln for ln in pytesseract.image_to_string(im, lang="ita+eng", config="--oem 1 --psm 11").splitlines() if ln.strip()]',
    ),
    "easyocr": (
        'image = (modal.Image.debian_slim(python_version="3.12")\n'
        '    .apt_install("libgl1", "libglib2.0-0")\n'
        '    .pip_install("torch", "torchvision", index_url="https://download.pytorch.org/whl/cpu")\n'
        '    .pip_install("easyocr", "pillow", "numpy")\n'
        '    .run_commands("python -c \\"import easyocr; easyocr.Reader([\'it\', \'en\'], gpu=False)\\""))',
        '    import numpy as np\n'
        '    import torch\n'
        '    import easyocr\n'
        '    torch.set_num_threads(threads)\n'
        '    reader = easyocr.Reader(["it", "en"], gpu=False)\n'
        '    return lambda im: [t for _, t, _ in reader.readtext(np.array(im))]',
    ),
    "paddleocr": (
        'image = (modal.Image.debian_slim(python_version="3.12")\n'
        '    .apt_install("libgl1", "libglib2.0-0", "libgomp1")\n'
        '    .pip_install("paddlepaddle", "paddleocr", "pillow", "numpy")\n'
        '    .run_commands("python -c \\"from paddleocr import PaddleOCR; PaddleOCR(lang=\'it\', use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)\\""))',
        '    import numpy as np\n'
        '    from paddleocr import PaddleOCR\n'
        '    ocr = PaddleOCR(lang="it", use_doc_orientation_classify=False, use_doc_unwarping=False,\n'
        '                    use_textline_orientation=False, cpu_threads=threads)\n'
        '    return lambda im: list(ocr.predict(np.ascontiguousarray(np.array(im)[:, :, ::-1]))[0]["rec_texts"])',
    ),
    "mmocr": (
        'image = (modal.Image.debian_slim(python_version="3.10")\n'
        '    .apt_install("libgl1", "libglib2.0-0", "libgomp1", "build-essential")\n'
        '    .pip_install("torch==2.0.1", "torchvision==0.15.2", index_url="https://download.pytorch.org/whl/cpu")\n'
        '    .pip_install("numpy<2", "mmengine==0.10.4", "pillow")\n'
        '    .run_commands("pip install mmcv==2.0.1 -f https://download.openmmlab.com/mmcv/dist/cpu/torch2.0/index.html",\n'
        '                  "pip install mmdet==3.1.0 mmocr==1.0.1",\n'
        '                  "python -c \\"from mmocr.apis import MMOCRInferencer; MMOCRInferencer(det=\'DBNet\', rec=\'SAR\', device=\'cpu\')\\""))',
        '    import numpy as np\n'
        '    import torch\n'
        '    from mmocr.apis import MMOCRInferencer\n'
        '    torch.set_num_threads(threads)\n'
        '    inf = MMOCRInferencer(det="DBNet", rec="SAR", device="cpu")\n'
        '    return lambda im: inf(np.ascontiguousarray(np.array(im)[:, :, ::-1]), return_vis=False)["predictions"][0]["rec_texts"]',
    ),
}

for engine, (image, setup) in ENGINES.items():
    (HERE / f"modal_classic_{engine}.py").write_text(COMMON.format(engine=engine, image=image, setup=setup), encoding="utf-8")
    print("wrote", engine)
