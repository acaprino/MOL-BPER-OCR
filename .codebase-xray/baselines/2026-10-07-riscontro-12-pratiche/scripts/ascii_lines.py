"""Find the text lines inside a vertical band of a screenshot and print each as an intensity grid.

Usage: python -I ascii_lines.py <image> <x0> <x1> [y0 y1]
Ink is measured as distance from the row's background colour, so black and blue text both show.
Reading key for the ~7px table font (rows counted from the top of the digit):
  6: bar on row 3 joined to the left stroke, left stroke unbroken down to the base
  8: side strokes with a gap on row 3, waist centred on row 4
  9: bar on row 5 joined to the right stroke        0: two side strokes, nothing in the middle
  3: right-hand strokes only, short bar on row 4    5: full top bar, bar on row 3, left stroke rows 1-3
"""
import sys

from PIL import Image

path, x0, x1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
img = Image.open(path).convert("RGB")
y0 = int(sys.argv[4]) if len(sys.argv) > 4 else 0
y1 = int(sys.argv[5]) if len(sys.argv) > 5 else img.height
px = img.load()
ramp = " .:-=+*#%@"


def ink_row(y: int) -> list:
    bg = px[x0, y]
    return [max(abs(px[x, y][c] - bg[c]) for c in range(3)) for x in range(x0, x1)]


rows = {y: ink_row(y) for y in range(y0, y1)}
has_ink = [y for y in range(y0, y1) if sum(v > 70 for v in rows[y]) >= 2]
lines, start, prev = [], None, None
for y in has_ink:
    if start is None:
        start = prev = y
    elif y - prev > 1:
        lines.append((start, prev))
        start = y
    prev = y
if start is not None:
    lines.append((start, prev))
print(f"{path} band x={x0}-{x1}: {len(lines)} text lines")
for top, bottom in lines:
    if not 5 <= bottom - top + 1 <= 12:
        continue
    print(f"-- y={top}-{bottom}")
    for y in range(top, bottom + 1):
        print("   " + "".join(ramp[min(9, v * 10 // 256)] for v in rows[y]))
