"""Check report citations and preserve evidence of the analyzed source tree."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

RUN_DIR = Path(__file__).resolve().parent.parent
ROOT = RUN_DIR.parents[2]
PHASE_NAMES = (
    "01-structure.md", "02-interfaces.md", "03-flows.md", "04-semantics.md",
    "05-risks.md", "06-documentation.md", "07-final-report.md", "08-interconnect-map.md",
)
CITATION = re.compile(
    r"(?<![\w/])((?:[A-Za-z]:[/\\])?[\w./\\-]+\.(?:py|md|json|ini|txt|bat|spec)):(\d+)"
)
PAIRED_SYMBOL = re.compile(
    r"`([\w./-]+\.py):\d+`(?:,\s*|\s+[—–-]\s*)`([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\(?"
)
ROOT_HEADERS = {
    "01-structure.md": ["Partition Map", "File Inventory", "Dependency Graph (cross-partition view)", "Global Entry Points", "Cross-Partition Reference Summary", "Where to Add New Code"],
    "02-interfaces.md": ["Public APIs (by partition)", "Cross-Partition Exports", "Contracts (by partition)", "External Dependencies"],
    "03-flows.md": ["Critical Paths (by partition)", "Cross-Partition Flows", "Data Flow (consolidated)", "Error Handling Paths", "Side Effects", "Process Diagrams"],
    "04-semantics.md": ["Module Purposes (by partition)", "Design Decisions (by partition)", "Architecture Decision Records (per partition)", "Cross-Partition ADR", "Embedded Assumptions (consolidated)", "Hidden Contracts (cross-partition)", "Conventions Observed"],
    "05-risks.md": ["Anti-Patterns Found (by severity)", "Red Flags (by severity)", "Technical Debt Inventory (by partition)", "Failure Mode Analysis", "Cross-Partition Risk Attribution"],
    "06-documentation.md": ["Documentation vs Code Accuracy (by partition)", "Coverage Gaps (priority-sorted)", "Broken References (by partition)"],
    "07-final-report.md": ["Target", "Executive Summary", "Project at a Glance", "Partition Map", "Cross-Partition Topology", "Architecture Overview", "Technology Decisions", "Critical Paths (cross-partition)", "Key Process Diagrams", "Design Insights", "Per-Partition Health Scorecard", "Risk Assessment (global)", "Documentation vs Reality", "Top Priority Actions", "Detailed Findings", "Quick Reference: Which File to Consult", "Analysis Metadata"],
    "08-interconnect-map.md": ["Target scope", "Call Graph (expanded, 2-3 hops)", "Contracts", "Invariants", "Domain Rules", "Assumptions", "Integration Hot-Spots", "Change Impact Radius", "Reviewer Hints"],
}


def normalized_hash(path: Path) -> str:
    text = path.read_bytes().decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def inspect_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"file": str(path.relative_to(RUN_DIR)), "missing": True}
    text = path.read_text(encoding="utf-8-sig")
    citations: set[tuple[str, int]] = set()
    issues: list[dict[str, Any]] = []
    symbol_issues: list[dict[str, Any]] = []
    manifest = json.loads((RUN_DIR / "snapshot/manifest.json").read_text(encoding="utf-8"))
    for number, line in enumerate(text.splitlines(), 1):
        for match in CITATION.finditer(line):
            reference, source_line = match.group(1), int(match.group(2))
            cited = Path(reference)
            if not cited.is_absolute():
                cited = ROOT / cited
            citations.add((reference, source_line))
            if not cited.is_file():
                issues.append({"report_line": number, "citation": match.group(), "issue": "missing source"})
            else:
                lines = len(cited.read_text(encoding="utf-8-sig", errors="replace").splitlines())
                if not 1 <= source_line <= lines:
                    issues.append({"report_line": number, "citation": match.group(), "issue": "line out of range", "source_lines": lines})
        for match in PAIRED_SYMBOL.finditer(line):
            source, symbol = match.groups()
            record = manifest["files"].get(source)
            is_method = "." in symbol
            plain_symbol = symbol.lstrip("_")
            is_function = bool(plain_symbol) and plain_symbol[0].islower()
            is_function = is_function and not (symbol.startswith("__") and symbol.endswith("__"))
            is_function = is_function and symbol not in {"import", "imports", "sys", "os"}
            if record and (is_method or is_function) and symbol not in record["symbols"]:
                symbol_issues.append({"report_line": number, "source": source, "symbol": symbol})
    fences = sum(line.startswith("```") for line in text.splitlines())
    diagram_issues: list[dict[str, Any]] = []
    for block_number, diagram in enumerate(re.findall(r"```mermaid\s*\n(.*?)```", text, flags=re.DOTALL), 1):
        depth = 0
        for line in diagram.splitlines():
            if line.strip().startswith("subgraph "):
                depth += 1
            elif line.strip() == "end":
                depth -= 1
            if depth < 0:
                diagram_issues.append({"block": block_number, "issue": "unexpected subgraph end"})
                break
        if depth != 0:
            diagram_issues.append({"block": block_number, "issue": "unbalanced subgraph", "depth": depth})
    headers = set(re.findall(r"^## (.+)$", text, flags=re.MULTILINE))
    required = ROOT_HEADERS.get(path.name, []) if path.parent == RUN_DIR else []
    return {
        "file": str(path.relative_to(RUN_DIR)), "missing": False,
        "lines": len(text.splitlines()), "bytes": path.stat().st_size,
        "unique_citations": len(citations), "citation_issues": issues,
        "unresolved_paired_symbols": symbol_issues,
        "missing_required_headers": [heading for heading in required if heading not in headers],
        "balanced_fences": fences % 2 == 0,
        "mermaid_subgraph_issues": diagram_issues,
        "stale_markers": text.count("<!-- xray:stale"),
    }


def main() -> None:
    manifest = json.loads((RUN_DIR / "snapshot/manifest.json").read_text(encoding="utf-8"))
    changed: list[str] = []
    checked = 0
    for name, record in manifest["files"].items():
        is_context = name.startswith(("prompts/", "processes/", "docs/"))
        is_config = Path(name).suffix in {".ini", ".txt"} or name.endswith("/prompts.json")
        if record["language"] != "python" and not is_context and not is_config:
            continue
        path = ROOT / name
        checked += 1
        if not path.is_file() or normalized_hash(path) != record["hash"]:
            changed.append(name)
    launchers = json.loads((RUN_DIR / "validation/launcher-baseline.json").read_text(encoding="utf-8"))
    for name, record in launchers.items():
        path = ROOT / name
        checked += 1
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            changed.append(name)
    reports = [inspect_report(RUN_DIR / name) for name in PHASE_NAMES]
    reports.extend(inspect_report(RUN_DIR / "partitions/root" / name) for name in PHASE_NAMES[:6])
    result = {"checked_source_files": checked, "changed_source_files": changed, "reports": reports}
    output = RUN_DIR / "validation/artifact-validation.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
