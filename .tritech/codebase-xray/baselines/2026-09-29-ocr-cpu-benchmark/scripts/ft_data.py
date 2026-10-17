"""Throwaway spike: word-level training data for LiLT (words + boxes -> field role).

Real examples: the 38 live captures (labels from Gemini pseudo-labels, train) and the
9 LUNARDI reference screens (labels from the ground truth, test only: the model never
sees that practice). Values are aligned to OCR words fuzzily, so OCR slips still align.

Roles are practice-independent: the ground truth names tooltips after one practice's
values (tooltip_descrizione_ipoteca...), which would not generalize, so the model
learns "tooltip on the fido row" / "tooltip on a garanzia row" and "soggetto NDG";
row indices are recovered from geometry after prediction.
"""

import csv
import json
import random
import re
from difflib import SequenceMatcher
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
REPO = Path(r"D:\Projects\poc-data-extraction")
OUT = HERE / "ft_out"

ROLES = [
    "O", "ndg", "denominazione", "tipo", "stato", "fase", "creazione", "evidenze", "filiale_relazione",
    "n_fido", "rapporto", "descrizione", "scadenza", "importo_euro", "tipo_op",
    "sogg_ndg", "sogg_denominazione", "sogg_ruolo",
    "tooltip_evidenze", "tooltip_fido", "tooltip_garanzia", "note_della_richiesta",
]

SCHEMA_TO_ROLE = {
    **{k: k for k in ROLES[1:15]},
    "tooltip_evidenze_b": "tooltip_evidenze",
    "tooltip_descrizione_m_consap": "tooltip_fido",
    "tooltip_descrizione_consap_dr_bis": "tooltip_garanzia",
    "tooltip_descrizione_ipoteca": "tooltip_garanzia",
    "note_della_richiesta": "note_della_richiesta",
}
for i in range(1, 5):
    SCHEMA_TO_ROLE[f"ndg_{i}"] = "sogg_ndg"
    SCHEMA_TO_ROLE[f"denominazione_{i}"] = "sogg_denominazione"
    SCHEMA_TO_ROLE[f"ruolo_{i}"] = "sogg_ruolo"

CSV_KEYS = None  # filled lazily from extraction.fields


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def similar(a: str, b: str) -> bool:
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    if a == b:
        return True
    if min(len(a), len(b)) < 4:
        return False
    return SequenceMatcher(None, a, b).ratio() >= 0.8


# ============================================================ OCR lines -> words in reading order

def to_words(lines: List[dict]) -> Tuple[List[dict], float, float]:
    """Words with estimated boxes, sorted in reading order; returns (words, width, height) of the word extent."""
    raw = []
    for li, ln in enumerate(lines):
        xs = [p[0] for p in ln["box"]]
        ys = [p[1] for p in ln["box"]]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        text = ln["text"].strip()
        if not text:
            continue
        step = (x1 - x0) / len(text)
        for m in re.finditer(r"\S+", text):
            raw.append({"text": m.group(0), "x0": x0 + m.start() * step, "x1": x0 + m.end() * step,
                        "y0": y0, "y1": y1, "line": li})
    if not raw:
        return [], 1.0, 1.0
    tol = 0.5 * median(w["y1"] - w["y0"] for w in raw)
    raw.sort(key=lambda w: (w["y0"] + w["y1"]) / 2)
    rows, current, last = [], [], None
    for w in raw:
        cy = (w["y0"] + w["y1"]) / 2
        if current and abs(cy - last) > tol:
            rows.append(current)
            current = []
        current.append(w)
        last = cy if len(current) == 1 else (last * (len(current) - 1) + cy) / len(current)
    rows.append(current)
    words = []
    for ri, r in enumerate(rows):
        for w in sorted(r, key=lambda w: w["x0"]):
            w["row"] = ri
            words.append(w)
    return words, max(w["x1"] for w in words), max(w["y1"] for w in words)


# ============================================================ alignment

def _cost(prev: dict, cand: dict) -> float:
    """Reading-order distance: same row to the right is cheap; next rows in the same column cost more."""
    if cand["row"] == prev["row"] and cand["x0"] >= prev["x0"]:
        return cand["x0"] - prev["x1"]
    if cand["row"] > prev["row"]:
        dy = cand["y0"] - prev["y1"]
        return 3 * dy + abs(cand["x0"] - prev["x0"])
    return float("inf")


def align_value(words: List[dict], value: str, taken: set, allowed=None) -> List[int]:
    tokens = [t for t in value.split() if norm(t)]
    if not tokens:
        return []
    best: Tuple[float, List[int]] = (-1.0, [])
    starts = [i for i, w in enumerate(words) if i not in taken and similar(w["text"], tokens[0])
              and (allowed is None or allowed(i))]
    for s in starts:
        seq, prev, score = [s], words[s], 1.0
        for tok in tokens[1:]:
            cands = [(i, _cost(prev, w)) for i, w in enumerate(words)
                     if i not in taken and i not in seq and similar(w["text"], tok)]
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


def align_note(words: List[dict], note: str, taken: set) -> List[int]:
    """The request note: label whole rows whose text is a fuzzy piece of the note."""
    target = norm(note)
    out = []
    rows: Dict[int, List[int]] = {}
    for i, w in enumerate(words):
        rows.setdefault(w["row"], []).append(i)
    for idx in rows.values():
        text = norm("".join(words[i]["text"] for i in idx))
        if len(text) < 6:
            continue
        m = SequenceMatcher(None, text, target).find_longest_match(0, len(text), 0, len(target))
        if m.size >= 0.6 * len(text):
            # keep only the words of that row that sit inside the matched stretch horizontally
            out += [i for i in idx if i not in taken and similar(words[i]["text"], words[i]["text"])
                    and norm(words[i]["text"]) in target]
    return out


HEADER_FIRST = ["ndg", "denominazione", "tipo", "filiale_relazione", "stato", "fase", "creazione", "evidenze"]


def label_screen(words: List[dict], values: Dict[str, str]) -> Tuple[List[str], Dict[str, bool]]:
    """Per-word roles for one screen; returns (labels, per-field alignment success)."""
    labels = ["O"] * len(words)
    taken: set = set()
    ok: Dict[str, bool] = {}
    ndg_rows = {w["row"] for w in words if norm(w["text"]) == "ndg" and w["text"].rstrip().endswith(":")}

    def put(key: str, role: str, idx: List[int]) -> None:
        for i in idx:
            labels[i] = role
            taken.add(i)
        ok[key] = bool(idx)

    order = sorted(values, key=lambda k: (0 if k in HEADER_FIRST else 1, k))
    for key in order:
        value = values[key]
        role = SCHEMA_TO_ROLE.get(key)
        if not role or not value:
            continue
        if role == "note_della_richiesta":
            put(key, role, align_note(words, value, taken))
            continue
        allowed = None
        if role in ("ndg", "denominazione") and ndg_rows:
            allowed = lambda i: words[i]["row"] in ndg_rows  # noqa: E731  detail pages: the NDG: header bar
        elif role.startswith("sogg_"):
            allowed = lambda i: words[i]["row"] not in ndg_rows  # noqa: E731
        put(key, role, align_value(words, value, taken, allowed))
    return labels, ok


# ============================================================ sources

def load_gt() -> Dict[str, Dict[str, str]]:
    import sys
    sys.path.insert(0, str(REPO))
    from extraction.fields import CSV_TO_SCHEMA
    gt: Dict[str, Dict[str, str]] = {}
    with open(REPO / "mnt/data/dati.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = CSV_TO_SCHEMA.get(row["Denominazione da attribuire"].strip())
            value = row["Valore rilevato"].strip()
            if key and value:
                gt.setdefault(row["Fotogramma"].strip(), {})[key] = value
    return gt


def build() -> None:
    OUT.mkdir(exist_ok=True)
    ref = json.load(open(HERE / "ocr_probe_out/rapid_v6_small_1x.json", encoding="utf-8"))
    live = json.load(open(HERE / "ocr_probe_out/live_boxes.json", encoding="utf-8"))
    pseudo = json.load(open(HERE / "ocr_probe_out/live_pseudo_labels.json", encoding="utf-8"))
    manifests = {}
    for sub in ("no-tooltip-rita", "tooltips-rita"):
        for fr in json.load(open(REPO / f"tests/fixtures/frames/{sub}/manifest.json", encoding="utf-8"))["frames"]:
            manifests[fr["frame"]] = fr

    def example(sid, lines, values, split, cluster):
        words, w, h = to_words(lines)
        labels, ok = label_screen(words, values)
        return {"id": sid, "split": split, "cluster": cluster, "width": w, "height": h,
                "words": [{k: wd[k] for k in ("text", "x0", "y0", "x1", "y1", "row")} for wd in words],
                "labels": labels, "aligned": ok, "values": values}

    examples = []
    gt = load_gt()
    for sid, lines in ref.items():
        examples.append(example(sid, lines, gt.get(sid, {}), "test", sid.split()[-1]))
    for rel, item in live.items():
        values = dict((pseudo.get(rel) or {}).get("fields") or {})
        cluster = str(manifests.get(rel, {}).get("cluster"))
        if cluster.startswith("altro"):
            values.pop("note_della_richiesta", None)  # "Note a Istruttoria" is not the request note
        examples.append(example(rel, item["lines"], values, "train", cluster))

    # Iteration 2: framed recording frames. Frames of the test practice (LUNARDI) are dropped:
    # the 20250909 recording is that same practice, and training on it would void the test.
    iter2_boxes = HERE / "ocr_probe_out/iter2_boxes.json"
    if iter2_boxes.exists():
        boxes2 = json.load(open(iter2_boxes, encoding="utf-8"))
        pseudo2 = json.load(open(HERE / "ocr_probe_out/iter2_pseudo_labels.json", encoding="utf-8"))
        index2 = json.load(open(HERE / "iter2_index.json", encoding="utf-8"))
        leaked, by_ndg = [], {}
        for fid, item in boxes2.items():
            text = " ".join(ln["text"] for ln in item["lines"]).upper()
            if "26871394" in text or "LUNARDI" in text:
                leaked.append(fid)
                continue
            values = dict((pseudo2.get(fid) or {}).get("fields") or {})
            cluster = index2[fid]["cluster"]
            if cluster.startswith("altro"):
                values.pop("note_della_richiesta", None)
            ex = example(fid, item["lines"], values, "train", cluster)
            examples.append(ex)
            m = re.search(r"NDG:?\s*(\d{7,8})", text)
            ndg = values.get("ndg") or (m.group(1) if m else None)
            if ndg and not cluster.startswith("altro"):
                by_ndg.setdefault(ndg, []).append(ex)
        # Validation practice: the recorded practice with the most distinct page classes, for early stopping only.
        if by_ndg:
            val_ndg = max(by_ndg, key=lambda k: (len({e["cluster"] for e in by_ndg[k]}), len(by_ndg[k])))
            for e in by_ndg[val_ndg]:
                e["split"] = "val"
            print(f"iteration 2: {len(boxes2)} frames, dropped {len(leaked)} of the test practice, "
                  f"validation practice NDG {val_ndg} ({len(by_ndg[val_ndg])} frames, "
                  f"pages {sorted({e['cluster'] for e in by_ndg[val_ndg]})}), practices {len(by_ndg)}")

    (OUT / "examples.json").write_text(json.dumps(examples, ensure_ascii=False), encoding="utf-8")
    for split in ("train", "val", "test"):
        tot = sum(len([k for k in e["aligned"]]) for e in examples if e["split"] == split)
        good = sum(sum(e["aligned"].values()) for e in examples if e["split"] == split)
        labeled = sum(sum(l != "O" for l in e["labels"]) for e in examples if e["split"] == split)
        print(f"{split}: {sum(e['split'] == split for e in examples)} screens, fields aligned {good}/{tot}, labeled words {labeled}")
    counts = {}
    for e in examples:
        if e["split"] == "train":
            for lab in e["labels"]:
                counts[lab] = counts.get(lab, 0) + 1
    print("train word labels per role:", dict(sorted(counts.items(), key=lambda kv: -kv[1])))


if __name__ == "__main__":
    build()
