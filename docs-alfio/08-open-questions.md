# Open Questions

What follows is an honest catalog of things the code cannot tell you on its own. Each question came out of something concrete in the repo -- a stubbed-out function, a configuration that disagrees with the docs, a comment that implies a decision nobody wrote down. Bring this list to your first conversation with the team; every answer you collect will make the next file you touch a little less confusing. Questions are grouped by category and ordered, within each group, by how much the answer will change your day-to-day work.

## Architecture

**Where did `app.py` go, and is Streamlit still in scope?**
`CLAUDE.md` lines 11-12 and 89 describe `app.py` as a Streamlit web UI entry point, and `extraction/cli.py` line 296 carries a docstring that says `run_extraction_batch()` is "Shared by CLI (main) and Streamlit (app.py)." But no `app.py` exists in the working tree, and `streamlit` is still pinned in `requirements.txt` line 6. Was this file removed recently on this branch, kept on another branch, or never committed? If Streamlit is gone for good, should the dependency and the docstring references be removed? This matters because a new developer reading `CLAUDE.md` will waste an hour looking for a file that isn't there.

**Which routing mode is the intended default for the edge-agent: `llm`, `ml`, or `hybrid`?**
`edge-agent/config.ini` line 4 sets `router = llm`, but `edge-agent/llm_router.py` (lines 42-50) and `edge-agent/page_classifier.py` implement a full DINOv2-based `MLPageRouter` and the repo ships cached prototype embeddings in `edge-agent/assets/templates/bper/bper_page_prototypes.json`. The context brief notes a hybrid option as well. Is the ML classifier the strategic target (cheaper, offline) with the LLM router as a fallback, or is the LLM router what actually performs well and the ML path is an early experiment? The answer changes which file you should invest time understanding first.

**Why does the pipeline keep both an anchor pass and a main pass instead of extracting NDG/Denominazione in a single call?**
`extraction/pipeline.py` lines 70-90 runs a dedicated anchor pass on just the header crop (`HEADER_IN_CONTENT = (0.00, 0.00, 1.00, 0.22)` in `extraction/config.py` line 56) with its own model (`LLM_MODEL_ANCHOR`) and its own prompt (`ANCHOR_PROMPT` in `extraction/prompts.py` line 25). The main pass then re-extracts the same fields across the full content crop. Was this split introduced because the single-pass version hallucinated anchors, because it allowed using a cheaper model for the anchor, or for some other accuracy reason? This is the single most expensive architectural decision in the pipeline -- knowing the rationale is essential before touching it.

**Is `extraction/canonical_mapping.py` the intended long-term bridge to a backend schema, or a temporary shim?**
`extraction/canonical_mapping.py` and the four canonical page names in `extraction/page_definitions.py` (`risultato_ricerca`, `elenco_soggetti`, `gestione_fidi_e_garanzie`, `note_da_richiesta`) flatten the 9-screen raw output into a smaller canonical model. This machinery lives alongside the original flat `FIELD_KEYS` list in `extraction/fields.py`. Which representation does downstream consumption actually use, and which is the one meant to survive into production? Also related: `extraction/cli.py` lines 268-273 leave `_deduplicate_same_page_outputs()` commented out with a `TEMP TEST: keep all outputs until page_key mapping is validated` note -- who owns validating that mapping, and what does "validated" mean in concrete terms?

**Why is `gui_app.py` a Tkinter app while `edge-agent/` is PyQt6?**
Two desktop UIs in the same repo use two different toolkits. `gui_app.py` is standalone Tkinter; the edge-agent under `edge-agent/ui/` is PyQt6 + qt-material. Was the Tkinter version meant to be replaced, is it a simpler fallback for users who can't install Qt, or do the two serve different personas (one operator-facing, one developer-facing)? If the Tkinter one is deprecated, new work probably shouldn't extend it.

## Business Logic

**What exactly does the ground truth `mnt/data/dati.csv` look like, and who maintains it?**
`extraction/evaluation.py` line 33 and `extraction/config.py` line 9 both point at `mnt/data/dati.csv`, but `/mnt` is gitignored (`.gitignore` line for `/mnt`) and the file isn't in the working tree. The loader in `load_ground_truth()` (`extraction/evaluation.py` lines 33-56) accepts several variant column names (`Screenshot`/`Fotogramma`/`Screen`, `Valore rilevato`/`Valore`, `Denominazione da attribuire`/`Campo`), which suggests the schema has drifted. Who owns the canonical version of that CSV, where is it stored, and which variant of the column names is authoritative right now?

**What is the exact meaning of the 9 BPER screens, and do they correspond 1:1 with the 4 canonical pages?**
The repo references "screen 1" through "screen 9" (e.g. `mnt/data/screen 1.png`, prototypes in `edge-agent/assets/templates/bper/`), while `extraction/page_definitions.py` defines only 4 canonical pages and `edge-agent/assets/templates/bper/prompts.json` defines 5 page types for the router. Are multiple screens merged into one canonical page (which is what the commented-out dedup logic in `extraction/cli.py` implies), and if so, what is the exact mapping? Someone validating extraction output on real data needs this translation table in writing.

**What is the operator supposed to do when the pipeline returns `_status: ANCHOR_UNCERTAIN`?**
`extraction/pipeline.py` emits this status when both anchor values are null and `STOP_ON_ANCHOR_UNCERTAIN=1`. Is this a hard failure that demands manual intervention, a soft warning to retry with a different screenshot, or a signal that the screen isn't a valid BPER page at all? The default is 0 (don't stop) per `extraction/config.py` line 51, but the `.env.example` line 30 comment suggests this is a deliberate knob. What's the intended production setting?

**Why does `normalize_tipo()` hard-code "mutui spesa" -> "BPI Mutui"?**
`extraction/normalization.py` lines 10-23 contains a single three-entry `TIPO_MAPPING` table that rewrites "mutui spesa"/"mutuo spesa"/"bpi mutui" to the canonical "BPI Mutui". Is this a temporary fix for a model quirk, the first entry in what should become a general synonym table, or a product-level rule that came from a stakeholder? A new developer won't know whether to add more entries here or to push back on the concept.

**What does the tooltip-based coherence check in the pipeline do, and when is it supposed to fire?**
`extraction/fields.py` lines 28-32 and 74-78 define five `tooltip_*` fields (e.g. `tooltip_descrizione_bmb`, `tooltip_evidenze_b`), and the context brief mentions a step 7 "Coherence check: tooltip-based corrections" in the pipeline. Which business rule dictates that a tooltip should override a field value, and are these tooltips page-specific or global? If a tooltip disagrees with the main extracted value, which one wins and why?

**Are the retry area crops (HEADER/BODY/FOOTER) tuned to a specific BPER page layout, or are they generic enough for all 9 screens?**
`extraction/config.py` lines 59-78 fixes three retry regions with hard-coded relative coordinates (`HEADER = (0.00, 0.00, 1.00, 0.35)`, `BODY = (0.00, 0.25, 1.00, 0.75)`, `FOOTER = (0.00, 0.65, 1.00, 1.00)`) and a static `AREA_TO_FIELDS` map. These overlap in the 0.25-0.35 and 0.65-0.75 bands. Was this tuned against one screen and just works for the rest, or was each region validated against every page? If you change one of those numbers, what test should you run?

## Infrastructure

**The committed OpenAI API key in `edge-agent/config.ini` line 23 -- is it live, already rotated, or a decoy?**
`edge-agent/config.ini` line 23 contains `api_key = REDACTED_OPENAI_API_KEY`, and the file is tracked in git. This should be the first thing the team confirms: has the key been revoked, and what is the plan to move edge-agent secrets out of `config.ini` (for example by deferring to `.env` the same way the extraction package does)? Until this is answered, nobody should assume the key is safe.

**What is the deployment target for the edge-agent, and who runs the extraction CLI?**
There is no Dockerfile, no systemd unit, no Windows service wrapper. `README.md` documents a PyInstaller recipe for `gui_app.py` but not for the edge-agent. Is the edge-agent meant to be distributed as a bundled executable, as a Python source drop on operator machines, or is it only a developer tool? And for the CLI, is the intended runner a developer laptop, a scheduled job, or an ops machine with access to `mnt/data/`?

**What are `localhost:8081` and `localhost:9000` referenced in `edge-agent/config.ini`?**
`edge-agent/config.ini` line 10 points `[api] base_url` at `http://localhost:8081` and lines 13-16 configure a full MinIO section (`http://localhost:9000`, bucket `edge-agent-frames`). But `bper_capture_worker.py` line 713 has `_maybe_upload_dataset()` stubbed to `return`, and no code currently posts to port 8081. Was there a SaaS backend these talked to that got ripped out (line 710 comment: "Rimossa logica di upload remoto (SaaS/Sauron) per consolidamento locale"), and if so, is the plan to bring it back or to delete the dead config?

**How is the DINOv2 model downloaded in a sandboxed or offline environment?**
`edge-agent/page_classifier.py` uses `torch.hub.load` to fetch `dinov2_vits14` on first run. Does the production or customer environment have outbound access to Facebook's torch hub CDN, or is the model expected to be pre-cached? If pre-cached, where does the team host it, and what's the expected size/location on disk?

**What's the release artifact?**
The `.gitignore` excludes `build/` and `dist/` but no artifact pipeline is committed. Is the team producing `.exe` bundles from `gui_app.py` manually, are there binary releases hosted somewhere (GitHub Releases, S3, internal file share), and who owns rebuilding them when the code changes?

## Process

**Which branch is the one new features land on: `develop` or `master`?**
`git status` shows the working tree on `develop`. Recent commits include a merge from `bug-fix/improove_accuracy` into `develop`. Is `master` a protected release branch that lags behind `develop`, or is it effectively dead? Should a new developer branch from `develop` for every change, and what is the code review / merge process?

**How does the team test changes without a test suite?**
`CLAUDE.md` explicitly states no tests exist, and there are no `tests/` or `test_*.py` files. The accuracy evaluator (`extraction/evaluation.py`) uses `mnt/data/dati.csv` as a ground truth, but that CSV isn't committed. Is the current workflow "run `python main.py` against a known set of screens and eyeball the accuracy numbers," and if so, who keeps the reference screens and expected outputs? More importantly, what is the smoke test a new developer should run after their first change to prove they haven't broken anything?

**Are there coding conventions beyond what's in the code itself?**
There's no `.editorconfig`, no `pyproject.toml` with `[tool.black]`, no `ruff.toml`, no pre-commit hooks. The repo mixes English and Italian in docstrings, comments, and even variable names (`extraction/prompts.py` is in Italian, `bper_capture_worker.py` comments are in Italian, Python keywords/identifiers are in English). Is the convention "Italian for user-facing and domain strings, English for code," or is this just inconsistent? A newcomer will need to pick sides when adding their first file.

**Who reviews changes, and what counts as "done"?**
The recent merged PR (`#2` from `bug-fix/improove_accuracy`) shows the team uses GitHub PRs, but there's no `CODEOWNERS`, no PR template, and no CI. What does a reviewer look for? Are manual accuracy metrics expected in the PR description?

## Technical Debt

**The commented-out dedup block in `extraction/cli.py` lines 268-273: is it supposed to come back, and when?**
The code ships with `# TEMP TEST: keep all outputs until page_key mapping is validated` followed by the three commented-out lines that would call `_deduplicate_same_page_outputs()`. The helper itself is fully implemented (lines 92-152) with log messages and four different fallback strategies. Who owns turning this back on, and what work blocks it? Is there a ticket?

**`boto3` and `keyboard` in `requirements.txt` with no current usage -- safe to remove?**
`requirements.txt` lines 15-16 pin `boto3>=1.35.0` and `keyboard==0.13.5`. A grep across the codebase (other than the no-op `_maybe_upload_dataset()` stub at `edge-agent/workers/capture/bper_capture_worker.py` line 713) turns up no calls. `boto3` is presumably for the MinIO path that got ripped out; `keyboard` is pinned to an exact old version with no caller at all. Can these be dropped, or is something planned that needs them?

**`PARALLEL_WORKERS` default says 12 in code but 4 in docs -- which is correct?**
`extraction/config.py` line 11 reads `int(os.getenv("PARALLEL_WORKERS", "12"))` but `.env.example` line 20 writes `PARALLEL_WORKERS=4` and `CLAUDE.md` also says 4. Was the code default bumped without updating the docs, or did somebody change the code default accidentally? This matters because 12 concurrent VLM calls will burn through the OpenAI rate limit on a small account faster than a newcomer expects.

**`LLM_THINKING_LEVEL` has a dead `medium` default in `extraction/config.py` -- should the constant be removed?**
`extraction/config.py` line 20 reads `os.getenv("LLM_THINKING_LEVEL", "medium")` into a module constant, but nothing imports or uses that constant. The actual gate lives in `extraction/llm_factory.py` line 72, which reads `os.getenv("LLM_THINKING_LEVEL", "")` with an empty default and only applies the value when the model name contains "thinking". So functionally the behaviour matches `.env.example` ("commented out -> off"), but the dead line in `config.py` is confusing and should probably be deleted or re-wired. Which is the intended contract: "default medium when unset" (currently documented) or "off when unset" (currently implemented)?

**Is `prompts_immagini.txt` still live content, or a leftover artifact?**
`prompts_immagini.txt` sits at the repo root. The context brief marks it as "Reference only: image generation prompts (not used)." Should it be moved under `docs/`, deleted, or is it actually referenced from a script a grep missed? Leaving it at the top level suggests it matters.

**`edge-agent/workers/capture/bper_capture_worker.py` expects a `Guida pagine ITA .xlsx` that isn't committed.**
Lines 253-284 of that file load page ordering from an Excel workbook at `edge-agent/assets/templates/bper/Guida pagine ITA .xlsx`, with a fallback to `prompts.json` when the file is missing. The Excel isn't in the repo. Is this file meant to live in the repo (and was just forgotten), is it distributed separately to operators, or is the Excel path dead code that should be deleted in favor of `prompts.json` alone?

**The `# TEMP TEST` marker is the only hint of a page_key validation campaign. What other in-flight work is there?**
When you find `TEMP TEST`, `FIXME`, `TODO`, or `# noqa: BLE001` sprinkled around (`bper_capture_worker.py` uses `noqa: BLE001` in several places to silence "blind except" warnings, for instance), it's worth asking the team which of these are near-term intentions and which have been marinating for months. Is there a list of POC-to-production work items somewhere outside the code?

## Cross-references

- [Architecture](04-architecture.md) for the layer diagram these questions circle around
- [Tech Stack](03-tech-stack.md) for dependency details (especially `boto3`, `keyboard`, `streamlit`)
- [Workflows](05-workflows.md) for the batch, edge-agent, and multi-pass pipeline sequences
- [Getting Started](07-getting-started.md) for the setup steps that assume many of these questions have been answered
