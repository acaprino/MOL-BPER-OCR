"""Risoluzione dei percorsi dell'app, da sorgente e da bundle PyInstaller."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def recovery_dir() -> Path:
    """Keep operator sessions in the user's profile across portable app upgrades."""
    override = os.getenv("EDGE_AGENT_RECOVERY_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.getenv("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "MutuiOnline" / "BPER-EdgeAgent" / "recovery"


def is_frozen() -> bool:
    """True se l'app gira da bundle PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """
    Cartella base scrivibile dell'app.

    Da bundle è la cartella accanto all'exe (layout portable);
    da sorgente è la cartella src/edge-agent/.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def backup_dir() -> Path:
    """Resolve the replica and history relative to the installed application."""
    directory = Path(os.getenv("EDGE_AGENT_BACKUP_DIR") or "backup").expanduser()
    return (app_dir() / directory).resolve()


def src_dir() -> Path:
    """Cartella src/ da sorgente; la cartella dell'exe da bundle."""
    if is_frozen():
        return app_dir()
    return app_dir().parent


def project_root() -> Path:
    """Root del progetto: il repo da sorgente, la cartella dell'exe da bundle."""
    if is_frozen():
        return app_dir()
    return app_dir().parent.parent


def config_ini() -> Path:
    """Percorso del config.ini modificabile."""
    return app_dir() / "config.ini"


def env_file() -> Path:
    """Percorso del .env: accanto all'exe da bundle, alla root del repo da sorgente."""
    return project_root() / ".env"


def templates_dir() -> Path:
    """Cartella asset BPER: catalogo delle pagine e prototipi distribuiti con l'app."""
    return app_dir() / "assets" / "templates" / "bper"


def torch_cache_dir() -> Path:
    """Cache locale dei pesi torch (TORCH_HOME) per mantenere la cartella portable."""
    return app_dir() / "torch-cache"


def bundled_defaults_dir() -> Path:
    """Cartella dei file default (bundle: datas PyInstaller; sorgente: src/edge-agent/defaults)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_dir())) / "defaults"
    return app_dir() / "defaults"


def prompts_dir() -> Path:
    """Catalogo dei prompt LLM modificabile (accanto all'exe da bundle, root del repo da sorgente)."""
    return project_root() / "prompts"


def bundled_prompts_dir() -> Path:
    """Copia del catalogo prompt inclusa nel bundle, usata per il seed al primo avvio."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_dir())) / "prompts"
    return project_root() / "prompts"


def bundled_assets_dir() -> Path:
    """Copia degli asset inclusa nel bundle, usata per il seed al primo avvio."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_dir())) / "assets"
    return app_dir() / "assets"
