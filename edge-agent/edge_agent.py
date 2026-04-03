"""Entry point per l'applicazione Edge Agent."""

from __future__ import annotations

import sys
from pathlib import Path

# Load .env from project root (parent of edge-agent/) so LLM_API_KEY etc. are set
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except Exception:
    pass

# Use an absolute import from the app root (same level as `workers/`).
from image_ops import preprocess_for_ocr, to_png8, to_webp_lossless

from PyQt6 import QtWidgets

from config import AgentConfig
from ui.main_window import MainWindow


def main() -> int:
    """
    Funzione principale dell'applicazione.

    Inizializza Qt, carica la configurazione e mostra la finestra principale.

    Returns:
        Exit code restituito da QApplication.exec().
    """
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Edge Agent")
    app.setOrganizationName("Tri-tech solutions")

    try:
        from qt_material import apply_stylesheet
        from PyQt6.QtCore import Qt
        is_dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark
        theme = "dark_cyan.xml" if is_dark else "dark_cyan.xml"
        apply_stylesheet(app, theme=theme)
    except ImportError:
        pass

    # Carica configurazione
    config_path = Path(__file__).parent / "config.ini"
    config = AgentConfig(config_path)

    # Crea e mostra finestra principale
    window = MainWindow(config)
    window.show()

    # Entra nel loop eventi Qt
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
