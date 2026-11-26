"""Exercise the capture tab at the worker signal boundary without grabbing a monitor."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PyQt6.QtWidgets")
os.environ.setdefault("LLM_API_KEY", "test-key")

from PyQt6 import QtCore, QtWidgets
from config import AgentConfig
from ui import capture_tab
from workers.capture import BaseCaptureWorker


class CaptureSource(BaseCaptureWorker):
    navigation_changed = QtCore.pyqtSignal(str, dict)

    def __init__(self, api_client: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.choices: list[tuple[str, str, bool]] = []

    def start_capture(self) -> None:
        pass

    def set_page_available(self, ndg: str, page: str, available: bool) -> None:
        self.choices.append((ndg, page, available))

    def reopen_page(self, ndg: str, page: str) -> None:
        self.reopened = (ndg, page)


class Session(QtCore.QObject):
    result_ready = QtCore.pyqtSignal(str, dict)
    frame_queued = QtCore.pyqtSignal(str, str)

    def start_job(self) -> str:
        return "current"


@pytest.fixture()
def tab(qapp: QtWidgets.QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[capture_tab.CaptureTab]:
    monkeypatch.setattr(capture_tab, "BPERCaptureWorker", CaptureSource)
    config = AgentConfig(config_path=tmp_path / "config.ini")
    config.show_capture_border = False
    widget = capture_tab.CaptureTab(config, Session())
    widget.start_capture()
    yield widget
    widget.close()


def snapshot(ndg: str) -> dict[str, Any]:
    return dict(practice_ndg=ndg, current_page="Fidi", next_page="Note", action="Apri la scheda delle note.",
                missing=["Note"], optional=["Tooltip garanzia"], unavailable=[], captured=["Fidi"],
                status="captured", identity_source="extracted")


def test_navigation_shows_the_current_practice_and_every_outstanding_view(tab: capture_tab.CaptureTab) -> None:
    tab.worker.navigation_changed.emit("current", snapshot("100"))
    guide = tab.navigation_card
    assert "100" in guide.current.text() and "Fidi" in guide.current.text()
    assert "Note" in guide.next_step.text() and "Apri la scheda" in guide.next_step.text()
    assert [guide.views.itemText(i) for i in range(guide.views.count())] == [
        "Da acquisire · Note", "Se presente · Tooltip garanzia", "Acquisita · Fidi",
    ]


def test_optional_view_choice_is_bound_to_the_practice_on_screen(tab: capture_tab.CaptureTab) -> None:
    tab.worker.navigation_changed.emit("current", snapshot("100"))
    guide = tab.navigation_card
    guide.views.setCurrentIndex(1)
    guide.availability_button.click()
    assert tab.worker.choices == [("100", "Tooltip garanzia", False)]
    changed = snapshot("100")
    changed.update(optional=[], unavailable=["Tooltip garanzia"])
    tab.worker.navigation_changed.emit("current", changed)
    guide.views.setCurrentIndex(guide.views.findText("Non applicabile · Tooltip garanzia"))
    guide.availability_button.click()
    assert tab.worker.choices[-1] == ("100", "Tooltip garanzia", True)


def test_an_old_job_cannot_replace_the_visible_checklist(tab: capture_tab.CaptureTab) -> None:
    tab.worker.navigation_changed.emit("current", snapshot("200"))
    tab.worker.navigation_changed.emit("previous", snapshot("100"))
    assert "200" in tab.navigation_card.current.text()


def test_operator_can_return_a_captured_view_to_the_checklist(tab: capture_tab.CaptureTab) -> None:
    tab.worker.navigation_changed.emit("current", snapshot("100"))
    guide = tab.navigation_card
    guide.views.setCurrentIndex(guide.views.findText("Acquisita · Fidi"))
    assert guide.availability_button.text() == "Da riacquisire"
    guide.availability_button.click()
    assert tab.worker.reopened == ("100", "Fidi")


def test_checklist_stays_open_on_the_highlighted_view_while_recognition_runs(tab: capture_tab.CaptureTab) -> None:
    tab.worker.navigation_changed.emit("current", snapshot("100"))
    combo = tab.navigation_card.views
    combo.showPopup()
    combo.view().setCurrentIndex(combo.model().index(1, 0))
    pending = snapshot("100")
    pending.update(practice_ndg=None, coverage_ndg="100", status="recognizing", current_page=None)
    tab.worker.navigation_changed.emit("current", pending)
    assert combo.view().currentIndex().data() == "Se presente · Tooltip garanzia"
    combo.hidePopup()


def test_leaving_the_banking_window_keeps_the_last_identified_checklist_actionable(tab: capture_tab.CaptureTab) -> None:
    tab.worker.navigation_changed.emit("current", snapshot("100"))
    tab.worker.navigation_changed.emit("current", {
        "status": "unrecognized", "current_page": None, "practice_ndg": None,
        "action": "Mostra la finestra PEF.", "missing": [], "optional": [], "unavailable": [], "captured": [],
    })
    guide = tab.navigation_card
    assert "100" not in guide.current.text()
    assert "100" in guide.view_count.text()
    guide.views.setCurrentIndex(guide.views.findText("Se presente · Tooltip garanzia"))
    guide.availability_button.click()
    assert tab.worker.choices == [("100", "Tooltip garanzia", False)]


def test_stopping_disables_availability_choices_before_the_worker_exits(tab: capture_tab.CaptureTab) -> None:
    tab.worker.navigation_changed.emit("current", snapshot("100"))
    guide = tab.navigation_card
    guide.views.setCurrentIndex(1)
    assert guide.availability_button.isEnabled()
    tab.stop_capture()
    assert not guide.availability_button.isEnabled()


def test_stopped_guide_labels_the_last_checklist_when_extraction_is_still_pending(tab: capture_tab.CaptureTab) -> None:
    progress = snapshot("100")
    progress.update(status="pending", next_page=None, practice_ndg=None, coverage_ndg="100")
    tab.worker.navigation_changed.emit("current", progress)
    tab.stop_capture()
    tab.worker.finished.emit()
    guide = tab.navigation_card
    assert "Cattura terminata" in guide.current.text() and "100" in guide.current.text()
    assert "Dati estratti" in guide.next_step.text()
    assert guide.views.findText("Da acquisire · Note") >= 0


def test_new_selection_retires_the_previous_checklist_even_for_the_same_customer(tab: capture_tab.CaptureTab) -> None:
    first = dict(snapshot("100"), practice_number="31", decision_key="pef:31")
    tab.worker.navigation_changed.emit("current", first)
    guide = tab.navigation_card
    guide.views.setCurrentIndex(1)
    guide.availability_button.click()
    assert tab.worker.choices[-1] == ("pef:31", "Tooltip garanzia", False)
    tab.worker.navigation_changed.emit("current", dict(new_selection=True, status="pending",
                                                      missing=["Fidi"], captured=[], optional=[]))
    assert guide.views.count() == 1 and "Da acquisire" in guide.views.itemText(0)
    assert not guide.availability_button.isEnabled()
    assert "31" not in guide.current.text()
    tab.worker.navigation_changed.emit("current", dict(snapshot("100"), practice_number="42", decision_key="pef:42"))
    assert "42" in guide.current.text()


def test_capture_border_leaves_the_banking_window_visible_to_native_hit_testing(qapp: QtWidgets.QApplication) -> None:
    from ui.overlay import CaptureBorderOverlay

    overlay = CaptureBorderOverlay(QtCore.QRect(0, 0, 400, 300))
    try:
        overlay.set_screen_geometry(QtCore.QRect(100, 0, 600, 400))
        assert overlay.windowFlags() & QtCore.Qt.WindowType.WindowDoesNotAcceptFocus
        assert not overlay.mask().isEmpty()
        assert not overlay.mask().contains(overlay.rect().center())
        assert overlay.mask().contains(QtCore.QPoint(3, 3))
    finally:
        overlay.close()
