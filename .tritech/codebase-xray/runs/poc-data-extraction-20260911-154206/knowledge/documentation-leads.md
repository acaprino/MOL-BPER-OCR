# Documentation Leads

> Leads, not truth. Every row points to where the project claims a concept lives.
> Status is documented or unverified. No row is verified; semantic source verification has not begun.

| Concept / symbol | Document | Anchor | Status |
|---|---|---|---|
| Pipeline stages and anchor confidence | docs/how-it-works.md:7 | Multi-pass extraction pipeline | documented |
| Shared CLI and Tkinter batch runner | docs/how-it-works.md:54 | Three run modes | documented |
| Capture, normalization, preprocessing and extraction | docs/how-it-works.md:70 | Edge-agent capture flow | documented |
| Architecture and dependency boundaries | docs/04-architecture.md:5 | Diagramma dei componenti | documented |
| Configuration import order and providers | docs/04-architecture.md:121 | Layer di configurazione | documented |
| Model factory and VLM boundary | docs/04-architecture.md:143 | Layer LLM | documented |
| Image entry points and crops | docs/04-architecture.md:136 | Layer delle immagini | documented |
| Ground-truth evaluation and costs | docs/05-workflows.md:145 | Valutazione dell'accuratezza | documented |
| Batch concurrency and errors | docs/05-workflows.md:93 | Estrazione batch da CLI | documented |
| Page routing | docs/05-workflows.md:279 | Routing di pagina (edge-agent) | documented |
| Background work and lifecycle | docs/05-workflows.md:319 | Processi in background | documented |
| Result dictionary and metadata | docs/06-data-model.md:78 | Il dict risultato | documented |
| FieldResult and dynamic fields | docs/06-data-model.md:109 | FieldResult e FieldsModel | documented |
| Nested subjects, credit and guarantees | docs/06-data-model.md:140 | Soggetto, Fido, Garanzia | documented |
| Structured extraction responses | docs/06-data-model.md:150 | ExtractionResponse e AnchorResponse | documented |
| Canonical field/page mapping | docs/06-data-model.md:169 | Pagina canonica | documented |
| Prompt catalog configuration | docs/10-configuration-guide.md:139 | Modificare i prompt o puntare a un catalogo alternativo | documented |
| Bootstrap and dependency ordering | docs/10-configuration-guide.md:43 | Dipendenze d'ordine che mordono | documented |
| Model pricing and retry budgets | docs/10-configuration-guide.md:186 | Limitare il costo per schermata | documented |
| Provider-aware router credentials | docs/10-configuration-guide.md:220 | Fornire la API key del router dell'edge-agent | documented |
| Windows executable packaging | README.md:106 | Generazione Eseguibile (.exe) | documented |
| Tests and verification conventions | AGENTS.md:122 | Test-Suite Rules | documented |
| Normalized NDG and practice consolidation | docs/superpowers/specs/2026-08-17-edge-agent-excel-export-design.md:93 | 1. `edge-agent/practice_consolidation.py` (nuovo, puro) | documented |
| Spreadsheet string cells and grouped columns | docs/superpowers/specs/2026-08-17-edge-agent-excel-export-design.md:156 | 2. `edge-agent/excel_export.py` (nuovo, puro) | documented |
| Async extraction queue and page registry | docs/superpowers/plans/2026-08-17-edge-agent-async-capture.md:703 | Task 4: Async LocalExtractionClient | documented |
| Process navigation and revisits | processes/README.md:43 | Navigazione: un grafo, non una lista | documented |
| Process catalog versus runtime catalog | processes/README.md:81 | Rapporto con `prompts.json` | documented |
| Frame reframing and window coordinates | docs/adr/0001-normalizzazione-inquadratura-frame.md:48 | Decisione | documented |
| Classifier ROI and centered cosine | docs/adr/0002-riconoscimento-pagina-roi-e-coseno-centrato.md:42 | Decisione | documented |
| Prototype cache geometry | docs/adr/0003-chiave-cache-prototipi-con-geometria.md:33 | Decisione | documented |
| Area-derived retry budget | docs/adr/0004-budget-retry-derivato-dalle-aree.md:33 | Decisione | documented |
| Superseded ML router default | docs/adr/0005-router-ml-invece-di-router-llm.md:36 | Decisione | documented |
| Shipped LLM router default | docs/adr/0006-router-llm-come-predefinito.md:44 | Decisione | documented |
| Stable unchanged-frame confirmation | docs/adr/0007-conferma-stabilita-su-frame-invariato.md:35 | Decisione | documented |
| Live prototypes and rejection classes | docs/adr/0008-classificatore-locale-prototipi-reali-e-classi-di-scarto.md:84 | Decisione | documented |
| Superseded calibration-only content crop | docs/adr/0009-ritaglio-contenuto-solo-su-inquadratura-calibrata.md:29 | Decisione | documented |
| Path and family authorized content crop | docs/adr/0010-ritaglio-autorizzato-dal-percorso-e-dalla-famiglia.md:37 | Decisione | documented |
| Deferred tooltip prototypes | docs/adr/0011-prototipi-tooltip-rimandati-purezza-di-popolazione.md:44 | Decisione | documented |
| Entirely live prototype population | docs/adr/0012-prototipi-interamente-nella-popolazione-live.md:74 | Decisione | documented |
| Known domain and design uncertainties | docs/08-open-questions.md:29 | Logica di business | documented |

## Concepts in scope with no lead

- Per-tool behavior under tools/: discover each utility from its own source and then search its name in ADRs and narrative documents. No dedicated tools index was found. Status: unverified.
- The absent generated .codebase-map/ context cannot establish any lead beyond the references in AGENTS.md and CLAUDE.md. Status: unverified.
