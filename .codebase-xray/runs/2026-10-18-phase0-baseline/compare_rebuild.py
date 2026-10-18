"""Compare a rebuilt v3.1 bundle with the committed data/training/ground-truth-v3.1.

Usage: python -I compare_rebuild.py <rebuilt_dir> <bundle_dir>
Prints file-level identity, manifest differences and word-level differences.
"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

rebuilt, bundle = Path(sys.argv[1]), Path(sys.argv[2])
for name in ("examples.json", "roles.json", "coverage.json", "ground_truth.csv", "alignment_report.csv"):
    a = hashlib.sha256((rebuilt / name).read_bytes()).hexdigest()
    b = hashlib.sha256((bundle / name).read_bytes()).hexdigest()
    print(f"{name}: {'SAME' if a == b else 'DIFF'} rebuilt={a[:16]} bundle={b[:16]}")

ma = json.loads((rebuilt / "manifest.json").read_text(encoding="utf-8"))
mb = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
print("manifest keys that differ:", sorted(k for k in set(ma) | set(mb) if ma.get(k) != mb.get(k)))
print("dataset_content_sha256:", ma["dataset_content_sha256"][:16], "vs", mb["dataset_content_sha256"][:16])

ea = {e["id"]: e for e in json.loads((rebuilt / "examples.json").read_text(encoding="utf-8"))}
eb = {e["id"]: e for e in json.loads((bundle / "examples.json").read_text(encoding="utf-8"))}
print("same ids:", set(ea) == set(eb))
keys = Counter(k for i in eb for k in eb[i] if ea[i].get(k) != eb[i][k])
print("example keys that differ:", dict(keys))
print("labels identical:", all(ea[i]["labels"] == eb[i]["labels"] for i in eb))
print("word count, text, y0, y1 identical:", all(
    [(w["text"], w["y0"], w["y1"]) for w in ea[i]["words"]] == [(w["text"], w["y0"], w["y1"]) for w in eb[i]["words"]]
    for i in eb))
tiny = large = 0
for i in eb:
    for j, (x, y) in enumerate(zip(ea[i]["words"], eb[i]["words"])):
        for k in ("x0", "x1"):
            d = abs(x[k] - y[k])
            if 0 < d <= 1e-6:
                tiny += 1
            elif d > 1e-6:
                large += 1
                print(f"  {i} word {j} {y['text']!r} {k}: rebuilt {x[k]} bundle {y[k]} fitted={y.get('fitted')} label={eb[i]['labels'][j]}")
print(f"x coordinates differing by <=1e-6: {tiny}; by more: {large}")
