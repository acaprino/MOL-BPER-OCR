# Findings — Codebase Hygiene (`extraction/`)

> Saved by team lead from the hygiene-reviewer's report (subagent file writes are blocked by the harness).

- **Dimension**: codebase-hygiene (dead code, orphan helpers, unused imports/exports, stale docs/docstrings, phantom dependencies, VCS-tracked artifacts)
- **Scope**: full-module review at HEAD of `extraction/` (15 files, 2,442 lines) per `.team-review/00-scope.md`, plus `requirements.txt` phantom deps and doc staleness directly tied to `extraction/`.
- **Method**: every map anchor re-verified independently. Tooling: `ruff 0.15.20` (`--select F401,F811,F841,E722`, 14 hits, all reproduced below); `vulture` not installed — function/constant-level dead code proven by repo-wide grep tracing across all consumers (`main.py`, `gui_app.py`, `edge-agent/`). VCS check via `git ls-files extraction`: **clean** — only the 15 `.py` sources are tracked, `__pycache__/` is gitignored (`.gitignore:21`), no artifacts committed.
- **Convention-kept exclusions** (checked, intentionally NOT reported as dead): `RESPONSE_SCHEMA`/`ANCHOR_SCHEMA` legacy aliases (`extraction/schemas.py:70-71`) — explicit backward-compat per CLAUDE.md; the broad `__init__.py` re-export facade itself — documented public API.

Severity scale: Critical / High / Medium / Low / Info. All findings are report-only; no edits made.

---

## Medium

### HYG-01 — ~117-line dead dedup cluster, quarantined pending decision
**Where**: `extraction/cli.py:36-152` (definitions), `extraction/cli.py:268-273` (only call site, commented out)
**Map anchor**: interconnect `### hygiene` bullet 1; deep-dive D1.
Five functions — `_has_meaningful_value` (`cli.py:36`), `_extract_page_key` (`cli.py:45`), `_output_score` (`cli.py:54`), `_is_confident_output` (`cli.py:77`), `_deduplicate_same_page_outputs` (`cli.py:92`) — are reachable **only** through the call commented out at `cli.py:273`. Repo-wide grep confirms zero other references. The comment reads "TEMP TEST: keep all outputs until page_key mapping is validated" and CLAUDE.md (Architectural Constraints #8) records the same intent, so this is **quarantined-pending-decision, not free-to-delete**: the correct resolution is an explicit decision (re-enable behind a flag once page_key mapping is validated, or delete) — not a drive-by removal.
Side effect worth recording: the `ANCHOR_CONF_MIN` import at `cli.py:14` is live *only* through this dead cluster (`cli.py:87-88`); if the cluster is ever deleted, that import must go with it (ruff cannot see this because the dead function still references it).
**Recommendation**: track as an explicit decision item; do not delete unilaterally.
Confidence: 95

### HYG-02 — Orphan helper `_prepare_content_image`, drifting duplicate of the live path
**Where**: `extraction/pipeline.py:193-200`
**Map anchor**: interconnect `### hygiene` bullet 2; deep-dive D4.
Never called anywhere in the repo (grep: only its definition). It duplicates the open→normalize→screen_id sequence that `extract_from_screen` inlines at `pipeline.py:182-187`, plus the content crop + debug save that `extract_from_image` performs at `pipeline.py:106-107`. Two copies of the same prep logic where one is dead is a drift hazard: a future fix to the live path will silently not touch this helper, and someone later "reusing" it gets stale behavior.
**Recommendation**: delete, or refactor `extract_from_screen` to actually call it (one copy either way).
Confidence: 98

### HYG-03 — Dead `get_screenshot_paths` chain (function + alias + facade exports)
**Where**: `extraction/config.py:99-109` (function, with function-body `import re` at `config.py:100`), `extraction/evaluation.py:19-21` (`infer_screenshots_from_gt` alias) + `extraction/evaluation.py:6` (import feeding only the alias), `extraction/__init__.py:17,41,62,117` (exports)
**Map anchor**: interconnect `### hygiene` bullet 2; deep-dive D5.
The whole chain has no live caller: `get_screenshot_paths` is called only by `infer_screenshots_from_gt`, which itself is called by nothing — `main()` scans `INPUT_DIR` directly (`cli.py:322-327`), and neither `gui_app.py` nor the edge-agent imports either symbol. CLAUDE.md (Constraint #9) already documents "no caller". The function-body `import re` (`config.py:100`) is a style smell inside already-dead code (`re` belongs at top-level per the package's own conventions).
**Recommendation**: remove the chain and its four facade export entries in one commit; CLAUDE.md already declares the CLI scan behavior authoritative.
Confidence: 95

### HYG-04 — Dead label→key resolution chains in `field_definitions.py` and `page_definitions.py` (~78 lines) — *not in the interconnect map*
**Where**: `extraction/field_definitions.py:188-235` (`FIELD_LABEL_ALIASES`, 48 lines), `:238-241` (`normalize_field_label`), `:243-246` (`resolve_schema_key`); `extraction/page_definitions.py:12-21` (`PAGE_NAME_ALIASES`), `:31-34` (`normalize_page_label`), `:36-39` (`resolve_page_key`), `:42-47` (`resolve_page_name`)
Repo-wide grep: `resolve_schema_key` and `resolve_page_name` have **zero callers**; `normalize_field_label` is called only by `resolve_schema_key`; `normalize_page_label` and `resolve_page_key` only by each other / `resolve_page_name`; `FIELD_LABEL_ALIASES` and `PAGE_NAME_ALIASES` are consumed only inside these dead resolvers. None is exported by the `__init__.py` facade, so no compat surface is affected. The *reverse* direction is live and untouched by this finding: `resolve_display_name`/`resolve_field_page_key` (used by `fields.py:118-126`), `get_canonical_page_name`, `CANONICAL_PAGE_NAMES`, `PAGE_SHEET_ORDER` (used by `canonical_mapping.py:6,12,14`), and `CANONICAL_FIELD_DEFINITIONS` (also imported directly by `edge-agent/ui/data_table_tab.py:36`). Telling detail: the edge-agent re-implements its own private `_normalize_page_label` (`edge-agent/workers/capture/bper_capture_worker.py:388`) instead of using this one — the chain was built for a consumer that never wired up.
**Recommendation**: delete the label→key chains, or wire the edge-agent's duplicate to them — a decision for the owner; intent is unknown, so flagged rather than assumed.
Confidence: 90

### HYG-05 — `streamlit` phantom dependency
**Where**: `requirements.txt:5`
**Map anchor**: interconnect `### hygiene` bullet 5; deep-dive D6.
No importer anywhere in the repo (grep for `streamlit` across all `.py` files: zero code hits; every hit is documentation discussing its orphan status). The historical importer (`app.py`, a Streamlit UI) was deleted (docs cite commit `ea04ef7`). CLAUDE.md's Dependencies section already lists it as a removal candidate — a documented-but-unexecuted cleanup, and a heavy install for a package that pulls it in for nothing.
**Recommendation**: remove the line; pair with HYG-10 items 1-2 (the docstrings that still name `app.py`) in one commit.
Confidence: 98

### HYG-06 — Bare `except:` in `norm_number_str`
**Where**: `extraction/normalization.py:54` (ruff `E722`, confirmed)
**Map anchor**: interconnect `### hygiene` bullet 6.
`try: ... float(s) ... except: return s.strip()` catches everything including `KeyboardInterrupt`/`SystemExit`, and silently returns the raw cleaned string on genuinely malformed numeric input. That fallback value then flows into numeric equality checks in `classify_field` (`normalization.py:129-133`) and `dataset_mismatch_guard` (`normalization.py:185`), where a silently-unparsed value can flip OK/WRONG classification or the mismatch guard. Kept in the hygiene report because it is a lint-verifiable pattern violation; the behavioral consequence belongs to logic-integrity (see Cross-Reviewer Notes).
**Recommendation**: `except ValueError:` at minimum (the only exception `float()` raises on a non-empty digits-and-dot string).
Confidence: 100

---

## Low

### HYG-07 — Unused imports: 10 × ruff F401, all linter-verified
**Where / list** (ruff 0.15.20 output, reproduced):
- `extraction/cli.py:25-27` — `eval_outputs`, `build_debug_report`, `print_cost_summary` (`main()` uses the `Evaluator` methods instead, `cli.py:343-347`; the functions themselves stay live via `gui_app.py:9-10` and the facade — only these cli-local imports are dead)
- `extraction/evaluation.py:2` `os`, `:3` `json`, `:4` `Tuple`, `:9` `norm_text`, `:10` `norm_number_str`
- `extraction/normalization.py:5` — `FIELD_KEYS`, `_SOGGETTI_KEY_MAP`
- `extraction/schemas.py:2` — `Union`, `Dict`, `Any`
**Map anchor**: interconnect `### hygiene` bullet 4 — matches exactly, nothing extra found and nothing refuted.
All are mechanically fixable (`ruff --fix`); none is a facade re-export (the `__init__.py` facade imports these symbols from their home modules directly, so removal is consumer-safe).
**Recommendation**: apply `ruff check extraction --select F401 --fix`; consider adding ruff to the (currently absent) CI story.
Confidence: 100

### HYG-08 — `FIELD_RETRY_MAP` built and exported, consumed nowhere
**Where**: `extraction/config.py:85-88` (built by loop at import time), `extraction/__init__.py:15,57` (exported)
**Map anchor**: interconnect `### hygiene` bullet 3.
Zero consumers repo-wide: the pipeline iterates `AREA_TO_FIELDS` directly in both the retry-trigger scan (`pipeline.py:252`) and the retry-merge loop (`pipeline.py:296`); no external consumer imports it (checked `main.py`, `gui_app.py`, `edge-agent/`). Pure derived state recomputed at every import; its existence invites a future caller to treat it as authoritative when `AREA_TO_FIELDS` is the actual source of truth (CLAUDE.md Constraint #10: consistency by convention only).
**Recommendation**: delete map, loop, and the two `__init__.py` entries — or document why the inverted index is kept.
Confidence: 95

### HYG-09 — `_SOGGETTI_KEY_MAP` and `_GARANZIE_KEY_MAP` are dead data constants
**Where**: `extraction/fields.py:102-106` and `extraction/fields.py:108-116`
**Map anchor**: interconnect `### hygiene` bullet 4 (covers `_GARANZIE_KEY_MAP`; the `_SOGGETTI_KEY_MAP` half is a refinement).
`_GARANZIE_KEY_MAP` has zero importers repo-wide (grep: definition only). `_SOGGETTI_KEY_MAP` is nominally imported by `normalization.py:5` but never used there (ruff F401, see HYG-07) — so both column→key tables are effectively dead. They look like leftovers from a pre-Pydantic table-parsing path; the live table schemas are the `Soggetto`/`Garanzia` Pydantic models (`schemas.py:15-41`).
**Recommendation**: delete both together with the HYG-07 import fix.
Confidence: 95

### HYG-10 — Stale docstrings: two Streamlit/`app.py` references, one wrong usage claim, one removed-package reference
1. `extraction/cli.py:296` — `run_extraction_batch` docstring: "Shared by CLI (main) and Streamlit (app.py)". No `app.py` exists (Glob-confirmed); the real second consumer is Tkinter `gui_app.py:6-14`. Map anchor: interconnect bullet 5. Confidence: 100
2. `extraction/__init__.py:3` — facade docstring: "backward compatibility with app.py and main.py". Same phantom `app.py`. Map anchor: interconnect bullet 5. Confidence: 100
3. `extraction/vlm_client.py:22` — `estimate_cost_usd` docstring: "used by evaluation and other modules". False: its only callers are inside `vlm_client.py` itself (`:105,165,212`) plus the facade export; `evaluation.py` reads pre-computed `_meta_agg` values and never calls it. *Not in the interconnect map.* Confidence: 95
4. `extraction/llm_factory.py:1` — "replaces extraction/providers/ package". No `extraction/providers/` exists (Glob-confirmed). Accurate as history, but it points readers at a path that is gone. *Not in the interconnect map.* Confidence: 90
**Recommendation**: fix all four in the same commit as HYG-05 (items 1-2 share the Streamlit-removal root cause).

### HYG-11 — `LLM_THINKING_LEVEL` config constant is dead; `llm_factory` re-reads the env var directly — *not in the interconnect map*
**Where**: `extraction/config.py:20` (constant, exported at `__init__.py:18,66`) vs `extraction/llm_factory.py:72` (`os.getenv("LLM_THINKING_LEVEL", ...)` direct read with duplicated `.strip().lower()`)
The constant has zero consumers; the one piece of code that uses the env var bypasses `config.py`, quietly violating the package's own stated pattern (CLAUDE.md Constraint #3: all config via `config.py` read at import time; deep-dive 02 §How-to-Add step 2: "Read env/config through `extraction.config`, never `os.getenv` directly"). Behavior is currently identical, but the two reads can drift.
**Recommendation**: make `llm_factory.py` import `LLM_THINKING_LEVEL` from `extraction.config`, or delete the constant and its two facade entries — one source either way.
Confidence: 90

### HYG-12 — Hardcoded `0.60` retry threshold vs env-driven dead anchor gate
**Where**: `extraction/pipeline.py:255` (literal `0.60` in the live retry-trigger gate) vs `extraction/config.py:56` (`ANCHOR_CONF_MIN` env-driven, feeding only the dead gate at `pipeline.py:91-96` and the dead `cli.py:87-88`)
**Map anchor**: interconnect `### hygiene` bullet 7; deep-dive D8.
Configurability is inverted: the confidence threshold that actually fires in production is an unnamed literal, while the one that provably affects nothing (see logic-integrity's anchor-gate finding) is a documented env var. Pure consistency/hygiene angle here — the gate bug itself is owned by logic-integrity.
**Recommendation**: promote `0.60` to a named constant in `config.py` (env-driven or not — but named and centralized).
Confidence: 95

### HYG-13 — Duplicated warnings-filter boilerplate
**Where**: `extraction/__init__.py:7-9` and `main.py:3-5`
**Map anchor**: interconnect `### hygiene` bullet 8.
Identical two-line `warnings.filterwarnings("ignore", category=UserWarning, module="pydantic"/"langchain_core")` blocks. `main.py` runs its copy, then `from extraction import *` runs the package copy again. Harmless at runtime (idempotent), but it is the same cross-cutting concern in two places.
**Recommendation**: keep the package-level copy (it protects all three front-ends), drop `main.py:3-5`.
Confidence: 95

### HYG-14 — Italian inline comments contradict the stated language policy — *not in the interconnect map*
**Where**: `extraction/config.py:62` ("Retry crops mirati (raggruppati per aree funzionali)"), `extraction/fields.py:34` ("Soggetti piatti (per compatibilità CSV screen 2)"), `extraction/fields.py:40` ("Nuovi campi screen 4 e 5")
CLAUDE.md Code Conventions mandate English comments (Italian only for prompts, field keys, UI strings, CSV headers). These three comments are in Italian. Cosmetic; noted because the policy is explicit and the rest of the package complies.
**Recommendation**: translate the three comments, or soften the CLAUDE.md rule.
Confidence: 85

---

## Info (verified, no action urged)

### HYG-15 — Module-level `extract_anchors` / `extract_from_screen` wrappers: zero callers, convention-kept
**Where**: `extraction/pipeline.py:347-365`, exported at `__init__.py:38,112`
No external caller repo-wide (CLI/GUI go through `BatchRunner`→`ExtractionPipeline`; edge-agent instantiates `ExtractionPipeline` directly at `edge-agent/local_extraction_client.py:28`). However, deep-dive 01/02 and the facade treat them as intentional backward-compatible API (same rationale as the `RESPONSE_SCHEMA`/`ANCHOR_SCHEMA` aliases), so classified **convention-kept**, not dead. Recorded so a future cleanup pass knows the call-count is zero and the compat window can be closed deliberately.
Confidence: 90

### HYG-16 — VCS hygiene: clean
`git ls-files extraction` returns exactly the 15 source files; `extraction/__pycache__` is correctly ignored via `.gitignore:21`; `git status` on the directory is clean. Generated CLI artifacts (`poc_outputs_improved.json`, `poc_debug_improved.csv`) land under `INPUT_DIR` (`mnt/data`), which is gitignored. No tracked artifacts, no orphan assets in scope.
Confidence: 100

---

## Anchor verification summary

| Interconnect map anchor (lines 507-533) | Verdict |
|---|---|
| ~115-line dead dedup cluster (`cli.py:36-152`, call at `:268-273`) | **Confirmed** (117 lines incl. blanks; classified quarantined per CLAUDE.md) → HYG-01 |
| `_prepare_content_image` never called | **Confirmed** → HYG-02 |
| `get_screenshot_paths` chain orphaned (+ body-level `import re`) | **Confirmed** → HYG-03 |
| `FIELD_RETRY_MAP` exported, unconsumed | **Confirmed** → HYG-08 |
| Unused imports (cli/normalization/evaluation/schemas) | **Confirmed, ruff-verified, exact match** → HYG-07 |
| `_GARANZIE_KEY_MAP` zero importers | **Confirmed + refined** (`_SOGGETTI_KEY_MAP` equally dead via unused import) → HYG-09 |
| Stale Streamlit docstrings + `streamlit` phantom dep | **Confirmed + extended** (two more stale docstrings found) → HYG-05, HYG-10 |
| Bare `except:` `normalization.py:54` | **Confirmed, ruff E722** → HYG-06 |
| Hardcoded `0.60` vs env-driven threshold | **Confirmed** → HYG-12 |
| Duplicated warnings-filter boilerplate | **Confirmed** → HYG-13 |
| Legacy aliases `RESPONSE_SCHEMA`/`ANCHOR_SCHEMA` | **Verified intentional — excluded** per CLAUDE.md |

New findings beyond the map: HYG-04 (dead resolver chains, ~78 lines), HYG-10 items 3-4 (two more stale docstrings), HYG-11 (`LLM_THINKING_LEVEL` dead constant + config bypass), HYG-14 (language-policy drift), HYG-15/16 (verified-clean records).

---

## Cross-Reviewer Notes

For **logic-integrity-reviewer**:
- The anchor confidence gate (`pipeline.py:91-96`) is dead *by bug*, not orphaning — `safe_field` copies (`pipeline.py:87-88`) discard the `safe_set_field` mutation, and `safe_set_field` cannot null non-null values (`normalization.py:78-79`). Deliberately NOT reported here as removable dead code; it needs fixing, not deleting.
- `_merge_tables` unreachable branch: `elif len(old_data) == 0 and len(new_data) > 0` (`pipeline.py:240-241`) is subsumed by `len(new_data) > len(old_data)` (`pipeline.py:236`). Dead branch; delete-vs-restructure is a logic call.
- HYG-06's behavioral tail: the bare-except fallback in `norm_number_str` returns unparsed strings into `classify_field` numeric comparison (`normalization.py:129-133`) — can silently mislabel OK/WRONG.
- If the HYG-01 dedup cluster is ever re-enabled: `_is_confident_output` (`cli.py:87-88`) keys off `ANCHOR_CONF_MIN`, whose semantics are currently broken by the dead anchor gate — re-enabling dedup before fixing the gate produces a near-unpassable filter.

For **security-reviewer**:
- `evaluation.py:172-177` and `:234-239` write LLM-extracted values verbatim to `;`-separated, `utf-8-sig` (Excel-destined) CSV with no formula escaping — CSV/formula injection surface (deep-dive S1).

For **architecture-reviewer**:
- HYG-11 is also an Architectural Constraint #3/#5 violation (env read outside `config.py`, duplicated normalization) — pattern enforcement is yours.
- Edge-agent's private `_normalize_page_label` (`edge-agent/workers/capture/bper_capture_worker.py:388`) duplicates the dead `page_definitions.normalize_page_label` — centralization miss related to HYG-04 (the live copy is outside my scope to report).
- `requirements.txt` has no pins and no lock file; beyond the `streamlit` orphan (HYG-05), LangChain-trio reproducibility is the risk the deep-dive notes — pinning policy is an architecture call.

---

**Status**: review complete. 6 Medium, 8 Low, 2 Info findings; all interconnect-map hygiene anchors confirmed (ruff-verified where lintable); 5 net-new findings beyond the map; no code edits made.
