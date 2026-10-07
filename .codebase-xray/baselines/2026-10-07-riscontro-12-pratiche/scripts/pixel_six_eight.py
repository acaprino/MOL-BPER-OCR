"""Tell a 6 from an 8 in the 7-pixel table font from the pixels alone, given where the text is.

Used as a library by make_review_workbook.py; run directly it prints the check for one region:
    python -I pixel_six_eight.py <image> <x0> <y0> <x1> <y1> "<expected text>"

Method: ink is the distance from the background colour. Text lines are split on blank pixel rows and
glyphs on blank pixel columns, in reading order. A character of the expected text is paired with a
glyph only when the pairing cannot be off by one: the counts match (with or without the punctuation,
which is often too faint to register), or the digit is reached from the start or the end of the text
without crossing a punctuation mark or two glyphs that touch. Every paired 6 or 8 is then tested:
a 6 has its bar on the third pixel row, joined to the left stroke; an 8 has its waist on the fourth.
Whatever cannot be paired, or scores too close to zero, is reported as not checkable, never guessed.
"""
import sys
from collections import Counter
from typing import Dict, List, Optional, Tuple

from PIL import Image

STRONG = 140     # ink level of a stroke pixel; fainter pixels are anti-aliasing and may bridge two glyphs
GLYPH_ROWS = 7   # height of a digit in the practice-detail tables
MAX_GLYPH = 6    # a wider run of columns is two glyphs touching
PITCH = 5.2      # average advance of a digit, to estimate how many glyphs a wide run holds
MARGIN = 25      # bar-minus-waist scores closer to zero than this are not trusted
Glyph = Tuple[int, int, int]  # top row, first column, last column
Region = Tuple[int, int, int, int]


def ink_grid(img: Image.Image, box: Region) -> List[List[int]]:
    x0, y0, x1, y1 = box
    px = img.load()
    background = Counter(px[x, y] for y in range(y0, y1) for x in range(x0, x1)).most_common(1)[0][0]
    return [[max(abs(px[x, y][c] - background[c]) for c in range(3)) for x in range(x0, x1)] for y in range(y0, y1)]


def runs(flags: List[bool]) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    start: Optional[int] = None
    for i, flag in enumerate(flags + [False]):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            out.append((start, i - 1))
            start = None
    return out


def glyphs_in(grid: List[List[int]]) -> List[Glyph]:
    """Runs of inked columns, line by line and left to right."""
    found: List[Glyph] = []
    for top, bottom in runs([any(v >= STRONG for v in row) for row in grid]):
        if bottom - top < 4:
            continue
        for c0, c1 in runs([any(grid[y][x] >= STRONG for y in range(top, bottom + 1)) for x in range(len(grid[0]))]):
            glyph_top = min(y for y in range(top, bottom + 1) if any(grid[y][x] >= STRONG for x in range(c0, c1 + 1)))
            found.append((glyph_top, c0, c1))
    return found


def width(glyph: Glyph) -> int:
    return glyph[2] - glyph[1] + 1


def pair(chars: List[str], glyphs: List[Glyph]) -> Dict[int, Glyph]:
    """Character index -> glyph, only where the pairing cannot be off by one."""
    solid = [i for i, c in enumerate(chars) if c.isalnum()]
    if len(glyphs) == len(chars):
        return dict(enumerate(glyphs))
    if len(glyphs) == len(solid):
        return dict(zip(solid, glyphs))
    implied = sum(1 if width(g) <= MAX_GLYPH else round(width(g) / PITCH) for g in glyphs)
    if not len(solid) <= implied <= len(chars):  # a glyph is missing or the region holds something else
        return {}
    paired: Dict[int, Glyph] = {}
    for i, char in enumerate(chars):  # from the start, up to the first mark or the first two glyphs that touch
        if not char.isdigit() or i >= len(glyphs) or width(glyphs[i]) > MAX_GLYPH:
            break
        paired[i] = glyphs[i]
    for back in range(1, len(chars) + 1):  # and from the end
        if not chars[-back].isdigit() or back > len(glyphs) or width(glyphs[-back]) > MAX_GLYPH:
            break
        paired[len(chars) - back] = glyphs[-back]
    return paired


def check(img: Image.Image, box: Region, expected: str) -> Tuple[str, List[Tuple[int, str, str, float]]]:
    """Returns (status, details). Status: 'conferma' (every 6 and 8 tested and as expected), 'discorda'
    (at least one reads as the other digit), 'parziale' (those tested agree, some could not be tested),
    'non verificabile'. Details: (position in the text without spaces, expected digit, digit from the
    pixels, score) for every tested digit."""
    chars = [c for c in expected if not c.isspace()]
    wanted = sum(c in "68" for c in chars)
    if not wanted:
        return "conferma", []
    grid = ink_grid(img, box)
    glyphs = glyphs_in(grid)
    if len(glyphs) < sum(c.isalnum() for c in chars) - 2:  # a two-line cell whose second line is outside the region
        x0, y0, x1, y1 = box
        box = (max(0, x0 - 10), y0, min(img.width, x1 + 10), min(img.height, y1 + 14))
        grid = ink_grid(img, box)
        glyphs = glyphs_in(grid)
    details: List[Tuple[int, str, str, float]] = []
    for index, (top, c0, c1) in sorted(pair(chars, glyphs).items()):
        char = chars[index]
        if char not in "68" or top + GLYPH_ROWS > len(grid):
            continue
        inked = [y for y in range(top, min(top + GLYPH_ROWS + 3, len(grid))) if any(grid[y][x] >= STRONG for x in range(c0, c1 + 1))]
        if max(inked) - top + 1 != GLYPH_ROWS:  # not the 7-pixel font: the rule does not apply
            continue
        inner = list(range(c0 + 1, c1)) or [c0, c1]
        score = sum(grid[top + 2][x] for x in inner) / len(inner) - sum(grid[top + 3][x] for x in inner) / len(inner)
        if abs(score) >= MARGIN:
            details.append((index + 1, char, "6" if score > 0 else "8", round(score)))
    if any(expected_digit != read for _, expected_digit, read, _ in details):
        return "discorda", details
    if not details:
        return "non verificabile", []
    return ("conferma" if len(details) == wanted else "parziale"), details


if __name__ == "__main__":
    image = Image.open(sys.argv[1]).convert("RGB")
    region = (int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]))
    print(check(image, region, sys.argv[6]))
