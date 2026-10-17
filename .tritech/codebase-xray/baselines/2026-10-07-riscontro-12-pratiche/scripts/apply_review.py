"""Read the reviewed workbook back and write the corrected ground truth.

Usage: python -I apply_review.py <reviewed.xlsx> <dati.csv> <out_dir>

Writes <out_dir>/dati_revisionato.csv: the same three columns the evaluator reads, with the corrected
values, plus the review outcome and the value before the correction. Prints what was reviewed and
every change. A row counts as reviewed only when "Esito" is filled. ERRATO needs "Valore corretto";
"(vuoto)" there means the field has no value on screen. Rows marked ERRATO without a corrected value
and rows marked NON LEGGIBILE keep the transcribed value and are listed, never silently accepted.
"""
import csv
import os
import sys
from collections import Counter
from typing import Dict, List, Tuple

from openpyxl import load_workbook

EMPTY = "(vuoto)"


def cell_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def main(workbook_path: str, csv_path: str, out_dir: str) -> None:
    sheet = load_workbook(workbook_path, read_only=True, data_only=True)["Revisione"]
    rows = sheet.iter_rows(values_only=True)
    header = [cell_text(v) for v in next(rows)]
    col = {name: header.index(name) for name in ("ID schermata", "Campo", "Valore letto", "Esito", "Valore corretto", "Note")}
    review: Dict[Tuple[str, str], Tuple[str, str, str, str]] = {}
    for row in rows:
        if row[col["ID schermata"]] is None:
            continue
        key = (cell_text(row[col["ID schermata"]]), cell_text(row[col["Campo"]]))
        review[key] = (cell_text(row[col["Valore letto"]]), cell_text(row[col["Esito"]]).upper(),
                       cell_text(row[col["Valore corretto"]]), cell_text(row[col["Note"]]))

    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        truth = list(csv.DictReader(fh, delimiter=";"))
    outcome: Counter = Counter()
    changes: List[str] = []
    problems: List[str] = []
    out_rows = []
    for row in truth:
        key = (row["Fotogramma"], row["Denominazione da attribuire"])
        value = row["Valore rilevato"]
        shown, verdict, corrected, note = review.get(key, ("", "", "", ""))
        if key not in review:
            problems.append(f"{key[0]} | {key[1]}: riga assente nel file di revisione")
        elif shown != (value if value.strip() else EMPTY):
            problems.append(f"{key[0]} | {key[1]}: il valore nel file di revisione ({shown!r}) non è quello del ground truth ({value!r})")
        before = ""
        if verdict == "ERRATO":
            fixed = "" if corrected == EMPTY else corrected
            if corrected and fixed != value:
                before, value = value, fixed
                changes.append(f"{key[0]} | {key[1]}: {before!r} -> {value!r}")
            elif corrected:
                problems.append(f"{key[0]} | {key[1]}: ERRATO ma il valore corretto coincide con quello letto ({value!r})")
            else:
                problems.append(f"{key[0]} | {key[1]}: ERRATO senza valore corretto, lasciato {value!r}")
        elif verdict not in ("", "OK", "NON LEGGIBILE"):
            problems.append(f"{key[0]} | {key[1]}: esito non riconosciuto {verdict!r}")
        outcome[verdict or "da rivedere"] += 1
        out_rows.append([row["Fotogramma"], row["Denominazione da attribuire"], value, row.get("Nota", ""), verdict, before, note])

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "dati_revisionato.csv")
    with open(out_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["Fotogramma", "Denominazione da attribuire", "Valore rilevato", "Nota", "Revisione",
                         "Valore prima della revisione", "Nota del revisore"])
        writer.writerows(out_rows)
    reviewed = sum(n for verdict, n in outcome.items() if verdict != "da rivedere")
    print(f"righe: {len(truth)}  riviste: {reviewed}  esiti: {dict(outcome)}")
    print(f"correzioni applicate: {len(changes)}")
    for line in changes:
        print("  " + line)
    print(f"da sistemare: {len(problems)}")
    for line in problems:
        print("  " + line)
    print("scritto", out_path)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
