"""Turn LiLT word roles back into schema fields and score them with the project's evaluator.

    python ft_eval.py _v2      # model_v2 predictions (ft_out/train_result_v2.json)

Reports both field reconstructions side by side: "v1" (first spike) and "fixed", which adds four
generic rules checked on the validation practice as well as on the test practice:
  1. a value is one contiguous stretch of its line (fill the words between two words of a role);
  2. soggetti row boundaries sit halfway between consecutive NDG anchors;
  3. words are joined by visual line, then left to right (two-line cells keep their order);
  4. the request note is one block of lines inside its panel.
"""

import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from extraction.evaluation import eval_outputs, load_ground_truth  # noqa: E402
from extraction.fields import CSV_TO_SCHEMA  # noqa: E402
from extraction.normalization import classify_field  # noqa: E402

SINGLE = ["ndg", "denominazione", "tipo", "stato", "fase", "creazione", "evidenze", "filiale_relazione",
          "n_fido", "rapporto", "descrizione", "scadenza", "importo_euro", "tipo_op", "note_della_richiesta"]


def join(ws, by_line=False):
    if not by_line:
        return " ".join(w["text"] for w in sorted(ws, key=lambda w: (w["row"], w["x0"])))
    if not ws:
        return ""
    h = sorted(w["y1"] - w["y0"] for w in ws)[len(ws) // 2]
    lines, cur = [], []
    for w in sorted(ws, key=lambda w: (w["y0"] + w["y1"]) / 2):
        c = (w["y0"] + w["y1"]) / 2
        if cur and c - sum((x["y0"] + x["y1"]) / 2 for x in cur) / len(cur) > 0.5 * h:
            lines.append(cur)
            cur = []
        cur.append(w)
    lines.append(cur)
    return " ".join(w["text"] for line in lines for w in sorted(line, key=lambda w: w["x0"]))


def note_block(words, note_words):
    if not note_words:
        return note_words
    starts = sorted(min(w["x0"] for w in note_words if w["row"] == r) for r in {w["row"] for w in note_words})
    left = starts[len(starts) // 2]
    h = sorted(w["y1"] - w["y0"] for w in note_words)[len(note_words) // 2]
    top = min(w["y0"] for w in note_words if w["x0"] >= left - 2 * h)
    bottom = max(w["y1"] for w in note_words if w["x0"] >= left - 2 * h)
    return [w for w in words if w["x0"] >= left - 2 * h and w["y0"] >= top - 0.2 * h and w["y1"] <= bottom + 0.2 * h]


def first_cluster(ws):
    """Words of the topmost occurrence: stop at the first vertical gap wider than ~3 text lines."""
    ws = sorted(ws, key=lambda w: (w["row"], w["x0"]))
    if not ws:
        return ws
    h = max(1.0, ws[0]["y1"] - ws[0]["y0"])
    out = [ws[0]]
    for w in ws[1:]:
        if w["y0"] - out[-1]["y1"] > 3 * h:
            break
        out.append(w)
    return out


def fill_gaps(words, preds):
    out = list(preds)
    rows = {}
    for i, (w, p) in enumerate(zip(words, preds)):
        if p not in ("O", "note_della_richiesta"):
            rows.setdefault((p, w["row"]), []).append(i)
    for (role, _), idx in rows.items():
        for j in range(min(idx), max(idx) + 1):
            if out[j] == "O" and words[j]["row"] == words[idx[0]]["row"]:
                out[j] = role
    return out


def to_fields(words, preds, fixed=True):
    if fixed:
        preds = fill_gaps(words, preds)
    by = {}
    for w, p in zip(words, preds):
        if p != "O":
            by.setdefault(p, []).append(w)
    f = {}
    for role in SINGLE:
        if role in by:
            if role == "note_della_richiesta":
                ws = note_block(words, by[role]) if fixed else by[role]
            else:
                ws = first_cluster(by[role])
            f[role] = join(ws, by_line=fixed)
    header_rows = {w["row"] for w in words if w["text"].rstrip().upper().startswith("NDG:")}
    anchors = sorted([w for w in by.get("sogg_ndg", [])
                      if w["row"] not in header_rows and re.fullmatch(r"\d{6,}", w["text"])], key=lambda w: w["y0"])
    cy = lambda w: (w["y0"] + w["y1"]) / 2  # noqa: E731
    for i, a in enumerate(anchors[:4], start=1):
        h = a["y1"] - a["y0"]
        if fixed:
            top = (cy(anchors[i - 2]) + cy(a)) / 2 if i > 1 else cy(a) - 2.5 * h
            bottom = (cy(a) + cy(anchors[i])) / 2 if i < len(anchors) else cy(a) + 2.5 * h
            in_row = lambda w, t=top, b=bottom: t <= cy(w) < b  # noqa: E731
        else:
            nxt = anchors[i]["y0"] if i < len(anchors) else float("inf")
            in_row = lambda w, a=a, h=h, nxt=nxt: a["y0"] - 2 * h <= w["y0"] < nxt - 2 * h  # noqa: E731
        f[f"ndg_{i}"] = a["text"]
        f[f"denominazione_{i}"] = join([w for w in by.get("sogg_denominazione", []) if in_row(w)], by_line=fixed)
        f[f"ruolo_{i}"] = join([w for w in by.get("sogg_ruolo", []) if in_row(w)], by_line=fixed)
    if "tooltip_evidenze" in by:
        f["tooltip_evidenze_b"] = join(first_cluster(by["tooltip_evidenze"]))
    if "tooltip_fido" in by:
        f["tooltip_descrizione_m_consap"] = join(first_cluster(by["tooltip_fido"]))
    if "tooltip_garanzia" in by:
        tip = first_cluster(by["tooltip_garanzia"])
        g_rows = sorted([w for w in words if re.fullmatch(r"G\d+", w["text"])], key=lambda w: w["y0"])
        above = [g for g in g_rows if g["y0"] <= tip[0]["y0"]]
        key = "tooltip_descrizione_consap_dr_bis" if len(above) <= 1 else "tooltip_descrizione_ipoteca"
        f[key] = join(tip)
    return {k: v for k, v in f.items() if v}


VERSION = sys.argv[1] if len(sys.argv) > 1 else ""
examples = {e["id"]: e for e in json.load(open(HERE / "ft_out/examples.json", encoding="utf-8"))}
res = json.load(open(HERE / f"ft_out/train_result{VERSION}.json", encoding="utf-8"))
gt = load_ground_truth(str(REPO / "data/reference/dati.csv"))


def test_outputs(fixed):
    outs = {}
    for sid, r in res["predictions"].items():
        e = examples.get(sid)
        if e and r["split"] == "test":
            outs[sid] = {"fields": {k: {"value": v, "confidence": 1.0}
                                    for k, v in to_fields(e["words"], r["pred"], fixed).items()}, "soggetti": []}
    with redirect_stdout(io.StringIO()):
        ev_ = eval_outputs(outs, gt)
    return outs, ev_


if __name__ == "__main__":
    for fixed in (False, True):
        _, ev_ = test_outputs(fixed)
        print(f"[{'fixed reconstruction' if fixed else 'v1 reconstruction   '}] LUNARDI (never seen): RAW {ev_['acc_raw']:.2%}")
    outputs, _ = test_outputs(True)
    for sid, kv in gt.items():
        for csv_key, gt_val in kv.items():
            key = CSV_TO_SCHEMA.get(csv_key.strip())
            pred = outputs.get(sid, {}).get("fields", {}).get(key, {}).get("value")
            status, _ = classify_field(gt_val, pred, field_key=key)
            if status not in ("OK", "OK_NULL"):
                print(f"   {sid:9s} {key:34s} {status:12s} gt={gt_val[:40]!r} pred={str(pred)[:40]!r}")
