"""Tests for edge-agent/env_key.py: the API key written into a packaged .env.

A beta tester cannot be expected to know what a Gemini key is, so the build can
bake one into the portable package's .env. These tests drive the same entry
point build_exe.bat calls and read the result the way the app does at startup
(python-dotenv), so they pin what the first run will actually see.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_KEY_SCRIPT = REPO_ROOT / "edge-agent" / "env_key.py"
ENV_TEMPLATE = REPO_ROOT / "edge-agent" / "defaults" / "env.template"


def _bake(env_path: Path, key: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["EDGE_AGENT_PACKAGE_KEY"] = key
    return subprocess.run(
        [sys.executable, str(ENV_KEY_SCRIPT), str(env_path)],
        env=env,
        capture_output=True,
        text=True,
    )


def _packaged_env(tmp_path: Path) -> Path:
    env_path = tmp_path / ".env"
    shutil.copyfile(ENV_TEMPLATE, env_path)
    return env_path


def test_packaged_env_hands_the_key_to_the_first_run(tmp_path: Path) -> None:
    env_path = _packaged_env(tmp_path)

    result = _bake(env_path, "AIzaTestKey_123-abc")

    assert result.returncode == 0, result.stderr
    values = dotenv_values(env_path)
    assert values["LLM_API_KEY"] == "AIzaTestKey_123-abc"
    assert values["LLM_PROVIDER"] == "gemini"


def test_packaged_env_is_refused_without_a_key(tmp_path: Path) -> None:
    env_path = _packaged_env(tmp_path)

    result = _bake(env_path, "   ")

    assert result.returncode != 0
    assert not dotenv_values(env_path).get("LLM_API_KEY")


def test_packaged_env_is_refused_for_a_key_with_a_line_break(tmp_path: Path) -> None:
    env_path = _packaged_env(tmp_path)

    result = _bake(env_path, "AIzaTestKey\nLLM_PROVIDER=openai")

    assert result.returncode != 0
    assert dotenv_values(env_path)["LLM_PROVIDER"] == "gemini"
