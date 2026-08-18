"""Tests for edge-agent/stability.py (page stability state machine)."""

from stability import StabilityConfig, StabilityTracker

CFG = StabilityConfig(min_matches=2, min_seconds=2.0, miss_tolerance=1)


def test_capture_requires_matches_and_min_seconds() -> None:
    t = StabilityTracker(CFG)
    assert t.observe("s9", 0.0) is None
    assert t.observe("s9", 1.0) is None  # 2 matches but only 1.0s elapsed
    assert t.observe("s9", 2.1) == "s9"


def test_two_quick_matches_do_not_capture_mid_scroll() -> None:
    t = StabilityTracker(CFG)
    assert t.observe("s6", 0.0) is None
    assert t.observe("s6", 0.4) is None  # matches ok, elapsed < min_seconds


def test_single_miss_is_tolerated() -> None:
    # Regression for the 13:38:06 log: one unrecognized frame killed a valid candidate.
    t = StabilityTracker(CFG)
    t.observe("s9", 0.0)
    t.observe("s9", 1.0)
    assert t.observe(None, 1.5) is None
    assert t.candidate == "s9"
    assert t.observe("s9", 2.2) == "s9"


def test_two_consecutive_misses_reset() -> None:
    t = StabilityTracker(CFG)
    t.observe("s9", 0.0)
    t.observe(None, 0.5)
    t.observe(None, 1.0)
    assert t.candidate is None


def test_single_different_page_blip_keeps_candidate() -> None:
    t = StabilityTracker(CFG)
    t.observe("s9", 0.0)
    t.observe("s9", 1.0)
    assert t.observe("s2", 1.4) is None  # blip, tolerated as miss
    assert t.candidate == "s9"
    assert t.observe("s9", 2.1) == "s9"


def test_two_consecutive_new_page_observations_switch_candidate() -> None:
    t = StabilityTracker(CFG)
    t.observe("s9", 0.0)
    t.observe("s9", 1.0)
    assert t.observe("s2", 1.5) is None
    assert t.observe("s2", 2.0) is None
    assert t.candidate == "s2"
    # first_seen anchored at the first s2 observation (1.5): 1.5 + 2.0 = 3.5
    assert t.observe("s2", 3.4) is None
    assert t.observe("s2", 3.6) == "s2"


def test_miss_overflow_adopts_pending_page() -> None:
    t = StabilityTracker(CFG)
    t.observe("s9", 0.0)
    t.observe("s2", 0.5)   # miss 1, pending s2
    t.observe("s6", 1.0)   # miss 2 > tolerance: reset, adopt pending s6
    assert t.candidate == "s6"


def test_observe_none_without_candidate_is_noop() -> None:
    t = StabilityTracker(CFG)
    assert t.observe(None, 0.0) is None
    assert t.candidate is None


def test_reset_clears_state() -> None:
    t = StabilityTracker(CFG)
    t.observe("s9", 0.0)
    t.reset()
    assert t.candidate is None
    assert t.observe("s9", 5.0) is None  # fresh cycle after reset


# --------------------------------------------------- unchanged-frame confirmation

def test_unchanged_frame_confirms_the_candidate_without_a_second_route() -> None:
    """An identical frame is direct evidence that the page has not changed.

    The page router costs one VLM call per answer (4-5s), so demanding two
    concordant answers means demanding that the operator hold a screen still for
    10-24 seconds. A duplicate frame measures the same thing the second answer was
    standing in for, at no cost.
    """
    t = StabilityTracker(CFG)
    assert t.observe("s9", 0.0) is None       # one routed answer adopts the candidate
    assert t.confirm(1.0) is None             # unchanged, but under min_seconds
    assert t.confirm(2.1) == "s9"             # unchanged for long enough


def test_confirming_without_a_candidate_does_nothing() -> None:
    t = StabilityTracker(CFG)

    assert t.confirm(5.0) is None
    assert t.candidate is None


def test_confirmation_still_honours_min_seconds() -> None:
    # An unchanged frame must not shortcut the anti-mid-scroll delay.
    t = StabilityTracker(CFG)
    t.observe("s4", 0.0)

    assert t.confirm(0.5) is None
    assert t.confirm(1.9) is None
    assert t.confirm(2.0) == "s4"


def test_confirmation_does_not_resurrect_a_reset_candidate() -> None:
    t = StabilityTracker(CFG)
    t.observe("s4", 0.0)
    t.reset()

    assert t.confirm(10.0) is None
