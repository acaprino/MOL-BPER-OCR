"""Startup from the desktop entry point with an unavailable recovery directory."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")


def test_gui_launcher_shows_the_desktop_error_when_the_prompt_catalog_is_unreadable(tmp_path: Path) -> None:
    launcher = Path(__file__).resolve().parents[1] / "main.py"
    script = """
import runpy, sys
from PyQt6.QtWidgets import QMessageBox
QMessageBox.critical = lambda owner, title, message: print("DIALOG", title, message)
sys.argv = [sys.argv[1], "--gui"]
runpy.run_path(sys.argv[0], run_name="__main__")
"""
    env = dict(os.environ, EDGE_AGENT_SMOKE="1", LLM_API_KEY="offline-only",
               QT_QPA_PLATFORM="offscreen", PROMPTS_DIR=str(tmp_path / "missing-catalog"),
               EDGE_AGENT_RECOVERY_DIR=str(tmp_path / "unused"))
    result = subprocess.run([sys.executable, "-c", script, str(launcher)], env=env,
                            capture_output=True, timeout=45)
    assert result.returncode == 1
    assert b"DIALOG Edge Agent" in result.stdout


def test_inaccessible_recovery_directory_stops_startup_with_an_operator_message(
    qapp: QtWidgets.QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import bootstrap
    import edge_agent
    from config import AgentConfig

    blocked = tmp_path / "occupied"
    blocked.write_text("occupied", encoding="utf-8")
    monkeypatch.setenv("EDGE_AGENT_RECOVERY_DIR", str(blocked / "recovery"))
    monkeypatch.setenv("EDGE_AGENT_BACKUP_DIR", str(tmp_path / "backup"))
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("EDGE_AGENT_SMOKE", "1")
    monkeypatch.delenv("EDGE_AGENT_PRIORITY", raising=False)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    config = AgentConfig(config_path=tmp_path / "config.ini")
    monkeypatch.setattr(bootstrap, "run_preflight", lambda _parent: config)
    dialog = Mock()
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", dialog)

    assert edge_agent.main() == 1
    assert "recupero" in dialog.call_args.args[2].lower()
    assert blocked.read_text(encoding="utf-8") == "occupied"
