"""Simulate a one-row constraint for FIDI fields in decode_fields() on saved predictions.

Usage: python -I simulate_fidi_row.py <repo_root> LABEL=RUN_DIR=EXAMPLES_JSON [...]
Prints strict accuracy and FIDI non-null correct (n_fido, rapporto, descrizione, scadenza,
importo_euro, tipo_op) per split, before -> after keeping only the topmost predicted n_fido row.
"""
import json, sys
from pathlib import Path
root = Path(sys.argv[1]); sys.path.insert(0, str(root / "src"))
import training.evaluation as ev

FIDI_ROLES = ("n_fido", "rapporto", "descrizione", "scadenza", "importo_euro", "tipo_op")
original = ev.decode_fields

def center(w):
    b = ev._box(w); return (b[1] + b[3]) / 2

def constrained(example, roles, probabilities=None):
    fields = original(example, roles, probabilities)
    words = example["words"]
    anchors = [w for w, r in zip(words, roles) if r == "n_fido"]
    if not anchors:
        return fields
    anchor = min(anchors, key=center)
    a = ev._box(anchor); height = max(1.0, a[3] - a[1])
    below = sorted(center(w) for w in words if abs(ev._box(w)[0] - a[0]) <= height and center(w) > center(anchor) + height)
    bottom = (center(anchor) + below[0]) / 2 if below else float("inf")
    for role in FIDI_ROLES:
        kept = [w for w, r in zip(words, roles) if r == role and center(w) < bottom]
        if kept: fields[role] = ev._join(kept)
        else: fields.pop(role, None)
    return fields

FIDI = {"n_fido", "importo_euro", "scadenza", "tipo_op", "rapporto", "descrizione"}
for spec in sys.argv[2:]:
    label, run_dir, ex_path = spec.split("=", 2)
    examples = json.loads(Path(ex_path).read_text(encoding="utf-8"))
    out = []
    for name, split in (("validation", "val"), ("test", "test")):
        preds = json.loads((Path(run_dir) / f"{name}_predictions.json").read_text(encoding="utf-8"))
        sel = [e for e in examples if e["split"] == split]
        res = []
        for fn in (original, constrained):
            ev.decode_fields = fn
            rep = ev.evaluate_predictions(sel, preds)
            recs = rep["records"]
            ok = sum(r["status"] in ("correct", "correct_null") for r in recs)
            fid = [r for r in recs if r["field"] in FIDI and r["expected"] is not None]
            res.append(f"{ok}/{len(recs)} fidi {sum(r['status']=='correct' for r in fid)}/{len(fid)}")
        ev.decode_fields = original
        out.append(f"{split}: {res[0]} -> {res[1]}")
    print(label, " | ".join(out))
