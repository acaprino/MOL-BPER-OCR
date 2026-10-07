"""Throwaway benchmark: OCR models on the 9 BPER screens, CPU only, on Modal.

Simulates a BPER operator workstation: no GPU, 8 GB RAM, two CPU profiles
("pc4" = 4 physical cores, an office Core i5; "vdi2" = 2 cores, a lean virtual
desktop). Each engine/profile runs in its own container; scoring happens locally.

    modal run modal_ocr_bench.py
"""

import base64
import io
import json
import os
import subprocess
import time
from pathlib import Path

import modal

MEMORY_MB = 8192
BUDGET_S = 1500  # stop an engine once it has spent this long on screens
REPO = Path(r"D:\Projects\poc-data-extraction")
OUT = Path(__file__).resolve().parent / "ocr_probe_out"

app = modal.App("ocr-bench-bper")

llama_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "cmake", "build-essential", "libgomp1", "curl", "libgl1", "libglib2.0-0")
    .run_commands(
        "git clone --depth 1 https://github.com/ggml-org/llama.cpp /opt/llama.cpp",
        "cmake -S /opt/llama.cpp -B /opt/llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF "
        "-DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF",
        "cmake --build /opt/llama.cpp/build -j 16 --target llama-server",
    )
    .pip_install("huggingface_hub[hf_xet]", "requests")
    .run_commands(
        "hf download noctrex/LightOnOCR-2-1B-GGUF LightOnOCR-2-1B-Q8_0.gguf LightOnOCR-2-1B-Q4_K_M.gguf "
        "mmproj-F32.gguf --local-dir /models/lighton",
        "hf download PaddlePaddle/PaddleOCR-VL-1.6-GGUF --local-dir /models/paddlevl",
    )
)

falcon_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", "torchvision", index_url="https://download.pytorch.org/whl/cpu")
    .pip_install("transformers", "einops", "pillow", "accelerate", "triton", "requests")
    .run_commands("python -c \"from huggingface_hub import snapshot_download; "
                  "snapshot_download('tiiuae/Falcon-OCR', local_dir='/models/falcon')\"")
    .env({"TORCH_COMPILE_DISABLE": "1"})
)

rapid_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install("rapidocr", "onnxruntime", "pillow", "numpy")
    .run_commands("python -c \"from rapidocr import RapidOCR, OCRVersion; "
                  "RapidOCR(params={'Det.ocr_version': OCRVersion.PPOCRV6, 'Rec.ocr_version': OCRVersion.PPOCRV6})\"")
)

LLAMA_MODELS = {
    "lighton_q8": ("/models/lighton/LightOnOCR-2-1B-Q8_0.gguf", "/models/lighton/mmproj-F32.gguf", None),
    "lighton_q4": ("/models/lighton/LightOnOCR-2-1B-Q4_K_M.gguf", "/models/lighton/mmproj-F32.gguf", None),
    "paddlevl": ("/models/paddlevl/PaddleOCR-VL-1.6-GGUF.gguf", "/models/paddlevl/PaddleOCR-VL-1.6-GGUF-mmproj.gguf", "OCR:"),
}


def _machine() -> dict:
    """CPU model and the cgroup CPU quota actually granted to this container."""
    name = "?"
    for line in open("/proc/cpuinfo"):
        if line.startswith("model name"):
            name = line.split(":", 1)[1].strip()
            break
    quota = None
    try:
        q, period = open("/sys/fs/cgroup/cpu.max").read().split()
        if q != "max":
            quota = round(int(q) / int(period), 2)
    except (OSError, ValueError):
        pass
    return {"cpu_model": name, "cpu_quota": quota, "os_cpu_count": os.cpu_count()}




# ------------------------------------------------------------ engines

def _run_llama(key: str, images: dict, threads: int) -> dict:
    import requests

    model, mmproj, prompt = LLAMA_MODELS[key]
    server = subprocess.Popen(
        ["/opt/llama.cpp/build/bin/llama-server", "-m", model, "--mmproj", mmproj, "--port", "8080",
         "--host", "127.0.0.1", "-t", str(threads), "-c", "16384", "--temp", "0"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    t0 = time.time()
    while True:
        try:
            if requests.get("http://127.0.0.1:8080/health", timeout=2).status_code == 200:
                break
        except requests.RequestException:
            pass
        if server.poll() is not None:
            return {"error": "server exited", "stderr": server.stderr.read()[-3000:]}
        if time.time() - t0 > 600:
            return {"error": "server did not start"}
        time.sleep(2)
    load_s = time.time() - t0

    results, spent = {}, 0.0
    for sid, png in images.items():
        if spent > BUDGET_S:
            break
        content = [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}]
        if prompt:
            content.append({"type": "text", "text": prompt})
        body = {"messages": [{"role": "user", "content": content}], "temperature": 0, "max_tokens": 4096}
        t1 = time.time()
        r = requests.post("http://127.0.0.1:8080/v1/chat/completions", json=body, timeout=3600)
        wall = time.time() - t1
        spent += wall
        if r.status_code != 200:
            results[sid] = {"error": r.text[:1000], "seconds": round(wall, 2)}
            continue
        d = r.json()
        results[sid] = {"text": d["choices"][0]["message"]["content"], "seconds": round(wall, 2), "timings": d.get("timings")}
    server.terminate()
    return {"threads": threads, "load_seconds": round(load_s, 1), "screens": results}


def _run_falcon(images: dict, threads: int) -> dict:
    import torch
    from PIL import Image
    from transformers import AutoModelForCausalLM

    torch.set_num_threads(threads)
    t0 = time.time()
    try:
        model = AutoModelForCausalLM.from_pretrained("/models/falcon", trust_remote_code=True, torch_dtype=torch.float32)
        model.eval()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"load: {exc!r}"[:3000]}
    load_s = time.time() - t0
    results, spent = {}, 0.0
    for sid, png in images.items():
        if spent > BUDGET_S:
            break
        im = Image.open(io.BytesIO(png)).convert("RGB")
        t1 = time.time()
        try:
            with torch.inference_mode():
                text = model.generate(im)[0]
        except Exception as exc:  # noqa: BLE001
            results[sid] = {"error": repr(exc)[:3000], "seconds": round(time.time() - t1, 2)}
            break
        spent += time.time() - t1
        results[sid] = {"text": text, "seconds": round(time.time() - t1, 2)}
    return {"threads": threads, "load_seconds": round(load_s, 1), "screens": results}


def _run_rapid(images: dict, threads: int) -> dict:
    import numpy as np
    from PIL import Image
    from rapidocr import OCRVersion, RapidOCR

    engine = RapidOCR(params={
        "Det.ocr_version": OCRVersion.PPOCRV6, "Rec.ocr_version": OCRVersion.PPOCRV6, "Global.log_level": "warning",
        "EngineConfig.onnxruntime.intra_op_num_threads": threads,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    })
    results = {}
    for scale in (1, 2):
        first = True
        for sid, png in images.items():
            im = Image.open(io.BytesIO(png)).convert("RGB")
            if scale != 1:
                im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
            arr = np.array(im)
            if first:
                engine(arr)  # warm-up
                first = False
            t1 = time.time()
            res = engine(arr)
            lines = [] if res.txts is None else list(res.txts)
            results[f"{sid}@{scale}x"] = {"text": "\n".join(lines), "seconds": round(time.time() - t1, 2)}
    return {"threads": threads, "screens": results}


def _tag(result: dict, engine: str, profile: str) -> dict:
    return {"engine": engine, "profile": profile, **_machine(), **result}


# ------------------------------------------------------------ Modal functions, one per CPU profile

@app.function(image=llama_image, cpu=(4.0, 4.0), memory=MEMORY_MB, timeout=3600)
def llama_pc4(key: str, images: dict) -> dict:
    return _tag(_run_llama(key, images, 4), key, "pc4")


@app.function(image=llama_image, cpu=(2.0, 2.0), memory=MEMORY_MB, timeout=3600)
def llama_vdi2(key: str, images: dict) -> dict:
    return _tag(_run_llama(key, images, 2), key, "vdi2")


@app.function(image=falcon_image, cpu=(4.0, 4.0), memory=MEMORY_MB, timeout=3600)
def falcon_pc4(images: dict) -> dict:
    return _tag(_run_falcon(images, 4), "falcon", "pc4")


@app.function(image=falcon_image, cpu=(2.0, 2.0), memory=MEMORY_MB, timeout=3600)
def falcon_vdi2(images: dict) -> dict:
    return _tag(_run_falcon(images, 2), "falcon", "vdi2")


@app.function(image=rapid_image, cpu=(4.0, 4.0), memory=MEMORY_MB, timeout=3600)
def rapid_pc4(images: dict) -> dict:
    return _tag(_run_rapid(images, 4), "rapid_v6_small", "pc4")


@app.function(image=rapid_image, cpu=(2.0, 2.0), memory=MEMORY_MB, timeout=3600)
def rapid_vdi2(images: dict) -> dict:
    return _tag(_run_rapid(images, 2), "rapid_v6_small", "vdi2")


@app.local_entrypoint()
def main(only: str = "") -> None:
    images = {f"screen {i}": (REPO / f"mnt/data/screen {i}.png").read_bytes() for i in range(1, 10)}
    OUT.mkdir(exist_ok=True)
    calls = []
    if only in ("", "rapid"):
        calls += [rapid_pc4.spawn(images), rapid_vdi2.spawn(images)]
    if only in ("", "falcon"):
        calls += [falcon_pc4.spawn(images), falcon_vdi2.spawn(images)]
    if only in ("", "llama"):
        for key in LLAMA_MODELS:
            calls += [llama_pc4.spawn(key, images), llama_vdi2.spawn(key, images)]
    for call in calls:
        try:
            res = call.get()
        except Exception as exc:  # noqa: BLE001
            print("CALL FAILED:", repr(exc)[:500], flush=True)
            continue
        name = f"{res.get('engine')}_{res.get('profile')}"
        (OUT / f"modal_{name}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        secs = [s.get("seconds", 0) for s in res.get("screens", {}).values()]
        errs = [k for k, s in res.get("screens", {}).items() if "error" in s]
        print(f"RESULT {name}: cpu={res.get('cpu_model')} quota={res.get('cpu_quota')} threads={res.get('threads')} "
              f"load={res.get('load_seconds')}s screens={len(secs)} mean={round(sum(secs)/max(1,len(secs)),1)}s "
              f"max={max(secs) if secs else None}s errors={errs or res.get('error')}", flush=True)
