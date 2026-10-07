"""Compare exact matching with the evaluator's verdict on identifier-like long fields.

Usage: python exact_identifiers.py <repo_root> <input_dir>
classify_field() accepts any text longer than 20 characters at a 0.85 similarity ratio, so a
22-character account number with one wrong digit is scored OK. This counts how often that happens.
"""
import json
import os
import sys

repo = os.path.abspath(sys.argv[1])
sys.path.insert(0, repo)
os.chdir(repo)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(repo, ".env"))
from extraction.evaluation import load_ground_truth  # noqa: E402
from extraction.normalization import classify_field  # noqa: E402

input_dir = os.path.abspath(sys.argv[2])
gt = load_ground_truth(os.path.join(input_dir, "dati.csv"))
outputs = json.load(open(os.path.join(input_dir, "poc_outputs_improved.json"), encoding="utf-8"))
total = exact = evaluator_ok = 0
for screen, kv in gt.items():
    truth = kv.get("Rapporto")
    if not truth or not str(truth).strip() or screen not in outputs:
        continue
    pred = (outputs[screen]["fields"].get("rapporto") or {}).get("value")
    total += 1
    same = "".join(str(truth).split()) == "".join(str(pred or "").split())
    exact += same
    status, _ = classify_field(truth, pred, field_key="rapporto")
    evaluator_ok += status == "OK"
    if not same:
        print(f"  {screen:36s} truth={truth!r} read={pred!r} evaluator={status}")
print(f"rapporto: exact {exact}/{total}, evaluator OK {evaluator_ok}/{total}")
