"""Formatted Excel export of consolidated practices.

openpyxl directly rather than pandas: the two-level header needs merged cells
and per-cell styling that df.to_excel() cannot express.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Mapping, Optional, Sequence

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

import app_paths

_SRC_DIR = str(app_paths.src_dir())
if not app_paths.is_frozen() and _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from extraction.field_definitions import (
    CANONICAL_FIELD_DEFINITIONS,
    resolve_field_export_group_key,
)
from extraction.page_definitions import CANONICAL_PAGE_NAMES, PAGE_SHEET_ORDER

from practice_consolidation import Corrections, PracticeRecord, consolidate, has_content

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
    """A canonical field column; page_key/name describe its spreadsheet group."""

    schema_key: str
    label: str
    page_key: str
    page_name: str


def _canonical_sort_key(schema_key: str) -> tuple:
    definition = CANONICAL_FIELD_DEFINITIONS[schema_key]
    export_group_key = resolve_field_export_group_key(schema_key) or definition["page_key"]
    return (
        PAGE_SHEET_ORDER.index(export_group_key),
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
        page_key = resolve_field_export_group_key(schema_key) or definition["page_key"]
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
    # Characters Excel refuses would make openpyxl raise and lose the whole export.
    text = "" if value is None else ILLEGAL_CHARACTERS_RE.sub("", str(value))
    if text.strip() == "":
        cell.value = None
    else:
        cell.value = text
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
        cell = _set_text(ws, 2, index, column.label)
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

    # Stage on the destination volume for atomic replace. Windows requires
    # the temporary handle to be closed before the rename.
    destination = Path(path)
    staged = NamedTemporaryFile(dir=destination.parent, prefix=".edge-agent-", delete=False)
    try:
        with staged:
            wb.save(staged)
            staged.flush()
            os.fsync(staged.fileno())
        os.replace(staged.name, destination)
    except BaseException:
        Path(staged.name).unlink(missing_ok=True)
        raise


def export_results(
    results: Sequence[Dict[str, Any]],
    path: str,
    labels: Optional[Mapping[str, str]] = None,
    corrections: Optional[Corrections] = None,
) -> int:
    """Consolidate raw pipeline results and write the workbook.

    Single entry point shared by the Cattura and Dati Estratti tabs so the two
    buttons cannot drift apart. `corrections` are the operator's edits, applied
    over the merged values. Returns the number of practices written.
    """
    # A session of errors only consolidates to one blank record: it is not a practice.
    records = [record for record in consolidate(results, corrections) if has_content(record)]
    write_workbook(records, build_columns(labels), path)
    return len(records)
