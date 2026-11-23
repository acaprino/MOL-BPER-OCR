"""The simple live test: its table of truth values found in the OCR of the captured frames, and its saved frames."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

import live_simple

TRUTH = [("ndg", "NDG", "91000170"), ("denominazione", "Denom.", "MARCHESI FRANCESCO"),
         ("note_della_richiesta", "Note della richiesta", "Richiesta di surroga"), ("tipo_op", "Tipo Op.", "")]


def _soggetti_frame(tmp_path: Path) -> List[Dict[str, Any]]:
    """One captured Soggetti frame whose OCR read the header line and nothing of the note."""
    Image.new("RGB", (1600, 1200), "white").save(tmp_path / "00000.png")
    words = [["NDG: 91000170 - MARCHESI FRANCESCO", 0.99, [[400, 400], [900, 400], [900, 420], [400, 420]]]]
    return [{"file": "00000.png", "ndg": "91000170", "page": "screen 4", "items": words}]


def test_a_truth_value_read_on_a_captured_frame_of_its_page_is_found(tmp_path) -> None:
    rows = live_simple.found_table({"pratica-a": TRUTH}, _soggetti_frame(tmp_path), tmp_path)

    assert {r["field"]: r["found"] for r in rows} == {"ndg": "yes", "denominazione": "yes",
                                                     "note_della_richiesta": "no"}


def test_an_empty_truth_value_is_not_counted(tmp_path) -> None:
    rows = live_simple.found_table({"pratica-a": TRUTH}, _soggetti_frame(tmp_path), tmp_path)

    assert "tipo_op" not in {r["field"] for r in rows}


def test_a_practice_the_agent_never_captured_finds_nothing(tmp_path) -> None:
    rows = live_simple.found_table({"sim-006": [("ndg", "NDG", "91000050")]}, [], tmp_path)

    assert rows == [{"practice": "sim-006", "field": "ndg", "expected": "91000050", "found": "no"}]


def test_percentages_are_per_practice_and_overall() -> None:
    rows = [{"practice": "a", "found": "yes"}, {"practice": "a", "found": "no"},
            {"practice": "b", "found": "yes"}, {"practice": "b", "found": "yes"}]

    assert live_simple.percentages(rows) == {"a": 50.0, "b": 100.0, "overall": 75.0}


def test_a_saved_frame_carries_no_desktop_pixel(tmp_path) -> None:
    # A wide window crop after preprocess_for_ocr (x1.25): the invisible borders are about 9 px wide.
    frame = Image.new("RGB", (2390, 1287), "white")
    for box in ((0, 0, 9, 1287), (2381, 0, 2390, 1287), (0, 1278, 2390, 1287)):
        frame.paste((200, 0, 200), box)
    probes = [{"t": 0.0, "state": {"view": "detail", "loading": False, "page": "subjects", "ndg": "1"}}]
    keeper = live_simple.frame_keeper(tmp_path)(lambda: probes, {}, lambda: 0.0)

    keeper.extract_from_image(frame, "Elenco Soggetti")

    saved = Image.open(tmp_path / keeper.frames[0]["file"]).convert("RGB")
    assert (200, 0, 200) not in {color for _n, color in saved.getcolors(2390 * 1287)}
