"""Verify the delivered annotation workbook and package its original screenshots."""

from __future__ import annotations

import hashlib
import json
import posixpath
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import load_workbook


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finalize_native_navigation(path: Path, links: list[dict[str, str]]) -> int:
    """Add native internal links absent from the authoring API and reuse identical PNGs."""
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relationship_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    ET.register_namespace("", main_ns)
    ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
    with ZipFile(path) as archive:
        entries = {item.filename: (item, archive.read(item.filename)) for item in archive.infolist()}
    grouped: dict[str, list[dict[str, str]]] = {}
    for link in links:
        grouped.setdefault(link["sheet"], []).append(link)
    following_elements = {
        "printOptions", "pageMargins", "pageSetup", "headerFooter", "rowBreaks", "colBreaks",
        "customProperties", "cellWatches", "ignoredErrors", "smartTags", "drawing",
        "legacyDrawing", "legacyDrawingHF", "picture", "oleObjects", "controls", "webPublishItems", "tableParts", "extLst",
    }
    for index, sheet_name in enumerate(("Istruzioni", "Revisione", "Schermate"), 1):
        entry = f"xl/worksheets/sheet{index}.xml"
        info, raw = entries[entry]
        root = ET.fromstring(raw)
        hyperlinks = root.find(f"{{{main_ns}}}hyperlinks")
        if hyperlinks is None:
            hyperlinks = ET.Element(f"{{{main_ns}}}hyperlinks")
            position = next((i for i, child in enumerate(root) if child.tag.split("}")[-1] in following_elements), len(root))
            root.insert(position, hyperlinks)
        else:
            hyperlinks.clear()
        for link in grouped.get(sheet_name, []):
            ET.SubElement(hyperlinks, f"{{{main_ns}}}hyperlink", {
                "ref": link["address"], "location": link["location"], "display": link["label"],
            })
        entries[entry] = (info, ET.tostring(root, encoding="utf-8", xml_declaration=True))
    seen: dict[str, str] = {}
    duplicate_media: dict[str, str] = {}
    for name, (_, raw) in entries.items():
        if name.startswith("xl/media/"):
            digest = hashlib.sha256(raw).hexdigest()
            if digest in seen:
                duplicate_media[name] = seen[digest]
            else:
                seen[digest] = name
    for name, (info, raw) in list(entries.items()):
        if not name.endswith(".rels"):
            continue
        root = ET.fromstring(raw)
        base = posixpath.dirname(posixpath.dirname(name))
        changed = False
        for relationship in root.findall(f"{{{relationship_ns}}}Relationship"):
            target = relationship.get("Target", "")
            resolved = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(base, target))
            if resolved in duplicate_media:
                replacement = duplicate_media[resolved]
                relationship.set("Target", "/" + replacement if target.startswith("/") else posixpath.relpath(replacement, base))
                changed = True
        if changed or b"ns0:Relationships" in raw:
            ET.register_namespace("", relationship_ns)
            entries[name] = (info, ET.tostring(root, encoding="utf-8", xml_declaration=True))
    content_entry = "[Content_Types].xml"
    info, raw = entries[content_entry]
    content_root = ET.fromstring(raw)
    for child in list(content_root):
        if child.get("PartName", "").lstrip("/") in duplicate_media:
            content_root.remove(child)
    ET.register_namespace("", "http://schemas.openxmlformats.org/package/2006/content-types")
    entries[content_entry] = (info, ET.tostring(content_root, encoding="utf-8", xml_declaration=True))
    temporary = path.with_name(path.stem + ".finalizing.xlsx")
    with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
        for name, (info, raw) in entries.items():
            if name not in duplicate_media:
                archive.writestr(info, raw)
    temporary.replace(path)
    return len(duplicate_media)


def main() -> None:
    output = Path(__file__).resolve().parent
    repository = output.parents[1]
    inventory = json.loads((output / "annotation_inventory.json").read_text(encoding="utf-8"))
    metadata = json.loads((output / "workbook_metadata.json").read_text(encoding="utf-8"))
    path = Path(metadata["output"])
    reused_media = finalize_native_navigation(path, metadata["navigation_links"])
    workbook = load_workbook(path, data_only=False)
    assert workbook.sheetnames == ["Istruzioni", "Revisione", "Schermate"]
    review = workbook["Revisione"]
    assert review.max_row == 321
    assert review.max_column == 9
    assert review.freeze_panes == "E2", review.freeze_panes
    keys: set[tuple[str, str]] = set()
    for number, item in enumerate(inventory["annotations"], 2):
        assert review.cell(number, 1).value == number - 1
        assert review.cell(number, 2).value == item["practice"]
        assert review.cell(number, 4).value == item["display_name"]
        assert review.cell(number, 9).value == item["screen"]
        assert review.cell(number, 6).value is None
        assert review.cell(number, 7).value is None
        assert review.cell(number, 6).number_format == "@"
        key = (item["screen"], item["field_key"])
        assert key not in keys
        keys.add(key)
        expected_link = f"'Schermate'!A{metadata['screenshot_rows'][item['screen']]}"
        assert review.cell(number, 3).hyperlink.location == expected_link
        assert review.cell(number, 3).value == item["screen"].split("__")[1] + ".png"
    assert len(review._images) == metadata.get("embedded_field_images", 320)
    assert len(workbook["Schermate"]._images) == 34
    validations = list(review.data_validations.dataValidation)
    assert len(validations) == 1
    assert str(validations[0].sqref) == "G2:G321"
    assert all(word in validations[0].formula1 for word in ("TRASCRITTO", "VUOTO", "NON LEGGIBILE", "NON VISIBILE", "PARZIALE"))
    counts = Counter(item["practice"] for item in inventory["annotations"])
    assert len(counts) == 10
    assert dict(counts) == inventory["counts"]["rows_by_practice"]
    for link in metadata["navigation_links"]:
        cell = workbook[link["sheet"]][link["address"]]
        assert cell.value == link["label"]
        assert cell.hyperlink.location == link["location"]
    for sheet in workbook:
        for row in sheet:
            for cell in row:
                assert cell.data_type != "e", (sheet.title, cell.coordinate, cell.value)
    workbook.close()
    cards = json.loads((output / "audit/field_cards.json").read_text(encoding="utf-8"))
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        media_hashes = {hashlib.sha256(archive.read(name)).hexdigest() for name in names if name.startswith("xl/media/")}
        for screen in inventory["screens"]:
            assert screen["screenshot_sha256"] in media_hashes
        for card in cards["rows"]:
            if card["image_path"]:
                assert card["image_sha256"] in media_hashes
        relationship_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
        for name in names:
            if not name.endswith(".rels"):
                continue
            root = ET.fromstring(archive.read(name))
            base = posixpath.dirname(posixpath.dirname(name))
            for relationship in root.findall(f"{{{relationship_ns}}}Relationship"):
                if relationship.get("Type", "").endswith("/image"):
                    target = relationship.attrib["Target"]
                    resolved = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(base, target))
                    assert resolved in names, (name, target)
    source_manifest = json.loads((repository / "data/training/ground-truth-v3.1/manifest.json").read_text(encoding="utf-8"))
    source = repository / "data/revisione/revisione/Revisione_ground_truth_v3_1.xlsx"
    assert sha256(source) == source_manifest["workbook"]["sha256"]
    package = output / "Materiale_per_Rita_10_pratiche.zip"
    readme = (
        "ANNOTAZIONE DELLE 10 PRATICHE DI AGOSTO\n\n"
        "Apri Revisione_10_pratiche_agosto_da_compilare.xlsx e leggi il foglio Istruzioni.\n"
        "Nel foglio Revisione compila le celle gialle Trascrizione, Esito e Note.\n"
        "Il file contiene 320 campi per 34 schermate di 10 pratiche. Nessuna risposta è precompilata.\n"
        "Le immagini sono incorporate nell'Excel. I nomi delle schermate portano alla vista completa.\n"
        "La cartella schermate contiene anche i 34 PNG originali, senza modifiche.\n"
        "Non occorre ricompilare la revisione precedente delle 12 pratiche.\n"
        "Questo lotto non contiene Scheda Privati.\n"
    )
    with ZipFile(package, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(path, path.name)
        archive.writestr("LEGGIMI.txt", readme.encode("utf-8"))
        for screen in inventory["screens"]:
            image = Path(screen["screenshot_path"])
            assert sha256(image) == screen["screenshot_sha256"]
            archive.write(image, f"schermate/{screen['practice']}/{screen['filename']}")
    with ZipFile(package) as archive:
        assert archive.testzip() is None
        assert len([name for name in archive.namelist() if name.endswith(".png")]) == 34
        assert len([name for name in archive.namelist() if name.endswith(".xlsx")]) == 1
        for screen in inventory["screens"]:
            archived = archive.read(f"schermate/{screen['practice']}/{screen['filename']}")
            assert hashlib.sha256(archived).hexdigest() == screen["screenshot_sha256"]
    result = {
        "workbook": str(path),
        "workbook_bytes": path.stat().st_size,
        "package": str(package),
        "package_bytes": package.stat().st_size,
        "practices": len(counts),
        "screens": 34,
        "annotation_rows": len(keys),
        "blank_human_transcriptions": 320,
        "blank_human_outcomes": 320,
        "embedded_field_images": metadata.get("embedded_field_images", 320),
        "embedded_original_images": 34,
        "original_workbook_unchanged": True,
        "archive_verified": True,
        "native_navigation_links_verified": len(metadata["navigation_links"]),
        "identical_media_reused": reused_media,
    }
    (output / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
