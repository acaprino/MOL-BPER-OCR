# Documentation Leads

These are discovery leads, not verified technical claims.

| Concept / symbol | Document | Heading | Status |
|---|---|---|---|
| Shared engine and interfaces | docs/04-architecture.md | Diagramma dei componenti; Layer / moduli | documented |
| Anchor, main, retry | docs/05-workflows.md | Pipeline di estrazione multi-pass | documented |
| Capture acknowledgement and visit | docs/05-workflows.md; docs/adr/0014-acquisizione-per-visita-con-esito.md | Accodamento, esito e nuovo tentativo | documented |
| Capture result ordering | docs/06-data-model.md; docs/adr/0013-risultati-nell-ordine-di-acquisizione.md | Ordine di acquisizione e disponibilità dei risultati | documented |
| Manual command queue | docs/05-workflows.md; docs/adr/0015-scatto-manuale-nel-thread-di-cattura.md | Scatto manuale e arresto | documented |
| NDG consolidation and Excel | docs/06-data-model.md | Una riga per pratica: PracticeRecord; Excel: colonne e valori | documented |
| Batch and client public contracts | docs/12-python-api.md | Batch di file; Client asincrono dell'edge-agent | documented |
| Bootstrap and portable build | docs/07-getting-started.md | Setup; Creare il pacchetto portable Windows | documented |
| Provider and router configuration | docs/10-configuration-guide.md | Environment and INI configuration | documented |
| Geometry and prototypes | docs/adr/README.md | ADR 0001–0012 | documented |
| Known constraints | docs/08-open-questions.md; AGENTS.md | Domande aperte; Architectural Constraints | documented |

## Concepts in scope with no lead
DINOv3 benchmark tooling has no dedicated official chapter; discover its implementation independently in tools/benchmark_backbones.py.
