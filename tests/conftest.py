"""Shared test setup: make repo root and src/edge-agent/ importable."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
EDGE_AGENT_DIR = SRC_DIR / "edge-agent"

for _p in (str(REPO_ROOT), str(SRC_DIR), str(EDGE_AGENT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ------------------------------------------------- shared fake VLM plumbing

EMPTY_VLM_RESPONSE = {"fields": {}, "soggetti": [], "fidi": [], "garanzie": [], "_meta": {}}


def install_fake_vlm(monkeypatch, recorder, responder=None):
    """Route every pipeline VLM call to `recorder`; no network, no model.

    One place owns the monkeypatch target and the response contract, so when
    either changes (as happened when 'garanzie' joined the schema) one edit
    fixes every suite instead of each file's copy failing separately.

    Also pins the pipeline's import-time env bindings that would otherwise leak
    into tests: with STOP_ON_ANCHOR_UNCERTAIN=1 exported, extract_from_image
    returns before the main pass and a size assertion fails looking like a crop
    regression; MAX_IMAGE_LONG_SIDE below a fixture's frame width shrinks the
    frame and fails the same way.

    `responder(kwargs) -> dict | None` lets a test shape specific replies;
    returning None falls back to the empty response.
    """
    import extraction.pipeline as pipeline_mod

    def fake_call(**kwargs):
        recorder(kwargs)
        reply = responder(kwargs) if responder is not None else None
        if reply is not None:
            return reply
        return {key: (dict(val) if isinstance(val, dict) else list(val))
                for key, val in EMPTY_VLM_RESPONSE.items()}

    monkeypatch.setattr(pipeline_mod, "call_vlm_with_retry", fake_call)
    monkeypatch.setattr(pipeline_mod, "STOP_ON_ANCHOR_UNCERTAIN", False)
    monkeypatch.setattr(pipeline_mod, "MAX_IMAGE_LONG_SIDE", 4000)


# ------------------------------------------------- shared QApplication (widget tests)
#
# One QApplication for the whole session, created at import so a plain
# QCoreApplication made by an earlier test module can never block widget tests.
# Offscreen: no display needed (also on Modal). Absent PyQt6 -> widget tests skip.

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PyQt6.QtWidgets import QApplication

    _QAPP = QApplication.instance() or QApplication([])
except ImportError:
    _QAPP = None


@pytest.fixture(scope="session")
def qapp():
    if _QAPP is None:
        pytest.skip("PyQt6 is not installed")
    return _QAPP


@pytest.fixture
def isolated_edge_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "backup"
    monkeypatch.setenv("EDGE_AGENT_BACKUP_DIR", str(directory))
    return directory
