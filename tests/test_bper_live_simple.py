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

    assert rows == [{"practice": "sim-006", "field": "ndg", "expected": "91000050", "found": "no", "lines": ""}]


# ------------------------------------------------- the note, line by line

NOTE_LINES = ["- Numero proposta DESK: 9900018", "- Valore immobile presunto: 99.000,00",
              "Richiedente di 62 anni, pensionato."]
NOTE = "\n".join(NOTE_LINES)
NOTE_TRUTH = [("ndg", "NDG", "91000170"), ("note_della_richiesta", "Note della richiesta", NOTE)]


def _note_frame(tmp_path: Path, read: List[str]) -> List[Dict[str, Any]]:
    """A Note da Richiesta frame whose OCR read these lines of the note, one OCR line each."""
    Image.new("RGB", (1600, 1200), "white").save(tmp_path / "00001.png")
    items = [[text, 0.99, [[300, 300 + 30 * i], [1100, 300 + 30 * i], [1100, 320 + 30 * i], [300, 320 + 30 * i]]]
             for i, text in enumerate(read)]
    return [{"file": "00001.png", "ndg": "91000170", "page": "screen 9", "items": items}]


def _note_row(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    return next(r for r in rows if r["field"] == "note_della_richiesta")


def test_a_note_partly_read_reports_the_share_of_its_lines_found(tmp_path) -> None:
    frames = _note_frame(tmp_path, NOTE_LINES[:2])

    note = _note_row(live_simple.found_table({"pratica-a": NOTE_TRUTH}, frames, tmp_path))

    assert (note["found"], note["lines"]) == ("no", "2/3")


def test_a_note_whose_every_line_was_read_is_found(tmp_path) -> None:
    frames = _note_frame(tmp_path, NOTE_LINES)

    note = _note_row(live_simple.found_table({"pratica-a": NOTE_TRUTH}, frames, tmp_path))

    assert (note["found"], note["lines"]) == ("yes", "3/3")


def test_note_lines_read_on_different_scrolled_frames_add_up(tmp_path) -> None:
    first = _note_frame(tmp_path, NOTE_LINES[:2])
    Image.new("RGB", (1600, 1200), "white").save(tmp_path / "00002.png")
    box = [[300, 300], [1100, 300], [1100, 320], [300, 320]]
    second = [{**first[0], "file": "00002.png", "items": [[NOTE_LINES[2], 0.99, box]]}]

    note = _note_row(live_simple.found_table({"pratica-a": NOTE_TRUTH}, first + second, tmp_path))

    assert note["lines"] == "3/3"


def test_each_practice_shows_the_tipo_tooltip_and_the_note_to_its_end() -> None:
    steps = [(s["do"], s.get("target") or s.get("to")) for s in live_simple.walk(["k"])["steps"]]

    assert ("hover", "tipo") in steps and steps[-2:] == [("tab", "note"), ("scroll-page", None)]


def test_percentages_are_per_practice_and_overall() -> None:
    rows = [{"practice": "a", "found": "yes"}, {"practice": "a", "found": "no"},
            {"practice": "b", "found": "yes"}, {"practice": "b", "found": "yes"}]

    assert live_simple.percentages(rows) == {"a": 50.0, "b": 100.0, "overall": 75.0}


# ------------------------------------------------- one frame per dwell, whatever the classifier says

MONITOR = {"left": 0, "top": 0, "width": 1200, "height": 900}
WINDOW = (200, 150, 800, 630)
SUBJECTS = {"view": "detail", "loading": False, "page": "subjects", "ndg": "1"}


class _Shot:
    def __init__(self, img: Image.Image) -> None:
        self.size, self.rgb = img.size, img.convert("RGB").tobytes()


class _Mss:
    monitors = [MONITOR, MONITOR]

    def grab(self, _mon: Dict[str, int]) -> _Shot:
        desktop = Image.new("RGB", (MONITOR["width"], MONITOR["height"]), (200, 0, 200))
        desktop.paste(Image.new("RGB", (586, 473), "white"), (207, 150))
        return _Shot(desktop)

    def close(self) -> None:
        pass


class _Config:
    fps, monitor_index, window_title_contains, image_scale = 3, 1, "zzz-no-such-window-zzz", None
    unsharp_amount, unsharp_radius, unsharp_threshold = 0.8, 1.2, 2
    router_mode, dedup_threshold, route_retry_seconds, local_margin_min = "ml", 3, 1.0, 0.10


def _worker(rect: Any) -> Any:
    import live_test as lt

    worker = lt.make_harness_worker(_Config(), lambda: "simple", None, recorder=lt.Recorder(),
                                    rect_provider=lambda _title: rect, own_rect=lambda: WINDOW,
                                    exposure=lambda: True, guard=lt.PrivacyGuard(), live=True,
                                    scrub=lambda img: lt.blank_outside_window(img, (7, 0, 7, 7)))
    worker._mss_ctx = _Mss()
    worker._detect_page = lambda _img: (None, 0.0, {})  # the classifier recognises nothing
    return worker


def test_a_frame_is_kept_at_a_dwell_even_when_the_classifier_finds_no_page(qapp, tmp_path) -> None:
    kept = live_simple.capture(_worker(WINDOW), SUBJECTS, tmp_path, 0)

    assert (kept["page"], kept["classifier"]) == ("screen 4", None)
    assert (tmp_path / kept["file"]).exists()


def test_a_kept_frame_carries_no_desktop_pixel(qapp, tmp_path) -> None:
    kept = live_simple.capture(_worker(WINDOW), SUBJECTS, tmp_path, 0)

    saved = Image.open(tmp_path / kept["file"]).convert("RGB")
    assert (200, 0, 200) not in {color for _n, color in saved.getcolors(saved.width * saved.height)}


def test_the_guard_still_drops_a_frame_of_a_foreign_window(qapp, tmp_path) -> None:
    kept = live_simple.capture(_worker((0, 0, 600, 480)), SUBJECTS, tmp_path, 0)

    assert kept is None and list(tmp_path.iterdir()) == []


def test_the_frame_is_grabbed_near_the_end_of_a_page_dwell() -> None:
    assert live_simple.grab_time({"do": "next"}, {"t": 10.0, "what": "fidi e garanzie"}, 5000) == 14.0


def test_no_frame_is_grabbed_for_a_step_that_shows_no_page_or_for_an_inner_wait() -> None:
    assert [live_simple.grab_time(step, settled, 5000) for step, settled in [
        ({"do": "unhover", "dwell_ms": 0}, {"t": 1.0, "what": "no tooltip"}),
        ({"do": "start"}, {"t": 1.0, "what": "home"}),
        ({"do": "search"}, {"t": 1.0, "what": "search form"})]] == [None, None, None]
