# Glossary

Plain-language definitions of every recurring term in this documentation set. Domain terms come from the Italian banking context of the BPER credit-management application; they appear verbatim in the code as field keys, prompts, and UI strings, and are never translated there. Technical terms cover the extraction pipeline and the tools around it.

If you are new to the project, read the [Executive Summary](00-executive-summary.md) first and keep this page open alongside anything else. For where each structure lives in the code, see [Data Model](06-data-model.md); for what the system does with them, see [Features](02-features.md).

## Italian Banking / Domain Terms

| Term | Meaning |
|---|---|
| **BPER** | The Italian banking group whose internal credit-management application ("BStore Pratiche" / PEF pages) is what this project reads. |
| **pratica** (practice) | A credit file: the dossier the bank keeps for one credit request: customer, credit lines, guarantees, income data. |
| **NDG** / `ndg` | The bank's unique customer identification number. Together with `denominazione` it identifies whose practice a screen shows. |
| **denominazione** | The customer's (person or company) name as registered by the bank. |
| **anchors** (NDG + denominazione) | The two identity fields extracted first, in their own dedicated pass: every other value only makes sense once the customer identity is locked. If either disagrees with the answer sheet, the whole screen is excluded from FILTERED accuracy. |
| **fido** (plural **fidi**) | A credit line: a facility the bank grants the customer. `n_fido` is its number. |
| **garanzia** (plural **garanzie**) | A guarantee (collateral or personal surety) backing a credit line. |
| **soggetti** | The parties (co-holders, guarantors) linked to a practice. The first four are flattened into `ndg_1..4` / `denominazione_1..4` / `ruolo_1..4`. |
| **ruolo** | The role a party plays in the practice (holder, co-holder, guarantor, …). |
| **tipo / stato / fase** | The practice's type, status, and phase as shown in the screen header. |
| **evidenze** | An alert/flag field on the practice; the value "B" can be repaired from its tooltip by the coherence check. |
| **BMB / BPI Mutui** | Practice-type labels as displayed in the BPER UI. Spelling variants of the mortgage type (`mutui spesa`, `mutuo spesa`, `bpi mutui`) are canonicalized to "BPI Mutui". |
| **scheda privati** | The "private customers" data sheet: 13 employment/income fields such as `professione_principale` (main occupation) and `retribuzione_annua_netta` (net annual salary). |
| **filiale_relazione** | The bank branch that holds the customer relationship. |
| **rapporto** | The account/relationship a credit line is attached to. |
| **scadenza** | Expiry date. |
| **importo_euro** | Amount in euro. |
| **tipo_op** | Operation type of a credit-line or guarantee row. |
| **tooltip fields** (`tooltip_*`) | Text that appears only on hover in the BPER UI; five fields capture it, and two of them feed the coherence repair rules for `evidenze` and `tipo`. |
| **Fotogramma** | "Frame": the ground-truth CSV column naming which screenshot a value belongs to. |
| **canonical pages** | The fixed four-page grouping used for client-facing export and display: `risultato_ricerca` (search result), `elenco_soggetti` (parties list), `gestione_fidi_e_garanzie` (credit lines and guarantees), `note_da_richiesta` (request notes). |
| **"Altro / Non riconosciuto"** | The catch-all "other / unrecognized" page definition; the edge-agent never captures it. |

## Technical Terms

| Term | Meaning |
|---|---|
| **VLM** (Vision Language Model) | An AI model that can look at an image and answer questions about it, the project's reading engine. Also written "Vision-LLM". |
| **LLM** | Large language model; the text-and-image AI behind both extraction and page routing. |
| **prompt** | The written instructions sent to the model with each image. Italian here, by design. |
| **anchor pass / main pass / retry pass** | The three reading steps: customer identity first, everything on the page second, a focused re-read of weak areas third. |
| **confidence** (score) | The model's self-reported 0-1 certainty for each value. It drives retries and tie-breaks but is not independently verified. |
| **structured output** | Forcing the model to answer in a fixed, machine-checkable JSON shape instead of free text; invalid answers fail loudly. |
| **Pydantic** | The Python library that defines and validates those output shapes ("schemas"). |
| **LangChain / ChatModel** | The abstraction layer that makes OpenAI and Google Gemini interchangeable behind one factory function. |
| **provider** | Which AI service runs the extraction (OpenAI (default) or Google Gemini) selected by the `LLM_PROVIDER` setting. |
| **ground truth** / `dati.csv` | The answer sheet of human-verified expected values used to grade the extraction. |
| **token** | The unit AI services bill by; per-call token counts feed the cost report. |
| **crop / crop region** | A fixed rectangular slice of the screenshot sent to the model (header strip, content area, retry areas). |
| **result dict** | The single per-screen output structure (values, tables, provenance, cost) that everything downstream consumes. |
| **field provenance** / `_field_sources` | The record of which pass produced each field's final value. |
| **coherence check** | Post-processing rules that repair `evidenze` and `tipo` from tooltip evidence after all passes. |
| **RAW vs FILTERED** | Accuracy counted over all screens vs only screens whose identity anchors matched ground truth. |
| **DATASET_MISMATCH** | A whole-screen flag: the extracted NDG/denominazione disagree with the ground-truth row, so the screen is excluded from FILTERED metrics. |
| **OK / WRONG / MISSING / HALLUCINATED / OK_NULL** | The per-field grades: correct; incorrect; expected a value but got none; produced a value where none was expected; correctly empty. |
| **edge-agent** | The PyQt6 desktop app that watches a monitor and runs extraction live as an operator navigates BPER. |
| **pHash dedup** | Perceptual hashing: near-identical consecutive frames get near-identical fingerprints and are skipped instead of re-processed. |
| **Hamming distance** | How many bits differ between two hashes; a small distance means near-duplicate frames. |
| **stability gate** | The 2-second "hold still" requirement before a detected page is captured: prevents extracting mid-scroll. |
| **page routing / router** | Deciding which BPER page is on screen before extracting; modes `llm` (OpenAI Vision), `ml` (local classifier), `hybrid` (LLM first, ML fallback). |
| **prototype classifier** (DINOv2) | The local ML router: turns the page header into a 384-number embedding and compares it by cosine similarity against cached per-page prototypes. |
| **embedding** | A numeric fingerprint of an image that makes visual similarity measurable. |
| **hallucination guard** | Rejecting router answers that name a page not present in the page definitions file. |
| **QThread / Qt signal** | Background thread and thread-safe messaging in the PyQt6 UI; the `result_ready` signal carries each result back to the interface. |
| **CLI** | Command-line interface: `python main.py`, the batch-and-evaluate front-end. |
| **Tkinter / PyQt6** | The two desktop UI toolkits: Python's built-in one (the simple GUI) and the richer one (the edge-agent). |
| **mss** | The library used for fast whole-monitor screen capture. |
| **FPS** | Frames per second: how often the edge-agent looks at the monitor. |
| **thread pool** | Running several screens' extractions in parallel to shorten batch runs. |
| **env var / `.env`** | Configuration through environment variables, loaded from a local (never committed) `.env` file. |
| **POC** (proof of concept) | Software built to prove and measure an approach, not to ship to end users. |

---

See also: [Data Model](06-data-model.md) for the exact shape each term takes in code, and [Open Questions](08-open-questions.md) for the terms whose semantics are still unconfirmed (coherence rules, `tipo` synonyms, canonical page bindings).
