# Alignment test evidence — 2026-10-16

Scope: `training/alignment.py` and `tests/test_training_alignment.py`.
Command throughout: `.venv/Scripts/python.exe -m pytest tests/test_training_alignment.py -q`.
These are checks executed during implementation, not copied results from an older run.

## Initial behavior checks

Five tests were written before the module existed. Collection failed as expected with
`ModuleNotFoundError: No module named 'training'` (one collection error).
After implementation: **5 passed in 0.27s**; the subsequent cleanup run reported
**5 passed in 0.26s**.

The behaviors covered are field-region isolation for every token, repeated long-note
coverage, unchanged OCR text when locating a reviewed six against an observed eight,
no synthetic positive annotation for an absent subject, and word bounds following
asymmetric source ink rather than character-count spacing.

## Explicit partial text supervision

The long-note test with one incorrect OCR digit was added before `verified_indices`.
Observed red result: **1 failed, 5 passed**; failure was the expected
`KeyError: 'verified_indices'`. After implementation: **6 passed in 0.67s**.

The validation-date test was added before extending partial supervision to that field.
Observed red result: **1 failed, 6 passed**; failure was again the expected missing
`verified_indices`. After implementation: **7 passed in 0.40s**.

These changes add ordered exact word verification for the two note fields and the
validation-date field only. They retain false whole-field exactness when any OCR word
differs. Observed incorrect digits and misspelled words never become verified tokens.

## Source punctuation preservation

Three tests were added before the punctuation fix. Observed red result:
**3 failed, 7 passed**. The failures showed:

- A source hyphen between matched field words was omitted from the selected indices.
- A source value missing reviewed punctuation incorrectly counted as exact.
- A partial note word missing its reviewed punctuation incorrectly counted as verified.

After preserving real intervening source punctuation and making full/partial exact
comparison preserve punctuation and word boundaries: **10 passed in 3.96s**, exit 0.
No existing assertion was weakened.

## Cached-data checks

Implementation smoke checks used the existing local OCR cache and original PNGs,
covering Elenco, Soggetti, Gestione Fidi, Note and all five Scheda Privati screenshots.
They made no provider calls and changed no source screenshots or OCR text.

The final independent aggregate check is recorded in `dataset-audit.json` beside this
file. It verifies all 1,008 Excel targets against the exported CSV, all 113 source OCR
word sets, role coverage, frozen-content hashes and split isolation. It reports no raw
banking names, identifiers or note text.

The root task owns full-suite verification and the current X-ray refresh.
