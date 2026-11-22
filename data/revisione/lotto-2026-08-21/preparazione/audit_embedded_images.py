"""Independently compare every embedded image with its original pixel region."""

from __future__ import annotations

import hashlib
import io
import json
import posixpath
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from PIL import Image, ImageDraw


def main() -> None:
    output = Path(__file__).resolve().parent
    inventory = json.loads((output / "annotation_inventory.json").read_text(encoding="utf-8"))
    contexts = json.loads((output / "context_images.json").read_text(encoding="utf-8"))
    by_screen = {item["screen"]: item for item in contexts["images"]}
    metadata = json.loads((output / "workbook_metadata.json").read_text(encoding="utf-8"))
    field_revision = metadata.get("field_card_revision", False)
    cards = json.loads((output / "audit/field_cards.json").read_text(encoding="utf-8")) if field_revision else None
    path = output / "Revisione_10_pratiche_agosto_da_compilare.xlsx"
    ns = {
        "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    results: list[dict[str, object]] = []
    with ZipFile(path) as archive:
        drawing = ET.fromstring(archive.read("xl/drawings/drawing1.xml"))
        relationships = ET.fromstring(archive.read("xl/drawings/_rels/drawing1.xml.rels"))
        worksheet = ET.fromstring(archive.read("xl/worksheets/sheet2.xml"))
        row_heights = {int(row.attrib["r"]): float(row.attrib.get("ht", "15")) * 4 / 3 for row in worksheet.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheetData/{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row")}
        targets = {item.attrib["Id"]: posixpath.normpath(posixpath.join("xl/drawings", item.attrib["Target"]))
                   if not item.attrib["Target"].startswith("/") else item.attrib["Target"].lstrip("/") for item in relationships}
        for anchor in drawing:
            start = anchor.find("xdr:from", ns)
            assert start is not None
            index = int(start.findtext("xdr:row", namespaces=ns)) - 1
            assert int(start.findtext("xdr:col", namespaces=ns)) == 4
            annotation = inventory["annotations"][index]
            context = by_screen[annotation["screen"]]
            blip = anchor.find(".//a:blip", ns)
            image_bytes = archive.read(targets[blip.attrib[f"{{{ns['r']}}}embed"]])
            with Image.open(io.BytesIO(image_bytes)) as embedded, Image.open(context["original_path"]) as original:
                if field_revision:
                    original = original.convert("RGB")
                    card = cards["rows"][index]
                    assert card["excel_row"] == index + 2 and card["screen"] == annotation["screen"]
                    assert hashlib.sha256(image_bytes).hexdigest() == card["image_sha256"]
                    bbox = card["context_bbox"]
                    padding = card["padding"]
                    crop = original.crop(bbox)
                    expected = Image.new("RGB", (crop.width + 2 * padding, crop.height + 2 * padding), "white")
                    expected.paste(crop, (padding, padding))
                    for marker in card["marker_bboxes"]:
                        ImageDraw.Draw(expected).rectangle(marker, outline=(200, 34, 34), width=1)
                    for target in card["target_bboxes"]:
                        expected.paste(original.crop(target), (target[0] - bbox[0] + padding, target[1] - bbox[1] + padding))
                    for target in card["target_bboxes"]:
                        local = (target[0] - bbox[0] + padding, target[1] - bbox[1] + padding,
                                 target[2] - bbox[0] + padding, target[3] - bbox[1] + padding)
                        assert embedded.crop(local).tobytes() == original.crop(target).tobytes()
                else:
                    bbox = context["bbox"]
                    expected = original.crop(bbox)
                assert embedded.mode == expected.mode
                assert embedded.size == expected.size
                assert embedded.tobytes() == expected.tobytes(), (index, annotation["screen"])
                extent = anchor.find("xdr:ext", ns)
                displayed_width = int(extent.attrib["cx"]) / 9525
                displayed_height = int(extent.attrib["cy"]) / 9525
                assert abs(displayed_width / embedded.width - displayed_height / embedded.height) < 0.00001
                assert displayed_height + int(start.findtext("xdr:rowOff", namespaces=ns)) / 9525 + 5 <= row_heights[index + 2] + 0.01
                if field_revision:
                    assert displayed_width / embedded.width >= 1 - 0.000001
                    assert displayed_width + 6 <= 1200
                results.append({
                    "excel_row": index + 2, "screen": annotation["screen"], "field": annotation["field_key"],
                    "original_bbox": bbox, "embedded_pixels_equal_expected": True,
                    "display_scale": round(displayed_width / embedded.width, 5),
                })
    assert len(inventory["annotations"]) == 320
    assert len(results) == (cards["image_count"] if field_revision else 320)
    if field_revision:
        expected_rows = {item["excel_row"] for item in cards["rows"] if item["image_path"]}
        assert {item["excel_row"] for item in results} == expected_rows
    report = {
        "workbook_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "embedded_crops_verified": len(results),
        "crops_displayed_smaller_than_original": sum(item["display_scale"] < 1 for item in results),
        "original_value_rectangles_pixel_identical": cards["marker_count"] if field_revision else None,
        "fields_without_invented_images": 320 - len(results),
        "rows": results,
    }
    (output / "audit").mkdir(exist_ok=True)
    destination = "final_embedded_audit.json" if field_revision else "initial_embedded_audit.json"
    (output / f"audit/{destination}").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}))


if __name__ == "__main__":
    main()
