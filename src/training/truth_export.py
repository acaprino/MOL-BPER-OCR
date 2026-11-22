"""Export the truth tables of a reviewed bundle as one workbook, for whoever reads Excel rather than CSV.

Run from ``src/``::

    python -m training.truth_export --bundle ../data/training/ground-truth-v3.2 --out ../data/training/ground-truth-v3.2/ground_truth.xlsx
    python -m training.truth_export --bundle ../data/training/ground-truth-v3.4 --out ../data/pratiche/pratiche.xlsx --per-practice

The second writes the archive of the practices: an index and one sheet per practice. The bundle stays the source: the workbook is derived from its CSV tables and manifest, never edited by hand.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from openpyxl import Workbook

SHEETS = (("Pratiche", "practices.csv"), ("Schermate", "screens.csv"), ("Valori", "ground_truth.csv"))
INTEGER_COLUMNS = {"Schermate", "Righe", "Larghezza", "Altezza", "Riga Excel"}
# Column of a practice sheet -> column of ground_truth.csv; the screen is named by its page alone.
PRACTICE_COLUMNS = {"Schermata": "Fotogramma", "Campo": "Denominazione da attribuire", "Valore": "Valore rilevato",
                    "Esito": "Esito", "Stato revisione": "Stato revisione", "Riga Excel": "Riga Excel",
                    "Correzione": "Correzione"}
PRACTICE_WIDTHS = {"A": 24, "B": 34, "C": 60, "D": 16, "E": 16, "F": 12, "G": 40}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=";"))


def _append_text(sheet: Any, values: list[Any]) -> None:
    """Append one row, storing every string as text so that a reviewed value is never read as a formula."""
    sheet.append(values)
    for cell in sheet[sheet.max_row]:
        if isinstance(cell.value, str):
            cell.data_type = "s"


def _cell(column: str, value: str) -> int | str | None:
    if column in INTEGER_COLUMNS and value.isdigit():
        return int(value)
    return value or None


def export_practice_workbook(bundle_dir: Path, out_path: Path) -> dict[str, int]:
    """Write Indice and one sheet per practice with its reviewed, corrected values, in the order of the truth table."""
    practices = _rows(bundle_dir / "practices.csv")
    values: dict[str, list[dict[str, str]]] = {row["Pratica"]: [] for row in practices}
    for row in _rows(bundle_dir / "ground_truth.csv"):
        values[row["Pratica"]].append(row)  # a value of a practice missing from practices.csv fails here
    workbook = Workbook()
    index = workbook.active
    index.title = "Indice"
    columns = list(practices[0]) if practices else []
    _append_text(index, columns)
    for row in practices:
        _append_text(index, [_cell(column, row[column]) for column in columns])
    index.freeze_panes = "A2"
    for practice, rows in values.items():
        sheet = workbook.create_sheet(practice)
        _append_text(sheet, list(PRACTICE_COLUMNS))
        for row in rows:
            cells = {column: row[source] for column, source in PRACTICE_COLUMNS.items()}
            cells["Schermata"] = cells["Schermata"].split("__", 1)[1]
            _append_text(sheet, [_cell(column, value) for column, value in cells.items()])
        sheet.freeze_panes = "A2"
        for letter, width in PRACTICE_WIDTHS.items():
            sheet.column_dimensions[letter].width = width
    out_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(out_path)
    return {practice: len(rows) for practice, rows in values.items()}


def export_workbook(bundle_dir: Path, out_path: Path) -> dict[str, int]:
    """Write Info, Pratiche, Schermate and Valori; every reviewed text is stored as text, never as a formula."""
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    workbook = Workbook()
    info = workbook.active
    info.title = "Info"
    info.append(["Versione", manifest["dataset_version"]])
    for key, value in manifest["truth_counts"].items():
        info.append([f"Verità: {key}", value])
    for source in manifest["sources"]:
        for kind, file in source.items():
            if kind != "lotto":
                info.append([f"{source['lotto']}: {kind}", Path(file["path"]).name, file["sha256"]])
    counts: dict[str, int] = {}
    for title, name in SHEETS:
        sheet = workbook.create_sheet(title)
        rows = _rows(bundle_dir / name)
        columns = list(rows[0]) if rows else []
        sheet.append(columns)
        for row in rows:
            _append_text(sheet, [int(row[column]) if column in INTEGER_COLUMNS and row[column].isdigit() else row[column]
                                 for column in columns])
        sheet.freeze_panes = "A2"
        counts[title] = len(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(out_path)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the truth tables of a reviewed bundle as one workbook.")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--per-practice", action="store_true", help="An index and one sheet per practice.")
    arguments = parser.parse_args()
    export = export_practice_workbook if arguments.per_practice else export_workbook
    print(json.dumps(export(arguments.bundle, arguments.out)))


if __name__ == "__main__":
    main()
