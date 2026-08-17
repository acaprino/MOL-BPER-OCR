"""Entry point per l'applicazione Edge Agent."""

from __future__ import annotations

import os
import sys

import app_paths

# Da bundle windowed (console=False) sys.stdout/stderr sono None: qualunque
# print (torch.hub, tqdm, warning) manderebbe in crash chi scrive. Redirigiamo
# su un file di log accanto all'exe, utile anche per la diagnostica remota.
if sys.stdout is None or sys.stderr is None:
    try:
        _log = open(app_paths.app_dir() / "edge-agent.log", "w", encoding="utf-8", buffering=1)
    except Exception:
        _log = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = _log
    if sys.stderr is None:
        sys.stderr = _log

# Load .env (accanto all'exe da bundle; root del repo da sorgente) così
# LLM_API_KEY ecc. sono nel processo prima degli import di `extraction`.
try:
    from dotenv import load_dotenv
    load_dotenv(app_paths.env_file())
except Exception:
    pass

# Use an absolute import from the app root (same level as `workers/`).
from image_ops import preprocess_for_ocr, to_png8, to_webp_lossless

from PyQt6 import QtCore, QtWidgets


def main() -> int:
    """
    Funzione principale dell'applicazione.

    Inizializza Qt, esegue il pre-flight (verifica ambiente / primo avvio),
    carica la configurazione e mostra la finestra principale.

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

    # Pre-flight: file, chiave API, pesi DINOv2, warm-up. Esce se l'utente rinuncia.
    import bootstrap
    if not bootstrap.run_preflight(None):
        return 1

    # Import pesanti (LangChain/torch via MainWindow) solo a pre-flight superato.
    from config import AgentConfig
    from ui.main_window import MainWindow

    config = AgentConfig(app_paths.config_ini())

    show_debug = "--debug" in sys.argv
    window = MainWindow(config, show_debug=show_debug)
    window.show()

    # Hook per lo smoke test automatico: chiude l'app dopo pochi secondi.
    if os.getenv("EDGE_AGENT_SMOKE") == "1":
        QtCore.QTimer.singleShot(5000, app.quit)

    # Entra nel loop eventi Qt
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
