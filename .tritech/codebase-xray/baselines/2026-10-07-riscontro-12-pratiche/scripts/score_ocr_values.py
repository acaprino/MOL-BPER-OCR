"""Score raw OCR text against dati.csv: values read, and digit substitutions on the small-font fields.

Usage: python -I score_ocr_values.py <dati.csv> <ocr.json>
"Read" follows the 2026-09-29 benchmark: the ground-truth value, lowercased and without spaces,
appears in the OCR text of its screenshot. Long notes are scored by the share of 3+ letter words found.
For the numeric chunks of NDG, rapporto, scadenza and importo, the nearest OCR token of the same
length (at most 2 different characters) gives the digit-level substitutions.
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

SMALL_FIELDS = {"NDG 1", "NDG 2", "NDG 3", "NDG 4", "Rapporto", "Scadenza", "Importo (€)"}
NOTE_FIELDS = {"Note della richiesta", "Note Scheda Privati"}


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def nearest(chunk: str, tokens: List[str]) -> Optional[str]:
    best: Tuple[int, Optional[str]] = (3, None)
    for token in tokens:
        for start in range(0, max(len(token) - len(chunk), 0) + 1):
            piece = token[start:start + len(chunk)]
            if len(piece) != len(chunk):
                continue
            distance = sum(a != b for a, b in zip(chunk, piece))
            if distance < best[0]:
                best = (distance, piece)
    return best[1]


with open(sys.argv[1], encoding="utf-8-sig", newline="") as fh:
    rows = list(csv.DictReader(fh, delimiter=";"))
ocr = json.load(open(sys.argv[2], encoding="utf-8"))

read: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
note_words = [0, 0]
subs: Counter = Counter()
digits: Counter = Counter()
values = {"co_ndg": [0, 0], "scadenza_with_6": [0, 0], "rapporto": [0, 0]}
for row in rows:
    screen, field, value = row["Fotogramma"], row["Denominazione da attribuire"], row["Valore rilevato"]
    if not value.strip() or screen not in ocr:
        continue
    items = [item[0] for item in ocr[screen]["items"]]
    text = squash("".join(items))
    tokens = [squash(t) for t in items]
    if field in NOTE_FIELDS:
        words = [w for w in re.findall(r"[^\W\d_]{3,}", value.lower())]
        note_words[0] += sum(w in text for w in words)
        note_words[1] += len(words)
        continue
    found = squash(value) in text
    read[field][0] += found
    read[field][1] += 1
    if field in SMALL_FIELDS:
        chunks = [squash(c) for c in value.split() if any(ch.isdigit() for ch in c)]
        all_ok = True
        for chunk in chunks:
            piece = chunk if chunk in text else nearest(chunk, tokens)
            if piece is None:
                all_ok = False
                continue
            for a, b in zip(chunk, piece):
                if a.isdigit():
                    digits[a] += 1
                    if a != b:
                        subs[(a, b)] += 1
                        all_ok = False
        if field in ("NDG 2", "NDG 3", "NDG 4"):
            values["co_ndg"][0] += all_ok
            values["co_ndg"][1] += 1
        if field == "Scadenza" and "6" in value:
            values["scadenza_with_6"][0] += all_ok
            values["scadenza_with_6"][1] += 1
        if field == "Rapporto":
            values["rapporto"][0] += all_ok
            values["rapporto"][1] += 1

ok = sum(v[0] for v in read.values())
total = sum(v[1] for v in read.values())
print(f"values read: {ok}/{total} = {100 * ok / total:.1f}%   note words found: {note_words[0]}/{note_words[1]}")
for field, (c, t) in sorted(read.items(), key=lambda kv: kv[1][0] / kv[1][1]):
    if c != t:
        print(f"  {field[:52]:52s} {c:3d}/{t:<3d}")
six_wrong = sum(n for (a, b), n in subs.items() if a == "6")
print(f"digits compared: {sum(digits.values())}  sixes misread: {six_wrong} of {digits['6']}  other digits misread: {sum(subs.values()) - six_wrong} of {sum(digits.values()) - digits['6']}")
print("substitutions:", {f"{a}->{b}": n for (a, b), n in subs.most_common(8)})
for name, (c, t) in values.items():
    print(f"{name}: {c}/{t} read exactly")
seconds = [v["seconds"] for v in ocr.values()][1:]
print(f"time per screen: mean {sum(seconds) / len(seconds):.2f}s, max {max(seconds):.2f}s")
