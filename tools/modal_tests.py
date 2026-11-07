"""Run tests on a Modal container: this PC is often short of memory, so they do not run here.

    env -u HTTPS_PROXY -u HTTP_PROXY .venv/Scripts/python.exe -m modal run tools/modal_tests.py --args "tests/test_training_dataset.py -q"

The container has what the fast lane needs, with Qt offscreen but no torch: the DINOv2 cases skip, so run the
fast lane (``-m "not slow"``). tests/fixtures stays out of the upload.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
REPO = "/repo"

app = modal.App("bper-tests")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libgl1", "libegl1", "libglib2.0-0", "libdbus-1-3", "libxkbcommon0", "libfontconfig1", "python3-tk")
    .pip_install("pytest>=8.0", "Pillow>=10.0.0", "numpy", "openpyxl>=3.1.2", "pandas", "python-dotenv",
                 "langchain-core", "langchain-openai", "langchain-google-genai", "PyQt6>=6.4.0", "qt-material>=2.14",
                 "mss>=9.0.0", "imagehash>=4.3.0", "requests>=2.31.0", "openai>=1.51.0")
    .env({"QT_QPA_PLATFORM": "offscreen"})
    .add_local_file(str(ROOT / "pyproject.toml"), f"{REPO}/pyproject.toml")
    .add_local_file(str(ROOT / ".env.example"), f"{REPO}/.env.example")
    .add_local_file(str(ROOT / "gui_app.py"), f"{REPO}/gui_app.py")
    .add_local_file(str(ROOT / "main.py"), f"{REPO}/main.py")
    .add_local_file(str(ROOT / "build_exe.bat"), f"{REPO}/build_exe.bat")
    .add_local_dir(str(ROOT / "prompts"), f"{REPO}/prompts")
    .add_local_dir(str(ROOT / "src"), f"{REPO}/src",
                   ignore=["edge-agent/assets/**/*.pt", "edge-agent/assets/**/*.png", "**/__pycache__/**"])
    .add_local_dir(str(ROOT / "tests"), f"{REPO}/tests", ignore=["fixtures/**", "**/__pycache__/**"])
)


@app.function(image=image, cpu=2.0, memory=4096, timeout=900, retries=0)
def run_pytest(arguments: list[str]) -> tuple[int, str]:
    done = subprocess.run([sys.executable, "-m", "pytest", *arguments], cwd=REPO, capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


@app.local_entrypoint()
def main(args: str = "tests -q") -> None:
    code, output = run_pytest.remote(shlex.split(args))
    sys.stdout.buffer.write(output.encode("utf-8", "replace"))
    sys.stdout.flush()
    if code:
        raise SystemExit(code)
