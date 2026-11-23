"""The live test harness: the real edge-agent capture path against the BPER emulator.

The pure parts (scenario, truth timeline, scoring, the field comparator, the cost, role and desktop-privacy
guards) are tested on hand-built data. The worker seam is tested with the real BPERCaptureWorker on a fake
monitor grab, and one slow case replays the nine reference screens through the real worker and the real
DINOv2 classifier on a virtual clock.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
from PIL import Image

import live_test as lt

REPO = Path(__file__).resolve().parents[1]
SCENARIOS = REPO / "bper-emulator" / "live_scenarios"


def _scenario(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "name": "prova",
        "geometry": "wide",
        "practices": ["sim-006"],
        "steps": [{"do": "start"}, {"do": "search", "practice": "sim-006"}],
    }
    base.update(overrides)
    return base


# ============================================================ scenario


def test_a_named_geometry_expands_to_its_window_and_zoom() -> None:
    scenario = lt.load_scenario(_scenario(geometry="wide"))

    assert scenario["geometry"]["window"] == [1912, 1030]
    assert scenario["geometry"]["zoom"] == pytest.approx(0.9)


def test_a_step_with_an_unknown_action_is_refused() -> None:
    with pytest.raises(lt.ScenarioError, match="teleport"):
        lt.load_scenario(_scenario(steps=[{"do": "teleport"}]))


def test_a_step_naming_a_practice_the_scenario_does_not_declare_is_refused() -> None:
    with pytest.raises(lt.ScenarioError, match="sim-099"):
        lt.load_scenario(_scenario(steps=[{"do": "search", "practice": "sim-099"}]))


def test_a_practice_can_be_declared_in_visualizzazione() -> None:
    scenario = lt.load_scenario(_scenario(practices=[{"key": "sim-006", "mode": "visualizzazione"}]))

    assert (scenario["practices"], scenario["modes"]) == (["sim-006"], {"sim-006": "visualizzazione"})


def test_a_practice_without_a_mode_is_in_lavorazione() -> None:
    assert lt.load_scenario(_scenario())["modes"] == {"sim-006": "lavorazione"}


def test_an_unknown_practice_mode_is_refused() -> None:
    with pytest.raises(lt.ScenarioError, match="consultazione"):
        lt.load_scenario(_scenario(practices=[{"key": "sim-006", "mode": "consultazione"}]))


def test_a_scenario_longer_than_the_headed_limit_is_refused() -> None:
    long_steps = [{"do": "start"}] + [{"do": "wait", "ms": 10_000}] * 13

    with pytest.raises(lt.ScenarioError, match="120"):
        lt.load_scenario(_scenario(steps=long_steps), max_seconds=120)


def test_every_shipped_scenario_loads() -> None:
    files = sorted(SCENARIOS.glob("*.json"))

    assert files, "no scenario in bper-emulator/live_scenarios"
    for path in files:
        scenario = lt.load_scenario(path)
        if scenario.get("headed"):
            assert lt.estimate_seconds(scenario) <= lt.HEADED_MAX_SECONDS, path.name


# ============================================================ truth timeline


@pytest.mark.parametrize("state, label", [
    ({"view": "list", "loading": False, "scroll": 0, "scrollMax": 600, "tooltip": False}, "screen 1"),
    ({"view": "list", "loading": False, "scroll": 300, "scrollMax": 600, "tooltip": False}, "screen 2"),
    ({"view": "list", "loading": False, "scroll": 600, "scrollMax": 600, "tooltip": True}, "screen 3"),
    ({"view": "detail", "loading": False, "page": "subjects"}, "screen 4"),
    ({"view": "detail", "loading": False, "page": "credit", "tooltip": False}, "screen 5"),
    ({"view": "detail", "loading": False, "page": "credit", "tooltip": True, "tooltipStep": 8}, "screen 8"),
    ({"view": "detail", "loading": False, "page": "notes"}, "screen 9"),
])
def test_each_observed_state_maps_to_its_catalogue_page(state: Dict[str, Any], label: str) -> None:
    assert lt.label_for_probe(state) == (label, "page")


def test_a_list_scrolled_less_than_half_its_own_range_is_still_the_first_list_screen() -> None:
    # The list's offsets move with the site (native state 1 now opens at 0): the range is read from the DOM.
    state = {"view": "list", "loading": False, "scroll": 181, "scrollMax": 640, "tooltip": False}

    assert lt.label_for_probe(state) == ("screen 1", "page")


def test_a_list_that_fits_its_window_is_the_first_list_screen() -> None:
    state = {"view": "list", "loading": False, "scroll": 0, "scrollMax": 0, "tooltip": False}

    assert lt.label_for_probe(state) == ("screen 1", "page")


def test_a_loading_state_is_a_transition_whatever_page_is_underneath() -> None:
    state = {"view": "detail", "loading": True, "page": "subjects"}

    assert lt.label_for_probe(state) == (None, "transition")


def test_a_page_outside_the_catalogue_expects_no_capture() -> None:
    state = {"view": "detail", "loading": False, "page": "delibere"}

    assert lt.label_for_probe(state) == (None, "off-catalogue")


def _probe(t: float, **state: Any) -> Dict[str, Any]:
    return {"t": t, "state": {"loading": False, **state}}


def test_consecutive_probes_of_the_same_state_form_one_segment() -> None:
    probes = [
        _probe(0.0, view="detail", page="subjects"),
        _probe(0.1, view="detail", page="subjects"),
        _probe(4.0, view="detail", page="notes"),
    ]

    segments = lt.truth_segments(probes, end=6.0)

    assert [(s["label"], s["start"], s["end"]) for s in segments] == [
        ("screen 4", 0.0, 4.0), ("screen 9", 4.0, 6.0)]


def test_a_change_that_leaves_the_same_page_on_screen_does_not_split_the_dwell() -> None:
    # A wheel on a list that already fits changes a DOM detail, not the page the operator looks at.
    probes = [
        _probe(0.0, view="list", scroll=0, rows=["1"], hint=False),
        _probe(3.5, view="list", scroll=0, rows=["1"], hint=True),
        _probe(7.0, view="detail", page="subjects", ndg="1"),
    ]

    segments = lt.truth_segments(probes, end=9.0)

    assert [(s["label"], s["start"], s["end"]) for s in segments] == [
        ("screen 1", 0.0, 7.0), ("screen 4", 7.0, 9.0)]


def test_latency_is_measured_for_an_adoption_of_another_screen_too() -> None:
    report = lt.score_run([_segment(10.0, 14.0, "screen 5")], [_adoption(12.5, "screen 6")], frames=[])

    assert report["segments"][0]["latency_s"] == pytest.approx(2.5)


# ============================================================ scoring


def _segment(start: float, end: float, label: Any = "screen 4", kind: str = "page") -> Dict[str, Any]:
    return {"start": start, "end": end, "label": label, "kind": kind, "practice": "1"}


def _adoption(t: float, page: str) -> Dict[str, Any]:
    return {"t": t, "page": page, "name": page, "score": 0.6, "margin": 0.2}


def _outcomes(report: Dict[str, Any]) -> List[str]:
    return [s["outcome"] for s in report["segments"]]


def test_an_adoption_of_the_page_on_screen_is_right() -> None:
    report = lt.score_run([_segment(10.0, 14.0)], [_adoption(12.3, "screen 4")], frames=[])

    assert _outcomes(report) == ["right"]


def test_capture_latency_runs_from_the_moment_the_page_settled() -> None:
    report = lt.score_run([_segment(10.0, 14.0)], [_adoption(12.3, "screen 4")], frames=[])

    assert report["segments"][0]["latency_s"] == pytest.approx(2.3)


def test_an_adoption_of_another_page_is_wrong() -> None:
    report = lt.score_run([_segment(10.0, 14.0)], [_adoption(12.3, "screen 9")], frames=[])

    assert _outcomes(report) == ["wrong"]


def test_a_wrong_screen_of_the_right_page_family_counts_in_the_family_score() -> None:
    report = lt.score_run([_segment(10.0, 14.0, "screen 5")], [_adoption(12.3, "screen 6")], frames=[])

    assert report["summary"]["family_right"] == 1


def test_any_list_screen_adopted_on_the_list_is_right() -> None:
    # At native widths the list's columns do not match the reference states: the list is scored as a page only.
    report = lt.score_run([_segment(10.0, 14.0, "screen 1")], [_adoption(12.3, "screen 2")], frames=[])

    assert _outcomes(report) == ["right"]


def test_a_long_dwell_without_adoption_is_missed() -> None:
    report = lt.score_run([_segment(10.0, 14.0)], [], frames=[])

    assert _outcomes(report) == ["missed"]


def test_a_second_adoption_in_the_same_dwell_is_a_duplicate() -> None:
    adoptions = [_adoption(12.3, "screen 4"), _adoption(13.5, "screen 4")]

    report = lt.score_run([_segment(10.0, 14.0)], adoptions, frames=[])

    assert report["summary"]["duplicates"] == 1


def test_an_adoption_during_a_transition_is_a_false_adoption() -> None:
    report = lt.score_run([_segment(10.0, 14.0, None, "transition")], [_adoption(12.3, "screen 4")], frames=[])

    assert _outcomes(report) == ["false-adoption"]


def test_an_adoption_inside_a_dwell_shorter_than_the_stability_time_is_a_violation() -> None:
    report = lt.score_run([_segment(10.0, 11.0)], [_adoption(10.7, "screen 4")], frames=[])

    assert report["summary"]["fast_violations"] == 1


def test_a_miss_after_an_accepted_label_is_told_apart_from_a_page_never_recognised() -> None:
    frames = [{"t": 10.5, "kept": True, "visit": 1, "routed": {"label": "Elenco Soggetti", "best": "screen 4"}}]

    report = lt.score_run([_segment(10.0, 14.0), _segment(20.0, 24.0)], [], frames=frames)

    assert [s["miss_reason"] for s in report["segments"]] == ["dwell-ended-before-stability", "no-accepted-label"]


def test_pixel_identity_resets_are_counted_per_dwell() -> None:
    frames = [{"t": 10.1 + i * 0.33, "visit": 7 + (i % 3 == 0) * i, "kept": True} for i in range(9)]

    report = lt.score_run([_segment(10.0, 14.0)], [], frames=frames)

    assert report["segments"][0]["visits"] == len({f["visit"] for f in frames})


# ============================================================ field comparator


TRUTH_CSV = "﻿Chiave;Campo;Valore\nndg;NDG;0012345\ndenominazione;Denom.;ROSSI MARIO\ntipo;Tipo;MUTUO\n"


def test_the_practice_truth_csv_is_read_by_field_key() -> None:
    assert lt.parse_practice_truth(TRUTH_CSV) == {
        "ndg": "0012345", "denominazione": "ROSSI MARIO", "tipo": "MUTUO"}


def test_an_extracted_ndg_is_compared_as_an_identifier() -> None:
    result = lt.compare_record({"ndg": "0012345"}, {"ndg": "12345"}, shown={"ndg"})

    assert result["fields"]["ndg"]["status"] == "OK"


def test_a_field_shown_on_screen_but_not_extracted_is_missing() -> None:
    result = lt.compare_record({"tipo": "MUTUO"}, {}, shown={"tipo"})

    assert result["fields"]["tipo"]["status"] == "MISSING"


def test_a_field_the_run_never_showed_is_not_counted_as_missing() -> None:
    result = lt.compare_record({"tipo": "MUTUO"}, {}, shown=set())

    assert result["fields"]["tipo"]["status"] == "NOT_SHOWN"


def test_the_oracle_reads_only_the_ndg_from_a_list_frame() -> None:
    probes = [{"t": 0.0, "state": {"view": "list", "loading": False, "scroll": 0, "scrollMax": 0, "rows": ["123"]}}]
    truth = {"123": {"screen 1": {"ndg": "123", "stato": "LAV", "creazione": "19/01/2026"}}}
    oracle = lt.OraclePipeline(lambda: probes, truth, lambda: 1.0)

    assert oracle.extract_from_image(Image.new("RGB", (8, 8)), "Risultato ricerca")["fields"] == {
        "ndg": {"value": "123", "confidence": 1.0}}


def test_a_list_dwell_sets_no_field_expectation() -> None:
    segments = [_segment(0.0, 4.0, "screen 1"), _segment(4.0, 8.0, "screen 9")]
    screens = {"screen 1": {"ndg": "1", "stato": "LAV"}, "screen 9": {"ndg": "1", "note_della_richiesta": "n"}}

    assert lt.expected_fields(segments, screens, "1") == {"ndg", "note_della_richiesta"}


# ============================================================ cost and role guards


def test_extract_without_accept_cost_is_refused() -> None:
    with pytest.raises(lt.GuardError, match="--accept-cost"):
        lt.check_extract_request(extract=True, accept_cost=False, max_screens=None)


def test_max_screens_defaults_to_twelve() -> None:
    assert lt.check_extract_request(extract=True, accept_cost=True, max_screens=None) == 12


def test_max_screens_above_the_hard_cap_is_refused() -> None:
    with pytest.raises(lt.GuardError, match="60"):
        lt.check_extract_request(extract=True, accept_cost=True, max_screens=61)


def test_a_model_without_a_price_is_refused_because_its_cost_would_print_as_zero() -> None:
    with pytest.raises(lt.GuardError, match="PRICING_PER_1M"):
        lt.estimate_cost("modello-sconosciuto", screens=12)


def test_the_cost_estimate_grows_with_the_screens() -> None:
    assert lt.estimate_cost("gemini-3.8-flash", 24)["upper_usd"] == pytest.approx(
        2 * lt.estimate_cost("gemini-3.8-flash", 12)["upper_usd"])


def test_a_practice_whose_role_is_not_sintetica_is_refused() -> None:
    catalogue = [{"key": "arch-1", "role": "controllo"}, {"key": "sim-006", "role": "sintetica"}]

    with pytest.raises(lt.GuardError, match="arch-1"):
        lt.check_roles(catalogue, ["sim-006", "arch-1"])


def test_a_practice_missing_from_the_catalogue_is_refused() -> None:
    with pytest.raises(lt.GuardError, match="sim-404"):
        lt.check_roles([{"key": "sim-006", "role": "sintetica"}], ["sim-404"])


class _CountingPipeline:
    def __init__(self) -> None:
        self.calls = 0

    def extract_from_image(self, img: Image.Image, screen_id: str) -> Dict[str, Any]:
        self.calls += 1
        return {"screen_id": screen_id, "fields": {}, "_status": "OK"}


def test_the_screen_cap_stops_provider_calls_after_max_screens() -> None:
    inner = _CountingPipeline()
    capped = lt.CappedPipeline(inner, cap=2)

    for _ in range(4):
        capped.extract_from_image(Image.new("RGB", (8, 8)), "screen 1")

    assert inner.calls == 2


def test_a_screen_over_the_cap_completes_without_fields_instead_of_failing() -> None:
    capped = lt.CappedPipeline(_CountingPipeline(), cap=0)

    result = capped.extract_from_image(Image.new("RGB", (8, 8)), "screen 1")

    assert (result["fields"], result["_status"]) == ({}, "SKIPPED_COST_CAP")


def test_the_run_cost_is_summed_from_the_meta_of_each_result() -> None:
    results = [{"_meta_agg": {"estimated_cost_usd": 0.01, "calls": 2, "total_tokens": 100}},
               {"_meta_agg": {"estimated_cost_usd": 0.02, "calls": 3, "total_tokens": 50}}, {}]

    assert lt.summarize_costs(results) == {"cost_usd": pytest.approx(0.03), "calls": 5, "tokens": 150,
                                           "screens": 2}


class _FakeProviderModel:
    """The provider SDK, the only thing faked: one canned reply with token usage, as tests/test_vlm_call.py."""

    def __init__(self, reply: str) -> None:
        from langchain_core.messages import AIMessage

        self.calls = 0
        self.reply = AIMessage(content=reply, usage_metadata={
            "input_tokens": 8000, "output_tokens": 1500, "total_tokens": 9500})

    def bind(self, **_kwargs: Any) -> "_FakeProviderModel":
        return self

    def invoke(self, _messages: Any) -> Any:
        self.calls += 1
        return self.reply


def test_extract_mode_costs_come_from_the_real_pipeline_meta(qapp, monkeypatch) -> None:
    import extraction.pipeline as pipeline_mod
    from extraction.pipeline import ExtractionPipeline
    from local_extraction_client import LocalExtractionClient

    monkeypatch.setattr(pipeline_mod, "STOP_ON_ANCHOR_UNCERTAIN", False)
    fake = _FakeProviderModel('{"fields": {"ndg": {"value": "12345", "confidence": 0.99}}}')
    real = ExtractionPipeline(main_model=fake, anchor_model=fake, main_model_name="gemini-3.8-flash",
                              anchor_model_name="gemini-3.8-flash")
    client = LocalExtractionClient(pipeline=lt.CappedPipeline(real, cap=1))
    job = client.start_job()
    try:
        for _ in range(2):
            client.ingest_frame(job, Image.new("RGB", (64, 48), "white"), 4, "Elenco Soggetti")
        lt.wait_for_extractions(client, timeout=30)
        cost = lt.summarize_costs(client.get_results(job))
    finally:
        client.shutdown()

    assert cost["screens"] == 1 and cost["cost_usd"] > 0


# ============================================================ desktop privacy


def test_an_unchanged_frame_is_discarded() -> None:
    assert lt.frame_verdict("unchanged", None, (0, 0, 100, 100), exposed=True, live=True) == (False, "unchanged")


def test_a_window_rect_that_is_not_the_emulator_window_is_discarded() -> None:
    verdict = lt.frame_verdict("window-rect", (0, 0, 800, 600), (100, 100, 900, 700), exposed=True, live=True)

    assert verdict == (False, "foreign-window")


def test_a_covered_emulator_window_is_discarded() -> None:
    verdict = lt.frame_verdict("window-rect", (0, 0, 800, 600), (0, 0, 800, 600), exposed=False, live=True)

    assert verdict == (False, "not-exposed")


def test_a_content_rect_crop_is_not_trusted_on_the_real_desktop() -> None:
    verdict = lt.frame_verdict("content-rect", (0, 0, 800, 600), (0, 0, 800, 600), exposed=True, live=True)

    assert verdict == (False, "content-rect-on-desktop")


def test_the_exposed_emulator_window_is_kept() -> None:
    assert lt.frame_verdict("window-rect", (0, 0, 800, 600), (0, 0, 800, 600), exposed=True, live=True) == (True, "")


def test_the_run_aborts_at_the_third_unchanged_frame() -> None:
    guard = lt.PrivacyGuard()
    guard.observe(False, "unchanged")
    guard.observe(False, "unchanged")

    with pytest.raises(lt.PrivacyAbort):
        guard.observe(False, "unchanged")


# ------------------------------------------------- the guard at the worker seam

MONITOR = {"left": 0, "top": 0, "width": 1200, "height": 900}


class _FakeShot:
    def __init__(self, img: Image.Image) -> None:
        self.size = img.size
        self.rgb = img.convert("RGB").tobytes()


class _FakeMss:
    def __init__(self, img: Image.Image) -> None:
        self.img = img
        self.monitors = [MONITOR, MONITOR]

    def grab(self, _mon: Dict[str, int]) -> _FakeShot:
        return _FakeShot(self.img)

    def close(self) -> None:
        pass


class _Config:
    fps = 3
    monitor_index = 1
    window_title_contains = "zzz-no-such-window-zzz"
    image_scale = None
    unsharp_amount = 0.8
    unsharp_radius = 1.2
    unsharp_threshold = 2
    router_mode = "ml"
    dedup_threshold = 3
    route_retry_seconds = 1.0
    local_margin_min = 0.10


def _maximized_desktop() -> Image.Image:
    # No window rectangle and no uniform border: normalize_frame leaves the whole monitor in place.
    frame = Image.new("RGB", (MONITOR["width"], MONITOR["height"]), "white")
    frame.paste(Image.new("RGB", (MONITOR["width"], 60), (10, 40, 90)), (0, 0))
    return frame


def test_an_unchanged_frame_never_reaches_the_page_router(qapp) -> None:
    routed: List[Any] = []
    worker = lt.make_harness_worker(_Config(), lambda: "job", None, recorder=lt.Recorder(),
                                    rect_provider=lambda _title: None, exposure=lambda: True,
                                    guard=lt.PrivacyGuard(), live=True)
    worker._mss_ctx = _FakeMss(_maximized_desktop())
    worker._detect_page = lambda img: routed.append(img) or (None, 0.0, {})

    worker._capture_once()

    assert routed == []


def test_an_unchanged_frame_is_never_saved(qapp) -> None:
    saved: List[Any] = []
    worker = lt.make_harness_worker(_Config(), lambda: "job", None, recorder=lt.Recorder(),
                                    rect_provider=lambda _title: None, exposure=lambda: True,
                                    guard=lt.PrivacyGuard(), live=True, keep_frame=lambda f, img: saved.append(img))
    worker._mss_ctx = _FakeMss(_maximized_desktop())

    worker._capture_once()

    assert saved == []


def test_the_window_frame_is_saved_when_it_is_the_exposed_emulator_window(qapp) -> None:
    window = (200, 150, 800, 630)
    desktop = Image.new("RGB", (MONITOR["width"], MONITOR["height"]), (32, 34, 38))
    desktop.paste(Image.new("RGB", (600, 480), "white"), window[:2])
    saved: List[Any] = []
    worker = lt.make_harness_worker(_Config(), lambda: "job", None, recorder=lt.Recorder(),
                                    rect_provider=lambda _title: window, own_rect=lambda: window,
                                    exposure=lambda: True, guard=lt.PrivacyGuard(), live=True,
                                    keep_frame=lambda f, img: saved.append(img.size))
    worker._mss_ctx = _FakeMss(desktop)
    worker._detect_page = lambda img: (None, 0.0, {})

    worker._capture_once()

    assert saved == [(600, 480)]


def _window_with_desktop_strips() -> Image.Image:
    img = Image.new("RGB", (100, 80), "white")
    for box in ((0, 0, 7, 80), (93, 0, 100, 80), (0, 73, 100, 80)):
        img.paste((200, 0, 200), box)  # what lies behind the invisible borders
    return img


def test_blanking_leaves_no_desktop_pixel_outside_the_drawn_window() -> None:
    blanked = lt.blank_outside_window(_window_with_desktop_strips(), (7, 0, 7, 7))

    assert (200, 0, 200) not in {color for _n, color in blanked.getcolors(100 * 80)}


def test_saved_frames_carry_no_desktop_pixel(tmp_path) -> None:
    saver = lt.FrameSaver(tmp_path, mask=lambda: (7, 0, 7, 7))
    saver({"index": 0, "t": 0.0}, _window_with_desktop_strips())
    saver.close()

    saved = Image.open(tmp_path / "00000.png").convert("RGB")
    assert (200, 0, 200) not in {color for _n, color in saved.getcolors(100 * 80)}


def test_an_extract_run_hands_the_worker_a_frame_without_desktop_strips(qapp) -> None:
    window = (200, 150, 800, 630)
    desktop = Image.new("RGB", (MONITOR["width"], MONITOR["height"]), (200, 0, 200))
    desktop.paste(Image.new("RGB", (586, 473), "white"), (207, 150))
    worker = lt.make_harness_worker(_Config(), lambda: "job", None, recorder=lt.Recorder(),
                                    rect_provider=lambda _title: window, own_rect=lambda: window,
                                    exposure=lambda: True, guard=lt.PrivacyGuard(), live=True,
                                    scrub=lambda img: lt.blank_outside_window(img, (7, 0, 7, 7)))
    worker._mss_ctx = _FakeMss(desktop)

    framed = worker._grab_raw()

    assert (200, 0, 200) not in {color for _n, color in framed.getcolors(600 * 480)}


def test_a_config_whose_router_is_not_ml_is_refused() -> None:
    class Llm(_Config):
        router_mode = "llm"

    with pytest.raises(lt.GuardError, match="ml"):
        lt.require_ml_router(Llm())


# ============================================================ replay of the reference screens (slow)


def _reference_recording(tmp_path: Path) -> Path:
    """The nine reference screens as a recording: each held 3.5 s, with a 1 s glimpse of another screen between."""
    from tools.reference_screens import reference_screens

    screens = reference_screens()
    frames, probes, t = [], [], 0.0
    blank = tmp_path / "blank.png"
    Image.new("RGB", (848, 679), "white").save(blank)
    frames.append({"t": t, "image": blank.name, "window": [536, 200, 848, 679], "kind": "window"})
    probes.append({"t": t, "state": {"label": None, "kind": "transition"}})
    t += 2.0
    for n in range(1, 10):
        # The glimpse is never the screen before or after it, so it is a visit of its own.
        for label, hold in ((f"screen {n}", 3.5), (f"screen {(n + 4) % 9 + 1}", 1.0)):
            frames.append({"t": t, "image": str(screens[label]), "window": [536, 200, 848, 679], "kind": "window"})
            probes.append({"t": t, "state": {"label": label, "kind": "page", "ndg": "ref"}})
            t += hold
    # Framed from the uniform desktop, as test_page_classifier frames them: an exact window-rect crop moves the
    # framing by 1-3 px, which flips Gestione Fidi variants whose margins are below 0.01 (reported, not tested here).
    recording = {"canvas": [1920, 1080], "desktop": [32, 34, 38], "framing": "content-rect", "frames": frames,
                 "probes": probes, "end": t}
    (tmp_path / "recording.json").write_text(json.dumps(recording), encoding="utf-8")
    return tmp_path


@pytest.mark.slow
def test_the_reference_screens_replay_through_the_real_worker(qapp, tmp_path) -> None:
    pytest.importorskip("torch", reason="DINOv2 page classifier needs torch")
    report = lt.run_virtual_replay(_reference_recording(tmp_path), truth={})

    summary = report["score"]["summary"]
    assert (summary["right"], summary["wrong"], summary["fast_violations"]) == (9, 0, 0), summary
    assert set(report["frames"]["strategies"]) == {"content-rect"}
