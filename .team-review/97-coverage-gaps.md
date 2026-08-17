# Phase 4c — Completeness Critic: Coverage Gaps

The review had strong coverage: all 10 interconnect integration hot-spots and 8 of 11 unverified assumptions each drew ≥1 finding. The gaps below are what the four dimensions (security, architecture, logic-integrity, hygiene) did NOT examine.

## Coverage Gaps

### 1. Dimensions warranted but not run

- **Performance — the biggest omission.** No reviewer examined the image-payload cost path, despite cost tracking being load-bearing architectural constraint #2. Deep-dive `05-risks.md` localized three performance defects that NO consolidated finding picked up:
  - **P1** — every VLM call encodes each crop as **lossless PNG** then base64s it (`imaging.py:31-34`, sends at `pipeline.py:75,128,276`, base64 at `vlm_client.py:132`); a 1800px content crop is multi-MB, re-sent on anchor + main + every retry (up to 4 calls/screen). Directly inflates the token bill that ME-07 tracks. No JPEG/downscale option.
  - **P3** — `normalize_image` only shrinks, never upscales low-DPI captures (`imaging.py:14-16`) — an accuracy gap for an OCR-fidelity pipeline.
- **Testing — knowably zero.** No test suite exists; no reviewer assessed testability or flagged the absence as a risk. The pipeline's accuracy claims are unverifiable without the absent `mnt/data/dati.csv`.
- **API-contract — not run as a dedicated dimension.** The `schemas.py` Pydantic surface is a formal contract; ME-05 caught the missing confidence-bounds validator, but the schema-as-contract was not adversarially audited.

### 2. In-scope files with little or no finding coverage

- **`prompts.py` (78 lines) — ZERO dedicated findings.** The largest unreviewed file. For an extraction engine the prompts ARE the core logic: no dimension checked whether the Italian extraction/anchor/retry prompts cover all 45 fields, whether the anchor prompt's now-dead `confidence≥0.95` instruction (`prompts.py:36`) is misleading, or the Gemini free-form concatenation.
- **`imaging.py`** — one finding (LO-04); its performance surface (P1/P3) is uncovered.
- **`canonical_mapping.py`** — one finding (LO-09). **`page_definitions.py`** — one (ME-21). **`schemas.py`** — light (ME-05, LO-10); the import-time-build crash risk is uncovered.

### 3. Unverified map assumptions no finding addressed

- **`AREA_TO_FIELDS` keys ⊆ `RETRY_AREAS` keys** — a mismatched key raises `KeyError` at `pipeline.py:266`. Same unguarded-config crash class as CR-01; no finding. (Low practical stakes — both dicts hand-maintained together.)
- **`AREA_TO_FIELDS` values ⊆ `FIELD_KEYS` (typo direction)** — `05-risks` D2; ME-03 covers only the opposite direction (fields missing from all areas), not a typo silently creating an unread `result["fields"]` entry.
- **Pydantic reserved-name collision → global import failure** (`schemas.py:46-49`) — mentioned only as a consequence of ME-09, never a first-class finding.

### 4. High-risk `05-risks.md` items with zero findings

P1, P3, and the Pydantic-import-crash (D3) are the deep-dive risk items that reached no consolidated finding. Everything else in `05-risks` mapped to a finding.

## Recommended follow-up

**Performance review of the image-payload / encoding path** — `imaging.py` (`:31-34` encoding, `:14-16` shrink-only), `pipeline.py` (`:75,128,276` image sends), `vlm_client.py:132` (base64), cross-referenced with the cost-telemetry chain (ME-07); secondary read of `prompts.py` for correctness/completeness and prompt token weight.

**Status: SKIPPED (cost guard).** The cost guard fired in Phase 4b (52 findings > 25). Per the review framework, the bounded follow-up round degrades to report-only when the cost guard applies. The performance gap is recorded here and surfaced in the final report as the top recommended next action; the user can trigger a focused `performance` review of these files to close it.
