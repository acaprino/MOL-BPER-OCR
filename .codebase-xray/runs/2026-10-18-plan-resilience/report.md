# Scoped review: resilience requirement in the next-version plan

- Reviewed on 2026-10-18, at HEAD `d9462a46b75a5cb50e58ad6c6ebb30ddec85b807` with uncommitted documentation changes.
- Covered document: `docs/next-ver-plan.md`, SHA-256 `14bdb6c07cd4ba7a4e159cdd8eadce86acf8d051aced91f2287481c31e767b8f`.
- The plan was already untracked before this change. The unrelated untracked `uv.lock` was left untouched.
- No runtime, test, configuration, model, screenshot, workbook, or training dataset was changed.
- No earlier X-ray report exists in the current working tree at either `.codebase-xray/` or `.tritech/codebase-xray/`. Historical reports remain in Git; this is a new scoped review, not a claim that the entire codebase has been reanalysed.

## Documentation finding addressed

**R1 — Resilience was absent from the acceptance gates: resolved in the plan only.**
The user's requirement is now explicit at `docs/next-ver-plan.md:12`, with blocking gate G7 at line 120 and its test protocol at line 158. The protocol covers fault isolation, hangs and worker failures, bounded load and retention, ordered identity-safe results, offline startup, stop/restart, export failures, and an eight-hour / 1,000-frame soak for each CPU profile. Phase 2 promotion at line 211 now distinguishes experimental integration from operational adoption; G6 must be measured on the integrated process and G7 must pass. The same rule applies to Phase 3. Required reliability reports are listed at line 230.

The protocol requires finite declared recovery limits, real packaged-runtime checks, and evidence for every criterion. It does not claim those guarantees exist today. Changes to practice association require an explicit ADR and behavioral regression rather than an implicit rewrite of the current rule.

## Affected flow and interface review

The relevant flow remains capture -> normalized frame -> `LocalExtractionClient.ingest_frame()` -> daemon pool -> extraction -> ordered results -> practice consolidation -> Excel export. Public interfaces and runtime behavior are unchanged.

| Finding | Current evidence | Status |
|---|---|---|
| Queue capacity is unbounded | `src/edge-agent/extraction_pool.py:24` constructs `queue.Queue()` without a maximum. | Open runtime requirement; G7 now requires explicit capacity and saturation behavior. |
| Native inference hangs are not recovered | `src/edge-agent/local_extraction_client.py:173` calls the pipeline without a per-task deadline or cancellation mechanism; daemon workers permit process exit, not recovery. | Open; G7 requires restored capacity, including with one worker. |
| Ordered publication can wait indefinitely | `src/edge-agent/local_extraction_client.py:200` publishes only the contiguous completed prefix. This protects capture order but a hung earlier task can hold subsequent results. | Open; preserve ordering while ensuring a terminal outcome for every accepted job. |
| Results have no retention bound | `src/edge-agent/local_extraction_client.py:116` retains job results and completions in dictionaries without an explicit retention policy. | Open; queue, images, results, logs and resident engines must fit the declared resource envelope. |
| Anonymous frames can be ambiguous at a practice boundary | `src/edge-agent/practice_consolidation.py` associates a frame lacking NDG with the preceding practice. Capture order alone cannot establish identity if the first new-practice identifier is unreadable. | Open design decision; G7 requires an ADR and a regression for any association change. |
| Current startup is not proof of offline readiness | `LocalExtractionClient` constructs LLM models when no pipeline is injected; existing bootstrap supports a first-run classifier download. | Open for the future offline OCR candidate; packaged startup must be tested with networking disabled and no cache. |

The earlier plan-review findings about test-set selection, missing field coverage, G3 population, baseline per-field numbers, evaluation/subset/version contracts, Pixel Guard coverage, licenses and gate arithmetic were not repaired by this requirement-only change. Integrated G6 promotion was clarified, but no resource measurement has been performed.

## Newly executed verification

- Documentation clause and code-fence checks passed: all six required clauses present; two code fences, balanced.
- `python -m pytest tests`, using Python 3.13.14: exit code **2**, **183 items collected / 16 collection errors**, final summary **16 errors in 6.55s**. Missing dependencies reported by collection are `PyQt6` and `langchain_core`. Full output: `pytest.txt` beside this report. No tests were weakened or skipped to hide these errors, and no dependencies were installed for this documentation-only change.
- No soak, fault injection, OCR benchmark, training, packaged-app smoke test, latency/RAM measurement, or cloud call was run. G6/G7 remain unverified.
- Existing historical test results were not reused as fresh verification.
