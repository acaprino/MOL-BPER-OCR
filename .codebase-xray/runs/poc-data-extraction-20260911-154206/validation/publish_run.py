"""Publish a fully delivered and validated X-ray run."""

from __future__ import annotations

import contextlib
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import runpy
import shutil
from typing import Any


RUN = Path(__file__).resolve().parent.parent
MIRROR = RUN.parents[1]


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".publishing.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    state = json.loads((RUN / "state.json").read_text(encoding="utf-8-sig"))
    if not all(value == "complete" for value in state["phases"].values()):
        raise RuntimeError("Every phase must be complete before publication")
    if not all(agent["status"] == "delivered" for agent in state["agents_spawned"]):
        raise RuntimeError("Every worker must have delivered before publication")
    if state["validation"]["exit_code"] != 0:
        raise RuntimeError("The required test suite did not pass")

    validator = runpy.run_path(str(RUN / "validation/check_artifacts.py"))
    with contextlib.redirect_stdout(io.StringIO()):
        validator["main"]()
    validation = json.loads((RUN / "validation/artifact-validation.json").read_text(encoding="utf-8"))
    if validation["changed_source_files"]:
        raise RuntimeError(f"Analyzed source changed: {validation['changed_source_files']}")
    for report in validation["reports"]:
        if report.get("missing") or report.get("citation_issues") or report.get("unresolved_paired_symbols"):
            raise RuntimeError(f"Unresolved report evidence: {report['file']}")
        if report.get("missing_required_headers") or not report.get("balanced_fences") or report.get("stale_markers") or report.get("mermaid_subgraph_issues"):
            raise RuntimeError(f"Invalid report structure: {report['file']}")

    names = list(validator["PHASE_NAMES"])
    state["status"] = "complete"
    state["completed_at"] = datetime.now().astimezone().isoformat()
    state["validation"]["artifact_check"] = {
        "reports_checked": len(validation["reports"]),
        "source_files_unchanged": validation["checked_source_files"],
        "log": "validation/artifact-validation.json",
    }
    for name in names + ["validation/publish_run.py", "validation/publication.json"]:
        if name not in state["files_created"]:
            state["files_created"].append(name)
    write_json(RUN / "state.json", state)

    hashes: dict[str, str] = {}
    for name in names + ["state.json"]:
        shutil.copy2(RUN / name, MIRROR / name)
        source_hash = digest(RUN / name)
        if digest(MIRROR / name) != source_hash:
            raise RuntimeError(f"Mirror verification failed: {name}")
        hashes[name] = source_hash

    registry_path = MIRROR / "runs.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    registry["active"] = [entry for entry in registry["active"] if entry["run_id"] != state["run_id"]]
    registry["latest_completed"] = state["run_id"]
    write_json(registry_path, registry)
    publication = {
        "run_id": state["run_id"],
        "published_at": state["completed_at"],
        "mirror": str(MIRROR),
        "matching_sha256": hashes,
        "registry_latest_completed": registry["latest_completed"],
    }
    write_json(RUN / "validation/publication.json", publication)
    print(json.dumps(publication, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
