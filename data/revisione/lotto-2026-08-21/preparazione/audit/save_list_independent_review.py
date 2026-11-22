"""Save the independent visual review and text-only marker corrections."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


AUDIT = Path(__file__).resolve().parent


def main() -> None:
    source = AUDIT / "field_cards.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    rows = [row for row in data["rows"] if "__Elenco" in row["screen"]]
    screens = sorted({row["screen"] for row in rows})
    assert len(screens) == 13
    corrections: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    panels: list[tuple[str, Image.Image]] = []
    for row in rows:
        if row["field_key"] != "evidenze":
            continue
        box = row["target_bbox"]
        with Image.open(row["original_path"]) as original:
            pixels = np.asarray(original.crop(box).convert("RGB")).astype(np.int16)
            red, green, blue = (pixels[:, :, index] for index in range(3))
            # Visual review identifies the green letters as the value. Color
            # boundaries refine only their coordinates, without reading text.
            ink = ((red < 170) & (green > 90) & (blue > 60)
                   & ((green - red) > 35) & ((green - blue) > 5))
            columns = np.flatnonzero(ink.any(axis=0))
            groups: list[tuple[int, int]] = []
            first = previous = int(columns[0])
            for column in columns[1:]:
                column = int(column)
                if column - previous > 4:
                    groups.append((first, previous + 1))
                    first = column
                previous = column
            groups.append((first, previous + 1))
            targets: list[list[int]] = []
            for left, right in groups:
                y, x = np.where(ink[:, left:right])
                if len(x) < 8 or int(y.max()) - int(y.min()) < 3:
                    continue  # Exclude isolated badge antialiasing pixels.
                targets.append([box[0] + left + int(x.min()) - 2,
                                box[1] + int(y.min()) - 2,
                                box[0] + left + int(x.max()) + 3,
                                box[1] + int(y.max()) + 3])
            assert targets, row["screen"]
            correction = {"screen": row["screen"], "field_key": "evidenze",
                          "excel_row": row["excel_row"], "original_path": row["original_path"],
                          "original_sha256": hashlib.sha256(Path(row["original_path"]).read_bytes()).hexdigest(),
                          "old_target_bbox": box, "target_bboxes": targets,
                          "target_bbox": [min(item[0] for item in targets), min(item[1] for item in targets),
                                          max(item[2] for item in targets), max(item[3] for item in targets)],
                          "context_bbox": row["context_bbox"],
                          "draw_separate_rectangles": True,
                          "do_not_draw_union": len(targets) > 1,
                          "reason": "Frame only the visible textual value. Exclude paperclip, other icons, circled symbols and version badge; disconnected text groups need separate rectangles."}
            corrections.append(correction)
            issues.append({"screen": row["screen"], "field_key": "evidenze",
                           "excel_row": row["excel_row"], "coordinates": box,
                           "severity": "must_fix", "issue": "Current marker encloses non-value icons and the version badge.",
                           "correction_file": "list_corrections.json"})
            context = row["context_bbox"]
            panel = original.crop(context).convert("RGB")
            drawing = ImageDraw.Draw(panel)
            for target in targets:
                drawing.rectangle((target[0] - context[0], target[1] - context[1],
                                   target[2] - context[0] - 1, target[3] - context[1] - 1),
                                  outline=(220, 30, 30), width=1)
            panels.append((row["screen"], panel))

    assert len(corrections) == 13
    file_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    correction_output = {"coordinate_system": "original source pixels, [left, top, right-exclusive, bottom-exclusive]",
                         "field_cards_sha256_reviewed": file_hash, "correction_count": len(corrections),
                         "no_values_transcribed": True, "corrections": corrections}
    (AUDIT / "list_corrections.json").write_text(json.dumps(correction_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checks = []
    for screen in screens:
        current = [row for row in rows if row["screen"] == screen]
        checks.append({"screen": screen, "montage_visually_reviewed": True,
                       "card_count": len(current), "other_field_markers_correct": True,
                       "creation_header_distinct_from_assignment_date": True,
                       "truncated_names_preserved_without_completion": True,
                       "out_of_view_fields_not_marked_empty": True,
                       "evidenze_result": "must_fix_text_only_marker",
                       "result": "changes_required"})
    review = {"review_kind": "independent visual review of all 13 list-page montages",
              "field_cards_sha256_reviewed": file_hash,
              "result": "changes_required", "screens_reviewed": len(screens),
              "cards_reviewed": len(rows), "issues": issues, "screen_checks": checks,
              "source_spot_checks": ["51772928__Elenco_dx", "51792073__Elenco_tooltip1", "51859514__Elenco_tooltip1"],
              "notes": ["All 13 existing Evidenze markers include icons or badge: use list_corrections.json before acceptance.",
                        "The partially visible type on 51772928__Elenco_dx remains partial, not blank.",
                        "The unavailable type/status/phase/creation fields on horizontally scrolled sources remain not_visible, not blank.",
                        "No values were transcribed; no OCR or model calls were performed. Sources, cards and workbook were not modified."]}
    (AUDIT / "list_independent_review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    width = max(420, max(panel.width for _, panel in panels) + 16)
    height = sum(panel.height + 30 for _, panel in panels)
    preview = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(preview)
    cursor = 0
    for screen, panel in panels:
        draw.text((8, cursor + 3), screen, fill="black")
        preview.paste(panel, (8, cursor + 22))
        cursor += panel.height + 30
    preview.save(AUDIT / "list_evidenze_corrections_preview.png")
    print(json.dumps({"screens_reviewed": len(screens), "cards_reviewed": len(rows),
                      "issues": len(issues), "corrections": len(corrections)}))


if __name__ == "__main__":
    main()
