"""Publish a fully validated X-ray run without altering its parent."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parent.parent
ROOT = RUN_DIR.parents[2]
MIRROR = ROOT / ".codebase-xray"
REPORTS = (
    "01-structure.md", "02-interfaces.md", "03-flows.md", "04-semantics.md",
    "05-risks.md", "06-documentation.md", "07-final-report.md", "08-interconnect-map.md",
)


def main() -> None:
    state = json.loads((RUN_DIR / "state.json").read_text(encoding="utf-8"))
    if any(a["status"] != "delivered" for a in state["agents_spawned"]):
        raise RuntimeError("A dispatched worker has not delivered")
    if any(value != "complete" for value in state["phases"].values()):
        raise RuntimeError("Not all phases completed")
    verification = json.loads((RUN_DIR / "validation/artifact-validation.json").read_text(encoding="utf-8"))
    if verification["changed_source_files"]:
        raise RuntimeError("The analyzed source changed")
    for report in verification["reports"]:
        if report.get("missing") or report.get("citation_issues") or report.get("unresolved_paired_symbols") or report.get("missing_required_headers") or not report.get("balanced_fences") or report.get("mermaid_subgraph_issues") or report.get("stale_markers"):
            raise RuntimeError("Artifact validation has unresolved issues")
    parent = MIRROR / "runs" / state["parent_run"]
    expected = json.loads((RUN_DIR / "validation/parent-integrity.json").read_text(encoding="utf-8"))
    actual = {str(p.relative_to(parent)): hashlib.sha256(p.read_bytes()).hexdigest() for p in parent.rglob("*") if p.is_file()}
    if actual != expected:
        raise RuntimeError("Historical run was altered")
    if int((RUN_DIR / "validation/pytest-exit-code.txt").read_text().strip()) != 0:
        raise RuntimeError("Tests did not pass")
    links = json.loads((RUN_DIR / "validation/report-links.json").read_text(encoding="utf-8"))
    if links["issues"]:
        raise RuntimeError("Broken report links")
    state["status"] = "complete"
    state["completed_at"] = datetime.now(timezone.utc).isoformat()
    state["files_created"] = sorted(str(p.relative_to(RUN_DIR)).replace("\\", "/") for p in RUN_DIR.rglob("*") if p.is_file() and "pytest-cache" not in p.parts)
    state["files_created"] = sorted(set(state["files_created"]) | {"validation/publication.json"})
    (RUN_DIR / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name in (*REPORTS, "state.json"):
        (MIRROR / name).write_bytes((RUN_DIR / name).read_bytes())
    registry_path = MIRROR / "runs.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["active"] = [r for r in registry["active"] if r["run_id"] != RUN_DIR.name]
    registry["latest_completed"] = RUN_DIR.name
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    hashes = {name: hashlib.sha256((RUN_DIR / name).read_bytes()).hexdigest() for name in (*REPORTS, "state.json")}
    assert all(hashlib.sha256((MIRROR / name).read_bytes()).hexdigest() == digest for name, digest in hashes.items())
    publication = {"run_id": RUN_DIR.name, "parent_run": state["parent_run"], "published_at": state["completed_at"], "mirror_sha256": hashes, "parent_files_preserved": len(expected)}
    (RUN_DIR / "validation/publication.json").write_text(json.dumps(publication, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(publication, indent=2))


if __name__ == "__main__":
    main()
