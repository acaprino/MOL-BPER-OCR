"""Build the Excel workbook for the manual review of the ground truth.

Usage (cwd = repo root): python make_review_workbook.py <input_dir> <baseline_dir> <out.xlsx> <work_dir>

One row per ground-truth value: a crop of the screenshot with a red frame on the value, the value as
transcribed, and yellow cells for the reviewer (Esito, Valore corretto, Note). The position of each
value comes from the local OCR lines. The OCR gives one box per line, not per word, so the words of
a line are placed on the runs of its ink. A value is then looked for only inside the region its field
belongs to (the banner, a table row, the proposed-loans half of the loans table): word by word with
align_value from ft_data.py and, where the OCR split a cell into other words, letter by letter.
A long note is framed as the block of lines whose text is a piece of it.
Where the value is not found the frame is orange and marks the zone where it should be. Small-font
numbers also get a pixel-by-pixel drawing, because a smoothed enlargement makes a 6 look like an 8.
"""
import csv
import json
import math
import os
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, TwoCellAnchor
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils.units import pixels_to_EMU
from openpyxl.worksheet.datavalidation import DataValidation
from PIL import Image, ImageDraw

input_dir, baseline_dir, out_path, work_dir = (os.path.abspath(p) for p in sys.argv[1:5])
sys.path.insert(0, os.path.join(os.path.dirname(baseline_dir), "2026-09-29-ocr-cpu-benchmark", "scripts"))
from ft_data import align_value, norm, similar  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pixel_six_eight import check as six_eight_check  # noqa: E402

Box = Tuple[float, float, float, float]
Allowed = Optional[Callable[[int], bool]]

HEADER_FIELDS = ["NDG", "DENOMINAZIONE", "Tipo", "Filiale relazione"]
FIDI_FIELDS = {"n° FIDO": "fido", "Rapporto": "rapporto", "Descrizione": "descrizione", "Scadenza": "scadenza",
               "Importo (€)": "importo", "Tipo Op.": "tipo"}
ELENCO_LABELS = {"NDG": "ndg", "DENOMINAZIONE": "denom", "Tipo": "tipo", "Stato": "stato", "Fase": "fase",
                 "Creazione": "creazione", "Evidenze": "evidenze"}
SCHEDA_LABELS = {
    "Professione principale": "professione", "DAL": "dal", "Numero mensilità": "mensilit",
    "Retribuzione annua netta": "retribuzione", "Tipo contratto": "contratto",
    "DATORE DI LAVORO ANAGRAFICA": "anagrafica", "RATING UFFICIALE": "rating", "SCORE CGS": "cribis",
    "Nr altri componenti nucleo familiare": "nr", "Di cui percepiscono reddito": "percepiscono",
    "Importo totale annuo altri componenti nucleo familiare": "importo", "Ultima validazione scheda privati": "validazione",
}
SOGGETTI_COLUMNS = {"NDG": "ndg", "DENOMINAZIONE": "denominazione", "RUOLO": "ruolo"}
NOTE_FIELDS = {"Note della richiesta", "Note Scheda Privati"}
SMALL_DIGITS = {"NDG 1", "NDG 2", "NDG 3", "NDG 4", "Rapporto", "Scadenza", "Importo (€)"}
# Practices whose loan expiry was read digit by digit on the pixel grid on 2026-10-07 (see the baseline README).
SCADENZA_CHECKED = {"52062600", "52130861", "52126316", "52060489", "52135039", "51531667", "52068422"}
PAGE_ORDER = ["elenco", "elenco_dx", "elenco_tooltip", "soggetti", "gestionefidi", "gestionefidi_down",
              "gestionefidi_tooltip", "note", "scheda_privati"]
SLOT = re.compile(r"(NDG|DENOMINAZIONE|RUOLO) (\d)")


def kind_of(stem: str) -> str:
    low = stem.lower()
    for prefix in ("elenco_tooltip", "elenco_dx", "elenco", "soggetti", "gestionefidi_tooltip", "gestionefidi_down",
                   "gestionefidi", "note", "scheda_privati"):
        if low.startswith(prefix):
            return prefix
    return "?"


def char_width(char: str) -> float:
    """Rough advance of a character in a proportional sans font, in ems: only the ratios matter."""
    if char in "iljI.,:;'|! ":
        return 0.28
    if char in "ftr()[]-/":
        return 0.34
    if char in "mwMW%@":
        return 0.86
    if char.isdigit():
        return 0.56
    return 0.68 if char.isupper() else 0.52


def ink_spans(arr: np.ndarray, box: Tuple[int, int, int, int], gap: int) -> List[Tuple[int, int]]:
    """Horizontal extents (first column, one past the last) of the runs of ink in a text line.

    Two runs are separate when more than `gap` - 1 blank columns lie between them.
    """
    x0, y0, x1, y1 = max(0, box[0] - 2), max(0, box[1]), min(arr.shape[1], box[2] + 2), min(arr.shape[0], box[3])
    if x1 - x0 < 2 or y1 - y0 < 2:
        return []
    strip = arr[y0:y1, x0:x1].astype(np.int16)
    # background = the most frequent colour (the median fails on bold text, which covers half of its rows)
    colours, counts = np.unique((strip.reshape(-1, 3) // 8).astype(np.int16), axis=0, return_counts=True)
    background = colours[counts.argmax()] * 8 + 4
    ink = np.abs(strip - background).max(axis=2) >= 50
    # a line box can spill over the edge of a coloured bar: such rows are "ink" from side to side
    rows = (ink.mean(axis=1) < 0.85) & ink.any(axis=1)
    if not rows.any():
        return []
    # a tall box also catches the edge of the lines above and below, which fills the gaps between words:
    # keep the unbroken block of inked rows around the middle of the box, that is the text line itself
    middle = len(rows) // 2
    if rows[middle]:
        top = bottom = middle
        while top > 0 and rows[top - 1]:
            top -= 1
        while bottom + 1 < len(rows) and rows[bottom + 1]:
            bottom += 1
        rows[:top] = False
        rows[bottom + 1:] = False
    inked = ink[rows].any(axis=0)
    spans: List[Tuple[int, int]] = []
    start, last = None, None
    for x, flag in enumerate(inked):
        if not flag:
            continue
        if start is None:
            start = x
        elif x - last > gap:
            spans.append((x0 + start, x0 + last + 1))
            start = x
        last = x
    if start is not None:
        spans.append((x0 + start, x0 + last + 1))
    # a sliver on the very edge of the box is the side of a glyph of the next cell, cut by the box
    if spans and spans[0][0] == x0 and spans[0][1] - spans[0][0] <= 2:
        spans = spans[1:]
    if spans and spans[-1][1] == x1 and spans[-1][1] - spans[-1][0] <= 2:
        spans = spans[:-1]
    return spans


def assign_spans(texts: List[str], spans: List[Tuple[int, int]]) -> Optional[Tuple[List[Tuple[float, float]], float]]:
    """Horizontal extent of each word of a line, pairing the words with the inked spans by width.

    The counts often differ: an icon next to the text adds a span, a tight space joins two words,
    a wide gap inside a word splits it. A shortest-path pairing over those four cases keeps the
    words in order. Returns the extents and the cost of the fit, or None when the fit is poor.
    """
    n, m = len(texts), len(spans)
    if not n or not m:
        return None
    model = [max(0.2, sum(char_width(c) for c in t)) for t in texts]
    inf = float("inf")
    Step = Tuple[int, int, str]

    def solve(scale: float) -> Tuple[float, Dict[Tuple[int, int], Step]]:
        """Cheapest pairing when one em of the model is `scale` pixels wide."""
        expected = [w * scale for w in model]
        space = 0.28 * scale
        cost = [[inf] * (m + 1) for _ in range(n + 1)]
        back: Dict[Tuple[int, int], Step] = {}
        cost[0][0] = 0.0

        def relax(i: int, j: int, value: float, origin: Step) -> None:
            if value < cost[i][j]:
                cost[i][j] = value
                back[(i, j)] = origin

        for i in range(n + 1):
            for j in range(m + 1):
                here = cost[i][j]
                if here == inf:
                    continue
                if j < m:
                    relax(i, j + 1, here + 0.8, (i, j, "icon"))
                if i < n and j < m:
                    relax(i + 1, j + 1, here + abs(math.log((spans[j][1] - spans[j][0]) / expected[i])), (i, j, "one"))
                if i < n and j + 1 < m:
                    # no word holds a gap of two spaces: that is an icon next to the text (a paper clip before "BC")
                    apart = 1.0 if spans[j + 1][0] - spans[j][1] > 2 * space else 0.0
                    relax(i + 1, j + 2, here + 0.35 + apart + abs(math.log((spans[j + 1][1] - spans[j][0]) / expected[i])), (i, j, "split"))
                if i + 1 < n and j < m:
                    joined = expected[i] + space + expected[i + 1]
                    relax(i + 2, j + 1, here + 0.35 + abs(math.log((spans[j][1] - spans[j][0]) / joined)), (i, j, "joined"))
        return cost[n][m], back

    def steps(back: Dict[Tuple[int, int], Step]) -> List[Step]:
        path: List[Step] = []
        at = (n, m)
        while at != (0, 0):
            pi, pj, how = back[at]
            path.append((pi, pj, how))
            at = (pi, pj)
        return path

    scale = sum(b - a for a, b in spans) / sum(model)
    total, back = solve(scale)
    if total == inf:
        return None
    # the ink of an icon is not text: once the icons are told apart, size the words on the text alone
    text_ink = sum(spans[pj][1] - spans[pj][0] + (spans[pj + 1][1] - spans[pj + 1][0] if how == "split" else 0)
                   for _, pj, how in steps(back) if how != "icon")
    if 0 < text_ink < sum(b - a for a, b in spans):
        again, back_again = solve(text_ink / sum(model))
        if again < total:
            total, back, scale = again, back_again, text_ink / sum(model)
    if total > 0.35 * n + 0.9:
        return None
    expected = [w * scale for w in model]
    space = 0.28 * scale
    extents: List[Tuple[float, float]] = [(0.0, 0.0)] * n
    for pi, pj, how in steps(back):
        if how == "one":
            extents[pi] = (float(spans[pj][0]), float(spans[pj][1]))
        elif how == "split":
            extents[pi] = (float(spans[pj][0]), float(spans[pj + 1][1]))
        elif how == "joined":
            a, b = spans[pj]
            cut = a + (b - a) * (expected[pi] + space / 2) / (expected[pi] + space + expected[pi + 1])
            extents[pi], extents[pi + 1] = (float(a), cut), (cut, float(b))
    return extents, total


def build_words(lines: List[dict], arr: np.ndarray) -> Tuple[List[dict], Dict[int, List[Tuple[int, int]]]]:
    """Words of every OCR line with their horizontal extent, sorted in reading order.

    The extents come from the ink of the line (assign_spans); when that fails the text is spread over
    the line by character widths, and the frame is later snapped to the ink (snap_to_ink).
    """
    raw: List[dict] = []
    line_spans: Dict[int, List[Tuple[int, int]]] = {}
    for li, line in enumerate(lines):
        xs = [p[0] for p in line["box"]]
        ys = [p[1] for p in line["box"]]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        text = line["text"].strip()
        if not text:
            continue
        region = (int(x0), int(y0), int(x1 + 0.999), int(y1 + 0.999))
        pieces = list(re.finditer(r"\S+", text))
        # the width of a space depends on the font and its weight: try a few and keep the best fit
        widest = max(3, round(0.17 * (region[3] - region[1]))) + 1
        fits = []
        for gap in range(widest, 1, -1):
            spans = ink_spans(arr, region, gap)
            fit = assign_spans([piece.group(0) for piece in pieces], spans)
            if fit is not None:
                fits.append((fit[1], -gap, spans, fit[0]))
        if fits:
            _, _, spans, extents = min(fits, key=lambda f: (f[0], f[1]))
        else:
            spans, extents = ink_spans(arr, region, widest - 1), None
        # frames are trimmed on single glyphs: on the runs of the fit, the dash before a name in bold comes along with it
        line_spans[li] = ink_spans(arr, region, 1)
        fitted = extents is not None
        if extents is None:
            left, right = (spans[0][0], spans[-1][1]) if spans else (x0, x1)
            scale = (right - left) / (sum(char_width(c) for c in text) or 1.0)
            extents = [(left + sum(char_width(c) for c in text[:piece.start()]) * scale,
                        left + sum(char_width(c) for c in text[:piece.end()]) * scale) for piece in pieces]
        for piece, (a, b) in zip(pieces, extents):
            raw.append({"text": piece.group(0), "x0": a, "x1": b, "y0": y0, "y1": y1, "line": li, "fitted": fitted})
    if not raw:
        return [], line_spans
    heights = sorted(w["y1"] - w["y0"] for w in raw)
    tolerance = 0.5 * heights[len(heights) // 2]
    raw.sort(key=lambda w: (w["y0"] + w["y1"]) / 2)
    rows: List[List[dict]] = []
    current: List[dict] = []
    centre = 0.0
    for word in raw:  # same row grouping as ft_data.to_words
        cy = (word["y0"] + word["y1"]) / 2
        if current and abs(cy - centre) > tolerance:
            rows.append(current)
            current = []
        current.append(word)
        centre = cy if len(current) == 1 else (centre * (len(current) - 1) + cy) / len(current)
    rows.append(current)
    words: List[dict] = []
    for index, row in enumerate(rows):
        for word in sorted(row, key=lambda w: w["x0"]):
            word["row"] = index
            words.append(word)
    return words, line_spans


def snap_to_ink(words: List[dict], idx: List[int], line_spans: Dict[int, List[Tuple[int, int]]]) -> Box:
    """Frame of the matched words, widened or narrowed to whole inked words so that it never cuts a letter."""
    boxes: List[Box] = []
    for line in sorted({words[i]["line"] for i in idx}):
        members = [words[i] for i in idx if words[i]["line"] == line]
        x0, x1 = min(w["x0"] for w in members), max(w["x1"] for w in members)
        inside = [(a, b) for a, b in line_spans.get(line, []) if min(b, x1) - max(a, x0) >= 0.5 * (b - a)]
        if inside:
            a, b = inside[0][0], inside[-1][1]
            # where the ink of a line could not be split into words a run holds several of them:
            # snapping to the runs that fit would then leave a matched word out of the frame
            if all(min(w["x1"], b) - max(w["x0"], a) >= 0.5 * (w["x1"] - w["x0"]) for w in members):
                x0, x1 = a, b
        boxes.append((x0, min(w["y0"] for w in members), x1, max(w["y1"] for w in members)))
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def union(words: List[dict], idx: List[int]) -> Box:
    return (min(words[i]["x0"] for i in idx), min(words[i]["y0"] for i in idx),
            max(words[i]["x1"] for i in idx), max(words[i]["y1"] for i in idx))


def find_label(words: List[dict], key: str, allowed: Allowed = None) -> Optional[dict]:
    for i, word in enumerate(words):
        if norm(word["text"]).startswith(key) and (allowed is None or allowed(i)):
            return word
    return None


def permitted(words: List[dict], taken: Set[int], allowed: Allowed) -> List[int]:
    """Indexes of the words a value may use: free, and inside the region its field belongs to."""
    return [i for i in range(len(words)) if i not in taken and (allowed is None or allowed(i))]


def fold(text: str) -> str:
    """Text as compared when looking for a value: the OCR reads the small 6 as 8, and "381 mesi" is where "361 mesi" is.

    Only for finding the place. What the reviewer checks is the transcribed value, never the OCR text.
    """
    return text.replace("8", "6")


def folded(words: List[dict], view: List[int]) -> List[dict]:
    return [dict(words[i], text=fold(words[i]["text"])) for i in view]


def best_alignment(words: List[dict], value: str, taken: Set[int], allowed: Allowed) -> List[int]:
    """align_value tried from every possible first word, keeping the most complete and most compact result.

    align_value alone returns the first start that matches as many tokens as any other: the tooltip
    "55-IPOTECA DI PRIMO GRADO" then starts on the cell "IPOTECA I GR." above it and spans two lines.
    It also checks `allowed` on the first word only, so it runs here on the permitted words alone:
    otherwise the last group of a loan account jumps to the copy of the account in the next table.
    """
    value = fold(value)
    tokens = [t for t in value.split() if norm(t)]
    if not tokens:
        return []
    view = permitted(words, taken, allowed)
    sub = folded(words, view)
    wanted = Counter(norm(t) for t in tokens)
    best: List[int] = []
    best_key: Optional[Tuple[int, int, int]] = None
    for start, word in enumerate(sub):
        if not similar(word["text"], tokens[0]):
            continue
        seq = align_value(sub, value, set(), lambda i, only=start: i == only)
        if not seq:
            continue
        got = Counter(norm(sub[i]["text"]) for i in seq)
        exact = sum(min(count, got[key]) for key, count in wanted.items())
        heights = sorted(sub[i]["y1"] - sub[i]["y0"] for i in seq)
        spread = max(sub[i]["y1"] for i in seq) - min(sub[i]["y0"] for i in seq)
        # in text lines, not pixels: two copies of a value on one line tie, and the first in reading order wins
        key = (len(seq), exact, -round(spread / heights[len(heights) // 2]))
        if best_key is None or key > best_key:
            best, best_key = seq, key
    return [view[i] for i in best]


def run_align(words: List[dict], value: str, taken: Set[int], allowed: Allowed) -> List[int]:
    """Words that, read one after the other, spell the value letter by letter.

    For the cells the OCR split into other words than the transcription: "DE MARCHIALESSANDRO",
    or "KOLAALTIN,KOLA" with "KLEJDI" on the next line of the cell. A value may go on for three lines.
    """
    target = norm(fold(value))
    if len(target) < 4:
        return []
    by_line: Dict[int, List[int]] = {}
    for i in permitted(words, taken, allowed):
        by_line.setdefault(words[i]["line"], []).append(i)
    for members in by_line.values():
        members.sort(key=lambda i: words[i]["x0"])
    order = sorted(by_line, key=lambda line: words[by_line[line][0]]["y0"])

    def pieces(done: int, previous: Optional[List[int]]) -> List[int]:
        """Runs of words spelling target[done:], the longest run of a line first; `previous` is the run above."""
        for line in order:
            members = by_line[line]
            if previous is not None:
                above, here = words[previous[0]], words[members[0]]
                height = above["y1"] - above["y0"]
                if not above["y0"] + 0.5 * height < here["y0"] <= above["y1"] + 1.5 * height:
                    continue
            for a in range(len(members)):
                spelled = ""
                runs: List[Tuple[List[int], int]] = []
                for b in range(a, len(members)):
                    letters = norm(fold(words[members[b]]["text"]))
                    spelled += letters
                    if not spelled or not target.startswith(spelled, done):
                        break
                    if letters:  # a run never ends on a dash or a slash standing alone
                        runs.append((members[a:b + 1], done + len(spelled)))
                for run, reached in reversed(runs):
                    if previous is not None and (words[run[-1]]["x1"] < words[previous[0]]["x0"]
                                                 or words[run[0]]["x0"] > words[previous[-1]]["x1"]):
                        continue  # the next line of a cell is under the line above, not in another column
                    if reached == len(target):
                        return run
                    rest = pieces(reached, run)
                    if rest:
                        return run + rest
        return []

    return pieces(0, None)


def note_frame(lines: List[dict], note: str) -> Optional[Box]:
    """Frame of a long note: the block of OCR lines whose text is a piece of the note, in the order of the note.

    A note is compared line by line, not word by word: the menu on the left of the page shares
    plenty of short words with any note. Two kinds of line cannot be matched and are added when they
    touch the block: a line the OCR could not read, for as long as text of the note is unaccounted
    for, and a line too short to be told from chance, when it is exactly the next piece of the note.
    """
    target = norm(note)
    if len(target) < 6:
        return None
    # autojunk off: on a text longer than 200 characters difflib otherwise ignores every common letter
    matcher = SequenceMatcher(None, "", target, autojunk=False)
    matched: List[Tuple[Box, int, int]] = []
    others: List[Tuple[Box, str, float]] = []
    read: Dict[Box, Tuple[str, float]] = {}
    for line in lines:
        xs, ys = [p[0] for p in line["box"]], [p[1] for p in line["box"]]
        box = (min(xs), min(ys), max(xs), max(ys))
        text = norm(line["text"])
        start = -1
        if len(text) >= 6:
            matcher.set_seq1(text)
            hit = matcher.find_longest_match(0, len(text), 0, len(target))
            window = target[max(0, hit.b - hit.a):max(0, hit.b - hit.a) + len(text)]
            # "DETTAGLIO PRATICA" is 81% like "Dettaglio importi": a short line has to match almost to the letter
            if hit.size >= 5 and SequenceMatcher(None, text, window, autojunk=False).ratio() >= (0.7 if len(text) >= 20 else 0.9):
                start = max(0, hit.b - hit.a)
        if start >= 0:
            matched.append((box, start, start + len(text)))
            read[box] = (text, float(line["score"]))
        elif text:
            others.append((box, text, float(line["score"])))
    if not matched:
        return None
    heights = sorted(box[3] - box[1] for box, _, _ in matched)
    height = heights[len(heights) // 2]
    matched.sort(key=lambda entry: entry[0][1])
    blocks = [[matched[0]]]
    for entry in matched[1:]:  # a note has blank lines between its paragraphs, not half a page
        if entry[0][1] - blocks[-1][-1][0][3] > 3.5 * height:
            blocks.append([entry])
        else:
            blocks[-1].append(entry)
    block = max(blocks, key=lambda entries: sum(end - begin for _, begin, end in entries))
    lefts = sorted(box[0] for box, _, _ in block)
    margin = lefts[len(lefts) // 5]  # the text is aligned left, a few lines are indented

    def in_column(box: Box) -> bool:
        return margin - 14 <= box[0] <= margin + 110

    block = [entry for entry in block if in_column(entry[0])]
    # the lines of a note come in the order of its text: keep the longest run that does, drop chance matches
    best = [1] * len(block)
    link = [-1] * len(block)
    for i in range(len(block)):
        for j in range(i):
            if block[j][1] <= block[i][1] and best[j] + 1 > best[i]:
                best[i], link[i] = best[j] + 1, j
    at = max(range(len(block)), key=lambda i: best[i])
    ordered = []
    while at >= 0:
        ordered.append(block[at])
        at = link[at]
    block = ordered[::-1]
    # a line left out here may still be the next piece of the note ("temporale coerente." occurs three times)
    kept = {box for box, _, _ in block}
    others += [(box, text, score) for box, (text, score) in read.items() if box not in kept]
    left, top = min(box[0] for box, _, _ in block), min(box[1] for box, _, _ in block)
    right, bottom = max(box[2] for box, _, _ in block), max(box[3] for box, _, _ in block)
    per_char = sum(box[2] - box[0] for box, _, _ in block) / max(1, sum(end - begin for _, begin, end in block))
    begin, end = min(b for _, b, _ in block), max(e for _, _, e in block)

    def touching(up: bool) -> Optional[Tuple[Box, str, float]]:
        """The nearest unmatched line right above or right below the block, in its column."""
        if up:
            near = [o for o in others if in_column(o[0]) and o[0][1] < top and top - o[0][3] <= 1.6 * height]
            return max(near, key=lambda o: o[0][3]) if near else None
        near = [o for o in others if in_column(o[0]) and o[0][3] > bottom and o[0][1] - bottom <= 1.6 * height]
        return min(near, key=lambda o: o[0][1]) if near else None

    for up in (True, False):
        while (begin if up else len(target) - end) > 3:
            line = touching(up)
            if line is None:
                break
            box, text, score = line
            if score < 0.85:  # unreadable: count its width as text of the note
                size = round((box[2] - box[0]) / per_char)
            elif up and target[max(0, begin - len(text) - 4):begin].find(text) >= 0:
                size = len(text)
            elif not up and target[end:end + len(text) + 4].find(text) >= 0:
                size = len(text)
            else:
                break  # a readable line that is not the next piece of the note: the note ends here
            others.remove(line)
            if up:
                top, begin = min(top, box[1]), begin - size
            else:
                bottom, end = max(bottom, box[3]), end + size
            left, right = min(left, box[0]), max(right, box[2])
    for box, _, _ in others:  # unreadable lines inside the block may be longer than the others
        if in_column(box) and top <= (box[1] + box[3]) / 2 <= bottom:
            left, right = min(left, box[0]), max(right, box[2])
    return (left, top, right, bottom)


def near_align(words: List[dict], value: str, taken: Set[int], allowed: Allowed) -> List[int]:
    """Second attempt when the reading-order alignment finds nothing or misses part of the value.

    Two cases seen on these screens: the OCR drops the space inside a cell ("KOLAENKELEDA"), and a
    two-line cell is merged into one OCR row with its lines swapped ("Finanza" before "Nuova").
    """
    value = fold(value)
    tokens = [t for t in value.split() if norm(t)]
    if not tokens:
        return []
    view = permitted(words, taken, allowed)
    sub = folded(words, view)
    whole = norm(value)
    for i, word in enumerate(sub):
        if norm(word["text"]) == whole:
            return [view[i]]
    best: List[int] = []
    for start, word in enumerate(sub):
        if not similar(word["text"], tokens[0]):
            continue
        seq = [start]
        height = word["y1"] - word["y0"]
        for token in tokens[1:]:
            x0, y0, x1, y1 = union(sub, seq)
            options = []
            for i, cand in enumerate(sub):
                if i in seq or not similar(cand["text"], token):
                    continue
                dx = max(0.0, cand["x0"] - x1, x0 - cand["x1"])
                dy = max(0.0, cand["y0"] - y1, y0 - cand["y1"])
                if dx <= 260 and dy <= 3.5 * height:
                    options.append((dx + 2 * dy, i))
            if options:
                seq.append(min(options)[1])
        if len(seq) > len(best):
            best = seq
    return [view[i] for i in best] if len(best) >= max(1, 0.7 * len(tokens)) else []


def locate_screen(stem: str, fields: List[Tuple[str, str]], lines: List[dict],
                  arr: np.ndarray) -> Dict[str, Tuple[Optional[Box], str]]:
    """Where each field of one screenshot is: 'esatta' = the OCR words of the value, 'zona' = where it should be."""
    words, line_spans = build_words(lines, arr)
    size = (arr.shape[1], arr.shape[0])
    kind = kind_of(stem)
    detail = kind in ("soggetti", "gestionefidi", "gestionefidi_down", "gestionefidi_tooltip", "note")
    ndg_rows = {w["row"] for w in words if norm(w["text"]) == "ndg" and w["text"].rstrip().endswith(":")}
    title = {name: min((w["row"] for w in words if w["text"].strip() == name), default=None) for name in ("FIDI", "GARANZIE")}
    second_table = min((w["row"] for w in words if norm(w["text"]) == "attesa"), default=None)
    taken: Set[int] = set()
    found: Dict[str, Tuple[Optional[Box], str]] = {}
    slots: Dict[int, Box] = {}
    first_fido: List[Box] = []

    def band(box: Box, reach: float) -> Callable[[int], bool]:
        """Words whose centre is on the same table row as the box (cells may wrap on two lines)."""
        top, bottom = box[1] - reach * (box[3] - box[1]), box[3] + reach * (box[3] - box[1])
        return lambda i: top <= (words[i]["y0"] + words[i]["y1"]) / 2 <= bottom

    def ends_with_colon(i: int) -> bool:
        return words[i]["text"].rstrip().endswith(":")

    def right_of(label: Optional[dict]) -> Callable[[int], bool]:
        """Words on the text line of a "label:" and after it; no word at all when the label was not read."""
        if label is None:
            return lambda i: False
        on_line = band((label["x0"], label["y0"], label["x1"], label["y1"]), 0.3)
        return lambda i: on_line(i) and words[i]["x0"] >= label["x1"] - 2

    def tipo_label() -> Optional[dict]:
        """The "Tipo Pratica:" label of the detail header, not "N° Pratica:" on the same line."""
        for i, word in enumerate(words):
            text = norm(word["text"])
            if not ends_with_colon(i) or not text.endswith("pratica"):
                continue
            before = words[i - 1] if i > 0 and words[i - 1]["row"] == word["row"] else None
            if text.startswith("tipo") or (before is not None and norm(before["text"]).endswith("tipo")):
                return word
        return None

    def left_half_limit() -> Optional[float]:
        """The loans table is two tables side by side, proposed loans and existing ones: x where the second starts.

        The fields to review are those of the proposed loan. On a replacement the existing loan repeats
        the same account, description and amount a few columns to the right.
        """
        header = find_label(words, "rapporto", in_fidi)
        amount = find_label(words, "importo", in_fidi)
        if header is None or amount is None:
            return None
        later = [w for i, w in enumerate(words) if in_fidi(i) and w["row"] == header["row"] and w["x0"] > amount["x1"]
                 and norm(w["text"]).endswith("fido")]
        if not later:
            return None
        second = min(later, key=lambda w: w["x0"])
        return second["x0"] - (26 if norm(second["text"]) == "fido" else 4)  # "N°" is a word of its own before "Fido"

    def elenco_row() -> Optional[dict]:
        header = find_label(words, "ndg", first_table)
        return next((w for i, w in enumerate(words) if first_table(i) and header is not None and w["y0"] > header["y1"]
                     and re.fullmatch(r"\d{7,8}", w["text"])), None)

    def in_fidi(i: int) -> bool:
        row = words[i]["row"]
        return (title["FIDI"] is None or row > title["FIDI"]) and (title["GARANZIE"] is None or row < title["GARANZIE"])

    def first_table(i: int) -> bool:
        return second_table is None or words[i]["row"] < second_table

    def in_table(i: int) -> bool:
        return words[i]["row"] not in ndg_rows and not words[i]["text"].rstrip().endswith(":")

    def elenco_zone(field: str) -> Optional[Box]:
        data = elenco_row()
        label = find_label(words, ELENCO_LABELS[field], first_table)
        if data is None:
            return None if label is None else (label["x0"] - 45, label["y1"] + 4, label["x1"] + 75, label["y1"] + 62)
        if label is None:  # column scrolled out of view or clipped: show the stretch of the row where it would be
            return (size[0] - 900, data["y0"] - 16, size[0], data["y1"] + 16) if field == "Evidenze" else (0, data["y0"] - 16, 1000, data["y1"] + 16)
        if field == "Evidenze":  # a run of icons to the right of the column title
            return (label["x0"] - 45, data["y0"] - 12, label["x1"] + 75, data["y1"] + 12)
        return (label["x0"] - 25, data["y0"] - 12, label["x1"] + 45, data["y1"] + 12)

    def fidi_zone(field: str) -> Optional[Box]:
        label = find_label(words, FIDI_FIELDS[field], in_fidi)
        top, bottom = (first_fido[0][1] - 12, first_fido[0][3] + 12) if first_fido else (None, None)
        if label is not None:  # cells are centred under their title and about as wide: stay clear of the next column
            return (label["x0"] - 16, label["y1"] - 6 if top is None else top, label["x1"] + 16, label["y1"] + 44 if bottom is None else bottom)
        amount = find_label(words, "importo", in_fidi)
        if field == "Tipo Op." and amount is not None:  # this header is often clipped: it is the column after the amount
            right = amount["x1"] + 88 if limit is None else min(amount["x1"] + 88, limit)
            return (amount["x1"] + 2, amount["y1"] - 6 if top is None else top, right, amount["y1"] + 44 if bottom is None else bottom)
        anchor = next((w for w in words if w["text"].strip() == "FIDI"), None)
        inside = [i for i, w in enumerate(words) if in_fidi(i) and anchor is not None and w["x0"] >= anchor["x0"] - 20]
        return union(words, inside) if inside else None

    def soggetti_zone(column: str, slot: int) -> Optional[Box]:
        labels = {name: find_label(words, key, in_table) for name, key in SOGGETTI_COLUMNS.items()}
        label = labels[column]
        if label is None:
            return None
        if slot in slots:  # the NDG of that row was found: same line, this column
            ndg = slots[slot]
            right = labels["RUOLO"]["x0"] - 8 if column == "DENOMINAZIONE" and labels["RUOLO"] is not None else label["x0"] + 260
            return (label["x0"] - 10, ndg[1] - 14, right, ndg[3] + 14)
        left = labels["NDG"]["x0"] - 50 if labels["NDG"] is not None else label["x0"] - 60
        right = labels["RUOLO"]["x0"] + 260 if labels["RUOLO"] is not None else label["x0"] + 700
        bottom = max([b[3] for b in slots.values()] + [label["y1"]]) + 70
        return (left, label["y1"] + 2, right, bottom)  # the whole table: the reviewer sees that the row is not there

    def scheda_zone(field: str) -> Optional[Box]:
        label = find_label(words, SCHEDA_LABELS[field])
        return None if label is None else (label["x0"] - 140, label["y1"] + 2, label["x0"] + 480, label["y1"] + 70)

    def zone(field: str) -> Optional[Box]:
        slot = SLOT.fullmatch(field)
        if kind.startswith("elenco") and field in ELENCO_LABELS:
            return elenco_zone(field)
        if field in FIDI_FIELDS:
            return fidi_zone(field)
        if slot:
            return soggetti_zone(slot.group(1), int(slot.group(2)))
        if field in SCHEDA_LABELS:
            return scheda_zone(field)
        if detail and field in ("NDG", "DENOMINAZIONE"):
            label = find_label(words, "ndg", ends_with_colon)
            if label is not None:
                return (label["x0"] - 6, label["y0"] - 6, label["x1"] + 420, label["y1"] + 6)
            below = find_label(words, "natura")  # the OCR skipped the banner: it is the bar right above this line
            return None if below is None else (below["x0"] - 8, below["y0"] - 23, below["x0"] + 640, below["y0"] - 4)
        if detail and field == "Tipo":
            label = tipo_label()
            return None if label is None else (label["x0"] - 40, label["y0"] - 6, label["x1"] + 190, label["y1"] + 6)
        if detail and field == "Filiale relazione":
            label = find_label(words, "relazione")
            return None if label is None else (label["x0"] - 50, label["y0"] - 6, label["x1"] + 190, label["y1"] + 6)
        return None

    def rank(item: Tuple[str, str]) -> int:
        return 0 if item[0] in HEADER_FIELDS else 1 if item[0].startswith("NDG ") or item[0] == "n° FIDO" else 2

    def both(first: Allowed, second: Allowed) -> Allowed:
        if first is None or second is None:
            return first or second
        return lambda i: first(i) and second(i)

    limit = left_half_limit()
    proposed: Allowed = None if limit is None else lambda i: (words[i]["x0"] + words[i]["x1"]) / 2 < limit

    for field, value in sorted(fields, key=rank):
        idx: List[int] = []
        if value.strip():
            if field in NOTE_FIELDS:
                block = note_frame(lines, value)
                if block is not None:
                    taken.update(i for i, w in enumerate(words)
                                 if block[0] <= (w["x0"] + w["x1"]) / 2 <= block[2] and block[1] <= (w["y0"] + w["y1"]) / 2 <= block[3])
                    found[field] = (block, "esatta")
                    continue
            else:
                allowed: Allowed = None
                slot = SLOT.fullmatch(field)
                if kind.startswith("elenco"):
                    data = elenco_row()
                    on_row = band((data["x0"], data["y0"], data["x1"], data["y1"]), 0.6) if data is not None and field in ELENCO_LABELS else None
                    allowed = both(first_table, on_row)
                elif detail and field in ("NDG", "DENOMINAZIONE"):
                    # the banner only: when the OCR skipped it, the same number in the table below is another field
                    allowed = lambda i: words[i]["row"] in ndg_rows  # noqa: E731
                elif detail and field == "Tipo":
                    allowed = right_of(tipo_label())
                elif detail and field == "Filiale relazione":
                    allowed = right_of(find_label(words, "relazione", ends_with_colon))
                elif slot:
                    same_row = band(slots[int(slot.group(2))], 0.45) if slot.group(1) != "NDG" and int(slot.group(2)) in slots else None
                    allowed = both(in_table, same_row)
                elif field in FIDI_FIELDS:
                    allowed = both(both(in_fidi, proposed), band(first_fido[0], 0.6) if first_fido and field != "n° FIDO" else None)
                elif field in SCHEDA_LABELS:
                    area = scheda_zone(field)
                    if area is not None:
                        allowed = lambda i, a=area: a[0] <= words[i]["x0"] <= a[2] and a[1] - 4 <= words[i]["y0"] <= a[3]  # noqa: E731
                idx = best_alignment(words, value, taken, allowed)
                if len(idx) < len([t for t in value.split() if norm(t)]):
                    # part of the value is missing: the OCR split the cell into other words, or read its two
                    # lines as one row with the second line first, where the reading-order pass stops half way
                    idx = run_align(words, value, taken, allowed) or max(idx, near_align(words, value, taken, allowed), key=len)
        if idx:
            heights = sorted(words[i]["y1"] - words[i]["y0"] for i in idx)
            spread = max(words[i]["y1"] for i in idx) - min(words[i]["y0"] for i in idx)
            if spread > 2.6 * heights[len(heights) // 2]:
                idx = []  # the words found belong to different table rows: better a zone than a wrong frame
        if idx:
            taken.update(idx)
            frame = snap_to_ink(words, idx, line_spans)
            first = min(idx, key=lambda i: (words[i]["row"], words[i]["x0"]))
            if words[first]["text"].startswith("-") and not value.lstrip().startswith("-") and words[first]["x0"] <= frame[0] + 1:
                # the banner reads "NDG: number - name": when the OCR ties the dash to the name, leave the dash out
                glyphs = [span for span in line_spans.get(words[first]["line"], []) if span[1] > frame[0]]
                if len(glyphs) > 1 and glyphs[0][1] - glyphs[0][0] <= 6:
                    frame = (float(glyphs[1][0]), frame[1], frame[2], frame[3])
            if value.rstrip().endswith("..."):
                # the dots the application puts after a cut value are small marks drawn apart from the word
                line = words[max(idx, key=lambda i: words[i]["x1"])]["line"]
                for a, b in line_spans.get(line, []):
                    if 0 <= a - frame[2] <= 10 and b - a <= 16:
                        frame = (frame[0], frame[1], float(b), frame[3])
            found[field] = (frame, "esatta")
            if field.startswith("NDG "):
                slots[int(field.split()[1])] = found[field][0]
            if field == "n° FIDO":
                first_fido.append(found[field][0])
        else:
            area = zone(field)
            found[field] = (area, "zona") if area is not None else (None, "nessuna")
    return found


def clamp(box: Box, size: Tuple[int, int]) -> Tuple[int, int, int, int]:
    return (max(0, int(box[0])), max(0, int(box[1])), min(size[0], int(box[2] + 0.999)), min(size[1], int(box[3] + 0.999)))


def context_crop(img: Image.Image, box: Optional[Box], how: str, wide_page: bool, path: str) -> Tuple[int, int]:
    """Crop around the value with a frame on it; returns the display size in pixels."""
    if box is None:
        crop_box = (0, 0, img.width, img.height) if wide_page or img.width <= 1200 else (150, 255, min(1100, img.width), img.height)
        crop = img.crop(crop_box)
        scale = min(1.0, 760 / crop.width, 520 / crop.height)
    else:
        pad_x = max(36.0, (380 - (box[2] - box[0])) / 2)
        pad_y = max(16.0, (64 - (box[3] - box[1])) / 2)
        crop_box = clamp((box[0] - pad_x, box[1] - pad_y, box[2] + pad_x, box[3] + pad_y), img.size)
        crop = img.crop(crop_box)
        scale = min(2.0, 760 / crop.width, 520 / crop.height)
    shown = (max(1, int(crop.width * scale)), max(1, int(crop.height * scale)))
    # a long note is shown smaller than the screen to fit the cell, but its pixels are all kept:
    # zooming in Excel then shows the text as sharp as on the screenshot
    stored = max(scale, 1.0)
    crop = crop.resize((max(1, int(crop.width * stored)), max(1, int(crop.height * stored))), Image.LANCZOS)
    if box is not None:
        draw = ImageDraw.Draw(crop)
        x0, y0 = (box[0] - 3 - crop_box[0]) * stored, (box[1] - 3 - crop_box[1]) * stored
        x1, y1 = (box[2] + 3 - crop_box[0]) * stored, (box[3] + 3 - crop_box[1]) * stored
        draw.rectangle((x0, y0, x1, y1), outline=(220, 30, 30) if how == "esatta" else (240, 140, 0), width=round(3 * stored / scale))
    # 64 colours are enough for a screenshot and keep the workbook a quarter of the size
    crop.quantize(colors=64, dither=Image.Dither.NONE).save(path, optimize=True)
    return shown


def pixel_matrix(img: Image.Image, box: Box, path: str) -> Tuple[int, int]:
    """One square per screen pixel: black = stroke, grey = faint edge, white = background.

    A plain enlargement keeps the coloured sub-pixel fringes of the screen font, which hide the shape
    of a 7-pixel digit; three tones against the background colour show it.
    """
    x0, y0, x1, y1 = clamp((box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2), img.size)
    width, height = x1 - x0, y1 - y0
    px = img.load()
    background = Counter(px[x, y] for y in range(y0, y1) for x in range(x0, x1)).most_common(1)[0][0]
    cell = max(3, min(12, 456 // max(width, 1), 236 // max(height, 1)))
    out = Image.new("RGB", (width * cell + 1, height * cell + 1), "white")
    draw = ImageDraw.Draw(out)
    for y in range(height):
        for x in range(width):
            pixel = px[x0 + x, y0 + y]
            ink = max(abs(pixel[c] - background[c]) for c in range(3))
            tone = (0, 0, 0) if ink >= 140 else (150, 150, 150) if ink >= 60 else (255, 255, 255)
            draw.rectangle((x * cell, y * cell, (x + 1) * cell, (y + 1) * cell), fill=tone, outline=(222, 222, 222))
    out.save(path, optimize=True)
    return out.size


def place(ws: Any, path: str, size: Tuple[int, int], col: int, row: int) -> None:
    """Anchor the picture to its cell so that it hides with the row when the sheet is filtered."""
    picture = XLImage(path)
    picture.width, picture.height = size
    start = AnchorMarker(col=col, colOff=pixels_to_EMU(4), row=row, rowOff=pixels_to_EMU(4))
    end = AnchorMarker(col=col, colOff=pixels_to_EMU(4 + size[0]), row=row, rowOff=pixels_to_EMU(4 + size[1]))
    picture.anchor = TwoCellAnchor(editAs="twoCell", _from=start, to=end)
    ws.add_image(picture)


def main() -> None:
    os.makedirs(work_dir, exist_ok=True)
    with open(os.path.join(input_dir, "dati.csv"), encoding="utf-8-sig", newline="") as fh:
        gt_rows = list(csv.DictReader(fh, delimiter=";"))
    ocr = json.load(open(os.path.join(baseline_dir, "prove", "ocr-locale-rapidocr", "rapid_v6_small_1x.json"), encoding="utf-8"))
    summary = json.load(open(os.path.join(baseline_dir, "summary.json"), encoding="utf-8"))
    gemini_wrong = {(r["screen"], r["field"]) for r in summary["error_rows"]}
    outputs = json.load(open(os.path.join(baseline_dir, "run1.outputs.json"), encoding="utf-8"))
    sys.path.insert(0, os.getcwd())
    from extraction.fields import CSV_TO_SCHEMA

    by_screen: Dict[str, List[dict]] = {}
    fics: Dict[str, Set[str]] = {}
    for row in gt_rows:
        by_screen.setdefault(row["Fotogramma"], []).append(row)
        if row["Denominazione da attribuire"] == "Note della richiesta":
            fics.setdefault(row["Fotogramma"].split("__")[0], set()).update(re.findall(r"FICS:\s*\d+/(\d+)", row["Valore rilevato"]))

    def screen_key(screen: str) -> Tuple[str, int, str]:
        practice, stem = screen.split("__", 1)
        return practice, PAGE_ORDER.index(kind_of(stem)) if kind_of(stem) in PAGE_ORDER else 99, stem.lower()

    wb = Workbook()
    ws = wb.active
    ws.title = "Revisione"
    headers = ["N.", "Pratica", "Schermata", "Campo", "Immagine (riquadro rosso = valore da leggere)",
               "Pixel per pixel (solo numeri piccoli)", "Valore letto", "Esito", "Valore corretto", "Note",
               "Priorità", "Perché guardarlo con attenzione", "Gemini ha letto", "Riquadro", "ID schermata"]
    widths = [6, 11, 30, 30, 112, 68, 44, 16, 44, 30, 10, 52, 30, 10, 34]
    font = Font(name="Arial", size=10)
    bold = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    yellow = PatternFill("solid", start_color="FFFF00")
    thin = Side(style="thin", color="BBBBBB")
    wrap = Alignment(wrap_text=True, vertical="top")
    for col, (title, width) in enumerate(zip(headers, widths), start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.font, cell.fill, cell.alignment = bold, PatternFill("solid", start_color="1F4E78"), Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[cell.column_letter].width = width
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "E2"

    counts = {"esatta": 0, "zona": 0, "nessuna": 0, "alta": 0}
    excel_row = 1
    for screen in sorted(by_screen, key=screen_key):
        practice, stem = screen.split("__", 1)
        img = Image.open(os.path.join(input_dir, screen + ".png")).convert("RGB")
        lines = [{"text": t, "score": s, "box": b} for t, s, b in ocr[screen]["items"]]
        ocr_text = re.sub(r"\s+", "", "".join(t for t, _, _ in ocr[screen]["items"])).lower()
        rows = by_screen[screen]
        located = locate_screen(stem, [(r["Denominazione da attribuire"], r["Valore rilevato"]) for r in rows], lines, np.asarray(img))
        wide_page = kind_of(stem).startswith(("elenco", "scheda"))
        for index, row in enumerate(rows):
            field, value = row["Denominazione da attribuire"], row["Valore rilevato"]
            box, how = located[field]
            counts[how] += 1
            excel_row += 1
            crop_path = os.path.join(work_dir, f"{screen}__{index:02d}.png")
            size = context_crop(img, box, how, wide_page, crop_path)
            place(ws, crop_path, size, 4, excel_row - 1)
            height = size[1]
            small = field in SMALL_DIGITS and not kind_of(stem).startswith("elenco")
            pixel_status = ""
            if small and how == "esatta" and box is not None:
                matrix_path = os.path.join(work_dir, f"{screen}__{index:02d}_px.png")
                matrix_size = pixel_matrix(img, box, matrix_path)
                place(ws, matrix_path, matrix_size, 5, excel_row - 1)
                height = max(height, matrix_size[1])
                if re.search(r"[68]", value):
                    pixel_status, tested = six_eight_check(img, clamp((box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2), img.size), value)
                    counts["pixel " + pixel_status] = counts.get("pixel " + pixel_status, 0) + 1
            ws.row_dimensions[excel_row].height = min(409, (height + 10) * 0.75)

            reasons = []
            schema_key = CSV_TO_SCHEMA.get(field.strip())
            gemini = (outputs.get(screen, {}).get("fields", {}).get(schema_key) or {}).get("value")
            if (screen, schema_key) in gemini_wrong:
                reasons.append("Gemini ha letto un valore diverso")
            if value.strip() and field not in NOTE_FIELDS and not all(token.lower() in ocr_text for token in value.split()):
                reasons.append("l'OCR locale non lo trova scritto così")
            if pixel_status == "discorda":
                reasons.append("ATTENZIONE: per il controllo automatico sui pixel almeno un 6 o un 8 è l'altra cifra: "
                               + ", ".join(f"carattere {pos}: atteso {exp}, pixel {read}" for pos, exp, read, _ in tested if exp != read))
            elif small and re.search(r"[68]", value) and pixel_status != "conferma":
                reasons.append("numeri piccoli: a occhio il 6 sembra un 8 e il controllo automatico qui non è riuscito"
                               + (" del tutto" if pixel_status == "parziale" else "") + ", guarda la colonna pixel per pixel")
            if how != "esatta" and value.strip():
                reasons.append("posizione stimata (riquadro arancione)" if how == "zona" else "posizione non individuata")
            checked = []
            if pixel_status == "conferma":
                checked.append("già controllato sui pixel in automatico: "
                               + ("1 cifra 6/8 confermata" if len(tested) == 1 else f"{len(tested)} cifre 6/8 confermate"))
            if SLOT.fullmatch(field) and field.startswith("NDG") and re.search(r"[68]", value) and pixel_status != "conferma":
                checked.append("già controllato: cifre 6 e 8 verificate sui pixel con il controllo dedicato agli NDG dei soggetti")
            if field == "Rapporto" and any(re.sub(r"\s+", "", value).endswith(n) for n in fics.get(practice, ())):
                checked.append("già controllato: coincide con il numero FICS scritto nella nota")
            if field == "Scadenza" and "6" in value and practice in SCADENZA_CHECKED:
                checked.append("già controllato: letto cifra per cifra sulla griglia dei pixel")
            priority = "ALTA" if reasons else "normale"
            counts["alta"] += priority == "ALTA"
            if not value.strip():
                reasons.append("atteso vuoto: conferma che il valore non è a schermo")
            if row.get("Nota"):
                reasons.append("nota di chi ha trascritto: " + row["Nota"])

            values = [excel_row - 1, practice, f"{practice}\\{stem}.png", field, None, None, value if value.strip() else "(vuoto)",
                      None, None, None, priority, "; ".join(reasons + checked), "" if gemini is None else str(gemini),
                      {"esatta": "rosso", "zona": "arancione", "nessuna": "assente"}[how], screen]
            for col, item in enumerate(values, start=1):
                cell = ws.cell(row=excel_row, column=col, value=item)
                cell.font, cell.alignment, cell.border = font, wrap, Border(bottom=thin)
                if isinstance(item, str):
                    cell.data_type = "s"  # never let Excel evaluate a transcribed value as a formula
                if col in (8, 9, 10):
                    cell.fill = yellow
    last = excel_row
    check = DataValidation(type="list", formula1='"OK,ERRATO,NON LEGGIBILE"', allow_blank=True, showErrorMessage=True,
                           errorTitle="Esito", error="Scegli OK, ERRATO oppure NON LEGGIBILE")
    ws.add_data_validation(check)
    check.add(f"H2:H{last}")
    ws.auto_filter.ref = f"A1:O{last}"

    info = wb.create_sheet("Istruzioni", 0)
    for letter, width in zip("ABCD", (26, 34, 22, 34)):
        info.column_dimensions[letter].width = width
    text = [
        ("Revisione manuale della ground truth", True),
        (f"{last - 1} valori di {len(by_screen)} schermate (12 pratiche). Foglio \"Revisione\": una riga per valore.", False),
        ("", False),
        ("Cosa compilare: solo le celle gialle (colonne Esito, Valore corretto, Note).", True),
        ("1. Guarda l'immagine: il riquadro rosso segna il valore da leggere. Arancione = zona dove dovrebbe trovarsi.", False),
        ("2. Confronta con la colonna \"Valore letto\".", False),
        ("3. Esito: OK se coincide carattere per carattere, ERRATO se è diverso, NON LEGGIBILE se dall'immagine non si capisce.", False),
        ("4. Se ERRATO scrivi il valore giusto in \"Valore corretto\". Se OK lascialo vuoto.", False),
        ("5. \"(vuoto)\" significa che a schermo non deve esserci nulla per quel campo: OK se è così.", False),
        ("   Se invece un valore c'è scrivilo in \"Valore corretto\"; se il valore letto non doveva esserci scrivi (vuoto).", False),
        ("", False),
        ("Numeri piccoli (NDG dei soggetti, rapporto, scadenza, importo dei fidi).", True),
        ("Nell'immagine ingrandita il 6 sembra un 8 anche a occhio. Per questo un programma ha già controllato i pixel di ogni 6 e 8:", False),
        ("dove leggi \"già controllato\" nella colonna \"Perché guardarlo con attenzione\", la distinzione fra 6 e 8 è verificata e resta da guardare il resto del valore.", False),
        ("Dove il controllo non è riuscito usa la colonna \"Pixel per pixel\": un quadretto per ogni pixel dello schermo.", False),
        ("Nel 6 la barra orizzontale è sulla terza riga di quadretti e tocca il tratto sinistro; nell'8 la strozzatura è sulla quarta riga, al centro.", False),
        ("In caso di dubbio scegli NON LEGGIBILE: il controllo sicuro è sull'applicativo, ingrandendo la pagina.", False),
        ("", False),
        ("Note lunghe: l'immagine è rimpicciolita per stare nella cella ma conserva tutti i pixel. Aumenta lo zoom di Excel (Ctrl + rotellina) per leggerla.", False),
        ("", False),
        ("Per cominciare dai casi dubbi filtra la colonna Priorità su ALTA. Non ordinare le righe: le immagini non seguono l'ordinamento.", False),
        ("Le colonne \"Gemini ha letto\" e \"Perché guardarlo con attenzione\" sono solo un aiuto, non la risposta.", False),
        ("", False),
        ("Esempio di righe compilate (valori di fantasia):", True),
    ]
    for r, (line, strong) in enumerate(text, start=1):
        cell = info.cell(row=r, column=1, value=line)
        cell.font = Font(name="Arial", size=12 if r == 1 else 10, bold=strong)
    start = len(text) + 1
    example = [("Campo", "Valore letto", "Esito", "Valore corretto"),
               ("Scadenza", "381 mesi", "ERRATO", "361 mesi"),
               ("NDG 2", "36214602", "OK", ""),
               ("Tipo", "(vuoto)", "OK", "")]
    for r, line in enumerate(example, start=start):
        for c, item in enumerate(line, start=1):
            cell = info.cell(row=r, column=c, value=item)
            cell.font = Font(name="Arial", size=10, bold=r == start)
            cell.data_type = "s"
            if r > start and c in (3, 4):
                cell.fill = yellow
    wb.active = 1
    wb.save(out_path)
    print(f"rows={last - 1} frame on the value={counts['esatta']} zone={counts['zona']} no position={counts['nessuna']} priority ALTA={counts['alta']}")
    print("automatic 6/8 check:", {k[6:]: v for k, v in counts.items() if k.startswith("pixel ")})
    print("saved", out_path, f"{os.path.getsize(out_path) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
