# Consolidated Findings — team review of `extraction/`

**Target**: `extraction/` (full-module review at HEAD, no diff)
**Reviewers**: security (security-auditor), architecture (code-auditor), logic-integrity (logic-integrity-auditor), hygiene (cleanup-auditor)
**Date**: 2026-07-21
**Raw findings**: 58 (ARCH 18, SEC 7, LI 17, HYG 16) → **52 consolidated** after 5 merges + 1 partial merge; 2 Info records kept separately.
Full detail per finding lives in `findings-{architecture,security,logic-integrity,hygiene}.md`; this file is the dedup ledger and severity ordering.

**Merges applied** (same defect, multiple reviewers — credited to all):
- CR-01 ← ARCH-01 + F1 (independently verified by both; cross-noted by security)
- ME-07 ← ARCH-10 + F11 (cost-telemetry under-count cluster)
- LO-14 ← ARCH-14 + HYG-11 (`LLM_THINKING_LEVEL` dual read / dead constant)
- LO-18 ← ARCH-18 + HYG-12 (hardcoded 0.60 vs env-driven dead threshold)
- LO-13 ← HYG-10 + ARCH-16 stale-reference half (ARCH-16's export-asymmetry half kept as LO-16)

**Co-located, kept separate**: ME-23 (HYG-06 bare `except:`) and LO-05 (F13 numeric misparse) both at `normalization.py:40-55` — different defects. HI-02 (F3 dead gate) and ME-12 (ARCH-09 API-design root) — manifestation vs root cause.

**Cross-dimension confirmations** (≥2 reviewers independently, high real-bug signal): CR-01 (arch + LI), HI-02/ME-12 (LI + arch + sec + hyg notes), HI-04 (LI + arch note), HI-01 (sec + arch note + hyg note), ME-23/LO-05 (hyg + LI + sec note), LO-06 dead branch (LI + arch note + hyg note).

---

> **Post-verification (Phase 4b) severity adjustments** — see `98-verification.md`. 0 findings filtered; all 12 panel findings survived. Recalibrations: HI-01 High→Medium (verified); HI-06 High→Medium (contested); HI-07 High→Medium (contested). Contested (survive, reviewers split): HI-04 (High), HI-06, HI-07, ME-17, LO-01, LO-08. The tables below show original reviewer severity; the final report applies the adjusted severities.

## Critical (1)

| ID | Title | Location | Sources | Conf |
|---|---|---|---|---|
| CR-01 | `MAX_CALLS_PER_SCREEN ≤ 2` crashes effectively every screen (`ThreadPoolExecutor(max_workers=0)`); docs claim clean disable; parallel batch then silently yields zero results | `pipeline.py:259-263, 284` | ARCH-01 + F1 | 95 |

## High (8)

| ID | Title | Location | Sources | Conf |
|---|---|---|---|---|
| HI-01 | CSV/formula injection at all 3 export sinks (CWE-1236); Excel is the intended consumer | `evaluation.py:172-177, 234-239`; `local_extraction_client.py:131-143` | SEC-001 (+ARCH-13, HYG note) | 90 |
| HI-02 | Anchor confidence gate dead via 3 independent mechanisms; `ANCHOR_CONF_MIN` tunes nothing | `pipeline.py:86-102`; `normalization.py:78-79` | F3 (root: ME-12) | 98 |
| HI-03 | Nullish-vocabulary bypass at 4 anchor-path sites; `"n/d"` anchor poisons hint, overwrites good values, `_status="OK"` | `pipeline.py:113, 205-216, 173-178` | F4 | 85 |
| HI-04 | Soggetti flatten destroys retry-recovered values, drops `evidence_text`, mixed provenance, stale `_field_sources` | `pipeline.py:159-166` | F5 (+ARCH note) | 95 |
| HI-05 | Retry areas page-type-blind: HEADER never retried under default budget; retry budget burned unconditionally every screen | `pipeline.py:251-263`; `config.py:69-82` | F2 | 85 |
| HI-06 | Nested unbounded thread-pool fan-out (up to 24-36 concurrent VLM calls), no global ceiling, no explicit timeouts; retry amplifies load under throttling | `cli.py:229-234`; `pipeline.py:284` | ARCH-02 (+SEC note) | 90 |
| HI-07 | Untyped tri-shape result contract; error envelope minted by a consumer outside the package | `pipeline.py:104-180, 112-124`; `local_extraction_client.py:89-94` | ARCH-03 | 90 |
| HI-08 | Anchor-model fallback ignores provider override: GUI cross-provider selection crashes both directions; same-provider cost surprise | `cli.py:177`; `gui_app.py:238-247`; `llm_factory.py:49-63` | ARCH-04 | 90 |

## Medium (23)

| ID | Title | Location | Sources | Conf |
|---|---|---|---|---|
| ME-01 | Parallel vs serial error-semantics divergence in shared runner | `cli.py:246-251, 261-266` | ARCH-05 | 95 |
| ME-02 | Metric denominators silently shrink; crashed screens inflate accuracy vs graceful failures | `evaluation.py:79-81, 88-90` | F9 (+ME-01 feed) | 90 |
| ME-03 | Retry coverage hole: `creazione` + 5 `tooltip_*` unretryable; coherence check depends on exactly those inputs | `config.py:69-82`; `pipeline.py:311-328` | F6 | 95 |
| ME-04 | Coherence repairs don't update `_field_sources` (no `COHERENCE` source exists) | `pipeline.py:311-328` vs `:157` | F7 | 92 |
| ME-05 | Confidence unvalidated: NaN candidate always WINS `pick_best`; >1.0 unbeatable; NaN suppresses retries | `schemas.py:11`; `normalization.py:94-96`; `pipeline.py:255` | F8 (+SEC note) | 85 |
| ME-06 | Transient/permanent error split inverted: auth errors retried 3×, one-off parse failures never; sleep after final attempt | `vlm_client.py:252-257` | F10 | 90 |
| ME-07 | Cost telemetry under-counts: unknown model → $0.00, failed retries unmetered, intra-retry HTTP attempts vanish | `vlm_client.py:23-25, 241-257`; `pipeline.py:287-292, 330-340` | ARCH-10 + F11 | 90 |
| ME-08 | CSV dialect asymmetry: reader can't parse Italian-Excel GT nor the writers' own `;` output | `evaluation.py:35` vs `:172-177, 234-239` | F12 (+SEC note) | 95 |
| ME-09 | Eager monolithic facade forces full dep graph (incl. pandas) on every consumer incl. edge-agent | `__init__.py:47-126` | ARCH-06 | 90 |
| ME-10 | Import-time env config + `from`-import snapshots: untunable, untestable after import | `config.py:8-56`; `pipeline.py:11-19` | ARCH-07 | 95 |
| ME-11 | Provider dispatch re-derived from model-name substrings downstream of the factory | `vlm_client.py:18, 134, 138` | ARCH-08 | 90 |
| ME-12 | `safe_set_field` overloaded `None` sentinel + `safe_field` copy asymmetry (API root of HI-02) | `normalization.py:60-85` | ARCH-09 | 95 |
| ME-13 | `_meta` finalization triplicated across the 3 VLM paths | `vlm_client.py:100-119, 160-179, 205-226` | ARCH-11 | 95 |
| ME-14 | Raw entry point (`extract_from_image`) has no input-size clamp; contract lives in a consumer comment | `pipeline.py:104`; `local_extraction_client.py:84-86` | ARCH-12 | 85 |
| ME-15 | Result-presentation branching duplicated ×2 + third hand-rolled CSV writer (feeds HI-01 blast radius) | `evaluation.py:186-217`; `gui_app.py:333-368`; `local_extraction_client.py:112-143` | ARCH-13 | 85 |
| ME-16 | Banking PII written to cwd, outside `.gitignore` coverage (GUI outputs) | `gui_app.py:250-256, 273-274` | SEC-002 | 82 |
| ME-17 | Raw OCR JSON (PII) in exception strings surfaced to stdout/log pane/dialogs | `vlm_client.py:39, 43-44, 95-98` | SEC-003 | 75 |
| ME-18 | ~117-line dead dedup cluster, quarantined pending decision (not free-to-delete) | `cli.py:36-152, 268-273` | HYG-01 | 95 |
| ME-19 | Orphan `_prepare_content_image`, drifting duplicate of live prep path | `pipeline.py:193-200` | HYG-02 | 98 |
| ME-20 | Dead `get_screenshot_paths` chain (function + alias + 4 facade exports) | `config.py:99-109`; `evaluation.py:19-21` | HYG-03 | 95 |
| ME-21 | Dead label→key resolver chains (~78 lines); edge-agent re-implements its own copy | `field_definitions.py:188-246`; `page_definitions.py:12-47` | HYG-04 | 90 |
| ME-22 | `streamlit` phantom dependency | `requirements.txt:5` | HYG-05 | 98 |
| ME-23 | Bare `except:` in `norm_number_str` (E722); co-located with LO-05 | `normalization.py:54` | HYG-06 | 100 |

## Low (20)

| ID | Title | Location | Sources | Conf |
|---|---|---|---|---|
| LO-01 | Prompt-injection surface via screenshot; no post-hoc value validation; anchor value re-injected into main prompt | `vlm_client.py:63-74, 186-192`; `pipeline.py:205-208` | SEC-004 (+F4 note) | 70 |
| LO-02 | Gemini safety filters hard-disabled (`BLOCK_NONE`), undocumented risk-acceptance | `llm_factory.py:64-71` | SEC-005 | 88 |
| LO-03 | API-key flow acceptable; residual `repr(chat_model)` exposure note (info) | `llm_factory.py:30-44` | SEC-006 | 80 |
| LO-04 | `DEBUG_SAVE_CROPS` writes raw banking screenshots; no guard if `INPUT_DIR` repointed into tracked tree | `imaging.py:37-42`; `config.py:93-94` | SEC-007 | 78 |
| LO-05 | `norm_number_str` misparses Italian thousands-dot amounts (`36.177`→`36.18`), strips minus sign | `normalization.py:40-55` | F13 | 80 |
| LO-06 | `_merge_tables`: dead third branch (cross-confirmed ×3) + "more rows wins" invites hallucinated-table replacement | `pipeline.py:225-241` | F14 (+ARCH, HYG notes) | 95/70 |
| LO-07 | `_field_sources` depends on `pick_best` identity return; sound today, no failure signal if changed | `normalization.py:105-107` | F15 | 95 |
| LO-08 | `dataset_mismatch_guard` soggetti fallback may compare co-obligor NDG vs practice NDG | `normalization.py:162-189` | F16 | 60 |
| LO-09 | `canonical_fields` cardinality varies with retry path, not data | `pipeline.py:297-301`; `canonical_mapping.py:24-26` | F17 | 85 |
| LO-10 | Unused imports: 10 × ruff F401 (mechanically fixable) | `cli.py:25-27`; `evaluation.py:2-10`; `normalization.py:5`; `schemas.py:2` | HYG-07 | 100 |
| LO-11 | `FIELD_RETRY_MAP` built + exported, consumed nowhere | `config.py:85-88`; `__init__.py:15,57` | HYG-08 | 95 |
| LO-12 | `_SOGGETTI_KEY_MAP` / `_GARANZIE_KEY_MAP` dead data constants | `fields.py:102-116` | HYG-09 | 95 |
| LO-13 | Stale docstrings ×4 (phantom `app.py`/Streamlit ×2, wrong usage claim, removed-package ref) | `cli.py:296`; `__init__.py:3`; `vlm_client.py:22`; `llm_factory.py:1` | HYG-10 + ARCH-16 (partial) | 95 |
| LO-14 | `LLM_THINKING_LEVEL`: dead config constant; `llm_factory` re-reads env directly (constraint #3/#5 violation) | `config.py:20` vs `llm_factory.py:72` | ARCH-14 + HYG-11 | 95 |
| LO-15 | Name shadowing method vs module wrapper `extract_from_screen`; throwaway pipelines contradict docstring | `pipeline.py:182, 357-365` | ARCH-15 | 90 |
| LO-16 | Facade export asymmetry (`Soggetto` exported; `Fido`/`Garanzia`/`AnchorFields`/`FieldsModel` not) | `__init__.py:27` vs `schemas.py:22-49` | ARCH-16 (remainder) | 95 |
| LO-17 | `screen_id` derivation duplicated ×4 (ground-truth join key) | `cli.py:225, 237, 254`; `pipeline.py:186` | ARCH-17 | 90 |
| LO-18 | Live retry threshold hardcoded `0.60`; dead anchor gate env-tunable (configurability inverted) | `pipeline.py:255` vs `config.py:56` | ARCH-18 + HYG-12 | 95 |
| LO-19 | Duplicated warnings-filter boilerplate | `__init__.py:7-9`; `main.py:3-5` | HYG-13 | 95 |
| LO-20 | Italian inline comments contradict stated language policy (×3) | `config.py:62`; `fields.py:34, 40` | HYG-14 | 85 |

## Info (2, verified-clean records)

- HYG-15 — module-level `extract_anchors`/`extract_from_screen` wrappers: zero callers but convention-kept (backward-compat).
- HYG-16 — VCS hygiene clean: only the 15 sources tracked, no artifacts, `.gitignore` correct for `extraction/`.

---

## Phase 4b selection (adversarial verification panel)

52 consolidated findings > 25 → **cost guard fires** (finding-count proxy, no `--rigorous`). Panel narrowed to **stakes + uncertainty band**:

- **Stakes (all Critical/High)**: CR-01, HI-01, HI-02, HI-03, HI-04, HI-05, HI-06, HI-07, HI-08 (9)
- **Uncertainty band (Medium/Low, confidence 50-75)**: ME-17 (75), LO-01 (70), LO-08 (60) (3)
- **Verified**: 12 findings × 3 lenses = 36 verifiers
- **Unverified (cost-guard)**: 40 findings — pass through with original severity, tagged `unverified (cost-guard)`. Note: LO-06's dead-branch half was independently confirmed by three reviewers; ME-23/LO-10 are linter-verified (ruff); ME-18..ME-22 are grep-proven dead-code claims re-verified by two agents.
