"""Check both evaluation entry points on the real B0 predictions.

Usage (repository root): python -I check_field_evaluation.py <repo_root> [--perturb]
--perturb rewrites one decoded field value before the field-path run (negative control).
1. The refactored role path reproduces the field metrics written before the change,
   apart from the keys it adds (abstained, complete).
2. evaluate_field_values() on the fields decoded from the same roles gives the same
   records and per-field summaries as the role path.
Exits 1 if either check fails.
"""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "src"))
from training.evaluation import decode_fields, evaluate_field_values, evaluate_predictions  # noqa: E402

NEW_KEYS = {"abstained", "complete"}


def strip(value):
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in NEW_KEYS}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


examples = json.loads((root / "data/training/ground-truth-v3.1/examples.json").read_text(encoding="utf-8"))
run = root / "data/training/runs/lilt-v3.1-20261018-current-bundle"
ok = True
for name, split in (("validation", "val"), ("test", "test")):
    selected = [e for e in examples if e["split"] == split]
    preds = json.loads((run / f"{name}_predictions.json").read_text(encoding="utf-8"))
    saved = json.loads((run / f"{name}_field_metrics.json").read_text(encoding="utf-8"))
    roles = evaluate_predictions(selected, preds)
    same_role_report = strip(roles) == saved
    fields = {e["id"]: {"fields": decode_fields(e, preds[e["id"]]["pred"], preds[e["id"]]["prob"])} for e in selected}
    if "--perturb" in sys.argv:
        first = selected[0]
        target = next(f for f, v in first["values"].items() if v is not None)
        fields[first["id"]]["fields"][target] = "PERTURBED"
    values = evaluate_field_values(selected, fields)
    key = lambda r: (r["id"], r["field"], r["expected"], r["predicted"], r["status"], r["content_available"])  # noqa: E731
    same_records = [key(r) for r in values["records"]] == [key(r) for r in roles["records"]]
    same_by_field = values["by_field"] == roles["by_field"]
    print(f"{name}: role report equals pre-change report without new keys: {same_role_report}; "
          f"complete={roles['complete']}; field path records equal: {same_records}; by_field equal: {same_by_field}; "
          f"strict {values['overall']['correct']}/{values['overall']['total']}; field word_metrics={values['word_metrics']}")
    ok &= same_role_report and same_records and same_by_field and roles["complete"] and values["complete"]
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
