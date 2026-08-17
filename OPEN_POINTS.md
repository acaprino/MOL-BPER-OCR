# Open Points

Findings that need a measured decision rather than a drive-by edit. Sections 1 and 2 come from the
2026-08-17 prompt-catalog rewrite and are things **no prompt change can fix**; section 3 is the
residual risk left by the page-routing repair of the same day.

Decisions already taken are not here: they live in `docs/adr/`.

The challenge packet and the cross-model review that surfaced part of this are in
`.peer-review/2026-08-17-1520-prompt-catalog-rewrite/`.

---

## 1. Retry crop geometry and the retry budget

### 1.1 The HEADER retry is armed on almost every screen, and often sees nothing

Verified in code:

- An area is marked for retry if **any** of its fields is nullish **or** below `RETRY_CONF_MIN`
  (0.60) -- `pipeline.py:250-256`.
- `ultima_validazione_scheda` only exists on the scheda privati, so it is null on nearly every
  screen. On its own it arms the HEADER retry almost always.
- The budget is `max(0, MAX_CALLS_PER_SCREEN - 2)` areas, taken in `AREA_TO_FIELDS` declaration
  order HEADER, BODY, FOOTER (`pipeline.py:261-266`). With the former literal default of 4 that was
  2 areas: HEADER and BODY consumed the budget on most screens and **FOOTER almost never ran**.

**Resolved on 2026-08-17 (the budget half only).** `MAX_CALLS_PER_SCREEN` now defaults to
`2 + len(AREA_TO_FIELDS)` = 5, derived rather than written, so every declared area gets a retry and
FOOTER is no longer starved. Covered by `tests/test_pipeline_retry.py`, rationale in
`docs/adr/0004-budget-retry-derivato-dalle-aree.md`. Note that `.env` and `.env.example` had an
explicit `MAX_CALLS_PER_SCREEN=4` that would have silently cancelled the change; both were updated.

**Still open: the wasted HEADER call.** Raising the budget does not stop the HEADER retry from being
armed on screens where it cannot succeed. Both facts below are unchanged.

Verified empirically (crop chain regenerated for all 9 screenshots): on the three "Risultato
ricerca" screens, `RETRY_AREAS["HEADER"] = (0.00, 0.00, 1.00, 0.35)` cuts **exactly above the table
header row**. The crop contains only application chrome (menu tabs, the connected operator's name
and codes, the "Legenda Icone" link) and **none of the 8 HEADER fields**, while containing several
numbers that look like an NDG.

Consequence: one VLM call per screen that cannot succeed by construction. The rewritten prompt makes
that call harmless (everything null) but not useful. It no longer costs FOOTER its retry, but it
still costs money on every screen.

Options, none evaluated:

- remove `ultima_validazione_scheda` from the fields that arm the HEADER retry, keeping it
  extractable in the main pass
- widen `RETRY_AREAS["HEADER"]` from 0.35 to roughly 0.50, so the crop includes the table header
  and the first data row
- ~~raise `MAX_CALLS_PER_SCREEN`~~ -- done, see above; it fixed the starvation, not the waste

The principled fix for both is to scope the retry areas by the recognized page, which the pipeline
already receives as `screen_id`. It is blocked on the field → page map being wrong: several scheda
privati fields are tagged `note_da_richiesta` in `extraction/field_definitions.py`. Tracked in
`docs/08-open-questions.md`.

### 1.2 The FOOTER crop may not contain the field it exists to repair

`AREA_TO_FIELDS["FOOTER"]` holds `note_della_richiesta` **and** `note_scheda_privati`. On screens 4
and 5 (the scheda privati pages) the FOOTER crop `(0.00, 0.65, 1.00, 1.00)` shows no free-note box:
the field appears to sit above the 0.65 line. If that holds, the retry meant to repair
`note_scheda_privati` can never see it, and the field is unrecoverable after the main pass.

**Status: inferred from crop inspection, not confirmed against ground truth.** Confirm before
moving the crop boundary, since widening FOOTER upward overlaps BODY.

Related, lower stakes: on 4 of the 9 screens the FOOTER crop contains a long "Strategie Politiche
Creditizie" block, an ideal decoy for `note_della_richiesta`. The rewritten prompt now names that
class of decoy, but a crop that excluded it would be the stronger fix.

---

## 2. Silent failures on the free-form JSON path

`ExtractionResponse` has **no required fields and no `extra="forbid"`**, so two different broken
responses validate cleanly and yield a full set of MISSING fields, indistinguishable from a
genuinely empty screen. No exception, no warning, no log entry.

1. **Schema echo** -- the model returns the *schema* (`properties`, definitions, references) instead
   of an instance. The extra keys are ignored, `fields` stays empty.
2. **Empty instance** -- `{}` or `{"fields": {}}`. Flagged by the cross-model review as the failure
   mode that the new "omit the keys you did not read" instruction makes *more* likely.

The rewritten `extraction_json_schema_instruction` forbids both, and `extraction_main` now requires
6 always-present keys so an empty `fields` object is not a valid answer. Neither is a guarantee: a
prompt cannot enforce an output contract that the parser does not check.

A code-level guard would:

- reject a raw payload whose top level carries metaschema keys, **before** Pydantic validation
- log a warning, or count a distinct failure kind, when a parsed response yields zero non-null
  fields

Related decision worth revisiting at the same time: `call_vlm_with_retry()` re-raises parse failures
immediately (`vlm_client.py:253-257`, which since the prompt-store refactor also covers the
`KeyError`/`IndexError` a stray brace in a template would raise) because they are not transient. The
consequence is that a single malformed response costs the **entire screen**, with no second attempt.
That is
defensible on its own, but combined with the two silent failures above it means the free-form path
has one loud failure that is never retried and two quiet ones that are never noticed.

---

## 3. Page routing degrades silently when the framing cannot be normalized

The routing failure fixed on 2026-08-17 had a self-reinforcing shape worth keeping in view. See
`docs/adr/0001-normalizzazione-inquadratura-frame.md` for the full account; what remains open:

### 3.1 The fallback rectangle detection can quietly give up

`frame_normalize.normalize_frame()` tries the OS window rect first, then infers the app rectangle
from a uniform desktop background, then gives up and passes the frame through unchanged. The last
branch restores exactly the broken behaviour, without saying so.

It triggers when `window_title_contains` does not match the real window title **and** the desktop
around the window is not uniform (other windows visible at the corners). Both are plausible on an
operator's machine.

Options, none evaluated:

- log once per session when normalization falls through to the unchanged frame, so the condition is
  visible in the capture feed instead of being inferred from bad results
- refuse to route at all when neither strategy concludes, rather than routing a frame known to be
  out of distribution

### 3.2 A misdetection permanently burns a page slot

`captured_page_types` is append-only for the life of a job. A page captured under the wrong label is
consumed, the real page can no longer be acquired under that name, and the operator has no way to
undo it: `_capture_once()` returns early on every subsequent frame with "già acquisita". That is what
turned a routing error into a stuck session.

The routing fix makes it far less likely, not impossible. Worth considering:

- an operator action to release a captured page slot
- refusing to mark a page acquired when the extraction result is incoherent with the claimed page
  (e.g. the page's own defining field came back null), which would need the field → page map that
  `docs/08-open-questions.md` flags as currently wrong

### 3.3 The similarity threshold is calibrated on synthetic negatives only

`DEFAULT_SIMILARITY_THRESHOLD = 0.35` sits between correct matches (0.664-0.982 measured across 9
pages and 3 window scales) and two synthetic negatives (a flat desktop at 0.096, mid-grey at 0.200).
There are no real non-BPER screenshots to calibrate against, because the only images available are
the 9 reference pages. The margin is wide, but the negative side of it is unmeasured on real input.
