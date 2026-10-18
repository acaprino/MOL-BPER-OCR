"""Compare two OCR caches screen by screen: same texts, same scores, same boxes.

Usage: python -I compare_caches.py <reference cache.json> <other cache.json>
Exits 1 unless every screen of the reference has the same texts in the same order in the other.
Scores and boxes are compared within 1e-4 and reported, not required.
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

reference = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
other = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
same_texts = same_numbers = 0
differing = []
for screen, entry in reference.items():
    mine, theirs = entry["items"], other.get(screen, {}).get("items")
    if theirs is not None and [i[0] for i in mine] == [i[0] for i in theirs]:
        same_texts += 1
        close = all(abs(a[1] - b[1]) <= 1e-4 and all(abs(p - q) <= 1e-4 for u, v in zip(a[2], b[2]) for p, q in zip(u, v))
                    for a, b in zip(mine, theirs))
        same_numbers += close
    else:
        differing.append(screen)
print(f"screens {len(reference)}, other {len(other)}")
print(f"same texts in order: {same_texts}/{len(reference)}; same scores and boxes within 1e-4: {same_numbers}/{len(reference)}")
for screen in differing:
    a = [i[0] for i in reference[screen]["items"]]
    b = [i[0] for i in other.get(screen, {}).get("items", [])]
    gone, new = [t for t in a if t not in b], [t for t in b if t not in a]
    print(f"  {screen}: {len(a)} vs {len(b)} items; only reference {gone[:6]}; only other {new[:6]}")
ok = same_texts == len(reference) and set(other) == set(reference)
print("PASS" if ok else "FAIL", "the other cache has the same texts as the reference on every screen")
sys.exit(0 if ok else 1)
