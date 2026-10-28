"""Export the truth tables of a reviewed bundle as one workbook, for whoever reads Excel rather than CSV.

Run from ``src/``::

    python -m training.truth_export --bundle ../data/training/ground-truth-v3.2 --out ../data/training/ground-truth-v3.2/ground_truth.xlsx

The bundle stays the source: the workbook is derived from its CSV tables and manifest, never edited by hand.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from openpyxl import Workbook

SHEETS = (("Pratiche", "practices.csv"), ("Schermate", "screens.csv"), ("Valori", "ground_truth.csv"))
INTEGER_COLUMNS = {"Schermate", "Righe", "Larghezza", "Altezza", "Riga Excel"}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=";"))


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
            sheet.append([int(row[column]) if column in INTEGER_COLUMNS and row[column] else row[column]
                          for column in columns])
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
        sheet.freeze_panes = "A2"
        counts[title] = len(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(out_path)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the truth tables of a reviewed bundle as one workbook.")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(export_workbook(arguments.bundle, arguments.out)))


if __name__ == "__main__":
    main()
