"""Score the Modal OCR benchmark outputs with the same metric as the local probe."""

import glob
import json
import re
import statistics

from ocr_probe import OUT, load_gt, score


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")        # HTML tables
    text = re.sub(r"[|*#`]", " ", text)                # markdown tables, emphasis, headings
    return text.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")


gt = load_gt()
for path in sorted(glob.glob(str(OUT / "modal_*.json"))):
    res = json.load(open(path, encoding="utf-8"))
    if "error" in res and not res.get("screens"):
        print(res.get("engine"), res.get("profile"), "ERROR", str(res["error"])[:300])
        continue
    groups = {}
    for key, s in res["screens"].items():
        sid, _, scale = key.partition("@")
        groups.setdefault(scale or "1x", {})[sid] = s
    for scale, screens in sorted(groups.items()):
        found = total = 0
        notes, secs, errors, missing = [], [], [], {}
        for sid, s in screens.items():
            if "error" in s:
                errors.append(sid)
                continue
            secs.append(s["seconds"])
            lines = [(ln, 1.0, None) for ln in clean(s["text"]).splitlines() if ln.strip()]
            rows = gt.get(sid, [])
            f, miss, nr = score(rows, lines)
            found += f
            total += sum(1 for _, v in rows if len(v) <= 120)
            if miss:
                missing[sid] = miss
            if nr is not None:
                notes.append(round(nr, 3))
        mean = round(statistics.mean(secs), 1) if secs else None
        print(f"{res['engine']+'_'+str(res.get('profile')):22s} {scale:3s} found {found}/{total}  note {notes}  "
              f"sec/screen mean {mean} max {max(secs) if secs else None}  errors {errors}  quota {res.get('cpu_quota')} {res.get('cpu_model')}")
        for sid, miss in missing.items():
            print("      ", sid, miss)
