"""Read the review workbook back and check its structure: python -I check_review_workbook.py <workbook.xlsx> <dati.csv>"""
import csv
import sys
import zipfile
from collections import Counter

from openpyxl import load_workbook

path, gt_path = sys.argv[1], sys.argv[2]
wb = load_workbook(path)
print("sheets:", wb.sheetnames, "active:", wb.active.title)
ws = wb["Revisione"]
headers = [c.value for c in ws[1]]
print("headers:", headers)
rows = list(ws.iter_rows(min_row=2, values_only=True))
print("rows:", len(rows), "freeze:", ws.freeze_panes, "filter:", ws.auto_filter.ref)
print("frames:", Counter(r[13] for r in rows), "priority:", Counter(r[10] for r in rows))
print("yellow cells empty:", all(r[7] is None and r[8] is None and r[9] is None for r in rows))
print("validation:", [(str(v.sqref), v.formula1) for v in ws.data_validations.dataValidation])
with open(gt_path, encoding="utf-8-sig", newline="") as fh:
    gt = list(csv.DictReader(fh, delimiter=";"))
want = Counter((r["Fotogramma"], r["Denominazione da attribuire"], r["Valore rilevato"] if r["Valore rilevato"].strip() else "(vuoto)") for r in gt)
got = Counter((r[14], r[3], r[6]) for r in rows)
print("same (screen, field, value) rows as dati.csv:", want == got, len(gt))
formulas = sum(1 for row in ws.iter_rows(min_row=2) for c in row if c.data_type == "f")
print("formula cells:", formulas)
images = ws._images
cells = Counter()
bad = 0
for im in images:
    a = im.anchor
    same = a._from.col == a.to.col and a._from.row == a.to.row
    bad += not same
    cells[a._from.col] += 1
print("pictures:", len(images), "by column index:", dict(cells), "anchored across cells:", bad)
picture_rows = {im.anchor._from.row for im in images if im.anchor._from.col == 4}
print("every data row has its picture:", picture_rows == set(range(1, len(rows) + 1)))
heights = [ws.row_dimensions[i].height for i in range(2, len(rows) + 2)]
print("row heights (pt): min", min(heights), "max", max(heights))
with zipfile.ZipFile(path) as z:
    media = [n for n in z.namelist() if n.startswith("xl/media/")]
    print("media files:", len(media), "bytes:", sum(z.getinfo(n).file_size for n in media))
info = wb["Istruzioni"]
print("instructions rows:", info.max_row, "| first:", info["A1"].value)
