"""RapidOCR configurations for the throwaway OCR probe."""

import json

import numpy as np
from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

from ocr_probe import OUT, run

CONFIGS = {
    "rapid_v6_small": {"Det.ocr_version": OCRVersion.PPOCRV6, "Rec.ocr_version": OCRVersion.PPOCRV6},
    "rapid_v6_medium": {
        "Det.ocr_version": OCRVersion.PPOCRV6, "Det.model_type": ModelType.MEDIUM,
        "Rec.ocr_version": OCRVersion.PPOCRV6, "Rec.model_type": ModelType.MEDIUM,
    },
    "rapid_v5_server_latin": {
        "Det.ocr_version": OCRVersion.PPOCRV5, "Det.model_type": ModelType.SERVER,
        "Rec.ocr_version": OCRVersion.PPOCRV5, "Rec.lang_type": LangRec.LATIN, "Rec.model_type": ModelType.MOBILE,
    },
}

reports = {}
for label, params in CONFIGS.items():
    params = {**params, "Global.log_level": "warning", "EngineConfig.onnxruntime.intra_op_num_threads": 4, "EngineConfig.onnxruntime.inter_op_num_threads": 1}
    try:
        engine = RapidOCR(params=params)
    except Exception as exc:  # noqa: BLE001
        print(label, "FAILED TO LOAD:", exc)
        continue

    def ocr_fn(im, engine=engine):
        res = engine(np.array(im))
        if res.txts is None:
            return []
        return [(t, s, b.tolist()) for t, s, b in zip(res.txts, res.scores, res.boxes)]

    reports.update(run(label, ocr_fn))

(OUT / "rapid_report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=1), encoding="utf-8")
