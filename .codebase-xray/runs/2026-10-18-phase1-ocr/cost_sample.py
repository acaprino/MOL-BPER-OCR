"""Measure the per-screen cost of one stage A configuration on the first N reviewed screens.

Usage: python -I cost_sample.py <repo_root> <config> <N> <out_dir>
The output is a cost sample, not a selection run: its screen set differs from the full
corpus, so report() and build_dataset() refuse it.
"""
import sys
from pathlib import Path

root, config, count, out = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
sys.path.insert(0, str(root / "src"))
from training.ocr_runner import load_screens, run_ocr  # noqa: E402

screens = load_screens(root / "data/training/ground-truth-v3.1/examples.json", root / "data")[:count]
manifest = run_ocr(config, "pc4", screens, out)
print(config, manifest["status"], [s.id for s in screens], manifest.get("timing"), flush=True)
