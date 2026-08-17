# Open Points

Findings from the 2026-08-17 prompt-catalog rewrite that **no prompt change can fix**. Both are
code-level. Neither was fixed inline, because both change extraction behaviour and deserve a
measured decision rather than a drive-by edit.

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
- The budget is `max(0, MAX_CALLS_PER_SCREEN - 2)` = 2 areas, taken in `AREA_TO_FIELDS` declaration
  order HEADER, BODY, FOOTER (`pipeline.py:261-266`). HEADER and BODY therefore consume the budget
  on most screens and **FOOTER almost never runs**.

Verified empirically (crop chain regenerated for all 9 screenshots): on the three "Risultato
ricerca" screens, `RETRY_AREAS["HEADER"] = (0.00, 0.00, 1.00, 0.35)` cuts **exactly above the table
header row**. The crop contains only application chrome (menu tabs, the connected operator's name
and codes, the "Legenda Icone" link) and **none of the 8 HEADER fields**, while containing several
numbers that look like an NDG.

Consequence: one VLM call per screen that cannot succeed by construction, plus
`note_della_richiesta` and `note_scheda_privati` rarely getting the repair pass that exists for
them. The rewritten prompt makes that call harmless (everything null) but not useful.

Options, none evaluated:

- remove `ultima_validazione_scheda` from the fields that arm the HEADER retry, keeping it
  extractable in the main pass
- widen `RETRY_AREAS["HEADER"]` from 0.35 to roughly 0.50, so the crop includes the table header
  and the first data row
- raise `MAX_CALLS_PER_SCREEN`, at a direct per-screen cost

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
