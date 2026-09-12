# Interconnect Map

> Prodotto da `semantic-interconnect-mapper` il 2026-09-12. Output: `.codebase-xray/runs/poc-data-extraction-20260912-175144/08-interconnect-map.md`. Contesto primario: [partitions/root](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/01-structure.md). Ambito: cross-partition surface.

> **Status: fallible hypothesis index, not ground truth.** Ogni riga è una dichiarazione di un osservatore. Le dichiarazioni `documented`, `unverified` e `disputed` richiedono derivazione indipendente prima di fondare un rilievo. Una riga assente non dimostra assenza di problemi.

## Target scope

- **documented** — Partizione unica `root`, 71 moduli Python; superficie tra partizioni: zero file e zero archi. Fonte: [.codebase-xray/runs/poc-data-extraction-20260912-175144/state.json:22](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/state.json:22); inventario: [01-structure.md:5](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/01-structure.md:5).
- **verified** — Punti d'ingresso applicativi, interni a `root`: blocco principale [main.py:7](D:/Projects/poc-data-extraction/main.py:7), `gui_app.py::App` avviata da [gui_app.py:401](D:/Projects/poc-data-extraction/gui_app.py:401), `edge-agent/edge_agent.py::main` in [edge-agent/edge_agent.py:38](D:/Projects/poc-data-extraction/edge-agent/edge_agent.py:38).
- **documented** — Modalità X-ray `full`, revisione `f8f57e6124e0`, working tree documentale non committato incluso: [.codebase-xray/runs/poc-data-extraction-20260912-175144/state.json:6](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/state.json:6), [01-structure.md:3](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/01-structure.md:3).
- Sono stati consultati soltanto i rapporti 01–04 della partizione corrente, lo stato del run e i punti d'ingresso citati. Nessun test, provider o sessione GUI eseguito da questo mapper.

## Call Graph (expanded, 2-3 hops)

*(Nessun arco tra partizioni da espandere.)*

**documented** — L'assenza di partizioni sorelle è esplicita in [01-structure.md:644](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/01-structure.md:644) e [02-interfaces.md:713](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/02-interfaces.md:713). Gli import interni restano nel [Dependency Graph](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/01-structure.md#dependency-graph).

## Contracts

### Formal

*(Nessun contratto formale tra partizioni.)*

Per le API e gli schemi interni consultare [02-interfaces.md — Contracts](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/02-interfaces.md#contracts).

### Structural

*(Nessun contratto strutturale tra partizioni.)*

Le convenzioni di ritorno e i consumatori interni sono nel [catalogo delle API](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/02-interfaces.md#public-apis).

### Implicit (review priority)

*(Nessun contratto implicito tra partizioni.)*

Gli accordi interni sono in [04-semantics.md — Hidden Contracts](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/04-semantics.md#hidden-contracts); i relativi percorsi sono in [03-flows.md — Critical Paths](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/03-flows.md#critical-paths).

## Invariants

*(Nessun invariante tra partizioni.)*

Per gli invarianti interni usare [Hidden Contracts](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/04-semantics.md#hidden-contracts) e [Data Flow](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/03-flows.md#data-flow), mantenendo stato ed evidenza di ogni dichiarazione originale.

## Domain Rules

*(Nessuna regola di dominio tra partizioni.)*

Le decisioni interne sono in [04-semantics.md — Design Decisions](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/04-semantics.md#design-decisions).

## Assumptions

*(Nessuna assunzione aggiuntiva su un confine tra partizioni.)*

Le assunzioni interne non garantite e le dichiarazioni contraddette rimangono in [04-semantics.md — Embedded Assumptions](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/04-semantics.md#embedded-assumptions). Questo indice non ne modifica gli stati.

## Integration Hot-Spots

*(Nessun punto di integrazione tra partizioni.)*

I confini con SDK, filesystem, configurazione e servizi esterni appartengono alla partizione `root`; per la loro analisi usare [02-interfaces.md — External Dependencies](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/02-interfaces.md#external-dependencies) e [03-flows.md — Side Effects](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/03-flows.md#side-effects). È un rimando di ambito, non un giudizio sulla sicurezza di tali confini.

## Change Impact Radius

- **Callers affected:** nessun chiamante in una partizione sorella; riferimento di ambito [02-interfaces.md:713](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/02-interfaces.md:713), **status: documented**.
- **Tests encoding contract:** nessun contratto tra partizioni; inventario interno in [01-structure.md — File Inventory](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/01-structure.md#file-inventory).
- **Persisted data shape dependencies:** nessuna dipendenza tra partizioni; formati interni nel [catalogo dei contratti](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/02-interfaces.md#contracts).
- **Downstream services:** nessuna partizione downstream; confini esterni nel [catalogo delle dipendenze](D:/Projects/poc-data-extraction/.codebase-xray/runs/poc-data-extraction-20260912-175144/partitions/root/02-interfaces.md#external-dependencies).

## Reviewer Hints

> Le sezioni vuote delimitano il compito del mapper. Per analizzare `root`, seguire i rimandi ai rapporti della partizione e verificarne le premesse sul codice.

- **security-auditor**: `## Integration Hot-Spots`, `## Assumptions`.
- **code-auditor**: `## Invariants`, `## Contracts`.
- **logic-integrity-auditor**: `## Contracts`, `## Invariants`, `## Assumptions`, `## Domain Rules`.
- **distributed-flow-auditor**: `## Integration Hot-Spots`, `## Call Graph (expanded, 2-3 hops)`.
- **chicken-egg-detector**: `## Assumptions`, `## Integration Hot-Spots`.
- **ui-race-auditor**: `## Invariants`, `## Integration Hot-Spots`.
- **api-contract-auditor**: `## Contracts`, `## Change Impact Radius`.
