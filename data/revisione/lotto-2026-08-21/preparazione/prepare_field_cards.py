"""Build lossless field-specific cards from visually audited original coordinates."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


OUTPUT = Path(__file__).resolve().parent
AUDIT = OUTPUT / "audit"
CARDS = AUDIT / "field_cards"


def normalize_regions() -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for name in ("list_regions.json", "other_regions.json"):
        data = json.loads((AUDIT / name).read_text(encoding="utf-8"))
        for item in data["regions"]:
            value = dict(item)
            value["target_bbox"] = value.get("bbox", value.get("target_bboxXYXY"))
            result[(value["screen"], value["field_key"])] = value
    data = json.loads((AUDIT / "fidi_regions.json").read_text(encoding="utf-8"))
    for screen in data["screens"]:
        for field in screen["fields"]:
            value = {**field, "screen": screen["screen"]}
            result[(value["screen"], value["field_key"])] = value
    for name in ("list_corrections.json", "fidi_corrections.json", "other_corrections.json"):
        path = AUDIT / name
        if path.exists():
            changes = json.loads(path.read_text(encoding="utf-8"))
            for change in changes["corrections"]:
                key = (change["screen"], change["field_key"])
                assert key in result, key
                result[key].update({key: value for key, value in change.items() if key in {"target_bbox", "target_bboxes", "context_bbox", "visibility"}})
                if "context_bbox" in change:
                    result[key]["context_from_correction"] = True
    return result


def italian_note(region: dict[str, Any]) -> str:
    visibility = region["visibility"].lower()
    if visibility == "visible_truncated_text":
        return "Nome troncato dalla schermata: riporta anche i puntini, senza completare il testo."
    if visibility == "visible_cell_without_rendered_text":
        return "La cella è visibile ma non mostra testo: verificare e scegliere VUOTO se confermato."
    if visibility == "clipped_unreadable":
        return "Campo tagliato al bordo dell’immagine originale. Non completarlo: indica NON LEGGIBILE o PARZIALE se una parte è leggibile."
    if "partial" in visibility:
        return "Il valore è visibile solo in parte nella schermata originale. Trascrivi solo la parte leggibile e scegli PARZIALE."
    if region["target_bbox"] is None:
        if region.get("context_bbox") and ("soggetti" in region["screen"].lower()):
            return "Non è visibile una riga per questo soggetto. Controlla la tabella: VUOTO se la riga è assente, NON VISIBILE se manca la fine della tabella."
        return "Campo fuori schermo o coperto nell’originale: verificare e scegliere NON VISIBILE. Non copiarlo da altre schermate."
    return ""


def main() -> None:
    inventory = json.loads((OUTPUT / "annotation_inventory.json").read_text(encoding="utf-8"))
    regions = normalize_regions()
    CARDS.mkdir(parents=True, exist_ok=True)
    prepared: list[dict[str, Any]] = []
    for index, annotation in enumerate(inventory["annotations"], 2):
        key = (annotation["screen"], annotation["field_key"])
        assert key in regions, key
        region = regions[key]
        target = region["target_bbox"]
        targets = region.get("target_bboxes", [target] if target is not None else [])
        context = region.get("context_bbox")
        visibility = region["visibility"].lower()
        if visibility in {"not_visible", "clipped_unreadable"}:
            context = None
        record: dict[str, Any] = {
            "excel_row": index, "screen": key[0], "field_key": key[1],
            "display_name": annotation["display_name"], "original_path": annotation["screenshot_path"],
            "visibility": visibility, "target_bbox": target, "note": italian_note(region),
            "image_path": None, "image_width": None, "image_height": None,
        }
        if context is None:
            assert target is None
            record["cell_text"] = ("Campo tagliato e non leggibile per intero nell’originale. Consulta la schermata completa."
                                   if visibility == "clipped_unreadable" else "Campo non visibile nell’originale. Consulta la schermata completa.")
            prepared.append(record)
            continue
        with Image.open(annotation["screenshot_path"]) as source:
            source = source.convert("RGB")
            left, top, right, bottom = map(int, context)
            if target is not None:
                tx1, ty1, tx2, ty2 = map(int, target)
                assert 0 <= tx1 < tx2 <= source.width and 0 <= ty1 < ty2 <= source.height, key
                # Keep the column or field label, while avoiding a full table in each card.
                if not region.get("context_from_correction") and annotation["field_key"] in {"n_fido", "rapporto", "descrizione", "scadenza", "importo_euro", "tipo_op"}:
                    left, right = max(left, tx1 - 10), min(right, tx2 + 10)
                elif not region.get("context_from_correction") and "Elenco" not in annotation["screen"] and annotation["field_key"] in {"ndg", "denominazione", "tipo", "filiale_relazione"}:
                    label_space = {"ndg": 40, "denominazione": 16, "tipo": 96, "filiale_relazione": 115}[annotation["field_key"]]
                    left, right = max(left, tx1 - label_space), min(right, tx2 + 12)
                left, top = min(left, tx1 - 3), min(top, ty1 - 3)
                right, bottom = max(right, tx2 + 3), max(bottom, ty2 + 3)
            left, top = max(0, left), max(0, top)
            right, bottom = min(source.width, right), min(source.height, bottom)
            assert left < right and top < bottom, key
            crop = source.crop((left, top, right, bottom))
            # Padding permits an external border even when a value meets the source edge.
            padding = 4
            card = Image.new("RGB", (crop.width + 2 * padding, crop.height + 2 * padding), "white")
            card.paste(crop, (padding, padding))
            markers: list[list[int]] = []
            for part in targets:
                tx1, ty1, tx2, ty2 = map(int, part)
                marker = [tx1 - left + padding - 2, ty1 - top + padding - 2,
                          tx2 - left + padding + 1, ty2 - top + padding + 1]
                ImageDraw.Draw(card).rectangle(marker, outline=(200, 34, 34), width=1)
                markers.append(marker)
            for part in targets:
                tx1, ty1, tx2, ty2 = map(int, part)
                # Adjacent segments can share an edge: restore all protected source pixels.
                card.paste(source.crop(tuple(part)), (tx1 - left + padding, ty1 - top + padding))
            for part in targets:
                tx1, ty1, tx2, ty2 = map(int, part)
                actual_target = card.crop((tx1 - left + padding, ty1 - top + padding,
                                           tx2 - left + padding, ty2 - top + padding))
                expected_target = source.crop(tuple(part))
                assert actual_target.tobytes() == expected_target.tobytes(), key
            target_path = CARDS / f"{annotation['screen']}__{annotation['field_key']}.png"
            card.save(target_path, format="PNG")
            with Image.open(target_path) as saved:
                assert saved.size == card.size and saved.tobytes() == card.tobytes(), key
            record.update({
                "context_bbox": [left, top, right, bottom], "padding": padding,
                "target_bboxes": targets, "marker_bboxes": markers,
                "image_path": str(target_path), "image_width": card.width, "image_height": card.height,
                "image_sha256": hashlib.sha256(target_path.read_bytes()).hexdigest(),
                "target_pixels_unchanged": True if target is not None else None,
                "resampled": False,
            })
        prepared.append(record)
    assert len(prepared) == 320
    data = {"rows": prepared, "counts": dict(Counter(row["visibility"] for row in prepared)),
            "image_count": sum(row["image_path"] is not None for row in prepared),
            "marker_count": sum(len(row.get("marker_bboxes", [])) for row in prepared),
            "marked_field_count": sum(bool(row.get("marker_bboxes")) for row in prepared)}
    (AUDIT / "field_cards.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    for screen in inventory["screens"]:
        cards = [row for row in prepared if row["screen"] == screen["screen"]]
        tile_width = 620
        rendered: list[tuple[dict[str, Any], Image.Image | None, int]] = []
        for row in cards:
            picture = Image.open(row["image_path"]).convert("RGB") if row["image_path"] else None
            if picture is not None:
                factor = min(2, (tile_width - 20) / picture.width)
                picture = picture.resize((round(picture.width * factor), round(picture.height * factor)), Image.Resampling.NEAREST)
            rendered.append((row, picture, max(100, (picture.height if picture else 40) + 60)))
        strips = [rendered[i:i + 2] for i in range(0, len(rendered), 2)]
        total_height = 45 + sum(max(tile[2] for tile in strip) for strip in strips)
        contact = Image.new("RGB", (tile_width * 2, total_height), "#EEF2F7")
        draw = ImageDraw.Draw(contact)
        draw.text((12, 10), screen["screen"], fill="black", font=font)
        y = 45
        for strip in strips:
            for col, (row, picture, _) in enumerate(strip):
                x = col * tile_width
                draw.text((x + 10, y + 6), f"{row['excel_row']}: {row['display_name']} [{row['visibility']}]", fill="black", font=font)
                if picture:
                    contact.paste(picture, (x + 10, y + 40))
                else:
                    draw.text((x + 10, y + 40), "NON VISIBILE: nessun riquadro inventato", fill="#A02020", font=font)
            y += max(tile[2] for tile in strip)
        contact.save(AUDIT / f"cards_{screen['screen']}.png")
    print(json.dumps({key: value for key, value in data.items() if key != "rows"}))


if __name__ == "__main__":
    main()
