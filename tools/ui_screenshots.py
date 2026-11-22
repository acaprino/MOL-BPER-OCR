"""Render the edge-agent window to PNG files, for visual review.

    python tools/ui_screenshots.py [--out outputs/ui-review] [--scale 1.5]

Writes {light,dark}-{capture,data,data-empty}.png. The window is drawn offscreen with
invented practices (no customer data): look at the files after every UI change, also
with --scale 1.5, which stands for Windows scaling at 150%.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent

# ============================================================
# Invented sample data
# ============================================================

_PRACTICES: List[Dict[str, Any]] = [
    {"ndg": "40100001", "denominazione": "Alfa Costruzioni S.r.l.", "tipo": "BPI Mutui", "stato": "In lavorazione",
     "fase": "Istruttoria", "creazione": "12/03/2026", "importo_euro": "250.000,00"},
    {"ndg": "40100002", "denominazione": "Beta Servizi S.p.A.", "tipo": "Fido a revoca", "stato": "Deliberata",
     "fase": "Perfezionamento", "creazione": "02/04/2026", "importo_euro": "80.000,00"},
    {"ndg": "40100003", "denominazione": "Gamma Agricola S.n.c.", "tipo": "BPI Mutui", "stato": "Aperta",
     "fase": "Istruttoria", "creazione": "18/05/2026", "importo_euro": "1.200.000,00"},
]


class _SamplePipeline:
    """The extraction boundary: replies with one invented practice per page type."""

    def extract_from_image(self, img: Any, screen_id: str) -> Dict[str, Any]:
        practice = _PRACTICES[int(screen_id.removeprefix("p")) - 1]
        fields = {key: {"value": value, "confidence": 1.0} for key, value in practice.items()}
        return {"screen_id": screen_id, "fields": fields, "_status": "OK"}


def _populate(client: Any, qapp: Any) -> str:
    """Run three invented practices through the client; return the session id."""
    from PIL import Image

    job = client.start_job()
    for index in range(len(_PRACTICES)):
        client.ingest_frame(job, Image.new("RGB", (10, 10)), page_type=f"p{index + 1}")
    deadline = time.time() + 10
    while len(client.get_results(job)) < len(_PRACTICES) and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    return job


# ============================================================
# Rendering
# ============================================================


def _grab(window: Any, qapp: Any, path: Path) -> None:
    window.show()
    qapp.processEvents()
    if not window.grab().save(str(path)):
        raise RuntimeError(f"Cannot write {path}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(REPO_ROOT / "outputs" / "ui-review"))
    parser.add_argument("--scale", type=float, default=1.0, help="Windows-like scaling, e.g. 1.5")
    args = parser.parse_args(argv)

    # Before any Qt or extraction import: both read the environment once.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("LLM_API_KEY", "screenshot-only")
    # The offscreen platform has no system fonts of its own: without this every
    # character is drawn as an empty box.
    windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    if windows_fonts.is_dir():
        os.environ.setdefault("QT_QPA_FONTDIR", str(windows_fonts))
    if args.scale != 1.0:
        os.environ["QT_SCALE_FACTOR"] = str(args.scale)
    for path in (REPO_ROOT / "src", REPO_ROOT / "src" / "edge-agent"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    import local_extraction_client as lec
    import theme
    from config import AgentConfig
    from ui.main_window import MainWindow

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    config = AgentConfig(config_path=Path(tempfile.gettempdir()) / "ui-screenshots-missing.ini")

    for scheme, name in ((Qt.ColorScheme.Light, "light"), (Qt.ColorScheme.Dark, "dark")):
        theme.apply_theme(app, scheme)

        client = lec.LocalExtractionClient(pipeline=_SamplePipeline())
        window = MainWindow(config, extraction_client=client)
        window.resize(1280, 800)
        job = _populate(client, app)
        window.capture_tab.job_id = job
        for line in ("Avvio cattura in modalità BPER.", "Elaborazione terminata: «p1» (stato: OK)",
                     "[ERROR] Esempio di riga di errore nel registro."):
            window.capture_tab._log(line)
        window.nav.set_current(0)
        _grab(window, app, out / f"{name}-capture.png")
        window.nav.set_current(1)
        window.data_tab.set_job_id(job)
        app.processEvents()
        _grab(window, app, out / f"{name}-data.png")
        window.hide()  # not close(): it would ask about the unexported sample data
        client.shutdown()

        empty_client = lec.LocalExtractionClient(pipeline=_SamplePipeline())
        empty = MainWindow(config, extraction_client=empty_client)
        empty.resize(1280, 800)
        empty.nav.set_current(1)
        _grab(empty, app, out / f"{name}-data-empty.png")
        empty.hide()
        empty_client.shutdown()

    theme.apply_theme(app)  # back to following the system, for whoever runs next
    print(f"Screenshots in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
