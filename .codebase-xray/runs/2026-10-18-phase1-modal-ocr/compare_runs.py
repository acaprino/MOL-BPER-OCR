"""Compare stage A runs on train and validation only (docs/next-ver-plan.md Phase 1).

Usage: python -I compare_runs.py <out.json> LABEL=RUN_DIR [LABEL=RUN_DIR ...]
Each RUN_DIR holds manifest.json, ocr_selection.json and dataset/alignment_report.csv
(a local run or a Modal run merged by merge_runs()). The first run is the baseline.
Historical test rows are filtered out before any comparison.
"""
import csv
import json
import math
import sys
from pathlib import Path

out = Path(sys.argv[1])
folders = {label: Path(path) for label, path in (arg.split("=", 1) for arg in sys.argv[2:])}
configs = list(folders)
SELECTION = {"train", "val"}
G1_VAL = math.ceil(0.984 * 133)


def load_rows(config: str) -> dict[tuple[str, str], dict[str, str]]:
    with open(folders[config] / "dataset" / "alignment_report.csv", encoding="utf-8-sig", newline="") as fh:
        return {(r["screen"], r["field"]): r for r in csv.DictReader(fh, delimiter=";") if r["split"] in SELECTION}


def frac(d: dict[str, int]) -> str:
    return f"{d['available']}/{d['total']}"


result: dict[str, dict] = {}
base = load_rows(configs[0])
for config in configs:
    folder = folders[config]
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    selection = json.loads((folder / "ocr_selection.json").read_text(encoding="utf-8"))
    rows = load_rows(config)
    if set(rows) != set(base):
        raise SystemExit(f"{config}: train/val rows differ from {configs[0]}")
    gained = sorted((k, base[k]["ocr_text"], rows[k]["ocr_text"]) for k in rows
                    if rows[k]["expected"].strip() and rows[k]["exact_text"] == "True" and base[k]["exact_text"] != "True")
    lost = sorted((k, base[k]["ocr_text"], rows[k]["ocr_text"]) for k in rows
                  if rows[k]["expected"].strip() and rows[k]["exact_text"] != "True" and base[k]["exact_text"] == "True")
    val = selection["by_split"]["val"]
    ndg, rap = val["subject_ndg"], val["rapporto"]
    result[config] = {
        "params": manifest["identity"]["params"],
        "models": {k: f"{v['file']} {v['sha256'][:12]}" for k, v in manifest["provenance"]["models"].items()},
        "train": {k: (frac(v) if isinstance(v, dict) else v) for k, v in selection["by_split"]["train"].items()},
        "val": {k: (frac(v) if isinstance(v, dict) else v) for k, v in val.items()},
        "train_val": {k: (frac(v) if isinstance(v, dict) else v) for k, v in selection["by_split"]["train_val"].items()},
        "six_as_eight_per_practice": {p: v["six_as_eight"] for p, v in selection["per_practice"].items() if v["six_as_eight"]},
        "timing": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in manifest["timing"].items() if k != "scope"},
        "peak_memory_mb": round(max(s.get("peak_memory_bytes") or 0 for s in manifest["sessions"]) / 2**20),
        "gate_val": {
            "G1": f"{val['ocr_non_null']['available']}/133 (needs {G1_VAL})",
            "G1_pass": val["ocr_non_null"]["available"] >= G1_VAL,
            "G3_pass": ndg["available"] == ndg["total"] and rap["available"] >= math.ceil(0.975 * rap["total"]),
        },
        f"vs_{configs[0]}_gained": [f"{s} {f}: {a!r} -> {b!r}" for (s, f), a, b in gained],
        f"vs_{configs[0]}_lost": [f"{s} {f}: {a!r} -> {b!r}" for (s, f), a, b in lost],
    }

out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{'cfg':9} {'trainOCR':>9} {'valOCR':>8} {'tvNDG':>6} {'tvRAP':>6} {'6->8':>5} {'mean_s':>7} {'p95_s':>6} {'max_s':>6} {'MB':>5}  G1 G3  +/- vs {configs[0]}")
for config, r in result.items():
    t, tv = r["timing"], r["train_val"]
    print(f"{config:9} {r['train']['ocr_non_null']:>9} {r['val']['ocr_non_null']:>8} {tv['subject_ndg']:>6} {tv['rapporto']:>6} "
          f"{tv['six_as_eight']:>5} {t['mean']:>7} {t['p95']:>6} {t['max']:>6} {r['peak_memory_mb']:>5}  "
          f"{'ok' if r['gate_val']['G1_pass'] else 'no':2} {'ok' if r['gate_val']['G3_pass'] else 'no':2}  "
          f"+{len(r[f'vs_{configs[0]}_gained'])}/-{len(r[f'vs_{configs[0]}_lost'])}")
