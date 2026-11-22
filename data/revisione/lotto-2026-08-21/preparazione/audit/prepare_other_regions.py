"""Record visually selected field regions without OCR or value transcription."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


AUDIT = Path(__file__).resolve().parent
OUTPUT = AUDIT.parent
ROOT = OUTPUT.parents[1]
Box = tuple[int, int, int, int]

# Manually selected glyph regions in original screenshot coordinates. The last
# refinement finds only the ink boundaries inside these human-selected regions.
HEADERS: dict[str, dict[str, Box]] = {
    "51788077__Soggetti": {
        "ndg": (389, 358, 431, 371),
        "denominazione": (438, 358, 547, 371),
        "tipo": (934, 337, 976, 350),
        "filiale_relazione": (956, 389, 1053, 402),
    },
    "51800301__Soggetti": {
        "ndg": (416, 399, 463, 414),
        "denominazione": (471, 399, 664, 414),
        "tipo": (1022, 363, 1071, 376),
        "filiale_relazione": (1047, 436, 1147, 450),
    },
    "52032077__Soggetti": {
        "ndg": (386, 368, 428, 382),
        "denominazione": (434, 368, 535, 382),
        "tipo": (931, 334, 973, 347),
        "filiale_relazione": (953, 400, 1026, 414),
    },
    "51800301__Note": {
        "ndg": (388, 329, 430, 343),
        "denominazione": (437, 329, 610, 343),
        "tipo": (933, 295, 975, 308),
        "filiale_relazione": (955, 360, 1046, 374),
    },
    "51800301__Note_chiuso": {
        "ndg": (385, 366, 427, 380),
        "denominazione": (434, 366, 607, 380),
        "tipo": (930, 332, 972, 345),
        "filiale_relazione": (952, 398, 1043, 412),
    },
}
HEADER_CONTEXT: dict[str, Box] = {
    "51788077__Soggetti": (330, 337, 1075, 448),
    "51800301__Soggetti": (353, 362, 1178, 514),
    "52032077__Soggetti": (328, 333, 1072, 459),
    "51800301__Note": (331, 294, 1074, 433),
    "51800301__Note_chiuso": (328, 331, 1071, 470),
}
SUBJECT_CELLS: dict[str, list[dict[str, Box]]] = {
    "51788077__Soggetti": [
        {"ndg": (366, 529, 412, 545), "denominazione": (413, 529, 590, 545), "ruolo": (592, 529, 713, 545)},
    ],
    "51800301__Soggetti": [
        {"ndg": (390, 604, 441, 622), "denominazione": (442, 604, 643, 622), "ruolo": (645, 604, 783, 622)},
        {"ndg": (390, 626, 441, 659), "denominazione": (442, 626, 643, 659), "ruolo": (645, 626, 783, 659)},
        {"ndg": (390, 664, 441, 696), "denominazione": (442, 664, 643, 696), "ruolo": (645, 664, 783, 696)},
    ],
    "52032077__Soggetti": [
        {"ndg": (355, 539, 400, 556), "denominazione": (401, 539, 550, 556), "ruolo": (551, 539, 658, 556)},
        {"ndg": (355, 560, 400, 589), "denominazione": (401, 560, 550, 589), "ruolo": (551, 560, 658, 589)},
    ],
}
SUBJECT_CONTEXT: dict[str, Box] = {
    "51788077__Soggetti": (333, 471, 1074, 550),
    "51800301__Soggetti": (355, 539, 1177, 701),
    "52032077__Soggetti": (330, 481, 1071, 594),
}
NOTES: dict[str, tuple[Box, Box, str, str]] = {
    "51800301__Note": (
        (339, 513, 1062, 925), (334, 476, 1071, 950), "visible",
        "Expanded note panel; all note text visible in this source is inside the real text region.",
    ),
    "51800301__Note_chiuso": (
        (336, 550, 1046, 575), (331, 513, 1068, 578), "visible_partial",
        "Reduced scrollable note panel shows two text lines; the remaining note is not visible in this screenshot.",
    ),
}


def ink_box(image: Image.Image, region: Box, light: bool = False, red_only: bool = False) -> Box:
    pixels = np.asarray(image.crop(region).convert("RGB")).astype(np.int16)
    if light:
        ink = (pixels > 140).all(axis=2)
    elif red_only:
        ink = (pixels[:, :, 0] > 220) & (pixels[:, :, 1] < 75) & (pixels[:, :, 2] < 75)
    else:
        ink = (pixels < 190).all(axis=2)
    y, x = np.where(ink)
    if not len(x):
        raise ValueError(f"No ink in manually selected region {region}")
    # Two source pixels of padding keep antialiasing inside the frame.
    return (region[0] + int(x.min()) - 2, region[1] + int(y.min()) - 2,
            region[0] + int(x.max()) + 3, region[1] + int(y.max()) + 3)


def main() -> None:
    manifest = json.loads((OUTPUT / "context_images.json").read_text(encoding="utf-8"))
    existing = {item["screen"]: item for item in manifest["images"]}
    regions: list[dict[str, Any]] = []
    screen_checks: list[dict[str, Any]] = []
    AUDIT.mkdir(parents=True, exist_ok=True)
    for screen, header in HEADERS.items():
        original = Path(existing[screen]["original_path"])
        before = hashlib.sha256(original.read_bytes()).hexdigest()
        with Image.open(original) as image:
            screen_records: list[dict[str, Any]] = []

            def record(field: str, target: Box | None, context: Box, visibility: str, reason: str) -> None:
                if target is not None:
                    assert context[0] <= target[0] < target[2] <= context[2], (screen, field, target, context)
                    assert context[1] <= target[1] < target[3] <= context[3], (screen, field, target, context)
                current = existing[screen]["bbox"]
                assert current[0] <= context[0] < context[2] <= current[2]
                assert current[1] <= context[1] < context[3] <= current[3]
                item = {"screen": screen, "field_key": field,
                        "target_bboxXYXY": list(target) if target else None,
                        "context_bbox": list(context), "visibility": visibility, "reason": reason}
                regions.append(item)
                screen_records.append(item)

            for field, seed in header.items():
                target = ink_box(image, seed, light=field in {"ndg", "denominazione"}, red_only=field == "tipo")
                record(field, target, HEADER_CONTEXT[screen], "visible",
                       "Visually identified header value; target includes the complete glyphs and a two-pixel margin.")
            if screen in SUBJECT_CELLS:
                rows = SUBJECT_CELLS[screen]
                for index in range(1, 5):
                    for field in ("ndg", "denominazione", "ruolo"):
                        if index <= len(rows):
                            target = ink_box(image, rows[index - 1][field])
                            record(f"{field}_{index}", target, SUBJECT_CONTEXT[screen], "visible",
                                   "Real visible subject row; multiline cells are enclosed in full.")
                        else:
                            record(f"{field}_{index}", None, SUBJECT_CONTEXT[screen], "not_present",
                                   f"The real table contains {len(rows)} visible row(s) and ends before subject slot {index}; no fictional target is drawn.")
            else:
                seed, context, visibility, reason = NOTES[screen]
                record("note_della_richiesta", ink_box(image, seed), context, visibility, reason)

            # Audit-only overlays are separate files; neither source screenshots
            # nor workbook/context images are edited.
            current = tuple(existing[screen]["bbox"])
            preview = image.crop(current).convert("RGB")
            draw = ImageDraw.Draw(preview)
            for item in screen_records:
                box = item["target_bboxXYXY"]
                if box is not None:
                    shifted = (box[0] - current[0], box[1] - current[1], box[2] - current[0] - 1, box[3] - current[1] - 1)
                    draw.rectangle(shifted, outline=(220, 30, 30), width=1)
            preview.save(AUDIT / f"{screen}__regions.png")
            screen_checks.append({"screen": screen, "original_sha256": before,
                                  "current_context_crop_complete": True,
                                  "visible_subject_rows": len(SUBJECT_CELLS[screen]) if screen in SUBJECT_CELLS else None,
                                  "note_partial": screen.endswith("Note_chiuso"),
                                  "source_and_current_context_visually_reviewed": True})
        assert hashlib.sha256(original.read_bytes()).hexdigest() == before

    assert len(regions) == 58
    result = {"coordinate_system": "original source image pixels, [left, top, right-exclusive, bottom-exclusive]",
              "method": "Direct visual inspection of every source and current context crop; pixel color/ink boundaries only inside manually selected regions; no OCR, LLM, or value transcription.",
              "region_count": len(regions), "screen_checks": screen_checks,
              "defects": [], "regions": regions}
    (AUDIT / "other_regions.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"screens": len(screen_checks), "regions": len(regions),
                      "target_null": sum(item["target_bboxXYXY"] is None for item in regions),
                      "partial": sum(item["visibility"] == "visible_partial" for item in regions)}))


if __name__ == "__main__":
    main()
