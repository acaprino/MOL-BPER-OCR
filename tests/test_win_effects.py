"""Tests for ui/win_effects.py (dark title bar and optional Mica through DWM)."""

import os

import pytest

pytest.importorskip("PyQt6.QtWidgets")

# Must be set before ui/__init__ pulls in extraction.config (read at import time).
os.environ.setdefault("LLM_API_KEY", "test-key")

from PyQt6.QtWidgets import QWidget

from ui import win_effects


@pytest.fixture
def calls(monkeypatch) -> list:
    """The DWM call is the genuine OS boundary: record it instead of making it."""
    recorded: list = []
    monkeypatch.setattr(win_effects, "_set_attribute", lambda hwnd, attribute, value: recorded.append((attribute, value)) or True)
    monkeypatch.setattr(win_effects.sys, "platform", "win32")
    return recorded


def test_constants_match_the_documented_dwm_values() -> None:
    assert win_effects.DWMWA_USE_IMMERSIVE_DARK_MODE == 20
    assert win_effects.DWMWA_SYSTEMBACKDROP_TYPE == 38
    assert win_effects.BACKDROP_MICA == 2


def test_effects_are_a_noop_off_windows(calls, monkeypatch, qapp) -> None:
    monkeypatch.setattr(win_effects.sys, "platform", "linux")
    assert win_effects.apply_window_effects(QWidget(), dark=True) is False
    assert calls == []


def test_effects_are_a_noop_on_old_windows_builds(calls, monkeypatch, qapp) -> None:
    monkeypatch.setattr(win_effects, "_windows_build", lambda: 18362)
    assert win_effects.apply_window_effects(QWidget(), dark=True) is False
    assert calls == []


def test_dark_title_bar_follows_the_theme_from_windows_10_2004(calls, monkeypatch, qapp) -> None:
    monkeypatch.setattr(win_effects, "_windows_build", lambda: 19041)
    assert win_effects.apply_window_effects(QWidget(), dark=True) is True
    assert win_effects.apply_window_effects(QWidget(), dark=False) is True
    assert calls == [(20, 1), (20, 0)]


def test_mica_is_requested_only_when_enabled_and_supported(calls, monkeypatch, qapp) -> None:
    monkeypatch.setattr(win_effects, "_windows_build", lambda: 22621)
    win_effects.apply_window_effects(QWidget(), dark=False)
    assert calls == [(20, 0)]  # USE_MICA is off until a real capture shows the frames unchanged
    calls.clear()
    monkeypatch.setattr(win_effects, "USE_MICA", True)
    win_effects.apply_window_effects(QWidget(), dark=False)
    assert calls == [(20, 0), (38, 2)]


def test_a_failing_dwm_call_never_raises(monkeypatch, qapp) -> None:
    monkeypatch.setattr(win_effects.sys, "platform", "win32")
    monkeypatch.setattr(win_effects, "_windows_build", lambda: 22621)

    def explode(hwnd, attribute, value):
        raise OSError("dwmapi unavailable")

    monkeypatch.setattr(win_effects, "_set_attribute", explode)
    assert win_effects.apply_window_effects(QWidget(), dark=True) is False
