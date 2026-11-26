"""Process scheduling at the Windows API boundary."""

import ctypes
import sys
from unittest.mock import Mock

import pytest

from process_priority import apply_process_priority


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> Mock:
    kernel = Mock()
    kernel.GetCurrentProcess.return_value = 42
    kernel.SetPriorityClass.return_value = 1
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", Mock(return_value=kernel), raising=False)
    return kernel


def test_above_normal_is_applied_to_the_current_process(
    windows: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EDGE_AGENT_PRIORITY", "above_normal")
    apply_process_priority()
    windows.SetPriorityClass.assert_called_once_with(42, 0x8000)


@pytest.mark.parametrize("setting", [None, "normal", "high", "realtime"])
def test_other_settings_keep_the_inherited_priority(
    setting: str | None, windows: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    if setting is None:
        monkeypatch.delenv("EDGE_AGENT_PRIORITY", raising=False)
    else:
        monkeypatch.setenv("EDGE_AGENT_PRIORITY", setting)
    apply_process_priority()
    windows.SetPriorityClass.assert_not_called()


def test_other_platforms_keep_the_inherited_priority(
    windows: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("EDGE_AGENT_PRIORITY", "above_normal")
    apply_process_priority()
    windows.SetPriorityClass.assert_not_called()


def test_windows_refusing_a_priority_change_only_logs_a_warning(
    windows: Mock, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("EDGE_AGENT_PRIORITY", "above_normal")
    windows.SetPriorityClass.return_value = 0
    apply_process_priority()
    assert "priority" in caplog.text.lower()
