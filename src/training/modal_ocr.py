"""Read the stage A screen set on Modal CPU containers, in parallel shards.

Invoke from ``src/`` with ``modal run --detach -m training.modal_ocr --out-dir ABS``.
Each shard is an ordinary ``run_ocr()`` run over part of the reviewed screens, with the
same configuration, CPU profile and pinned engine (``requirements-ocr.txt`` and the model
files of the local ``.venv-ocr``, checked against the RapidOCR catalog digests). The local
entrypoint stores every shard unchanged and joins them with ``merge_runs()``, so
``ocr_runner report`` reads the result like a local run. An optional cost panel reads the
same few screens with every configuration in one container, so their timings share one host.

The screenshots of the archive are sent to Modal; the values stay local.
If the local process stops, the detached app keeps reading: run again with ``--collect``
to download what has finished.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import modal

from training.ocr_runner import CONFIGS, PROFILES, Screen, load_screens, merge_runs, run_ocr


ROOT = Path(__file__).resolve().parents[2]
LOCAL_MODELS = ROOT / ".venv-ocr" / "Lib" / "site-packages" / "rapidocr" / "models"
PANEL_ORDER = ("A0", "A4", "A1", "A3", "A2")
RESOURCES = {"cpu": 4.0, "memory_mib": 4096, "timeout_seconds": 7200, "retries": 1, "max_containers": 50}

app = modal.App("bper-ocr-stage-a")
image = (
    modal.Image.debian_slim(python_version="3.13")
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install_from_requirements(str(ROOT / "requirements-ocr.txt"))
    .add_local_dir(str(LOCAL_MODELS), "/opt/rapidocr-models", copy=True)
    .run_commands(
        "python -c \"import pathlib, shutil, rapidocr; "
        "target = pathlib.Path(rapidocr.__file__).parent / 'models'; "
        "[shutil.copy2(f, target / f.name) for f in pathlib.Path('/opt/rapidocr-models').glob('*.onnx')]\""
    )
    .add_local_python_source("training")
)


# ============================================================
# Remote
# ============================================================


def _host() -> dict[str, Any]:
    """What the container actually ran on: CPU model, visible cores and the cgroup quota."""
    cpu_model = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                      if line.startswith("model name")), None)
    quota = Path("/sys/fs/cgroup/cpu.max")
    return {"cpu_model": cpu_model, "logical_cpus": os.cpu_count(),
            "affinity_cpus": len(os.sched_getaffinity(0)),
            "cgroup_cpu_max": quota.read_text().strip() if quota.exists() else None}


def _materialize(screens: list[tuple[str, str, str, bytes]], work: Path) -> list[Screen]:
    listed = []
    for screen_id, digest, name, data in screens:
        path = work / "images" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        listed.append(Screen(screen_id, path, digest))
    return listed


def _run_files(run_dir: Path) -> dict[str, bytes]:
    return {name: (run_dir / name).read_bytes() for name in ("manifest.json", "cache.json") if (run_dir / name).exists()}


@app.function(image=image, cpu=(RESOURCES["cpu"], RESOURCES["cpu"]), memory=RESOURCES["memory_mib"],
              timeout=RESOURCES["timeout_seconds"], retries=RESOURCES["retries"],
              max_containers=RESOURCES["max_containers"])
def read_shard(config: str, profile: str, screens: list[tuple[str, str, str, bytes]]) -> dict[str, Any]:
    """One ordinary run over part of the screens; its manifest and cache come back as written."""
    work = Path(tempfile.mkdtemp())
    run_ocr(config, profile, _materialize(screens, work), work / "run")
    return {"files": _run_files(work / "run"), "host": _host()}


@app.function(image=image, cpu=(RESOURCES["cpu"], RESOURCES["cpu"]), memory=RESOURCES["memory_mib"],
              timeout=RESOURCES["timeout_seconds"], retries=RESOURCES["retries"])
def cost_panel(configs: list[str], profile: str, screens: list[tuple[str, str, str, bytes]]) -> dict[str, Any]:
    """The same screens read by every configuration in turn, on one host."""
    work = Path(tempfile.mkdtemp())
    listed = _materialize(screens, work)
    runs = {}
    for config in configs:
        run_ocr(config, profile, listed, work / config)
        runs[config] = _run_files(work / config)
    return {"runs": runs, "host": _host()}


# ============================================================
# Local
# ============================================================


def _payload(screens: list[Screen]) -> list[tuple[str, str, str, bytes]]:
    return [(s.id, s.sha256, f"{s.id}{s.path.suffix}", s.path.read_bytes()) for s in screens]


def _store(directory: Path, files: dict[str, bytes], host: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        (directory / name).write_bytes(data)
    (directory / "host.json").write_text(json.dumps(host, indent=2), encoding="utf-8")


def _jobs(screens: list[Screen], configs: list[str], shard_size: int, whole: set[str]) -> list[dict[str, Any]]:
    jobs = []
    for config in configs:
        size = len(screens) if config in whole else shard_size
        for number, start in enumerate(range(0, len(screens), size)):
            jobs.append({"config": config, "shard": number, "ids": [s.id for s in screens[start:start + size]]})
    return jobs


@app.local_entrypoint()
def main(out_dir: str, configs: str = "A0,A1,A2,A3,A4", profile: str = "pc4", shard_size: int = 8,
         whole: str = "A0,A4", panel: str = "51185037__elenco-01,51185037__gestione-fidi-01,51185037__note-01",
         collect: bool = False, include_test: bool = False) -> None:
    """Spawn every shard and the cost panel, then download each result and merge each configuration.

    The screens are those of the archive's training and control practices; ``--include-test`` adds the test ones.
    """
    output = Path(out_dir)
    if not output.is_absolute():
        raise ValueError("out-dir must be an absolute path")
    screens = load_screens(ROOT / "data" / "dataset", include_test)
    by_id = {s.id: s for s in screens}
    calls_path = output / "calls.json"
    if not collect:
        chosen = configs.split(",")
        unknown = [c for c in chosen if c not in CONFIGS] + ([] if profile in PROFILES else [profile])
        if unknown:
            raise ValueError(f"Unknown configuration or profile: {unknown}")
        output.mkdir(parents=True, exist_ok=False)
        jobs = _jobs(screens, chosen, shard_size, set(whole.split(",")))
        for job in jobs:
            job["call"] = read_shard.spawn(job["config"], profile, _payload([by_id[i] for i in job["ids"]])).object_id
        calls = {"profile": profile, "resources": RESOURCES, "jobs": jobs, "panel": None}
        if panel:
            panel_ids = panel.split(",")
            calls["panel"] = {"configs": list(PANEL_ORDER), "ids": panel_ids,
                              "call": cost_panel.spawn(list(PANEL_ORDER), profile,
                                                       _payload([by_id[i] for i in panel_ids])).object_id}
        calls_path.write_text(json.dumps(calls, indent=2), encoding="utf-8")
        print(f"spawned {len(jobs)} shards and the cost panel; calls in {calls_path}", flush=True)
    calls = json.loads(calls_path.read_text(encoding="utf-8"))

    failures = {}
    for job in calls["jobs"]:
        directory = output / job["config"] / "shards" / str(job["shard"])
        if directory.exists():
            continue
        try:
            result = modal.FunctionCall.from_id(job["call"]).get()
        except Exception as error:  # one failed shard must not lose the others
            failures[f"{job['config']}/{job['shard']}"] = f"{type(error).__name__}: {error}"
            print(f"FAILED {job['config']} shard {job['shard']}: {error}", flush=True)
            continue
        _store(directory, result["files"], result["host"])
        timing = json.loads(result["files"]["manifest.json"]).get("timing") or {}
        print(f"{job['config']} shard {job['shard']} {len(job['ids'])} screens, "
              f"mean {timing.get('mean', float('nan')):.1f}s on {result['host']['cpu_model']}", flush=True)
    panel_dir = output / "cost-panel"
    if calls["panel"] and not panel_dir.exists():
        try:
            result = modal.FunctionCall.from_id(calls["panel"]["call"]).get()
            for config, files in result["runs"].items():
                _store(panel_dir / config, files, result["host"])
        except Exception as error:
            failures["cost-panel"] = f"{type(error).__name__}: {error}"
    for config in sorted({job["config"] for job in calls["jobs"]}):
        shard_dirs = [output / config / "shards" / str(job["shard"]) for job in calls["jobs"] if job["config"] == config]
        if (output / config / "run").exists() or not all(d.exists() for d in shard_dirs):
            continue
        try:
            manifest = merge_runs(shard_dirs, screens, output / config / "run")
            print(f"{config} merged: mean {manifest['timing']['mean']:.2f}s, max {manifest['timing']['max']:.2f}s", flush=True)
        except ValueError as error:
            failures[f"{config}/merge"] = str(error)
    (output / "failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
    print(json.dumps({"failures": failures}, indent=2), flush=True)
