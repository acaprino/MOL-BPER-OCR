"""Iteration 2: Gemini pseudo-labels for the framed recording frames (project pipeline, live path).

Run with the project venv from the repo root's environment (it loads .env for the Gemini key).
"""

import glob
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from PIL import Image  # noqa: E402

from extraction.config import LLM_MODEL, LLM_MODEL_ANCHOR, LLM_PROVIDER  # noqa: E402
from extraction.llm_factory import create_chat_model  # noqa: E402
from extraction.pipeline import ExtractionPipeline  # noqa: E402

OUT = HERE / "ocr_probe_out" / "iter2_pseudo_labels.json"
pipeline = ExtractionPipeline(
    main_model=create_chat_model(LLM_PROVIDER, model=LLM_MODEL),
    anchor_model=create_chat_model(LLM_PROVIDER, model=LLM_MODEL_ANCHOR),
    main_model_name=LLM_MODEL,
    anchor_model_name=LLM_MODEL_ANCHOR,
)


def run(p: str):
    fid = Path(p).stem
    try:
        out = pipeline.extract_from_image(Image.open(p).convert("RGB"), fid)
    except Exception as exc:  # noqa: BLE001
        return fid, {"error": repr(exc)[:500]}
    fields = {k: v.get("value") for k, v in (out.get("fields") or {}).items() if v and v.get("value") not in (None, "")}
    meta = out.get("_meta_agg", {})
    return fid, {"fields": fields, "status": out.get("_status"), "cost_usd": meta.get("estimated_cost_usd")}


paths = sorted(glob.glob(str(HERE / "iter2_frames" / "*.png")))
with ThreadPoolExecutor(max_workers=6) as ex:
    results = dict(ex.map(run, paths))
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
cost = sum((r.get("cost_usd") or 0) for r in results.values())
print(f"model={LLM_MODEL} frames={len(results)} errors={[k for k, r in results.items() if 'error' in r]} cost=${cost:.3f}")
