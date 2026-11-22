"""Tests for src/edge-agent/error_report.py (an error in a slot must not end the app)."""

import sys

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6 import QtCore

import error_report


class _Boom(QtCore.QObject):
    fired = QtCore.pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.fired.connect(self._explode)

    def _explode(self) -> None:
        raise ValueError("slot exploded")


def test_a_slot_exception_is_reported_instead_of_ending_the_process(qapp, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)  # put back by monkeypatch
    shown: list = []
    error_report.install_excepthook(show=shown.append)
    boom = _Boom()  # a temporary would be collected before the signal fires
    boom.fired.emit()
    qapp.processEvents()
    assert len(shown) == 1 and "slot exploded" in shown[0]
    assert "slot exploded" in capsys.readouterr().err


def test_repeated_errors_open_one_dialog_but_are_all_logged(qapp, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    shown: list = []
    error_report.install_excepthook(show=shown.append, min_interval=60.0)
    boom = _Boom()
    boom.fired.emit()
    boom.fired.emit()
    qapp.processEvents()
    assert len(shown) == 1
    assert capsys.readouterr().err.count("slot exploded") >= 2


def test_a_failing_dialog_never_raises_out_of_the_hook(qapp, monkeypatch) -> None:
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)

    def broken_dialog(_text: str) -> None:
        raise RuntimeError("no display")

    error_report.install_excepthook(show=broken_dialog)
    boom = _Boom()  # a temporary would be collected before the signal fires
    boom.fired.emit()
    qapp.processEvents()  # reaching this line is the assertion
