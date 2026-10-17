"""Align reviewed field values to source OCR words for offline training.

Geometry and field-region rules were adapted from the manually checked
2026-10-07 review-workbook generator. Historical scripts remain unchanged.
Only source OCR words become tokens; empty values never acquire a synthetic box.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np
from PIL import Image

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
NOTE_FIELDS = {"Note della richiesta", "Note Scheda Privati"}
PARTIAL_TEXT_FIELDS = NOTE_FIELDS | {"Ultima validazione scheda privati", "Scadenza", "Tipo Op."}
SLOT = re.compile(r"(NDG|DENOMINAZIONE|RUOLO) (\d)")

def _norm(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKC", text).casefold() if char.isalnum())


def _comparison(text: str) -> str:
    """Normalize presentation without discarding punctuation or inventing word boundaries."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def _similar(first: str, second: str) -> bool:
    first, second = _norm(first), _norm(second)
    if not first or not second:
        return False
    if first == second:
        return True
    return min(len(first), len(second)) >= 4 and SequenceMatcher(None, first, second, autojunk=False).ratio() >= 0.8


def _cost(prev: dict, cand: dict) -> float:
    """Reading-order distance: same row to the right is cheap; next rows in the same column cost more."""
    if cand["row"] == prev["row"] and cand["x0"] >= prev["x0"]:
        return cand["x0"] - prev["x1"]
    if cand["row"] > prev["row"]:
        dy = cand["y0"] - prev["y1"]
        return 3 * dy + abs(cand["x0"] - prev["x0"])
    return float("inf")


def _align_value(words: List[dict], value: str, taken: Set[int], allowed: Allowed = None) -> List[int]:
    tokens = [t for t in value.split() if _norm(t)]
    if not tokens:
        return []
    best: Tuple[float, List[int]] = (-1.0, [])
    starts = [i for i, w in enumerate(words) if i not in taken and _similar(w["text"], tokens[0])
              and (allowed is None or allowed(i))]
    for s in starts:
        seq, prev, score = [s], words[s], 1.0
        for tok in tokens[1:]:
            cands = [(i, _cost(prev, w)) for i, w in enumerate(words)
                     if i not in taken and i not in seq and _similar(w["text"], tok)]
            cands = [c for c in cands if c[1] < 60 * (prev["y1"] - prev["y0"])]
            if not cands:
                continue
            i, _ = min(cands, key=lambda c: c[1])
            seq.append(i)
            prev = words[i]
            score += 1
        if score > best[0]:
            best = (score, seq)
    if best[0] >= max(1, 0.7 * len(tokens)):
        return best[1]
    return []

def _kind_of(stem: str) -> str:
    low = stem.lower()
    for prefix in ("elenco_tooltip", "elenco_dx", "elenco", "soggetti", "gestionefidi_tooltip", "gestionefidi_down",
                   "gestionefidi", "note", "scheda_privati"):
        if low.startswith(prefix):
            return prefix
    return "?"


def _char_width(char: str) -> float:
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


def _ink_spans(arr: np.ndarray, box: Tuple[int, int, int, int], gap: int) -> List[Tuple[int, int]]:
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


def _assign_spans(texts: List[str], spans: List[Tuple[int, int]]) -> Optional[Tuple[List[Tuple[float, float]], float]]:
    """Horizontal extent of each word of a line, pairing the words with the inked spans by width.

    The counts often differ: an icon next to the text adds a span, a tight space joins two words,
    a wide gap inside a word splits it. A shortest-path pairing over those four cases keeps the
    words in order. Returns the extents and the cost of the fit, or None when the fit is poor.
    """
    n, m = len(texts), len(spans)
    if not n or not m:
        return None
    model = [max(0.2, sum(_char_width(c) for c in t)) for t in texts]
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


def _build_words(lines: List[dict], arr: np.ndarray) -> Tuple[List[dict], Dict[int, List[Tuple[int, int]]]]:
    """Words of every OCR line with their horizontal extent, sorted in reading order.

    The extents come from the ink of the line (_assign_spans); when that fails the text is spread over
    the line by character widths, and the frame is later snapped to the ink (_snap_to_ink).
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
            spans = _ink_spans(arr, region, gap)
            fit = _assign_spans([piece.group(0) for piece in pieces], spans)
            if fit is not None:
                fits.append((fit[1], -gap, spans, fit[0]))
        if fits:
            _, _, spans, extents = min(fits, key=lambda f: (f[0], f[1]))
        else:
            spans, extents = _ink_spans(arr, region, widest - 1), None
        # frames are trimmed on single glyphs: on the runs of the fit, the dash before a name in bold comes along with it
        line_spans[li] = _ink_spans(arr, region, 1)
        fitted = extents is not None
        if extents is None:
            left, right = (spans[0][0], spans[-1][1]) if spans else (x0, x1)
            scale = (right - left) / (sum(_char_width(c) for c in text) or 1.0)
            extents = [(left + sum(_char_width(c) for c in text[:piece.start()]) * scale,
                        left + sum(_char_width(c) for c in text[:piece.end()]) * scale) for piece in pieces]
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


def _snap_to_ink(words: List[dict], idx: List[int], line_spans: Dict[int, List[Tuple[int, int]]]) -> Box:
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


def _union(words: List[dict], idx: List[int]) -> Box:
    return (min(words[i]["x0"] for i in idx), min(words[i]["y0"] for i in idx),
            max(words[i]["x1"] for i in idx), max(words[i]["y1"] for i in idx))


def _find_label(words: List[dict], key: str, allowed: Allowed = None) -> Optional[dict]:
    for i, word in enumerate(words):
        if _norm(word["text"]).startswith(key) and (allowed is None or allowed(i)):
            return word
    return None


def _permitted(words: List[dict], taken: Set[int], allowed: Allowed) -> List[int]:
    """Indexes of the words a value may use: free, and inside the region its field belongs to."""
    return [i for i in range(len(words)) if i not in taken and (allowed is None or allowed(i))]


def _fold(text: str) -> str:
    """Text as compared when looking for a value: the OCR reads the small 6 as 8, and "381 mesi" is where "361 mesi" is.

    Only for finding the place. What the reviewer checks is the transcribed value, never the OCR text.
    """
    return text.replace("8", "6")


def _folded(words: List[dict], view: List[int]) -> List[dict]:
    return [dict(words[i], text=_fold(words[i]["text"])) for i in view]


def _best_alignment(words: List[dict], value: str, taken: Set[int], allowed: Allowed) -> List[int]:
    """_align_value tried from every possible first word, keeping the most complete and most compact result.

    _align_value alone returns the first start that matches as many tokens as any other: the tooltip
    "55-IPOTECA DI PRIMO GRADO" then starts on the cell "IPOTECA I GR." above it and spans two lines.
    It also checks `allowed` on the first word only, so it runs here on the _permitted words alone:
    otherwise the last group of a loan account jumps to the copy of the account in the next table.
    """
    value = _fold(value)
    tokens = [t for t in value.split() if _norm(t)]
    if not tokens:
        return []
    view = _permitted(words, taken, allowed)
    sub = _folded(words, view)
    wanted = Counter(_norm(t) for t in tokens)
    best: List[int] = []
    best_key: Optional[Tuple[int, int, int]] = None
    for start, word in enumerate(sub):
        if not _similar(word["text"], tokens[0]):
            continue
        seq = _align_value(sub, value, set(), lambda i, only=start: i == only)
        if not seq:
            continue
        got = Counter(_norm(sub[i]["text"]) for i in seq)
        exact = sum(min(count, got[key]) for key, count in wanted.items())
        heights = sorted(sub[i]["y1"] - sub[i]["y0"] for i in seq)
        spread = max(sub[i]["y1"] for i in seq) - min(sub[i]["y0"] for i in seq)
        # in text lines, not pixels: two copies of a value on one line tie, and the first in reading order wins
        key = (len(seq), exact, -round(spread / heights[len(heights) // 2]))
        if best_key is None or key > best_key:
            best, best_key = seq, key
    return [view[i] for i in best]


def _run_align(words: List[dict], value: str, taken: Set[int], allowed: Allowed) -> List[int]:
    """Words that, read one after the other, spell the value letter by letter.

    For the cells the OCR split into other words than the transcription: "DE MARCHIALESSANDRO",
    or "KOLAALTIN,KOLA" with "KLEJDI" on the next line of the cell. A value may go on for three lines.
    """
    target = _norm(_fold(value))
    if len(target) < 4:
        return []
    by_line: Dict[int, List[int]] = {}
    for i in _permitted(words, taken, allowed):
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
                    letters = _norm(_fold(words[members[b]]["text"]))
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


def _note_frame(lines: List[dict], note: str) -> Optional[Box]:
    """Frame of a long note: the block of OCR lines whose text is a piece of the note, in the order of the note.

    A note is compared line by line, not word by word: the menu on the left of the page shares
    plenty of short words with any note. Two kinds of line cannot be matched and are added when they
    touch the block: a line the OCR could not read, for as long as text of the note is unaccounted
    for, and a line too short to be told from chance, when it is exactly the next piece of the note.
    """
    target = _norm(note)
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
        text = _norm(line["text"])
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


def _near_align(words: List[dict], value: str, taken: Set[int], allowed: Allowed) -> List[int]:
    """Second attempt when the reading-order alignment finds nothing or misses part of the value.

    Two cases seen on these screens: the OCR drops the space inside a cell ("KOLAENKELEDA"), and a
    two-line cell is merged into one OCR row with its lines swapped ("Finanza" before "Nuova").
    """
    value = _fold(value)
    tokens = [t for t in value.split() if _norm(t)]
    if not tokens:
        return []
    view = _permitted(words, taken, allowed)
    sub = _folded(words, view)
    whole = _norm(value)
    for i, word in enumerate(sub):
        if _norm(word["text"]) == whole:
            return [view[i]]
    best: List[int] = []
    for start, word in enumerate(sub):
        if not _similar(word["text"], tokens[0]):
            continue
        seq = [start]
        height = word["y1"] - word["y0"]
        for token in tokens[1:]:
            x0, y0, x1, y1 = _union(sub, seq)
            options = []
            for i, cand in enumerate(sub):
                if i in seq or not _similar(cand["text"], token):
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


def _scheda_region(words: List[dict], field: str) -> Optional[Box]:
    label = _find_label(words, SCHEDA_LABELS[field])
    return None if label is None else (label["x0"] - 140, label["y1"] + 2, label["x0"] + 480, label["y1"] + 70)


def _note_indices(words: List[dict], lines: List[dict], note: str) -> List[int]:
    """Select reviewed words in matched note rows, excluding incidental text in the block."""
    frame = _note_frame(lines, note)
    if frame is None:
        return []
    target = _norm(note)
    selected: List[int] = []
    for line_id, line in enumerate(lines):
        members = [i for i, word in enumerate(words) if word["line"] == line_id
                   and frame[0] <= (word["x0"] + word["x1"]) / 2 <= frame[2]
                   and frame[1] <= (word["y0"] + word["y1"]) / 2 <= frame[3]]
        if not members:
            continue
        text = _norm(line["text"])
        matcher = SequenceMatcher(None, text, target, autojunk=False)
        hit = matcher.find_longest_match(0, len(text), 0, len(target))
        if not text or hit.size < min(5, len(text)):
            continue
        window = target[max(0, hit.b - hit.a):max(0, hit.b - hit.a) + len(text)]
        if SequenceMatcher(None, text, window, autojunk=False).ratio() < (0.7 if len(text) >= 20 else 0.9):
            continue
        # A matched row can contain an adjacent label that was not part of the note.
        # Only include words that independently occur in the reviewed text.
        selected.extend(i for i in members if _norm(words[i]["text"]) and _norm(words[i]["text"]) in target)
    return selected


def _order_cell_indices(words: List[dict], indices: List[int]) -> List[int]:
    """Order matched words by local visual lines within the cell, then left-to-right."""
    if len(indices) <= 1:
        return list(indices)
    heights = sorted(max(1.0, words[i]["y1"] - words[i]["y0"]) for i in indices)
    tolerance = 0.5 * heights[len(heights) // 2]
    lines: List[List[int]] = []
    centers: List[float] = []
    for index in sorted(indices, key=lambda i: (words[i]["y0"] + words[i]["y1"]) / 2):
        center = (words[index]["y0"] + words[index]["y1"]) / 2
        if not lines or abs(center - centers[-1]) > tolerance:
            lines.append([index])
            centers.append(center)
        else:
            lines[-1].append(index)
            centers[-1] = sum((words[i]["y0"] + words[i]["y1"]) / 2 for i in lines[-1]) / len(lines[-1])
    return [i for line in lines for i in sorted(line, key=lambda idx: words[idx]["x0"])]


def _field_result(indices: List[int], bbox: Optional[Box], status: str,
                 words: List[dict], expected: str) -> Dict[str, Any]:
    ordered = _order_cell_indices(words, indices)
    text = " ".join(words[i]["text"] for i in ordered)
    return {"indices": ordered, "bbox": bbox, "status": status, "ocr_text": text,
            "exact_text": _comparison(text) == _comparison(expected)}


def _include_punctuation(words: List[dict], indices: List[int], expected: str,
                         allowed: Allowed) -> List[int]:
    """Keep real punctuation words between matched tokens in the same field region."""
    selected = set(indices)
    target = _comparison(expected)
    by_line: Dict[int, List[int]] = {}
    for index in indices:
        by_line.setdefault(words[index]["line"], []).append(index)
    for index, word in enumerate(words):
        text = _comparison(word["text"])
        if index in selected or not text or _norm(text) or text not in target:
            continue
        members = by_line.get(word["line"], [])
        if len(members) < 2 or (allowed is not None and not allowed(index)):
            continue
        left = min(words[member]["x0"] for member in members)
        right = max(words[member]["x1"] for member in members)
        if left <= word["x0"] and word["x1"] <= right:
            selected.add(index)
    return sorted(selected)


def _verified_text_indices(expected: str, words: List[dict], indices: List[int]) -> List[int]:
    """Ordered exact word matches for explicitly permitted partial text supervision."""
    target = [_comparison(token) for token in expected.split() if _comparison(token)]
    candidates = [index for index in indices if _comparison(words[index]["text"])]
    observed = [_comparison(words[index]["text"]) for index in candidates]
    matcher = SequenceMatcher(None, target, observed, autojunk=False)
    return [candidates[position]
            for block in matcher.get_matching_blocks()
            for position in range(block.b, block.b + block.size)]


def align_screen(stem: str, fields: List[Tuple[str, str]], lines: List[dict],
                 image: Image.Image) -> Dict[str, Any]:
    """Return source OCR words and diagnostic alignments of reviewed field values.

    ``exact_text`` preserves punctuation and real word boundaries, without the 6/8
    substitution used for location. A fuzzy location must not become an exact label.
    Notes and the validation timestamp additionally expose ``verified_indices``:
    exact matching word blocks whose remaining words may contain OCR errors.
    All coordinates refer to the original image; neither pixels nor OCR text change.
    """
    if len({field for field, _ in fields}) != len(fields):
        raise ValueError("Duplicate reviewed field names in one screenshot")
    page_stem = stem.split("__", 1)[-1]
    result = _locate_screen(page_stem, fields, lines, np.asarray(image.convert("RGB")))
    for field, expected in fields:
        if field in PARTIAL_TEXT_FIELDS:
            match = result["fields"][field]
            match["verified_indices"] = (
                _verified_text_indices(expected, result["words"], match["indices"])
                if match["status"] == "aligned" else []
            )
    return result
def _locate_screen(stem: str, fields: List[Tuple[str, str]], lines: List[dict],
                  arr: np.ndarray) -> Dict[str, Any]:
    """Locate OCR words within the region owned by each reviewed field."""
    words, line_spans = _build_words(lines, arr)
    kind = _kind_of(stem)
    detail = kind in ("soggetti", "gestionefidi", "gestionefidi_down", "gestionefidi_tooltip", "note")
    ndg_rows = {w["row"] for w in words if _norm(w["text"]) == "ndg" and w["text"].rstrip().endswith(":")}
    title = {name: min((w["row"] for w in words if w["text"].strip() == name), default=None) for name in ("FIDI", "GARANZIE")}
    second_table = min((w["row"] for w in words if _norm(w["text"]) == "attesa"), default=None)
    taken: Set[int] = set()
    found: Dict[str, Dict[str, Any]] = {}
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
            text = _norm(word["text"])
            if not ends_with_colon(i) or not text.endswith("pratica"):
                continue
            before = words[i - 1] if i > 0 and words[i - 1]["row"] == word["row"] else None
            if text.startswith("tipo") or (before is not None and _norm(before["text"]).endswith("tipo")):
                return word
        return None

    def left_half_limit() -> Optional[float]:
        """The loans table is two tables side by side, proposed loans and existing ones: x where the second starts.

        The fields to review are those of the proposed loan. On a replacement the existing loan repeats
        the same account, description and amount a few columns to the right.
        """
        header = _find_label(words, "rapporto", in_fidi)
        amount = _find_label(words, "importo", in_fidi)
        if header is None or amount is None:
            return None
        later = [w for i, w in enumerate(words) if in_fidi(i) and w["row"] == header["row"] and w["x0"] > amount["x1"]
                 and _norm(w["text"]).endswith("fido")]
        if not later:
            return None
        second = min(later, key=lambda w: w["x0"])
        return second["x0"] - (26 if _norm(second["text"]) == "fido" else 4)  # "N°" is a word of its own before "Fido"

    def elenco_row() -> Optional[dict]:
        header = _find_label(words, "ndg", first_table)
        return next((w for i, w in enumerate(words) if first_table(i) and header is not None and w["y0"] > header["y1"]
                     and re.fullmatch(r"\d{7,8}", w["text"])), None)

    def in_fidi(i: int) -> bool:
        row = words[i]["row"]
        return (title["FIDI"] is None or row > title["FIDI"]) and (title["GARANZIE"] is None or row < title["GARANZIE"])

    def first_table(i: int) -> bool:
        return second_table is None or words[i]["row"] < second_table

    def in_table(i: int) -> bool:
        return words[i]["row"] not in ndg_rows and not words[i]["text"].rstrip().endswith(":")


    def rank(item: Tuple[str, str]) -> int:
        return 0 if item[0] in HEADER_FIELDS else 1 if item[0].startswith("NDG ") or item[0] == "n° FIDO" else 2

    def both(first: Allowed, second: Allowed) -> Allowed:
        if first is None or second is None:
            return first or second
        return lambda i: first(i) and second(i)

    limit = left_half_limit()
    proposed: Allowed = None if limit is None else lambda i: (words[i]["x0"] + words[i]["x1"]) / 2 < limit


    unresolved_regions: List[Tuple[str, str, Allowed, Optional[Box]]] = []

    for field, value in sorted(fields, key=rank):
        if not value.strip():
            found[field] = _field_result([], None, "empty", words, value)
            continue
        allowed: Allowed = None
        fallback_area: Optional[Box] = None
        slot = SLOT.fullmatch(field)
        if kind.startswith("elenco"):
            data = elenco_row()
            on_row = band((data["x0"], data["y0"], data["x1"], data["y1"]), 0.6) if data is not None and field in ELENCO_LABELS else None
            allowed = both(first_table, on_row)
        elif detail and field in ("NDG", "DENOMINAZIONE"):
            if ndg_rows:
                allowed = lambda i: words[i]["row"] in ndg_rows
            else:
                top_lbl = _find_label(words, "pratica", ends_with_colon)
                bot_lbl = _find_label(words, "giuridica", ends_with_colon) or _find_label(words, "relazione", ends_with_colon)
                if top_lbl is not None and bot_lbl is not None:
                    allowed = lambda i, r0=top_lbl["row"], r1=bot_lbl["row"]: r0 < words[i]["row"] < r1
        elif detail and field == "Tipo":
            allowed = right_of(tipo_label())
        elif detail and field == "Filiale relazione":
            allowed = right_of(_find_label(words, "relazione", ends_with_colon))
        elif slot:
            same_row = band(slots[int(slot.group(2))], 0.45) if slot.group(1) != "NDG" and int(slot.group(2)) in slots else None
            allowed = both(in_table, same_row)
        elif field in FIDI_FIELDS:
            allowed = both(both(in_fidi, proposed), band(first_fido[0], 0.6) if first_fido and field != "n° FIDO" else None)
        elif field in SCHEDA_LABELS:
            area = _scheda_region(words, field)
            fallback_area = area
            if area is not None:
                allowed = lambda i, a=area: a[0] <= words[i]["x0"] <= a[2] and a[1] - 4 <= words[i]["y0"] <= a[3]
        if field in NOTE_FIELDS:
            idx = _note_indices(words, lines, value)
        else:
            # Find the region's best candidate before resolving ownership conflicts.
            idx = _best_alignment(words, value, set(), allowed)
            if len(idx) < len([token for token in value.split() if _norm(token)]):
                idx = _run_align(words, value, set(), allowed) or max(idx, _near_align(words, value, set(), allowed), key=len)
            if idx:
                heights = sorted(words[i]["y1"] - words[i]["y0"] for i in idx)
                spread = max(words[i]["y1"] for i in idx) - min(words[i]["y0"] for i in idx)
                if spread > 2.6 * heights[len(heights) // 2]:
                    idx = []
        idx = _include_punctuation(words, idx, value, allowed)
        if not idx:
            unresolved_regions.append((field, value, allowed, fallback_area))
            found[field] = _field_result([], fallback_area, "unresolved", words, value)
            continue
        frame = _snap_to_ink(words, idx, line_spans)
        collisions = {i for i in idx if i in taken}
        status = "conflict" if collisions else "aligned"
        found[field] = _field_result(idx, frame, status, words, value)
        if collisions:
            for previous in found.values():
                if set(previous["indices"]) & collisions:
                    previous["status"] = "conflict"
        taken.update(idx)
        if field.startswith("NDG "):
            slots[int(field.split()[1])] = frame
        if field == "n° FIDO":
            first_fido.append(frame)
    for field, value, allowed, fallback_area in unresolved_regions:
        if allowed is not None:
            candidates = _permitted(words, taken, allowed)
            if candidates:
                fallback_area = _union(words, candidates)
        found[field] = _field_result([], fallback_area, "unresolved", words, value)
    return {"words": words, "fields": found}


