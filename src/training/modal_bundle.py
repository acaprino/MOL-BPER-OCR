"""Build a reviewed dataset bundle and score a frozen LiLT run on it, on Modal containers.

Invoke from ``src/`` with ``modal run -m training.modal_bundle``, the same inputs as ``training.dataset`` and:
    --lots "WORKBOOK,ASSIGNMENT,CORRECTIONS,OCR;..."   every lot, in its dataset order
    --model model_v3_1_33da126207bf6876                a run on the ``bper-lilt-spike`` volume

The workbooks, the screenshots in ``data/pratiche`` and the OCR caches go to Modal. Back come the bundle and the
score of the extended validation; nothing here decodes an image or loads a model on this PC. Only screens with an
example reach the model, and the builder refuses an OCR reading of a sealed one.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import modal

ROOT = Path(__file__).resolve().parents[2]
PRACTICES = "/data/pratiche"
MODELS = "/vol"
EXTENDED_SPLIT = "val_ext"

app = modal.App("bper-bundle")
volume = modal.Volume.from_name("bper-lilt-spike", create_if_missing=False)
build_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("Pillow>=10.0.0", "numpy", "openpyxl>=3.1.2", "pandas", "python-dotenv",
                 "langchain-core", "langchain-openai", "langchain-google-genai")
    .env({"PROMPTS_DIR": "/opt/prompts"})
    .add_local_dir(str(ROOT / "prompts"), "/opt/prompts")
    .add_local_dir(str(ROOT / "data/pratiche"), PRACTICES, ignore=["**/offtopic/**"])
    .add_local_python_source("training", "extraction", "prompt_store")
)
score_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch==2.12.0", "transformers==5.15.0", "tokenizers==0.22.2", "huggingface_hub")
    .add_local_python_source("training")
)


def _save(work: Path, group: str, source: dict[str, Any]) -> Path:
    """A file sent by the local entrypoint, under its own name: the manifest records that name."""
    path = work / group / source["name"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source["data"])
    return path


def _sent(path: str) -> dict[str, Any] | None:
    return None if path == "-" else {"name": Path(path).name, "data": Path(path).read_bytes()}


@app.function(image=build_image, cpu=4.0, memory=8192, timeout=1800, retries=0)
def build(workbook: dict[str, Any], ocr: dict[str, Any], lots: list[list[dict[str, Any] | None]]) -> dict[str, bytes]:
    from training.dataset import Lot, build_dataset
    from training.truth_export import export_workbook

    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        lot_inputs = [Lot(*[_save(work, f"lot{number}", source) if source else None for source in sources])
                      for number, sources in enumerate(lots)]
        output = work / "bundle"
        build_dataset(_save(work, "riscontro", workbook), Path(PRACTICES), _save(work, "riscontro", ocr), output, lot_inputs)
        export_workbook(output, output / "ground_truth.xlsx")
        return {path.name: path.read_bytes() for path in output.iterdir()}


@app.function(image=score_image, cpu=4.0, memory=8192, timeout=1800, retries=0, volumes={MODELS: volume})
def score(examples_json: bytes, model_name: str) -> dict[str, Any]:
    import torch
    from transformers import AutoTokenizer, LiltForTokenClassification

    from training.evaluation import evaluate_predictions
    from training.model import predict

    torch.set_num_threads(4)
    model_dir = Path(MODELS) / model_name
    roles = json.loads((model_dir / "labelmap.json").read_text(encoding="utf-8"))["roles"]
    tokenizer = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
    model = LiltForTokenClassification.from_pretrained(model_dir).eval()
    examples = [example for example in json.loads(examples_json) if example["split"] == EXTENDED_SPLIT]
    predictions = {}
    for example in examples:
        predicted, probabilities = predict(model, tokenizer, example, roles)
        predictions[example["id"]] = {"pred": predicted, "prob": probabilities}
    report = evaluate_predictions(examples, predictions)
    report["model"] = model_name
    return report


@app.local_entrypoint()
def main(workbook: str, ocr: str, lots: str, out: str, model: str = "") -> None:
    output = Path(out)
    if not output.is_absolute():
        raise ValueError("out must be an absolute path")
    output.mkdir(parents=True, exist_ok=False)
    sources = [[_sent(path) for path in lot.split(",")] for lot in lots.split(";")]
    files = build.remote(_sent(workbook), _sent(ocr), sources)
    for name, data in files.items():
        (output / name).write_bytes(data)
    manifest = json.loads(files["manifest.json"])
    print(json.dumps({key: manifest[key] for key in ("dataset_version", "reviewed_rows", "screens", "practices",
                                                     "truth_counts", "supervision_counts", "practice_splits")},
                     ensure_ascii=False), flush=True)
    print(json.dumps({"overlaps_examples": manifest["leakage_audit"]["recorded_overlaps"],
                      "overlaps_truth": manifest["truth_isolation"]["recorded_overlaps"]}, ensure_ascii=False), flush=True)
    if model:
        report = score.remote(files["examples.json"], model)
        (output / "score-val-ext.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        split = report["by_split"][EXTENDED_SPLIT]
        print(json.dumps({"strict": f"{split['correct']}/{split['total']}", "counts": split["counts"],
                          "content_availability": split["content_availability"], "complete": report["complete"]},
                         ensure_ascii=False), flush=True)
