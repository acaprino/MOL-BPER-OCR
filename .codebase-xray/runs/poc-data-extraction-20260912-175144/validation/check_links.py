"""Validate report links both in the immutable run and after mirroring."""
from __future__ import annotations
import json
import re
from pathlib import Path
from urllib.parse import unquote

RUN_DIR = Path(__file__).resolve().parent.parent
ROOT = RUN_DIR.parents[2]


def anchors(path: Path) -> set[str]:
    found: set[str] = set()
    counts: dict[str, int] = {}
    text = path.read_text(encoding="utf-8-sig")
    for title in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.M):
        slug = re.sub(r"[^\w\-\s]", "", title.lower())
        slug = re.sub(r"\s", "-", slug)
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        found.add(slug + (f"-{count}" if count else ""))
    return found


def main() -> None:
    issues: list[str] = []
    checked = 0
    reports = sorted(RUN_DIR.glob("0[1-8]-*.md")) + sorted((RUN_DIR / "partitions/root").glob("0[1-6]-*.md"))
    for report in reports:
        text = report.read_text(encoding="utf-8-sig")
        for raw in re.findall(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)", text):
            raw = raw.strip("<>")
            if re.match(r"^(?:https?|mailto|app|codex):", raw): continue
            target, _, fragment = raw.partition("#")
            target = unquote(target)
            line_match = re.search(r":(\d+)$", target)
            source_line = int(line_match.group(1)) if line_match else None
            if line_match:
                target = target[:line_match.start()]
            fragment = unquote(fragment)
            locations = [report.parent]
            if report.parent == RUN_DIR: locations.append(ROOT / ".codebase-xray")
            for location in locations:
                candidate = Path(target) if target else location / report.name
                if not candidate.is_absolute(): candidate = location / candidate
                candidate = candidate.resolve()
                # The mirror is not published yet; look up its planned report bytes.
                inspected = RUN_DIR / candidate.name if candidate.parent == ROOT / ".codebase-xray" and (RUN_DIR / candidate.name).is_file() else candidate
                checked += 1
                if not inspected.is_file():
                    issues.append(f"{report.name}: missing {raw} when resolved from {location}")
                elif source_line is not None and not 1 <= source_line <= len(inspected.read_text(encoding="utf-8-sig", errors="replace").splitlines()):
                    issues.append(f"{report.name}: line out of range {raw}")
                elif fragment and inspected.suffix == ".md" and fragment not in anchors(inspected):
                    issues.append(f"{report.name}: missing anchor {raw}")
    result = {"reports": len(reports), "links_checked_including_mirror": checked, "issues": issues}
    (RUN_DIR / "validation/report-links.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(issues))


if __name__ == "__main__":
    main()
