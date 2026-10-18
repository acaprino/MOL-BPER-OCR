"""Check that the OCR runner reproduces A0 and that its report matches hand-derived counts.

Usage: python -I check_a0_runner.py <repo_root> <A0 run dir>
Expected values come from the earlier reading of alignment_report.csv (plan sections 1.2 and 4),
not from the code under test. Exits 1 if any check fails.
"""
import hashlib
import json
import sys
from pathlib import Path

root, run = Path(sys.argv[1]), Path(sys.argv[2])
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


manifest = load(run / "manifest.json")
check("run is complete and binds its cache", manifest["status"] == "complete"
      and manifest["cache_sha256"] == sha(run / "cache.json"), manifest["status"])
models = {k: v["sha256"][:8] for k, v in manifest["provenance"]["models"].items()}
check("A0 models are v6 small det/rec and the v2.0 classifier",
      models == {"Det": "090f04ab", "Cls": "e47acedf", "Rec": "6f327246"}, str(models))
check("pc4 threads 4/1", manifest["identity"]["threads"] == {"intra_op": 4, "inter_op": 1})

historic = load(root / "data/training/ocr-cache/rapid_v6_small_1x.json")
cache = load(run / "cache.json")
same = sum(cache[s]["items"] == historic[s]["items"] for s in historic) if set(cache) == set(historic) else -1
check("113/113 screens identical to the bundle's OCR cache (texts, scores, boxes)", same == 113, str(same))
check("derived alignment_report.csv identical to the bundle's",
      sha(run / "dataset/alignment_report.csv") == sha(root / "data/training/ground-truth-v3.1/alignment_report.csv"))

metrics = load(run / "ocr_selection.json")
split = metrics["by_split"]
check("OCR non-null train 562/613, val 124/133, train+val 686/746",
      [split[s]["ocr_non_null"] for s in ("train", "val", "train_val")]
      == [{"available": 562, "total": 613}, {"available": 124, "total": 133}, {"available": 686, "total": 746}],
      str([split[s]["ocr_non_null"] for s in ("train", "val", "train_val")]))
check("subject NDG train 16/21, val 5/5",
      (split["train"]["subject_ndg"], split["val"]["subject_ndg"])
      == ({"available": 16, "total": 21}, {"available": 5, "total": 5}), str(split["train"]["subject_ndg"]))
check("rapporto train 23/24, val 5/5",
      (split["train"]["rapporto"], split["val"]["rapporto"])
      == ({"available": 23, "total": 24}, {"available": 5, "total": 5}), str(split["train"]["rapporto"]))
check("6 read as 8: train 10, val 1", (split["train"]["six_as_eight"], split["val"]["six_as_eight"]) == (10, 1),
      str((split["train"]["six_as_eight"], split["val"]["six_as_eight"])))
practice = metrics["per_practice"]
observed = {p: (v["six_as_eight"], v["six_as_eight_values"]) for p, v in practice.items() if v["six_as_eight"]}
check("6 read as 8 per practice (observations, distinct values)",
      observed == {"52062600": (3, 3), "52068422": (2, 1), "52080223": (2, 2), "52135039": (3, 2), "52126316": (1, 1)},
      str(observed))
check("historical test practices absent", not {"51531667", "52060489"} & set(practice), str(sorted(practice)))
check("ten train+val practices", len(practice) == 10, str(len(practice)))

for name, ok, detail in results:
    print("PASS" if ok else "FAIL", name, "" if ok else f"-> {detail}")
print(f"{sum(ok for _, ok, _ in results)}/{len(results)} checks passed")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
