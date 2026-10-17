"""Throwaway: score the anchor-rules spike with the project's own evaluator (same metric as the Gemini baseline)."""

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(r"D:\Projects\poc-data-extraction")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from anchor_rules import extract  # noqa: E402
from extraction.evaluation import load_ground_truth, eval_outputs  # noqa: E402
from extraction.fields import CSV_TO_SCHEMA  # noqa: E402
from extraction.normalization import classify_field  # noqa: E402

gt = load_ground_truth(str(REPO / "mnt/data/dati.csv"))
FAMILY = {"1": "list", "2": "list", "3": "list", "4": "soggetti", "5": "fidi", "6": "fidi", "7": "fidi", "8": "fidi", "9": "note"}

for scale in ("1x", "2x"):
    dump = json.load(open(HERE / f"ocr_probe_out/rapid_v6_small_{scale}.json", encoding="utf-8"))
    outputs, families = {}, {}
    for sid, lines in dump.items():
        family, fields = extract(lines)
        families[sid] = family
        outputs[sid] = {"fields": {k: {"value": v, "confidence": 1.0} for k, v in fields.items()}, "soggetti": []}
    buf = io.StringIO()
    with redirect_stdout(buf):
        res = eval_outputs(outputs, gt)
    fam_ok = sum(families[s] == FAMILY[s.split()[-1]] for s in families)
    print(f"=== reference screens @{scale}: RAW {res['acc_raw']:.2%}  page family {fam_ok}/9")
    for sid, kv in gt.items():
        for csv_key, gt_val in kv.items():
            key = CSV_TO_SCHEMA.get(csv_key.strip())
            pred = outputs.get(sid, {}).get("fields", {}).get(key, {}).get("value")
            status, _ = classify_field(gt_val, pred, field_key=key)
            if status not in ("OK", "OK_NULL"):
                print(f"   {sid:9s} {key:34s} {status:12s} gt={gt_val[:45]!r} pred={str(pred)[:45]!r}")

# ------------------------------------------------------------ live captures (no field GT: family + coverage)
live_path = HERE / "ocr_probe_out/live_boxes.json"
if live_path.exists():
    live = json.load(open(live_path, encoding="utf-8"))
    manifests = {}
    for sub in ("no-tooltip-rita", "tooltips-rita"):
        for fr in json.load(open(REPO / f"tests/fixtures/frames/{sub}/manifest.json", encoding="utf-8"))["frames"]:
            manifests[fr["frame"]] = fr
    fam_ok = total = 0
    print("\n=== live captures (~1890 px)")
    for rel, item in live.items():
        fr = manifests.get(rel, {})
        expected = FAMILY.get(str(fr.get("cluster")), "other")
        family, fields = extract(item["lines"])
        total += 1
        fam_ok += family == expected
        flag = "" if family == expected else f"  <-- expected {expected}"
        shown = {k: (v if len(v) < 40 else v[:37] + "...") for k, v in fields.items()}
        print(f"{rel:38s} {item['seconds']:4.1f}s {family:8s}{flag}  {len(fields):2d} fields {shown}")
    print(f"page family on live captures: {fam_ok}/{total}")
