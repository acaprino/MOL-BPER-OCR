"""Count digit substitutions between ground truth and extraction on the small-font numeric fields.

Usage: python digit_confusions.py <repo_root> <input_dir>
Fields: ndg_1..4 (subjects table) and rapporto, scadenza, importo_euro (loans table).
Only pairs of equal length are compared character by character.
"""
import json
import os
import sys
from collections import Counter

repo = os.path.abspath(sys.argv[1])
sys.path.insert(0, repo)
os.chdir(repo)
from dotenv import load_dotenv  # noqa: E402

load_dotenv()
from extraction.evaluation import load_ground_truth  # noqa: E402
from extraction.fields import CSV_TO_SCHEMA  # noqa: E402

FIELDS = {"ndg_1", "ndg_2", "ndg_3", "ndg_4", "rapporto", "scadenza", "importo_euro"}
input_dir = os.path.abspath(sys.argv[2])
gt = load_ground_truth(os.path.join(input_dir, "dati.csv"))
outputs = json.load(open(os.path.join(input_dir, "poc_outputs_improved.json"), encoding="utf-8"))

subs: Counter = Counter()
digits_seen: Counter = Counter()
values = {"co_ndg": [0, 0], "scadenza_with_6": [0, 0], "any_with_6": [0, 0]}
for screen, kv in gt.items():
    pred = outputs.get(screen)
    if not pred:
        continue
    for csv_key, gt_val in kv.items():
        field = CSV_TO_SCHEMA.get(str(csv_key).strip())
        if field not in FIELDS or not str(gt_val).strip():
            continue
        g = "".join(str(gt_val).split())
        p = "".join(str((pred.get("fields", {}).get(field) or {}).get("value") or "").split())
        same = g == p
        if field in ("ndg_2", "ndg_3", "ndg_4"):
            values["co_ndg"][0] += same
            values["co_ndg"][1] += 1
        if "6" in g:
            values["any_with_6"][0] += same
            values["any_with_6"][1] += 1
            if field == "scadenza":
                values["scadenza_with_6"][0] += same
                values["scadenza_with_6"][1] += 1
        if len(g) != len(p):
            continue
        for a, b in zip(g, p):
            if a.isdigit():
                digits_seen[a] += 1
                if a != b:
                    subs[(field if not field.startswith("ndg_") else "ndg_n", a, b)] += 1

print("digits compared:", sum(digits_seen.values()), "| sixes:", digits_seen["6"], "| eights:", digits_seen["8"])
print("substitutions (field, truth, read): count")
for (field, a, b), n in subs.most_common():
    print(f"  {field:13s} {a} -> {b}: {n}")
six_wrong = sum(n for (f, a, b), n in subs.items() if a == "6")
print(f"sixes misread: {six_wrong} of {digits_seen['6']}  | other digits misread: {sum(subs.values()) - six_wrong} of {sum(digits_seen.values()) - digits_seen['6']}")
for name, (ok, total) in values.items():
    print(f"{name}: {ok}/{total} values read correctly")
