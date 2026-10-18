"""Run one bounded LiLT experiment on the existing Modal training volume.

Invoke with ``modal run -m training.modal_train --data-dir ABS --out-dir ABS``.
Only reviewed OCR words, boxes, labels, and provenance are sent to the trainer.
The original screenshots and workbooks remain local.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path, PurePosixPath
from typing import Any

import modal

from training.model import BASE_MODEL, train_model, validate_reviewed_dataset


app = modal.App("bper-lilt-reviewed-v3-1")
volume = modal.Volume.from_name("bper-lilt-spike", create_if_missing=False)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch==2.12.0", "transformers==5.15.0", "tokenizers==0.22.2", "huggingface_hub")
    .run_commands(
        "python -c \"from huggingface_hub import snapshot_download; from pathlib import Path; "
        f"p = snapshot_download('{BASE_MODEL}', "
        "allow_patterns=['config.json', '*.safetensors', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json']); "
        "Path('/base-path.txt').write_text(p)\""
    )
    .add_local_python_source("training")
)


def _experiment_id(examples: list[dict[str, Any]], roles: list[str], settings: dict[str, Any]) -> str:
    payload = json.dumps({"examples": examples, "roles": roles, "settings": settings,
                          "base_model": BASE_MODEL}, sort_keys=True, ensure_ascii=False)
    return "model_v3_1_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@app.function(
    image=image, gpu="L4", cpu=(2.0, 4.0), memory=12288, timeout=1800,
    max_containers=1, scaledown_window=2, retries=0, volumes={"/vol": volume},
)
@modal.concurrent(max_inputs=1)
def run_training(
    examples: list[dict[str, Any]], roles: list[str], dataset_manifest: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Write a fresh immutable version, then evaluate the held-out test once."""
    started = time.perf_counter()
    validate_reviewed_dataset(examples, roles, dataset_manifest)
    name = _experiment_id(examples, roles, settings)
    destination = Path("/vol") / name
    if destination.exists():
        raise FileExistsError(f"Immutable experiment already exists: {name}")
    base_path = Path("/base-path.txt").read_text().strip()
    result = train_model(
        examples, roles, destination, dataset_manifest, base_path=base_path,
        base_revision=Path(base_path).name, device="cuda", **settings,
    )
    volume.commit()
    result["remote_wall_seconds"] = round(time.perf_counter() - started, 3)
    result["remote_model_dir"] = name
    result["resources"] = {"gpu": "L4", "cpu_request": 2, "cpu_limit": 4,
                           "memory_mib": 12288, "timeout_seconds": 1800,
                           "max_containers": 1, "retries": 0}
    return result


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


@app.local_entrypoint()
def main(data_dir: str, out_dir: str, epochs: int = 8, variants: int = 2, seed: int = 7,
         patience: int = 2) -> None:
    """Train once and download the ordinary CPU-loadable model and its report."""
    dataset = Path(data_dir)
    output = Path(out_dir)
    if not dataset.is_absolute() or not output.is_absolute():
        raise ValueError("data-dir and out-dir must be absolute paths")
    examples = json.loads((dataset / "examples.json").read_text(encoding="utf-8"))
    roles = json.loads((dataset / "roles.json").read_text(encoding="utf-8"))
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    validate_reviewed_dataset(examples, roles, manifest)
    if output.exists():
        raise FileExistsError("Output directory must be new; previous experiments are immutable")
    settings = {"epochs": epochs, "variants": variants, "seed": seed,
                "batch_size": 2, "accumulation_steps": 4, "patience": patience}
    if not 1 <= epochs <= 16 or not 0 <= variants <= 2 or not 1 <= patience <= 4:
        raise ValueError("The bounded experiment allows at most 16 epochs, 2 train variants and patience 4")
    output.mkdir(parents=True, exist_ok=False)
    result = run_training.remote(examples, roles, manifest, settings)
    _write_json(output / "result.json", result)
    _write_json(output / "test_predictions.json", result["test_predictions"])
    _write_json(output / "validation_predictions.json", result["validation_predictions"])
    _write_json(output / "metrics.json", result["metrics"])
    model_dir = output / "cpu_model"
    model_dir.mkdir()
    for filename in result["model_files"]:
        if PurePosixPath(filename).name != filename or "\\" in filename:
            raise ValueError("Trainer returned an unsafe model filename")
        remote_path = str(PurePosixPath(result["remote_model_dir"]) / filename)
        with (model_dir / filename).open("xb") as stream:
            for block in volume.read_file(remote_path):
                stream.write(block)
    _write_json(output / "download_manifest.json", {
        "volume": "bper-lilt-spike", "remote_model_dir": result["remote_model_dir"],
        "files": {path.name: {"bytes": path.stat().st_size,
                             "sha256": _file_sha256(path)} for path in model_dir.iterdir()},
    })
    print(json.dumps({"best_epoch": result["best_epoch"], "train_seconds": result["train_seconds"],
                      "val_f1": result["metrics"]["validation"]["f1"],
                      "test_f1": result["metrics"]["test"]["f1"],
                      "remote_model_dir": result["remote_model_dir"],
                      "local_model_dir": str(model_dir)}, ensure_ascii=False), flush=True)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
