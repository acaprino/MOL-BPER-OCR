"""Prepare untouched context crops for a blank human transcription workbook."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


OUTPUT = Path(__file__).resolve().parent
ROOT = OUTPUT.parents[1]
CROPS = OUTPUT / "crops"
BATCH = "lotto-2026-08-21"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def context_bounds(image: Image.Image, stem: str) -> tuple[tuple[int, int, int, int], str, list[str]]:
    """Find broad UI regions by color only, without reading or predicting text."""
    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    red, green, blue = (rgb[:, :, index].astype(np.int16) for index in range(3))
    warnings: list[str] = []
    if stem.lower().startswith("elenco"):
        teal = ((red > 145) & (red < 215) & (green > 175) & (green < 235)
                & (blue > 180) & (blue < 240) & ((green - red) > 10))
        rows = np.flatnonzero(teal.sum(axis=1) > 0.3 * width)
        if len(rows):
            # Include every heading, the sole result row, and any tooltip below it.
            top = max(0, int(rows[0]) - 140)
            bottom = min(height, int(rows[-1]) + 86)
            return (0, top, width, bottom), "table scrollbar with broad heading and tooltip margins", warnings
        # This source has no horizontal scrollbar; its result table is fully visible.
        if (width, height) == (1897, 1020):
            return (20, 340, width - 8, 452), "visually verified table without horizontal scrollbar", warnings
        warnings.append("No table scrollbar found: full source retained for review")
        return (0, 0, width, height), "conservative full source fallback", warnings

    navy = (red < 35) & (green > 20) & (green < 85) & (blue > 60) & (blue < 155)
    # Some screenshots have a navy VDI capture border; it is not application data.
    navy[:8, :] = navy[-8:, :] = False
    navy[:, :8] = navy[:, -8:] = False
    navy_rows = np.flatnonzero(navy.sum(axis=1) > 0.3 * width)
    if not len(navy_rows):
        warnings.append("No application navbar found: full source retained for review")
        return (0, 0, width, height), "conservative full source fallback", warnings

    selected = navy[navy_rows]
    columns = np.flatnonzero(selected.any(axis=0))
    first, last = int(columns[0]), int(columns[-1])
    left = max(0, first - (12 if first < 0.15 * width else round(0.13 * width)))
    right = min(width, last + 24)

    # The beige application tab strip sits below the browser chrome. Keep every
    # visible business header below it, including partial headers after scrolling.
    beige = ((red >= 205) & (green >= 200) & (blue >= 185)
             & ((red - blue) >= 5) & ((green - blue) >= 4)
             & (np.abs(red - green) < 8))
    tab_rows = np.flatnonzero(beige[:min(400, height // 2)].sum(axis=1) > 0.4 * width)
    if len(tab_rows) and int(tab_rows[-1]) < int(navy_rows[0]):
        top = int(tab_rows[-1]) + 1
    else:
        top = max(0, int(navy_rows[0]) - 65)
        warnings.append("Tab strip not detected: conservative margin above the first navy bar")
    # The bottom is deliberately retained: notes or tables can meet the image edge.
    return (left, top, right, height), "application tab strip and navy bars; complete visible bottom retained", warnings


def main() -> None:
    manifest_path = ROOT / "data" / "pratiche" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    practices = [item for item in manifest["practices"] if item["batch"] == BATCH]
    CROPS.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for practice in practices:
        for name in practice["screens"]:
            original = ROOT / "data" / "pratiche" / practice["practice"] / name
            screen = f"{practice['practice']}__{Path(name).stem}"
            target = CROPS / f"{screen}.png"
            before = sha256(original)
            with Image.open(original) as image:
                bounds, method, warnings = context_bounds(image, Path(name).stem)
                crop = image.crop(bounds)
                crop.save(target, format="PNG")
                with Image.open(target) as check:
                    assert check.mode == crop.mode and check.size == crop.size
                    assert check.tobytes() == crop.tobytes(), screen
                records.append({
                    "screen": screen,
                    "practice": practice["practice"],
                    "page": Path(name).stem,
                    "original_path": str(original.resolve()),
                    "original_width": image.width,
                    "original_height": image.height,
                    "original_sha256": before,
                    "crop_path": str(target.resolve()),
                    "crop_width": crop.width,
                    "crop_height": crop.height,
                    "bbox": list(bounds),
                    "bbox_convention": "Pillow left, top, right-exclusive, bottom-exclusive",
                    "crop_sha256": sha256(target),
                    "crop_pixel_sha256": hashlib.sha256(crop.tobytes()).hexdigest(),
                    "method": method,
                    "warnings": warnings,
                    "pixel_equality_verified": True,
                    "resized": False,
                    "quantized": False,
                    "annotated": False,
                })
            assert sha256(original) == before, original
    assert len(practices) == 10 and len(records) == 34
    result = {
        "batch": BATCH,
        "practice_count": len(practices),
        "image_count": len(records),
        "source_manifest": str(manifest_path.resolve()),
        "source_manifest_sha256": sha256(manifest_path),
        "policy": "Original pixels only; no OCR, LLM, expected values, resampling, quantization, or annotations",
        "images": records,
    }
    (OUTPUT / "context_images.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"images": len(records), "practices": len(practices), "warnings": {item["screen"]: item["warnings"] for item in records if item["warnings"]}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
