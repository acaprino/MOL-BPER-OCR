"""Resumable OCR caches for the stage A comparison of ``docs/next-ver-plan.md``.

One run reads every reviewed screen with one engine configuration and one CPU
profile. Each screen is written as soon as it is read, so an interrupted run
resumes where it stopped and a partial run is never taken for a complete one:
``cache.json``, in the format ``build_dataset()`` reads, exists only once every
screen has a result, and the manifest binds its digest.

Read the screens with an interpreter that has rapidocr and onnxruntime, from ``src/``::

    python -m training.ocr_runner run --config A1 --profile pc4 \\
        --examples ../data/training/ground-truth-v3.1/examples.json --screenshots ../data --out DIR

``report`` then builds the derived dataset from a complete cache and writes the
OCR-only selection metrics. They cover train and validation; the historical test
is left out, as the plan requires for every choice made before the freeze.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

Reader = Callable[[Path], list[list[Any]]]
EngineFactory = Callable[[dict[str, str], dict[str, int]], tuple[Reader, dict[str, Any]]]

# Stage A configurations of the plan (section 3.1). A5 is a check on top of the chosen one.
CONFIGS: dict[str, dict[str, str]] = {
    "A0": {"Det.ocr_version": "PP-OCRv6", "Det.model_type": "small",
           "Rec.ocr_version": "PP-OCRv6", "Rec.model_type": "small"},
    "A1": {"Det.ocr_version": "PP-OCRv6", "Det.model_type": "small",
           "Rec.ocr_version": "PP-OCRv6", "Rec.model_type": "medium"},
    "A2": {"Det.ocr_version": "PP-OCRv6", "Det.model_type": "medium",
           "Rec.ocr_version": "PP-OCRv6", "Rec.model_type": "medium"},
    "A3": {"Det.ocr_version": "PP-OCRv6", "Det.model_type": "tiny",
           "Rec.ocr_version": "PP-OCRv6", "Rec.model_type": "medium"},
    "A4": {"Det.ocr_version": "PP-OCRv6", "Det.model_type": "small",
           "Rec.ocr_version": "PP-OCRv5", "Rec.lang_type": "latin", "Rec.model_type": "mobile"},
}
PROFILES: dict[str, dict[str, int]] = {
    "pc4": {"intra_op": 4, "inter_op": 1},
    "vdi2": {"intra_op": 2, "inter_op": 1},
}
SELECTION_SPLITS = ("train", "val")
SUBJECT_NDG_FIELDS = {f"ndg_{index}" for index in range(1, 5)}


class Screen(NamedTuple):
    id: str
    path: Path
    sha256: str


# ============================================================
# Files
# ============================================================


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any, indent: int | None = None) -> None:
    """Replace the file in one step, so an interruption never leaves half of it."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=indent), encoding="utf-8")
    os.replace(temporary, path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_screens(examples_path: Path, screenshots_dir: Path) -> list[Screen]:
    """Reviewed screens in bundle order, each bound to the image digest the review used."""
    from training.dataset import resolve_screenshot_path

    examples = _read_json(examples_path)
    return [Screen(e["id"], resolve_screenshot_path(screenshots_dir, e["id"]), e["image_sha256"]) for e in examples]


# ============================================================
# Measurements
# ============================================================


def _peak_memory_bytes() -> int | None:
    """Peak resident memory of this process, where the platform reports it."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        current = ctypes.windll.kernel32.GetCurrentProcess
        current.restype = wintypes.HANDLE
        query = ctypes.windll.psapi.GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        return int(counters.PeakWorkingSetSize) if query(current(), ctypes.byref(counters), counters.cb) else None
    try:
        import resource
    except ImportError:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def _timing(seconds: list[float], sessions: int) -> dict[str, Any]:
    p95 = statistics.quantiles(seconds, n=20, method="inclusive")[-1] if len(seconds) > 1 else seconds[0]
    return {
        "screens": len(seconds), "mean": statistics.mean(seconds), "median": statistics.median(seconds),
        "p95": p95, "max": max(seconds), "sessions": sessions,
        "scope": "seconds per screen include PNG decoding; the warm-up read and engine loading are excluded",
    }


# ============================================================
# Run
# ============================================================


def run_ocr(config: str, profile: str, screens: list[Screen], out_dir: Path,
            engine_factory: EngineFactory | None = None) -> dict[str, Any]:
    """Read every screen still pending, then publish the cache only if all of them have a result."""
    if config not in CONFIGS:
        raise ValueError(f"Unknown OCR configuration {config}; expected one of {sorted(CONFIGS)}")
    if profile not in PROFILES:
        raise ValueError(f"Unknown CPU profile {profile}; expected one of {sorted(PROFILES)}")
    for screen in screens:
        if _sha256(screen.path) != screen.sha256:
            raise ValueError(f"Screenshot {screen.id} differs from the reviewed image: {screen.path}")
    identity = {"config": config, "params": CONFIGS[config], "profile": profile,
                "threads": PROFILES[profile], "screens": {s.id: s.sha256 for s in screens}}
    manifest_path = out_dir / "manifest.json"
    previous = _read_json(manifest_path) if manifest_path.exists() else None
    if previous is not None and previous["identity"] != identity:
        raise ValueError(f"{out_dir} holds another configuration, profile or screen set; use a new directory")

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    loading = time.perf_counter()
    read, provenance = (engine_factory or _rapidocr_engine)(CONFIGS[config], PROFILES[profile])
    session: dict[str, Any] = {"started_utc": started,
                               "engine_load_seconds": round(time.perf_counter() - loading, 3)}
    provenance = json.loads(json.dumps(provenance, default=str))
    if previous is not None and previous["provenance"] != provenance:
        raise ValueError(f"{out_dir} was produced by another engine build: models or versions differ")

    screen_dir = out_dir / "screens"
    screen_dir.mkdir(parents=True, exist_ok=True)
    sessions = [*(previous or {}).get("sessions", []), session]
    manifest: dict[str, Any] = {"schema_version": 1, "identity": identity, "provenance": provenance,
                                "sessions": sessions, "status": "partial"}
    _write_json(manifest_path, manifest, indent=2)

    pending = [s for s in screens if not (screen_dir / f"{s.id}.json").exists()]
    if pending:
        warming = time.perf_counter()
        try:
            read(screens[0].path)
        except Exception as error:  # the same screen is read again below and recorded there
            session["warmup_error"] = f"{type(error).__name__}: {error}"
        session["warmup_seconds"] = round(time.perf_counter() - warming, 3)
    failed: dict[str, str] = {}
    for number, screen in enumerate(pending, 1):
        error_path = screen_dir / f"{screen.id}.error.json"
        reading = time.perf_counter()
        try:
            items = read(screen.path)
        except Exception as error:  # one screen's failure must not stop the others
            failed[screen.id] = f"{type(error).__name__}: {error}"
            _write_json(error_path, {"error": failed[screen.id], "session": len(sessions) - 1,
                                     "seconds": round(time.perf_counter() - reading, 3)})
            continue
        seconds = round(time.perf_counter() - reading, 3)
        _write_json(screen_dir / f"{screen.id}.json", {"seconds": seconds, "items": items, "session": len(sessions) - 1})
        error_path.unlink(missing_ok=True)
        if number % 10 == 0 or number == len(pending):
            print(f"{number}/{len(pending)} {screen.id} {seconds:.2f}s", file=sys.stderr, flush=True)

    stored = {s.id: _read_json(screen_dir / f"{s.id}.json") for s in screens if (screen_dir / f"{s.id}.json").exists()}
    session.update({"screens_read": len(pending) - len(failed), "screens_failed": len(failed),
                    "peak_memory_bytes": _peak_memory_bytes()})
    manifest["failed"] = failed
    manifest["pending"] = [s.id for s in screens if s.id not in stored]
    if not manifest["pending"]:
        cache = {s.id: {"seconds": stored[s.id]["seconds"], "items": stored[s.id]["items"]} for s in screens}
        _write_json(out_dir / "cache.json", cache)
        manifest["status"] = "complete"
        manifest["cache_sha256"] = _sha256(out_dir / "cache.json")
        manifest["timing"] = _timing([entry["seconds"] for entry in cache.values()],
                                     sessions=len({entry["session"] for entry in stored.values()}))
    _write_json(manifest_path, manifest, indent=2)
    return manifest


def _complete_run(run_dir: Path, action: str) -> tuple[dict[str, Any], Path]:
    """The manifest of a complete run whose cache still has the digest the run recorded."""
    manifest_path, cache = run_dir / "manifest.json", run_dir / "cache.json"
    manifest = _read_json(manifest_path) if manifest_path.exists() else {}
    if (manifest.get("status") != "complete" or not cache.exists()
            or _sha256(cache) != manifest.get("cache_sha256")):
        raise ValueError(f"{run_dir} is not a complete OCR run; resume it before {action}")
    return manifest, cache


def merge_runs(shard_dirs: list[Path], screens: list[Screen], out_dir: Path) -> dict[str, Any]:
    """Join complete runs that read disjoint parts of the screen set into one complete run.

    The shards must share configuration, profile and engine build; only the host may
    differ, and each host is recorded. The output directory must be new.
    """
    if not shard_dirs:
        raise ValueError("No shard to merge")
    shards = [(shard, *_complete_run(shard, "merging")) for shard in shard_dirs]
    reviewed = {s.id: s.sha256 for s in screens}

    def setup(manifest: dict[str, Any]) -> dict[str, Any]:
        return {key: manifest["identity"][key] for key in ("config", "params", "profile", "threads")}

    def build(manifest: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in manifest["provenance"].items() if key != "platform"}

    first = shards[0][1]
    reads: dict[str, int] = {}
    for shard, manifest, _ in shards:
        if setup(manifest) != setup(first):
            raise ValueError(f"{shard} was read with another configuration or profile")
        if build(manifest) != build(first):
            raise ValueError(f"{shard} was produced by another engine build: models or versions differ")
        for screen_id, digest in manifest["identity"]["screens"].items():
            if reviewed.get(screen_id) != digest:
                raise ValueError(f"{shard} holds a screen outside the set or that differs from the reviewed image: {screen_id}")
            reads[screen_id] = reads.get(screen_id, 0) + 1
    twice = [s.id for s in screens if reads.get(s.id, 0) > 1]
    if twice:
        raise ValueError(f"The shards read more than once: {', '.join(twice)}")
    unread = [s.id for s in screens if s.id not in reads]
    if unread:
        raise ValueError(f"The shards leave unread: {', '.join(unread)}")

    entries = {screen_id: entry for _, _, cache in shards for screen_id, entry in _read_json(cache).items()}
    merged = {s.id: entries[s.id] for s in screens}
    out_dir.mkdir(parents=True, exist_ok=False)
    _write_json(out_dir / "cache.json", merged)
    platforms: list[Any] = []
    for _, manifest, _ in shards:
        platform = manifest["provenance"].get("platform")
        if platform is not None and platform not in platforms:
            platforms.append(platform)
    manifest = {
        "schema_version": 1, "identity": {**setup(first), "screens": reviewed},
        "provenance": {**build(first), "platforms": platforms},
        "sessions": [{**session, "shard": number} for number, (_, shard_manifest, _) in enumerate(shards)
                     for session in shard_manifest["sessions"]],
        "status": "complete", "failed": {}, "pending": [],
        "cache_sha256": _sha256(out_dir / "cache.json"),
        "timing": _timing([entry["seconds"] for entry in merged.values()],
                          sessions=sum(shard_manifest["timing"]["sessions"] for _, shard_manifest, _ in shards)),
        "merged_from": [{"run": Path(os.path.relpath(shard, out_dir)).as_posix(),
                         "cache_sha256": shard_manifest["cache_sha256"]} for shard, shard_manifest, _ in shards],
    }
    _write_json(out_dir / "manifest.json", manifest, indent=2)
    return manifest


def _rapidocr_engine(params: dict[str, str], threads: dict[str, int]) -> tuple[Reader, dict[str, Any]]:
    """RapidOCR with explicit models and thread limits, plus what it actually loaded."""
    import os as os_info
    import platform
    from enum import Enum
    from importlib.metadata import version

    import numpy as np
    from omegaconf import OmegaConf
    from PIL import Image
    from rapidocr import RapidOCR
    from rapidocr.inference_engine.base import FileInfo
    from rapidocr.utils.typings import LangDet, LangRec, ModelType, OCRVersion, TaskType

    typed: dict[str, Any] = {}
    for key, value in params.items():
        section, name = key.split(".")
        if name == "ocr_version":
            typed[key] = OCRVersion(value)
        elif name == "model_type":
            typed[key] = ModelType(value)
        elif name == "lang_type":
            typed[key] = (LangRec if section == "Rec" else LangDet)(value)
        else:
            typed[key] = value
    engine = RapidOCR(params={**typed, "Global.log_level": "warning",
                              "EngineConfig.onnxruntime.intra_op_num_threads": threads["intra_op"],
                              "EngineConfig.onnxruntime.inter_op_num_threads": threads["inter_op"]})

    models: dict[str, dict[str, str]] = {}
    for section, module in (("Det", engine.text_det), ("Cls", engine.text_cls), ("Rec", engine.text_rec)):
        if section == "Cls" and not engine.cfg.Global.use_cls:
            continue
        cfg = engine.cfg[section]
        info = type(module.session).get_model_url(FileInfo(
            engine_type=cfg.engine_type, ocr_version=cfg.ocr_version, task_type=TaskType(section.lower()),
            lang_type=cfg.lang_type, model_type=cfg.model_type))
        path = Path(cfg.model_path) if cfg.model_path else Path(cfg.model_root_dir) / Path(info["model_dir"]).name
        digest = _sha256(path)
        if info.get("SHA256") and digest != info["SHA256"]:
            raise ValueError(f"{path.name} does not match the RapidOCR catalog digest")
        models[section] = {"file": path.name, "sha256": digest, "source": info["model_dir"]}

    def plain(value: Any) -> Any:
        return value.value if isinstance(value, Enum) else str(value)

    effective = json.loads(json.dumps(OmegaConf.to_container(engine.cfg, resolve=True), default=plain))
    packages = ("rapidocr", "onnxruntime", "numpy", "opencv-python", "pillow", "omegaconf")
    provenance = {
        "models": models, "effective_config": effective,
        "versions": {name: version(name) for name in packages} | {"python": sys.version.split()[0]},
        "platform": {"system": platform.platform(), "processor": platform.processor(),
                     "logical_cpus": os_info.cpu_count()},
        "input": "PIL Image.convert('RGB') as a numpy array, scale 1x",
    }

    def read(image_path: Path) -> list[list[Any]]:
        with Image.open(image_path) as image:
            pixels = np.array(image.convert("RGB"))
        result = engine(pixels)
        if result.txts is None:
            return []
        return [[text, float(score), [[float(v) for v in point] for point in box.tolist()]]
                for text, score, box in zip(result.txts, result.scores, result.boxes)]

    return read, provenance


# ============================================================
# Selection metrics
# ============================================================


def _six_read_as_eight(expected: Any, ocr_text: Any) -> bool:
    """True when the OCR digits differ from the reviewed ones only by a 6 read as 8."""
    if not isinstance(expected, str) or not isinstance(ocr_text, str):
        return False
    want, got = re.sub(r"\D", "", expected), re.sub(r"\D", "", ocr_text)
    if not want or len(want) != len(got) or want == got:
        return False
    return all((a, b) == ("6", "8") for a, b in zip(want, got) if a != b)


def ocr_selection_metrics(examples: list[dict[str, Any]]) -> dict[str, Any]:
    """OCR-only metrics for choosing an engine: train and validation, never the historical test."""
    from training.evaluation import evaluate_field_values

    selected = [e for e in examples if e["split"] in SELECTION_SPLITS]
    records = evaluate_field_values(selected, {})["records"]
    six_as_eight = {
        e["id"]: [(field, e["values"].get(field)) for field, alignment in e.get("field_alignment", {}).items()
                  if isinstance(alignment, dict) and _six_read_as_eight(e["values"].get(field), alignment.get("ocr_text"))]
        for e in selected
    }

    def counts(rows: list[dict[str, Any]]) -> dict[str, int]:
        return {"available": sum(r["content_available"] for r in rows), "total": len(rows)}

    def summary(chosen: list[dict[str, Any]]) -> dict[str, Any]:
        ids = {e["id"] for e in chosen}
        present = [r for r in records if r["id"] in ids and r["expected"] is not None]
        return {"ocr_non_null": counts(present),
                "subject_ndg": counts([r for r in present if r["field"] in SUBJECT_NDG_FIELDS]),
                "rapporto": counts([r for r in present if r["field"] == "rapporto"]),
                "six_as_eight": sum(len(six_as_eight[i]) for i in ids)}

    by_split = {split: summary([e for e in selected if e["split"] == split]) for split in SELECTION_SPLITS}
    by_split["train_val"] = summary(selected)
    per_practice: dict[str, dict[str, Any]] = {}
    for practice in sorted({e["practice"] for e in selected}):
        chosen = [e for e in selected if e["practice"] == practice]
        per_practice[practice] = {
            "split": chosen[0]["split"], **summary(chosen),
            "six_as_eight_values": len({(e["practice"], *pair) for e in chosen for pair in six_as_eight[e["id"]]}),
        }
    return {"population": "train and validation; the historical test is not reported",
            "by_split": by_split, "per_practice": per_practice}


def report(run_dir: Path, workbook: Path, screenshots: Path) -> dict[str, Any]:
    """Build the derived dataset of a complete run, then write its OCR selection metrics."""
    manifest, cache = _complete_run(run_dir, "reporting")
    from training.dataset import build_dataset

    build_dataset(workbook, screenshots, cache, run_dir / "dataset")
    metrics = {
        "config": manifest["identity"]["config"], "profile": manifest["identity"]["profile"],
        "cache_sha256": manifest["cache_sha256"], "timing": manifest["timing"],
        "peak_memory_bytes": max((s.get("peak_memory_bytes") or 0) for s in manifest["sessions"]) or None,
        **ocr_selection_metrics(_read_json(run_dir / "dataset" / "examples.json")),
    }
    _write_json(run_dir / "ocr_selection.json", metrics, indent=2)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Resumable OCR caches and OCR-only selection metrics.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="read every reviewed screen with one configuration")
    run.add_argument("--config", choices=sorted(CONFIGS), required=True)
    run.add_argument("--profile", choices=sorted(PROFILES), required=True)
    run.add_argument("--examples", type=Path, required=True)
    run.add_argument("--screenshots", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    summary = commands.add_parser("report", help="derived dataset and selection metrics of a complete run")
    summary.add_argument("--run", type=Path, required=True)
    summary.add_argument("--workbook", type=Path, required=True)
    summary.add_argument("--screenshots", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "run":
        manifest = run_ocr(arguments.config, arguments.profile,
                           load_screens(arguments.examples, arguments.screenshots), arguments.out)
        print(json.dumps({key: manifest.get(key) for key in ("status", "failed", "pending", "timing")}, indent=2))
    else:
        metrics = report(arguments.run, arguments.workbook, arguments.screenshots)
        print(json.dumps({key: metrics[key] for key in ("config", "profile", "by_split")}, indent=2))


if __name__ == "__main__":
    main()
