"""Tkinter startup uses the same effective dotenv configuration as extraction."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
_READ_CONFIG = """
import json
import sys
import tkinter as tk

sys.path[:0] = [sys.argv[2], sys.argv[3]]
import gui_app
from extraction.config import LLM_PROVIDER, LLM_MODEL

result = {"effective_provider": LLM_PROVIDER, "effective_model": LLM_MODEL}
if sys.argv[1] == "widgets":
    try:
        app = gui_app.App()
    except tk.TclError as error:
        result["tk_unavailable"] = str(error)
    else:
        app.withdraw()
        try:
            result["provider"] = app.provider_choice.get()
            result["model"] = app.model_choice.get()
            menu = app.model_menu["menu"]
            result["model_options"] = [menu.entrycget(index, "label")
                                       for index in range(menu.index("end") + 1)]
        finally:
            app.destroy()
print(json.dumps(result))
"""


def _startup_config(
    directory: Path,
    dotenv_values: str,
    *,
    widgets: bool = False,
    inherited_settings: dict[str, str] | None = None,
) -> dict[str, Any]:
    # The GUI copy and cwd both point at synthetic dotenv data. The user's real
    # dotenv file cannot be discovered through either python-dotenv lookup mode.
    shutil.copyfile(REPO_ROOT / "gui_app.py", directory / "gui_app.py")
    (directory / ".env").write_text(dotenv_values, encoding="utf-8")
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("LLM_", "OPENAI_", "GEMINI_", "GOOGLE_"))
        and key not in ("PROMPTS_DIR", "PYTHON_DOTENV_DISABLED")
    }
    env.update(inherited_settings or {})
    for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        env[variable] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", _READ_CONFIG, "widgets" if widgets else "import",
         str(directory), str(REPO_ROOT)],
        cwd=directory, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    if widgets and "tk_unavailable" in result:
        pytest.skip(f"Tk display unavailable: {result['tk_unavailable']}")
    return result


def test_dotenv_config_is_loaded_before_extraction(tmp_path: Path) -> None:
    config = _startup_config(tmp_path, "LLM_PROVIDER= GeMiNi\nLLM_MODEL=gemini-2.0-flash\n")

    assert (config["effective_provider"], config["effective_model"]) == ("gemini", "gemini-2.0-flash")


@pytest.fixture(scope="module")
def configured_gui(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    directory = tmp_path_factory.mktemp("gemini-gui")
    return _startup_config(directory, "LLM_PROVIDER=gemini\nLLM_MODEL=gemini-2.0-flash\n",
                           widgets=True)


def test_initial_provider_uses_effective_configuration(configured_gui: dict[str, Any]) -> None:
    assert configured_gui["provider"] == "gemini"


def test_initial_model_uses_effective_configuration(configured_gui: dict[str, Any]) -> None:
    assert configured_gui["model"] == "gemini-2.0-flash"


def test_initial_model_menu_lists_the_selected_provider(configured_gui: dict[str, Any]) -> None:
    assert "gemini-2.0-flash" in configured_gui["model_options"]
    assert "gpt-4o" not in configured_gui["model_options"]


def test_custom_configured_model_survives_menu_creation(tmp_path: Path) -> None:
    config = _startup_config(tmp_path, "LLM_PROVIDER=openai\nLLM_MODEL=gpt-4o-2024-08-06\n",
                             widgets=True)

    assert config["model"] == "gpt-4o-2024-08-06"


def test_exported_settings_take_precedence_over_dotenv(tmp_path: Path) -> None:
    config = _startup_config(
        tmp_path, "LLM_PROVIDER=gemini\nLLM_MODEL=gemini-2.0-flash\n",
        inherited_settings={"LLM_PROVIDER": "openai", "LLM_MODEL": "gpt-4o-mini"},
    )

    assert (config["effective_provider"], config["effective_model"]) == ("openai", "gpt-4o-mini")
