# Phase 4b — Adversarial Verification Panel

12 findings entered the panel (stakes = all Critical/High; uncertainty band = Medium/Low at confidence 50-75). 3 lenses each (L1 reachability, L2 refutation, L3 severity), 36 verifiers total. Survival rule: survives if ≥2 of L1-L2 vote REAL; filtered if ≥2 vote FALSE_POSITIVE; tie → survives `contested`. Final severity = L3 vote when confirmed real, else original.

**Result: 0 filtered. 6 verified-clean (2×REAL), 6 contested (1 REAL / 1 FALSE_POSITIVE). Every finding survived.**

| ID | L1 (reach) | L2 (refute) | L3 severity | Outcome | Final severity |
|---|---|---|---|---|---|
| CR-01 | REAL 96 | REAL 97 | *(abstained — idle)* | **verified** | Critical (unchanged; L3 fail-open) |
| HI-01 | REAL 88 | REAL 88 | Medium 65 | **verified** | **Medium** (down from High) |
| HI-02 | REAL 99 | REAL 97 | High 75 | **verified** | High |
| HI-03 | REAL 92 | REAL 80 | High 78 | **verified** | High |
| HI-05 | REAL 92 | REAL 88 | High 72 | **verified** | High |
| HI-08 | REAL 92 | REAL 90 | High 82 | **verified** | High |
| HI-04 | REAL 97 | FALSE_POSITIVE 75 | High 85 | **contested** | High (contested) |
| HI-06 | REAL 88 | FALSE_POSITIVE 72 | Medium 70 | **contested** | **Medium** (down from High) |
| HI-07 | REAL 80 | FALSE_POSITIVE 85 | Medium 75 | **contested** | **Medium** (down from High) |
| ME-17 | REAL 90 | FALSE_POSITIVE 80 | Medium 65 | **contested** | Medium |
| LO-01 | REAL 90 | FALSE_POSITIVE 66 | Low 70 | **contested** | Low |
| LO-08 | REAL 80 | FALSE_POSITIVE 62 | Low 75 | **contested** | Low |

## Recalibrations applied to 99-consolidated.md

- **HI-01 → Medium**: both L1 and L2 confirm the sink is real and unescaped, but L3 (and L2's framing) place it at Medium — multi-stage precondition chain (attacker text must survive verbatim OCR into a field, analyst must open the CSV in Excel), local-analyst impact, workaround exists. Vulnerability class is unambiguously present; severity is Medium not High.
- **HI-06 → Medium (contested)**: L2 refutes the "unbounded / 24-36 / High" framing — both pools have explicit `max_workers`; realistic CLI peak is 4×2=8, GUI 12×2=24 only if a user uploads 12+ images; LangChain ChatModels are thread-safe by design and the SDK carries default timeouts + rate-limit retries. L1 confirms the residual real defect: no global ceiling *across* the two pools and no app-set timeout. Net: a real but self-limited resource-management gap at POC scale → Medium.
- **HI-07 → Medium (contested)**: L2 traced all three result shapes to every live consumer and found none hard-indexes a minority shape (all use `.get(...) or {}/[]`); the "unguarded" engine reads are on freshly-constructed VLM outputs, not the variant envelope. L1 and the finding itself frame it as *latent*, not a current crash. Real maintainability/latent-crash risk, no reachable crash today → Medium.

## Contested-finding notes (survive, but reviewers split)

- **HI-04** — genuine technical dispute. L1: `ndg_1..ruolo_4` ARE scalar schema fields (`schemas.py:46-48`), BODY retry populates them via `merge_field_sources`, and `_merge_tables` can keep an old table whose row-1 `ndg` is None, so the flatten writes None over a retry-recovered scalar → data loss reachable. L2: neither the main prompt nor `RETRY_PROMPT_BODY` ever asks the VLM to fill the flat keys (only the `soggetti` array), so the flat fields stay null through main+retry and the flatten is the sole authoritative source — "table wins" is intentional, documented design (CLAUDE.md constraint #6). **Agreed by both**: the missing `_field_sources` update and dropped `evidence_text` are real (provenance/debug metadata only). Kept at High, contested — the disagreement is whether the flat scalar fields are ever independently populated; resolving it needs a runtime check of what the VLM actually returns for those keys.
- **ME-17** — L1 correction: the raw-PII exception strings reach stdout (`cli.py:251`) and the GUI **log pane** (`gui_app.py:236`), but NOT the modal dialog (`gui_app.py:283`) — per-screen ValueErrors are routed to `on_error`, only whole-batch failures hit the modal. L2: the leak sites are on the Gemini free-form path only (never fires in the default OpenAI config), and add no new data class beyond what the results pane + JSON/CSV outputs already expose to the same local analyst. Survives contested at Medium.
- **LO-01** — L2: "no value validation" is the documented verbatim-transcription requirement; the anchor re-injection crosses no new trust boundary (the screenshot is already attacker-controlled); the material risk (CSV injection) is owned by HI-01. Real surface, minimal standalone actionability → Low, contested.
- **LO-08** — L2: first-row-only premise is code-accurate, but the guard feeds only the RAW-vs-FILTERED split (RAW always counts every screen; FILTERED needs the absent CSV); fires only when the header NDG is already nullish on screens 2-3 where the intestatario is normally first. Best-effort heuristic → Low, contested.

## Unverified (cost-guard): 40 findings

52 consolidated findings > 25 → cost guard fired (finding-count proxy; no `--rigorous`). The 40 findings outside the panel pass through at their original reviewer severity, tagged `unverified (cost-guard)`. Confidence in this set is nonetheless high for the mechanical claims: ME-23/LO-10 are ruff-verified; ME-18..ME-22 and LO-06's dead-branch are grep-proven dead code re-verified by two independent agents; LO-06's dead `_merge_tables` branch, ARCH-01/F1 duplication, and the hygiene anchors were each confirmed by ≥2 reviewers during Phase 2.
