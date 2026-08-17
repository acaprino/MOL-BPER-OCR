"""Risoluzione dei percorsi dell'app, da sorgente e da bundle PyInstaller."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """True se l'app gira da bundle PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """
    Cartella base scrivibile dell'app.

    Da bundle è la cartella accanto all'exe (layout portable);
    da sorgente è la cartella edge-agent/.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def project_root() -> Path:
    """Root del progetto: il repo da sorgente, la cartella dell'exe da bundle."""
    if is_frozen():
        return app_dir()
    return app_dir().parent


def config_ini() -> Path:
    """Percorso del config.ini modificabile."""
    return app_dir() / "config.ini"


def env_file() -> Path:
    """Percorso del .env: accanto all'exe da bundle, alla root del repo da sorgente."""
    return project_root() / ".env"


def templates_dir() -> Path:
    """Cartella asset/prototipi BPER (scrivibile: ospita la cache dei prototipi)."""
    return app_dir() / "assets" / "templates" / "bper"


def torch_cache_dir() -> Path:
    """Cache locale dei pesi torch (TORCH_HOME) per mantenere la cartella portable."""
    return app_dir() / "torch-cache"


def bundled_defaults_dir() -> Path:
    """Cartella dei file default (bundle: datas PyInstaller; sorgente: edge-agent/defaults)."""
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
