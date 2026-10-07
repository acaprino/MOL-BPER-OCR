"""Summarize one CLI run: accuracy by page kind / field / practice, error list, statuses, cost.

Usage (any cwd): python report_run.py <repo_root> <input_dir> [--errors N] [--json out.json]
Reads dati.csv and poc_outputs_improved.json from <input_dir>.

Every verdict comes from the project's own classify_field(), applied exactly as eval_outputs()
does, so OVERALL here equals the CLI's "OVERALL (RAW)". The "sola forma" count is a separate,
clearly labelled breakdown of the errors and never changes the headline numbers.
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any, Callable, Dict, List

repo =os.path.abspath(sys.argv[1])
sys.path.insert(0, repo)
os.chdir(repo)
from dotenv import load_dotenv  # noqa: E402

load_dotenv()
from extraction.evaluation import load_ground_truth  # noqa: E402
from extraction.fields import CSV_TO_SCHEMA  # noqa: E402
from extraction.normalization import classify_field, dataset_mismatch_guard  # noqa: E402

IDENTITY = {"ndg", "denominazione"} | {f"{p}_{i}" for p in ("ndg", "denominazione") for i in range(1, 5)}
GOOD = {"OK", "OK_NULL"}


def kind_of(screen: str) -> str:
    stem = screen.split("__", 1)[-1].lower()
    if stem.startswith("elenco_tooltip"):
        return "Elenco con tooltip"
    if stem.startswith("elenco"):
        return "Elenco"
    if stem.startswith("soggetti"):
        return "Soggetti"
    if stem.startswith("gestionefidi_tooltip"):
        return "Fidi con tooltip"
    if stem.startswith("gestionefidi"):
        return "Fidi"
    if stem.startswith("note"):
        return "Note"
    if stem.startswith("scheda"):
        return "Scheda Privati"
    return "?"


def squash(text: Any) -> str:
    """Form-only normalization: case, spaces, ellipsis glyph and dot runs."""
    text = str(text or "").replace("…", "...").lower()
    text = re.sub(r"\.{2,}", "...", text)
    return re.sub(r"\s+", "", text)


def pct(ok: int, total: int) -> str:
    return f"{ok:4d}/{total:<4d} {100 * ok / total:5.1f}%" if total else "   0/0        -"


def main(input_dir: str, max_errors: int, json_out: str) -> None:
    gt = load_ground_truth(os.path.join(input_dir, "dati.csv"))
    outputs = json.load(open(os.path.join(input_dir, "poc_outputs_improved.json"), encoding="utf-8"))

    rows: List[Dict[str, Any]] = []
    guarded = set()
    for screen, kv in gt.items():
        pred = outputs.get(screen)
        if not pred:
            continue
        if dataset_mismatch_guard(kv, pred):
            guarded.add(screen)
        sources = pred.get("_field_sources") or {}
        for csv_key, gt_val in kv.items():
            field = CSV_TO_SCHEMA.get(str(csv_key).strip())
            if not field:
                continue
            pred_val = (pred.get("fields", {}).get(field) or {}).get("value")
            status, reason = classify_field(gt_val, pred_val, field_key=field)
            rows.append({"screen": screen, "field": field, "gt": gt_val, "pred": pred_val, "status": status,
                         "reason": reason, "source": sources.get(field, "-")})

    missing_screens = sorted(set(gt) - set(outputs))
    total = len(rows)
    ok = sum(r["status"] in GOOD for r in rows)
    filt = [r for r in rows if r["screen"] not in guarded]
    filt_ok = sum(r["status"] in GOOD for r in filt)
    statuses = Counter(r["status"] for r in rows)
    print(f"screens with output: {len(outputs)}   screens in GT without output: {missing_screens}")
    print(f"OVERALL (RAW)      {pct(ok, total)}   statuses: {dict(statuses)}")
    print(f"OVERALL (FILTERED) {pct(filt_ok, len(filt))}   screens excluded by the NDG/denominazione guard: {len(guarded)}")

    def table(title: str, key: Callable[[Dict[str, Any]], str]) -> Dict[str, List[int]]:
        agg: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
        for r in rows:
            k = key(r)
            agg[k][1] += 1
            agg[k][0] += r["status"] in GOOD
        print(f"\n{title}")
        for k, (c, t) in sorted(agg.items(), key=lambda kv: (kv[1][0] / kv[1][1], kv[0])):
            print(f"  {k:42s} {pct(c, t)}")
        return agg

    by_kind = table("BY PAGE KIND", lambda r: kind_of(r["screen"]))
    by_field = table("BY FIELD", lambda r: r["field"])
    by_practice = table("BY PRACTICE", lambda r: r["screen"].split("__", 1)[0])

    ident = [r for r in rows if r["field"] in IDENTITY]
    ident_ok = sum(r["status"] in GOOD for r in ident)
    print(f"\nIDENTITY (ndg/denominazione, header and soggetti)  {pct(ident_ok, len(ident))}")

    bad = [r for r in rows if r["status"] not in GOOD]
    form_only = [r for r in bad if r["gt"] and r["pred"] and squash(r["gt"]) == squash(r["pred"])]
    print(f"errors: {len(bad)}  of which sola forma (spazi, maiuscole, puntini): {len(form_only)}")
    print(f"errors by status: {dict(Counter(r['status'] for r in bad))}")
    print(f"errors by source pass: {dict(Counter(r['source'] for r in bad))}")
    print(f"errors by field: {dict(Counter(r['field'] for r in bad).most_common())}")

    print(f"\nERRORS (first {max_errors})")
    for r in bad[:max_errors]:
        print(f"  {r['screen']:38s} {r['field']:27s} {r['status']:12s} gt={str(r['gt'])[:46]!r} pred={str(r['pred'])[:46]!r} src={r['source']}")

    def agg(name: str) -> float:
        return sum(float((o.get("_meta_agg") or {}).get(name) or 0) for o in outputs.values())

    screen_status = Counter(o.get("_status") for o in outputs.values())
    crops = Counter(str(o.get("_content_crop")) for o in outputs.values())
    calls, cost = int(agg("calls")), agg("estimated_cost_usd")
    p_tok, c_tok, lat = int(agg("prompt_tokens")), int(agg("completion_tokens")), agg("latency_ms")
    n = max(len(outputs), 1)
    print(f"\nscreen _status: {dict(screen_status)}   _content_crop: {dict(crops)}")
    print(f"calls={calls} ({calls / n:.1f}/screen)  tokens prompt/completion={p_tok}/{c_tok}  cost=${cost:.3f} (${cost / n:.4f}/screen)  latency sum/screen={lat / n / 1000:.1f}s")

    if json_out:
        json.dump({
            "screens": len(outputs), "rows": total, "ok": ok, "filtered": [filt_ok, len(filt)],
            "guard_excluded_screens": sorted(guarded), "statuses": dict(statuses),
            "by_kind": dict(by_kind), "by_field": dict(by_field), "by_practice": dict(by_practice),
            "identity": [ident_ok, len(ident)], "errors": len(bad), "errors_form_only": len(form_only),
            "errors_by_field": dict(Counter(r["field"] for r in bad)),
            "error_rows": [{k: r[k] for k in ("screen", "field", "status", "gt", "pred", "source")} for r in bad],
            "screen_status": dict(screen_status), "content_crop": dict(crops), "calls": calls,
            "prompt_tokens": p_tok, "completion_tokens": c_tok, "cost_usd": round(cost, 4),
            "latency_s_per_screen": round(lat / n / 1000, 1),
        }, open(json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    args = sys.argv[2:]
    errors = int(args[args.index("--errors") + 1]) if "--errors" in args else 60
    out = args[args.index("--json") + 1] if "--json" in args else ""
    main(os.path.abspath(args[0]), errors, out)
