# Interconnect Map

> Prodotto da `semantic-interconnect-mapper` il 2026-09-11. Output: `.codebase-xray/runs/poc-data-extraction-20260911-154206/08-interconnect-map.md`. Contesto primario: `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/`. Scope: cross-partition surface.

> **Status: fallible hypothesis index, not ground truth.** Ogni riga è un'affermazione di un osservatore. Le affermazioni `documented`, `unverified` e `disputed` richiedono una derivazione indipendente prima di diventare premesse di un finding. Una riga assente non dimostra assenza di rischio.

## Target scope

- **Files analyzed:** 0 sorgenti cross-partition; lettura delle sezioni pertinenti dei sei report consegnati e dello stato del run. La mappa delle partizioni contiene soltanto `root`, con 70 file Python e l'intero repository come percorso — `.codebase-xray/runs/poc-data-extraction-20260911-154206/state.json:19` — **status: documented**.
- **Top-level entry points:** nessun ingresso fra partizioni. Gli ingressi applicativi interni sono indicizzati nel report di struttura — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/01-structure.md:154` — **status: documented**.
- **X-ray mode:** `full`, `critical=false`, `comments=false` — `.codebase-xray/runs/poc-data-extraction-20260911-154206/state.json:6` — **status: documented**.
- **Partition map:** `extraction/`, `edge-agent/`, `tools/` e `tests/` sono sottosistemi di `root`, non partizioni distinte — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/01-structure.md:5`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/state.json:29` — **status: documented**.

## Call Graph (expanded, 2-3 hops)

| Exported symbol | Declared at | External callers | External callees | Status |
|-----------------|-------------|------------------|------------------|--------|

*(Nessun arco fra partizioni da espandere.)* Le sezioni di uscita e ingresso dichiarano lo stesso perimetro vuoto; le dipendenze di libreria non costituiscono partizioni sorelle — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/01-structure.md:152`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/02-interfaces.md:475` — **status: documented**.

## Contracts

### Formal

*(Nessun contratto formale fra partizioni identificato.)* Non esistono consumer di altre partizioni nel perimetro assegnato — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/02-interfaces.md:475` — **status: documented**.

### Structural

*(Nessun contratto strutturale fra partizioni identificato.)* Le connessioni del grafo rimangono interne a `root` — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/01-structure.md:100` — **status: documented**.

### Implicit (review priority)

*(Nessun contratto implicito fra partizioni identificato.)* La sezione `Hidden Contracts` delimita esplicitamente i propri contratti ai sottosistemi interni — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/04-semantics.md:156` — **status: documented**.

## Invariants

| Invariant | Scope | Source | Enforcement | Status |
|-----------|-------|--------|-------------|--------|

*(Nessun invariante fra partizioni identificato.)* Il run assegna tutto il repository a una sola partizione; questa sezione non riclassifica gli invarianti interni come confini fra partizioni — `.codebase-xray/runs/poc-data-extraction-20260911-154206/state.json:19`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/04-semantics.md:156` — **status: documented**.

## Domain Rules

*(Nessuna regola di dominio da riconciliare fra partizioni.)* La partizione unica contiene l'intero inventario; il contesto semantico interno è nel report della partizione — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/01-structure.md:5`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/04-semantics.md:5` — **status: documented**.

## Assumptions

| Assumption | Status | Evidence |
|------------|--------|----------|

*(Nessuna assunzione fra partizioni identificata.)* Le assunzioni dei sottosistemi sono già raccolte nel report semantico dell'unica partizione — `.codebase-xray/runs/poc-data-extraction-20260911-154206/state.json:19`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/04-semantics.md:139` — **status: documented**.

## Integration Hot-Spots

| Type | Location | Direction | Risk class | Notes | Status |
|------|----------|-----------|------------|-------|--------|

*(Nessun punto di integrazione fra partizioni.)* Il report dei rischi distingue esplicitamente le integrazioni interne da un'attribuzione cross-partition, che risulta vuota — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/05-risks.md:58` — **status: documented**.

## Change Impact Radius

- **Callers affected:** nessun chiamante di una partizione sorella; i consumer interni rimangono nel report delle interfacce — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/02-interfaces.md:475` — **status: documented**.
- **Tests encoding contract:** nessun contratto fra partizioni da associare a test; `tests/` appartiene alla stessa partizione del codice applicativo — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/01-structure.md:5` — **status: documented**.
- **Persisted data shape dependencies:** nessuna dipendenza da riconciliare fra partizioni; i contratti interni di dati e workbook sono indicizzati nel report delle interfacce — `.codebase-xray/runs/poc-data-extraction-20260911-154206/state.json:19`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/02-interfaces.md:445` — **status: documented**.
- **Downstream services:** nessuna partizione downstream; le dipendenze esterne sono trattate separatamente e non vengono trasformate in partizioni — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/01-structure.md:152`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/02-interfaces.md:453` — **status: documented**.

## Reviewer Hints

> Il perimetro cross-partition vuoto non implica assenza di rischio d'integrazione: il report dei rischi attribuisce i collegamenti UI/cattura/client/pipeline/configurazione a `root` — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/05-risks.md:58` — **status: documented**.

I rimandi seguenti sono indici di contesto interno, non nuove valutazioni o raccomandazioni sul codice.

- **security-auditor:** `Red Flags`, `Side Effects` e dipendenze esterne — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/05-risks.md:16`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/03-flows.md:90`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/02-interfaces.md:453` — **status: documented**.
- **code-auditor:** contratti delle interfacce e `Hidden Contracts` — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/02-interfaces.md:367`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/04-semantics.md:154` — **status: documented**.
- **logic-integrity-auditor:** `Embedded Assumptions`, `Hidden Contracts` e decisioni di dominio — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/04-semantics.md:139`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/04-semantics.md:154`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/04-semantics.md:53` — **status: documented**.
- **distributed-flow-auditor:** flussi ed errori interni, con le sequenze della `Failure Mode Analysis` — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/03-flows.md:68`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/03-flows.md:78`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/05-risks.md:41` — **status: documented**.
- **chicken-egg-detector:** avvio/configurazione e assunzioni di inizializzazione — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/03-flows.md:7`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/04-semantics.md:158` — **status: documented**.
- **ui-race-auditor:** contratti di concorrenza/segnali Qt e flusso di acquisizione/coda/chiusura — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/02-interfaces.md:432`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/03-flows.md:45` — **status: documented**.
- **api-contract-auditor:** contratti interni, workbook e divergenze documentali — `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/02-interfaces.md:367`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/02-interfaces.md:445`; `.codebase-xray/runs/poc-data-extraction-20260911-154206/partitions/root/06-documentation.md:7` — **status: documented**.
