"""Entry point per l'applicazione Edge Agent."""

from __future__ import annotations

import os
import sys

import app_paths

# Da bundle windowed (console=False) sys.stdout/stderr sono None: qualunque
# print (torch.hub, tqdm, warning) manderebbe in crash chi scrive. Redirigiamo
# su un file di log accanto all'exe, utile anche per la diagnostica remota.
# Append con tetto di dimensione: "w" cancellerebbe il log del run precedente,
# che è l'unico artefatto diagnostico recuperabile da un utente remoto.
if sys.stdout is None or sys.stderr is None:
    try:
        _log_path = app_paths.app_dir() / "edge-agent.log"
        _mode = "w" if (_log_path.exists() and _log_path.stat().st_size > 1_000_000) else "a"
        _log = open(_log_path, _mode, encoding="utf-8", buffering=1)
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

from PyQt6 import QtCore, QtWidgets


def main() -> int:
    """
    Funzione principale dell'applicazione.

    Inizializza Qt, esegue il pre-flight (verifica ambiente / primo avvio),
    quindi mostra la finestra principale con la configurazione caricata.

    Returns:
        Exit code restituito da QApplication.exec().
    """
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Edge Agent")
    app.setOrganizationName("Tri-tech solutions")

    # An error in a slot would end the process and lose every unexported session.
    import error_report
    error_report.install_excepthook()

    # Own theme (light/dark like Windows), applied before the preflight so the
    # first-run dialog is styled too. theme.py is top-level and imports neither
    # `ui` nor `extraction` (import-order constraint, below).
    import theme
    theme.apply_theme(app)

    # Pre-flight: file, chiave API, pesi DINOv2, warm-up. Esce se l'utente rinuncia.
    import bootstrap
    config = bootstrap.run_preflight(None)
    if config is None:
        return 1

    # VINCOLO: questo import deve restare DOPO run_preflight(). La catena
    # ui.main_window → local_extraction_client → extraction.config fotografa
    # le env var (provider/modello/chiave) a import time, e il pre-flight
    # può crearle/caricarle proprio al primo avvio.
    # Da bundle windowed un'eccezione qui ucciderebbe il processo senza finestra:
    # il caso concreto è un catalogo prompts/ illeggibile in entrambe le copie.
    try:
        from ui.main_window import MainWindow
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        QtWidgets.QMessageBox.critical(
            None, "Edge Agent",
            "Avvio non riuscito: i componenti dell'applicazione non sono "
            f"caricabili.\n\nDettaglio: {exc}\n\n"
            "Se hai modificato i file in prompts/, ripristina il pacchetto originale.",
        )
        return 1

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
