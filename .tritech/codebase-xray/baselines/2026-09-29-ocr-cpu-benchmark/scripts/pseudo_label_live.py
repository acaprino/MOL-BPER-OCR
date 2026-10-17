"""Throwaway: pseudo-labels for the 38 live captures via the project's own pipeline (live path, Gemini)."""

import glob
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(r"D:\Projects\poc-data-extraction")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from PIL import Image  # noqa: E402

from extraction.config import LLM_MODEL, LLM_MODEL_ANCHOR, LLM_PROVIDER  # noqa: E402
from extraction.llm_factory import create_chat_model  # noqa: E402
from extraction.pipeline import ExtractionPipeline  # noqa: E402

OUT = Path(__file__).resolve().parent / "ocr_probe_out" / "live_pseudo_labels.json"

pipeline = ExtractionPipeline(
    main_model=create_chat_model(LLM_PROVIDER, model=LLM_MODEL),
    anchor_model=create_chat_model(LLM_PROVIDER, model=LLM_MODEL_ANCHOR),
    main_model_name=LLM_MODEL,
    anchor_model_name=LLM_MODEL_ANCHOR,
)
paths = sorted(glob.glob(str(REPO / "tests/fixtures/frames/no-tooltip-rita/*.png"))) + \
        sorted(glob.glob(str(REPO / "tests/fixtures/frames/tooltips-rita/*.png")))


def run(p: str):
    rel = str(Path(p).relative_to(REPO / "tests/fixtures/frames")).replace("\\", "/")
    img = Image.open(p).convert("RGB")
    try:
        out = pipeline.extract_from_image(img, rel)
    except Exception as exc:  # noqa: BLE001
        return rel, {"error": repr(exc)[:500]}
    fields = {k: v.get("value") for k, v in (out.get("fields") or {}).items() if v and v.get("value") not in (None, "")}
    meta = out.get("_meta_agg", {})
    return rel, {"fields": fields, "status": out.get("_status"), "cost_usd": meta.get("estimated_cost_usd"),
                 "calls": meta.get("calls")}


with ThreadPoolExecutor(max_workers=4) as ex:
    results = dict(ex.map(run, paths))
OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
cost = sum((r.get("cost_usd") or 0) for r in results.values())
errors = [k for k, r in results.items() if "error" in r]
print(f"model={LLM_MODEL} shots={len(results)} errors={errors} cost=${cost:.3f}")
