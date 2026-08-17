# Edge-Agent Excel Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the edge-agent's three technical CSV exports with a single formatted Excel export whose rows are consolidated banking practices, and move all diagnostic data to the log.

**Architecture:** Two new pure modules under `edge-agent/` — `practice_consolidation.py` groups captured frames by NDG and merges their fields with the existing `pick_best()`, and `excel_export.py` writes a formatted openpyxl workbook with a two-level header. `DataTableTab` is rewritten on top of them, the diagnostic `ExtractionResultsTab` is deleted, and `LocalExtractionClient` logs per-frame diagnostics instead of exporting CSV.

**Tech Stack:** Python 3.13, openpyxl 3.1.5, PyQt6, pytest. No pandas in the new code.

**Spec:** `docs/superpowers/specs/2026-08-17-edge-agent-excel-export-design.md`

## Global Constraints

- **Run everything in the venv.** The system Python has neither PyQt6 nor LangChain. Use `.venv/Scripts/python.exe -m pytest tests -q`. Baseline before starting: 60 passed.
- **Commit authorship:** never credit Claude or any AI assistant in a commit — no `Co-Authored-By:`, no "Generated with", no AI mention in subject, body or footer.
- **Language policy:** English for code, identifiers, comments and commit messages. Italian for UI strings and field keys. Never translate the Italian schema keys.
- **Type annotations:** every function annotates all parameters and the return type.
- **Section markers:** delimit code sections with `# ============================================================`.
- **Naming:** constants `UPPER_SNAKE_CASE`, private helpers `_leading_underscore`, dataclasses `PascalCase`.
- **Formula neutralization in xlsx:** always `cell.data_type = "s"` after assigning a value. Never `escape_csv_formula()` — that is the CSV convention and leaves a visible apostrophe, and it also prefixes `-` and `+`, corrupting negative amounts.
- **Column order:** `ndg` and `denominazione` pinned first, then the remaining 43 sorted by `(PAGE_SHEET_ORDER.index(page_key), display_name, schema_key)`.
- **Canonical page order:** `("risultato_ricerca", "elenco_soggetti", "gestione_fidi_e_garanzie", "note_da_richiesta")` from `extraction/page_definitions.py`.

## File Structure

| File | Responsibility |
|---|---|
| `edge-agent/practice_consolidation.py` (new) | `PracticeRecord`, `consolidate()`. Groups frames by NDG, merges fields. No Qt, no openpyxl. |
| `edge-agent/excel_export.py` (new) | `ColumnSpec`, `build_columns()`, `write_workbook()`, `export_results()`. No Qt. |
| `edge-agent/ui/data_table_tab.py` (rewrite) | Practice rows, page band via `setSpan()`, single Excel button. |
| `edge-agent/ui/capture_tab.py` (modify) | Export button retargeted to `export_results()`. |
| `edge-agent/ui/main_window.py` (modify) | Two tabs; fix the hardcoded tab index. |
| `edge-agent/ui/__init__.py` (modify) | Drop the `ExtractionResultsTab` re-export. |
| `edge-agent/ui/extraction_results_tab.py` (delete) | Diagnostic tab, replaced by the log. |
| `edge-agent/local_extraction_client.py` (modify) | Drop `export_csv()`, add per-frame diagnostic logging. |
| `tests/test_practice_consolidation.py` (new) | Grouping, fallback, merge, ordering. |
| `tests/test_excel_export.py` (new) | Header structure, freeze, autofilter, formula inertness. |

---

### Task 1: Practice consolidation module

**Files:**
- Create: `edge-agent/practice_consolidation.py`
- Test: `tests/test_practice_consolidation.py`

**Interfaces:**
- Consumes: `pick_best`, `safe_field`, `is_nullish` from `extraction.normalization`; `FIELD_KEYS` from `extraction.fields`.
- Produces: `PracticeRecord(ndg, denominazione, fields, source_pages, frame_count)`, `normalize_ndg(value) -> Optional[str]` and `consolidate(results) -> List[PracticeRecord]`. Task 2 and Task 3 both depend on these exact names.

**Do not reuse `norm_number_str()` for the NDG.** It is a quantity normalizer: verified,
it turns `12.345` into `12.35` and `12345/A` into `12345.00`. The first splits one
practice into two rows, the second silently merges two distinct practices. `normalize_ndg()`
below is an identifier normalizer and is deliberately local to this module.

- [ ] **Step 1: Write the failing test**

Create `tests/test_practice_consolidation.py`:

```python
"""Tests for edge-agent/practice_consolidation.py (frame -> practice grouping)."""

from typing import Any, Dict, Optional

from practice_consolidation import PracticeRecord, consolidate, normalize_ndg


def _frame(
    ndg: Optional[str],
    page_type: str = "Risultato ricerca",
    **fields: Any,
) -> Dict[str, Any]:
    """Build a minimal pipeline result: {key: (value, confidence)} in **fields."""
    payload: Dict[str, Any] = {}
    if ndg is not None:
        payload["ndg"] = {"value": ndg, "confidence": 1.0}
    for key, spec in fields.items():
        value, confidence = spec
        payload[key] = {"value": value, "confidence": confidence}
    return {"fields": payload, "_page_type": page_type, "_status": "OK"}


def test_normalize_ndg_ignores_separators_and_leading_zeros() -> None:
    assert normalize_ndg("12345") == "12345"
    assert normalize_ndg("12.345") == "12345"
    assert normalize_ndg("12 345") == "12345"
    assert normalize_ndg("0012345") == "12345"


def test_normalize_ndg_keeps_a_non_numeric_suffix() -> None:
    # norm_number_str() would drop the suffix and merge this with practice 12345.
    assert normalize_ndg("12345/A") == "12345A"
    assert normalize_ndg("12345/A") != normalize_ndg("12345")


def test_normalize_ndg_returns_none_when_unreadable() -> None:
    assert normalize_ndg(None) is None
    assert normalize_ndg("") is None
    assert normalize_ndg("n/d") is None
    assert normalize_ndg("---") is None


def test_same_ndg_frames_collapse_into_one_record() -> None:
    records = consolidate([
        _frame("12345", tipo=("BPI Mutui", 0.9)),
        _frame("12345", "Elenco Soggetti", ruolo_1=("TITOLARE", 0.9)),
    ])
    assert len(records) == 1
    assert records[0].ndg == "12345"
    assert records[0].frame_count == 2
    assert records[0].fields["tipo"]["value"] == "BPI Mutui"
    assert records[0].fields["ruolo_1"]["value"] == "TITOLARE"


def test_distinct_ndg_produce_records_in_first_appearance_order() -> None:
    records = consolidate([_frame("999"), _frame("111"), _frame("999")])
    assert [r.ndg for r in records] == ["999", "111"]
    assert records[0].frame_count == 2


def test_frame_without_ndg_attaches_to_last_seen_practice() -> None:
    records = consolidate([
        _frame("12345"),
        _frame(None, "Risultato ricerca - Colonne estese", creazione=("01/02/2026", 0.9)),
    ])
    assert len(records) == 1
    assert records[0].fields["creazione"]["value"] == "01/02/2026"


def test_leading_frames_without_ndg_join_the_first_identified_practice() -> None:
    records = consolidate([
        _frame(None, "Risultato ricerca - Tooltip mostrata", evidenze=("B", 0.9)),
        _frame("12345", tipo=("BPI Mutui", 0.9)),
    ])
    assert len(records) == 1
    assert records[0].ndg == "12345"
    assert records[0].fields["evidenze"]["value"] == "B"
    assert records[0].frame_count == 2


def test_session_without_any_readable_ndg_yields_one_anonymous_record() -> None:
    records = consolidate([_frame(None, tipo=("BPI Mutui", 0.9)), _frame(None)])
    assert len(records) == 1
    assert records[0].ndg is None
    assert records[0].fields["tipo"]["value"] == "BPI Mutui"


def test_higher_confidence_wins_on_conflict() -> None:
    records = consolidate([
        _frame("12345", tipo=("SBAGLIATO", 0.4)),
        _frame("12345", tipo=("BPI Mutui", 0.95)),
    ])
    assert records[0].fields["tipo"]["value"] == "BPI Mutui"


def test_non_null_beats_null_even_at_high_confidence() -> None:
    records = consolidate([
        _frame("12345", tipo=(None, 0.99)),
        _frame("12345", tipo=("BPI Mutui", 0.2)),
    ])
    assert records[0].fields["tipo"]["value"] == "BPI Mutui"


def test_ndg_written_in_different_formats_group_together() -> None:
    records = consolidate([_frame("12345"), _frame("12.345")])
    assert len(records) == 1


def test_denominazione_is_exposed_on_the_record() -> None:
    records = consolidate([_frame("12345", denominazione=("ROSSI MARIO", 0.9))])
    assert records[0].denominazione == "ROSSI MARIO"


def test_source_pages_records_every_contributing_frame() -> None:
    records = consolidate([
        _frame("12345", "Risultato ricerca"),
        _frame("12345", "Elenco Soggetti"),
    ])
    assert records[0].source_pages == ("Risultato ricerca", "Elenco Soggetti")


def test_every_canonical_field_is_present_even_when_never_extracted() -> None:
    records = consolidate([_frame("12345")])
    assert len(records[0].fields) == 45
    assert records[0].fields["note_della_richiesta"]["value"] is None


def test_empty_input_yields_no_records() -> None:
    assert consolidate([]) == []


def test_record_is_frozen() -> None:
    record = consolidate([_frame("12345")])[0]
    assert isinstance(record, PracticeRecord)
    try:
        record.ndg = "999"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("PracticeRecord must be frozen")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_practice_consolidation.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'practice_consolidation'`.

- [ ] **Step 3: Write the implementation**

Create `edge-agent/practice_consolidation.py`:

```python
"""Consolidate captured frames into one record per banking practice.

The router recognises 9 screens but they are variants of 4 canonical pages of a
single practice: scrolled tables and open tooltips each carry only 1-6 useful
fields. Presenting one row per frame shows the operator nine mostly-empty rows
for one subject, so frames are grouped by NDG and merged field by field.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import app_paths

_PROJECT_ROOT = str(app_paths.project_root())
if not app_paths.is_frozen() and _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from extraction.fields import FIELD_KEYS
from extraction.normalization import is_nullish, pick_best, safe_field

# ============================================================
# Record
# ============================================================


@dataclass(frozen=True)
class PracticeRecord:
    """One banking practice, merged from every frame that showed it."""

    ndg: Optional[str]
    denominazione: Optional[str]
    fields: Dict[str, Dict[str, Any]]
    source_pages: Tuple[str, ...]
    frame_count: int


# ============================================================
# Consolidation
# ============================================================


class _Group:
    """Mutable accumulator; frozen into a PracticeRecord at the end."""

    def __init__(self, ndg: Optional[str]) -> None:
        self.ndg = ndg
        self.fields: Dict[str, Dict[str, Any]] = {
            key: {"value": None, "confidence": 0.0, "evidence_text": None, "section": None}
            for key in FIELD_KEYS
        }
        self.source_pages: List[str] = []
        self.frame_count = 0

    def absorb(self, result: Dict[str, Any]) -> None:
        raw = result.get("fields") or {}
        for key in FIELD_KEYS:
            # safe_field() returns a fresh dict, so pick_best never aliases the
            # caller's payload and a later frame cannot mutate an earlier choice.
            self.fields[key] = pick_best(self.fields[key], safe_field(raw, key))
        self.source_pages.append(str(result.get("_page_type") or ""))
        self.frame_count += 1

    def to_record(self) -> PracticeRecord:
        denominazione = self.fields["denominazione"]["value"]
        return PracticeRecord(
            ndg=self.ndg,
            denominazione=None if is_nullish(denominazione) else str(denominazione),
            fields=self.fields,
            source_pages=tuple(self.source_pages),
            frame_count=self.frame_count,
        )


def normalize_ndg(value: Any) -> Optional[str]:
    """Group key for an NDG, or None when it was not read.

    Deliberately not norm_number_str(): that is a quantity normalizer and reads
    the dot as a decimal separator, so "12.345" becomes "12.35" (splitting one
    practice in two) and "12345/A" becomes "12345.00" (merging two distinct
    practices). An NDG is an identifier: keep the alphanumerics, uppercase, and
    drop leading zeros only when what remains is all digits.
    """
    if is_nullish(value):
        return None
    cleaned = re.sub(r"[^0-9A-Za-z]", "", str(value)).upper()
    if cleaned.isdigit():
        cleaned = cleaned.lstrip("0") or "0"
    return cleaned or None


def _frame_ndg(result: Dict[str, Any]) -> Optional[str]:
    """Group key of a frame, from its ndg field."""
    return normalize_ndg(((result.get("fields") or {}).get("ndg") or {}).get("value"))


def consolidate(results: Sequence[Dict[str, Any]]) -> List[PracticeRecord]:
    """Group pipeline results into one record per practice.

    NDG is the key. A frame whose NDG was not read attaches to the most recent
    practice; frames arriving before any readable NDG wait in a buffer and join
    the first practice identified. A session that never reads an NDG yields a
    single record with ndg=None.
    """
    groups: Dict[str, _Group] = {}
    order: List[str] = []
    pending: List[Dict[str, Any]] = []
    last_key: Optional[str] = None

    for result in results:
        key = _frame_ndg(result)

        if key is None:
            if last_key is None:
                pending.append(result)
                continue
            groups[last_key].absorb(result)
            continue

        if key not in groups:
            groups[key] = _Group(key)
            order.append(key)

        # The first identified practice adopts everything seen before it.
        for buffered in pending:
            groups[key].absorb(buffered)
        pending.clear()

        groups[key].absorb(result)
        last_key = key

    if pending:
        anonymous = _Group(None)
        for buffered in pending:
            anonymous.absorb(buffered)
        return [anonymous.to_record()]

    return [groups[key].to_record() for key in order]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_practice_consolidation.py -q`
Expected: 16 passed.

- [ ] **Step 5: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: 76 passed (60 baseline + 16).

- [ ] **Step 6: Commit**

```bash
git add edge-agent/practice_consolidation.py tests/test_practice_consolidation.py
git commit -m "Consolidate captured frames into one record per practice"
```

---

### Task 2: Formatted Excel writer

**Files:**
- Create: `edge-agent/excel_export.py`
- Test: `tests/test_excel_export.py`

**Interfaces:**
- Consumes: `PracticeRecord`, `consolidate` from Task 1.
- Produces: `ColumnSpec(schema_key, label, page_key, page_name)`, `build_columns(labels=None) -> List[ColumnSpec]`, `write_workbook(records, columns, path) -> None`, `export_results(results, path, labels=None) -> int` returning the number of practices written. Tasks 3 and 4 both call `export_results()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_excel_export.py`:

```python
"""Tests for edge-agent/excel_export.py (formatted workbook writer)."""

from pathlib import Path
from typing import Any, Dict, Optional

from openpyxl import load_workbook

from excel_export import build_columns, export_results, write_workbook
from practice_consolidation import consolidate


def _frame(ndg: Optional[str], **fields: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if ndg is not None:
        payload["ndg"] = {"value": ndg, "confidence": 1.0}
    for key, spec in fields.items():
        value, confidence = spec
        payload[key] = {"value": value, "confidence": confidence}
    return {"fields": payload, "_page_type": "Risultato ricerca", "_status": "OK"}


def test_ndg_and_denominazione_are_pinned_first() -> None:
    columns = build_columns()
    assert [c.schema_key for c in columns[:2]] == ["ndg", "denominazione"]


def test_all_45_canonical_fields_are_columns() -> None:
    columns = build_columns()
    assert len(columns) == 45
    assert len({c.schema_key for c in columns}) == 45


def test_columns_are_grouped_by_page_without_gaps() -> None:
    seen = []
    for column in build_columns():
        if not seen or seen[-1] != column.page_key:
            seen.append(column.page_key)
    assert seen == [
        "risultato_ricerca",
        "elenco_soggetti",
        "gestione_fidi_e_garanzie",
        "note_da_richiesta",
    ]


def test_user_label_overrides_the_display_name() -> None:
    columns = build_columns({"ndg": "Codice cliente"})
    assert columns[0].label == "Codice cliente"


def test_header_row_one_holds_merged_page_bands(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    write_workbook(consolidate([_frame("12345")]), build_columns(), str(path))
    ws = load_workbook(path).active
    assert ws.cell(row=1, column=1).value == "Risultato ricerca"
    merged = {str(r) for r in ws.merged_cells.ranges}
    assert "A1:I1" in merged  # 9 risultato_ricerca fields


def test_header_row_two_holds_field_labels(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    write_workbook(consolidate([_frame("12345")]), build_columns(), str(path))
    ws = load_workbook(path).active
    assert ws.cell(row=2, column=1).value == "NDG"
    assert ws.cell(row=2, column=2).value == "DENOMINAZIONE"


def test_data_starts_at_row_three_one_row_per_practice(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    records = consolidate([_frame("12345"), _frame("67890")])
    write_workbook(records, build_columns(), str(path))
    ws = load_workbook(path).active
    assert ws.max_row == 4
    # Column 1 holds the ndg *field value* as extracted, not the group key.
    assert ws.cell(row=3, column=1).value == "12345"
    assert ws.cell(row=4, column=1).value == "67890"


def test_panes_are_frozen_below_the_two_header_rows(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    write_workbook(consolidate([_frame("12345")]), build_columns(), str(path))
    assert load_workbook(path).active.freeze_panes == "C3"


def test_autofilter_covers_the_label_row_and_the_data(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    write_workbook(consolidate([_frame("12345")]), build_columns(), str(path))
    ws = load_workbook(path).active
    assert ws.auto_filter.ref == "A2:AS3"


def test_a_value_starting_with_equals_is_inert_text(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    records = consolidate([_frame("12345", tipo=("=1+1", 0.9))])
    columns = build_columns()
    write_workbook(records, columns, str(path))
    ws = load_workbook(path).active
    col = next(i for i, c in enumerate(columns, start=1) if c.schema_key == "tipo")
    cell = ws.cell(row=3, column=col)
    assert cell.data_type == "s"
    assert cell.value == "=1+1"  # preserved verbatim, no apostrophe


def test_a_negative_amount_keeps_its_minus_sign(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    records = consolidate([_frame("12345", importo_euro=("-1.234,00", 0.9))])
    columns = build_columns()
    write_workbook(records, columns, str(path))
    ws = load_workbook(path).active
    col = next(i for i, c in enumerate(columns, start=1) if c.schema_key == "importo_euro")
    assert ws.cell(row=3, column=col).value == "-1.234,00"


def test_unextracted_field_leaves_the_cell_empty(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    columns = build_columns()
    write_workbook(consolidate([_frame("12345")]), columns, str(path))
    ws = load_workbook(path).active
    col = next(i for i, c in enumerate(columns, start=1) if c.schema_key == "fase")
    assert ws.cell(row=3, column=col).value is None


def test_export_results_consolidates_and_returns_the_practice_count(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    written = export_results([_frame("12345"), _frame("12345")], str(path))
    assert written == 1
    assert load_workbook(path).active.max_row == 3


def test_export_results_applies_renamed_labels(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    export_results([_frame("12345")], str(path), labels={"ndg": "Codice cliente"})
    assert load_workbook(path).active.cell(row=2, column=1).value == "Codice cliente"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_excel_export.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'excel_export'`.

- [ ] **Step 3: Write the implementation**

Create `edge-agent/excel_export.py`:

```python
"""Formatted Excel export of consolidated practices.

openpyxl directly rather than pandas: the two-level header needs merged cells
and per-cell styling that df.to_excel() cannot express.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

import app_paths

_PROJECT_ROOT = str(app_paths.project_root())
if not app_paths.is_frozen() and _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from extraction.field_definitions import CANONICAL_FIELD_DEFINITIONS
from extraction.page_definitions import CANONICAL_PAGE_NAMES, PAGE_SHEET_ORDER

from practice_consolidation import PracticeRecord, consolidate

# ============================================================
# Layout constants
# ============================================================

SHEET_TITLE = "Dati Estratti"

# NDG and DENOMINAZIONE must anchor the reading, but the canonical sort orders
# display names by codepoint, which puts "Creazione" first and NDG sixth.
PINNED_KEYS = ("ndg", "denominazione")

PAGE_BAND_COLORS: Dict[str, str] = {
    "risultato_ricerca": "1F4E79",
    "elenco_soggetti": "2E6B4F",
    "gestione_fidi_e_garanzie": "7B3F00",
    "note_da_richiesta": "4A3C8C",
}

LABEL_FILL = "E7E6E6"
ZEBRA_FILL = "F7F9FC"

# Free-text fields wrap instead of stretching the sheet past the screen.
WRAP_KEYS = frozenset({
    "note_della_richiesta",
    "note_scheda_privati",
    "tooltip_descrizione_bmb",
    "tooltip_evidenze_b",
    "tooltip_descrizione_m_consap",
    "tooltip_descrizione_consap_dr_bis",
    "tooltip_descrizione_ipoteca",
})

MIN_WIDTH = 12
MAX_WIDTH = 46
HEADER_ROWS = 2

_THIN = Side(style="thin", color="BFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


# ============================================================
# Columns
# ============================================================


@dataclass(frozen=True)
class ColumnSpec:
    """One spreadsheet column bound to a canonical field."""

    schema_key: str
    label: str
    page_key: str
    page_name: str


def _canonical_sort_key(schema_key: str) -> tuple:
    definition = CANONICAL_FIELD_DEFINITIONS[schema_key]
    return (
        PAGE_SHEET_ORDER.index(definition["page_key"]),
        definition["display_name"],
        schema_key,
    )


def build_columns(labels: Optional[Mapping[str, str]] = None) -> List[ColumnSpec]:
    """All 45 canonical fields, NDG and DENOMINAZIONE first.

    `labels` overrides the canonical display name per schema key; it carries the
    renames the operator made on the Dati Estratti headers.
    """
    labels = labels or {}
    rest = sorted(
        (k for k in CANONICAL_FIELD_DEFINITIONS if k not in PINNED_KEYS),
        key=_canonical_sort_key,
    )

    columns: List[ColumnSpec] = []
    for schema_key in list(PINNED_KEYS) + rest:
        definition = CANONICAL_FIELD_DEFINITIONS[schema_key]
        page_key = definition["page_key"]
        columns.append(
            ColumnSpec(
                schema_key=schema_key,
                label=labels.get(schema_key) or definition["display_name"],
                page_key=page_key,
                page_name=CANONICAL_PAGE_NAMES.get(page_key, page_key),
            )
        )
    return columns


# ============================================================
# Writing
# ============================================================


def _set_text(ws: Worksheet, row: int, col: int, value: Any) -> Any:
    """Write a value as inert text.

    openpyxl types a string starting with "=" as a formula (data_type "f").
    Forcing "s" keeps the value verbatim and stops Excel evaluating it, without
    the leading apostrophe the CSV convention would leave visible.
    """
    cell = ws.cell(row=row, column=col)
    if value is None or str(value).strip() == "":
        cell.value = None
    else:
        cell.value = str(value)
        cell.data_type = "s"
    return cell


def _write_page_bands(ws: Worksheet, columns: Sequence[ColumnSpec]) -> None:
    start = 1
    for index in range(1, len(columns) + 1):
        is_last = index == len(columns)
        changes = not is_last and columns[index].page_key != columns[index - 1].page_key
        if not (is_last or changes):
            continue

        cell = ws.cell(row=1, column=start)
        cell.value = columns[start - 1].page_name
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.fill = PatternFill(
            "solid", start_color=PAGE_BAND_COLORS.get(columns[start - 1].page_key, "555555")
        )
        if index > start:
            ws.merge_cells(start_row=1, start_column=start, end_row=1, end_column=index)
        start = index + 1


def _write_labels(ws: Worksheet, columns: Sequence[ColumnSpec]) -> None:
    fill = PatternFill("solid", start_color=LABEL_FILL)
    for index, column in enumerate(columns, start=1):
        cell = ws.cell(row=2, column=index)
        cell.value = column.label
        cell.font = Font(bold=True)
        cell.fill = fill
        cell.border = _BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _apply_widths(ws: Worksheet, columns: Sequence[ColumnSpec], widths: Sequence[int]) -> None:
    for index, (column, width) in enumerate(zip(columns, widths), start=1):
        capped = max(MIN_WIDTH, min(MAX_WIDTH, width + 2))
        ws.column_dimensions[get_column_letter(index)].width = capped


def write_workbook(
    records: Sequence[PracticeRecord],
    columns: Sequence[ColumnSpec],
    path: str,
) -> None:
    """Write the formatted workbook: page bands, labels, one row per practice."""
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_TITLE

    _write_page_bands(ws, columns)
    _write_labels(ws, columns)

    widths = [len(column.label) for column in columns]
    zebra = PatternFill("solid", start_color=ZEBRA_FILL)

    for row_offset, record in enumerate(records):
        row = HEADER_ROWS + 1 + row_offset
        for col_index, column in enumerate(columns, start=1):
            value = (record.fields.get(column.schema_key) or {}).get("value")
            cell = _set_text(ws, row, col_index, value)
            cell.border = _BORDER
            cell.alignment = Alignment(
                vertical="top", wrap_text=column.schema_key in WRAP_KEYS
            )
            if row_offset % 2 == 1:
                cell.fill = zebra
            if cell.value is not None:
                widths[col_index - 1] = max(widths[col_index - 1], len(str(cell.value)))

    _apply_widths(ws, columns, widths)

    last_column = get_column_letter(len(columns))
    last_row = HEADER_ROWS + max(1, len(records))
    ws.auto_filter.ref = f"A2:{last_column}{last_row}"
    ws.freeze_panes = "C3"

    wb.save(path)


def export_results(
    results: Sequence[Dict[str, Any]],
    path: str,
    labels: Optional[Mapping[str, str]] = None,
) -> int:
    """Consolidate raw pipeline results and write the workbook.

    Single entry point shared by the Cattura and Dati Estratti tabs so the two
    buttons cannot drift apart. Returns the number of practices written.
    """
    records = consolidate(results)
    write_workbook(records, build_columns(labels), path)
    return len(records)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_excel_export.py -q`
Expected: 14 passed.

If `test_autofilter_covers_the_label_row_and_the_data` fails on the range, print the real value with `-vv` and fix the *test* to the produced range only after confirming 45 columns end at `AS` (column 45 = `AS`) and that a single practice ends at row 3.

- [ ] **Step 5: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: 90 passed.

- [ ] **Step 6: Commit**

```bash
git add edge-agent/excel_export.py tests/test_excel_export.py
git commit -m "Write consolidated practices to a formatted workbook"
```

---

### Task 3: Rewrite the Dati Estratti tab

**Files:**
- Modify: `edge-agent/ui/data_table_tab.py` (full rewrite of the body)

**Interfaces:**
- Consumes: `consolidate`, `PracticeRecord` (Task 1); `build_columns`, `export_results` (Task 2).
- Produces: `DataTableTab(extraction_client, parent=None)` with `set_job_id(job_id)` — unchanged constructor and public surface, so `main_window.py` needs no change for this task.

- [ ] **Step 1: Replace the module**

Replace the whole content of `edge-agent/ui/data_table_tab.py`:

```python
"""Tab con vista a spreadsheet delle pratiche estratte."""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from PyQt6 import QtCore
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QHeaderView,
)

import app_paths

_EXTRACTION_ROOT = app_paths.project_root()
if not app_paths.is_frozen() and str(_EXTRACTION_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXTRACTION_ROOT))

from excel_export import ColumnSpec, PAGE_BAND_COLORS, build_columns, export_results
from practice_consolidation import PracticeRecord, consolidate

# ============================================================
# Costanti
# ============================================================

# Riga 0 della tabella: fascia di raggruppamento per pagina canonica.
# QTableWidget non ha intestazioni a due livelli native, quindi la fascia e'
# una riga reale con celle unite via setSpan().
_BAND_ROW = 0
_FIRST_DATA_ROW = 1


# ============================================================
# Tab
# ============================================================


class DataTableTab(QWidget):
    """
    Tab spreadsheet: una riga per pratica, una colonna per campo canonico.

    I frame catturati vengono consolidati per NDG: le 9 schermate del router
    sono varianti di 4 pagine della stessa pratica, quindi una riga per frame
    mostrerebbe la stessa pratica nove volte, quasi sempre vuota.
    """

    def __init__(
        self,
        extraction_client: Any,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._client = extraction_client
        self._current_job_id: Optional[str] = None
        self._records: List[PracticeRecord] = []

        # Rinomina colonne: schema_key -> label utente (sovrascrive display_name)
        self._column_labels: Dict[str, str] = {}
        self._columns: List[ColumnSpec] = build_columns()
        self._selected_col_idx: Optional[int] = None

        self._init_ui()

        try:
            self._client.result_ready.connect(self._on_result_ready)
        except Exception:
            pass

    # ------------------------------------------------------------------ UI setup

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()

        top_row.addWidget(QLabel("Sessione:", self))
        self.job_combo = QComboBox(self)
        self.job_combo.currentTextChanged.connect(self._on_job_changed)
        top_row.addWidget(self.job_combo)

        refresh_btn = QPushButton("🔄 Ricarica", self)
        refresh_btn.clicked.connect(self._refresh)
        top_row.addWidget(refresh_btn)

        self.rename_btn = QPushButton("✏️ Rinomina colonna", self)
        self.rename_btn.setEnabled(False)
        self.rename_btn.setToolTip(
            "Clicca un'intestazione di colonna, poi questo pulsante per rinominarla"
        )
        self.rename_btn.clicked.connect(self._on_rename_column)
        top_row.addWidget(self.rename_btn)

        export_xlsx_btn = QPushButton("⬇️ Esporta Excel", self)
        export_xlsx_btn.clicked.connect(self._on_export_excel)
        top_row.addWidget(export_xlsx_btn)

        top_row.addStretch(1)
        layout.addLayout(top_row)

        self.table = QTableWidget(self)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

        layout.addWidget(self.table)

    # ------------------------------------------------------------------ Slots

    def _on_result_ready(self, job_id: str, _result: dict) -> None:
        if self.job_combo.findText(job_id) == -1:
            self.job_combo.addItem(job_id)
        if self._current_job_id is None:
            self._current_job_id = job_id
            self.job_combo.setCurrentText(job_id)
        if job_id == self._current_job_id:
            self._load_table(job_id)

    def _on_job_changed(self, job_id: str) -> None:
        self._current_job_id = job_id.strip() or None
        if self._current_job_id:
            self._load_table(self._current_job_id)
        else:
            self._clear_table()

    def _refresh(self) -> None:
        try:
            for job_id in self._client.get_all_job_ids():
                if self.job_combo.findText(job_id) == -1:
                    self.job_combo.addItem(job_id)
        except Exception:
            pass
        if self._current_job_id:
            self._load_table(self._current_job_id)

    def _on_header_clicked(self, col_idx: int) -> None:
        self._selected_col_idx = col_idx
        item = self.table.horizontalHeaderItem(col_idx)
        label_text = item.text() if item else "?"
        self.rename_btn.setEnabled(True)
        self.rename_btn.setText(f"✏️ Rinomina: {label_text}")

    def _on_rename_column(self) -> None:
        if self._selected_col_idx is None:
            return
        if not 0 <= self._selected_col_idx < len(self._columns):
            return

        column = self._columns[self._selected_col_idx]

        new_label, ok = QInputDialog.getText(
            self,
            "Rinomina colonna",
            "Nuovo nome per la colonna:",
            text=column.label,
        )
        if not ok or not new_label.strip():
            return

        new_label = new_label.strip()
        self._column_labels[column.schema_key] = new_label
        self._columns = build_columns(self._column_labels)
        self._refresh_headers()
        self.rename_btn.setText(f"✏️ Rinomina: {new_label}")

    # ------------------------------------------------------------------ Table population

    def _clear_table(self) -> None:
        self._records = []
        self.table.clearContents()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

    def _load_table(self, job_id: str) -> None:
        self._records = consolidate(self._client.get_results(job_id))
        if not self._records:
            self._clear_table()
            return

        self.table.clearSpans()
        self.table.setColumnCount(len(self._columns))
        self.table.setRowCount(_FIRST_DATA_ROW + len(self._records))

        self._refresh_headers()
        self._paint_band_row()

        for row_offset, record in enumerate(self._records):
            row = _FIRST_DATA_ROW + row_offset
            for col_idx, column in enumerate(self._columns):
                value = (record.fields.get(column.schema_key) or {}).get("value")
                self._set_cell(row, col_idx, "" if value is None else str(value))

    def _refresh_headers(self) -> None:
        self.table.setHorizontalHeaderLabels([c.label for c in self._columns])
        for col_idx, column in enumerate(self._columns):
            item = self.table.horizontalHeaderItem(col_idx)
            if item:
                item.setToolTip(f"{column.page_name} — {column.schema_key}")

    def _paint_band_row(self) -> None:
        """Riga 0: nome della pagina canonica su celle unite, una per gruppo."""
        start = 0
        for index in range(1, len(self._columns) + 1):
            is_last = index == len(self._columns)
            changes = (
                not is_last
                and self._columns[index].page_key != self._columns[index - 1].page_key
            )
            if not (is_last or changes):
                continue

            column = self._columns[start]
            item = QTableWidgetItem(column.page_name)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            font = QFont()
            font.setBold(True)
            item.setFont(font)
            item.setBackground(
                QBrush(QColor("#" + PAGE_BAND_COLORS.get(column.page_key, "555555")))
            )
            item.setForeground(QBrush(QColor("#FFFFFF")))
            self.table.setItem(_BAND_ROW, start, item)
            if index > start + 1:
                self.table.setSpan(_BAND_ROW, start, 1, index - start)
            start = index

    def _set_cell(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col, item)

    # ------------------------------------------------------------------ Export

    def _on_export_excel(self) -> None:
        job_id = self._current_job_id or self.job_combo.currentText().strip()
        if not job_id or not self._records:
            QMessageBox.warning(
                self, "Esporta Excel", "Nessun dato disponibile da esportare."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Salva Excel", f"dati_{job_id}.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return

        try:
            written = export_results(
                self._client.get_results(job_id), path, labels=self._column_labels
            )
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Errore", f"Errore durante la scrittura:\n{e}")
            return

        QMessageBox.information(
            self,
            "Esporta Excel",
            f"{written} pratiche salvate in:\n{path}",
        )

    # ------------------------------------------------------------------ Public API

    def set_job_id(self, job_id: Optional[str]) -> None:
        """Chiamato da MainWindow quando si passa a questa tab."""
        if not job_id:
            return
        if self.job_combo.findText(job_id) == -1:
            self.job_combo.addItem(job_id)
        self.job_combo.setCurrentText(job_id)
```

- [ ] **Step 2: Verify the module imports cleanly**

Run:
```bash
.venv/Scripts/python.exe -c "import sys; sys.path[:0]=['edge-agent']; import ui.data_table_tab; print('ok')"
```
Expected: `ok`.

- [ ] **Step 3: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: 90 passed, unchanged.

- [ ] **Step 4: Commit**

```bash
git add edge-agent/ui/data_table_tab.py
git commit -m "Show one row per practice in the Dati Estratti tab"
```

---

### Task 4: Remove the diagnostic tab and the CSV exports

**Files:**
- Delete: `edge-agent/ui/extraction_results_tab.py`
- Modify: `edge-agent/ui/__init__.py`
- Modify: `edge-agent/ui/main_window.py:14,62-65,74,88-89`
- Modify: `edge-agent/ui/capture_tab.py:120,153,331-360`
- Modify: `edge-agent/local_extraction_client.py:5-6,46,153-185`

**Interfaces:**
- Consumes: `export_results` (Task 2).
- Produces: nothing new. `LocalExtractionClient` loses `export_csv()`; its remaining surface is `start_job()`, `ingest_frame()`, `requeue_job()`, `pending_extractions()`, `shutdown()`, `get_results()`, `get_all_job_ids()`.

- [ ] **Step 1: Delete the diagnostic tab**

```bash
git rm edge-agent/ui/extraction_results_tab.py
```

- [ ] **Step 2: Drop the re-export**

Replace `edge-agent/ui/__init__.py` with:

```python
from .capture_tab import CaptureTab
from .main_window import MainWindow

__all__ = [
    "CaptureTab",
    "MainWindow",
]
```

- [ ] **Step 3: Update MainWindow**

In `edge-agent/ui/main_window.py` delete the import at line 14:

```python
from .extraction_results_tab import ExtractionResultsTab
```

Delete the tab construction (lines 61-65) and its `addTab` (line 74):

```python
        # Tab di risultati locali
        self.results_tab = ExtractionResultsTab(
            extraction_client=self.extraction_client,
            parent=self,
        )
```

```python
        self.tabs.addTab(self.results_tab, "Risultati")
```

Replace `_on_tab_changed` so the index matches the two remaining tabs:

```python
    def _on_tab_changed(self, index: int) -> None:
        job_id = None
        if hasattr(self.capture_tab, "get_current_job_id"):
            job_id = self.capture_tab.get_current_job_id()
        # Cattura = 0, Dati Estratti = 1 (era 2 quando esisteva il tab Risultati).
        if job_id and index == 1 and hasattr(self.data_tab, "set_job_id"):
            self.data_tab.set_job_id(job_id)
```

Update the class docstring so it stops promising a "Risultati" tab:

```python
    """
    Finestra principale dell'app Edge Agent.

    Contiene:
        - una tab "Cattura" per gestire job e worker di screenshot;
        - una tab "Dati Estratti" con una riga per pratica consolidata.

    Condivide:
        - AgentConfig
        - LocalExtractionClient

    e sincronizza automaticamente il job_id tra le due tab.
    """
```

- [ ] **Step 4: Retarget the Cattura export button**

In `edge-agent/ui/capture_tab.py` line 120, change the label:

```python
        self.export_button = QPushButton("⬇️  Esporta Excel", self)
```

Line 153, change the connection:

```python
        self.export_button.clicked.connect(self._on_export_excel)
```

Replace the whole `_on_export_csv` method (starting line 331) with:

```python
    def _on_export_excel(self) -> None:
        if not self.job_id:
            QMessageBox.warning(
                self,
                "Nessun job",
                "Non è presente alcun job corrente da esportare.",
            )
            return

        results = self.api_client.get_results(self.job_id)
        if not results:
            self._log(f"[ERROR] Export Excel fallita: nessun risultato per {self.job_id}.")
            QMessageBox.warning(
                self,
                "Nessun dato",
                "Nessuna estrazione completata da esportare.",
            )
            return

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Salva Excel",
            f"dati-{self.job_id}.xlsx",
            "File Excel (*.xlsx)",
        )
        if not file_path:
            return

        try:
            written = export_results(results, file_path)
        except Exception as e:  # noqa: BLE001
            self._log(f"[ERROR] Export Excel fallita: {e}")
            QMessageBox.critical(self, "Errore", f"Errore durante la scrittura:\n{e}")
            return

        self._log(f"Export Excel salvata in: {file_path} ({written} pratiche)")
        QMessageBox.information(
            self,
            "Export completata",
            f"{written} pratiche salvate in:\n{file_path}",
        )
```

Add the import near the other local imports at the top of `capture_tab.py`:

```python
from excel_export import export_results
```

Read the file first: if the old `_on_export_csv` body continues past line 360 with a
`try/except` and a trailing `QMessageBox`, delete it all — the replacement above is the
complete method.

- [ ] **Step 5: Drop export_csv from the client**

In `edge-agent/local_extraction_client.py` delete the `export_csv` method (lines 153-185) and the now-unused imports on lines 5-6:

```python
import csv
import io
```

Also drop `escape_csv_formula` from the import on line 33 if nothing else uses it, and update the class docstring line 46:

```python
    Compatible surface: start_job(), ingest_frame(), requeue_job(), get_results().
```

- [ ] **Step 6: Verify nothing still references the removed names**

Run:
```bash
grep -rn "export_csv\|ExtractionResultsTab\|results_tab\|escape_csv_formula" edge-agent/ tests/ --include=*.py
```
Expected: no output.

- [ ] **Step 7: Verify the UI package imports**

Run:
```bash
.venv/Scripts/python.exe -c "import sys; sys.path[:0]=['edge-agent']; import ui; from ui.main_window import MainWindow; print('ok')"
```
Expected: `ok`.

- [ ] **Step 8: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: 90 passed.

- [ ] **Step 9: Commit**

```bash
git add -A edge-agent/
git commit -m "Drop the diagnostic tab and the three CSV exports"
```

---

### Task 5: Log the diagnostics that left the UI

**Files:**
- Modify: `edge-agent/local_extraction_client.py` (`_process_frame`)

**Interfaces:**
- Consumes: `_meta_agg` keys `calls`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `estimated_cost_usd`, `latency_ms` (`extraction/pipeline.py:339-349`); `_field_sources` (`pipeline.py:167`).
- Produces: nothing importable. Log lines only.

- [ ] **Step 1: Add the logging helper**

In `edge-agent/local_extraction_client.py`, add above the class:

```python
# ============================================================
# Diagnostics
# ============================================================


def _log_extraction(job_id: str, result: Dict[str, Any]) -> None:
    """Print the per-frame diagnostics to stdout.

    In the windowed bundle stdout is edge-agent.log (edge_agent.py:15-25). This
    is the only place confidence, cost and field provenance survive now that the
    diagnostic tab is gone: the UI shows business data only.
    """
    meta = result.get("_meta_agg") or {}
    sources = result.get("_field_sources") or {}

    print(
        f"[EXTRACT] job={job_id} screen={result.get('screen_id')!r} "
        f"page={result.get('_page_type')!r} status={result.get('_status')} "
        f"calls={meta.get('calls', 0)} tokens={meta.get('total_tokens', 0)} "
        f"cost=${float(meta.get('estimated_cost_usd', 0.0) or 0.0):.6f} "
        f"latency={meta.get('latency_ms', 0)}ms"
    )

    error = result.get("_error")
    if error:
        print(f"[EXTRACT]   error: {error}")

    for key, payload in (result.get("fields") or {}).items():
        if not isinstance(payload, dict):
            continue
        value = payload.get("value")
        if value is None or str(value).strip() == "":
            continue
        confidence = payload.get("confidence") or 0.0
        print(
            f"[EXTRACT]   {key}={value!r} conf={float(confidence):.2f} "
            f"src={sources.get(key, '?')}"
        )
```

- [ ] **Step 2: Call it from `_process_frame`**

In `_process_frame`, immediately after the three `result["_page_*"]` assignments and before the `with self._lock:` block, insert:

```python
        _log_extraction(job_id, result)
```

- [ ] **Step 3: Verify the helper against a realistic result**

Run:
```bash
.venv/Scripts/python.exe -c "
import sys; sys.path[:0]=['edge-agent']
import os; os.environ.setdefault('LLM_API_KEY','test-key')
from local_extraction_client import _log_extraction
_log_extraction('job-1', {
    'screen_id': 'Risultato ricerca',
    '_page_type': 'Risultato ricerca',
    '_status': 'OK',
    '_meta_agg': {'calls': 3, 'total_tokens': 4211, 'estimated_cost_usd': 0.0123, 'latency_ms': 8400},
    '_field_sources': {'ndg': 'ANCHOR_HEADER', 'tipo': 'RETRY_HEADER'},
    'fields': {
        'ndg': {'value': '12345', 'confidence': 0.99},
        'tipo': {'value': 'BPI Mutui', 'confidence': 0.81},
        'fase': {'value': None, 'confidence': 0.0},
    },
})
"
```
Expected: a `[EXTRACT] job=job-1 ...` header line, then two indented field lines for `ndg` and `tipo`, and none for `fase`.

- [ ] **Step 4: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: 90 passed.

- [ ] **Step 5: Commit**

```bash
git add edge-agent/local_extraction_client.py
git commit -m "Log per-frame extraction diagnostics to edge-agent.log"
```

---

### Task 6: Update the documentation

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: nothing. Documentation only.

- [ ] **Step 1: Update the capture flow diagram**

In `CLAUDE.md`, in the "Edge-agent capture flow" block, replace the two result sinks:

```
                                       → stores result → emits result_ready(job_id, result)
                                                             ├── ExtractionResultsTab (Risultati)
                                                             └── DataTableTab (Dati Estratti)
```

with:

```
                                       → logs diagnostics → stores result
                                       → emits result_ready(job_id, result)
                                                             └── DataTableTab (Dati Estratti)
```

- [ ] **Step 2: Update the module tables**

In the `edge-agent/` package table, delete the `ui/extraction_results_tab.py` row and add two rows:

```
| `practice_consolidation.py` | `PracticeRecord`/`consolidate()`: groups captured frames by NDG and merges their fields with `pick_best()` |
| `excel_export.py` | `ColumnSpec`, `build_columns()`, `write_workbook()`, `export_results()` -- formatted openpyxl workbook, two-level header |
```

Update the `local_extraction_client.py` row to drop `export_csv()`:

```
| `local_extraction_client.py` | `LocalExtractionClient(QObject)`: bridge to `ExtractionPipeline`; `start_job()`, `ingest_frame()` (enqueues on the daemon pool, returns immediately), `shutdown()`; `result_ready`/`frame_queued` signals; logs per-frame diagnostics |
```

Update the `ui/data_table_tab.py` row:

```
| `ui/data_table_tab.py` | `DataTableTab`: spreadsheet view (rows = consolidated practices, cols = the 45 canonical fields), Excel export |
```

Update the `ui/main_window.py` row:

```
| `ui/main_window.py` | `MainWindow`: creates `LocalExtractionClient` and the Cattura / Dati Estratti tabs (+ Debug LLM with `--debug`) |
```

- [ ] **Step 3: Add an architectural constraint**

Append to the "Architectural Constraints" list:

```
14. **Edge-agent shows business data only** -- the UI presents the 45 canonical fields,
    one row per consolidated practice. Confidence, status, cost, tokens, latency and
    field provenance go to `edge-agent.log` via `_log_extraction()`, never back into a
    tab. Consolidation groups frames by normalized NDG (a frame whose NDG was not read
    attaches to the most recent practice) and merges fields with `pick_best()` -- do not
    write a second merge semantics. In xlsx, neutralize formulas with
    `cell.data_type = "s"`, never `escape_csv_formula()`: that is the CSV convention, it
    leaves a visible apostrophe and it corrupts negative amounts.
```

- [ ] **Step 4: Update the Testing section**

In "Testing & Validation", replace the edge-agent smoke test step:

```
6. **Edge-agent smoke test:** `python edge-agent/edge_agent.py` -- start capture in BPER mode,
   verify `ingest_frame()` is called and results appear in the Dati Estratti tab, then
   export the workbook and check the two-level header.
```

And update the suite description sentence to mention the two new test modules:

```
A pytest suite lives in `tests/` (`python -m pytest tests`) covering the page registry, the capture
stability tracker, the daemon thread pool, the prompt catalog, practice consolidation and the Excel
writer; the extraction pipeline itself is still untested.
```

- [ ] **Step 5: Verify no stale references remain**

Run:
```bash
grep -n "ExtractionResultsTab\|export_csv\|Risultati" CLAUDE.md
```
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "Document the practice consolidation and the Excel export"
```

---

## Manual verification

The automated suite cannot exercise Qt rendering or a real capture. After Task 6:

1. `.venv/Scripts/python.exe edge-agent/edge_agent.py` — the window shows **Cattura** and **Dati Estratti** only.
2. Start a capture over the 9 BPER screens. The Cattura log shows frames queued.
3. Switch to Dati Estratti: **one row**, not nine. The band row shows the four page names in `PAGE_SHEET_ORDER`, each spanning its own columns. NDG and DENOMINAZIONE are the first two columns.
4. Rename a column, then export: the renamed label appears in row 2 of the workbook.
5. Open the workbook: page bands merged and coloured, panes frozen so NDG and DENOMINAZIONE stay visible while scrolling right, autofilter dropdowns on the label row, long notes wrapped.
6. `edge-agent.log` contains one `[EXTRACT]` header per frame plus the per-field lines.
