# Project Knowledge Navigation

> Discovery only. Documentation is a lead to inspect, never proof of implementation. Status: documented or unverified.

## Project instructions read

| File | Navigation rule it states | Status |
|---|---|---|
| AGENTS.md:18 | Read docs/how-it-works.md for mechanics, keep Architectural Constraints as mandatory guidance; start narrative discovery at docs/INDEX.md and decisions at docs/adr/README.md. | documented |
| CLAUDE.md:18 | Same navigation rules as AGENTS.md; text comparison found only the title and assistant-name substitution differ. | documented |

Ancestor instruction files AGENTS.md, CLAUDE.md, GEMINI.md and .cursorrules were searched in D:/Projects and D:/; none found. No nested AGENTS.md or CLAUDE.md was found outside excluded generated/dependency directories.

## Canonical indexes found

| Index | Path | What it indexes | Status |
|---|---|---|---|
| Narrative guide | docs/INDEX.md | Twelve numbered guides, reading paths, ADRs and pipeline mechanics. | documented |
| Decision index | docs/adr/README.md | ADR 0001 through 0012, declared statuses and deferred decisions. | documented |
| Project overview | README.md | Purpose, installation, entry points, build, configuration, output and evaluation. | documented |
| Process catalog | processes/README.md | Process metadata, navigation hierarchy, capture revisits and the stated gap with runtime prompts.json. | documented |
| Pipeline mechanics | docs/how-it-works.md | Anchor/main/retry stages, run modes, live capture and page routing. | documented |

## Conventions observed

The declared front door for the narrative documentation is docs/INDEX.md. Numbered guides describe architecture, flows, data, setup and unresolved questions. Architectural decisions are separately numbered in docs/adr/ and declare that accepted decisions are immutable except for supersession status. docs/superpowers/specs/ and docs/superpowers/plans/ preserve design and implementation intent for asynchronous capture and spreadsheet export. Their embedded example code is documentation, not implementation evidence.

OPEN_POINTS.md, .deep-dive/ and .team-review/ contain earlier claims; they are secondary discovery material, not a parent X-ray run or verified evidence. The project instructions name .codebase-map/INDEX.md, but that directory is absent in this checkout.

The automatic detection chain found no workspace manifest, convention-based multi-workspace layout, backend/frontend split, or second supported language with at least 20 files. Its proposed result is one root partition. Mechanical classification counted 70 Python files and 8,150 non-comment code lines (12,294 physical lines): 26 edge-agent, 15 extraction, 3 root entry/shared files, 15 tests and 11 tools. This count does not include JSON catalogs, batch launchers or the PyInstaller specification; those remain context for the analysis. No semantic source claims are established here.

## Not found

- SEARCH_INDEX.md or BY_DOMAIN.md anywhere in the eligible tree.
- docs/README.md (docs/INDEX.md is present instead).
- .codebase-map/INDEX.md and its advertised internal context documents.
- Separate decisions/, architecture/ or domains/ document directories; docs/adr/ and docs/04-architecture.md cover those topics.
- Existing .codebase-xray/runs.json or a legacy root state at preflight. This is a new full run with no parent.

Generated and dependency directories excluded from discovery: .git, .venv, node_modules, dist, build, .next, target, vendor and __pycache__. Credentials and local logs are not knowledge sources.
