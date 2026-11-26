"""Live test of the edge agent against the BPER emulator: the real capture path and a scripted operator.

The real BPERCaptureWorker (frame_normalize, preprocess_for_ocr, pHash dedup, StabilityTracker), the real DINOv2
page classifier (router ``ml``, no LLM) and the real page registry run inside a QCoreApplication. Frames come
through the worker's own ``_grab_raw()``, fed one of two ways:

* ``live``: the real mss grab of the monitor while ``live_driver.cjs`` drives a headed Chrome window;
* ``replay``: a recording (headless renders of the same scenario, or the nine reference screens) pasted into a
  desktop canvas at the window rectangle, served at the worker's fps on a virtual or a real clock.

Extraction defaults to an oracle that returns the emulator's truth for the state on screen, so the run is free and
"one row per practice" measures grouping given perfect reading. ``--extract --accept-cost`` uses the real
ExtractionPipeline instead (paid provider calls, capped by ``--max-screens``).

Desktop privacy: a full-monitor frame is never saved, shown or forwarded. A live frame reaches routing only when
frame_normalize cropped it to the emulator window by its window rectangle and that window is the one on top;
anything else is discarded and counted, and the run stops at the third such frame.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import math
import os
import queue
import shutil
import statistics
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DRIVER = HERE / "live_driver.cjs"
SERVER = HERE / "serve_bper_simulator.py"
EDGE_AGENT = REPO / "src" / "edge-agent"
for _path in (REPO, REPO / "src", EDGE_AGENT, HERE):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

Rect = Tuple[int, int, int, int]

# ============================================================
# Constants
# ============================================================

HEADED_MAX_SECONDS = 120
MAX_SCREENS_DEFAULT = 12
MAX_SCREENS_CAP = 60
# The emulator's <title>; Chrome shows it in the window title, which is what frame_normalize matches.
WINDOW_TITLE = "BPER · Nuova PEF"
# How a Chrome window sits inside its GetWindowRect on Windows 11 at 100%, measured in live run 1: invisible resize
# borders of 7 px left, right and bottom (DwmGetWindowAttribute), a 1 px frame, then 87 px of tab strip and toolbar
# above the page. A replay draws the same, so its crop matches a live one.
# shortcut: measured on one Windows 11 machine at 100% scaling, re-measure (report notes) on another machine or DPI
CHROME_UI_HEIGHT = 87
INVISIBLE_BORDER = 7
FRAME_BORDER = 1


def viewport_of(window: Sequence[int]) -> Tuple[int, int]:
    """Device-pixel size of the page area of a Chrome window whose GetWindowRect is `window` (width, height)."""
    w, h = window
    return (w - 2 * INVISIBLE_BORDER - 2 * FRAME_BORDER, h - INVISIBLE_BORDER - CHROME_UI_HEIGHT - FRAME_BORDER)
GEOMETRIES: Dict[str, Dict[str, Any]] = {
    # The reference screenshots: a 1280 px window at browser zoom 110% (app.js), later shrunk to 848x679.
    "reference": {"window": [1280, 1025], "position": [40, 40], "zoom": 1.1},
    # What the real archive mostly shows (fidelity audit): a ~1912 px window at browser zoom 90%.
    "wide": {"window": [1912, 1030], "position": [4, 4], "zoom": 0.9},
    # A maximized window at 90%: its invisible borders fall outside the monitor, so the crop holds no desktop
    # (live only; the window size is the work area of the measuring machine).
    "maximized": {"window": [1920, 1152], "position": [0, 0], "zoom": 0.9, "maximized": True},
}
PAGE_FAMILY = {
    "screen 1": "elenco", "screen 2": "elenco", "screen 3": "elenco", "screen 4": "soggetti",
    "screen 5": "fidi", "screen 6": "fidi", "screen 7": "fidi", "screen 8": "fidi", "screen 9": "note",
}
# The list is judged as a page only: at native widths its columns are not those of the reference states (state 1
# opens at offset 0, Creazione can sit under the pinned Evidenze), so neither the exact list screen nor its fields
# per screen are expected.
PAGE_ONLY_FAMILIES = {"elenco"}
PRACTICE_MODES = {"lavorazione", "visualizzazione"}
HOVER_TARGETS = {"evidence", "tipo", "fido", "guarantee-1", "guarantee-2"}
SCROLL_TARGETS = {"start", "middle", "end"}
TAB_TARGETS = {"fidi", "note"}
# Seconds each action takes before its page settles, with the emulator's native waits (loading.js, pef-extra.js).
ACTION_SECONDS = {
    "start": 2.5, "search": 2.5, "open": 8.8, "next": 9.0, "tab": 2.0, "list": 0.6, "scroll-list": 0.6,
    "hover": 0.4, "unhover": 0.4, "resize": 1.0, "wait": 0.0,
    "scroll-page": 10.0,  # a long note: about two more viewports, each with its own dwell
}
# Cost model of one screen, calibrated on the recorded gemini-3.8-flash baseline (~$0.04/screen, CLAUDE.md).
# shortcut: assumed tokens and calls per screen, replace with the _meta of the first paid run
TYPICAL_INPUT_TOKENS = 8000
TYPICAL_OUTPUT_TOKENS = 1500
TYPICAL_CALLS_PER_SCREEN = 3


class ScenarioError(ValueError):
    """A scenario file that cannot be played."""


class GuardError(RuntimeError):
    """A run refused before it starts: cost, role or configuration."""


class PrivacyAbort(RuntimeError):
    """The live run stopped because frames could not be confined to the emulator window."""


# ============================================================
# Scenario
# ============================================================


def _positive_pair(value: Any, what: str) -> List[int]:
    if not (isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) for v in value)):
        raise ScenarioError(f"{what} must be a list of two integers, got {value!r}")
    return list(value)


def _geometry(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        if value not in GEOMETRIES:
            raise ScenarioError(f"unknown geometry {value!r} (known: {', '.join(GEOMETRIES)})")
        return {"name": value, **copy.deepcopy(GEOMETRIES[value])}
    if not isinstance(value, dict):
        raise ScenarioError("geometry must be a name or an object")
    window = _positive_pair(value.get("window"), "geometry.window")
    position = _positive_pair(value.get("position", [0, 0]), "geometry.position")
    zoom = value.get("zoom", 1.0)
    if not isinstance(zoom, (int, float)) or not 0.25 <= zoom <= 5 or min(window) < 200:
        raise ScenarioError(f"geometry out of range: window {window}, zoom {zoom}")
    return {"name": str(value.get("name", "custom")), "window": window, "position": position, "zoom": float(zoom),
            "maximized": bool(value.get("maximized", False))}


def _practices(value: Any) -> Tuple[List[str], Dict[str, str]]:
    """Practice keys in order, and the mode each one is opened in (lavorazione unless stated)."""
    if not (isinstance(value, list) and value):
        raise ScenarioError("'practices' must list the practice keys the steps use")
    keys: List[str] = []
    modes: Dict[str, str] = {}
    for entry in value:
        key, mode = (entry, "lavorazione") if isinstance(entry, str) else (
            entry.get("key") if isinstance(entry, dict) else None,
            entry.get("mode", "lavorazione") if isinstance(entry, dict) else None)
        if not isinstance(key, str) or not key:
            raise ScenarioError(f"a practice is a key or an object with 'key', got {entry!r}")
        if mode not in PRACTICE_MODES:
            raise ScenarioError(f"practice {key}: mode {mode!r} is not one of {sorted(PRACTICE_MODES)}")
        if key not in modes:
            keys.append(key)
        modes[key] = mode
    return keys, modes


def _check_step(index: int, step: Any, practices: Set[str]) -> Dict[str, Any]:
    if not isinstance(step, dict) or step.get("do") not in ACTION_SECONDS:
        raise ScenarioError(f"step {index}: unknown action {step.get('do') if isinstance(step, dict) else step!r}")
    action = step["do"]
    if action in ("search", "open") and step.get("practice") not in practices:
        raise ScenarioError(f"step {index}: practice {step.get('practice')!r} is not declared in 'practices'")
    if action == "hover" and step.get("target") not in HOVER_TARGETS:
        raise ScenarioError(f"step {index}: hover target must be one of {sorted(HOVER_TARGETS)}")
    if action == "scroll-list" and step.get("to") not in SCROLL_TARGETS:
        raise ScenarioError(f"step {index}: scroll-list 'to' must be one of {sorted(SCROLL_TARGETS)}")
    if action == "tab" and step.get("to") not in TAB_TARGETS:
        raise ScenarioError(f"step {index}: tab 'to' must be one of {sorted(TAB_TARGETS)}")
    if action == "resize":
        _positive_pair(step.get("window"), f"step {index}: window")
        if "position" in step:
            _positive_pair(step["position"], f"step {index}: position")
    if action == "wait" and not (isinstance(step.get("ms"), int) and step["ms"] >= 0):
        raise ScenarioError(f"step {index}: wait needs a non-negative integer 'ms'")
    if "dwell_ms" in step and not (isinstance(step["dwell_ms"], int) and step["dwell_ms"] >= 0):
        raise ScenarioError(f"step {index}: dwell_ms must be a non-negative integer")
    return dict(step)


def load_scenario(source: Any, *, max_seconds: Optional[float] = None) -> Dict[str, Any]:
    """Read and validate a scenario (a path or a dict); geometry names are expanded."""
    if isinstance(source, dict):
        data = copy.deepcopy(source)
    else:
        try:
            data = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ScenarioError(f"cannot read scenario {source}: {exc}") from exc
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        raise ScenarioError("a scenario needs a 'name'")
    practices, modes = _practices(data.get("practices"))
    steps = data.get("steps")
    if not (isinstance(steps, list) and steps):
        raise ScenarioError("a scenario needs 'steps'")
    checked = [_check_step(i, step, set(practices)) for i, step in enumerate(steps)]
    if checked[0]["do"] != "start":
        raise ScenarioError("the first step must be 'start'")
    scenario = {
        "name": data["name"].strip(),
        "description": str(data.get("description", "")),
        "geometry": _geometry(data.get("geometry", "reference")),
        "loading": bool(data.get("loading", True)),
        "dwell_ms": int(data.get("dwell_ms", 3500)),
        "practices": practices,
        "modes": modes,
        "profiles": [str(p) for p in data.get("profiles", [])],
        "headed": bool(data.get("headed", False)),
        "steps": checked,
    }
    if max_seconds is not None and estimate_seconds(scenario) > max_seconds:
        raise ScenarioError(
            f"scenario {scenario['name']!r} takes about {estimate_seconds(scenario):.0f} s, "
            f"over the {max_seconds:.0f} s a headed run may last")
    return scenario


def step_dwell_ms(scenario: Dict[str, Any], step: Dict[str, Any]) -> int:
    """How long the operator stays on what a step shows; a wait is its own duration."""
    if step["do"] == "wait":
        return 0
    return int(step.get("dwell_ms", scenario["dwell_ms"]))


def estimate_seconds(scenario: Dict[str, Any]) -> float:
    """Expected duration of a scenario, from the emulator's waits and the dwells."""
    total = 0.0
    for step in scenario["steps"]:
        action = ACTION_SECONDS[step["do"]]
        if not scenario["loading"]:
            action = min(action, 0.6)
        total += action + step_dwell_ms(scenario, step) / 1000 + step.get("ms", 0) / 1000
    return total


# ============================================================
# Truth timeline
# ============================================================

_TRANSITION_FLAGS = ("loading", "veil", "menu", "ghost", "notice", "alert")
_VOLATILE_KEYS = {"t", "title"}


def label_for_probe(state: Dict[str, Any]) -> Tuple[Optional[str], str]:
    """The catalogue page ('screen N') an observed emulator state shows, and its kind.

    kind is ``page`` (a catalogue page: one adoption expected when the operator dwells), ``transition`` (loading,
    menus, notices: nothing to adopt) or ``off-catalogue`` (Home, Ricerca, Note Delibere, documents...: a capture
    there is a false adoption). A synthetic recording states ``label`` and ``kind`` directly.
    """
    if "label" in state or "kind" in state:
        label = state.get("label")
        return label, str(state.get("kind") or ("page" if label else "transition"))
    if not state.get("ready", True) or any(state.get(flag) for flag in _TRANSITION_FLAGS):
        return None, "transition"
    view = state.get("view")
    if view == "list":
        if state.get("tooltip"):
            return "screen 3", "page"
        # Past half of the list's own scroll range, read from the DOM, as list.js publishes state 2 past half of
        # its two offsets; the offsets themselves move with the site.
        scroll, scroll_max = state.get("scroll") or 0, state.get("scrollMax") or 0
        if scroll_max > 0 and 2 * scroll + 2 >= scroll_max:
            return "screen 2", "page"
        return "screen 1", "page"
    if view == "detail":
        page = state.get("page")
        if page == "subjects":
            return "screen 4", "page"
        if page == "notes":
            return "screen 9", "page"
        if page == "credit":
            step = state.get("tooltipStep")
            if state.get("tooltip") and step in (6, 7, 8):
                return f"screen {step}", "page"
            return "screen 5", "page"
    return None, "off-catalogue"


def practice_of(state: Dict[str, Any]) -> Optional[str]:
    """NDG of the practice a state shows: the detail header, or the list's single row."""
    if state.get("ndg"):
        return str(state["ndg"])
    rows = state.get("rows") or []
    return str(rows[0]) if len(rows) == 1 else None


def _signature(state: Dict[str, Any]) -> str:
    return json.dumps({k: v for k, v in state.items() if k not in _VOLATILE_KEYS}, sort_keys=True, default=str)


def truth_segments(probes: Sequence[Dict[str, Any]], end: float) -> List[Dict[str, Any]]:
    """Cut the probe timeline into segments of one unchanged state each."""
    segments: List[Dict[str, Any]] = []
    for probe in sorted(probes, key=lambda p: p["t"]):
        state = probe["state"]
        signature = _signature(state)
        if segments and segments[-1]["signature"] == signature:
            continue
        if segments:
            segments[-1]["end"] = probe["t"]
        label, kind = label_for_probe(state)
        segments.append({"start": probe["t"], "end": end, "label": label, "kind": kind,
                         "practice": practice_of(state), "window": state.get("win"), "signature": signature})
    # A DOM change that leaves the same page of the same practice in the same window is one dwell, not two: the
    # operator still looks at that page, and the worker's own visit count says whether pixels changed.
    merged: List[Dict[str, Any]] = []
    for seg in (s for s in segments if s["end"] > s["start"]):
        key = (seg["label"], seg["kind"], seg["practice"], seg["window"])
        if merged and (merged[-1]["label"], merged[-1]["kind"], merged[-1]["practice"], merged[-1]["window"]) == key:
            merged[-1]["end"] = seg["end"]
            continue
        merged.append(seg)
    return merged


def state_at(probes: Sequence[Dict[str, Any]], t: float) -> Dict[str, Any]:
    """The last probed state at or before t (the first one when t precedes them all)."""
    chosen: Dict[str, Any] = probes[0]["state"] if probes else {}
    for probe in probes:
        if probe["t"] > t:
            break
        chosen = probe["state"]
    return chosen


# ============================================================
# Scoring
# ============================================================


def _quantile(values: Sequence[float], q: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]


def score_run(
    segments: Sequence[Dict[str, Any]],
    adoptions: Sequence[Dict[str, Any]],
    frames: Sequence[Dict[str, Any]],
    *,
    fps: float = 3.0,
    min_seconds: float = 2.0,
) -> Dict[str, Any]:
    """Compare what the worker adopted with what the page showed, segment by segment.

    An adoption belongs to the segment in which its frame was grabbed. A page segment is ``right`` when an adoption
    names its page, ``wrong`` when adoptions name only other pages, ``missed`` when it lasted long enough to be
    captured (the stability time plus a confirming frame and a routing slot) without any, else ``short``. A
    transition or an off-catalogue page with an adoption is a ``false-adoption``. An adoption inside a segment
    shorter than the stability time is a fast violation: stability exists to prevent exactly that.
    """
    capturable = min_seconds + 2.0 / fps
    entries: List[Dict[str, Any]] = []
    attributed: Set[int] = set()
    for seg in segments:
        duration = seg["end"] - seg["start"]
        inside = [a for a in adoptions if seg["start"] <= a["t"] < seg["end"]]
        attributed.update(id(a) for a in inside)
        seg_frames = [f for f in frames if seg["start"] <= f["t"] < seg["end"]]
        entry: Dict[str, Any] = {k: v for k, v in seg.items() if k != "signature"}
        routes = [f["routed"] for f in seg_frames if f.get("routed")]
        entry.update(
            # What the classifier saw in this segment, accepted or not: the best prototype and its centred score.
            answers=dict(Counter(str(r.get("best") or r.get("label")) for r in routes)),
            best_score_max=max((r.get("best_score") or r.get("score") or 0.0 for r in routes), default=None),
            duration_s=duration,
            adopted=[a["page"] for a in inside],
            frames=len(seg_frames),
            visits=len({f.get("visit") for f in seg_frames if f.get("kept", True) and f.get("visit") is not None}),
            routed=sum(1 for f in seg_frames if f.get("routed")),
            duplicates=max(0, len(inside) - 1),
            fast_violation=bool(inside) and duration < min_seconds,
            latency_s=None,
        )
        if seg["kind"] != "page" or not seg.get("label"):
            entry["outcome"] = "false-adoption" if inside else "clean"
        else:
            family = PAGE_FAMILY.get(seg["label"])
            matching = [a for a in inside if a["page"] == seg["label"]
                        or (family in PAGE_ONLY_FAMILIES and PAGE_FAMILY.get(a["page"]) == family)]
            if matching:
                entry["outcome"] = "right"
                entry["latency_s"] = matching[0]["t"] - seg["start"]
            elif inside:
                entry["outcome"] = "wrong"
                entry["latency_s"] = inside[0]["t"] - seg["start"]
            else:
                entry["outcome"] = "missed" if duration >= capturable else "short"
            if entry["outcome"] == "missed":
                # Recognition or timing: a label the classifier accepted, which the dwell did not let stabilise,
                # is a timing miss; no accepted label at all is a recognition miss.
                entry["miss_reason"] = ("dwell-ended-before-stability" if any(r.get("label") for r in routes)
                                        else "no-accepted-label")
            entry["family_right"] = any(PAGE_FAMILY.get(a["page"]) == PAGE_FAMILY.get(seg["label"]) for a in inside)
            entry["scores"] = [(a.get("score"), a.get("margin")) for a in inside]
        entries.append(entry)

    outcomes = Counter(e["outcome"] for e in entries)
    latencies = [e["latency_s"] for e in entries if e["latency_s"] is not None]
    per_page: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        if e["kind"] != "page" or not e.get("label"):
            continue
        row = per_page.setdefault(e["label"], {"dwells": 0, "right": 0, "wrong": 0, "missed": 0, "short": 0,
                                               "adopted_as": Counter(), "latencies": []})
        row["dwells"] += 1
        row[e["outcome"]] += 1
        row["adopted_as"].update(e["adopted"])
        if e["latency_s"] is not None:
            row["latencies"].append(e["latency_s"])
    for row in per_page.values():
        row["adopted_as"] = dict(row["adopted_as"])
        row["median_latency_s"] = statistics.median(row["latencies"]) if row["latencies"] else None
        del row["latencies"]
    summary = {
        "right": outcomes["right"], "wrong": outcomes["wrong"], "missed": outcomes["missed"],
        "short": outcomes["short"], "false_adoptions": outcomes["false-adoption"], "clean": outcomes["clean"],
        "duplicates": sum(e["duplicates"] for e in entries),
        "fast_violations": sum(1 for e in entries if e["fast_violation"]),
        "family_right": sum(1 for e in entries if e.get("family_right")),
        "missed_no_label": sum(1 for e in entries if e.get("miss_reason") == "no-accepted-label"),
        "missed_timing": sum(1 for e in entries if e.get("miss_reason") == "dwell-ended-before-stability"),
        "adoptions": len(adoptions),
        "unattributed_adoptions": sum(1 for a in adoptions if id(a) not in attributed),
        "latency_median_s": statistics.median(latencies) if latencies else None,
        "latency_p90_s": _quantile(latencies, 0.9),
        "latency_max_s": max(latencies) if latencies else None,
    }
    return {"segments": entries, "summary": summary, "per_page": dict(sorted(per_page.items()))}


def frame_stats(frames: Sequence[Dict[str, Any]], duration: float, fps: float) -> Dict[str, Any]:
    """What the capture loop did with its frames."""
    kept = [f for f in frames if f.get("kept")]
    expected = int(duration * fps)
    return {
        "grabbed": len(frames),
        "expected_at_fps": expected,
        "lag_dropped": max(0, expected - len(frames)),
        "kept": len(kept),
        "discarded": dict(Counter(f.get("reason") for f in frames if not f.get("kept"))),
        "strategies": dict(Counter(f.get("strategy") for f in frames if f.get("strategy"))),
        "duplicates": sum(1 for f in kept if f.get("dup")),
        "routed": sum(1 for f in kept if f.get("routed")),
        "idle_while_captured": sum(1 for f in kept if f.get("dup") is None and not f.get("routed")),
        "visits": len({f.get("visit") for f in kept if f.get("visit") is not None}),
        "route_ms_median": statistics.median([f["routed"]["ms"] for f in kept if f.get("routed")] or [0]),
    }


# ============================================================
# Truth files and the field comparator
# ============================================================


def _strip_bom(text: str) -> str:
    return text[1:] if text.startswith("﻿") else text


def parse_practice_truth(text: str) -> Dict[str, str]:
    """``/api/truth-practice/<key>.csv`` (Chiave;Campo;Valore) as {schema key: value}."""
    reader = csv.DictReader(io.StringIO(_strip_bom(text)), delimiter=";")
    return {row["Chiave"]: row["Valore"] or "" for row in reader if row.get("Chiave")}


def _label_to_key() -> Dict[str, str]:
    from extraction.fields import CSV_TO_SCHEMA

    return {" ".join(label.split()): key for label, key in CSV_TO_SCHEMA.items()}


def parse_screen_truth(text: str) -> Dict[str, Dict[str, str]]:
    """``/api/truth/<key>.csv`` (one dati.csv per practice) as {screen: {schema key: value}}."""
    labels = _label_to_key()
    screens: Dict[str, Dict[str, str]] = {}
    for row in csv.reader(io.StringIO(_strip_bom(text))):
        if len(row) < 3 or row[0] == "Fotogramma":
            continue
        key = labels.get(" ".join(row[1].split()))
        if key:
            screens.setdefault(row[0], {})[key] = row[2]
    return screens


def compare_record(truth: Dict[str, str], extracted: Dict[str, Any], shown: Iterable[str]) -> Dict[str, Any]:
    """Classify each field of one consolidated practice row against the practice truth.

    Uses the evaluator's classify_field (NDG as identifier, numbers, fuzzy long text). A field the run never put on
    screen and that was not extracted is NOT_SHOWN rather than MISSING: the scenario, not the extractor, left it out.
    """
    from extraction.normalization import classify_field, is_nullish

    shown = set(shown)
    fields: Dict[str, Dict[str, Any]] = {}
    for key in sorted(set(truth) | {k for k, v in extracted.items() if not is_nullish(v)}):
        gt, pred = truth.get(key), extracted.get(key)
        if key not in shown and is_nullish(pred):
            status, reason = "NOT_SHOWN", "the run never showed this field"
        else:
            status, reason = classify_field(gt, pred, key)
        fields[key] = {"truth": gt, "extracted": pred, "status": status, "reason": reason}
    return {"fields": fields, "summary": dict(Counter(f["status"] for f in fields.values()))}


# ============================================================
# Guards: cost, role, configuration, desktop privacy
# ============================================================


def check_extract_request(extract: bool, accept_cost: bool, max_screens: Optional[int]) -> int:
    """How many screens may reach the paid extractor (0 without --extract)."""
    if not extract:
        return 0
    if not accept_cost:
        raise GuardError("--extract calls a paid VLM provider: add --accept-cost to accept the cost")
    cap = MAX_SCREENS_DEFAULT if max_screens is None else int(max_screens)
    if not 1 <= cap <= MAX_SCREENS_CAP:
        raise GuardError(f"--max-screens must be between 1 and {MAX_SCREENS_CAP}, got {cap}")
    return cap


def estimate_cost(model: str, screens: int) -> Dict[str, Any]:
    """Expected and worst-case USD of extracting `screens` screens with `model`."""
    from extraction.config import MAX_CALLS_PER_SCREEN, PRICING_PER_1M
    from extraction.vlm_client import estimate_cost_usd

    if model not in PRICING_PER_1M:
        raise GuardError(f"model {model!r} is not in PRICING_PER_1M: its cost would print as $0.00")
    per_call = estimate_cost_usd(model, TYPICAL_INPUT_TOKENS, TYPICAL_OUTPUT_TOKENS)
    return {
        "model": model, "screens": screens, "per_call_usd": per_call,
        "typical_usd": screens * TYPICAL_CALLS_PER_SCREEN * per_call,
        "upper_usd": screens * MAX_CALLS_PER_SCREEN * per_call,
    }


def check_roles(practices: Sequence[Dict[str, Any]], keys: Iterable[str]) -> None:
    """Only synthetic practices are driven: never an archive or test practice (ADR 0027)."""
    roles = {p.get("key"): p.get("role") for p in practices}
    for key in keys:
        if key not in roles:
            raise GuardError(f"practice {key!r} is not in the emulator catalogue")
        if roles[key] != "sintetica":
            raise GuardError(f"practice {key!r} has role {roles[key]!r}: only 'sintetica' practices may be used")


def require_ml_router(config: Any) -> None:
    """The live test must not route through the paid LLM router, which also sends frames off the machine."""
    mode = (getattr(config, "router_mode", "") or "").lower()
    if mode != "ml":
        raise GuardError(f"router must be 'ml' for the live test, config has {mode!r}")


def _same_rect(a: Sequence[int], b: Sequence[int], tolerance: int = 2) -> bool:
    return all(abs(int(x) - int(y)) <= tolerance for x, y in zip(a, b))


def frame_verdict(
    strategy: Optional[str],
    crop_rect: Optional[Sequence[int]],
    own_rect: Optional[Sequence[int]],
    exposed: bool,
    *,
    live: bool,
) -> Tuple[bool, str]:
    """Whether a normalized frame may reach routing, extraction and the disk.

    On the real desktop only a crop by the emulator window's own rectangle, with that window on top, shows nothing
    but the emulator: an unchanged frame is the whole monitor, a content-rect crop is a guess over the user's
    desktop, another window's rectangle is another application, and a covered window shows what covers it.
    """
    if strategy == "unchanged" or strategy is None:
        return False, "unchanged"
    if not live:
        return True, ""
    if strategy != "window-rect":
        return False, "content-rect-on-desktop"
    if crop_rect is None or own_rect is None or not _same_rect(crop_rect, own_rect):
        return False, "foreign-window"
    if not exposed:
        return False, "not-exposed"
    return True, ""


class PrivacyGuard:
    """Counts discarded frames; the third unchanged frame, or the third of any other privacy reason, aborts."""

    def __init__(self, limit: int = 3) -> None:
        self.limit = limit
        self.discarded: Counter = Counter()

    def observe(self, keep: bool, reason: str) -> None:
        if keep:
            return
        self.discarded[reason] += 1
        others = sum(n for r, n in self.discarded.items() if r not in ("unchanged", "no-image"))
        if self.discarded["unchanged"] >= self.limit or others >= self.limit:
            raise PrivacyAbort(f"frames could not be confined to the emulator window: {dict(self.discarded)}")


# ============================================================
# Extraction: oracle, cost cap, cost summary
# ============================================================


class CappedPipeline:
    """Lets at most `cap` screens reach the wrapped pipeline; later screens complete without fields or calls."""

    def __init__(self, pipeline: Any, cap: int) -> None:
        self._pipeline = pipeline
        self.cap = int(cap)
        self.calls = 0
        self._lock = threading.Lock()

    def extract_from_image(self, img: Any, screen_id: str, **kwargs: Any) -> Dict[str, Any]:
        with self._lock:
            allowed = self.calls < self.cap
            if allowed:
                self.calls += 1
        if not allowed:
            return {"screen_id": screen_id, "fields": {}, "_status": "SKIPPED_COST_CAP"}
        return self._pipeline.extract_from_image(img, screen_id, **kwargs)


class OraclePipeline:
    """A perfect reader: the emulator's truth for the state on screen when the frame was adopted."""

    def __init__(self, probes: Callable[[], Sequence[Dict[str, Any]]],
                 truth_by_ndg: Dict[str, Dict[str, Dict[str, str]]], acquired_at: Callable[[], Optional[float]]) -> None:
        self._probes = probes
        self._truth = truth_by_ndg
        self._acquired_at = acquired_at

    def extract_from_image(self, img: Any, screen_id: str, **_kwargs: Any) -> Dict[str, Any]:
        from extraction.normalization import normalize_ndg

        t = self._acquired_at()
        state = state_at(self._probes(), t if t is not None else time.time())
        label, _kind = label_for_probe(state)
        ndg = practice_of(state)
        values = self._truth.get(normalize_ndg(ndg) or "", {}).get(label or "", {})
        if PAGE_FAMILY.get(label or "") in PAGE_ONLY_FAMILIES:
            values = {k: v for k, v in values.items() if k == "ndg"}  # the pinned NDG column: what groups the row
        return {
            "screen_id": screen_id,
            "fields": {k: {"value": v, "confidence": 1.0} for k, v in values.items() if v != ""},
            "_status": "OK",
            "_oracle": {"label": label, "ndg": ndg},
        }


def summarize_costs(results: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Cost, calls and tokens of a run, from the `_meta_agg` every pipeline result carries."""
    total = {"cost_usd": 0.0, "calls": 0, "tokens": 0, "screens": 0}
    for result in results:
        meta = result.get("_meta_agg") or {}
        if not meta:
            continue
        total["screens"] += 1
        total["cost_usd"] += float(meta.get("estimated_cost_usd", 0.0) or 0.0)
        total["calls"] += int(meta.get("calls", 0) or 0)
        total["tokens"] += int(meta.get("total_tokens", 0) or 0)
    return total


def wait_for_extractions(client: Any, timeout: float = 30.0) -> bool:
    """Wait until every accepted frame has a published result."""
    end = time.time() + timeout
    while time.time() < end:
        if client.pending_extractions() == 0 and client.frames_in_progress() == 0:
            return True
        time.sleep(0.02)
    return False


# ============================================================
# The worker, instrumented
# ============================================================


class Recorder:
    """What the capture loop did, frame by frame (thread-safe; written from the capture thread)."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self.lock = threading.Lock()
        self.frames: List[Dict[str, Any]] = []
        self.adoptions: List[Dict[str, Any]] = []
        self.ticks: List[Tuple[float, str]] = []
        self.current: Dict[str, Any] = {}
        self.last_acquired_t: Optional[float] = None
        self.last_route: Optional[Dict[str, Any]] = None
        self.abort: Optional[str] = None
        self.started = threading.Event()

    def begin(self) -> Dict[str, Any]:
        frame = {"t": self.clock(), "index": len(self.frames)}
        with self.lock:
            self.frames.append(frame)
            self.current = frame
        return frame

    def tick(self, message: str) -> None:
        with self.lock:
            self.ticks.append((self.clock(), message))
        if message.startswith("[Worker] Avviato"):
            self.started.set()


def make_harness_worker(
    config: Any,
    job_id_getter: Callable[[], Optional[str]],
    api_client: Any,
    *,
    recorder: Recorder,
    rect_provider: Callable[[str], Optional[Rect]],
    exposure: Callable[[], bool],
    guard: PrivacyGuard,
    live: bool,
    own_rect: Callable[[], Optional[Rect]] = lambda: None,
    keep_frame: Optional[Callable[[Dict[str, Any], Any], None]] = None,
    scrub: Optional[Callable[[Any], Any]] = None,
) -> Any:
    """The production BPERCaptureWorker with a recorder around its steps and the privacy guard after _grab_raw.

    The guard sits between the grab and everything downstream, so a frame it refuses never reaches dedup,
    routing, ingest_frame or the disk. Record the rectangle actually used for framing. A replay gets
    its desktop geometry and window from the recording without sampling the host's foreground window.
    """
    from PyQt6 import QtCore
    from workers.capture import bper_capture_worker as bcw

    class HarnessWorker(bcw.BPERCaptureWorker):
        def _init_router(self) -> None:
            super()._init_router()
            classifier = self.classifier
            if classifier is not None and hasattr(classifier, "classify_detailed"):
                embed = classifier._compute_embedding

                def compute_embedding(image: Any) -> Any:
                    emb = embed(image)
                    recorder.current["best"] = _best_prototype(classifier, emb)
                    return emb

                def classify(image: Any) -> Tuple[Optional[str], float]:
                    result = classifier.classify_detailed(image)
                    recorder.current.update(margin=result.margin, runner_up=result.runner_up,
                                            rejected_by=result.rejected_by, raw_score=result.score)
                    return result.label, result.score

                # One inference, plus what the plain API drops: margin, runner-up, and the best prototype even
                # when it stays under the acceptance threshold.
                classifier._compute_embedding = compute_embedding
                classifier.classify = classify

        def _capture_window(self, monitor: dict[str, int]) -> bcw.CaptureWindow | None:
            return super()._capture_window(monitor) if live else None

        def _window_rect(self, window: bcw.CaptureWindow | None) -> Optional[Rect]:
            rect = super()._window_rect(window) if window else rect_provider(self.config.window_title_contains)
            recorder.current["rect"] = list(rect) if rect else None
            return rect

        def _grab_raw(self) -> Any:
            frame = recorder.begin()
            img = super()._grab_raw()
            if img is None:
                frame.update(kept=False, reason="no-image")
                return None
            keep, reason = frame_verdict(frame.get("strategy"), frame.get("rect"), own_rect(),
                                         exposure() if live else True, live=live)
            frame.update(kept=keep, reason=reason, size=list(img.size))
            try:
                guard.observe(keep, reason)
            except PrivacyAbort as exc:
                recorder.abort = str(exc)
                self.stop()
                return None
            if keep and keep_frame is not None:
                keep_frame(frame, img)
            if keep and scrub is not None:
                img = scrub(img)  # --extract: no desktop pixel may reach the provider
            return img if keep else None

        def _announce_framing(self, strategy: str, full_size: Any, framed_size: Any) -> None:
            recorder.current["strategy"] = strategy
            super()._announce_framing(strategy, full_size, framed_size)

        def _observe_frame(self, raw: Any) -> None:
            super()._observe_frame(raw)
            recorder.current["visit"] = self._visit_sequence

        def _is_duplicate_frame(self, img: Any) -> bool:
            dup = super()._is_duplicate_frame(img)
            recorder.current["dup"] = dup
            return dup

        def _detect_page(self, img: Any) -> Tuple[Optional[str], float, dict]:
            t0 = time.perf_counter()
            label, score, fields = super()._detect_page(img)
            current = recorder.current
            best = current.get("best") or (None, None)
            routed = {"label": label, "score": current.get("raw_score", score), "margin": current.get("margin"),
                      "runner_up": current.get("runner_up"), "rejected_by": current.get("rejected_by"),
                      "best": best[0], "best_score": best[1], "ms": round((time.perf_counter() - t0) * 1000)}
            recorder.current["routed"] = routed
            recorder.last_route = routed
            return label, score, fields

        def _acquire(self, job_id: str, img: Any, page: Any, score: float, fields: dict) -> None:
            frame = recorder.current
            # A confirming duplicate frame is not routed again: the answer it confirms is the last route.
            route = frame.get("routed") or recorder.last_route or {}
            recorder.last_acquired_t = frame.get("t")
            with recorder.lock:
                recorder.adoptions.append({
                    "t": frame.get("t"), "t_acquire": recorder.clock(), "frame": frame.get("index"),
                    "page": page.template or page.name, "name": page.name, "score": score,
                    "margin": route.get("margin"), "runner_up": route.get("runner_up"),
                    "by": "confirm" if frame.get("dup") else "route",
                })
            frame["acquired"] = page.name
            super()._acquire(job_id, img, page, score, fields)

    worker = HarnessWorker(config, job_id_getter, api_client)
    worker.tick.connect(recorder.tick, QtCore.Qt.ConnectionType.DirectConnection)
    return worker


def _best_prototype(classifier: Any, emb: Any) -> Tuple[Optional[str], Optional[float]]:
    """The winning prototype and its centred score, as classify_detailed computes them (diagnostics only)."""
    try:
        torch = classifier._torch
        centered = classifier._proto_matrix_centered
        if emb is None or centered is None:
            return None, None
        query = torch.nn.functional.normalize(emb - classifier._proto_mean, p=2, dim=0)
        sims = torch.mv(centered, query)
        index = int(torch.argmax(sims).item())
        return classifier._proto_labels[index], round(float(sims[index].item()), 4)
    except Exception:  # noqa: BLE001 - a diagnostic must not stop the capture
        return None, None


def harness_config(run_dir: Path, *, fps: int = 3) -> Any:
    """A copy of the agent's config.ini under the run folder: emulator title, fps 3, router ml, no border."""
    import configparser

    from config import AgentConfig

    parser = configparser.ConfigParser()
    parser.read(EDGE_AGENT / "config.ini", encoding="utf-8")
    parser["agent"].update({
        "fps": str(fps), "window_title_contains": WINDOW_TITLE, "router": "ml", "monitor_index": "1",
        "show_capture_border": "false",
    })
    if parser.has_section("llm"):
        parser["llm"]["api_key"] = ""  # the ml router needs none, and a key must never be copied around
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "config.ini"
    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle)
    config = AgentConfig(path)
    require_ml_router(config)
    return config


class _PatchedClock:
    """The worker module's `time`, swapped for a virtual clock during a deterministic replay."""

    def __init__(self, module: Any, clock: Callable[[], float]) -> None:
        self.module, self.clock, self.saved = module, clock, None

    def __enter__(self) -> "_PatchedClock":
        import types

        self.saved = self.module.time
        self.module.time = types.SimpleNamespace(time=self.clock, sleep=time.sleep, perf_counter=time.perf_counter)
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.module.time = self.saved


# ============================================================
# Replay
# ============================================================


class _Shot:
    def __init__(self, img: Any) -> None:
        self.size = img.size
        self.rgb = img.tobytes()


class Replay:
    """A recording: window images with their times and places, the probes, and the canvas they sit on."""

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        data = json.loads((self.folder / "recording.json").read_text(encoding="utf-8"))
        self.data = data
        self.canvas = tuple(data.get("canvas", [1920, 1080]))
        self.desktop = tuple(data.get("desktop", [32, 34, 38]))
        self.frames = sorted(data["frames"], key=lambda f: f["t"])
        self.probes = sorted(data.get("probes", []), key=lambda p: p["t"])
        self.start = self.frames[0]["t"]
        self.end = float(data.get("end", self.frames[-1]["t"] + 1.0))
        self.chrome_height = int(data.get("chrome_height", CHROME_UI_HEIGHT))
        self.border = int(data.get("invisible_border", 0))
        self.frame_border = int(data.get("frame_border", 0))
        # window-rect: the OS answers with the window rectangle; content-rect: no answer, the uniform desktop frames it.
        self.framing = data.get("framing", "window-rect")
        self.current = 0
        self._cache: Dict[int, Any] = {}
        self.background: Any = None

    def use_background(self, image: Path) -> None:
        """Tile an image over the canvas: a busy desktop behind the window instead of a uniform colour."""
        from PIL import Image

        tile = Image.open(image).convert("RGB")
        canvas = Image.new("RGB", self.canvas, self.desktop)
        for x in range(0, self.canvas[0], tile.width):
            for y in range(0, self.canvas[1], tile.height):
                canvas.paste(tile, (x, y))
        self.background = canvas
        self._cache = {}

    def index_at(self, t: float) -> int:
        index = 0
        for i, frame in enumerate(self.frames):
            if frame["t"] > t:
                break
            index = i
        return index

    def window_rect(self, index: int) -> Rect:
        """What GetWindowRect answers: a frame's `window` is that rectangle, invisible borders included."""
        x, y, w, h = self.frames[index]["window"]
        return (x, y, x + w, y + h)

    def _window_image(self, frame: Dict[str, Any]) -> Any:
        """The visible window: a neutral tab strip and toolbar, a 1 px frame, the page render below the bars."""
        from PIL import Image, ImageDraw

        image = Image.open(self.folder / frame["image"]).convert("RGB")
        if frame.get("kind", "viewport") == "window":
            return image
        _x, _y, w, h = frame["window"]
        w, h = w - 2 * self.border, h - self.border
        band, edge = self.chrome_height, self.frame_border
        window = Image.new("RGB", (w, h), (48, 52, 56))
        draw = ImageDraw.Draw(window)
        draw.rectangle([0, 0, w, band // 2], fill=(211, 227, 253))
        draw.rectangle([0, band // 2, w, band - 2], fill=(255, 255, 255))
        draw.rounded_rectangle([130, band // 2 + 5, max(140, w - 140), band - 8], radius=14, fill=(238, 242, 250))
        draw.line([0, band - 1, w, band - 1], fill=(225, 227, 225))
        window.paste(image.crop((0, 0, min(image.width, w - 2 * edge), min(image.height, h - band - edge))),
                     (edge, band))
        return window

    def desktop_at(self, t: float) -> Any:
        from PIL import Image

        index = self.index_at(t)
        self.current = index
        if index not in self._cache:
            frame = self.frames[index]
            canvas = self.background.copy() if self.background is not None else Image.new(
                "RGB", self.canvas, self.desktop)
            x, y = frame["window"][:2]
            offset = self.border if frame.get("kind", "viewport") == "viewport" else 0
            canvas.paste(self._window_image(frame), (x + offset, y))
            self._cache = {index: canvas}  # one composed desktop at a time: recordings can be long
        return self._cache[index]


class ReplayMss:
    """Stands in for the mss context: the monitor is the replay canvas at the clock's time."""

    def __init__(self, replay: Replay, clock: Callable[[], float]) -> None:
        self.replay = replay
        self.clock = clock
        mon = {"left": 0, "top": 0, "width": replay.canvas[0], "height": replay.canvas[1]}
        self.monitors = [mon, mon]

    def grab(self, _mon: Dict[str, int]) -> _Shot:
        return _Shot(self.replay.desktop_at(self.clock()))

    def close(self) -> None:
        pass


def _consolidation(results: List[Dict[str, Any]], segments: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    from extraction.normalization import normalize_ndg
    from practice_consolidation import consolidate, has_content

    rows = [r for r in consolidate(results) if has_content(r)]
    shown = sorted({normalize_ndg(s["practice"]) for s in segments if s["kind"] == "page" and s.get("practice")}
                   - {None})
    return {
        "rows": len(rows), "practices_shown": len(shown),
        "row_ndgs": [r.ndg for r in rows], "shown_ndgs": shown,
        "note": "oracle extraction: counts grouping given a perfect NDG, not extraction quality",
        "records": rows,
    }


def expected_fields(segments: Sequence[Dict[str, Any]], screens: Dict[str, Dict[str, str]], ndg: Optional[str]) -> Set[str]:
    """Fields a practice's dwells put on screen, by the per-screen truth; the list sets no expectation."""
    from extraction.normalization import normalize_ndg

    shown: Set[str] = set()
    for seg in segments:
        if (seg["kind"] == "page" and PAGE_FAMILY.get(seg["label"]) not in PAGE_ONLY_FAMILIES
                and normalize_ndg(seg.get("practice")) == normalize_ndg(ndg)):
            shown.update(screens.get(seg["label"], {}))
    return shown


def _comparisons(records: Sequence[Any], truth: Dict[str, Dict[str, Any]],
                 segments: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Each consolidated row against /api/truth-practice of the practice with its NDG."""
    from extraction.normalization import normalize_ndg

    out: Dict[str, Any] = {}
    for record in records:
        info = truth.get(record.ndg or "")
        if info is None:
            out[str(record.ndg)] = {"error": "row of a practice the scenario did not declare"}
            continue
        shown = expected_fields(segments, info["screens"], record.ndg)
        extracted = {k: v.get("value") for k, v in record.fields.items()}
        out[info["key"]] = compare_record(info["record"], extracted, shown)
    return out


def run_virtual_replay(folder: Path, **kwargs: Any) -> Dict[str, Any]:
    """Play a recording through the real worker on a virtual clock: deterministic, as fast as the CPU allows.

    Every frame of the recording's span is grabbed exactly at k/fps and extraction finishes before the next frame,
    so the result does not depend on the machine's speed; run_replay(realtime=True) keeps the real lag.
    """
    return run_replay(folder, realtime=False, **kwargs)


def run_replay(
    folder: Path,
    *,
    truth: Optional[Dict[str, Dict[str, Any]]] = None,
    fps: int = 3,
    pipeline: Any = None,
    run_dir: Optional[Path] = None,
    realtime: bool = False,
    desktop_image: Optional[Path] = None,
) -> Dict[str, Any]:
    """A recording through the real worker, the real classifier and the real registry.

    realtime: the worker runs in its own QThread at its own pace while the recording plays at wall-clock speed, so
    routing time, dropped frames and late captures show as they would live. desktop_image: the canvas behind the
    window is that image tiled instead of a uniform colour, to see what the invisible borders let in.
    """
    import tempfile

    from PyQt6.QtCore import QCoreApplication
    from local_extraction_client import LocalExtractionClient
    from workers.capture import bper_capture_worker as bcw

    replay = Replay(Path(folder))
    if desktop_image is not None:
        replay.use_background(Path(desktop_image))
    truth = truth or {}
    QCoreApplication.instance() or QCoreApplication([])
    state = {"t": replay.start, "t0": None}

    def clock() -> float:
        if realtime and state["t0"] is not None:
            return replay.start + (time.time() - state["t0"])
        return state["t"]

    recorder = Recorder(clock=clock)
    probes = replay.probes
    pipeline = pipeline or OraclePipeline(lambda: probes, {k: v["screens"] for k, v in truth.items()},
                                          lambda: recorder.last_acquired_t)
    client = LocalExtractionClient(pipeline=pipeline)
    job = client.start_job()
    guard = PrivacyGuard()
    owned_tmp = None
    if run_dir is None:
        owned_tmp = tempfile.TemporaryDirectory()
        run_dir = Path(owned_tmp.name)
    try:
        config = harness_config(Path(run_dir), fps=fps)
        worker = make_harness_worker(
            config, lambda: job, client, recorder=recorder,
            rect_provider=(lambda _title: None) if replay.framing == "content-rect"
            else (lambda _title: replay.window_rect(replay.current)),
            own_rect=lambda: replay.window_rect(replay.current), exposure=lambda: True, guard=guard, live=False)
        with _PatchedClock(bcw, clock):
            worker._init_router()
            worker._load_registry()
            worker._router_ready = True
            worker._mss_ctx = ReplayMss(replay, clock)
            if realtime:
                state["t0"] = time.time()
                worker.start()
                while clock() < replay.end:
                    time.sleep(0.05)
                worker.stop()
                worker.wait(30_000)
            else:
                for k in range(int((replay.end - replay.start) * fps)):
                    state["t"] = replay.start + k / fps
                    worker._capture_once()
                    wait_for_extractions(client)
        wait_for_extractions(client)
        results = client.get_results(job)
    finally:
        client.shutdown()
        if owned_tmp is not None:
            owned_tmp.cleanup()
    return build_report(
        mode="replay-" + ("realtime" if realtime else "virtual") + ("+busy-desktop" if desktop_image else ""),
        recording=str(folder), frames=recorder.frames, adoptions=recorder.adoptions, probes=probes,
        end=replay.end, start=replay.start, fps=fps, results=results, truth=truth, guard=guard,
        ticks=recorder.ticks)


def build_report(*, mode: str, frames: List[Dict[str, Any]], adoptions: List[Dict[str, Any]],
                 probes: Sequence[Dict[str, Any]], start: float, end: float, fps: float,
                 results: List[Dict[str, Any]], truth: Dict[str, Dict[str, Any]], guard: PrivacyGuard,
                 ticks: Sequence[Tuple[float, str]], **extra: Any) -> Dict[str, Any]:
    segments = truth_segments(probes, end)
    score = score_run(segments, adoptions, frames, fps=fps)
    consolidation = _consolidation(results, segments)
    records = consolidation.pop("records")
    report = {
        "mode": mode, **extra, "start": start, "end": end, "duration_s": end - start, "fps": fps,
        "score": score, "frames": frame_stats(frames, end - start, fps),
        "adoptions": adoptions, "consolidation": consolidation,
        "comparison": _comparisons(records, truth, segments) if truth else {},
        "cost": summarize_costs(results),
        "statuses": dict(Counter(r.get("_status") for r in results)),
        "privacy_discards": dict(guard.discarded),
        "ticks": [m for _t, m in ticks][:400],
        "frame_log": frames,
        "probes": list(probes),
    }
    return report


def rescore(report: Dict[str, Any]) -> Dict[str, Any]:
    """Score a finished run again from what it recorded (probes, frames, adoptions), with today's rules."""
    if report.get("probes") and "end" in report:
        segments = truth_segments(report["probes"], report["end"])
    else:  # a run recorded before probes were kept: its segments, merged as truth_segments merges them
        segments = []
        for seg in report["score"]["segments"]:
            key = (seg["label"], seg["kind"], seg.get("practice"), seg.get("window"))
            if segments and (segments[-1]["label"], segments[-1]["kind"], segments[-1].get("practice"),
                             segments[-1].get("window")) == key:
                segments[-1]["end"] = seg["end"]
            else:
                segments.append({k: seg[k] for k in ("start", "end", "label", "kind", "practice", "window")})
    report = dict(report)
    report["score"] = score_run(segments, report["adoptions"], report["frame_log"], fps=report["fps"])
    return report


# ============================================================
# Report
# ============================================================


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def markdown_report(report: Dict[str, Any]) -> str:
    s = report["score"]["summary"]
    f = report["frames"]
    c = report["consolidation"]
    lines = [
        f"# Live harness: {report.get('scenario', report.get('recording', ''))}",
        "",
        f"- Mode: {report['mode']}; geometry: {report.get('geometry', '-')}; duration {report['duration_s']:.1f} s at "
        f"{report['fps']} fps",
        f"- Adoptions: {s['adoptions']} - right {s['right']}, wrong {s['wrong']}, missed {s['missed']} (no accepted "
        f"label {s.get('missed_no_label', '-')}, accepted but the dwell ended first {s.get('missed_timing', '-')}), "
        f"short dwells {s['short']}, false adoptions {s['false_adoptions']}, duplicates {s['duplicates']}, fast "
        f"violations {s['fast_violations']}, right page family {s['family_right']}",
        f"- Latency page settled -> capture: median {_fmt(s['latency_median_s'])} s, p90 {_fmt(s['latency_p90_s'])} s, "
        f"max {_fmt(s['latency_max_s'])} s",
        f"- Frames: grabbed {f['grabbed']} (expected {f['expected_at_fps']}, lag-dropped {f['lag_dropped']}), kept "
        f"{f['kept']}, discarded {f['discarded']}, strategies {f['strategies']}, duplicates {f['duplicates']}, routed "
        f"{f['routed']} (median {f['route_ms_median']} ms), visits {f['visits']}",
        f"- Consolidation: {c['rows']} row(s) for {c['practices_shown']} practice(s) shown ({c['note']})",
    ]
    if report.get("cost", {}).get("screens"):
        cost = report["cost"]
        lines.append(f"- Extraction cost: ${cost['cost_usd']:.4f} over {cost['screens']} screens, "
                     f"{cost['calls']} calls, {cost['tokens']} tokens")
    for key, value in report.get("notes", {}).items():
        lines.append(f"- {key}: {value}")
    lines += ["", "| Page | Dwells | Right | Wrong | Missed | Short | Adopted as | Median latency (s) |",
              "|---|---|---|---|---|---|---|---|"]
    for label, row in report["score"]["per_page"].items():
        lines.append(f"| {label} | {row['dwells']} | {row['right']} | {row['wrong']} | {row['missed']} | {row['short']} "
                     f"| {row['adopted_as'] or '-'} | {_fmt(row['median_latency_s'])} |")
    lines += ["", "| Start | Dur (s) | Window | Truth | Kind | Outcome | Adopted | Visits | Routed | Best prototype "
              "(count) | Best score |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    t0 = report.get("t0") or 0.0
    for e in report["score"]["segments"]:
        answers = ", ".join(f"{k} x{v}" for k, v in e.get("answers", {}).items()) or "-"
        lines.append(f"| {e['start'] - t0:.1f} | {e['duration_s']:.1f} | {e.get('window') or '-'} | "
                     f"{e['label'] or '-'} | {e['kind']} | {e['outcome']} | {', '.join(e['adopted']) or '-'} | "
                     f"{e['visits']} | {e['routed']} | {answers} | {_fmt(e.get('best_score_max'), 3)} |")
    for key, comparison in report.get("comparison", {}).items():
        lines.append(f"\nFields of {key}: {comparison.get('summary', comparison)}")
    return "\n".join(lines) + "\n"


def write_report(report: Dict[str, Any], run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str),
                                         encoding="utf-8")
    path = run_dir / "report.md"
    path.write_text(markdown_report(report), encoding="utf-8")
    return path


# ============================================================
# Emulator server and driver processes
# ============================================================


def _child_env() -> Dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


class EmulatorServer:
    """Our own emulator server on our own port; only this process is ever stopped."""

    def __init__(self, db: Path, profiles: Sequence[Path], port: int = 0) -> None:
        if port == 8765:
            raise GuardError("port 8765 belongs to the user's simulator")
        args = [sys.executable, str(SERVER), "--port", str(port), "--db", str(db)]
        for profile in profiles:
            args += ["--profiles", str(profile)]
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                     encoding="utf-8", env=_child_env(), cwd=str(REPO))
        line = self.proc.stdout.readline() if self.proc.stdout else ""
        if "http://" not in line:
            self.stop()
            raise GuardError(f"the emulator server did not start: {line.strip()!r}")
        self.url = line[line.index("http://"):].split()[0]

    def get(self, path: str) -> bytes:
        import urllib.request

        with urllib.request.urlopen(self.url.rstrip("/") + path, timeout=30) as response:
            return response.read()

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class RemoteServer:
    """An emulator server someone else runs (--url): only read from, never stopped."""

    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/") + "/"

    get = EmulatorServer.get

    def stop(self) -> None:
        pass


class DriverProcess:
    """live_driver.cjs as a child process: JSON events on stdout, 'go' and 'quit' on stdin."""

    def __init__(self, args: Sequence[str], log: Path) -> None:
        node = shutil.which("node")
        if node is None:
            raise GuardError("Node.js is needed for the driver")
        self._log = log.open("w", encoding="utf-8")
        self.proc = subprocess.Popen([node, str(DRIVER), *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self._log, text=True, encoding="utf-8", env=_child_env())
        self.events: List[Dict[str, Any]] = []
        self.queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            self.events.append(event)
            self.queue.put(event)
        self.queue.put({"event": "exit", "t": time.time()})

    def wait_for(self, name: str, timeout: float) -> Dict[str, Any]:
        end = time.time() + timeout
        while time.time() < end:
            try:
                event = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if event.get("event") == name:
                return event
            if event.get("event") == "exit" or (event.get("event") == "error" and event.get("fatal")):
                raise GuardError(f"driver stopped before '{name}': {event}")
        raise GuardError(f"driver sent no '{name}' within {timeout:.0f} s")

    def send(self, line: str) -> None:
        try:
            assert self.proc.stdin is not None
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError):
            pass

    def close(self, timeout: float = 20.0) -> None:
        self.send("quit")
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self._log.close()

    def probes(self) -> List[Dict[str, Any]]:
        return [{"t": e["t"], "state": e["state"]} for e in list(self.events) if e.get("event") == "probe"]


def load_truth(server: EmulatorServer, keys: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """{normalized NDG: {key, record, screens}} for the scenario's practices."""
    from extraction.normalization import normalize_ndg

    catalogue = json.loads(server.get("/api/practices.json"))["practices"]
    by_key = {p["key"]: p for p in catalogue}
    truth: Dict[str, Dict[str, Any]] = {}
    for key in keys:
        practice = by_key[key]
        truth[normalize_ndg(practice["ndg"]) or key] = {
            "key": key,
            "record": parse_practice_truth(server.get(f"/api/truth-practice/{key}.csv").decode("utf-8")),
            "screens": parse_screen_truth(server.get(f"/api/truth/{key}.csv").decode("utf-8")),
        }
    return truth


def _scenario_profiles(scenario: Dict[str, Any], extra: Sequence[str]) -> List[Path]:
    return [(REPO / p).resolve() for p in [*scenario["profiles"], *extra]]


def _driver_args(scenario: Dict[str, Any], url: str, out: Path, *, headless: bool, record: bool) -> List[str]:
    """The driver reads the validated scenario, geometry expanded, never the file the user wrote."""
    resolved = out / "scenario.json"
    resolved.write_text(json.dumps(scenario, ensure_ascii=False, indent=1), encoding="utf-8")
    args = ["--url", url, "--scenario", str(resolved), "--out", str(out), "--chrome-ui", str(CHROME_UI_HEIGHT),
            "--border", str(INVISIBLE_BORDER), "--edge", str(FRAME_BORDER)]
    if headless:
        args.append("--headless")
    if record:
        args.append("--record")
    return args


def _clean_temp() -> None:
    """Chrome leaves profiles and *.tmp in TEMP; empty it when it is our own scratch folder."""
    temp = Path(os.environ.get("TEMP", ""))
    if temp.name == "tmp-live" and temp.is_dir():
        for child in temp.iterdir():
            try:
                shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)
            except OSError:
                pass  # still held by a running process: the next run removes it


# ============================================================
# record: headless Chrome plays the scenario, the window is saved at each change
# ============================================================


def with_geometry(scenario: Dict[str, Any], geometry: Optional[str]) -> Dict[str, Any]:
    """The same scenario at another named geometry (the --geometry option)."""
    if geometry:
        scenario = {**scenario, "geometry": _geometry(geometry)}
    return scenario


def record(scenario_path: Path, out: Path, *, db: Path, port: int = 0, profiles: Sequence[str] = (),
           geometry: Optional[str] = None) -> Path:
    scenario = with_geometry(load_scenario(scenario_path), geometry)
    out.mkdir(parents=True, exist_ok=False)
    server = EmulatorServer(db, _scenario_profiles(scenario, profiles), port)
    try:
        check_roles(json.loads(server.get("/api/practices.json"))["practices"], scenario["practices"])
        truth = load_truth(server, scenario["practices"])
        driver = DriverProcess(_driver_args(scenario, server.url, out, headless=True, record=True),
                               out / "driver.log")
        try:
            done = driver.wait_for("done", timeout=estimate_seconds(scenario) * 2 + 90)
        finally:
            driver.close()
    finally:
        server.stop()
        _clean_temp()
    # The time the screenshot was asked for, not when it was saved: its pixels are those of that moment.
    frames = [{"t": e.get("shot_t", e["t"]), "image": e["file"], "window": e["window"], "kind": "viewport"}
              for e in driver.events if e.get("event") == "frame"]
    ready = next((e for e in driver.events if e.get("event") == "ready"), {})
    recording = {
        "scenario": scenario["name"], "geometry": scenario["geometry"], "canvas": [1920, 1080],
        "desktop": [32, 34, 38], "chrome_height": CHROME_UI_HEIGHT, "invisible_border": INVISIBLE_BORDER,
        "frame_border": FRAME_BORDER, "ready": ready,
        "frames": frames, "probes": driver.probes(), "end": done["t"],
        "actions": [e for e in driver.events if e.get("event") in ("action", "settled", "skip", "error")],
        "truth": {k: {"key": v["key"], "record": v["record"], "screens": v["screens"]} for k, v in truth.items()},
    }
    (out / "recording.json").write_text(json.dumps(recording, ensure_ascii=False), encoding="utf-8")
    if not done.get("ok", False):
        print(f"driver reported a problem: {done}", file=sys.stderr)
    return out


# ============================================================
# live: the real monitor, a headed Chrome, the real worker
# ============================================================


def _win32() -> Any:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
    return ctypes, wintypes, user32


def own_windows(pid: int, needle: str) -> List[Tuple[int, Rect]]:
    """Visible top-level windows of our own Chrome process whose title contains the needle."""
    ctypes, wintypes, user32 = _win32()
    found: List[Tuple[int, Rect]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd: int, _lparam: int) -> bool:
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        length = user32.GetWindowTextLengthW(hwnd)
        if owner.value == pid and user32.IsWindowVisible(hwnd) and length > 0:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if needle.lower() in buffer.value.lower():
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                found.append((int(hwnd), (rect.left, rect.top, rect.right, rect.bottom)))
        return True

    user32.EnumWindows(visit, 0)
    return found


def matching_window_pids(needle: str) -> List[int]:
    """Owners of the visible windows whose title contains the needle; the titles themselves are not kept."""
    ctypes, wintypes, user32 = _win32()
    pids: List[int] = []
    needle = needle.lower()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd: int, _lparam: int) -> bool:
        length = user32.GetWindowTextLengthW(hwnd)
        if user32.IsWindowVisible(hwnd) and length > 0:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if needle in buffer.value.lower():
                owner = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
                pids.append(int(owner.value))
        return True

    user32.EnumWindows(visit, 0)
    return pids


def window_rect(hwnd: int) -> Optional[Rect]:
    ctypes, wintypes, user32 = _win32()
    rect = wintypes.RECT()
    if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def visible_frame_bounds(hwnd: int) -> Optional[Rect]:
    """DWM's extended frame bounds: the window as drawn, without the invisible resize borders."""
    ctypes, wintypes, _user32 = _win32()
    rect = wintypes.RECT()
    result = ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(rect),
                                                         ctypes.sizeof(rect))
    return None if result else (rect.left, rect.top, rect.right, rect.bottom)


def set_topmost(hwnd: int, on: bool) -> None:
    _ctypes, wintypes, user32 = _win32()
    insert_after = wintypes.HWND(-1 if on else -2)  # HWND_TOPMOST / HWND_NOTOPMOST
    user32.SetWindowPos(wintypes.HWND(hwnd), insert_after, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)


def covering_owners(pid: int, rect: Rect, grid: int = 7) -> List[int]:
    """Processes, other than our Chrome, whose windows show at sampled points of the rectangle."""
    ctypes, wintypes, user32 = _win32()
    left, top, right, bottom = rect
    owners: List[int] = []
    for i in range(grid):
        for j in range(grid):
            x = int(left + 12 + (right - left - 24) * i / (grid - 1))
            y = int(top + 12 + (bottom - top - 24) * j / (grid - 1))
            hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
            root = user32.GetAncestor(hwnd, 2) if hwnd else None  # GA_ROOT
            owner = wintypes.DWORD()
            if root:
                user32.GetWindowThreadProcessId(root, ctypes.byref(owner))
            if owner.value != pid:
                owners.append(int(owner.value))
    return owners


def window_exposed(pid: int, rect: Rect, grid: int = 7) -> bool:
    """True when every sampled point of the rectangle shows a window of our Chrome process."""
    return not covering_owners(pid, rect, grid)


def process_names(pids: Iterable[int]) -> Dict[str, int]:
    """Executable names of processes (no window titles, no pixels), for a refusal message."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    names: Counter = Counter()
    for pid in pids:
        handle = kernel32.OpenProcess(0x1000, False, pid)
        name = "?"
        if handle:
            buffer, size = ctypes.create_unicode_buffer(260), wintypes.DWORD(260)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                name = Path(buffer.value).name
            kernel32.CloseHandle(handle)
        names[name] += 1
    return dict(names)


def blank_outside_window(img: Any, mask: Optional[Tuple[int, int, int, int]]) -> Any:
    """Grey out what a GetWindowRect crop holds outside the drawn window (in place; the image is returned).

    `mask` gives the widths (left, top, right, bottom) of the invisible borders or of the overhang past the
    monitor; Windows 11 also rounds the window's corners, where the desktop shows through.
    """
    from PIL import ImageDraw

    if not mask or not any(mask):
        return img
    left, top, right, bottom = mask
    draw = ImageDraw.Draw(img)
    w, h = img.size
    r = 8
    boxes = [(0, 0, left - 1, h), (w - right, 0, w, h), (0, h - bottom, w, h), (0, 0, w, top - 1),
             (left, top, left + r, top + r), (w - right - r, top, w - right, top + r),
             (left, h - bottom - r, left + r, h - bottom), (w - right - r, h - bottom - r, w - right, h - bottom)]
    for box in boxes:
        if box[2] > box[0] and box[3] > box[1]:
            draw.rectangle(box, fill=(128, 128, 128))
    return img


def strip_stats(img: Any, mask: Optional[Tuple[int, int, int, int]]) -> Optional[Dict[str, float]]:
    """Luminance mean and spread of the invisible-border strips a GetWindowRect crop carries: numbers, no pixels.

    Those strips show whatever lies behind the window. Their statistics tell whether the classifier and the pixel
    identity of a visit were fed a quiet or a busy background, without keeping any of the user's desktop.
    """
    from PIL import ImageStat

    if not mask or not any(mask):
        return None
    left, _top, right, bottom = mask
    w, h = img.size
    parts = [img.crop(box).convert("L") for box in ((0, 0, left, h), (w - right, 0, w, h), (0, h - bottom, w, h))
             if box[2] > box[0] and box[3] > box[1]]
    if not parts:
        return None
    stats = [ImageStat.Stat(p) for p in parts]
    return {"mean": round(sum(s.mean[0] for s in stats) / len(stats), 1),
            "std": round(max(s.stddev[0] for s in stats), 1)}


class FrameSaver:
    """Saves kept live frames when their pixels change, off the capture thread; invisible borders are blanked."""

    def __init__(self, folder: Path, mask: Callable[[], Optional[Tuple[int, int, int, int]]]) -> None:
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.mask = mask
        self.index: List[Dict[str, Any]] = []
        self._last: Optional[bytes] = None
        self._queue: "queue.Queue[Any]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def __call__(self, frame: Dict[str, Any], img: Any) -> None:
        mask = self.mask()
        frame["strips"] = strip_stats(img, mask)
        digest = hashlib.blake2b(img.tobytes(), digest_size=16).digest()
        if digest == self._last:
            return
        self._last = digest
        name = f"{frame['index']:05d}.png"
        self.index.append({"t": frame["t"], "image": name, "rect": frame.get("rect"), "kind": "window"})
        self._queue.put((name, img.copy(), mask))

    def _run(self) -> None:
        from PIL import ImageDraw

        while True:
            item = self._queue.get()
            if item is None:
                return
            name, img, mask = item
            blank_outside_window(img, mask).save(self.folder / name)

    def close(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=30)


def run_live(scenario_path: Path, run_dir: Path, *, db: Path, port: int = 0, extract: bool = False,
             accept_cost: bool = False, max_screens: Optional[int] = None, countdown: int = 10,
             profiles: Sequence[str] = (), geometry: Optional[str] = None, url: Optional[str] = None,
             max_seconds: float = HEADED_MAX_SECONDS) -> Dict[str, Any]:
    """One headed run: refuses before anything opens when a guard fails.

    scenario_path may also be a scenario dict; url uses an emulator someone else runs instead of starting one.
    """
    if sys.platform != "win32":
        raise GuardError("the live run needs Windows (window rectangle and exposure checks)")
    scenario = with_geometry(load_scenario(scenario_path, max_seconds=max_seconds), geometry)
    cap = check_extract_request(extract, accept_cost, max_screens)
    run_dir.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import ctypes

    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    if any(pid for pid in matching_window_pids(WINDOW_TITLE)):
        raise GuardError(f"a window titled «{WINDOW_TITLE}» is already open: close it, the crop would be ambiguous")

    server: Any = RemoteServer(url) if url else EmulatorServer(db, _scenario_profiles(scenario, profiles), port)
    driver: Optional[DriverProcess] = None
    saver: Optional[FrameSaver] = None
    worker = None
    client = None
    hwnd_box: Dict[str, Any] = {}
    notes: Dict[str, Any] = {}
    try:
        catalogue = json.loads(server.get("/api/practices.json"))["practices"]
        check_roles(catalogue, scenario["practices"])
        truth = load_truth(server, scenario["practices"])
        config = harness_config(run_dir)

        from PyQt6.QtCore import QCoreApplication
        from local_extraction_client import LocalExtractionClient

        app = QCoreApplication.instance() or QCoreApplication([])
        recorder = Recorder()
        guard = PrivacyGuard()
        live_probes: List[Dict[str, Any]] = []
        if cap:
            pipeline: Any = CappedPipeline(_vlm_pipeline(cap), cap)
        else:
            pipeline = OraclePipeline(lambda: live_probes, {k: v["screens"] for k, v in truth.items()},
                                      lambda: recorder.last_acquired_t)
        client = LocalExtractionClient(pipeline=pipeline)
        job = client.start_job()

        def own_rect() -> Optional[Rect]:
            return window_rect(hwnd_box["hwnd"]) if "hwnd" in hwnd_box else None

        def exposed() -> bool:
            rect = own_rect()
            return bool(rect) and window_exposed(hwnd_box["pid"], rect)

        screen = (0, 0, ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1))

        def mask() -> Optional[Tuple[int, int, int, int]]:
            """Widths of what the crop holds outside the drawn window; the crop is clipped to the monitor."""
            outer, drawn = own_rect(), visible_frame_bounds(hwnd_box["hwnd"]) if "hwnd" in hwnd_box else None
            if not outer or not drawn:
                return None
            clipped = (max(outer[0], screen[0]), max(outer[1], screen[1]),
                       min(outer[2], screen[2]), min(outer[3], screen[3]))
            return tuple(max(0, v) for v in (drawn[0] - clipped[0], drawn[1] - clipped[1],
                                             clipped[2] - drawn[2], clipped[3] - drawn[3]))

        from frame_normalize import find_window_rect

        saver = FrameSaver(run_dir / "frames", mask)
        # With --extract the frames leave the machine: what the crop holds outside the drawn window is greyed first.
        scrub = (lambda img: blank_outside_window(img, mask())) if cap else None
        worker = make_harness_worker(config, lambda: job, client, recorder=recorder, rect_provider=find_window_rect,
                                     own_rect=own_rect, exposure=exposed, guard=guard, live=True, keep_frame=saver,
                                     scrub=scrub)
        print("Loading the page classifier (DINOv2)...", flush=True)
        worker._init_router()
        worker._load_registry()
        worker._router_ready = True

        for left in range(countdown, 0, -1):
            print(f"HEADED RUN: a Chrome window takes over the primary monitor in {left} s. Do not touch or cover it.",
                  flush=True)
            time.sleep(1)
        driver = DriverProcess(_driver_args(scenario, server.url, run_dir, headless=False, record=False),
                               run_dir / "driver.log")
        ready = driver.wait_for("ready", timeout=60)
        pid = int(ready["pid"])
        windows = own_windows(pid, WINDOW_TITLE)
        matching = matching_window_pids(WINDOW_TITLE)
        if len(windows) != 1 or matching != [pid]:
            raise GuardError(f"expected exactly one emulator window of Chrome {pid}: own {len(windows)}, "
                             f"titled {len(matching)}")
        hwnd_box.update(hwnd=windows[0][0], pid=pid)
        set_topmost(hwnd_box["hwnd"], True)
        time.sleep(0.5)
        notes["GetWindowRect"] = own_rect()
        notes["DWM frame bounds"] = visible_frame_bounds(hwnd_box["hwnd"])
        notes["invisible borders (l,t,r,b)"] = mask()
        notes["chrome ready"] = {k: ready.get(k) for k in ("bounds", "outer", "inner", "dpr")}
        for _attempt in range(10):
            if exposed():
                break
            set_topmost(hwnd_box["hwnd"], True)
            time.sleep(0.5)
        else:
            covering = process_names(covering_owners(pid, own_rect() or (0, 0, 0, 0)))
            raise GuardError(f"the emulator window is not on top after 5 s (covered by {covering}): "
                             "nothing was captured")

        worker.start()
        if not recorder.started.wait(30):
            raise GuardError("the capture worker did not start")
        go_at = time.time()
        driver.send("go")
        finished: Optional[Dict[str, Any]] = None
        while time.time() - go_at < max_seconds:
            app.processEvents()
            try:
                event = driver.queue.get(timeout=0.05)
            except queue.Empty:
                event = None
            if event and event.get("event") == "probe":
                live_probes.append({"t": event["t"], "state": event["state"]})
            if event and event.get("event") in ("done", "exit", "error"):
                finished = event
                if event.get("event") != "error":
                    break
            if recorder.abort:
                break
        tail_end = time.time() + 1.5
        while time.time() < tail_end and not recorder.abort:
            app.processEvents()
            time.sleep(0.05)
        end = time.time()
        worker.stop()
        worker.wait(10_000)
        set_topmost(hwnd_box["hwnd"], False)
        driver.close()
        driver_events = list(driver.events)
        driver = None
        wait_for_extractions(client, timeout=180 if cap else 30)
        results = client.get_results(job)
        if cap:
            spent = summarize_costs(results)
            print(f"--extract: ${spent['cost_usd']:.4f} spent on {spent['screens']} screens "
                  f"({spent['calls']} calls, {spent['tokens']} tokens), from the _meta of each result", flush=True)
        notes["driver"] = (finished or {}).get("event", "timeout")
        if recorder.abort:
            notes["ABORTED (privacy)"] = recorder.abort
        report = build_report(
            mode="live" + ("+extract" if cap else ""), scenario=scenario["name"],
            geometry=scenario["geometry"]["name"], frames=recorder.frames, adoptions=recorder.adoptions,
            probes=live_probes, start=go_at, end=end, fps=config.fps, results=results, truth=truth, guard=guard,
            ticks=recorder.ticks, notes=notes, t0=go_at,
            actions=[e for e in driver_events if e.get("event") != "probe"])
        report["saved_frames"] = saver.index
        return report
    finally:
        if worker is not None and worker.isRunning():
            worker.stop()
            worker.wait(10_000)
        if driver is not None:
            driver.close()
        if saver is not None:
            saver.close()
        if client is not None:
            client.shutdown()
        server.stop()
        _clean_temp()


def _vlm_pipeline(cap: int) -> Any:
    """The real ExtractionPipeline, after printing the cost estimate; the key is read by the provider only."""
    from extraction.config import LLM_MODEL, LLM_MODEL_ANCHOR, LLM_PROVIDER
    from extraction.llm_factory import create_chat_model
    from extraction.pipeline import ExtractionPipeline

    for model in {LLM_MODEL, LLM_MODEL_ANCHOR}:
        estimate = estimate_cost(model, cap)
        print(f"--extract: up to {cap} screens with {model} ({LLM_PROVIDER}): about ${estimate['typical_usd']:.2f}, "
              f"at most ${estimate['upper_usd']:.2f}", flush=True)
    return ExtractionPipeline(
        main_model=create_chat_model(LLM_PROVIDER, model=LLM_MODEL),
        anchor_model=create_chat_model(LLM_PROVIDER, model=LLM_MODEL_ANCHOR),
        main_model_name=LLM_MODEL, anchor_model_name=LLM_MODEL_ANCHOR)


# ============================================================
# CLI
# ============================================================


def _default_db() -> Path:
    """The harness's own database, one file per emulator schema: the server refuses a file of an older schema."""
    from bper_synthetic_db import SCHEMA_VERSION

    name = f"bper-live-test.v{SCHEMA_VERSION}.sqlite3"
    return Path(os.environ.get("BPER_LIVE_DB", REPO / ".tritech" / "local" / name))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", type=Path, default=None, help="emulator database (created on first use)")
    common.add_argument("--port", type=int, default=0, help="port of our own emulator server (default: free port)")
    common.add_argument("--profiles", action="append", default=[], help="extra profile file (repeatable)")
    common.add_argument("--geometry", choices=sorted(GEOMETRIES), help="play the scenario at another geometry")

    rec = sub.add_parser("record", parents=[common], help="headless recording of a scenario, for replay")
    rec.add_argument("--scenario", type=Path, required=True)
    rec.add_argument("--out", type=Path, required=True)

    rep = sub.add_parser("replay", help="a recording through the real worker on a virtual clock")
    rep.add_argument("--recording", type=Path, required=True)
    rep.add_argument("--out", type=Path, required=True, help="run folder for report.json and report.md")
    rep.add_argument("--realtime", action="store_true", help="wall-clock replay: the worker keeps its real lag")
    rep.add_argument("--desktop-image", type=Path, help="tile this image behind the window instead of a plain desktop")

    again = sub.add_parser("rescore", help="score a finished run again (report.json) and rewrite report.md")
    again.add_argument("--run", type=Path, required=True)

    live = sub.add_parser("live", parents=[common], help="headed run on the real monitor (Windows)")
    live.add_argument("--scenario", type=Path, required=True)
    live.add_argument("--out", type=Path, required=True)
    live.add_argument("--extract", action="store_true", help="real VLM extraction (paid; needs --accept-cost)")
    live.add_argument("--accept-cost", action="store_true")
    live.add_argument("--max-screens", type=int, default=None,
                      help=f"screens sent to the VLM (default {MAX_SCREENS_DEFAULT}, at most {MAX_SCREENS_CAP})")
    live.add_argument("--countdown", type=int, default=10)
    args = parser.parse_args(argv)
    # The edge agent's order (CLAUDE.md constraint 3): the .env is loaded before anything imports `extraction`,
    # whose configuration is read at import time. The key stays in the process environment, never printed.
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO / ".env")
    except ImportError:
        pass

    try:
        if args.command == "record":
            folder = record(args.scenario, args.out, db=args.db or _default_db(), port=args.port,
                            profiles=args.profiles, geometry=args.geometry)
            print(f"recording in {folder}")
            return 0
        if args.command == "rescore":
            report = rescore(json.loads((args.run / "report.json").read_text(encoding="utf-8")))
            print(f"report: {write_report(report, args.run)}")
            return 0
        if args.command == "replay":
            recording = json.loads((args.recording / "recording.json").read_text(encoding="utf-8"))
            report = run_replay(args.recording, truth=recording.get("truth"), run_dir=args.out,
                                realtime=args.realtime, desktop_image=args.desktop_image)
            report["scenario"] = recording.get("scenario")
            report["geometry"] = (recording.get("geometry") or {}).get("name")
            report["t0"] = recording["frames"][0]["t"] if recording.get("frames") else 0.0
            print(f"report: {write_report(report, args.out)}")
            return 0
        report = run_live(args.scenario, args.out, db=args.db or _default_db(), port=args.port,
                          extract=args.extract, accept_cost=args.accept_cost, max_screens=args.max_screens,
                          countdown=args.countdown, profiles=args.profiles, geometry=args.geometry)
        print(f"report: {write_report(report, args.out)}")
        return 2 if "ABORTED (privacy)" in report.get("notes", {}) else 0
    except (ScenarioError, GuardError, PrivacyAbort) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
