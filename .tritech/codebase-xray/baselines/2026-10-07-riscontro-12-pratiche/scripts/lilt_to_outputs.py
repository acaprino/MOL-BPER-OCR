"""Turn LiLT word-role predictions into the pipeline's output format, so the usual reports can score them.

Usage: python -I lilt_to_outputs.py <ft_eval.py> <examples.json> <train_result.json> <out_dir> [v1]

The field reconstruction is not reimplemented: the functions are loaded unchanged from the
2026-09-29 script (ft_eval.py), leaving out only its module-level evaluation of the LUNARDI screens.
Default is the "fixed" reconstruction (the four generic rules); pass v1 for the first version.
"""
import ast
import json
import os
import sys
from typing import Any, Callable, Dict

ft_eval_path, examples_path, result_path, out_dir = sys.argv[1:5]
fixed = not (len(sys.argv) > 5 and sys.argv[5] == "v1")


def load_reconstruction(path: str) -> Callable[..., Dict[str, str]]:
    """Function definitions, stdlib imports and the SINGLE constant of ft_eval.py, nothing else."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    keep = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name != "test_outputs":
            keep.append(node)
        elif isinstance(node, ast.Import):
            keep.append(node)
        elif isinstance(node, ast.ImportFrom) and not (node.module or "").startswith("extraction"):
            keep.append(node)
        elif isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "SINGLE" for t in node.targets):
            keep.append(node)
    namespace: Dict[str, Any] = {}
    exec(compile(ast.Module(body=keep, type_ignores=[]), path, "exec"), namespace)
    return namespace["to_fields"]


to_fields = load_reconstruction(ft_eval_path)
examples = {e["id"]: e for e in json.load(open(examples_path, encoding="utf-8"))}
predictions = json.load(open(result_path, encoding="utf-8"))["predictions"]

outputs: Dict[str, Dict[str, Any]] = {}
roles_used: Dict[str, int] = {}
for screen, result in predictions.items():
    example = examples[screen]
    for role in result["pred"]:
        roles_used[role] = roles_used.get(role, 0) + 1
    fields = to_fields(example["words"], result["pred"], fixed)
    outputs[screen] = {
        "fields": {key: {"value": value, "confidence": 1.0} for key, value in fields.items()},
        "soggetti": [], "fidi": [], "garanzie": [],
        "_status": "OK", "_content_crop": "ocr-lilt", "_field_sources": {key: "LILT" for key in fields},
        "_meta_agg": {"calls": 0, "estimated_cost_usd": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 0},
    }
os.makedirs(out_dir, exist_ok=True)
json.dump(outputs, open(os.path.join(out_dir, "poc_outputs_improved.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(f"{len(outputs)} screens, reconstruction={'fixed' if fixed else 'v1'}")
print("word roles predicted:", dict(sorted(roles_used.items(), key=lambda kv: -kv[1])))
