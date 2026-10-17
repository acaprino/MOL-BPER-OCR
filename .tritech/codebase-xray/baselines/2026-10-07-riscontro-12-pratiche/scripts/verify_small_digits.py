"""Check the transcribed NDGs of the "Elenco Soggetti" table against the pixels, without an LLM.

Usage: python -I verify_small_digits.py <gt_json_dir> <source_root> [--show PRACTICE]

Why: the table font is about 7px tall and a 6 differs from an 8 by one or two pixels, so a model
(or a person looking at an enlarged crop) can agree with a wrong transcription. Here every digit
glyph is compared with reference glyphs whose value is known from a larger font: the first row of
each table is the practice NDG, which the Elenco page and the banner show in a clear size.

Method: per screenshot, locate the NDG column, cut each line into fixed-pitch cells, then label
each cell with its nearest reference cell (L1 distance, +-1px horizontal shift). A cell whose
nearest reference disagrees with the transcription is reported with both readings and distances.
"""
import glob
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

from PIL import Image

CELL_W, ROWS = 5, 7   # glyph body is 4-5px wide; the pitch is fitted per screenshot
Y_RANGE = (440, 800)
Cell = Tuple[Tuple[int, ...], ...]


def ink_matrix(img: Image.Image, x0: int, x1: int, y0: int, y1: int) -> List[List[int]]:
    px = img.load()
    out = []
    for y in range(y0, y1):
        bg = px[x0, y]
        out.append([max(abs(px[x, y][c] - bg[c]) for c in range(3)) for x in range(x0, x1)])
    return out


def table_rows(img: Image.Image) -> Tuple[int, int]:
    """Vertical extent of the soggetti table: from under the last navy title bar to ~300px below."""
    px = img.load()
    last_navy = None
    for y in range(300, min(640, img.height)):
        r, g, b = px[700, y]
        if r < 50 and g < 70 and b > 70:
            last_navy = y
    if last_navy is None:
        return Y_RANGE[0], min(Y_RANGE[1], img.height)
    return last_navy + 2, min(last_navy + 300, img.height - 25)


def find_split(img: Image.Image, y0: int, y1: int) -> Optional[int]:
    """Blank column between the right-aligned NDG and the Denominazione text, nearest to x=410."""
    px = img.load()
    best = None
    for x in range(398, 424):
        blank = all(max(abs(px[x, y][c] - px[x - 1, y][c]) for c in range(3)) < 28 and
                    max(abs(px[x, y][c] - px[x + 1, y][c]) for c in range(3)) < 28 for y in range(y0, y1))
        if blank and (best is None or abs(x - 410) < abs(best - 410)):
            best = x
    return best


def lines_in_band(mat: List[List[int]], y0: int) -> List[Tuple[int, int]]:
    rows = [i for i, r in enumerate(mat) if sum(v > 70 for v in r) >= 2]
    out, start, prev = [], None, None
    for i in rows:
        if start is None:
            start = prev = i
        elif i - prev > 1:
            out.append((start, prev))
            start = i
        prev = i
    if start is not None:
        out.append((start, prev))
    return [(a, b) for a, b in out if b - a + 1 == ROWS]


def cells_for(mat: List[List[int]], top: int, origin: float, pitch: float, n: int) -> List[Cell]:
    cells = []
    for i in range(n):
        x = int(round(origin + i * pitch))
        cells.append(tuple(tuple(mat[top + r][x + c] if 0 <= x + c < len(mat[0]) else 0 for c in range(CELL_W))
                           for r in range(ROWS)))
    return cells


def fit_grid(mat: List[List[int]], tops: List[int], n_by_line: List[int], right: int) -> Tuple[float, float]:
    """Origin and pitch shared by all lines of a table: the grid leaving the least ink on cell boundaries."""
    n = max(n_by_line)
    best, best_cost = (right - n * 5.2, 5.2), None
    for p100 in range(480, 600, 2):
        pitch = p100 / 100
        for step in range(-10, 11):
            origin = right - n * pitch + step * 0.25
            cost = 0
            for top, k in zip(tops, n_by_line):
                for i in range(n - k, n + 1):
                    x = int(round(origin + i * pitch)) - 1
                    if 0 <= x < len(mat[0]):
                        cost += sum(mat[top + r][x] for r in range(ROWS))
            if best_cost is None or cost < best_cost:
                best, best_cost = (origin, pitch), cost
    return best


def dist(a: Cell, b: Cell) -> int:
    best = None
    for dx in (-1, 0, 1):
        total = 0
        for r in range(ROWS):
            for c in range(CELL_W):
                cb = c + dx
                total += abs(a[r][c] - (b[r][cb] if 0 <= cb < CELL_W else 0))
        best = total if best is None else min(best, total)
    return best


def art(cell: Cell) -> List[str]:
    ramp = " .:-=+*#%@"
    return ["".join(ramp[min(9, v * 10 // 256)] for v in row) for row in cell]


def main(json_dir: str, source_root: str, show: str) -> None:
    glyphs: List[Dict] = []
    for path in sorted(glob.glob(os.path.join(json_dir, "*.json"))):
        data = json.load(open(path, encoding="utf-8"))
        practice = str(data["pratica"])
        shots = data["screenshots"]
        stem = next((k for k, s in shots.items() if s.get("kind") == "soggetti"), None)
        if not stem:
            continue
        people = shots[stem].get("soggetti") or []
        ndgs = [str(p.get("ndg") or "") for p in people]
        elenco_ndg = next((str((s.get("elenco") or {}).get("row", {}).get("NDG") or "") for s in shots.values()
                           if s.get("kind") == "elenco" and (s.get("elenco") or {}).get("row", {}).get("NDG")), "")
        img = Image.open(os.path.join(source_root, practice, stem + ".png")).convert("RGB")
        y0, y1 = table_rows(img)
        split = find_split(img, y0, y1)
        if split is None:
            print(f"{practice}: NDG column not located (table rows {y0}-{y1})")
            continue
        x0 = split - 52
        mat = ink_matrix(img, x0, split, y0, y1)
        lines = lines_in_band(mat, y0)
        # the header row ("NDG", white on grey) is a 7px line too: keep the lines made of digits only
        lines = lines[-len(ndgs):] if len(lines) >= len(ndgs) else lines
        if len(lines) != len(ndgs):
            print(f"{practice}: {len(lines)} text lines in the NDG column, {len(ndgs)} transcribed rows -> check by hand")
            continue
        tops = [a for a, _ in lines]
        right = max(max(c for c in range(len(mat[0])) if any(mat[t + r][c] > 70 for r in range(ROWS))) for t in tops) + 1
        origin, pitch = fit_grid(mat, tops, [len(n) for n in ndgs], right)
        nmax = max(len(n) for n in ndgs)
        for row, (top, ndg) in enumerate(zip(tops, ndgs)):
            cells = cells_for(mat, top, origin + (nmax - len(ndg)) * pitch, pitch, len(ndg))
            confirmed = row == 0 and elenco_ndg.lstrip("0") == ndg.lstrip("0")
            for i, (cell, digit) in enumerate(zip(cells, ndg)):
                glyphs.append({"practice": practice, "row": row, "pos": i, "digit": digit, "cell": cell,
                               "confirmed": confirmed, "ndg": ndg})
            if show == practice:
                print(f"{practice} row {row + 1} transcribed {ndg} (confirmed={confirmed})")
                arts = [art(c) for c in cells]
                for r in range(ROWS):
                    print("   " + "  ".join(a[r] for a in arts))

    refs = [g for g in glyphs if g["confirmed"]]
    print(f"glyphs: {len(glyphs)}  of which confirmed by a larger font (practice NDG on the Elenco page): {len(refs)}")

    # 1) nearest-neighbour agreement: identical pixels cannot be two different digits
    flagged = 0
    for g in glyphs:
        pool = [r for r in glyphs if not (r["practice"] == g["practice"] and r["row"] == g["row"])]
        ranked = sorted(pool, key=lambda r: dist(g["cell"], r["cell"]))
        nearest = ranked[0]
        same = next((r for r in ranked if r["digit"] == g["digit"]), None)
        if nearest["digit"] != g["digit"]:
            flagged += 1
            d_same = dist(g["cell"], same["cell"]) if same else None
            print(f"  NN-CHECK {g['practice']} row {g['row'] + 1} ndg {g['ndg']} pos {g['pos'] + 1}: transcribed {g['digit']}, "
                  f"nearest glyph is a {nearest['digit']} from {nearest['practice']} row {nearest['row'] + 1} "
                  f"(d={dist(g['cell'], nearest['cell'])}); nearest {g['digit']} at d={d_same}")
            if "--art" in sys.argv:
                for line in art(g["cell"]):
                    print("        " + line)
    print(f"nearest-neighbour disagreements: {flagged} of {len(glyphs)}")

    # 2) structural 6-vs-8 test: a 6 has its bar on row 3, an 8 has its waist on row 4
    def six_eight_score(cell: Cell) -> float:
        cols = [c for c in range(CELL_W) if any(cell[r][c] > 70 for r in range(ROWS))]
        inner = [c for c in cols if cols[0] < c < cols[-1]] or cols
        bar = sum(cell[2][c] for c in inner) / len(inner)
        waist = sum(cell[3][c] for c in inner) / len(inner)
        return bar - waist

    scores = {"6": [], "8": []}
    wrong = 0
    for g in glyphs:
        if g["digit"] in scores:
            score = six_eight_score(g["cell"])
            scores[g["digit"]].append(score)
            if (g["digit"] == "6") != (score > 0):
                wrong += 1
                print(f"  6/8-CHECK {g['practice']} row {g['row'] + 1} ndg {g['ndg']} pos {g['pos'] + 1}: transcribed {g['digit']}, score {score:+.0f}")
                if "--art" in sys.argv:
                    for line in art(g["cell"]):
                        print("        " + line)
    for digit, values in scores.items():
        if values:
            print(f"digit {digit}: {len(values)} glyphs, bar-minus-waist score from {min(values):+.0f} to {max(values):+.0f}")
    print(f"6/8 structural disagreements: {wrong}")


if __name__ == "__main__":
    show = sys.argv[sys.argv.index("--show") + 1] if "--show" in sys.argv else ""
    main(sys.argv[1], sys.argv[2], show)
