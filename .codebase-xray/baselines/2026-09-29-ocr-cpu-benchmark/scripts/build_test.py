"""Rebuild ft_out/examples.json for the 9 LUNARDI test screens only (words, boxes, gold roles from the GT).

Uses the same to_words / label_screen as the training data (ft_data.py), so word boxes and chunking
match what model_v2 was trained with.
"""

import json
from pathlib import Path

from ft_data import label_screen, load_gt, to_words

HERE = Path(__file__).resolve().parent
ref = json.load(open(HERE / "ocr_probe_out/rapid_v6_small_1x.json", encoding="utf-8"))
gt = load_gt()
examples = []
for sid, lines in ref.items():
    words, w, h = to_words(lines)
    labels, ok = label_screen(words, gt.get(sid, {}))
    examples.append({"id": sid, "split": "test", "cluster": sid.split()[-1], "width": w, "height": h,
                     "words": [{k: wd[k] for k in ("text", "x0", "y0", "x1", "y1", "row")} for wd in words],
                     "labels": labels, "aligned": ok, "values": gt.get(sid, {})})
(HERE / "ft_out").mkdir(exist_ok=True)
(HERE / "ft_out/examples.json").write_text(json.dumps(examples, ensure_ascii=False), encoding="utf-8")
print("test screens", len(examples), "fields aligned", sum(sum(e["aligned"].values()) for e in examples),
      "/", sum(len(e["aligned"]) for e in examples))
